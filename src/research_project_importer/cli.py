from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import ImportOptions, ImportProjectError, import_project


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a read-only, human-reviewable import packet for an existing research project."
    )
    parser.add_argument("source", type=Path, help="Existing project directory to scan")
    parser.add_argument("--project-id", required=True, help="Stable project identifier")
    parser.add_argument("--output", type=Path, required=True, help="Output directory outside source")
    parser.add_argument("--max-files", type=int, default=50_000)
    parser.add_argument("--max-text-bytes", type=int, default=262_144)
    parser.add_argument("--hash-max-bytes", type=int, default=1_048_576)
    args = parser.parse_args()
    try:
        result = import_project(
            args.source,
            args.output,
            ImportOptions(
                project_id=args.project_id,
                max_files=args.max_files,
                max_text_bytes=args.max_text_bytes,
                hash_max_bytes=args.hash_max_bytes,
            ),
        )
    except ImportProjectError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
