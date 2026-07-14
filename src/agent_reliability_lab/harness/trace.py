"""Harness trace recording with argument redaction."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_RE = re.compile(
    r"(email|phone|password|secret|token|credential|api[_-]?key|authorization)",
    re.IGNORECASE,
)


def redact_value(key: str, value: Any) -> Any:
    """Redact sensitive scalar values; recurse into mappings and sequences."""
    if _SENSITIVE_KEY_RE.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(key, item) for item in value]
    return value


def redact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return a redacted copy of tool arguments for trace persistence."""
    return {str(k): redact_value(str(k), v) for k, v in arguments.items()}


class TraceStep(BaseModel):
    """One recorded agent step."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    step_number: int = Field(ge=1)
    agent_name: str
    decision_reason: str
    action_type: str
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    ended_at: datetime
    latency_ms: int = Field(ge=0)
    status: str
    tool_result_code: str | None = None
    result_summary: str = ""
    error: dict[str, Any] | None = None
    state_changes: dict[str, Any] = Field(default_factory=dict)


class TraceRecorder:
    """Owns creation of TraceStep records for a single run."""

    def __init__(self, run_id: str, task_id: str, agent_name: str) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self.agent_name = agent_name
        self.steps: list[TraceStep] = []

    def record(
        self,
        *,
        step_number: int,
        decision_reason: str,
        action_type: str,
        tool_name: str | None,
        raw_arguments: dict[str, Any],
        started_at: datetime,
        ended_at: datetime,
        status: str,
        tool_result_code: str | None = None,
        result_summary: str = "",
        error: dict[str, Any] | None = None,
        state_changes: dict[str, Any] | None = None,
    ) -> TraceStep:
        latency = max(
            0,
            int((ended_at - started_at).total_seconds() * 1000),
        )
        step = TraceStep(
            run_id=self.run_id,
            task_id=self.task_id,
            step_number=step_number,
            agent_name=self.agent_name,
            decision_reason=decision_reason,
            action_type=action_type,
            tool_name=tool_name,
            tool_arguments=redact_arguments(raw_arguments),
            started_at=started_at.astimezone(UTC),
            ended_at=ended_at.astimezone(UTC),
            latency_ms=latency,
            status=status,
            tool_result_code=tool_result_code,
            result_summary=result_summary,
            error=error,
            state_changes=state_changes or {},
        )
        self.steps.append(step)
        return step


__all__ = [
    "REDACTED",
    "TraceRecorder",
    "TraceStep",
    "redact_arguments",
    "redact_value",
]
