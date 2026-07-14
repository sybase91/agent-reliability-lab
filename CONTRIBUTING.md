# Contributing

## Requirements

- Python 3.12.x
- A virtual environment (this repo uses `.venv/`, which is gitignored)

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make setup
```

## Development workflow

1. Create or switch to a feature branch off `phase-1-retail-harness` (or `main` as agreed).
2. Make changes within the agreed checkpoint scope.
3. Run quality gates before opening a PR:

```bash
make format
make check
make smoke
```

## Project layout

- `src/agent_reliability_lab/` — installable package
- `tests/` — unit and integration tests
- `docs/` — architecture and phase documentation
- `evals/` — evaluation task definitions (**planned**; not present yet)

## Coding standards

- Format and lint with Ruff (`make format`, `make lint`)
- Type-check with mypy (`make typecheck`)
- Prefer stdlib where possible; runtime deps are limited to pydantic 2 and typer
- Do not commit secrets, `artifacts/`, or local SQLite files

## Documentation honesty

Label features as **implemented** or **planned**. Do not describe future Phase 1
components as working until their checkpoint lands.

## Pull requests

Keep PRs focused on one checkpoint or a narrow fix. Include how you validated
the change (`make check`, `make smoke`, etc.).
