"""Presentation helpers for the Agent Reliability Lab dashboard."""

from __future__ import annotations

from agent_reliability_lab.agents import build_agent
from agent_reliability_lab.harness.results import TrialResult
from agent_reliability_lab.harness.runner import TrialRunner
from agent_reliability_lab.harness.tasks import TaskDefinition, TaskLoader
from agent_reliability_lab.harness.trace import redact_text_pii
from agent_reliability_lab.presentation.formatters import build_dashboard_view
from agent_reliability_lab.presentation.view_models import DashboardViewModel

AGENT_CHOICES: tuple[str, ...] = (
    "reference",
    "skip_verification",
    "approval_bypass",
    "duplicate_refund",
)

DETERMINISTIC_MODE_CAPTION = (
    "Deterministic MVP mode: the selected scenario defines the expected behavior. "
    "The request text is recorded for the run but is not semantically interpreted "
    "by an LLM."
)


def list_scenario_ids() -> list[str]:
    return list(TaskLoader().list_task_ids())


def list_agent_ids() -> list[str]:
    return list(AGENT_CHOICES)


def load_scenario(task_id: str) -> TaskDefinition:
    return TaskLoader().load(task_id)


def default_request_for_scenario(task_id: str) -> str:
    """Return the scenario request with PII redacted for safe UI display."""
    task = load_scenario(task_id)
    return redact_text_pii(task.user_request)


def run_dashboard_evaluation(
    *,
    task_id: str,
    agent_name: str,
    user_request: str,
    output_dir: str = "artifacts",
) -> tuple[TaskDefinition, TrialResult, DashboardViewModel]:
    """Execute one evaluation and build the dashboard view model."""
    task = load_scenario(task_id)
    # Preserve deterministic scripts; edited text is recorded (already UI-redacted).
    task_for_run = task.model_copy(update={"user_request": user_request})
    runner = TrialRunner(output_dir=output_dir)
    result = runner.run_task(task_for_run, build_agent(agent_name))
    view = build_dashboard_view(task_for_run, result)
    return task_for_run, result, view


__all__ = [
    "AGENT_CHOICES",
    "DETERMINISTIC_MODE_CAPTION",
    "DashboardViewModel",
    "build_dashboard_view",
    "default_request_for_scenario",
    "list_agent_ids",
    "list_scenario_ids",
    "load_scenario",
    "run_dashboard_evaluation",
]
