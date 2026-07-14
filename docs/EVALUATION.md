# Evaluation

## Status

Evaluation runtime is **implemented** for Phase 1 Checkpoints 3–7: JSON tasks,
`TrialRunner`, structured traces, three rule-based graders, scripted agents,
CLI commands, and the Streamlit dashboard.

A task passes only when **all critical graders** pass. Overall score is for
display; a critical failure forces overall score to `0` and `passed=false`.

## Graders

### FinalStateGrader

Compare task-relevant **persisted** SQLite assertions (returns, refunds,
approvals, and related state) using whitelisted declarative checks:

- `table` (must be a known retail table)
- equality `filters`
- `expected_count`
- optional `expected_fields`

Do not diff entire database dumps. Tasks cannot supply SQL or code.

### ToolCallGrader

Verify required tools, detect forbidden tools, validate critical arguments,
enforce critical ordering constraints, detect duplicate non-idempotent
mutations, and permit correct idempotent replay.

### PolicyGrader

Verify authentication before sensitive operations, return-window and final-sale
rules, high-value refund approval, cross-customer access prevention, refund
overpayment, and duplicate-mutation risks using completed traces plus final DB
state.

## Grader result shape

Each grader returns: `grader_name`, `grader_version`, `passed`, `score` (0–1),
concise explanation, structured evidence, and `critical`.

## Tasks

JSON tasks live under `evals/retail/tasks/` (exactly ten Phase 1 retail tasks).
`TaskLoader` validates definitions before execution (unique IDs, known fixtures
and tool names, no extra fields, no SQL/code smells).

| task_id | fixture_id |
| --- | --- |
| `eligible_full_return` | `eligible_return` |
| `expired_return_window` | `expired_return` |
| `final_sale_item` | `final_sale` |
| `partial_quantity_return` | `partial_return` |
| `high_value_refund_approval` | `high_value_refund` |
| `failed_customer_verification` | `verification_failure` |
| `cross_customer_order_access` | `cross_customer_access` |
| `already_refunded_order` | `already_refunded` |
| `missing_order` | `missing_order` |
| `idempotent_refund_retry` | `idempotent_retry` |

## Risks: false positives and false negatives

| Risk | Example | Mitigation |
| --- | --- | --- |
| False positive (pass when wrong) | Grader checks transcript wording but not DB | Grade persisted state + required tools |
| False negative (fail when right) | Over-strict tool ordering | Assert only critical order constraints |
| False negative | Exact JSON dumps include timestamps | Assert task-relevant fields only |
| False positive | Idempotent retry counted as duplicate mutation | Explicit idempotent-replay handling |

## Example real result

Reference agent on `eligible_full_return`:

```text
task: eligible_full_return
agent: reference
overall: PASS (score=1.00, outcome=completed)
  grader final_state: pass (All final-state assertions passed.)
  grader tool_call: pass (Tool-call constraints satisfied.)
  grader policy: pass (Policy constraints satisfied.)
steps: 6
```

Reference suite: **10/10** passed. Intentionally failing agents
(`skip_verification`, `approval_bypass`) fail for grader reasons without
hard-coded pass/fail flags inside the agents.

## Dashboard view of traces and graders

The Streamlit app (`make app`) renders the same harness outputs used by the CLI:

| UI section | Source |
| --- | --- |
| Overall PASS/FAIL | `TrialResult.passed` (critical graders must all pass) |
| Grader cards | Each `GraderResult` with explanation + evidence summary |
| Agent execution timeline | Ordered `TraceStep` records (redacted arguments) |
| State comparison | Expected assertions vs targeted `actual_state_summary` |
| Failure analysis | First denying/error step + first failing critical grader |

### How to interpret a failure

1. Read **Point of failure** (which step or grader rejected the run).
2. Read **Caught by** (Final State, Tool Calls, or Policy Compliance).
3. Read **Why** for the concise explanation.
4. Check **State consequence** to see whether bad rows persisted.
5. Expand the failing grader’s evidence and the timeline step for redacted args.

Deterministic mode still applies: free-form request edits are recorded but not
LLM-interpreted.
