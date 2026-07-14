"""Isolated trial runner: environment, agent loop, tracing, grading, artifacts."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_reliability_lab.agents.protocol import ActionType, Agent, AgentObservation
from agent_reliability_lab.domains.retail.environment import RetailEnvironment
from agent_reliability_lab.domains.retail.tools import (
    TOOL_NAMES,
    ToolResult,
    invoke_tool,
)
from agent_reliability_lab.graders.final_state import FinalStateGrader
from agent_reliability_lab.graders.policy import PolicyGrader
from agent_reliability_lab.graders.tool_call import ToolCallGrader
from agent_reliability_lab.harness.results import RunnerOutcome, TrialResult
from agent_reliability_lab.harness.tasks import (
    ALLOWED_TABLES,
    StateAssertion,
    TaskDefinition,
    TaskLoader,
)
from agent_reliability_lab.harness.trace import (
    TraceRecorder,
    redact_text_pii,
    scrub_payload_pii,
)

_MUTATION_TABLES = ("returns", "refunds", "approvals", "payments", "case_events")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def summarize_assertion_state(
    connection: sqlite3.Connection,
    assertions: list[StateAssertion],
) -> list[dict[str, Any]]:
    """Capture targeted actual counts/fields for task assertions (not a DB dump)."""
    summaries: list[dict[str, Any]] = []
    for assertion in assertions:
        if assertion.table not in ALLOWED_TABLES:
            continue
        where_parts: list[str] = []
        values: list[Any] = []
        for column, expected in assertion.filters.items():
            if not column.isidentifier():
                continue
            where_parts.append(f"{column} = ?")
            values.append(expected)
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        count = int(
            connection.execute(
                f"SELECT COUNT(*) AS n FROM {assertion.table}{where_sql}",
                values,
            ).fetchone()["n"]
        )
        entry: dict[str, Any] = {
            "table": assertion.table,
            "filters": assertion.filters,
            "actual_count": count,
            "expected_count": assertion.expected_count,
        }
        if count > 0 and assertion.expected_fields:
            row = connection.execute(
                f"SELECT * FROM {assertion.table}{where_sql} LIMIT 1",
                values,
            ).fetchone()
            if row is not None:
                row_map = dict(row)
                entry["actual_fields"] = {
                    key: row_map.get(key) for key in assertion.expected_fields
                }
                entry["expected_fields"] = dict(assertion.expected_fields)
        summaries.append(entry)
    return summaries


def snapshot_mutation_state(connection: sqlite3.Connection) -> dict[str, Any]:
    """Targeted before/after counts and key ids — not a full database dump."""
    snapshot: dict[str, Any] = {}
    for table in _MUTATION_TABLES:
        count = int(
            connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        )
        snapshot[f"{table}_count"] = count
    payment_statuses = connection.execute(
        "SELECT payment_id, status FROM payments ORDER BY payment_id"
    ).fetchall()
    snapshot["payment_statuses"] = {
        row["payment_id"]: row["status"] for row in payment_statuses
    }
    return snapshot


def diff_state(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Return only keys whose values changed."""
    changed: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = {"before": before.get(key), "after": after.get(key)}
    return changed


def compute_overall(
    grader_results: list[Any],
    runner_outcome: RunnerOutcome,
) -> tuple[bool, float]:
    """Pass only when every critical grader passes; never average away a failure."""
    if runner_outcome is not RunnerOutcome.COMPLETED:
        return False, 0.0
    if not grader_results:
        return False, 0.0
    critical_failed = any(g.critical and not g.passed for g in grader_results)
    if critical_failed:
        return False, 0.0
    all_passed = all(g.passed for g in grader_results)
    scores = [float(g.score) for g in grader_results]
    mean = sum(scores) / len(scores) if scores else 0.0
    return all_passed, mean


