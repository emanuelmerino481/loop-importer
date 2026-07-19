from __future__ import annotations

import argparse
import json
from pathlib import Path

from .context import load_packet_context


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a bounded, evidence-safe context bundle from an import packet."
    )
    parser.add_argument("packet", type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-payload-bytes", type=int, default=8_192)
    parser.add_argument("--max-graph-nodes", type=int, default=40)
    args = parser.parse_args()
    bundle = load_packet_context(
        packet=args.packet,
        query=args.query,
        max_payload_bytes=args.max_payload_bytes,
        max_graph_nodes=args.max_graph_nodes,
    )
    text = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
