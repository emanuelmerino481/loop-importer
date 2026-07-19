from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from loop_importer import ImportOptions, build_code_graph, import_project


def _load_graph(packet: Path) -> dict:
    return json.loads((packet / "code-graph.json").read_text(encoding="utf-8"))


def _relations(graph: dict) -> set[tuple[str, str, str]]:
    names = {item["node_id"]: item["qualified_name"] for item in graph["nodes"]}
    return {
        (item["kind"], names[item["source_node_id"]], names[item["target_node_id"]])
        for item in graph["edges"]
    }


class CodeGraphTests(unittest.TestCase):
    def test_graph_extracts_symbols_imports_and_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "trainer.py").write_text(
                "def train():\n    return 1\n", encoding="utf-8"
            )
            (source / "main.py").write_text(
                "from trainer import train\n\ndef run():\n    return train()\n",
                encoding="utf-8",
            )

            import_project(source, packet, ImportOptions(project_id="GRAPH"))
            graph = _load_graph(packet)

            self.assertEqual("DRAFT_HUMAN_REVIEW", graph["status"])
            self.assertEqual("python-ast-lite", graph["engine"])
            names = {item["qualified_name"] for item in graph["nodes"]}
            self.assertTrue({"main", "main.run", "trainer", "trainer.train"} <= names)
            relations = _relations(graph)
            self.assertIn(("CONTAINS", "main", "main.run"), relations)
            self.assertIn(("IMPORTS", "main", "trainer"), relations)
            self.assertIn(("CALLS", "main.run", "trainer.train"), relations)
            train_node = next(
                item for item in graph["nodes"] if item["qualified_name"] == "trainer.train"
            )
            self.assertTrue(train_node["evidence"]["artifact_id"].startswith("ART-"))
            self.assertEqual(1, train_node["evidence"]["line_start"])
            self.assertTrue(train_node["evidence"]["sha256"])

    def test_relative_and_module_aliases_are_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            package = source / "package"
            packet = root / "packet"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "trainer.py").write_text(
                "def train():\n    return None\n", encoding="utf-8"
            )
            (package / "main.py").write_text(
                "from . import trainer as worker\n\ndef run():\n    worker.train()\n",
                encoding="utf-8",
            )

            import_project(source, packet, ImportOptions(project_id="ALIASES"))
            graph = _load_graph(packet)

            relations = _relations(graph)
            self.assertIn(("IMPORTS", "package.main", "package.trainer"), relations)
            self.assertIn(("CALLS", "package.main.run", "package.trainer.train"), relations)

    def test_classes_methods_and_self_calls_are_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "runner.py").write_text(
                "class Runner:\n"
                "    def step(self):\n"
                "        return 1\n\n"
                "    def run(self):\n"
                "        return self.step()\n",
                encoding="utf-8",
            )

            import_project(source, packet, ImportOptions(project_id="METHODS"))
            relations = _relations(_load_graph(packet))

            self.assertIn(("CONTAINS", "runner", "runner.Runner"), relations)
            self.assertIn(("CONTAINS", "runner.Runner", "runner.Runner.step"), relations)
            self.assertIn(
                ("CALLS", "runner.Runner.run", "runner.Runner.step"), relations
            )

    def test_local_binding_does_not_inherit_same_named_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "trainer.py").write_text(
                "def train():\n    return 1\n", encoding="utf-8"
            )
            (source / "main.py").write_text(
                "from trainer import train\n\ndef run(train):\n    return train()\n",
                encoding="utf-8",
            )

            import_project(source, packet, ImportOptions(project_id="SHADOW"))
            graph = _load_graph(packet)

            self.assertNotIn(
                ("CALLS", "main.run", "trainer.train"), _relations(graph)
            )
            self.assertTrue(
                any(
                    item["expression"] == "train"
                    and item["reason"] == "NO_LOCAL_TARGET"
                    for item in graph["unresolved_calls"]
                )
            )

    def test_duplicate_definitions_stay_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "duplicate.py").write_text(
                "def target():\n"
                "    return 1\n\n"
                "def target():\n"
                "    return 2\n\n"
                "target()\n",
                encoding="utf-8",
            )

            import_project(source, packet, ImportOptions(project_id="DUPLICATE"))
            graph = _load_graph(packet)
            target_nodes = [
                item for item in graph["nodes"]
                if item["qualified_name"] == "duplicate.target"
            ]

            self.assertEqual(2, len(target_nodes))
            self.assertEqual(2, len({item["node_id"] for item in target_nodes}))
            self.assertEqual(
                "duplicate.target", graph["ambiguous_symbols"][0]["qualified_name"]
            )
            self.assertNotIn(
                ("CALLS", "duplicate", "duplicate.target"), _relations(graph)
            )

    def test_unimported_name_does_not_resolve_to_same_named_module(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "foo.py").write_text(
                "def helper():\n    return 1\n", encoding="utf-8"
            )
            (source / "main.py").write_text(
                "def run():\n    return foo()\n", encoding="utf-8"
            )

            import_project(source, packet, ImportOptions(project_id="UNIMPORTED"))
            graph = _load_graph(packet)

            self.assertNotIn(("CALLS", "main.run", "foo"), _relations(graph))
            self.assertTrue(
                any(
                    item["expression"] == "foo"
                    and item["reason"] == "NO_LOCAL_TARGET"
                    for item in graph["unresolved_calls"]
                )
            )

    def test_graph_is_deterministic_for_fresh_packets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "main.py").write_text(
                "def main():\n    print('ok')\n", encoding="utf-8"
            )

            import_project(source, root / "packet-a", ImportOptions(project_id="STABLE"))
            import_project(source, root / "packet-b", ImportOptions(project_id="STABLE"))

            self.assertEqual(_load_graph(root / "packet-a"), _load_graph(root / "packet-b"))

    def test_unchanged_files_are_reused_without_reparse(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            (source / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
            import_project(source, packet, ImportOptions(project_id="REUSE"))

            with patch(
                "loop_importer.codegraph._parse_fragment",
                side_effect=AssertionError("unchanged file was reparsed"),
            ):
                import_project(source, packet, ImportOptions(project_id="REUSE"))

            graph = _load_graph(packet)
            self.assertTrue(graph["incremental"]["previous_graph_used"])
            self.assertEqual(0, graph["incremental"]["parsed_file_count"])
            self.assertEqual(2, graph["incremental"]["reused_file_count"])

    def test_changed_evidence_is_reparsed_and_marks_nodes_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            target = source / "trainer.py"
            target.write_text("def train():\n    return 1\n", encoding="utf-8")
            (source / "main.py").write_text(
                "from trainer import train\ntrain()\n", encoding="utf-8"
            )
            import_project(source, packet, ImportOptions(project_id="STALE"))
            before = _load_graph(packet)
            train_node_id = next(
                item["node_id"]
                for item in before["nodes"]
                if item["qualified_name"] == "trainer.train"
            )

            target.write_text("def train():\n    return 2\n", encoding="utf-8")
            import_project(source, packet, ImportOptions(project_id="STALE"))
            after = _load_graph(packet)

            self.assertEqual(1, after["incremental"]["parsed_file_count"])
            self.assertEqual(1, after["incremental"]["reused_file_count"])
            self.assertIn(train_node_id, after["incremental"]["stale_node_ids"])
            self.assertEqual(1, len(after["incremental"]["changed_artifact_ids"]))

    def test_changed_import_updates_only_the_affected_subgraph(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "trainer.py").write_text(
                "def execute():\n    return 'train'\n", encoding="utf-8"
            )
            (source / "helper.py").write_text(
                "def execute():\n    return 'helper'\n", encoding="utf-8"
            )
            main = source / "main.py"
            main.write_text(
                "from trainer import execute\nexecute()\n", encoding="utf-8"
            )
            import_project(source, packet, ImportOptions(project_id="AFFECTED"))
            self.assertIn(
                ("CALLS", "main", "trainer.execute"),
                _relations(_load_graph(packet)),
            )

            main.write_text(
                "from helper import execute\nexecute()\n", encoding="utf-8"
            )
            import_project(source, packet, ImportOptions(project_id="AFFECTED"))
            graph = _load_graph(packet)
            relations = _relations(graph)

            self.assertNotIn(("CALLS", "main", "trainer.execute"), relations)
            self.assertIn(("CALLS", "main", "helper.execute"), relations)
            self.assertEqual(1, graph["incremental"]["parsed_file_count"])
            self.assertEqual(2, graph["incremental"]["reused_file_count"])

    def test_deleted_file_removes_nodes_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            removed = source / "old.py"
            removed.write_text("def old():\n    return 1\n", encoding="utf-8")
            import_project(source, packet, ImportOptions(project_id="DELETE"))
            before = _load_graph(packet)
            old_ids = {
                item["node_id"] for item in before["nodes"]
                if item["qualified_name"].startswith("old")
            }

            removed.unlink()
            import_project(source, packet, ImportOptions(project_id="DELETE"))
            after = _load_graph(packet)

            self.assertTrue(old_ids <= set(after["incremental"]["removed_node_ids"]))
            self.assertEqual(1, len(after["incremental"]["removed_artifact_ids"]))
            self.assertFalse(old_ids & {item["node_id"] for item in after["nodes"]})

    def test_syntax_error_is_recorded_without_failing_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "broken.py").write_text("def broken(:\n", encoding="utf-8")

            result = import_project(source, packet, ImportOptions(project_id="BROKEN"))
            graph = _load_graph(packet)

            self.assertEqual("DRAFT_HUMAN_REVIEW", result["status"])
            self.assertEqual(1, graph["summary"]["parse_error_count"])
            self.assertEqual("SYNTAX_ERROR", graph["parse_errors"][0]["kind"])
            self.assertIn(
                "broken", {item["qualified_name"] for item in graph["nodes"]}
            )

    def test_content_change_during_scan_rejects_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            (source / "changing.py").write_text(
                "def changing():\n    return 1\n", encoding="utf-8"
            )
            artifact = {
                "artifact_id": "ART-changing",
                "path": "changing.py",
                "category": "script",
                "size_bytes": (source / "changing.py").stat().st_size,
                "sha256": "0" * 64,
                "hash_status": "COMPUTED",
                "redacted": False,
                "language": "Python",
            }

            graph = build_code_graph(
                source=source,
                artifacts=[artifact],
                project_id="RACE",
                max_source_bytes=262_144,
            )

            self.assertEqual([], graph["nodes"])
            self.assertEqual(
                "EVIDENCE_CHANGED_DURING_SCAN", graph["parse_errors"][0]["kind"]
            )

    def test_dynamic_calls_are_not_promoted_to_edges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "dynamic.py").write_text(
                "def factory():\n    return lambda: 1\n\ndef run():\n    return factory()()\n",
                encoding="utf-8",
            )

            import_project(source, packet, ImportOptions(project_id="DYNAMIC"))
            graph = _load_graph(packet)

            dynamic = [
                item for item in graph["unresolved_calls"]
                if item["reason"] == "DYNAMIC_EXPRESSION"
            ]
            self.assertEqual(1, len(dynamic))
            node_ids = {item["node_id"] for item in graph["nodes"]}
            self.assertTrue(
                all(item["target_node_id"] in node_ids for item in graph["edges"])
            )

    def test_secret_python_file_is_not_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            packet = root / "packet"
            source.mkdir()
            (source / "secret_token.py").write_text(
                "TOKEN = 'do-not-copy'\n", encoding="utf-8"
            )

            import_project(source, packet, ImportOptions(project_id="SECRET"))
            graph_text = (packet / "code-graph.json").read_text(encoding="utf-8")
            graph = json.loads(graph_text)

            self.assertNotIn("do-not-copy", graph_text)
            self.assertEqual(0, graph["summary"]["python_file_count"])
            self.assertEqual([], graph["nodes"])


if __name__ == "__main__":
    unittest.main()
