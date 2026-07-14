# Upstream Sources and Adaptation Record

## mattpocock/skills

- Repository: https://github.com/mattpocock/skills
- Pinned commit reviewed: `66898f60e8c744e269f8ce06c2b2b99ce7660d5f`
- Review date: 2026-07-14
- Upstream license: MIT
- Files reviewed: `skills/productivity/grilling/SKILL.md`, `skills/productivity/grill-me/SKILL.md`, and `skills/engineering/grill-with-docs/SKILL.md`.
- Adopted concepts: ask one question at a time, inspect known facts first, provide a recommended answer, wait for a human decision, branch from that decision, and preserve shared understanding in documentation.
- Local additions: evidence artifact IDs, human verdicts and corrections, question dependencies, and a hard gate that prevents activation while required answers remain unresolved.
- Code-copy status: no upstream implementation code was copied. The interaction pattern was adapted to scientific project import and human review.
- Affected local files: `src/loop_importer/core.py`, `skills/loop-importer/SKILL.md`, the Skill references and validator, `tests/test_importer.py`, and `README.md`.

This attribution does not imply that the upstream author reviewed or endorsed this project, its schema, or any scientific conclusion produced with it.

## Cookiecutter Data Science

- Repository: https://github.com/drivendataorg/cookiecutter-data-science
- Pinned commit reviewed: `0f6b163cdbe3918a2c65ab57ad9fefda93976d9e`
- Review date: 2026-07-14
- Upstream license: MIT
- Adopted concept: a recognizable research-project layout separating data, models/checkpoints, notebooks or notes, reports, configuration, and source code.
- Local adaptation: `examples/incomplete-research-project/` is entirely original synthetic content and deliberately retains incomplete decisions, conflicting results, and missing provenance so that the importer has realistic ambiguity to expose.
- Code-copy status: no template or implementation code was copied.

## GitHub Actions

- `actions/checkout` tag `v6`, resolved to `df4cb1c069e1874edd31b4311f1884172cec0e10` when reviewed.
- `actions/setup-python` tag `v6`, resolved to `ece7cb06caefa5fff74198d8649806c4678c61a1` when reviewed.
- Review date: 2026-07-14
- Use: CI checkout and Python 3.11/3.12 test setup in `.github/workflows/tests.yml`.
- Security boundary: workflow permissions remain `contents: read`; the demo executes the importer itself but never any script inside the synthetic source project.
