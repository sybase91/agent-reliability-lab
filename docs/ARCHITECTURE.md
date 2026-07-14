# Architecture

## Status

| Area | Status |
| --- | --- |
| Packaging, CLI `--help`, tooling | **Implemented** (Checkpoint 0) |
| SQLite retail environment, models, fixtures | **Implemented** (Checkpoint 1) |
| Typed tools and policies | **Planned** |
| Harness runner and traces | **Planned** |
| Graders | **Planned** |
| Reference agent | **Planned** |

Phase 1 is **in progress**.

## Component boundaries

```text
cli.py          → user entry (Checkpoint 0: --help / --version)
agents/         → agent protocol and scripted reference (planned)
domains/retail/ → SQLite source of truth, models, seed (implemented);
                  policies and tools (planned)
harness/        → task models, runner, isolation, traces (planned)
graders/        → final-state, tool-call, policy graders (planned)
```

## SQLite as source of truth (implemented)

Persisted retail state lives in file-backed SQLite databases. There is no
in-memory `WorldState` as the system of record. Application code uses:

- `database.py` — explicit SQL schema, connections, transactions, row converters
- `models.py` — Pydantic 2 boundary models (no DB handles)
- `seed.py` — deterministic synthetic fixtures keyed by `fixture_id`
- `environment.py` — per-run temp DB lifecycle

### Schema responsibility

`initialize_schema` creates tables for customers, products, inventory, orders,
order items, payments, returns, return items, refunds, approvals, and case
events. Constraints enforce integer cents, positive quantities where required,
foreign keys, and unique idempotency keys on returns and refunds.

### Database lifecycle and isolation

`RetailEnvironment`:

1. Creates a new temporary `.db` file (not SQLite `:memory:`)
2. Initializes schema
3. Seeds a selected fixture
4. Exposes the connection for inspection or future grading
5. Closes the connection and deletes the file on cleanup (including after errors)

Each environment instance uses an independent file, so mutations never leak
across environments. Temporary paths are excluded from determinism comparisons;
equal fixture IDs must produce equal logical records under `ORDER BY`.

### Pydantic boundary responsibility

Models validate IDs, enums, integer money, quantities, and timezone-aware UTC
datetimes at application edges. They forbid unexpected fields and do not open
database connections.

### Explicit SQL trade-off

Readable `sqlite3` SQL is preferred over an ORM so constraint behavior and
queries stay visible for evaluation and teaching. The cost is more hand-written
SQL and converters.

### Deterministic fixture strategy

Fixtures use a fixed `REFERENCE_TIME` and stable human-readable IDs. No
`datetime.now()`, random UUIDs, or real customer data. Ten fixture IDs cover
future return/refund evaluation scenarios.

## Execution flow (planned beyond Checkpoint 1)

1. Load and validate a JSON task.
2. Create a fresh temporary SQLite database and seed it deterministically.
3. Run the agent through typed tools (transactions for mutations).
4. Record a redacted structured trace (including failed attempts).
5. Grade with three independent graders against persisted DB state + trace.
6. Write a machine-readable result under `artifacts/`.

## Tools, traces, graders (planned)

Documented further when Checkpoints 2–5 land. See also [EVALUATION.md](EVALUATION.md).

## Security considerations

- Redact secrets and unnecessary customer fields in traces (**planned**)
- Never commit real customer data; Phase 1 uses synthetic fixtures (**implemented**)
- Local artifacts and `*.db` files are gitignored (**implemented**)

## Implemented versus planned

**Implemented:** packaging, CLI help, tooling, SQLite retail schema/models,
deterministic fixtures, environment isolation.

**Planned:** policies, tools, JSON tasks, runner, traces, graders, reference agent.

## Architectural trade-offs

- Deterministic, LLM-free Phase 1 trades realism for repeatability (see ADR 0001).
- SQLite over in-memory-only state enables grading true persistence without an ORM.
