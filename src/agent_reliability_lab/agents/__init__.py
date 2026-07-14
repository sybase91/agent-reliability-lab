"""Agent implementations for evaluation (reference and failing demos)."""

from agent_reliability_lab.agents.failing import (
    ApprovalBypassAgent,
    DuplicateRefundAgent,
    SkipVerificationAgent,
)
from agent_reliability_lab.agents.protocol import (
    ActionType,
    Agent,
    AgentAction,
    AgentObservation,
)
from agent_reliability_lab.agents.reference import ScriptedReferenceAgent


def build_agent(agent_name: str) -> Agent:
    """Factory for CLI-selected agents."""
    mapping: dict[str, type] = {
        "reference": ScriptedReferenceAgent,
        "skip_verification": SkipVerificationAgent,
        "approval_bypass": ApprovalBypassAgent,
        "duplicate_refund": DuplicateRefundAgent,
    }
    try:
        cls = mapping[agent_name]
    except KeyError as exc:
        known = ", ".join(sorted(mapping))
        msg = f"unknown agent {agent_name!r}; known: {known}"
        raise ValueError(msg) from exc
    return cls()  # type: ignore[no-any-return]


__all__ = [
    "ActionType",
    "Agent",
    "AgentAction",
    "AgentObservation",
    "ApprovalBypassAgent",
    "DuplicateRefundAgent",
    "ScriptedReferenceAgent",
    "SkipVerificationAgent",
    "build_agent",
]
