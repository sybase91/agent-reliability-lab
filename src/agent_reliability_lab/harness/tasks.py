"""JSON evaluation task definitions and loader.

Tasks are data only: no executable code, raw SQL, or Python expressions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_reliability_lab.domains.retail.database import REQUIRED_TABLES
from agent_reliability_lab.domains.retail.seed import list_fixture_ids
from agent_reliability_lab.domains.retail.tools import TOOL_NAMES

ALLOWED_TABLES: Final[frozenset[str]] = frozenset(REQUIRED_TABLES)

# Equality-compatible scalar values only (no nested structures that encode SQL).
FilterValue = str | int | float | bool | None


class StateAssertion(BaseModel):
    """Whitelisted declarative check against persisted SQLite state."""

    model_config = ConfigDict(extra="forbid")

    table: str
    filters: dict[str, FilterValue] = Field(default_factory=dict)
    expected_count: int = Field(ge=0)
    expected_fields: dict[str, FilterValue] = Field(default_factory=dict)

    @field_validator("table")
    @classmethod
    def _table_must_be_allowed(cls, value: str) -> str:
        if value not in ALLOWED_TABLES:
            known = ", ".join(sorted(ALLOWED_TABLES))
            msg = f"table {value!r} is not allowed; known: {known}"
            raise ValueError(msg)
        return value

    @field_validator("filters", "expected_fields")
    @classmethod
    def _reject_unsafe_keys(
        cls, value: dict[str, FilterValue]
    ) -> dict[str, FilterValue]:
        for key in value:
            if not key.isidentifier():
                msg = f"column name {key!r} must be a simple identifier"
                raise ValueError(msg)
            lowered = key.lower()
            if any(token in lowered for token in ("select", "drop", "insert", ";")):
                msg = f"column name {key!r} looks unsafe"
                raise ValueError(msg)
        return value


class ExpectedToolCall(BaseModel):
    """A tool that must appear in the trace, optionally with critical args."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    critical_arguments: dict[str, FilterValue] = Field(default_factory=dict)

    @field_validator("tool_name")
    @classmethod
    def _known_tool(cls, value: str) -> str:
        if value not in TOOL_NAMES:
            known = ", ".join(TOOL_NAMES)
            msg = f"unknown tool {value!r}; known: {known}"
            raise ValueError(msg)
        return value


class CriticalOrderingConstraint(BaseModel):
    """Require that ``before`` appears in the trace before ``after``."""

    model_config = ConfigDict(extra="forbid")

    before: str
    after: str

    @field_validator("before", "after")
    @classmethod
    def _known_tool(cls, value: str) -> str:
        if value not in TOOL_NAMES:
            known = ", ".join(TOOL_NAMES)
            msg = f"unknown tool {value!r}; known: {known}"
            raise ValueError(msg)
        return value


