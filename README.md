# Agent Reliability Lab

Stateful, deterministic evaluation harness for testing enterprise AI agents
across tools, policies, failures, safety, and repeated trials.

## Problem

Agent behavior is hard to trust without repeatable, policy-aware evaluation
against a known environment. Live LLM judges and mutable shared state make
failures noisy and hard to debug.

## Currently implemented scope

**Phase 1 is in progress.**

**Checkpoint 0 (foundation) — implemented:**

- Installable Python 3.12 package (`src/` layout)
- Minimal Typer CLI (`python -m agent_reliability_lab.cli --help`)
- Development tooling: pytest, ruff, mypy, Makefile
- Documentation skeleton with implemented vs planned labels

**Checkpoint 1 (SQLite retail domain) — implemented:**

- Explicit SQLite schema (stdlib `sqlite3`, no ORM)
- Pydantic boundary models (integer cents, timezone-aware UTC)
- Deterministic synthetic fixtures (ten `fixture_id` values)
- Isolated file-backed `RetailEnvironment` lifecycle

**Not implemented yet (planned for later Phase 1 checkpoints):**

- Retail policies and typed tools
- JSON evaluation tasks
- Task runner, traces, and graders
- Scripted reference agent

## Why final-state evaluation matters

*(Planned for graders)* Inspecting persisted SQLite state after tool calls
catches silent policy violations that “looked fluent” in a transcript alone.
Checkpoint 1 provides the persisted environment those graders will read.

## Architecture summary

SQLite is the source of truth for retail state. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make setup
make smoke
make check
```

## Commands

```bash
make setup      # editable install with dev extras
make format     # ruff format
make lint       # ruff check
make typecheck  # mypy src
make test       # pytest
make test-cov   # pytest with coverage
make smoke      # import + CLI --help
make check      # format check + lint + typecheck + test

python -m agent_reliability_lab.cli --help
python -m agent_reliability_lab.cli --version
```

Task run commands (`list-tasks`, `run-task`, `run-suite`, `show-result`) are
**planned**, not available yet.

## Example result

*(Planned)* Machine-readable JSON under `artifacts/` after a task or suite run.

## Current phase

**Phase 1 — Deterministic retail harness (in progress).** Checkpoints 0 and 1
complete.

## Roadmap

See [docs/PHASES.md](docs/PHASES.md). Phases 2–7 are planned.

## Limitations

- No policies, tools, evaluation tasks, runners, traces, graders, or agents yet
- CLI does not execute evaluations
- No LLM providers or external APIs
