#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


REQUIRED = {
    "project-manifest.yaml", "artifact-registry.yaml", "task-dag.yaml",
    "open-questions.yaml", "review-session.yaml", "bootstrap.md", "import-summary.json", "import-report.html",
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
