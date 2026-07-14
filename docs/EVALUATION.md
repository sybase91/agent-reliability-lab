# Evaluation

## Status

Evaluation runtime is **not implemented** yet (planned for Phase 1 Checkpoints 3–5).
This document describes the intended design so contributors do not invent a
single generic “Evaluator” when those checkpoints land.

Phase 1 is **in progress**. Checkpoints 0–2 are implemented today (packaging,
retail SQLite environment, pure policies, and typed tools). Graders and the task
runner remain planned; they will score agent behavior against the Checkpoint 2
tool and policy surface.

## Planned graders

A task passes only when **all critical graders** pass.

### FinalStateGrader (planned)

Compare task-relevant **persisted** SQLite assertions (returns, refunds,
approvals, and related state). Do not diff entire database dumps.

### ToolCallGrader (planned)

Verify required tools, detect forbidden tools, validate critical arguments,
detect duplicate mutations, and enforce ordering constraints.

### PolicyGrader (planned)

Verify authentication before sensitive operations, return-window and final-sale
rules, high-value refund approval, cross-customer access prevention, and
duplicate-refund prevention.

## Grader result shape (planned)

Each grader returns: `grader_name`, `grader_version`, `passed`, `score` (0–1),
concise explanation, and structured evidence.

## Risks: false positives and false negatives

| Risk | Example | Mitigation (planned) |
| --- | --- | --- |
| False positive (pass when wrong) | Grader checks transcript wording but not DB | Grade persisted state + required tools |
| False negative (fail when right) | Over-strict tool ordering | Assert only critical order constraints |
| False negative | Exact JSON dumps include timestamps | Assert task-relevant fields only |
| False positive | Idempotent retry counted as success without prior create | Explicit duplicate-mutation checks |

## Tasks (planned)

JSON tasks under `evals/retail/tasks/` (exactly ten Phase 1 retail tasks) will be
validated before execution. That directory is not created in Checkpoint 0.
