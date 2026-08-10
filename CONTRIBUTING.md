# Contributing

SensorProof favors small, reviewable changes with an explicit contract.

## Environment

Use one of the supported CPython releases. The quality lane runs on 3.14.6; compatibility runs on 3.11.15, 3.12.13, 3.13.14, and 3.14.6.

```bash
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps --require-hashes -r requirements/quality.txt
python -m pip install --no-build-isolation --no-deps -e .
```

## Before opening a pull request

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q --cov=sensorproof --cov-report=term-missing --cov-fail-under=90
python tools/capture_evidence.py --help
```

Also build a clean wheel when changing package metadata or the CLI.

## Design expectations

- Preserve strict bounded parsing; new schema fields require explicit limits.
- Keep generation deterministic and explain every rounding rule.
- Add adversarial verification tests for any new artifact field.
- Do not weaken a check to make a fixture pass.
- Separate synthetic evidence claims from real-world performance claims.
- Update architecture, scenario, security, and limitation documentation when behavior changes.

## Visual evidence

Changes to the scenario, engine, verifier, renderer, runtime lock, capture tool, or permanent evidence workflow must regenerate every affected file in `docs/evidence/`. The visual-drift workflow performs an exact byte comparison.

Generated evidence must come from the implemented workflow. Do not add hand-edited screenshots, fake terminal sessions, invented charts, external personal data, secrets, or unreviewed datasets.

## Commit and pull-request shape

Prefer one concern per commit. The PR description should state:

- the behavioral contract changed;
- tests added or updated;
- evidence affected;
- limitations or compatibility changes;
- security implications.

Do not include generated caches, environments, build products, local paths, credentials, or editor state.
