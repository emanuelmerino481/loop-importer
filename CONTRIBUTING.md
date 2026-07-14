# Contributing

Thanks for helping make existing research projects easier to audit and migrate.

## Before proposing a change

1. Keep source-project scanning read-only.
2. Treat inferred workflow structure as a candidate, never a scientific fact.
3. Add a regression test for changes to redaction, boundaries, artifact IDs, DAG inference, or review gates.
4. Do not commit private datasets, credentials, unpublished results, server addresses, or generated packets containing local paths.

## Development

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/refresh_demo.py
python skills/loop-importer/scripts/validate_import.py examples/generated-import-packet
git diff --exit-code examples/generated-import-packet
```

Open an issue before making a large schema or safety-policy change. Pull requests should explain the observed problem, the safety impact, and the checks performed.