class TrialRunner:
    """Run one agent against one task in a fresh RetailEnvironment."""

    def __init__(
        self,
        *,
        tasks_dir: Path | None = None,
        output_dir: Path | str = "artifacts",
    ) -> None:
        self.loader = TaskLoader(tasks_dir)
        self.output_dir = Path(output_dir)
        self._final_state = FinalStateGrader()
        self._tool_call = ToolCallGrader()
        self._policy = PolicyGrader()

    def run(self, task_id: str, agent: Agent) -> TrialResult:
        task = self.loader.load(task_id)
        return self.run_task(task, agent)

    def run_task(self, task: TaskDefinition, agent: Agent) -> TrialResult:
        run_id = uuid.uuid4().hex
        recorder = TraceRecorder(run_id, task.task_id, agent.name)
        outcome = RunnerOutcome.COMPLETED
        error_summary: str | None = None
        final_response: str | None = None
        previous: ToolResult | None = None
        grader_results: list[Any] = []

        env = RetailEnvironment(task.fixture_id)
        try:
            env.open()
            step_number = 0
            max_steps = task.maximum_steps

            while step_number < max_steps:
                observation = AgentObservation(
                    task_id=task.task_id,
                    user_request=task.user_request,
                    current_step=step_number,
                    steps_remaining=max_steps - step_number,
                    previous_tool_result=previous,
                )
                started = _utc_now()
                try:
                    action = agent.act(observation)
                except Exception as exc:  # noqa: BLE001 — convert to agent_error
                    ended = _utc_now()
                    step_number += 1
                    recorder.record(
                        step_number=step_number,
                        decision_reason="agent raised an exception",
                        action_type="error",
                        tool_name=None,
                        raw_arguments={},
                        started_at=started,
                        ended_at=ended,
                        status="agent_error",
                        error={"type": type(exc).__name__, "message": str(exc)},
                        result_summary="agent error",
                    )
                    outcome = RunnerOutcome.AGENT_ERROR
                    error_summary = f"{type(exc).__name__}: {exc}"
                    break

                if action.action_type is ActionType.FINISH:
                    ended = _utc_now()
                    step_number += 1
                    recorder.record(
                        step_number=step_number,
                        decision_reason=action.decision_reason,
                        action_type=ActionType.FINISH.value,
                        tool_name=None,
                        raw_arguments={},
                        started_at=started,
                        ended_at=ended,
                        status="finished",
                        result_summary=(action.final_response or "")[:240],
                    )
                    final_response = action.final_response
                    outcome = RunnerOutcome.COMPLETED
                    break

                tool_name = action.tool_name or ""
                raw_args = dict(action.arguments)
                if tool_name not in TOOL_NAMES:
                    ended = _utc_now()
                    step_number += 1
                    recorder.record(
                        step_number=step_number,
                        decision_reason=action.decision_reason,
                        action_type=ActionType.TOOL_CALL.value,
                        tool_name=tool_name,
                        raw_arguments=raw_args,
                        started_at=started,
                        ended_at=ended,
                        status="invalid_tool",
                        error={"message": f"unknown tool {tool_name!r}"},
                        result_summary="invalid tool",
                    )
                    outcome = RunnerOutcome.INVALID_TOOL
                    error_summary = f"unknown tool {tool_name!r}"
                    break

                before = snapshot_mutation_state(env.connection)
                try:
                    result = invoke_tool(env.connection, tool_name, raw_args)
                except ValidationError as exc:
                    ended = _utc_now()
                    step_number += 1
                    recorder.record(
                        step_number=step_number,
                        decision_reason=action.decision_reason,
                        action_type=ActionType.TOOL_CALL.value,
                        tool_name=tool_name,
                        raw_arguments=raw_args,
                        started_at=started,
                        ended_at=ended,
                        status="invalid_arguments",
                        error={
                            "type": "ValidationError",
                            "message": str(exc).split("\n")[0],
                        },
                        result_summary="invalid arguments",
                        state_changes={},
                    )
                    outcome = RunnerOutcome.INVALID_ARGUMENTS
                    error_summary = "invalid tool arguments"
                    break
                except Exception as exc:  # noqa: BLE001 — system failure path
                    ended = _utc_now()
                    step_number += 1
                    recorder.record(
                        step_number=step_number,
                        decision_reason=action.decision_reason,
                        action_type=ActionType.TOOL_CALL.value,
                        tool_name=tool_name,
                        raw_arguments=raw_args,
                        started_at=started,
                        ended_at=ended,
                        status="tool_system_error",
                        error={"type": type(exc).__name__, "message": str(exc)},
                        result_summary="tool system error",
                    )
                    outcome = RunnerOutcome.TOOL_SYSTEM_ERROR
                    error_summary = f"{type(exc).__name__}: {exc}"
                    break

                after = snapshot_mutation_state(env.connection)
                ended = _utc_now()
                step_number += 1
                if result.ok:
                    status = "idempotent_replay" if result.idempotent_replay else "ok"
                    summary = result.message
                    if result.idempotent_replay:
                        summary = f"idempotent replay: {result.message}"
                else:
                    status = "business_denial"
                    summary = result.message

                recorder.record(
                    step_number=step_number,
                    decision_reason=action.decision_reason,
                    action_type=ActionType.TOOL_CALL.value,
                    tool_name=tool_name,
                    raw_arguments=raw_args,
                    started_at=started,
                    ended_at=ended,
                    status=status,
                    tool_result_code=result.code.value,
                    result_summary=summary[:240],
                    state_changes=diff_state(before, after),
                )
                previous = result
            else:
                # while loop exhausted without finish
                outcome = RunnerOutcome.MAXIMUM_STEPS_EXCEEDED
                error_summary = f"exceeded maximum_steps={task.maximum_steps}"

            # Grade while connection is still open.
            if outcome is RunnerOutcome.COMPLETED:
                grader_results = [
                    self._final_state.grade(task, env.connection),
                    self._tool_call.grade(task, recorder.steps),
                    self._policy.grade(task, env.connection, recorder.steps),
                ]
            else:
                grader_results = []

            passed, overall_score = compute_overall(grader_results, outcome)
            actual_state = summarize_assertion_state(
                env.connection, list(task.expected_final_state)
            )
            total_latency_ms = sum(step.latency_ms for step in recorder.steps)
            metadata: dict[str, Any] = {
                "fixture_id": task.fixture_id,
                "user_request": redact_text_pii(task.user_request),
                "expected_final_state": [
                    assertion.model_dump(mode="json")
                    for assertion in task.expected_final_state
                ],
                "actual_state_summary": actual_state,
                "total_latency_ms": total_latency_ms,
            }
            result_body = TrialResult(
                run_id=run_id,
                task_id=task.task_id,
                agent_name=agent.name,
                runner_outcome=outcome,
                passed=passed,
                overall_score=overall_score,
                step_count=len(recorder.steps),
                final_response=final_response,
                grader_results=grader_results,
                trace=recorder.steps,
                artifact_path=None,
                error_summary=error_summary,
                metadata=metadata,
            )
            artifact_path = self._write_artifact(result_body)
            return TrialResult(
                run_id=run_id,
                task_id=task.task_id,
                agent_name=agent.name,
                runner_outcome=outcome,
                passed=passed,
                overall_score=overall_score,
                step_count=len(recorder.steps),
                final_response=final_response,
                grader_results=grader_results,
                trace=recorder.steps,
                artifact_path=str(artifact_path),
                error_summary=error_summary,
                metadata=metadata,
            )
        finally:
            env.close()

    def _write_artifact(self, result: TrialResult) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"{result.task_id}_{result.run_id}.json"
        payload = scrub_payload_pii(result.model_dump(mode="json"))
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return path


__all__ = [
    "TrialRunner",
    "compute_overall",
    "diff_state",
    "snapshot_mutation_state",
    "summarize_assertion_state",
]
