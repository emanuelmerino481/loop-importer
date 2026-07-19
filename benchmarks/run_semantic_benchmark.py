from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "benchmarks" / "semantic-fixture.json"
RUNS_ROOT = ROOT / "benchmarks" / "semantic-runs"
RESULTS_PATH = ROOT / "benchmarks" / "semantic-benchmark-results.json"
CHART_PATH = ROOT / "docs" / "semantic-benchmark.svg"
SCHEMA_PATH = RUNS_ROOT / "summary-schema.json"
RUN_METADATA_PATH = RUNS_ROOT / "run-metadata.json"


def _fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }


def _structured_round(fixture: dict[str, Any], round_number: int) -> str:
    facts = fixture["gold_facts"]
    keys = fixture["rounds"][round_number - 1]["structured_facts"]
    records = [
        {
            "field": key,
            "value": facts[key]["value"],
            "evidence_id": facts[key]["evidence_id"],
            "epistemic_status": "HUMAN_CONFIRMED",
            "validity": "CURRENT",
        }
        for key in keys
    ]
    return json.dumps(records, ensure_ascii=False, indent=2)


def _full_context(fixture: dict[str, Any], mode: str) -> str:
    if mode == "raw":
        return "\n\n".join(
            f"[{item['artifact_id']}]\n{item['raw_text']}" for item in fixture["rounds"]
        )
    records = []
    for round_number in range(1, len(fixture["rounds"]) + 1):
        records.extend(json.loads(_structured_round(fixture, round_number)))
    return json.dumps(records, ensure_ascii=False, indent=2)


def _summary_prompt(context: str, word_limit: int) -> str:
    return f"""You are evaluating project-memory stability. Do not use tools or outside knowledge.

Summarize the supplied project evidence in at most {word_limit} words. Preserve formal decisions, explicit non-goals, exact identifiers, and evidence IDs. Clearly distinguish approved facts from rejected or deprecated alternatives. Do not invent facts.

Return only the JSON object required by the output schema.

PROJECT EVIDENCE
{context}
"""


def _recursive_prompt(previous: str | None, update: str, word_limit: int) -> str:
    prior = previous if previous is not None else "No previous summary exists."
    return f"""You are maintaining a compressed project-memory summary. Do not use tools or outside knowledge.

Rewrite the previous summary after incorporating the new evidence. The replacement summary must be at most {word_limit} words. Preserve every still-valid formal decision, exact identifier, explicit non-goal, and evidence ID that is necessary for future work. Distinguish approved facts from rejected alternatives. Do not invent facts.

Return only the JSON object required by the output schema.

PREVIOUS SUMMARY
{prior}

NEW EVIDENCE
{update}
"""


def _codex_version(executable: str) -> str:
    completed = subprocess.run(
        ["cmd.exe", "/d", "/s", "/c", executable, "--version"],
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    version = (completed.stdout or completed.stderr).strip()
    return version or "unknown"


def _run_codex(prompt: str, output: Path, model: str) -> None:
    executable = shutil.which("codex.cmd")
    if not executable:
        raise RuntimeError("codex.cmd was not found on PATH")
    command = [
        "cmd.exe", "/d", "/s", "/c", executable,
        "exec", "--model", model, "--ephemeral", "--sandbox", "read-only",
        "--skip-git-repo-check", "--output-schema", str(SCHEMA_PATH),
        "--output-last-message", str(output), "-",
    ]
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=ROOT,
        capture_output=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"codex failed for {output.name}: {completed.stderr[-2000:]}"
        )
    json.loads(output.read_text(encoding="utf-8"))


