"""Final-state grader using whitelisted declarative assertions only."""

from __future__ import annotations

import sqlite3
from typing import Any

from agent_reliability_lab.graders.base import GraderResult
from agent_reliability_lab.harness.tasks import (
    ALLOWED_TABLES,
    StateAssertion,
    TaskDefinition,
)

GRADER_NAME = "final_state"
GRADER_VERSION = "1.0.0"


def _assert_count_and_fields(
    connection: sqlite3.Connection,
    assertion: StateAssertion,
) -> dict[str, Any]:
    if assertion.table not in ALLOWED_TABLES:
        return {
            "ok": False,
            "reason": f"table {assertion.table!r} is not allowed",
        }

    where_parts: list[str] = []
    values: list[Any] = []
    for column, expected in assertion.filters.items():
        if not column.isidentifier():
            return {"ok": False, "reason": f"unsafe filter column {column!r}"}
        where_parts.append(f"{column} = ?")
        values.append(expected)

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    # Table and column identifiers are whitelisted / identifier-validated above.
    count_sql = f"SELECT COUNT(*) AS n FROM {assertion.table}{where_sql}"
    count = int(connection.execute(count_sql, values).fetchone()["n"])
    if count != assertion.expected_count:
        return {
            "ok": False,
            "reason": (
                f"{assertion.table} count {count} != expected "
                f"{assertion.expected_count}"
            ),
            "actual_count": count,
            "expected_count": assertion.expected_count,
            "filters": assertion.filters,
        }

    if assertion.expected_fields and assertion.expected_count > 0:
        row_sql = f"SELECT * FROM {assertion.table}{where_sql} LIMIT 1"
        row = connection.execute(row_sql, values).fetchone()
        if row is None:
            return {"ok": False, "reason": "expected row missing"}
        row_map = dict(row)
        for field, expected in assertion.expected_fields.items():
            if not field.isidentifier():
                return {"ok": False, "reason": f"unsafe field {field!r}"}
            actual = row_map.get(field)
            if actual != expected:
                return {
                    "ok": False,
                    "reason": (f"{assertion.table}.{field}={actual!r} != {expected!r}"),
                    "field": field,
                    "actual": actual,
                    "expected": expected,
                }

    return {
        "ok": True,
        "table": assertion.table,
        "filters": assertion.filters,
        "expected_count": assertion.expected_count,
    }


class FinalStateGrader:
    """Inspect persisted SQLite state before environment cleanup."""

    name = GRADER_NAME
    version = GRADER_VERSION

    def grade(
        self,
        task: TaskDefinition,
        connection: sqlite3.Connection,
    ) -> GraderResult:
        details: list[dict[str, Any]] = []
        failures = 0
        for assertion in task.expected_final_state:
            detail = _assert_count_and_fields(connection, assertion)
            details.append(detail)
            if not detail.get("ok"):
                failures += 1

        total = max(1, len(task.expected_final_state))
        passed = failures == 0
        score = 0.0 if not passed else 1.0
        if task.expected_final_state and passed:
            score = 1.0
        elif task.expected_final_state:
            score = max(0.0, (total - failures) / total)

        return GraderResult(
            grader_name=self.name,
            grader_version=self.version,
            passed=passed,
            score=score if passed else 0.0,
            explanation=(
                "All final-state assertions passed."
                if passed
                else f"{failures} final-state assertion(s) failed."
            ),
            evidence={"assertions": details},
            critical=True,
        )


__all__ = ["FinalStateGrader"]
