"""Regenerate the committed demo packet with portable, deterministic metadata."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import yaml

from loop_importer import ImportOptions, import_project


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "incomplete-research-project"
OUTPUT = ROOT / "examples" / "generated-import-packet"
PUBLIC_SOURCE = "examples/incomplete-research-project"
FIXED_TIME = "2026-07-14T00:00:00+00:00"


def _portable_text(path: Path, private_source: Path) -> None:
    text = path.read_text(encoding="utf-8")
    variants = {str(private_source), private_source.as_posix()}
    for private in variants:
        text = text.replace(private, PUBLIC_SOURCE)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    with tempfile.TemporaryDirectory(prefix="research-import-demo-") as temp:
        source = Path(temp) / "incomplete-research-project"
        shutil.copytree(FIXTURE, source)
        import_project(source, OUTPUT, ImportOptions(project_id="SYNTHETIC-RESPONSE-DEMO"))
        for path in OUTPUT.iterdir():
            if path.suffix in {".yaml", ".json", ".md", ".html"}:
                _portable_text(path, source)

    for name in ("project-manifest.yaml", "artifact-registry.yaml"):
        path = OUTPUT / name
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        value["generated_at"] = FIXED_TIME
        if "source_root" in value:
            value["source_root"] = PUBLIC_SOURCE
        path.write_text(yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n")

    summary_path = OUTPUT / "import-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["generated_at"] = FIXED_TIME
    summary["source_root"] = PUBLIC_SOURCE
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
