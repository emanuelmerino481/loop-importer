from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from loop_importer import (
    ImportOptions,
    build_context_bundle,
    build_knowledge_baseline,
    import_project,
)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ContextBundleTests(unittest.TestCase):
    def test_import_creates_deterministic_knowledge_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "train.py").write_text(
                "def train():\n    return 1\n", encoding="utf-8"
            )

            import_project(source, packet, ImportOptions(project_id="KNOWLEDGE"))
            first = _load_yaml(packet / "knowledge-baseline.yaml")
            import_project(source, packet, ImportOptions(project_id="KNOWLEDGE"))
            second = _load_yaml(packet / "knowledge-baseline.yaml")

            self.assertEqual(first["baseline_digest"], second["baseline_digest"])
            self.assertTrue(second["previous_baseline_used"])
            self.assertEqual(1, second["summary"]["fact_count"])
            self.assertEqual("INFERRED", second["facts"][0]["epistemic_status"])

    def test_human_fact_is_marked_stale_when_evidence_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            train = source / "train.py"
            train.write_text("def train():\n    return 1\n", encoding="utf-8")
            import_project(source, packet, ImportOptions(project_id="STALE-KNOWLEDGE"))
            baseline_path = packet / "knowledge-baseline.yaml"
            baseline = _load_yaml(baseline_path)
            registry = _load_yaml(packet / "artifact-registry.yaml")
            artifact = registry["artifacts"][0]
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
            )

            train.write_text("def train():\n    return 2\n", encoding="utf-8")
            import_project(source, packet, ImportOptions(project_id="STALE-KNOWLEDGE"))
            refreshed = _load_yaml(baseline_path)
            human = next(
                item for item in refreshed["facts"]
                if item["fact_id"] == "FACT-HUMAN-TRAIN"
            )

            self.assertEqual("STALE", human["validity"])
            self.assertTrue(human["requires_human_review"])
            self.assertEqual("EVIDENCE_CHANGED", refreshed["invalidations"][0]["reason"])

            bundle = build_context_bundle(
                baseline=refreshed,
                code_graph=_load_json(packet / "code-graph.json"),
                query="confirmed train entrypoint",
            )
            selected_ids = {
                item["fact_id"] for item in bundle["payload"]["facts"]
            }
            self.assertNotIn("FACT-HUMAN-TRAIN", selected_ids)
            self.assertIn(
                "FACT-HUMAN-TRAIN", bundle["payload"]["warnings"]["stale_fact_ids"]
            )

    def test_fact_without_evidence_is_unverified_and_never_loaded(self) -> None:
        previous = {
            "schema_version": "1.0",
            "project_id": "MISSING",
            "baseline_id": "KB-MISSING",
            "baseline_digest": "digest",
            "facts": [{
                "fact_id": "FACT-MISSING",
                "kind": "metric",
                "statement": "Primary metric is AUROC.",
                "topics": ["metric", "auroc"],
                "epistemic_status": "HUMAN_CONFIRMED",
                "validity": "CURRENT",
                "origin": "HUMAN",
                "evidence": [],
                "requires_human_review": False,
            }],
        }
        baseline = build_knowledge_baseline("MISSING", [], [], previous)
        graph = {"nodes": [], "edges": []}

        bundle = build_context_bundle(baseline, graph, "primary metric auroc")

        self.assertEqual([], bundle["payload"]["facts"])
        self.assertEqual(
            ["FACT-MISSING"], bundle["payload"]["warnings"]["unverified_fact_ids"]
        )

    def test_importer_fact_without_hash_is_unverified(self) -> None:
        artifact = {
            "artifact_id": "ART-LARGE",
            "path": "scripts/large_train.py",
            "sha256": None,
        }
        task = {
            "task_id": "TASK-LARGE",
            "kind": "train",
            "entrypoint": "scripts/large_train.py",
            "evidence": ["ART-LARGE"],
            "depends_on_candidates": [],
        }

        baseline = build_knowledge_baseline("UNHASHED", [artifact], [task])

        self.assertEqual("UNVERIFIED", baseline["facts"][0]["validity"])
        bundle = build_context_bundle(
            baseline, {"nodes": [], "edges": []}, "train entrypoint"
        )
        self.assertEqual([], bundle["payload"]["facts"])

    def test_bundle_is_bounded_relevant_and_deterministic(self) -> None:
        facts = []
        for index in range(100):
            topic = "train" if index < 4 else "unrelated"
            facts.append({
                "fact_id": f"FACT-{index:03d}",
                "kind": "note",
                "statement": f"{topic} historical statement {index} " + "x" * 120,
                "topics": [topic],
                "epistemic_status": "OBSERVED",
                "validity": "CURRENT",
                "origin": "HUMAN",
                "evidence": [],
                "requires_human_review": False,
            })
        baseline = {
            "project_id": "BOUNDED",
            "baseline_id": "KB-BOUNDED",
            "baseline_digest": "digest",
            "facts": facts,
        }
        graph = {"nodes": [], "edges": []}

        first = build_context_bundle(
            baseline, graph, "train", max_payload_bytes=2_048
        )
        second = build_context_bundle(
            baseline, graph, "train", max_payload_bytes=2_048
        )

        self.assertLessEqual(first["payload_bytes"], 2_048)
        self.assertEqual(first["bundle_digest"], second["bundle_digest"])
        self.assertTrue(first["payload"]["facts"])
        self.assertTrue(
            all("train" in item["statement"] for item in first["payload"]["facts"])
        )


if __name__ == "__main__":
    unittest.main()
