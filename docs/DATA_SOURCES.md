# Data sources

## Phase 1 (current)

Phase 1 uses **original deterministic synthetic fixtures** only.

### Checkpoint 1 (implemented)

- Fixtures live in `src/agent_reliability_lab/domains/retail/seed.py`
- IDs are stable and human-readable (for example `er_cust_alice`)
- Timestamps derive from a fixed UTC `REFERENCE_TIME` (no wall clock)
- No real customer names, emails, phones, or third-party datasets are used
- Repeat seeding of the same `fixture_id` into fresh databases yields equal
  logical records when queried with explicit `ORDER BY`

Registered fixture IDs: `eligible_return`, `expired_return`, `final_sale`,
`partial_return`, `high_value_refund`, `verification_failure`,
`cross_customer_access`, `already_refunded`, `missing_order`,
`idempotent_retry`.

### Checkpoint 3 tasks (implemented)

JSON tasks under `evals/retail/tasks/` map one-to-one onto those fixtures (for
example `eligible_full_return` → `eligible_return`). Tasks contain no raw SQL,
Python expressions, secrets, or real customer information.

## Planned future sources

These are **not** integrated in Phase 1. Links and intended uses:

| Source | Link | Intended use |
| --- | --- | --- |
| UCI Online Retail II | https://archive.ics.uci.edu/dataset/502/online+retail+ii | Scale and schema inspiration for later retail fixtures |
| τ-bench / tau2 / tau3-bench | https://github.com/sierra-research/tau-bench | Tool-calling retail/airline benchmark patterns |
| Berkeley Function Calling Leaderboard | https://gorilla.cs.berkeley.edu/leaderboard.html | Function-calling eval methodology |
| AgentDojo | https://github.com/eth-sri/agentdojo | Adversarial tool-use and security scenarios |

Do not add these packages or datasets until a later phase explicitly allows it.
