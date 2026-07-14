"""Tests for agent protocol, trace redaction, and trial runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from agent_reliability_lab.agents.failing import SkipVerificationAgent
from agent_reliability_lab.agents.protocol import (
    ActionType,
    AgentAction,
    AgentObservation,
)
from agent_reliability_lab.agents.reference import ScriptedReferenceAgent
from agent_reliability_lab.domains.retail.environment import RetailEnvironment
from agent_reliability_lab.harness.results import RunnerOutcome
from agent_reliability_lab.harness.runner import TrialRunner
from agent_reliability_lab.harness.tasks import TaskLoader
from agent_reliability_lab.harness.trace import REDACTED, redact_arguments

SENSITIVE_FRAGMENTS = (
    "alice@example.test",
    "bob@example.test",
    "wrong@example.test",
    "+1-555-0100",
    "+1-555-0101",
    "+1-555-9999",
)


def _assert_artifact_has_no_sensitive_pii(artifact_path: str | None) -> None:
    assert artifact_path is not None
    text = Path(artifact_path).read_text(encoding="utf-8")
    for fragment in SENSITIVE_FRAGMENTS:
        assert fragment not in text, (
            f"sensitive value {fragment!r} leaked into artifact"
        )


class _ScriptedStub:
    def __init__(self, actions: list[AgentAction], name: str = "stub") -> None:
        self._actions = actions
        self._index = 0
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def act(self, observation: AgentObservation) -> AgentAction:
        _ = observation
        if self._index >= len(self._actions):
            return AgentAction(
                action_type=ActionType.FINISH,
                decision_reason="done",
                final_response="done",
            )
        action = self._actions[self._index]
        self._index += 1
        return action


def test_argument_redaction() -> None:
    redacted = redact_arguments(
        {
            "customer_id": "er_cust_alice",
            "email": "alice@example.test",
            "phone": "+1-555-0100",
            "amount_cents": 100,
        }
    )
    assert redacted["customer_id"] == "er_cust_alice"
    assert redacted["email"] == REDACTED
    assert redacted["phone"] == REDACTED
    assert redacted["amount_cents"] == 100


def test_fresh_environment_per_task_no_leakage(tmp_path: Path) -> None:
    runner = TrialRunner(output_dir=tmp_path)
    first = runner.run("eligible_full_return", ScriptedReferenceAgent())
    second = runner.run("eligible_full_return", ScriptedReferenceAgent())
    assert first.passed
    assert second.passed
    assert first.run_id != second.run_id


def test_max_steps_enforced(tmp_path: Path) -> None:
    task = TaskLoader().load("eligible_full_return")
    tiny = task.model_copy(update={"maximum_steps": 1})
    actions = [
        AgentAction(
            action_type=ActionType.TOOL_CALL,
            tool_name="verify_customer",
            arguments={
                "customer_id": "er_cust_alice",
                "email": "alice@example.test",
                "phone": "+1-555-0100",
            },
            decision_reason="verify",
        ),
        AgentAction(
            action_type=ActionType.TOOL_CALL,
            tool_name="get_order",
            arguments={"customer_id": "er_cust_alice", "order_id": "er_ord_1001"},
            decision_reason="order",
        ),
    ]
    runner = TrialRunner(output_dir=tmp_path)
    result = runner.run_task(tiny, _ScriptedStub(actions))
    assert result.runner_outcome is RunnerOutcome.MAXIMUM_STEPS_EXCEEDED
    assert result.step_count == 1
    assert not Path(result.metadata.get("fixture_id", "")).exists()


def test_invalid_tool(tmp_path: Path) -> None:
    task = TaskLoader().load("eligible_full_return")
    agent = _ScriptedStub(
        [
            AgentAction(
                action_type=ActionType.TOOL_CALL,
                tool_name="drop_database",
                arguments={},
                decision_reason="bad tool",
            )
        ]
    )
    result = TrialRunner(output_dir=tmp_path).run_task(task, agent)
    assert result.runner_outcome is RunnerOutcome.INVALID_TOOL
    assert result.trace[0].status == "invalid_tool"
    assert result.trace[0].tool_name == "drop_database"


def test_invalid_arguments(tmp_path: Path) -> None:
    task = TaskLoader().load("eligible_full_return")
    agent = _ScriptedStub(
        [
            AgentAction(
                action_type=ActionType.TOOL_CALL,
                tool_name="verify_customer",
                arguments={"customer_id": "er_cust_alice"},
                decision_reason="missing credentials",
            )
        ]
    )
    result = TrialRunner(output_dir=tmp_path).run_task(task, agent)
    assert result.runner_outcome is RunnerOutcome.INVALID_ARGUMENTS
    assert result.trace[0].status == "invalid_arguments"


def test_business_denial_is_not_system_failure(tmp_path: Path) -> None:
    task = TaskLoader().load("failed_customer_verification")
    result = TrialRunner(output_dir=tmp_path).run_task(task, ScriptedReferenceAgent())
    assert result.runner_outcome is RunnerOutcome.COMPLETED
    assert any(step.status == "business_denial" for step in result.trace)
    assert result.passed


def test_failed_call_preserved_and_redacted(tmp_path: Path) -> None:
    result = TrialRunner(output_dir=tmp_path).run(
        "eligible_full_return", SkipVerificationAgent()
    )
    assert not result.passed
    assert any(step.status == "business_denial" for step in result.trace)
    _assert_artifact_has_no_sensitive_pii(result.artifact_path)
    text = Path(result.artifact_path or "").read_text(encoding="utf-8")
    assert REDACTED in text or "email" not in text.lower()


def test_successful_and_failed_artifacts_never_contain_raw_pii(tmp_path: Path) -> None:
    runner = TrialRunner(output_dir=tmp_path)
    ok = runner.run("eligible_full_return", ScriptedReferenceAgent())
    bad = runner.run("eligible_full_return", SkipVerificationAgent())
    assert ok.passed
    assert not bad.passed
    _assert_artifact_has_no_sensitive_pii(ok.artifact_path)
    _assert_artifact_has_no_sensitive_pii(bad.artifact_path)
    # Cross-customer task also embeds bob@ in the source request.
    cross = runner.run("cross_customer_order_access", ScriptedReferenceAgent())
    assert cross.passed
    _assert_artifact_has_no_sensitive_pii(cross.artifact_path)


def test_cleanup_after_success_and_failure(tmp_path: Path) -> None:
    recorded_paths: list[Path] = []
    original_open = RetailEnvironment.open

    def tracking_open(self: RetailEnvironment) -> RetailEnvironment:
        original_open(self)
        recorded_paths.append(self.db_path)
        return self

    runner = TrialRunner(output_dir=tmp_path)
    with patch.object(RetailEnvironment, "open", tracking_open):
        ok = runner.run("expired_return_window", ScriptedReferenceAgent())
        bad = runner.run("eligible_full_return", SkipVerificationAgent())
    assert ok.passed
    assert not bad.passed
    assert ok.artifact_path is not None
    assert bad.artifact_path is not None
    assert len(recorded_paths) >= 2
    for path in recorded_paths:
        assert not path.exists(), f"temporary database still present: {path}"


def test_reference_agent_passes_all_ten(tmp_path: Path) -> None:
    runner = TrialRunner(output_dir=tmp_path)
    loader = TaskLoader()
    failures: list[str] = []
    for task_id in loader.list_task_ids():
        result = runner.run(task_id, ScriptedReferenceAgent())
        if not result.passed:
            failures.append(
                f"{task_id}: {[g.explanation for g in result.grader_results]}"
            )
    assert failures == []
