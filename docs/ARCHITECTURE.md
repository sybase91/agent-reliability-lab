# Architecture

## Status

| Area | Status |
| --- | --- |
| Packaging, CLI `--help`, tooling | **Implemented** (Checkpoint 0) |
| SQLite retail environment | **Planned** |
| Typed tools and policies | **Planned** |
| Harness runner and traces | **Planned** |
| Graders | **Planned** |
| Reference agent | **Planned** |

Phase 1 is **in progress**.

## Component boundaries (planned)

```text
cli.py          → user entry (partially implemented: --help / --version)
agents/         → agent protocol and scripted reference (planned)
domains/retail/ → SQLite source of truth, seed, policies, tools (planned)
harness/        → task models, runner, isolation, traces (planned)
graders/        → final-state, tool-call, policy graders (planned)
```

## Execution flow (planned)

1. Load and validate a JSON task.
2. Create a fresh temporary SQLite database and seed it deterministically.
3. Run the agent through typed tools (transactions for mutations).
4. Record a redacted structured trace (including failed attempts).
5. Grade with three independent graders against persisted DB state + trace.
6. Write a machine-readable result under `artifacts/`.

## SQLite state lifecycle (planned)

Per task: create temp DB → migrate schema → seed fixture → run → grade → dispose.
No shared mutable in-memory world as source of truth.

## Task isolation (planned)

Each run uses an isolated database file so state cannot leak across tasks.

## Tools, traces, graders (planned)

Documented further when Checkpoints 2–5 land. See also [EVALUATION.md](EVALUATION.md).

## Security considerations

- Redact secrets and unnecessary customer fields in traces (**planned**)
- Never commit real customer data; Phase 1 uses synthetic fixtures (**planned**)
- Local artifacts and `*.db` files are gitignored (**implemented**)

## Implemented versus planned

**Implemented:** package layout stubs, Typer CLI help, Makefile/tooling, docs skeleton.

**Planned:** all retail environment and harness runtime behavior.

## Architectural trade-offs

- Deterministic, LLM-free Phase 1 trades realism for repeatability (see ADR 0001).
- SQLite over in-memory-only state enables grading true persistence without an ORM.