def run_model(
    independent_runs: int,
    workers: int,
    model: str,
    extend_existing: bool = False,
) -> None:
    fixture = _fixture()
    if extend_existing and RUN_METADATA_PATH.is_file():
        previous_metadata = json.loads(RUN_METADATA_PATH.read_text(encoding="utf-8"))
        if previous_metadata.get("model") != model:
            raise RuntimeError(
                "cannot extend semantic runs with a different model: "
                f"{previous_metadata.get('model')} != {model}"
            )
    if RUNS_ROOT.exists() and not extend_existing:
        resolved = RUNS_ROOT.resolve()
        expected_parent = (ROOT / "benchmarks").resolve()
        if resolved.parent != expected_parent or resolved.name != "semantic-runs":
            raise RuntimeError(f"unsafe semantic run cleanup target: {resolved}")
        shutil.rmtree(RUNS_ROOT)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(
        json.dumps(_output_schema(), indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    executable = shutil.which("codex.cmd")
    if not executable:
        raise RuntimeError("codex.cmd was not found on PATH")
    RUN_METADATA_PATH.write_text(
        json.dumps(
            {
                "codex_cli_version": _codex_version(executable),
                "model": model,
                "session_mode": "isolated ephemeral",
                "independent_runs_per_input_mode": independent_runs,
                "recursive_rounds_per_input_mode": len(fixture["rounds"]),
                "note": "Model was explicitly selected by the benchmark command.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    jobs: list[tuple[str, Path]] = []
    for mode in ("raw", "structured"):
        prompt = _summary_prompt(
            _full_context(fixture, mode), fixture["summary_word_limit"]
        )
        mode_root = RUNS_ROOT / f"independent-{mode}"
        mode_root.mkdir(exist_ok=True)
        for index in range(1, independent_runs + 1):
            output = mode_root / f"run-{index:02d}.json"
            if extend_existing and output.is_file():
                continue
            jobs.append((prompt, output))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_codex, prompt, output, model): output
            for prompt, output in jobs
        }
        for future in as_completed(futures):
            future.result()
            print(f"completed {futures[future].relative_to(ROOT)}")

    for mode in ("raw", "structured"):
        mode_root = RUNS_ROOT / f"recursive-{mode}"
        mode_root.mkdir(exist_ok=True)
        previous: str | None = None
        for round_number, item in enumerate(fixture["rounds"], start=1):
            update = (
                f"[{item['artifact_id']}]\n{item['raw_text']}"
                if mode == "raw"
                else _structured_round(fixture, round_number)
            )
            output = mode_root / f"round-{round_number:02d}.json"
            if extend_existing and output.is_file():
                previous = json.loads(output.read_text(encoding="utf-8"))["summary"]
                continue
            _run_codex(
                _recursive_prompt(previous, update, fixture["summary_word_limit"]),
                output,
                model,
            )
            previous = json.loads(output.read_text(encoding="utf-8"))["summary"]
            print(f"completed {output.relative_to(ROOT)}")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().replace("，", ",").split())


def _score(summary: str, fixture: dict[str, Any], through_round: int) -> dict[str, Any]:
    normalized = _normalized(summary)
    active = {
        key: fact for key, fact in fixture["gold_facts"].items()
        if fact["round_introduced"] <= through_round
    }
    retained = sorted(
        key for key, fact in active.items()
        if any(
            _normalized(pattern) in normalized
            for pattern in fact.get("accepted_patterns", [fact["value"]])
        )
    )
    cited = sorted(
        key for key, fact in active.items()
        if key in retained and fact["evidence_id"].casefold() in normalized
    )
    lures = sorted(
        lure for lure in fixture["rejected_lures"]
        if _normalized(lure) in normalized
    )
    return {
        "active_fact_count": len(active),
        "retained_fact_ids": retained,
        "fact_recall_percent": round(100 * len(retained) / len(active), 2),
        "cited_fact_ids": cited,
        "evidence_id_coverage_percent": round(100 * len(cited) / len(active), 2),
        "rejected_alternative_mentions": lures,
        "word_count": len(summary.split()),
    }


def _independent_metrics(paths: list[Path], fixture: dict[str, Any]) -> dict[str, Any]:
    scores = []
    retention_sets = []
    for path in paths:
        summary = json.loads(path.read_text(encoding="utf-8"))["summary"]
        score = _score(summary, fixture, len(fixture["rounds"]))
        scores.append({"run": path.name, **score})
        retention_sets.append(set(score["retained_fact_ids"]))
    pairs = list(itertools.combinations(retention_sets, 2))
    similarities = [
        len(left & right) / len(left | right) if left | right else 1.0
        for left, right in pairs
    ]
    fields = fixture["gold_facts"].keys()
    disagreement_fields = sorted(
        field for field in fields
        if len({field in retained for retained in retention_sets}) > 1
    )
    return {
        "run_count": len(scores),
        "mean_fact_recall_percent": round(mean(item["fact_recall_percent"] for item in scores), 2),
        "min_fact_recall_percent": min(item["fact_recall_percent"] for item in scores),
        "mean_evidence_coverage_percent": round(mean(item["evidence_id_coverage_percent"] for item in scores), 2),
        "mean_pairwise_retention_jaccard": round(mean(similarities), 4) if similarities else 1.0,
        "cross_run_disagreement_fields": disagreement_fields,
        "distinct_summary_count": len({
            hashlib.sha256(
                json.loads(path.read_text(encoding="utf-8"))["summary"].encode("utf-8")
            ).hexdigest()
            for path in paths
        }),
        "mean_word_count": round(mean(item["word_count"] for item in scores), 2),
        "word_limit_violation_count": sum(
            item["word_count"] > fixture["summary_word_limit"] for item in scores
        ),
        "rejected_alternative_mention_count": sum(
            len(item["rejected_alternative_mentions"]) for item in scores
        ),
        "runs": scores,
    }


def _recursive_metrics(paths: list[Path], fixture: dict[str, Any]) -> dict[str, Any]:
    scores = []
    previously_retained: set[str] = set()
    regressions: list[dict[str, Any]] = []
    for round_number, path in enumerate(paths, start=1):
        summary = json.loads(path.read_text(encoding="utf-8"))["summary"]
        score = _score(summary, fixture, round_number)
        retained = set(score["retained_fact_ids"])
        lost = sorted(previously_retained - retained)
        if lost:
            regressions.append({"round": round_number, "lost_fact_ids": lost})
        previously_retained = retained
        scores.append({"round": round_number, **score})
    return {
        "round_count": len(scores),
        "final_fact_recall_percent": scores[-1]["fact_recall_percent"],
        "final_evidence_coverage_percent": scores[-1]["evidence_id_coverage_percent"],
        "retention_regressions": regressions,
        "word_limit_violation_count": sum(
            item["word_count"] > fixture["summary_word_limit"] for item in scores
        ),
        "rejected_alternative_mention_count": sum(
            len(item["rejected_alternative_mentions"]) for item in scores
        ),
        "rounds": scores,
    }


def collect_results() -> dict[str, Any]:
    fixture = _fixture()
    run_metadata = (
        json.loads(RUN_METADATA_PATH.read_text(encoding="utf-8"))
        if RUN_METADATA_PATH.is_file()
        else {"model": "unknown", "session_mode": "unknown"}
    )
    result = {
        "schema_version": "1.0",
        "benchmark": "controlled-semantic-summary-drift",
        "runner": run_metadata,
        "summary_word_limit": fixture["summary_word_limit"],
        "scoring": (
            "Controlled semantic-alias retention and evidence-ID coverage for retained facts; "
            "no LLM judge is used."
        ),
        "independent_raw": _independent_metrics(
            sorted((RUNS_ROOT / "independent-raw").glob("run-*.json")), fixture
        ),
        "independent_structured": _independent_metrics(
            sorted((RUNS_ROOT / "independent-structured").glob("run-*.json")), fixture
        ),
        "recursive_raw": _recursive_metrics(
            sorted((RUNS_ROOT / "recursive-raw").glob("round-*.json")), fixture
        ),
        "recursive_structured": _recursive_metrics(
            sorted((RUNS_ROOT / "recursive-structured").glob("round-*.json")), fixture
        ),
    }
    return result


def evaluate() -> dict[str, Any]:
    result = collect_results()
    RESULTS_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    CHART_PATH.write_text(render_svg(result), encoding="utf-8", newline="\n")
    return result


def render_svg(result: dict[str, Any]) -> str:
    independent_raw = result["independent_raw"]
    independent_structured = result["independent_structured"]
    recursive_raw = result["recursive_raw"]
    recursive_structured = result["recursive_structured"]
    lost_fact_ids = sorted({
        fact_id
        for regression in recursive_raw["retention_regressions"]
        for fact_id in regression["lost_fact_ids"]
    })

    def bar(y: int, value: float, color: str) -> str:
        width = 390 * value / 100
        return (
            f'<rect x="170" y="{y}" width="390" height="12" rx="6" fill="#e2e8f0"/>'
            f'<rect x="170" y="{y}" width="{width:.1f}" height="12" rx="6" fill="{color}"/>'
        )

    independent_raw_recall = independent_raw["mean_fact_recall_percent"]
    independent_structured_recall = independent_structured["mean_fact_recall_percent"]
    recursive_raw_recall = recursive_raw["final_fact_recall_percent"]
    recursive_structured_recall = recursive_structured["final_fact_recall_percent"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="620" viewBox="0 0 1200 620" role="img" aria-labelledby="title desc">
  <title id="title">Controlled semantic summary drift benchmark</title>
  <desc id="desc">Five isolated one-turn summaries and ten recursive summary rounds compare raw narrative history with structured evidence records.</desc>
  <style>.title{{font:700 28px Inter,Segoe UI,Arial,sans-serif;fill:#0f172a}}.sub{{font:15px Inter,Segoe UI,Arial,sans-serif;fill:#64748b}}.head{{font:700 18px Inter,Segoe UI,Arial,sans-serif;fill:#0f172a}}.label{{font:14px Inter,Segoe UI,Arial,sans-serif;fill:#334155}}.value{{font:700 15px Inter,Segoe UI,Arial,sans-serif;fill:#0f172a}}.small{{font:13px Inter,Segoe UI,Arial,sans-serif;fill:#64748b}}</style>
  <rect width="1200" height="620" rx="28" fill="#f8fafc"/><rect x="1" y="1" width="1198" height="618" rx="27" fill="none" stroke="#cbd5e1" stroke-width="2"/>
  <text x="60" y="54" class="title">Measured semantic retention under summary compression</text>
  <text x="60" y="82" class="sub">Controlled 11-fact fixture · 110-word summaries · {result["runner"].get("model", "unknown")} · isolated ephemeral sessions · no LLM judge</text>
  <rect x="60" y="112" width="520" height="428" rx="20" fill="#fff" stroke="#dbe4f0"/><rect x="620" y="112" width="520" height="428" rx="20" fill="#fff" stroke="#dbe4f0"/>
  <text x="88" y="151" class="head">5 independent one-turn summaries</text><text x="648" y="151" class="head">10 recursive summary rounds</text>
  <circle cx="94" cy="184" r="6" fill="#f59e0b"/><text x="108" y="189" class="small">Raw accumulated narrative</text><circle cx="286" cy="184" r="6" fill="#16a34a"/><text x="300" y="189" class="small">Structured current facts</text>
  <circle cx="654" cy="184" r="6" fill="#f59e0b"/><text x="668" y="189" class="small">Raw recursive summary</text><circle cx="846" cy="184" r="6" fill="#16a34a"/><text x="860" y="189" class="small">Structured recursive summary</text>

  <text x="88" y="231" class="label">Mean fact recall</text>{bar(244, independent_raw_recall, '#f59e0b')}<text x="568" y="255" text-anchor="end" class="value">{independent_raw_recall:.2f}%</text>
  {bar(278, independent_structured_recall, '#16a34a')}<text x="568" y="289" text-anchor="end" class="value">{independent_structured_recall:.0f}%</text>
  <text x="88" y="342" class="label">Cross-run fact disagreement</text><text x="540" y="342" text-anchor="end" class="value">{len(independent_raw["cross_run_disagreement_fields"])} raw · {len(independent_structured["cross_run_disagreement_fields"])} structured</text>
  <text x="88" y="389" class="label">Mean retention-set Jaccard</text><text x="540" y="389" text-anchor="end" class="value">{independent_raw["mean_pairwise_retention_jaccard"]:.4f} · {independent_structured["mean_pairwise_retention_jaccard"]:.4f}</text>
  <text x="88" y="436" class="label">Rejected alternatives repeated</text><text x="540" y="436" text-anchor="end" class="value">{independent_raw["rejected_alternative_mention_count"]} · {independent_structured["rejected_alternative_mention_count"]}</text>
  <text x="88" y="493" class="small">Raw summaries disagreed on: {', '.join(independent_raw["cross_run_disagreement_fields"]) or 'none'}</text>

  <text x="648" y="231" class="label">Final fact recall</text>{bar(244, recursive_raw_recall, '#f59e0b').replace('x="170"', 'x="730"')}<text x="1128" y="255" text-anchor="end" class="value">{recursive_raw_recall:.2f}%</text>
  {bar(278, recursive_structured_recall, '#16a34a').replace('x="170"', 'x="730"')}<text x="1128" y="289" text-anchor="end" class="value">{recursive_structured_recall:.0f}%</text>
  <text x="648" y="342" class="label">Retention regressions</text><text x="1100" y="342" text-anchor="end" class="value">{len(recursive_raw["retention_regressions"])} raw · {len(recursive_structured["retention_regressions"])} structured</text>
  <text x="648" y="389" class="label">Word-limit violations</text><text x="1100" y="389" text-anchor="end" class="value">{recursive_raw["word_limit_violation_count"]} · {recursive_structured["word_limit_violation_count"]}</text>
  <text x="648" y="436" class="label">Rejected alternatives repeated</text><text x="1100" y="436" text-anchor="end" class="value">{recursive_raw["rejected_alternative_mention_count"]} · {recursive_structured["rejected_alternative_mention_count"]}</text>
  <text x="648" y="481" class="small">Lost after added historical noise: {', '.join(lost_fact_ids) or 'none'}</text>
  <text x="60" y="580" class="small">Result scope: one controlled synthetic fixture and one environment-configured model; not a universal model-quality claim.</text>
  <text x="60" y="602" class="small">Mention count measures context carryover, not mistaken adoption. Raw outputs and semantic aliases are committed for audit.</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-codex", action="store_true")
    parser.add_argument("--independent-runs", type=int, default=5)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--model")
    parser.add_argument("--extend-existing", action="store_true")
    args = parser.parse_args()
    if args.run_codex:
        if not args.model:
            parser.error("--model is required with --run-codex")
        run_model(args.independent_runs, args.workers, args.model, args.extend_existing)
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
