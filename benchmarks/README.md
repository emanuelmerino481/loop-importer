# Reproducible benchmarks

The context benchmark compares two payloads over a controlled synthetic project history:

1. rereading the complete accumulated startup document;
2. loading a bounded, query-specific bundle containing only `CURRENT` structured facts and matching CodeGraph nodes.

It measures canonical UTF-8 payload bytes, not model tokens. This keeps the result deterministic and tokenizer-independent. It also checks same-snapshot bundle digests, changed/missing evidence invalidation, false-stale count, and stale-fact leakage.

Run from the repository root:

```bash
python -m pip install -e .
python benchmarks/run_context_benchmark.py
```

The script writes [`context-benchmark-results.json`](context-benchmark-results.json) and regenerates [`docs/context-benchmark.svg`](../docs/context-benchmark.svg) from those results. Do not edit benchmark numbers in the SVG or README by hand.

## Multi-project demo matrix

`run_demo_matrix.py` exercises six controlled edge cases and four public GitHub repositories at pinned commits. Public repositories are downloaded as commit-addressed archives; the runner records each archive SHA-256, compares a whole-source-tree digest before and after import, validates every packet, and imports each unchanged snapshot twice to check fragment reuse. It never installs dependencies or executes repository code.

```bash
python benchmarks/run_demo_matrix.py
```

The command requires network access for the four public snapshots. Use `--controlled-only` for the six fully local scenarios; that mode prints its summary and does not overwrite the checked-in ten-demo result unless `--output` is supplied explicitly. Aggregated evidence is written to [`demo-matrix-results.json`](demo-matrix-results.json); public source archives are temporary and are not redistributed by this repository.

`PASS` means that all scenario-specific assertions passed and the packet validator returned `IMPORT_PACKET_VALID`; it does not mean every source file parsed successfully. The result records file-level parse evidence, public archive hashes, pre/post source-tree digests, runner/Python/platform identity, the exact tested-code path set, and the canonicalization rules used for every digest. Source-tree digests hash sorted POSIX-relative paths plus raw-file SHA-256 values while excluding `.git` and filesystem metadata. Counts refer to the final source snapshot in each scenario: Python-file totals include non-redacted Python artifacts even when size-limited or syntactically invalid, while nodes and edges include only accepted static graph structure.

## Semantic summary drift

`semantic-fixture.json` contains a controlled sequence of approved facts, rejected alternatives, evidence IDs, and a gold record. The semantic benchmark runs two protocols in isolated ephemeral Codex sessions:

- independent one-turn summaries of the same complete evidence, repeated several times;
- recursive summaries where each fresh session receives only the previous compressed summary plus one new evidence round.

Both protocols compare raw narrative evidence with structured fact records. Scoring uses controlled semantic aliases for canonical-value retention, evidence-ID coverage for retained facts, rejected-alternative carryover, cross-run retention disagreement, and recursive retention regressions. It does not use an LLM judge. The aliases are checked into `semantic-fixture.json` so scoring changes remain reviewable. Rejected-alternative mentions measure context carried into the replacement summary; they are not counted as mistaken adoption when the summary labels them rejected.

```bash
python benchmarks/run_semantic_benchmark.py --run-codex --model gpt-5.6-sol --independent-runs 5
```

The model must be selected explicitly. The runner records that model, the Codex CLI version, session isolation mode, and run counts in `semantic-runs/run-metadata.json`. Raw outputs are retained in `semantic-runs/` for audit, and aggregate metrics are written to `semantic-benchmark-results.json`.
