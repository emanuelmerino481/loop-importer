from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import yaml


DEFAULT_IGNORES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    "wandb", "mlruns",
}
SECRET_NAMES = {
    ".env", ".netrc", "credentials", "credentials.json", "secrets.yaml",
    "secrets.yml", "id_rsa", "id_ed25519",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
TEXT_SUFFIXES = {
    ".py", ".r", ".sh", ".bash", ".slurm", ".sbatch", ".yaml", ".yml",
    ".json", ".toml", ".ini", ".cfg", ".md", ".txt", ".csv", ".tsv",
    ".ipynb", ".sql", ".jl",
}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}
SCRIPT_SUFFIXES = {".py", ".r", ".sh", ".bash", ".slurm", ".sbatch", ".jl"}
DATA_SUFFIXES = {".csv", ".tsv", ".parquet", ".feather", ".h5", ".hdf5", ".lmdb", ".npy", ".npz"}
CHECKPOINT_SUFFIXES = {".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".pkl", ".joblib"}
RESULT_SUFFIXES = {".json", ".csv", ".tsv", ".html", ".pdf", ".png", ".svg"}
ENTRYPOINT_WORDS = {
    "prepare": ("prepare", "preprocess", "build_data", "dataset", "tokenize"),
    "train": ("train", "fit", "finetune"),
    "infer": ("infer", "predict", "generate", "sample"),
    "evaluate": ("eval", "evaluate", "metric", "score", "benchmark", "test"),
    "report": ("report", "plot", "figure", "visualize", "summary"),
}


@dataclass(frozen=True)
class ImportOptions:
    project_id: str
    max_files: int = 50_000
    max_text_bytes: int = 262_144
    hash_max_bytes: int = 1_048_576


class ImportProjectError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def _is_secret(path: Path) -> bool:
    name = path.name.lower()
    return name in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES or any(
        token in name for token in ("secret", "credential", "private_key", "api_key")
    )


def _category(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    suffix = path.suffix.lower()
    stem = path.stem.lower()
    if _is_secret(path):
        return "secret_redacted"
    if suffix in CHECKPOINT_SUFFIXES or parts & {"checkpoint", "checkpoints", "weights", "models"}:
        return "checkpoint"
    if suffix in DATA_SUFFIXES or parts & {"data", "dataset", "datasets", "raw", "processed"}:
        return "data"
    if suffix in SCRIPT_SUFFIXES:
        return "script"
    if suffix in CONFIG_SUFFIXES or parts & {"config", "configs", "conf"}:
        return "config"
    if parts & {"result", "results", "output", "outputs", "figures", "reports", "logs"}:
        return "result_or_log"
    if suffix in RESULT_SUFFIXES and any(word in stem for word in ("result", "metric", "score", "report", "figure")):
        return "result_or_log"
    if path.name.lower() in {"readme.md", "agents.md", "claude.md", "contributing.md"}:
        return "documentation"
    return "other"


def _language(path: Path) -> str | None:
    return {
        ".py": "Python", ".r": "R", ".sh": "Shell", ".bash": "Shell",
        ".slurm": "Slurm", ".sbatch": "Slurm", ".jl": "Julia",
        ".ipynb": "Jupyter", ".sql": "SQL",
    }.get(path.suffix.lower())


def _sanitize_remote(remote: str | None) -> str | None:
    if not remote or "://" not in remote:
        return remote
    try:
        parsed = urlsplit(remote)
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return "REDACTED_INVALID_REMOTE"


def _git_metadata(source: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(source), *args], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10, check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    commit = run("rev-parse", "HEAD")
    root = run("rev-parse", "--show-toplevel")
    status = run("status", "--porcelain=v1")
    remote = run("remote", "get-url", "origin")
    return {
        "is_repository": bool(commit and root),
        "root": root,
        "commit": commit,
        "dirty": bool(status) if status is not None else None,
        "changed_path_count": len(status.splitlines()) if status else 0,
        "origin": _sanitize_remote(remote),
    }


def _iter_files(source: Path, output: Path, max_files: int) -> Iterable[Path]:
    count = 0
    output_resolved = output.resolve()
    for current, directories, filenames in os.walk(source, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if name not in DEFAULT_IGNORES
            and not (current_path / name).is_symlink()
            and (current_path / name).resolve() != output_resolved
        ]
        for filename in sorted(filenames):
            path = current_path / filename
            if path.is_symlink():
                continue
            count += 1
            if count > max_files:
                raise ImportProjectError(f"file limit exceeded: {max_files}")
            yield path


def _read_signal_text(path: Path, limit: int) -> str:
    if _is_secret(path) or path.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _task_kind(path: Path) -> str | None:
    value = path.as_posix().lower()
    for kind, words in ENTRYPOINT_WORDS.items():
        if any(word in value for word in words):
            return kind
    return None


def _build_task_candidates(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if entry["category"] != "script":
            continue
        kind = _task_kind(Path(entry["path"]))
        if not kind:
            continue
        key = (kind, entry["path"])
        if key in seen:
            continue
        seen.add(key)
        task_id = _stable_id(f"IMPORT-{kind.upper()}", entry["path"])
        dependencies: list[str] = []
        prior = {task["kind"]: task["task_id"] for task in tasks}
        if kind == "train" and "prepare" in prior:
            dependencies.append(prior["prepare"])
        elif kind == "infer" and "train" in prior:
            dependencies.append(prior["train"])
        elif kind == "evaluate":
            if "infer" in prior:
                dependencies.append(prior["infer"])
            elif "train" in prior:
                dependencies.append(prior["train"])
        elif kind == "report" and "evaluate" in prior:
            dependencies.append(prior["evaluate"])
        tasks.append({
            "task_id": task_id,
            "kind": kind,
            "entrypoint": entry["path"],
            "depends_on_candidates": dependencies,
            "confidence": "LOW",
            "evidence": [entry["artifact_id"]],
            "status": "DRAFT_HUMAN_REVIEW",
        })
        if len(tasks) >= 100:
            break
    return tasks


def _write_yaml(path: Path, value: Any) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def import_project(source: str | Path, output: str | Path, options: ImportOptions) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if not source_path.is_dir():
        raise ImportProjectError(f"source is not a directory: {source_path}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}", options.project_id):
        raise ImportProjectError("project_id must be 2-64 safe characters")
    if source_path == output_path or source_path in output_path.parents:
        raise ImportProjectError("output must be outside the imported project")

    output_path.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    language_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()

    for path in _iter_files(source_path, output_path, options.max_files):
        relative = path.relative_to(source_path).as_posix()
        stat = path.stat()
        category = _category(Path(relative))
        language = _language(path)
        if language:
            language_counts[language] += 1
        category_counts[category] += 1
        text = _read_signal_text(path, options.max_text_bytes)
        lower = text.lower()
        for signal in ("seed", "cuda", "slurm", "metric", "checkpoint", "wandb", "mlflow"):
            if signal in lower:
                signal_counts[signal] += 1
        redacted = category == "secret_redacted"
        digest = None
        if not redacted and stat.st_size <= options.hash_max_bytes:
            digest = _sha256(path)
        artifacts.append({
            "artifact_id": _stable_id("ART", relative),
            "path": relative,
            "category": category,
            "size_bytes": stat.st_size,
            "sha256": digest,
            "hash_status": "COMPUTED" if digest else ("REDACTED" if redacted else "SKIPPED_SIZE_LIMIT"),
            "redacted": redacted,
            "language": language,
        })

    git = _git_metadata(source_path)
    tasks = _build_task_candidates(artifacts)
    generated_at = _utc_now()
    manifest = {
        "schema_version": "1.0",
        "import_status": "DRAFT_HUMAN_REVIEW",
        "project_id": options.project_id,
        "generated_at": generated_at,
        "source_root": str(source_path),
        "source_mutated": False,
        "scanner_limits": asdict(options),
        "git": git,
        "summary": {
            "file_count": len(artifacts),
            "total_bytes": sum(item["size_bytes"] for item in artifacts),
            "categories": dict(category_counts),
            "languages": dict(language_counts),
            "text_signals": dict(signal_counts),
        },
    }
    def review_question(
        question_id: str,
        prompt: str,
        recommendation: str,
        evidence_categories: tuple[str, ...] = (),
        depends_on: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        evidence = [
            item["artifact_id"] for item in artifacts
            if item["category"] in evidence_categories
        ][:20]
        return {
            "id": question_id,
            "question": prompt,
            "agent_recommended_answer": recommendation,
            "evidence_candidates": evidence,
            "depends_on": list(depends_on),
            "human_answer": None,
            "human_verdict": "PENDING",
            "correction_or_notes": None,
            "resolution_status": "OPEN",
            "required": True,
        }

    questions = [
        review_question(
            "Q-PRIMARY-GOAL", "正式科研目标和非目标是什么？",
            "用一个可证伪的主目标描述成功，并明确至少一个非目标；不要从 README 自动升级为正式目标。",
            ("documentation",),
        ),
        review_question(
            "Q-DATASET", "哪一份数据及其版本/hash 是正式输入？",
            "选择唯一正式数据版本，并通过单独获批的证据任务计算 hash；本次扫描结果只能作为候选。",
            ("data",), ("Q-PRIMARY-GOAL",),
        ),
        review_question(
            "Q-METRIC", "主指标、辅助指标、统计单位和成功阈值是什么？",
            "先定义 estimand、实验单位和聚合口径，再冻结一个主指标；不得从结果文件名反推正式指标。",
            ("script", "config", "result_or_log"), ("Q-PRIMARY-GOAL", "Q-DATASET"),
        ),
        review_question(
            "Q-SEEDS", "正式 seed 列表及失败 seed 保留策略是什么？",
            "显式列出全部正式 seed，成功与失败均保留；日志中出现的 seed 只是候选。",
            ("script", "config", "result_or_log"), ("Q-METRIC",),
        ),
        review_question(
            "Q-BASELINE", "正式 baseline、当前最佳结果和对应 commit/config/checkpoint 是什么？",
            "baseline 与最佳结果都应绑定 commit、配置、数据版本、seed、checkpoint 和原始评价输出。",
            ("checkpoint", "config", "result_or_log"), ("Q-DATASET", "Q-METRIC", "Q-SEEDS"),
        ),
        review_question(
            "Q-GPU", "GPU 型号、数量、GPU-hours 预算和停止条件是什么？",
            "先做受限 GPU pilot，再确定批量、精度、吞吐和 GPU-hours 上限；未知异常默认停止并报告。",
            ("script", "config", "result_or_log"), ("Q-SEEDS",),
        ),
        review_question(
            "Q-PROTECTED", "哪些路径、评价器、协议和阈值必须冻结？",
            "至少保护原始数据、主评价器、冻结协议、成功阈值和历史 run，并由人工确认例外。",
            ("data", "script", "config"), ("Q-METRIC",),
        ),
    ]
    if not git["is_repository"]:
        questions.append(review_question(
            "Q-VERSIONING", "项目没有可识别 Git commit，采用什么版本标识？",
            "先创建可审计的代码快照或 commit；在此之前不得启动正式实验。",
        ))
    if not tasks:
        questions.append(review_question(
            "Q-ENTRYPOINTS", "训练、推理和评价的正式入口命令是什么？",
            "从已成功日志和调度记录交叉核对完整 argv、工作目录与环境，不凭脚本名猜测。",
            ("script", "result_or_log"),
        ))

    registry = {
        "schema_version": "1.0",
        "project_id": options.project_id,
        "generated_at": generated_at,
        "status": "DRAFT_HUMAN_REVIEW",
        "artifacts": artifacts,
    }
    dag = {
        "schema_version": "1.0",
        "project_id": options.project_id,
        "status": "DRAFT_HUMAN_REVIEW",
        "warning": "Dependencies are lexical candidates, not verified scientific workflow facts.",
        "tasks": tasks,
    }
    _write_yaml(output_path / "project-manifest.yaml", manifest)
    _write_yaml(output_path / "artifact-registry.yaml", registry)
    _write_yaml(output_path / "task-dag.yaml", dag)
    review_session = {
        "schema_version": "1.0",
        "project_id": options.project_id,
        "status": "HUMAN_REVIEW_REQUIRED",
        "interaction_policy": {
            "one_question_at_a_time": True,
            "inspect_available_evidence_before_asking": True,
            "provide_recommended_answer": True,
            "wait_for_human_answer": True,
            "do_not_activate_before_all_required_resolved": True,
            "allowed_verdicts": [
                "PENDING", "CONFIRM_CORRECT", "CORRECTED",
                "REJECT_INFERENCE", "NEEDS_EVIDENCE",
            ],
        },
        "questions": questions,
    }
    _write_yaml(output_path / "open-questions.yaml", review_session)
    _write_yaml(output_path / "review-session.yaml", review_session)
    _write_json(output_path / "import-summary.json", manifest)
    bootstrap = (
        f"# {options.project_id} 导入草案\n\n"
        f"状态：`DRAFT_HUMAN_REVIEW`\n\n"
        f"只读扫描源：`{source_path}`\n\n"
        f"已登记 {len(artifacts)} 个文件，推断 {len(tasks)} 个任务候选。"
        "所有任务依赖、指标、正式数据、seed、baseline 和阈值都必须人工确认后才能进入 Harness。\n"
    )
    (output_path / "bootstrap.md").write_text(bootstrap, encoding="utf-8", newline="\n")
    rows = "".join(
        f"<tr><td>{html.escape(key)}</td><td>{value}</td></tr>"
        for key, value in sorted(category_counts.items())
    )
    report = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(options.project_id)} 导入审核</title>
<style>body{{font-family:system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 20px;color:#172033}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd5e0;padding:8px;text-align:left}}.warn{{background:#fff4ce;padding:12px;border-left:4px solid #d89b00}}</style></head>
<body><h1>{html.escape(options.project_id)} 项目导入审核</h1><p class="warn">当前仅为 DRAFT_HUMAN_REVIEW，不得据此启动实验。</p>
<p>扫描文件：{len(artifacts)}；任务候选：{len(tasks)}；Git commit：{html.escape(str(git['commit'] or '未识别'))}</p>
<h2>文件分类</h2><table><tr><th>类别</th><th>数量</th></tr>{rows}</table>
<h2>必须人工确认</h2><ol>{''.join(f'<li><strong>{html.escape(q["question"])}</strong><br>建议：{html.escape(q["agent_recommended_answer"])}<br>人工判定：{q["human_verdict"]}</li>' for q in questions)}</ol></body></html>"""
    (output_path / "import-report.html").write_text(report, encoding="utf-8", newline="\n")
    return {
        "status": "DRAFT_HUMAN_REVIEW",
        "project_id": options.project_id,
        "output": str(output_path),
        "file_count": len(artifacts),
        "task_candidate_count": len(tasks),
        "required_question_count": len(questions),
    }
