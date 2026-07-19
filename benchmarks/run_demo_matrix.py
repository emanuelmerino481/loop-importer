from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from loop_importer import (
    ImportOptions,
    build_context_bundle,
    import_project,
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "benchmarks" / "demo-matrix-results.json"
VALIDATOR = ROOT / "skills" / "loop-importer" / "scripts" / "validate_import.py"
RESEARCH_FIXTURE = ROOT / "examples" / "incomplete-research-project"

PUBLIC_REPOSITORIES = (
    {
        "name": "micrograd",
        "repository": "karpathy/micrograd",
        "url": "https://github.com/karpathy/micrograd",
        "commit": "c911406e5ace8742e5841a7e0df113ecb5d54685",
        "purpose": "small Python ML library",
    },
    {
        "name": "nanoGPT",
        "repository": "karpathy/nanoGPT",
        "url": "https://github.com/karpathy/nanoGPT",
        "commit": "3adf61e154c3fe3fca428ad6bc3818b27a3b8291",
        "purpose": "script-and-config training repository",
    },
    {
        "name": "cookiecutter-data-science",
        "repository": "drivendataorg/cookiecutter-data-science",
        "url": "https://github.com/drivendataorg/cookiecutter-data-science",
        "commit": "0f6b163cdbe3918a2c65ab57ad9fefda93976d9e",
        "purpose": "templated data-science project layout",
    },
    {
        "name": "alphafold2",
        "repository": "lucidrains/alphafold2",
        "url": "https://github.com/lucidrains/alphafold2",
        "commit": "931466e487e1be87d1182b17ed4ecfac9e70948d",
        "purpose": "protein-model research implementation",
    },
)


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tree_digest(root: Path) -> str:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if ".git" in path.relative_to(root).parts:
            continue
        entries.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return _canonical_digest(entries)


def _tested_code_paths() -> list[Path]:
    return [
        *sorted((ROOT / "src" / "loop_importer").glob("*.py")),
        Path(__file__).resolve(),
        VALIDATOR,
        ROOT / "pyproject.toml",
    ]


def _portable_source_sha256(path: Path) -> str:
    """Hash UTF-8 source with canonical LF newlines across Git checkouts."""
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        canonical = payload
    else:
        canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _runner_source_digest() -> str:
    paths = _tested_code_paths()
    return _canonical_digest([
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": _portable_source_sha256(path),
        }
        for path in paths
    ])


def _run(command: list[str], cwd: Path | None = None, timeout: int = 300) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stderr[-2000:]}"
        )
    return completed.stdout.strip()


def _validate_packet(packet: Path) -> str:
    output = _run([sys.executable, str(VALIDATOR), str(packet)], cwd=ROOT)
    if output != "IMPORT_PACKET_VALID":
        raise RuntimeError(f"unexpected packet validation output: {output}")
    return output


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _packet_metrics(packet: Path) -> dict[str, Any]:
    summary = _load_json(packet / "import-summary.json")
    graph = _load_json(packet / "code-graph.json")
    baseline = _load_yaml(packet / "knowledge-baseline.yaml")
    registry = _load_yaml(packet / "artifact-registry.yaml")
    dag = _load_yaml(packet / "task-dag.yaml")
    return {
        "validation": _validate_packet(packet),
        "status": summary["import_status"],
        "source_mutated": summary["source_mutated"],
        "file_count": summary["summary"]["file_count"],
        "task_candidate_count": len(dag.get("tasks", [])),
        "redacted_artifact_count": sum(
            bool(item.get("redacted")) for item in registry.get("artifacts", [])
        ),
        "knowledge_fact_count": baseline["summary"]["fact_count"],
        "knowledge_validity": baseline["summary"]["validity"],
        "python_file_count": graph["summary"]["python_file_count"],
        "code_node_count": graph["summary"]["node_count"],
        "code_edge_count": graph["summary"]["edge_count"],
        "parse_error_count": graph["summary"]["parse_error_count"],
        "unresolved_call_count": graph["summary"]["unresolved_call_count"],
        "incremental": graph["incremental"],
    }


