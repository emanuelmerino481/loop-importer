<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/hero-light.svg">
  <img alt="Loop Importer — evidence first, human approved" src="docs/hero-light.svg">
</picture>

[![tests](https://github.com/emanuelmerino481/loop-importer/actions/workflows/tests.yml/badge.svg)](https://github.com/emanuelmerino481/loop-importer/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

[中文说明](README.zh-CN.md)

## Import existing research without importing its ambiguity

**Turn an existing scientific project into a reviewable Agent Harness draft—with one command, without executing or modifying the source project.**

![Read-only project import followed by human review](docs/demo-flow.svg)

Long-running research projects accumulate scripts, configs, checkpoints, old metrics, GPU logs, and undocumented decisions. An Agent can inventory these files, but it must not silently convert guesses into scientific facts. Loop Importer creates an evidence-linked draft and makes every unresolved scientific decision explicit.

## 💌 A note from the builder

Hi! I am a first-year university student, still very early in learning AI-assisted development, Agents, and Harnesses. 👋🌱

I started with Trae, using it step by step to work on projects I had already begun. As those projects grew, scripts, configs, experiment results, GPU notes, and unfinished decisions ended up everywhere. I wanted a real Loop: let an Agent understand the project, make a bounded change, run or verify it, preserve the evidence, report back, and continue. 🔁🧪

Then I discovered that connecting an **existing** project to a Loop is much harder than starting a clean demo from a template. A model finding `train.py` does not mean it knows the official entrypoint. Seeing the largest accuracy value does not mean it knows the primary metric. Reading the files does not mean it understands the experiment. And once a conversation is lost, a lot of project context disappears with it. 😵‍💫

That frustration is why I built this small tool. It is for the slightly awkward group of developers, students, and researchers whose projects are already alive—and already messy—but who still want to move toward an Agent-driven workflow without throwing away history or handing every decision to the model. 🧰🤖

This is my first public attempt, so it will not be perfect. If it helps, please try it and tell me what breaks. If I misunderstood something, open an issue and correct me. A Star is lovely ⭐, but a real project that this tool can help is even better. ❤️

I am also grateful to my undergraduate mentor, who welcomes students interested in the intersection of **biology + AI** to get in touch and exchange ideas. 🧬🤖 Students who are genuinely curious about this direction can reach him at [dacheng2023@126.com](mailto:dacheng2023@126.com). 📮

— [@emanuelmerino481](https://github.com/emanuelmerino481)

## See the complete demo

The repository includes a deliberately incomplete synthetic research project containing conflicting seeds, an unfrozen metric, an ambiguous “best” result, a GPU log, and a secret-like file.

**[Explore the before/after demo →](examples/README.md)**

| Before: observed files | After: reviewable evidence |
| --- | --- |
| `configs/experiment.yaml` | [`project-manifest.yaml`](examples/generated-import-packet/project-manifest.yaml) |
| `scripts/{prepare,train,evaluate,report}.py` | [`artifact-registry.yaml`](examples/generated-import-packet/artifact-registry.yaml) |
| Python modules, functions, imports, and calls | [`code-graph.json`](examples/generated-import-packet/code-graph.json) |
| conflicting `results/*.json` | [`task-dag.yaml`](examples/generated-import-packet/task-dag.yaml) |
| GPU log without utilization | [`review-session.yaml`](examples/generated-import-packet/review-session.yaml) |
| `.env` | redacted metadata, no content or hash |

The generated DAG remains `LOW` confidence. The review session asks one question at a time, shows evidence IDs and an Agent recommendation, then waits for a human verdict before continuing.

## Multi-project demo matrix

The importer was run against **6 controlled edge-case projects and 4 pinned public GitHub snapshots**. All 10 packets passed `IMPORT_PACKET_VALID`; every import reported `source_mutated: false`. Across the final snapshots of all ten rows—not only the public repositories—the scanner observed **186 files, 72 Python files, 391 code nodes, and 593 structural edges**. Public repositories were downloaded by exact commit, their archive SHA-256 values were recorded, and whole-source-tree digests matched before and after import. No dependency was installed and no repository code was executed.

| Public snapshot | Files / Python | CodeGraph nodes / edges | Parse errors | Unchanged second import |
| --- | ---: | ---: | ---: | ---: |
| [`karpathy/micrograd@c911406`](https://github.com/karpathy/micrograd/commit/c911406e5ace8742e5841a7e0df113ecb5d54685) | 13 / 5 | 45 / 58 | 0 | 0 parsed / 5 reused |
| [`karpathy/nanoGPT@3adf61e`](https://github.com/karpathy/nanoGPT/commit/3adf61e154c3fe3fca428ad6bc3818b27a3b8291) | 26 / 15 | 45 / 64 | 0 | 0 parsed / 15 reused |
| [`drivendataorg/cookiecutter-data-science@0f6b163`](https://github.com/drivendataorg/cookiecutter-data-science/commit/0f6b163cdbe3918a2c65ab57ad9fefda93976d9e) | 82 / 22 | 57 / 76 | 6 | 0 parsed / 22 reused |
| [`lucidrains/alphafold2@931466e`](https://github.com/lucidrains/alphafold2/commit/931466e487e1be87d1182b17ed4ecfac9e70948d) | 42 / 18 | 222 / 381 | 0 | 0 parsed / 18 reused |

The six Cookiecutter parse errors are preserved Jinja-templated Python files, demonstrating the non-fatal parse-error path rather than a clean-AST claim. Here `PASS` means all scenario assertions passed and the packet validator accepted the result; expected parse errors may still be present when they are explicitly recorded. In the drift and deletion rows, the benchmark harness intentionally changes a fixture between imports—`source_mutated: false` means the importer itself did not make that change.

| Controlled demo | Boundary exercised | Measured result |
| --- | --- | --- |
| Incomplete research project | conflicting artifacts, secret-like file, bounded context | secret redacted; 2 facts + 2 code nodes + 1 edge selected |
| Python package aliases | relative imports, aliases, classes, methods, calls | `IMPORTS` and `CALLS` resolved; 0 parse errors |
| Broken and dynamic Python | syntax error and `factory()()` | 1 syntax error and dynamic call recorded without aborting |
| Secret and size bounds | `.env`, hash limit, AST size limit | secret value absent; oversized task fact became `UNVERIFIED` |
| Evidence drift | human fact cites an earlier artifact hash | 2 graph nodes marked stale; stale human fact excluded from context |
| Deleted evidence | one of two Python files removed between imports | 1 artifact and 2 graph nodes reported removed |

Review the [complete demo matrix results](benchmarks/demo-matrix-results.json) and [reproducible runner](benchmarks/run_demo_matrix.py). These are compatibility and safety demonstrations, not claims that inferred workflows or scientific conclusions are correct.

## Measured controlled benchmarks

The following charts are generated from checked-in benchmark JSON, not hand-entered marketing numbers.

![Measured context growth and evidence-drift controls](docs/context-benchmark.svg)

The context selector has an honest crossover cost: at one history round, the evidence metadata makes the bundle **106.38% larger** than rereading the short startup text. At 5, 10, 20, and 40 accumulated rounds, the measured payload reduction is **50.76%, 74.77%, 87.23%, and 93.57%**. On the controlled invalidation fixture, same-snapshot bundle digests matched 20/20 times, stale-evidence recall was 100%, false-stale count was 0, and no stale fact entered the bundle.

![Measured semantic retention across independent and recursive summaries](docs/semantic-benchmark.svg)

Using one controlled 11-fact fixture, a 110-word limit, and isolated ephemeral `gpt-5.6-sol` sessions:

- five independent one-turn summaries of the same raw history retained 94.55% of facts on average and disagreed on two fields; structured current facts retained 100% with no field disagreement;
- after ten recursive summary rounds, raw summaries retained 81.82% and had lost `formal_seeds` and `gpu_budget`; the structured sequence retained 100% with no retention regression.

This is evidence for one synthetic fixture and one configured model, not a universal model-quality or production-token claim. Context cost is measured in canonical UTF-8 payload bytes, not model tokens. Review the [context results](benchmarks/context-benchmark-results.json), [semantic results](benchmarks/semantic-benchmark-results.json), [gold fixture and aliases](benchmarks/semantic-fixture.json), [raw model outputs](benchmarks/semantic-runs/), and [benchmark methodology](benchmarks/README.md).

## Implementation checks

The implementation was also checked with automated fixtures, the committed synthetic demo, and a read-only import of this repository itself.

| Check | Result |
| --- | --- |
| Automated test suite | **28/28 passed** |
| Synthetic demo packet | **`IMPORT_PACKET_VALID`** |
| Multi-project demo matrix | **10/10 packets valid; 4 pinned public repositories** |
| Repository self-import | **19 Python files → 188 nodes and 418 structural edges** |
| Unchanged second import | **0 files reparsed, 19 graph fragments reused** |

See the [CodeGraph tests](tests/test_codegraph.py), [context tests](tests/test_context.py), [packet validator](skills/loop-importer/scripts/validate_import.py), and [generated demo graph](examples/generated-import-packet/code-graph.json) for reproducible evidence.

This is partial groundwork for [Issue #2](https://github.com/emanuelmerino481/loop-importer/issues/2) and [Issue #3](https://github.com/emanuelmerino481/loop-importer/issues/3), not their closure. Evidence validity is currently file-hash based, context selection is lexical, and value-level locators, durable human review events, conflict propagation, and handover summaries remain future work.

## Quick start

```bash
git clone https://github.com/emanuelmerino481/loop-importer.git
cd loop-importer
python -m pip install -e .

loop-import /path/to/existing-project \
  --project-id MY-PROJECT \
  --output /path/to/imports/MY-PROJECT

python skills/loop-importer/scripts/validate_import.py \
  /path/to/imports/MY-PROJECT

loop-context /path/to/imports/MY-PROJECT \
  --query "train entrypoint and primary metric" \
  --output /path/to/context-bundle.json
```

The packet contains:

- `project-manifest.yaml` — scan boundary, languages, Git metadata, and category counts;
- `artifact-registry.yaml` — stable artifact IDs, sizes, redaction state, and bounded hashes;
- `task-dag.yaml` — low-confidence prepare/train/infer/evaluate/report candidates;
- `code-graph.json` — deterministic Python structure, resolved structural edges, unresolved calls, and incremental stale/removed IDs;
- `knowledge-baseline.yaml` — structured facts with evidence snapshots and `CURRENT`/`STALE`/`UNVERIFIED` validity;
- `review-session.yaml` — evidence, recommended answers, dependencies, and human verdicts;
- `bootstrap.md` — cold-start context for a new Agent session;
- `import-summary.json` and a Chinese `import-report.html`.

## Safety model

- Never executes source project code.
- Never modifies or reorganizes the source project.
- Does not follow symlinks or traverse Git metadata, environments, caches, WandB, or MLflow stores.
- Never reads or hashes secret-like files.
- Builds the Python graph with the standard-library AST without importing or executing project modules.
- Reuses cached graph fragments only when path, artifact ID, and SHA-256 are unchanged.
- Does not hash large datasets or checkpoints during reconnaissance.
- Removes credentials and query parameters from HTTP Git remotes.
- Refuses to place output inside the source directory.
- Keeps the packet in `DRAFT_HUMAN_REVIEW` until required human decisions are resolved.

This is reconnaissance software, not a sandbox and not scientific verification. Review generated paths before sharing a packet.

## Codex Skill

`skills/loop-importer/` is an installable Codex Skill. It requires evidence-first, one-question-at-a-time review and prevents an Agent from activating tasks before explicit human approval.

## Why the demo is synthetic

Its structure reflects common research layouts documented by projects such as [Cookiecutter Data Science](https://github.com/drivendataorg/cookiecutter-data-science), while all demo content is original. This keeps the example realistic, reproducible, small, and free of third-party dataset or research-result claims.

## Status and contributing

The project is an early public release. The lightweight CodeGraph currently supports Python static structure only; dynamic dispatch, runtime imports, and scientific workflow meaning remain unresolved. Useful next steps include additional language detectors, packet schema versioning, and integrations with existing Harness frameworks. See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Security-sensitive reports belong in [SECURITY.md](SECURITY.md), not a public issue.

## Acknowledgements and license

The human-review interaction was inspired by the `grilling`, `grill-me`, and `grill-with-docs` skills in [mattpocock/skills](https://github.com/mattpocock/skills). No upstream implementation code was copied; the pinned revision and adaptation boundary are documented in [docs/SOURCES.md](docs/SOURCES.md).

Licensed under [Apache-2.0](LICENSE).
