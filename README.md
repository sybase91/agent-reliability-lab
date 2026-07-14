# Agent Reliability Lab

An offline evaluation harness that tests whether enterprise AI agents use tools
correctly, follow business policies, and leave application data in the right
final state — with a visual Streamlit dashboard for reviewing runs.

## The business problem

Enterprise agents do not only chat. They look up customers, create returns,
issue refunds, and change records in business systems. Those actions have
financial, compliance, and trust consequences.

A fluent reply is not proof that the work was done correctly. Teams need
repeatable tests they can run before deploying or changing an agent. This
project is that testing system. It is **not** a customer-service agent.

## Phase 1 MVP capabilities (Checkpoints 0–7)

| Capability | Status |
| --- | --- |
| SQLite retail environment, policies, seven typed tools | Implemented |
| Ten JSON evaluation tasks | Implemented |
| Trace recorder + isolated `TrialRunner` | Implemented |
| Final-state, tool-call, and policy graders | Implemented |
| Scripted reference agent (10/10) and failing demos | Implemented |
| CLI evaluation commands | Implemented |
| Streamlit visual evaluation dashboard | Implemented |
| Coverage ≥85%, AppTest, redaction/cleanup hardening | Implemented |

## Deterministic-mode limitation

The dashboard shows this caption:

> Deterministic MVP mode: the selected scenario defines the expected behavior.
> The request text is recorded for the run but is not semantically interpreted
> by an LLM.

Scripted agents follow fixed trajectories for the selected scenario. Editing
the request text does **not** unlock arbitrary free-form agent reasoning.

## Visual workflow

1. Select an evaluation scenario (one of ten fixtures).
2. Choose the reference agent or a failing demo agent.
3. View (and optionally edit) the customer request — PII is redacted in the UI.
4. Run the evaluation.
5. Inspect overall PASS/FAIL, three grader cards, ordered agent steps,
   expected vs actual state, and (on failure) a failure analysis section.
6. Download the JSON result artifact.

### Reference vs failing-agent demo

| Agent | Expected result |
| --- | --- |
| `reference` | Passes all 10 tasks |
| `skip_verification` | Fails (sensitive tools before verify) |
| `approval_bypass` | Fails high-value approval path |
| `duplicate_refund` | Fails duplicate-mutation expectations |

## Quick start

Requires Python 3.12+.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make setup          # installs .[dev,ui]
make smoke
make mvp-check
```

### CLI evaluation

```bash
python -m agent_reliability_lab.cli list-tasks
python -m agent_reliability_lab.cli run-task eligible_full_return --agent reference
python -m agent_reliability_lab.cli run-suite --agent reference
```

### Dashboard

```bash
make app
# or:
streamlit run app/streamlit_app.py
```

Then open the local URL Streamlit prints (typically http://localhost:8501).

### Screenshot placeholder

To capture a dashboard screenshot for docs or demos:

1. Run `make app` and open the UI.
2. Select `eligible_full_return` + `reference`, click **Run evaluation**.
3. Capture the viewport showing the PASS summary and grader cards.
4. Save the image locally (do not commit large binaries unless intentionally adding
   media assets). Replace this placeholder section with the image path when ready.

## Quality results (current build)

Commands: `make mvp-check`, `pytest --cov=... --cov-fail-under=85`

| Check | Result |
| --- | --- |
| Unit + UI AppTests | 116 passed |
| Coverage | 88.06% (fail-under 85%) |
| Reference suite | 10/10 PASS |
| Failing agents | FAIL as expected |
| `make mvp-check` | passed |

## Repository structure

```text
app/streamlit_app.py              # Streamlit rendering only
src/agent_reliability_lab/
  cli.py
  agents/                         # Protocol, reference, failing agents
  domains/retail/                 # Schema, fixtures, policies, tools
  harness/                        # Tasks, runner, traces, results
  graders/                        # Final-state, tool-call, policy
  presentation/                   # View models + formatters for the UI
evals/retail/tasks/               # Ten JSON tasks
tests/unit/                       # Harness and domain tests
tests/ui/                         # Streamlit AppTest suite
artifacts/                        # Local JSON results (gitignored)
```

## Roadmap and non-goals

Full phase plan: [docs/PHASES.md](docs/PHASES.md).

Phase 1 does **not** include LLM APIs, LangGraph, RAG, authentication, or
public benchmark packages. Those remain planned for later phases.

## Limitations

- No custom authentication on the dashboard
- Synthetic retail data only
- Manager approval is a deterministic mock
- Request text is not LLM-interpreted
- Checkpoint 7 hardens quality; later phases may add richer UX analytics

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/EVALUATION.md](docs/EVALUATION.md).