def _standard_import(
    source: Path,
    packet: Path,
    project_id: str,
    options: ImportOptions | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_options = options or ImportOptions(project_id=project_id)
    import_project(source, packet, selected_options)
    first = _packet_metrics(packet)
    import_project(source, packet, selected_options)
    second = _packet_metrics(packet)
    return first, second


def _base_demo_result(
    name: str,
    purpose: str,
    first: dict[str, Any],
    second: dict[str, Any],
    checks: dict[str, bool],
) -> dict[str, Any]:
    if not all(checks.values()):
        failed = sorted(key for key, passed in checks.items() if not passed)
        raise AssertionError(f"{name} failed checks: {failed}")
    return {
        "name": name,
        "purpose": purpose,
        "result": "PASS",
        "checks": checks,
        "metrics": {
            key: second[key]
            for key in (
                "validation",
                "status",
                "source_mutated",
                "file_count",
                "task_candidate_count",
                "redacted_artifact_count",
                "knowledge_fact_count",
                "knowledge_validity",
                "python_file_count",
                "code_node_count",
                "code_edge_count",
                "parse_error_count",
                "unresolved_call_count",
            )
        },
        "second_import": {
            "parsed_file_count": second["incremental"]["parsed_file_count"],
            "reused_file_count": second["incremental"]["reused_file_count"],
            "first_import_parsed_file_count": first["incremental"]["parsed_file_count"],
        },
    }


def _research_demo(root: Path) -> dict[str, Any]:
    source = root / "source"
    packet = root / "packet"
    shutil.copytree(RESEARCH_FIXTURE, source)
    before = _tree_digest(source)
    first, second = _standard_import(source, packet, "DEMO-RESEARCH")
    after = _tree_digest(source)
    bundle = build_context_bundle(
        _load_yaml(packet / "knowledge-baseline.yaml"),
        _load_json(packet / "code-graph.json"),
        "train metric dataset seed",
        max_payload_bytes=4_096,
    )
    result = _base_demo_result(
        "incomplete-research-project",
        "conflicting research artifacts and one secret-like file",
        first,
        second,
        {
            "source_tree_unchanged": before == after,
            "secret_redacted": second["redacted_artifact_count"] == 1,
            "context_selected_facts": bundle["selected"]["fact_count"] > 0,
            "context_selected_code": bundle["selected"]["code_node_count"] > 0,
            "unchanged_graph_reused": second["incremental"]["reused_file_count"]
            == second["python_file_count"],
        },
    )
    result["context"] = {
        "query": "train metric dataset seed",
        "payload_bytes": bundle["payload_bytes"],
        "selected": bundle["selected"],
    }
    return result


def _package_demo(root: Path) -> dict[str, Any]:
    source = root / "source"
    packet = root / "packet"
    package = source / "protein_model"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "encoder.py").write_text(
        "class Encoder:\n"
        "    def encode(self, sequence):\n"
        "        return sequence.upper()\n",
        encoding="utf-8",
    )
    (package / "train.py").write_text(
        "from .encoder import Encoder as SequenceEncoder\n\n"
        "def train(sequence):\n"
        "    model = SequenceEncoder()\n"
        "    return model.encode(sequence)\n",
        encoding="utf-8",
    )
    before = _tree_digest(source)
    first, second = _standard_import(source, packet, "DEMO-PACKAGE")
    after = _tree_digest(source)
    graph = _load_json(packet / "code-graph.json")
    edge_kinds = {edge["kind"] for edge in graph["edges"]}
    return _base_demo_result(
        "python-package-aliases",
        "relative imports, aliases, classes, methods, and calls",
        first,
        second,
        {
            "source_tree_unchanged": before == after,
            "import_edge_resolved": "IMPORTS" in edge_kinds,
            "call_edge_resolved": "CALLS" in edge_kinds,
            "no_parse_errors": second["parse_error_count"] == 0,
            "unchanged_graph_reused": second["incremental"]["reused_file_count"]
            == second["python_file_count"],
        },
    )


