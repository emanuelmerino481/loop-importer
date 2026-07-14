# Import output contract

The importer creates a review packet outside the source project:

- `project-manifest.yaml`: scan limits, Git identity, language/category counts.
- `artifact-registry.yaml`: bounded metadata inventory with stable artifact IDs.
- `task-dag.yaml`: low-confidence entrypoint and dependency candidates.
- `open-questions.yaml`: scientific decisions that files cannot establish safely.
- `review-session.yaml`: evidence-linked agent recommendation, human answer, verdict, correction, and dependency fields for one-question-at-a-time review.
- `bootstrap.md`: concise cold-start context.
- `import-summary.json`: machine-readable summary.
- `import-report.html`: Chinese human-review view.

Every generated packet must remain `DRAFT_HUMAN_REVIEW` until a person confirms the formal goal, dataset, metric, statistical unit, seeds, baseline, GPU budget, protected paths, and stop conditions.

For each review item, inspect available evidence first, present one question plus a recommended answer, wait for the human response, and record one of `CONFIRM_CORRECT`, `CORRECTED`, `REJECT_INFERENCE`, or `NEEDS_EVIDENCE`. Do not ask a batch of questions or activate tasks with unresolved required items.

The scanner must not modify the source project, follow symlinks, read secret contents, hash secrets, or hash files above the configured size limit.
