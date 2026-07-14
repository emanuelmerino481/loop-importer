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
- Affected local files: `src/research_project_importer/core.py`, `skills/research-project-importer/SKILL.md`, the Skill references and validator, `tests/test_importer.py`, and `README.md`.

This attribution does not imply that the upstream author reviewed or endorsed this project, its schema, or any scientific conclusion produced with it.
