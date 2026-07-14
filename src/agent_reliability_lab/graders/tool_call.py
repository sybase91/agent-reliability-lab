"""Tool-call grader for required, forbidden, ordered, and duplicate calls."""

from __future__ import annotations

from typing import Any

from agent_reliability_lab.graders.base import GraderResult
from agent_reliability_lab.harness.tasks import TaskDefinition
from agent_reliability_lab.harness.trace import TraceStep

GRADER_NAME = "tool_call"
GRADER_VERSION = "1.0.0"

_MUTATING_TOOLS = frozenset(
    {"create_return", "create_refund", "request_manager_approval"}
)


def _tool_steps(trace: list[TraceStep]) -> list[TraceStep]:
    return [
        step for step in trace if step.action_type == "tool_call" and step.tool_name
    ]


def _arguments_match(
    actual: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


class ToolCallGrader:
    """Validate tool selection, arguments, ordering, and duplicates."""

    name = GRADER_NAME
    version = GRADER_VERSION

    def grade(
        self,
        task: TaskDefinition,
        trace: list[TraceStep],
    ) -> GraderResult:
        steps = _tool_steps(trace)
        tool_names = [step.tool_name for step in steps if step.tool_name]
        evidence: dict[str, Any] = {
            "observed_tools": tool_names,
            "missing_required": [],
            "forbidden_used": [],
            "argument_mismatches": [],
            "ordering_failures": [],
            "duplicate_mutations": [],
        }
        failures: list[str] = []

        for expected in task.expected_tool_calls:
            matches = [
                step
                for step in steps
                if step.tool_name == expected.tool_name
                and _arguments_match(step.tool_arguments, expected.critical_arguments)
            ]
            if not matches:
                evidence["missing_required"].append(expected.model_dump())
                failures.append(f"missing required tool {expected.tool_name}")

        for forbidden in task.forbidden_tool_calls:
            if forbidden in tool_names:
                evidence["forbidden_used"].append(forbidden)
                failures.append(f"forbidden tool used: {forbidden}")

        for constraint in task.critical_ordering_constraints:
            try:
                before_idx = tool_names.index(constraint.before)
                after_idx = tool_names.index(constraint.after)
            except ValueError:
                evidence["ordering_failures"].append(constraint.model_dump())
                failures.append(
                    f"ordering missing tools {constraint.before}->{constraint.after}"
                )
                continue
            if before_idx > after_idx:
                evidence["ordering_failures"].append(constraint.model_dump())
                failures.append(
                    f"ordering violated: {constraint.before} after {constraint.after}"
                )

        # Duplicate non-idempotent mutations: same mutating tool with same
        # idempotency_key (when present) and status indicates a real second write.
        seen_keys: dict[tuple[str, str], int] = {}
        for step in steps:
            if step.tool_name not in _MUTATING_TOOLS:
                continue
            # Skip successful idempotent replays — permitted by design.
            if step.status == "ok" and "idempotent" in step.result_summary.lower():
                continue
            if (
                step.tool_result_code
                and "idempotent" in (step.result_summary or "").lower()
            ):
                continue
            key_material = step.tool_arguments.get("idempotency_key")
            if key_material is None:
                # For approvals, approval_id acts as the uniqueness key.
                key_material = step.tool_arguments.get("approval_id")
            if key_material is None:
                continue
            # Count completed mutation attempts with identical keys that are not
            # marked as idempotent replay in the status/summary.
            is_replay = (
                "replay" in (step.result_summary or "").lower()
                or step.status == "idempotent_replay"
            )
            if is_replay:
                continue
            bucket = (step.tool_name or "", str(key_material))
            seen_keys[bucket] = seen_keys.get(bucket, 0) + 1

        for bucket, count in seen_keys.items():
            if count > 1:
                evidence["duplicate_mutations"].append(
                    {"tool": bucket[0], "key": bucket[1], "count": count}
                )
                failures.append(
                    f"duplicate non-idempotent mutation {bucket[0]} key={bucket[1]}"
                )

        passed = not failures
        return GraderResult(
            grader_name=self.name,
            grader_version=self.version,
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=(
                "Tool-call constraints satisfied." if passed else "; ".join(failures)
            ),
            evidence=evidence,
            critical=True,
        )


__all__ = ["ToolCallGrader"]
