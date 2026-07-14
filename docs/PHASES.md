# Phases

## Phase 1 — Deterministic retail harness (MVP complete)

Build an offline, LLM-free retail evaluation harness with SQLite-backed state,
typed tools, JSON tasks, traces, three graders, a scripted reference agent,
CLI evaluation commands, and a Streamlit visual dashboard.

| Checkpoint | Status |
| --- | --- |
| 0 Packaging, tooling, docs skeleton | **Implemented** |
| 1 SQLite schema, models, fixtures | **Implemented** |
| 2 Policies and typed tools | **Implemented** |
| 3 Ten JSON evaluation tasks | **Implemented** |
| 4 Trace recorder and isolated runner | **Implemented** |
| 5 Final-state, tool-call, policy graders | **Implemented** |
| 6 Reference agent, failing trajectory, CLI | **Implemented** |
| 7 Full tests, coverage, CI / dashboard polish | **Implemented** |

Phase 1 MVP is complete when `make mvp-check` passes (format, lint, mypy,
coverage ≥85%, CLI smoke, Streamlit AppTest) and the reference suite remains
10/10.

## Phase 2 — Planned

Broader agent adapters and multi-trial reliability metrics (details TBD).
May include LLM-backed agents; not part of Phase 1.

## Phase 3 — Planned

Failure injection and resilience scenarios (details TBD).

## Phase 4 — Planned

Safety and policy-stress evaluation expansions (details TBD).

## Phase 5 — Planned

External / public benchmark integrations where licensed (details TBD).

## Phase 6 — Planned

Deeper interactive analysis UX beyond the Phase 1 Streamlit dashboard
(details TBD).

## Phase 7 — Planned

Production hardening and operational tooling (details TBD).
