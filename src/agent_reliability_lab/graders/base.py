"""Shared grader result model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraderResult(BaseModel):
    """Outcome of one independent grader."""

    model_config = ConfigDict(extra="forbid")

    grader_name: str
    grader_version: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    explanation: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    critical: bool = True


__all__ = ["GraderResult"]
