"""Typed view models for the evaluation dashboard (no Streamlit imports)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunSummaryVM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    status_label: str
    task_id: str
    agent_name: str
    step_count: int
    total_latency_ms: int
    grader_pass_count: int
    grader_total: int
    overall_score: float
    runner_outcome: str


class GraderCardVM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grader_name: str
    display_name: str
    passed: bool
    status_label: str
    score: float
    explanation: str
    evidence_summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class TraceStepVM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_number: int
    decision_reason: str
    action_type: str
    tool_name: str | None
    arguments_display: str
    tool_result_code: str | None
    result_summary: str
    latency_ms: int
    status: str
    state_changes_display: str
    error_display: str | None


class StateDiffVM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_display: str
    actual_display: str
    diff_display: str


class FailureInsightVM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    point_of_failure: str
    catching_grader: str
    why_failed: str
    state_consequence: str


class DashboardViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: RunSummaryVM
    graders: list[GraderCardVM]
    steps: list[TraceStepVM]
    state: StateDiffVM
    failure: FailureInsightVM | None
    artifact_path: str | None
    artifact_json: str
    user_request_display: str


__all__ = [
    "DashboardViewModel",
    "FailureInsightVM",
    "GraderCardVM",
    "RunSummaryVM",
    "StateDiffVM",
    "TraceStepVM",
]