def _broken_dynamic_demo(root: Path) -> dict[str, Any]:
    source = root / "source"
    packet = root / "packet"
    source.mkdir()
    (source / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    (source / "dynamic.py").write_text(
        "def factory():\n"
        "    return lambda: 1\n\n"
        "def run():\n"
        "    return factory()()\n",
        encoding="utf-8",
    )
    before = _tree_digest(source)
    first, second = _standard_import(source, packet, "DEMO-BROKEN")
    after = _tree_digest(source)
    graph = _load_json(packet / "code-graph.json")
    result = _base_demo_result(
        "broken-and-dynamic-python",
        "syntax errors and dynamic calls remain explicit instead of guessed",
        first,
        second,
        {
            "source_tree_unchanged": before == after,
            "syntax_error_recorded": second["parse_error_count"] == 1,
            "dynamic_call_unresolved": any(
                item["reason"] == "DYNAMIC_EXPRESSION"
                for item in graph["unresolved_calls"]
            ),
            "packet_still_valid": second["validation"] == "IMPORT_PACKET_VALID",
        },
    )
    result["parse_error_evidence"] = [
        {
            "path": item["path"],
            "kind": item["kind"],
            "line": item["line"],
            "message": item["message"],
        }
        for item in graph["parse_errors"]
    ]
    return result


def _safety_bounds_demo(root: Path) -> dict[str, Any]:
    source = root / "source"
    packet = root / "packet"
    source.mkdir()
    marker = "DEMO_TOKEN_MUST_NOT_LEAK_7f5b"
    (source / ".env").write_text(f"API_TOKEN={marker}\n", encoding="utf-8")
    (source / "large_train.py").write_text(
        "def train():\n    return '" + ("x" * 1_024) + "'\n",
        encoding="utf-8",
    )
    options = ImportOptions(
        project_id="DEMO-SAFETY", max_text_bytes=128, hash_max_bytes=256
    )
    before = _tree_digest(source)
    first, second = _standard_import(
        source, packet, "DEMO-SAFETY", options=options
    )
    after = _tree_digest(source)
    packet_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in packet.iterdir()
        if path.is_file()
    )
    return _base_demo_result(
        "secret-and-size-bounds",
        "secret redaction plus hash and AST size limits",
        first,
        second,
        {
            "source_tree_unchanged": before == after,
            "secret_redacted": second["redacted_artifact_count"] == 1,
            "secret_value_absent": marker not in packet_text,
            "oversized_code_not_parsed": second["python_file_count"] == 1
            and second["code_node_count"] == 0,
            "unhashed_fact_unverified": second["knowledge_validity"].get("UNVERIFIED")
            == 1,
        },
    )


