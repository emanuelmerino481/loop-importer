from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkArtifactTests(unittest.TestCase):
    def test_context_results_and_chart_are_reproducible(self) -> None:
        module = _load_module(
            "context_benchmark", ROOT / "benchmarks" / "run_context_benchmark.py"
        )
        committed = json.loads(
            (ROOT / "benchmarks" / "context-benchmark-results.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(committed, module.run())
        self.assertEqual(
            module.render_svg(committed),
            (ROOT / "docs" / "context-benchmark.svg").read_text(encoding="utf-8"),
        )
        ET.parse(ROOT / "docs" / "context-benchmark.svg")

    def test_semantic_results_are_derived_from_audited_runs(self) -> None:
        module = _load_module(
            "semantic_benchmark", ROOT / "benchmarks" / "run_semantic_benchmark.py"
        )
        committed = json.loads(
            (ROOT / "benchmarks" / "semantic-benchmark-results.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(committed, module.collect_results())
        self.assertEqual(
            module.render_svg(committed),
            (ROOT / "docs" / "semantic-benchmark.svg").read_text(encoding="utf-8"),
        )
        ET.parse(ROOT / "docs" / "semantic-benchmark.svg")
        self.assertEqual(
            5,
            len(list((ROOT / "benchmarks" / "semantic-runs" / "independent-raw").glob("run-*.json"))),
        )
        self.assertEqual(
            10,
            len(list((ROOT / "benchmarks" / "semantic-runs" / "recursive-raw").glob("round-*.json"))),
        )

    def test_demo_matrix_results_and_controlled_scenarios_are_reproducible(self) -> None:
        module = _load_module(
            "demo_matrix", ROOT / "benchmarks" / "run_demo_matrix.py"
        )
        committed = json.loads(
            (ROOT / "benchmarks" / "demo-matrix-results.json").read_text(
                encoding="utf-8"
            )
        )
        identity = deepcopy(committed)
        result_digest = identity.pop("result_digest")

        self.assertEqual(result_digest, module._canonical_digest(identity))
        self.assertEqual(10, committed["summary"]["demo_count"])
        self.assertEqual(10, committed["summary"]["passed_count"])
        self.assertEqual(10, committed["summary"]["packet_valid_count"])
        self.assertEqual(0, committed["summary"]["source_mutation_claim_count"])
        self.assertEqual(
            committed["runner"]["tested_code_digest"],
            module._runner_source_digest(),
        )
        self.assertTrue(
            all(
                len(item["source_archive_sha256"]) == 64
                for item in committed["public_repositories"]
            )
        )
        for item in committed["public_repositories"]:
            self.assertEqual(
                item["source_tree_digest_before"], item["source_tree_digest_after"]
            )
            self.assertEqual(
                item["metrics"]["parse_error_count"],
                len(item["parse_error_evidence"]),
            )
        readmes = [
            (ROOT / name).read_text(encoding="utf-8")
            for name in ("README.md", "README.zh-CN.md")
        ]
        for readme in readmes:
            for value in (186, 72, 391, 593):
                self.assertIn(str(value), readme)
            for item in committed["public_repositories"]:
                self.assertIn(item["commit"][:7], readme)
        with tempfile.TemporaryDirectory() as temp:
            observed = module.run_controlled_matrix(Path(temp))
        self.assertEqual(committed["controlled_demos"], observed)


if __name__ == "__main__":
    unittest.main()
