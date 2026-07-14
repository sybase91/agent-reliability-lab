"""Pure formatters for dashboard view models (no Streamlit)."""

from __future__ import annotations

import json
from typing import Any

from agent_reliability_lab.graders.base import GraderResult
from agent_reliability_lab.harness.results import TrialResult
from agent_reliability_lab.harness.tasks import TaskDefinition
from agent_reliability_lab.harness.trace import (
    REDACTED,
    TraceStep,
    redact_text_pii,
    scrub_payload_pii,
)
from agent_reliability_lab.presentation.view_models import (
    DashboardViewModel,
    FailureInsightVM,
    GraderCardVM,
    RunSummaryVM,
    StateDiffVM,
    TraceStepVM,
)

_GRADER_DISPLAY = {
    "final_state": "Final State",
    "tool_call": "Tool Calls",
    "policy": "Policy Compliance",
}

KNOWN_SENSITIVE_FRAGMENTS = (
    "alice@example.test",
    "bob@example.test",
    "wrong@example.test",
    "+1-555-0100",
    "+1-555-0101",
    "+1-555-9999",
)


def status_label(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def format_latency_ms(latency_ms: int) -> str:
    if latency_ms < 1000:
        return f"{latency_ms} ms"
    return f"{latency_ms / 1000:.2f} s"


def pretty_json(value: Any) -> str:
    return json.dumps(scrub_payload_pii(value), indent=2, sort_keys=True, default=str)


def summarize_evidence(evidence: dict[str, Any]) -> str:
    if not evidence:
        return "No structured evidence."
    parts: list[str] = []
    for key, value in evidence.items():
        if isinstance(value, list):
            parts.append(f"{key}: {len(value)} item(s)")
        elif isinstance(value, dict):
            parts.append(f"{key}: {len(value)} field(s)")
        else:
            parts.append(f"{key}: {value!r}")
    return "; ".join(parts[:8])


def format_state_changes(state_changes: dict[str, Any]) -> str:
    if not state_changes:
        return "No task-relevant state changes."
    lines: list[str] = []
    for key, change in state_changes.items():
        if isinstance(change, dict) and "before" in change and "after" in change:
            lines.append(f"{key}: {change['before']!r} → {change['after']!r}")
        else:
            lines.append(f"{key}: {change!r}")
    return "\n".join(lines)


def build_state_diff(result: TrialResult) -> StateDiffVM:
    expected = result.metadata.get("expected_final_state") or []
    actual = result.metadata.get("actual_state_summary") or []
    diffs: list[str] = []
    for item in actual:
        if not isinstance(item, dict):
            continue
        table = item.get("table")
        expected_count = item.get("expected_count")
        actual_count = item.get("actual_count")
        if expected_count != actual_count:
            diffs.append(f"{table}: count {actual_count} (expected {expected_count})")
        expected_fields = item.get("expected_fields") or {}
        actual_fields = item.get("actual_fields") or {}
        for field, exp in expected_fields.items():
            act = actual_fields.get(field)
            if act != exp:
                diffs.append(f"{table}.{field}: {act!r} (expected {exp!r})")
    if not diffs:
        diffs.append("No differences between expected and actual asserted fields.")
    return StateDiffVM(
        expected_display=pretty_json(expected),
        actual_display=pretty_json(actual),
        diff_display="\n".join(diffs),
    )


def build_failure_insight(result: TrialResult) -> FailureInsightVM | None:
    if result.passed:
        return None

    failing_graders = [g for g in result.grader_results if not g.passed]
    catching = failing_graders[0] if failing_graders else None

    failure_step: TraceStep | None = None
    for step in result.trace:
        if step.status in {
            "business_denial",
            "invalid_tool",
            "invalid_arguments",
            "agent_error",
            "tool_system_error",
        }:
            failure_step = step
            break

    if failure_step is not None:
        point = (
            f"Step {failure_step.step_number}: "
            f"{failure_step.tool_name or failure_step.action_type} "
            f"({failure_step.status})"
        )
    elif catching is not None:
        point = f"Grader '{catching.grader_name}' rejected the final outcome"
    else:
        point = f"Runner outcome: {result.runner_outcome.value}"

    catching_name = (
        _GRADER_DISPLAY.get(catching.grader_name, catching.grader_name)
        if catching is not None
        else "Runner / incomplete grading"
    )
    why = (
        catching.explanation
        if catching is not None
        else (result.error_summary or "Run did not complete successfully.")
    )
    state = result.metadata.get("actual_state_summary") or []
    consequence = (
        "Persisted state does not match the scenario's expected final assertions."
        if any(
            isinstance(item, dict)
            and item.get("actual_count") != item.get("expected_count")
            for item in state
        )
        else "No unexpected persisted mutations beyond expected denials."
    )
    return FailureInsightVM(
        point_of_failure=redact_text_pii(point),
        catching_grader=catching_name,
        why_failed=redact_text_pii(why),
        state_consequence=redact_text_pii(consequence),
    )


def _grader_card(grader: GraderResult) -> GraderCardVM:
    return GraderCardVM(
        grader_name=grader.grader_name,
        display_name=_GRADER_DISPLAY.get(grader.grader_name, grader.grader_name),
        passed=grader.passed,
        status_label=status_label(grader.passed),
        score=grader.score,
        explanation=redact_text_pii(grader.explanation),
        evidence_summary=redact_text_pii(summarize_evidence(grader.evidence)),
        evidence=scrub_payload_pii(grader.evidence),
    )


def _step_card(step: TraceStep) -> TraceStepVM:
    error_display = None
    if step.error:
        error_display = pretty_json(step.error)
    elif step.status == "business_denial":
        error_display = (
            f"Business denial: {step.tool_result_code} — {step.result_summary}"
        )
    return TraceStepVM(
        step_number=step.step_number,
        decision_reason=redact_text_pii(step.decision_reason),
        action_type=step.action_type,
        tool_name=step.tool_name,
        arguments_display=pretty_json(step.tool_arguments),
        tool_result_code=step.tool_result_code,
        result_summary=redact_text_pii(step.result_summary),
        latency_ms=step.latency_ms,
        status=step.status,
        state_changes_display=format_state_changes(step.state_changes),
        error_display=error_display,
    )


def build_dashboard_view(
    task: TaskDefinition,
    result: TrialResult,
) -> DashboardViewModel:
    """Map harness output into a display-safe dashboard view model."""
    grader_pass_count = sum(1 for g in result.grader_results if g.passed)
    total_latency = int(result.metadata.get("total_latency_ms") or 0)
    if not total_latency:
        total_latency = sum(step.latency_ms for step in result.trace)

    summary = RunSummaryVM(
        passed=result.passed,
        status_label=status_label(result.passed),
        task_id=result.task_id,
        agent_name=result.agent_name,
        step_count=result.step_count,
        total_latency_ms=total_latency,
        grader_pass_count=grader_pass_count,
        grader_total=len(result.grader_results),
        overall_score=result.overall_score,
        runner_outcome=result.runner_outcome.value,
    )

    artifact_payload = scrub_payload_pii(result.model_dump(mode="json"))
    user_request = redact_text_pii(
        str(result.metadata.get("user_request") or task.user_request)
    )

    return DashboardViewModel(
        summary=summary,
        graders=[_grader_card(g) for g in result.grader_results],
        steps=[_step_card(step) for step in result.trace],
        state=build_state_diff(result),
        failure=build_failure_insight(result),
        artifact_path=result.artifact_path,
        artifact_json=json.dumps(artifact_payload, indent=2, sort_keys=True) + "\n",
        user_request_display=user_request,
    )


def contains_known_sensitive_fragment(text: str) -> bool:
    lowered = text.lower()
    return any(fragment.lower() in lowered for fragment in KNOWN_SENSITIVE_FRAGMENTS)


__all__ = [
    "KNOWN_SENSITIVE_FRAGMENTS",
    "REDACTED",
    "build_dashboard_view",
    "build_failure_insight",
    "build_state_diff",
    "contains_known_sensitive_fragment",
    "format_latency_ms",
    "format_state_changes",
    "pretty_json",
    "status_label",
    "summarize_evidence",
]
