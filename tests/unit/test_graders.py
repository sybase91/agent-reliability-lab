"""Tests for the three independent graders."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_reliability_lab.agents.failing import (
    ApprovalBypassAgent,
    DuplicateRefundAgent,
    SkipVerificationAgent,
)
from agent_reliability_lab.agents.reference import ScriptedReferenceAgent
from agent_reliability_lab.domains.retail.environment import RetailEnvironment
from agent_reliability_lab.graders.final_state import FinalStateGrader
from agent_reliability_lab.graders.tool_call import ToolCallGrader
from agent_reliability_lab.harness.runner import TrialRunner
from agent_reliability_lab.harness.tasks import StateAssertion, TaskLoader
from agent_reliability_lab.harness.trace import TraceStep


def _step(
    *,
    tool_name: str,
    status: str = "ok",
    args: dict | None = None,
    code: str | None = "OK",
    summary: str = "ok",
    step_number: int = 1,
) -> TraceStep:
    now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    return TraceStep(
        run_id="r",
        task_id="t",
        step_number=step_number,
        agent_name="a",
        decision_reason="reason",
        action_type="tool_call",
        tool_name=tool_name,
        tool_arguments=args or {},
        started_at=now,
        ended_at=now,
        latency_ms=0,
        status=status,
        tool_result_code=code,
        result_summary=summary,
    )


def test_final_state_grader_true_positive(tmp_path: Path) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "eligible_full_return", ScriptedReferenceAgent()
    )
    final = next(g for g in result.grader_results if g.grader_name == "final_state")
    assert final.passed
    assert final.score == 1.0
    assert "assertions" in final.evidence


def test_final_state_grader_intentional_failure() -> None:
    task = TaskLoader().load("eligible_full_return")
    with RetailEnvironment("eligible_return") as env:
        grade = FinalStateGrader().grade(task, env.connection)
    assert not grade.passed
    assert grade.critical
    assert grade.evidence["assertions"]


def test_declarative_assertion_rejects_unsafe_table() -> None:
    with pytest.raises(ValidationError):
        StateAssertion(table="sqlite_master", expected_count=1)


def test_tool_call_grader_ordering_and_forbidden() -> None:
    task = TaskLoader().load("expired_return_window")
    # Missing verify, uses forbidden create_return
    trace = [
        _step(tool_name="create_return", args={"order_id": "ex_ord_1001"}),
        _step(
            tool_name="check_return_eligibility",
            args={"order_id": "ex_ord_1001"},
            step_number=2,
        ),
    ]
    grade = ToolCallGrader().grade(task, trace)
    assert not grade.passed
    assert grade.evidence["forbidden_used"] or grade.evidence["missing_required"]


def test_tool_call_permits_idempotent_replay(tmp_path: Path) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "idempotent_refund_retry", ScriptedReferenceAgent()
    )
    tool = next(g for g in result.grader_results if g.grader_name == "tool_call")
    assert result.passed
    assert tool.passed
    assert any(step.status == "idempotent_replay" for step in result.trace)


def test_policy_grader_detects_skip_verification(tmp_path: Path) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "eligible_full_return", SkipVerificationAgent()
    )
    policy = next(g for g in result.grader_results if g.grader_name == "policy")
    assert not result.passed
    assert not policy.passed
    assert policy.evidence["auth_violations"]


def test_policy_grader_detects_approval_bypass(tmp_path: Path) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "high_value_refund_approval", ApprovalBypassAgent()
    )
    assert not result.passed
    names = {g.grader_name: g for g in result.grader_results}
    assert not names["final_state"].passed or not names["tool_call"].passed
    # Refund should not persist without approval.
    assert not names["final_state"].passed


def test_duplicate_refund_fails_graders(tmp_path: Path) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "eligible_full_return", DuplicateRefundAgent()
    )
    assert not result.passed
    # Second refund is a business denial; final state may still have one refund
    # but tool/policy expectations for the task likely fail on missing tools.
    assert any(not g.passed for g in result.grader_results)


def test_critical_failure_zeros_overall_score(tmp_path: Path) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "eligible_full_return", SkipVerificationAgent()
    )
    assert not result.passed
    assert result.overall_score == 0.0


def test_policy_grader_false_positive_resistance_on_owned_access(
    tmp_path: Path,
) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "eligible_full_return", ScriptedReferenceAgent()
    )
    policy = next(g for g in result.grader_results if g.grader_name == "policy")
    assert policy.passed
    assert policy.evidence["auth_violations"] == []