def _evidence_drift_demo(root: Path) -> dict[str, Any]:
    source = root / "source"
    packet = root / "packet"
    source.mkdir()
    train = source / "train.py"
    train.write_text("def train():\n    return 1\n", encoding="utf-8")
    import_project(source, packet, ImportOptions(project_id="DEMO-DRIFT"))
    registry = _load_yaml(packet / "artifact-registry.yaml")
    artifact = next(item for item in registry["artifacts"] if item["path"] == "train.py")
    baseline_path = packet / "knowledge-baseline.yaml"
    baseline = _load_yaml(baseline_path)
    baseline["facts"].append({
        "fact_id": "FACT-HUMAN-TRAIN",
        "kind": "entrypoint_decision",
        "statement": "The confirmed training entrypoint is train.py.",
        "value": "train.py",
        "topics": ["train", "entrypoint"],
        "epistemic_status": "HUMAN_CONFIRMED",
        "validity": "CURRENT",
        "origin": "HUMAN",
        "evidence": [{
            "artifact_id": artifact["artifact_id"],
            "path": artifact["path"],
            "sha256": artifact["sha256"],
        }],
        "requires_human_review": False,
    })
    baseline_path.write_text(
        yaml.safe_dump(baseline, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    train.write_text("def train():\n    return 2\n", encoding="utf-8")
    import_project(source, packet, ImportOptions(project_id="DEMO-DRIFT"))
    metrics = _packet_metrics(packet)
    refreshed = _load_yaml(baseline_path)
    graph = _load_json(packet / "code-graph.json")
    human = next(
        fact for fact in refreshed["facts"] if fact["fact_id"] == "FACT-HUMAN-TRAIN"
    )
    bundle = build_context_bundle(refreshed, graph, "confirmed train entrypoint")
    selected_ids = {fact["fact_id"] for fact in bundle["payload"]["facts"]}
    checks = {
        "changed_file_reparsed": metrics["incremental"]["parsed_file_count"] == 1,
        "graph_nodes_marked_stale": bool(metrics["incremental"]["stale_node_ids"]),
        "human_fact_marked_stale": human["validity"] == "STALE",
        "stale_fact_excluded": "FACT-HUMAN-TRAIN" not in selected_ids,
        "packet_still_valid": metrics["validation"] == "IMPORT_PACKET_VALID",
    }
    if not all(checks.values()):
        raise AssertionError(
            "evidence-drift failed checks: "
            + ", ".join(key for key, value in checks.items() if not value)
        )
    return {
        "name": "evidence-drift",
        "purpose": "human decision invalidation after its cited artifact changes",
        "result": "PASS",
        "checks": checks,
        "metrics": {
            key: metrics[key]
            for key in (
                "validation",
                "status",
                "source_mutated",
                "file_count",
                "task_candidate_count",
                "knowledge_fact_count",
                "knowledge_validity",
                "python_file_count",
                "code_node_count",
                "code_edge_count",
                "parse_error_count",
                "unresolved_call_count",
            )
        },
        "change_import": {
            "parsed_file_count": metrics["incremental"]["parsed_file_count"],
            "reused_file_count": metrics["incremental"]["reused_file_count"],
            "stale_node_count": len(metrics["incremental"]["stale_node_ids"]),
            "stale_fact_excluded": True,
        },
    }


def _deletion_demo(root: Path) -> dict[str, Any]:
    source = root / "source"
    packet = root / "packet"
    source.mkdir()
    (source / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    removable = source / "b.py"
    removable.write_text("def b():\n    return 2\n", encoding="utf-8")
    import_project(source, packet, ImportOptions(project_id="DEMO-DELETE"))
    removable.unlink()
    import_project(source, packet, ImportOptions(project_id="DEMO-DELETE"))
    metrics = _packet_metrics(packet)
    checks = {
        "unchanged_fragment_reused": metrics["incremental"]["reused_file_count"] == 1,
        "removed_artifact_reported": len(metrics["incremental"]["removed_artifact_ids"])
        == 1,
        "removed_nodes_reported": len(metrics["incremental"]["removed_node_ids"]) == 2,
        "packet_still_valid": metrics["validation"] == "IMPORT_PACKET_VALID",
    }
    if not all(checks.values()):
        raise AssertionError(
            "deleted-evidence failed checks: "
            + ", ".join(key for key, value in checks.items() if not value)
        )
    return {
        "name": "deleted-evidence",
        "purpose": "removed source files invalidate their cached graph fragments",
        "result": "PASS",
        "checks": checks,
        "metrics": {
            key: metrics[key]
            for key in (
                "validation",
                "status",
                "source_mutated",
                "file_count",
                "task_candidate_count",
                "knowledge_fact_count",
                "knowledge_validity",
                "python_file_count",
                "code_node_count",
                "code_edge_count",
                "parse_error_count",
                "unresolved_call_count",
            )
        },
        "deletion_import": {
            "parsed_file_count": metrics["incremental"]["parsed_file_count"],
            "reused_file_count": metrics["incremental"]["reused_file_count"],
            "removed_artifact_count": len(
                metrics["incremental"]["removed_artifact_ids"]
            ),
            "removed_node_count": len(metrics["incremental"]["removed_node_ids"]),
        },
    }


CONTROLLED_DEMOS: tuple[Callable[[Path], dict[str, Any]], ...] = (
    _research_demo,
    _package_demo,
    _broken_dynamic_demo,
    _safety_bounds_demo,
    _evidence_drift_demo,
    _deletion_demo,
)


def run_controlled_matrix(work_root: Path) -> list[dict[str, Any]]:
    results = []
    for index, runner in enumerate(CONTROLLED_DEMOS, start=1):
        scenario_root = work_root / f"controlled-{index:02d}"
        scenario_root.mkdir(parents=True)
        results.append(runner(scenario_root))
    return results


def _download_public_repository(spec: dict[str, str], destination: Path) -> str:
    archive_url = (
        f"https://codeload.github.com/{spec['repository']}/zip/{spec['commit']}"
    )
    request = urllib.request.Request(
        archive_url, headers={"User-Agent": "loop-importer-demo-matrix/1.0"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        archive_bytes = response.read()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    destination.mkdir(parents=True)
    destination_root = destination.resolve()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        for info in archive.infolist():
            parts = Path(info.filename).parts
            if len(parts) <= 1:
                continue
            relative = Path(*parts[1:])
            target = (destination / relative).resolve()
            if (
                target == destination_root
                or destination_root not in target.parents
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                raise RuntimeError(f"unsafe archive path: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
    return archive_sha256


def run_public_matrix(work_root: Path) -> list[dict[str, Any]]:
    work_root.mkdir(parents=True, exist_ok=True)
    results = []
    for index, original_spec in enumerate(PUBLIC_REPOSITORIES, start=1):
        spec = deepcopy(original_spec)
        source = work_root / f"public-{index:02d}-source"
        packet = work_root / f"public-{index:02d}-packet"
        archive_sha256 = _download_public_repository(spec, source)
        before = _tree_digest(source)
        first, second = _standard_import(
            source,
            packet,
            f"PUBLIC-{index:02d}-{spec['name'].upper().replace('_', '-')}",
        )
        after = _tree_digest(source)
        checks = {
            "pinned_commit_archive_loaded": bool(archive_sha256),
            "source_tree_unchanged": before == after,
            "packet_valid": second["validation"] == "IMPORT_PACKET_VALID",
            "unchanged_graph_reused": second["incremental"]["reused_file_count"]
            == second["python_file_count"],
        }
        result = _base_demo_result(
            spec["name"], spec["purpose"], first, second, checks
        )
        result["repository"] = spec["repository"]
        result["url"] = spec["url"]
        result["commit"] = spec["commit"]
        result["commit_url"] = f"{spec['url']}/commit/{spec['commit']}"
        result["source_archive_sha256"] = archive_sha256
        result["source_tree_digest_before"] = before
        result["source_tree_digest_after"] = after
        graph = _load_json(packet / "code-graph.json")
        result["parse_error_evidence"] = [
            {
                "path": item["path"],
                "kind": item["kind"],
                "line": item["line"],
                "message": item["message"],
            }
            for item in graph["parse_errors"]
        ]
        results.append(result)
    return results


def build_result(
    controlled: list[dict[str, Any]], public: list[dict[str, Any]]
) -> dict[str, Any]:
    all_results = [*controlled, *public]
    result = {
        "schema_version": "1.0",
        "benchmark": "read-only-import-demo-matrix",
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runner": {
            "runner_version": "1.0",
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "loop_importer_git_commit": _run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT
            ),
            "loop_importer_worktree_dirty": bool(
                _run(["git", "status", "--porcelain=v1"], cwd=ROOT)
            ),
            "tested_code_digest": _runner_source_digest(),
            "tested_code_digest_algorithm": (
                "SHA-256 of canonical UTF-8 JSON containing sorted repository-relative "
                "paths and each file's SHA-256 after UTF-8 newline normalization to LF."
            ),
            "tested_code_paths": [
                path.relative_to(ROOT).as_posix() for path in _tested_code_paths()
            ],
        },
        "pass_definition": (
            "PASS means every scenario-specific assertion passed and the generated packet "
            "returned IMPORT_PACKET_VALID. Expected, explicitly recorded parse errors may be "
            "present; PASS does not mean every source file parsed successfully."
        ),
        "count_definitions": {
            "file_count": "Final source-snapshot files observed by the bounded scanner.",
            "python_file_count": "Observed non-redacted Python artifacts, including files skipped or reporting parse errors.",
            "code_node_count": "Static module, class, function, and method nodes accepted into the final graph.",
            "code_edge_count": "Resolved CONTAINS, IMPORTS, and CALLS structural edges in the final graph.",
        },
        "source_tree_digest_algorithm": (
            "SHA-256 of canonical UTF-8 JSON containing repository-relative POSIX paths "
            "and raw-byte SHA-256 values for all recursively sorted files; .git paths, "
            "directories, timestamps, permissions, and other filesystem metadata are excluded."
        ),
        "scope": (
            "Six controlled synthetic scenarios and four pinned public GitHub snapshots. "
            "Source code was never executed. Public source trees were compared before and "
            "after import and remained unchanged. source_mutated is the importer's own claim; "
            "the evidence-drift and deletion fixtures intentionally change source files between "
            "imports in the benchmark harness."
        ),
        "summary": {
            "demo_count": len(all_results),
            "controlled_demo_count": len(controlled),
            "public_repository_count": len(public),
            "passed_count": sum(item["result"] == "PASS" for item in all_results),
            "packet_valid_count": sum(
                item["metrics"]["validation"] == "IMPORT_PACKET_VALID"
                for item in all_results
            ),
            "source_mutation_claim_count": sum(
                item["metrics"]["source_mutated"] is not False for item in all_results
            ),
            "total_files_observed": sum(
                item["metrics"]["file_count"] for item in all_results
            ),
            "total_python_files": sum(
                item["metrics"]["python_file_count"] for item in all_results
            ),
            "total_code_nodes": sum(
                item["metrics"]["code_node_count"] for item in all_results
            ),
            "total_code_edges": sum(
                item["metrics"]["code_edge_count"] for item in all_results
            ),
        },
        "controlled_demos": controlled,
        "public_repositories": public,
        "result_digest_algorithm": (
            "SHA-256 of canonical UTF-8 JSON with sorted keys and compact separators, "
            "computed before the result_digest field is added."
        ),
    }
    result["result_digest"] = _canonical_digest(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--controlled-only",
        action="store_true",
        help="Run local controlled demos without cloning public repositories.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="loop-importer-demo-matrix-") as temp:
        work_root = Path(temp)
        controlled = run_controlled_matrix(work_root / "controlled")
        public = [] if args.controlled_only else run_public_matrix(work_root / "public")
    result = build_result(controlled, public)
    output = args.output or (None if args.controlled_only else RESULTS_PATH)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
