from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from loop_importer import build_context_bundle, build_knowledge_baseline


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "context-benchmark-results.json"
CHART = ROOT / "docs" / "context-benchmark.svg"
ROUNDS = (1, 5, 10, 20, 40)
QUERY = "confirmed train entrypoint primary metric dataset seeds"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fact(index: int, topic: str, statement: str) -> dict:
    artifact_id = f"ART-FACT-{index:04d}"
    return {
        "fact_id": f"FACT-{index:04d}",
        "kind": "project_knowledge",
        "statement": statement,
        "value": statement,
        "topics": [topic],
        "epistemic_status": "HUMAN_CONFIRMED" if topic != "history" else "OBSERVED",
        "validity": "CURRENT",
        "origin": "HUMAN",
        "evidence": [{
            "artifact_id": artifact_id,
            "path": f"decisions/fact-{index:04d}.md",
            "sha256": _sha(statement),
        }],
        "requires_human_review": False,
    }


def _baseline(round_count: int) -> tuple[str, dict]:
    relevant = [
        _fact(1, "train", "The confirmed train entrypoint is scripts/train.py."),
        _fact(2, "metric", "The confirmed primary metric is macro AUROC."),
        _fact(3, "dataset", "The confirmed dataset snapshot is DATASET-v3."),
        _fact(4, "seeds", "The confirmed formal seeds are 7, 21, and 42."),
    ]
    history = []
    lines = [
        "Project startup knowledge. Every previous note is reread on every run.",
        *(fact["statement"] for fact in relevant),
    ]
    for round_number in range(1, round_count + 1):
        for item in range(6):
            index = 100 + (round_number - 1) * 6 + item
            statement = (
                f"Historical round {round_number:02d} note {item}: exploratory visualization "
                f"observation {index}; it is unrelated to the formal training contract. "
                "Retained for provenance and possible later review."
            )
            history.append(_fact(index, "history", statement))
            lines.append(statement)
    facts = sorted([*relevant, *history], key=lambda item: item["fact_id"])
    identity = {"project_id": "CONTEXT-BENCH", "facts": facts}
    baseline_digest = _sha(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    baseline = {
        "schema_version": "1.0",
        "project_id": "CONTEXT-BENCH",
        "status": "DRAFT_HUMAN_REVIEW",
        "baseline_id": f"KB-CONTEXT-{round_count:02d}",
        "baseline_digest": baseline_digest,
        "facts": facts,
    }
    return "\n".join(lines) + "\n", baseline


def _graph() -> dict:
    return {
        "nodes": [
            {
                "node_id": "CGN-TRAIN-MODULE",
                "kind": "module",
                "qualified_name": "scripts.train",
                "evidence": {"path": "scripts/train.py"},
            },
            {
                "node_id": "CGN-TRAIN-FUNCTION",
                "kind": "function",
                "qualified_name": "scripts.train.train",
                "evidence": {"path": "scripts/train.py"},
            },
        ],
        "edges": [
            {
                "edge_id": "CGE-TRAIN-CONTAINS",
                "kind": "CONTAINS",
                "source_node_id": "CGN-TRAIN-MODULE",
                "target_node_id": "CGN-TRAIN-FUNCTION",
                "confidence": "STRUCTURAL",
                "evidence": {"path": "scripts/train.py"},
            }
        ],
    }


def _artifact(artifact_id: str, path: str, content: str) -> dict:
    return {
        "artifact_id": artifact_id,
        "path": path,
        "sha256": _sha(content),
        "redacted": False,
        "category": "documentation",
        "size_bytes": len(content.encode("utf-8")),
        "language": None,
    }


def _consistency_results() -> dict:
    before = [
        _artifact("ART-TRAIN", "scripts/train.py", "train-v1"),
        _artifact("ART-NOTES", "notes/current.md", "notes-v1"),
        _artifact("ART-OLD", "notes/old.md", "old-v1"),
    ]
    previous = build_knowledge_baseline("DRIFT-BENCH", before, [])
    previous["facts"] = [
        {
            "fact_id": "FACT-TRAIN",
            "kind": "entrypoint",
            "statement": "The confirmed train entrypoint is scripts/train.py.",
            "value": "scripts/train.py",
            "topics": ["train", "entrypoint"],
            "epistemic_status": "HUMAN_CONFIRMED",
            "validity": "CURRENT",
            "origin": "HUMAN",
            "evidence": [{"artifact_id": "ART-TRAIN", "path": "scripts/train.py", "sha256": before[0]["sha256"]}],
            "requires_human_review": False,
        },
        {
            "fact_id": "FACT-NOTES",
            "kind": "note",
            "statement": "Current lab note remains informational.",
            "value": "informational",
            "topics": ["notes"],
            "epistemic_status": "HUMAN_CONFIRMED",
            "validity": "CURRENT",
            "origin": "HUMAN",
            "evidence": [{"artifact_id": "ART-NOTES", "path": "notes/current.md", "sha256": before[1]["sha256"]}],
            "requires_human_review": False,
        },
        {
            "fact_id": "FACT-OLD",
            "kind": "legacy_decision",
            "statement": "Legacy note controls the stop condition.",
            "value": "legacy-stop",
            "topics": ["stop"],
            "epistemic_status": "HUMAN_CONFIRMED",
            "validity": "CURRENT",
            "origin": "HUMAN",
            "evidence": [{"artifact_id": "ART-OLD", "path": "notes/old.md", "sha256": before[2]["sha256"]}],
            "requires_human_review": False,
        },
    ]
    after = [
        _artifact("ART-TRAIN", "scripts/train.py", "train-v2"),
        _artifact("ART-NOTES", "notes/current.md", "notes-v1"),
    ]
    refreshed = build_knowledge_baseline("DRIFT-BENCH", after, [], previous)
    expected_stale = {"FACT-TRAIN", "FACT-OLD"}
    actual_stale = {
        fact["fact_id"] for fact in refreshed["facts"] if fact["validity"] == "STALE"
    }
    expected_current = {"FACT-NOTES"}
    false_stale = actual_stale & expected_current
    bundle = build_context_bundle(refreshed, {"nodes": [], "edges": []}, "train stop notes")
    loaded_ids = {fact["fact_id"] for fact in bundle["payload"]["facts"]}

    _, stable_baseline = _baseline(40)
    stable_graph = _graph()
    digests = [
        build_context_bundle(stable_baseline, stable_graph, QUERY)["bundle_digest"]
        for _ in range(20)
    ]
    return {
        "same_snapshot_runs": len(digests),
        "same_snapshot_digest_matches": sum(item == digests[0] for item in digests),
        "stale_expected": sorted(expected_stale),
        "stale_detected": sorted(actual_stale),
        "stale_detection_recall_percent": round(
            100 * len(actual_stale & expected_stale) / len(expected_stale), 2
        ),
        "false_stale_count": len(false_stale),
        "stale_fact_leakage_count": len(loaded_ids & actual_stale),
    }


def run() -> dict:
    graph = _graph()
    rows = []
    cumulative_full = 0
    cumulative_bundle = 0
    for round_count in ROUNDS:
        startup, baseline = _baseline(round_count)
        bundle = build_context_bundle(baseline, graph, QUERY)
        full_bytes = len(startup.encode("utf-8"))
        bundle_bytes = bundle["payload_bytes"]
        cumulative_full += full_bytes
        cumulative_bundle += bundle_bytes
        rows.append({
            "history_rounds": round_count,
            "full_startup_bytes": full_bytes,
            "selected_bundle_bytes": bundle_bytes,
            "context_reduction_percent": round(100 * (1 - bundle_bytes / full_bytes), 2),
            "selected_fact_count": bundle["selected"]["fact_count"],
            "selected_code_node_count": bundle["selected"]["code_node_count"],
            "bundle_digest": bundle["bundle_digest"],
        })
    result = {
        "schema_version": "1.0",
        "benchmark": "controlled-synthetic-context-growth",
        "measurement_unit": "canonical UTF-8 payload bytes; not model tokens",
        "query": QUERY,
        "history_notes_added_per_round": 6,
        "context_cost": rows,
        "sampled_rounds_cumulative": {
            "full_startup_bytes": cumulative_full,
            "selected_bundle_bytes": cumulative_bundle,
            "reduction_percent": round(100 * (1 - cumulative_bundle / cumulative_full), 2),
        },
        "consistency": _consistency_results(),
    }
    result["result_digest"] = _sha(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return result


def _points(values: list[int], left: int, top: int, width: int, height: int, maximum: int) -> str:
    step = width / (len(values) - 1)
    return " ".join(
        f"{left + index * step:.1f},{top + height - (value / maximum) * height:.1f}"
        for index, value in enumerate(values)
    )


def render_svg(result: dict) -> str:
    rows = result["context_cost"]
    full = [row["full_startup_bytes"] for row in rows]
    bundle = [row["selected_bundle_bytes"] for row in rows]
    maximum = max(full) * 1.08
    left, top, width, height = 90, 190, 720, 250
    full_points = _points(full, left, top, width, height, maximum)
    bundle_points = _points(bundle, left, top, width, height, maximum)
    x_step = width / (len(rows) - 1)
    x_labels = "".join(
        f'<text x="{left + index * x_step:.1f}" y="466" text-anchor="middle" class="axis">{row["history_rounds"]}</text>'
        for index, row in enumerate(rows)
    )
    consistency = result["consistency"]
    final = rows[-1]
    first = rows[0]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="620" viewBox="0 0 1200 620" role="img" aria-labelledby="title desc">
  <title id="title">Measured context growth and consistency benchmark</title>
  <desc id="desc">In a controlled synthetic benchmark, full startup context grows with history while the selected evidence-safe bundle remains bounded. Same-snapshot digests match and stale facts are excluded.</desc>
  <style>
    .title{{font:700 28px Inter,Segoe UI,Arial,sans-serif;fill:#0f172a}} .sub{{font:15px Inter,Segoe UI,Arial,sans-serif;fill:#64748b}}
    .label{{font:600 14px Inter,Segoe UI,Arial,sans-serif;fill:#334155}} .value{{font:700 26px Inter,Segoe UI,Arial,sans-serif;fill:#0f172a}}
    .axis{{font:13px Inter,Segoe UI,Arial,sans-serif;fill:#64748b}} .legend{{font:600 13px Inter,Segoe UI,Arial,sans-serif;fill:#334155}}
  </style>
  <rect width="1200" height="620" rx="28" fill="#f8fafc"/><rect x="1" y="1" width="1198" height="618" rx="27" fill="none" stroke="#cbd5e1" stroke-width="2"/>
  <text x="60" y="54" class="title">Measured context cost and drift controls</text>
  <text x="60" y="82" class="sub">Controlled synthetic project · canonical UTF-8 payload bytes · generated from benchmark JSON</text>
  <rect x="60" y="110" width="1080" height="1" fill="#dbe4f0"/>
  <text x="60" y="151" class="label">CONTEXT GROWTH ACROSS HISTORY ROUNDS</text>
  <line x1="90" y1="440" x2="810" y2="440" stroke="#cbd5e1"/><line x1="90" y1="190" x2="90" y2="440" stroke="#cbd5e1"/>
  <polyline points="{full_points}" fill="none" stroke="#f59e0b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  <polyline points="{bundle_points}" fill="none" stroke="#16a34a" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  {x_labels}
  <text x="450" y="495" text-anchor="middle" class="axis">accumulated history rounds</text>
  <circle cx="120" cy="535" r="6" fill="#f59e0b"/><text x="136" y="540" class="legend">Full startup read</text>
  <circle cx="300" cy="535" r="6" fill="#16a34a"/><text x="316" y="540" class="legend">Selected context bundle</text>
  <text x="90" y="565" class="sub">Round {first["history_rounds"]}: {full[0]:,} B → {bundle[0]:,} B ({abs(first["context_reduction_percent"]):.2f}% metadata overhead)</text>
  <text x="90" y="587" class="sub">Round {final["history_rounds"]}: {full[-1]:,} B → {bundle[-1]:,} B ({final["context_reduction_percent"]}% less)</text>

  <rect x="850" y="145" width="290" height="96" rx="16" fill="#ffffff" stroke="#dbe4f0"/><text x="874" y="176" class="label">SAME SNAPSHOT DIGEST</text><text x="874" y="218" class="value">{consistency["same_snapshot_digest_matches"]}/{consistency["same_snapshot_runs"]}</text>
  <rect x="850" y="257" width="290" height="96" rx="16" fill="#ffffff" stroke="#dbe4f0"/><text x="874" y="288" class="label">STALE DETECTION RECALL</text><text x="874" y="330" class="value">{consistency["stale_detection_recall_percent"]:.0f}%</text>
  <rect x="850" y="369" width="290" height="96" rx="16" fill="#ffffff" stroke="#dbe4f0"/><text x="874" y="400" class="label">FALSE STALE</text><text x="874" y="442" class="value">{consistency["false_stale_count"]}</text>
  <rect x="850" y="481" width="290" height="96" rx="16" fill="#ffffff" stroke="#dbe4f0"/><text x="874" y="512" class="label">STALE FACTS LOADED</text><text x="874" y="554" class="value">{consistency["stale_fact_leakage_count"]}</text>
  <text x="60" y="610" class="axis">Synthetic functional benchmark, not a model-token or production-latency benchmark · digest {escape(result["result_digest"][:12])}</text>
</svg>'''


def main() -> int:
    result = run()
    RESULTS.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    CHART.write_text(render_svg(result), encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
