# Import output contract

The importer creates a review packet outside the source project:

- `project-manifest.yaml`: scan limits, Git identity, language/category counts.
- `artifact-registry.yaml`: bounded metadata inventory with stable artifact IDs.
- `task-dag.yaml`: low-confidence entrypoint and dependency candidates.
- `code-graph.json`: deterministic Python module/class/function structure, structural import/call edges, unresolved calls, parse errors, and incremental evidence changes.
- `knowledge-baseline.yaml`: structured importer inferences and preserved human facts with evidence-snapshot validity.
- `open-questions.yaml`: scientific decisions that files cannot establish safely.
- `review-session.yaml`: evidence-linked agent recommendation, human answer, verdict, correction, and dependency fields for one-question-at-a-time review.
- `bootstrap.md`: concise cold-start context.
- `import-summary.json`: machine-readable summary.
- `import-report.html`: Chinese human-review view.

Every generated packet must remain `DRAFT_HUMAN_REVIEW` until a person confirms the formal goal, dataset, metric, statistical unit, seeds, baseline, GPU budget, protected paths, and stop conditions.

For each review item, inspect available evidence first, present one question plus a recommended answer, wait for the human response, and record one of `CONFIRM_CORRECT`, `CORRECTED`, `REJECT_INFERENCE`, or `NEEDS_EVIDENCE`. Do not ask a batch of questions or activate tasks with unresolved required items.

The scanner must not modify the source project, follow symlinks, read secret contents, hash secrets, or hash files above the configured size limit.

## Lightweight CodeGraph contract

`code-graph.json` is a read-only static-analysis aid, not a verified execution trace and not a scientific fact model. Version 1 uses Python's standard-library AST only and never imports or executes project code.

- Every node carries an artifact ID, the artifact SHA-256 observed during the same scan, a relative path, and a line range.
- `CONTAINS`, `IMPORTS`, and `CALLS` edges are emitted only when both endpoints resolve to graph nodes. Their confidence is `STRUCTURAL`.
- Dynamic or unresolved calls remain in `unresolved_calls` with confidence `UNRESOLVED`; they must not be promoted to edges by guessing.
- Duplicate qualified names remain in `ambiguous_symbols`; calls to them are not resolved by choosing one definition arbitrarily.
- Syntax errors are recorded in `parse_errors` and do not abort the project import.
- A compatible previous graph may reuse a file fragment only when its relative path, artifact ID, and SHA-256 are unchanged.
- Changed evidence is reported through `changed_artifact_ids` and `stale_node_ids`; deleted evidence is reported through `removed_artifact_ids` and `removed_node_ids`.
- The whole graph remains `DRAFT_HUMAN_REVIEW`. It does not confirm entrypoints, experiment semantics, metrics, or workflow correctness.

## Knowledge and context contract

`knowledge-baseline.yaml` is a structured knowledge index, not a prompt that should be loaded in full on every run.

- Importer-generated task facts remain `INFERRED` and require human review.
- Human facts are preserved across compatible imports only when explicitly marked with `origin: HUMAN`.
- Every human fact must cite evidence snapshots. Missing hashes make it `UNVERIFIED`; changed or deleted evidence makes it `STALE`.
- `STALE` and `UNVERIFIED` facts must not enter a generated context bundle.
- `loop-context` creates a deterministic, query-specific payload with a strict byte budget. The payload records its baseline digest, selected facts, selected CodeGraph nodes, exclusions, and bundle digest.
- Lexical selection is routing, not semantic verification. Human approval remains authoritative.
