"""Trial result and runner outcome models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_reliability_lab.graders.base import GraderResult
from agent_reliability_lab.harness.trace import TraceStep


class RunnerOutcome(StrEnum):
    COMPLETED = "completed"
    MAXIMUM_STEPS_EXCEEDED = "maximum_steps_exceeded"
    AGENT_ERROR = "agent_error"
    INVALID_TOOL = "invalid_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    TOOL_SYSTEM_ERROR = "tool_system_error"


class TrialResult(BaseModel):
    """JSON-safe evaluation result for one task run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    agent_name: str
    runner_outcome: RunnerOutcome
    passed: bool
    overall_score: float = Field(ge=0.0, le=1.0)
    step_count: int = Field(ge=0)
    final_response: str | None = None
    grader_results: list[GraderResult] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    artifact_path: str | None = None
    error_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "RunnerOutcome",
    "TrialResult",
]