class TaskDefinition(BaseModel):
    """Validated evaluation task. Extra fields are forbidden."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    task_version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    business_description: str = Field(min_length=1)
    user_request: str = Field(min_length=1)
    fixture_id: str
    policy_tags: list[str] = Field(default_factory=list)
    maximum_steps: int = Field(ge=1, le=100)
    expected_outcome: str = Field(min_length=1)
    expected_final_state: list[StateAssertion] = Field(default_factory=list)
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    forbidden_tool_calls: list[str] = Field(default_factory=list)
    critical_ordering_constraints: list[CriticalOrderingConstraint] = Field(
        default_factory=list
    )

    @field_validator("fixture_id")
    @classmethod
    def _fixture_exists(cls, value: str) -> str:
        known = list_fixture_ids()
        if value not in known:
            msg = f"unknown fixture_id {value!r}; known: {', '.join(known)}"
            raise ValueError(msg)
        return value

    @field_validator("forbidden_tool_calls")
    @classmethod
    def _forbidden_tools_known(cls, value: list[str]) -> list[str]:
        for name in value:
            if name not in TOOL_NAMES:
                known = ", ".join(TOOL_NAMES)
                msg = f"unknown forbidden tool {name!r}; known: {known}"
                raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _reject_sql_or_code_smells(self) -> TaskDefinition:
        blobs = [
            self.business_description,
            self.user_request,
            self.expected_outcome,
            self.title,
        ]
        for blob in blobs:
            lowered = blob.lower()
            if "select " in lowered or "drop table" in lowered or "'; " in lowered:
                msg = "task text must not contain SQL-like content"
                raise ValueError(msg)
            if "__import__" in blob or "eval(" in blob or "exec(" in blob:
                msg = "task text must not contain Python expressions"
                raise ValueError(msg)
        return self


def find_tasks_directory(start: Path | None = None) -> Path:
    """Locate ``evals/retail/tasks`` by walking ancestors of ``start`` or cwd."""
    roots: list[Path] = []
    if start is not None:
        roots.append(start if start.is_dir() else start.parent)
    roots.append(Path.cwd())
    # Editable install: package lives under ``src/agent_reliability_lab/...``
    roots.append(Path(__file__).resolve().parents[3])
    roots.append(Path(__file__).resolve().parents[4])

    seen: set[Path] = set()
    for root in roots:
        current = root.resolve()
        for candidate in (current, *current.parents):
            if candidate in seen:
                continue
            seen.add(candidate)
            tasks_dir = candidate / "evals" / "retail" / "tasks"
            if tasks_dir.is_dir():
                return tasks_dir

    msg = "could not locate evals/retail/tasks directory"
    raise FileNotFoundError(msg)


class TaskLoader:
    """Load and validate JSON evaluation tasks. Fails closed."""

    def __init__(self, tasks_dir: Path | None = None) -> None:
        self.tasks_dir = tasks_dir if tasks_dir is not None else find_tasks_directory()

    def list_task_ids(self) -> tuple[str, ...]:
        """Return sorted unique task IDs discovered from ``*.json`` files."""
        ids = sorted(path.stem for path in self.tasks_dir.glob("*.json"))
        return tuple(ids)

    def load(self, task_id: str) -> TaskDefinition:
        """Load and validate a single task by ID."""
        path = self.tasks_dir / f"{task_id}.json"
        if not path.is_file():
            known = ", ".join(self.list_task_ids()) or "(none)"
            msg = f"unknown task_id {task_id!r}; known: {known}"
            raise FileNotFoundError(msg)
        return self._load_path(path)

    def load_all(self) -> tuple[TaskDefinition, ...]:
        """Validate every task file; enforce unique IDs; stable sorted order."""
        paths = sorted(self.tasks_dir.glob("*.json"))
        if not paths:
            msg = f"no task JSON files found in {self.tasks_dir}"
            raise FileNotFoundError(msg)

        tasks: list[TaskDefinition] = []
        seen: set[str] = set()
        for path in paths:
            task = self._load_path(path)
            if task.task_id != path.stem:
                msg = (
                    f"task_id {task.task_id!r} does not match filename stem "
                    f"{path.stem!r}"
                )
                raise ValueError(msg)
            if task.task_id in seen:
                msg = f"duplicate task_id {task.task_id!r}"
                raise ValueError(msg)
            seen.add(task.task_id)
            tasks.append(task)
        return tuple(sorted(tasks, key=lambda t: t.task_id))

    def _load_path(self, path: Path) -> TaskDefinition:
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"invalid JSON in {path}: {exc}"
            raise ValueError(msg) from exc
        try:
            return TaskDefinition.model_validate(raw)
        except Exception as exc:
            msg = f"invalid task definition in {path}: {exc}"
            raise ValueError(msg) from exc


__all__ = [
    "ALLOWED_TABLES",
    "CriticalOrderingConstraint",
    "ExpectedToolCall",
    "StateAssertion",
    "TaskDefinition",
    "TaskLoader",
    "find_tasks_directory",
]
