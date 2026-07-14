from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from research_project_importer import ImportOptions, ImportProjectError, import_project


class ImporterTests(unittest.TestCase):
    def test_packet_is_review_first_and_source_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "packet"
            source.mkdir()
            (source / "train.py").write_text("print('train')\n", encoding="utf-8")
            (source / "metrics.json").write_text('{"accuracy": 0.9}\n', encoding="utf-8")
            before = {p.name: p.read_bytes() for p in source.iterdir()}

            result = import_project(source, output, ImportOptions(project_id="DEMO"))

            self.assertEqual("DRAFT_HUMAN_REVIEW", result["status"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in source.iterdir()})
            review = yaml.safe_load((output / "review-session.yaml").read_text(encoding="utf-8"))
            self.assertTrue(review["interaction_policy"]["one_question_at_a_time"])
            self.assertTrue(review["interaction_policy"]["wait_for_human_answer"])
            self.assertTrue(all(q["agent_recommended_answer"] for q in review["questions"]))
            self.assertTrue(all(q["human_verdict"] == "PENDING" for q in review["questions"]))

    def test_secret_content_is_not_read_or_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "packet"
            source.mkdir()
            (source / ".env").write_text("API_TOKEN=super-secret\n", encoding="utf-8")
            import_project(source, output, ImportOptions(project_id="SAFE"))
            packet = (output / "artifact-registry.yaml").read_text(encoding="utf-8")
            self.assertNotIn("super-secret", packet)
            item = yaml.safe_load(packet)["artifacts"][0]
            self.assertTrue(item["redacted"])
            self.assertIsNone(item["sha256"])

    def test_output_inside_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            with self.assertRaises(ImportProjectError):
                import_project(source, source / "packet", ImportOptions(project_id="BAD"))

    def test_remote_credentials_are_removed(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://alice:token@example.com/org/repo.git?secret=yes\n", stderr="",
        )
        with tempfile.TemporaryDirectory() as temp, patch(
            "research_project_importer.core.subprocess.run", return_value=completed
        ):
            source = Path(temp) / "source"
            source.mkdir()
            packet = Path(temp) / "packet"
            import_project(source, packet, ImportOptions(project_id="REMOTE"))
            manifest = yaml.safe_load((packet / "project-manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual("https://example.com/org/repo.git", manifest["git"]["origin"])


if __name__ == "__main__":
    unittest.main()
