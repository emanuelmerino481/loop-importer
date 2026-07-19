# End-to-end demo

This demo starts with a deliberately incomplete but realistic synthetic research project. Its layout follows common data-science conventions—data, configs, scripts, checkpoints, results, logs, and notes—while preserving the ambiguity that accumulates in long-running manual projects.

No project script is executed. The importer reads bounded metadata and safe text signals, produces low-confidence workflow candidates, and turns unresolved scientific choices into a human review session.

## Before import

`incomplete-research-project/` contains:

- four documentary entrypoint candidates;
- one current config and two results from different seeds;
- an unverified “best” checkpoint placeholder;
- a GPU log without utilization telemetry;
- a secret-like `.env` file that must be redacted;
- notes admitting that the metric, split, baseline, and statistical unit are not frozen.

## Regenerate

From the repository root:

```bash
python -m pip install -e .
python examples/refresh_demo.py
python skills/loop-importer/scripts/validate_import.py \
  examples/generated-import-packet
```

## After import

Open these files in order:

1. [`project-manifest.yaml`](generated-import-packet/project-manifest.yaml) — bounded scan and Git state.
2. [`artifact-registry.yaml`](generated-import-packet/artifact-registry.yaml) — stable evidence IDs and redaction state.
3. [`code-graph.json`](generated-import-packet/code-graph.json) — Python structure, structural edges, unresolved calls, and incremental evidence state.
4. [`knowledge-baseline.yaml`](generated-import-packet/knowledge-baseline.yaml) — structured facts and evidence validity for bounded context loading.
5. [`task-dag.yaml`](generated-import-packet/task-dag.yaml) — low-confidence workflow candidates.
6. [`review-session.yaml`](generated-import-packet/review-session.yaml) — one-question-at-a-time human decisions.
7. [`import-report.html`](generated-import-packet/import-report.html) — Chinese review view.

The important output is not an automatically “correct” DAG. It is an auditable boundary between observed evidence, Agent recommendations, and decisions that still belong to a human.

## More demo coverage

The repository also includes a reproducible matrix of six controlled edge cases and four pinned public GitHub snapshots. See the [aggregated results](../benchmarks/demo-matrix-results.json) and [runner](../benchmarks/run_demo_matrix.py). Public snapshots are imported read-only without installing dependencies or executing their code.
