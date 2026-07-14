"""Typed agent protocol for deterministic evaluation agents."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_reliability_lab.domains.retail.tools import ToolResult


class ActionType(StrEnum):
    TOOL_CALL = "tool_call"
    FINISH = "finish"


class AgentAction(BaseModel):
    """Next action chosen by an agent under test."""

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    decision_reason: str = Field(min_length=1)
    final_response: str | None = None

    @model_validator(mode="after")
    def _validate_by_type(self) -> AgentAction:
        if self.action_type is ActionType.TOOL_CALL:
            if not self.tool_name:
                msg = "tool_call actions require tool_name"
                raise ValueError(msg)
        elif self.action_type is ActionType.FINISH:
            if self.tool_name is not None:
                msg = "finish actions must not set tool_name"
                raise ValueError(msg)
            if self.final_response is None or not self.final_response.strip():
                msg = "finish actions require final_response"
                raise ValueError(msg)
        return self


class AgentObservation(BaseModel):
    """What the runner exposes to an agent for the next decision."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    user_request: str
    current_step: int = Field(ge=0)
    steps_remaining: int = Field(ge=0)
    previous_tool_result: ToolResult | None = None


@runtime_checkable
class Agent(Protocol):
    """Minimal agent interface used by TrialRunner."""

    @property
    def name(self) -> str: ...

    def act(self, observation: AgentObservation) -> AgentAction: ...


__all__ = [
    "ActionType",
    "Agent",
    "AgentAction",
    "AgentObservation",
]
