# Phases

## Phase 1 — Deterministic retail harness (current)

Build an offline, LLM-free retail evaluation harness with SQLite-backed state,
typed tools, JSON tasks, traces, three graders, and a scripted reference agent.

| Checkpoint | Status |
| --- | --- |
| 0 Packaging, tooling, docs skeleton | **Implemented** |
| 1 SQLite schema, models, fixtures | **Implemented** |
| 2 Policies and typed tools | **Implemented** |
| 3 Ten JSON evaluation tasks | **Implemented** |
| 4 Trace recorder and isolated runner | **Implemented** |
| 5 Final-state, tool-call, policy graders | **Implemented** |
| 6 Reference agent, failing trajectory, CLI | **Implemented** |
| 7 Full tests, coverage, CI polish | Planned |

## Phase 2 — Planned

Broader agent adapters and multi-trial reliability metrics (details TBD).

## Phase 3 — Planned

Failure injection and resilience scenarios (details TBD).

## Phase 4 — Planned

Safety and policy-stress evaluation expansions (details TBD).

## Phase 5 — Planned

External / public benchmark integrations where licensed (details TBD).

## Phase 6 — Planned

Interactive analysis UX (details TBD). No Streamlit dashboard is implemented
in Phase 1 Checkpoints 0–6.

## Phase 7 — Planned

Production hardening and operational tooling (details TBD).
