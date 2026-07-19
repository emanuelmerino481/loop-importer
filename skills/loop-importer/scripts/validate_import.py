#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


REQUIRED = {
    "project-manifest.yaml", "artifact-registry.yaml", "task-dag.yaml",
    "code-graph.json", "open-questions.yaml", "review-session.yaml",
    "knowledge-baseline.yaml", "bootstrap.md", "import-summary.json", "import-report.html",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet")
    args = parser.parse_args()
    root = Path(args.packet)
    missing = sorted(name for name in REQUIRED if not (root / name).is_file())
    if missing:
        print("missing:", ", ".join(missing))
        return 2
    for name in ("project-manifest.yaml", "artifact-registry.yaml", "task-dag.yaml"):
        data = yaml.safe_load((root / name).read_text(encoding="utf-8"))
        if data.get("import_status", data.get("status")) != "DRAFT_HUMAN_REVIEW":
            print(f"unsafe status in {name}")
            return 2
    registry = yaml.safe_load((root / "artifact-registry.yaml").read_text(encoding="utf-8"))
    for artifact in registry.get("artifacts", []):
        if artifact.get("redacted") and artifact.get("sha256"):
            print(f"redacted artifact was hashed: {artifact.get('path')}")
            return 2
    graph = json.loads((root / "code-graph.json").read_text(encoding="utf-8"))
    if graph.get("status") != "DRAFT_HUMAN_REVIEW":
        print("unsafe status in code-graph.json")
        return 2
    scope = graph.get("scope", {})
    if scope.get("source_execution") is not False or scope.get("source_mutated") is not False:
        print("unsafe code graph scope")
        return 2
    nodes = graph.get("nodes", [])
    node_ids = {node.get("node_id") for node in nodes}
    if None in node_ids:
        print("code graph node without stable ID")
        return 2
    if len(node_ids) != len(nodes):
        print("duplicate code graph node ID")
        return 2
    for node in graph.get("nodes", []):
        evidence = node.get("evidence", {})
        if not evidence.get("artifact_id") or not evidence.get("sha256"):
            print(f"code graph node without snapshot evidence: {node.get('node_id')}")
            return 2
    for edge in graph.get("edges", []):
        if edge.get("source_node_id") not in node_ids or edge.get("target_node_id") not in node_ids:
            print(f"code graph edge references missing node: {edge.get('edge_id')}")
            return 2
        if edge.get("confidence") != "STRUCTURAL":
            print(f"code graph edge has unsafe confidence: {edge.get('edge_id')}")
            return 2
    baseline = yaml.safe_load((root / "knowledge-baseline.yaml").read_text(encoding="utf-8"))
    if baseline.get("status") != "DRAFT_HUMAN_REVIEW":
        print("unsafe status in knowledge-baseline.yaml")
        return 2
    facts = baseline.get("facts", [])
    fact_ids = {fact.get("fact_id") for fact in facts}
    if None in fact_ids or len(fact_ids) != len(facts):
        print("knowledge baseline has missing or duplicate fact IDs")
        return 2
    for fact in facts:
        if (
            fact.get("validity") in {"STALE", "UNVERIFIED"}
            and not fact.get("requires_human_review")
        ):
            print(f"unsafe knowledge fact bypasses review: {fact.get('fact_id')}")
            return 2
        if fact.get("origin") == "HUMAN" and fact.get("validity") == "CURRENT":
            evidence = fact.get("evidence", [])
            if not evidence or any(
                not item.get("artifact_id") or not item.get("sha256")
                for item in evidence
            ):
                print(f"current human fact lacks snapshot evidence: {fact.get('fact_id')}")
                return 2
    review = yaml.safe_load((root / "review-session.yaml").read_text(encoding="utf-8"))
    policy = review.get("interaction_policy", {})
    if not policy.get("one_question_at_a_time") or not policy.get("wait_for_human_answer"):
        print("unsafe review interaction policy")
        return 2
    for question in review.get("questions", []):
        if not question.get("agent_recommended_answer") or "human_verdict" not in question:
            print(f"incomplete review question: {question.get('id')}")
            return 2
    print("IMPORT_PACKET_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
