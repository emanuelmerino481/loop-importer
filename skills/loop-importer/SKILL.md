---
name: loop-importer
description: Import a long-running, manually operated scientific project into an agent Harness as a reviewable draft. Use when Codex needs to onboard an existing research repository, migrate IDE-driven experiments, inventory code/data/configs/checkpoints/results/logs, infer candidate task dependencies, or prepare task inputs without modifying or running the source project.
---

# Loop Importer

Convert an existing research directory into a bounded, evidence-linked Harness import packet. Treat the scan as reconnaissance, never as scientific verification.

## Workflow

1. Confirm the source project root and output root. Keep output outside the source project.
2. Run `loop-import SOURCE --project-id ID --output OUTPUT`.
3. Run `python skills/loop-importer/scripts/validate_import.py OUTPUT`.
4. Read `references/output-contract.md`, then inspect the generated manifest, registry, DAG candidates and Chinese HTML report.
5. Read `references/review-gates.md` before proposing promotion.
6. Open `review-session.yaml`. For each unresolved item, inspect its evidence candidates first. Ask exactly one question, include the Agent's recommended answer, wait for the human response, then record the answer, verdict, correction/notes and resolution status.
7. Follow question dependencies. Do not batch questions or continue past a decision that changes downstream questions.
8. Create active tasks only after every required review item is resolved and a human explicitly approves activation.

## Safety invariants

- Keep the source project read-only and never execute its code during import.
- Do not follow symlinks or traverse Git metadata, environments, caches, WandB, or MLflow stores.
- Never read or hash secret-like files; register only redacted metadata.
- Do not hash large data or checkpoints during reconnaissance.
- Treat filename-derived tasks and dependencies as `LOW` confidence candidates.
- Never infer the primary metric, statistical unit, threshold, dataset, seeds, baseline, or best result from filenames alone.
- Stop when limits are exceeded or source/output boundaries are ambiguous.

## Acceptance

Success means deterministic, source-preserving output marked `DRAFT_HUMAN_REVIEW`, a passing validator, and explicit unresolved questions. A zero exit code is not scientific verification.
