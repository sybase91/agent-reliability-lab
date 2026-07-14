"""Tests for JSON evaluation task definitions and TaskLoader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_reliability_lab.domains.retail.seed import list_fixture_ids
from agent_reliability_lab.domains.retail.tools import TOOL_NAMES
from agent_reliability_lab.harness.tasks import (
    StateAssertion,
    TaskDefinition,
    TaskLoader,
    find_tasks_directory,
)

EXPECTED_TASK_IDS = (
    "already_refunded_order",
    "cross_customer_order_access",
    "eligible_full_return",
    "expired_return_window",
    "failed_customer_verification",
    "final_sale_item",
    "high_value_refund_approval",
    "idempotent_refund_retry",
    "missing_order",
    "partial_quantity_return",
)


def test_find_tasks_directory() -> None:
    path = find_tasks_directory()
    assert path.is_dir()
    assert path.name == "tasks"


def test_loader_lists_exactly_ten_tasks_in_stable_order() -> None:
    loader = TaskLoader()
    assert loader.list_task_ids() == EXPECTED_TASK_IDS


def test_loader_validates_all_ten_definitions() -> None:
    loader = TaskLoader()
    tasks = loader.load_all()
    assert len(tasks) == 10
    assert tuple(t.task_id for t in tasks) == EXPECTED_TASK_IDS
    for task in tasks:
        assert task.fixture_id in list_fixture_ids()
        for expected in task.expected_tool_calls:
            assert expected.tool_name in TOOL_NAMES
        for forbidden in task.forbidden_tool_calls:
            assert forbidden in TOOL_NAMES


def test_load_single_task() -> None:
    task = TaskLoader().load("eligible_full_return")
    assert task.task_id == "eligible_full_return"
    assert task.fixture_id == "eligible_return"
    assert task.maximum_steps >= 1


def test_unknown_task_fails_closed() -> None:
    with pytest.raises(FileNotFoundError, match="unknown task_id"):
        TaskLoader().load("does_not_exist")


def test_extra_fields_forbidden() -> None:
    payload = TaskLoader().load("eligible_full_return").model_dump(mode="json")
    payload["sql"] = "SELECT 1"
    with pytest.raises(ValidationError):
        TaskDefinition.model_validate(payload)


def test_state_assertion_rejects_unknown_table() -> None:
    with pytest.raises(ValidationError):
        StateAssertion(table="not_a_table", expected_count=0)


def test_state_assertion_rejects_unsafe_column() -> None:
    with pytest.raises(ValidationError):
        StateAssertion(
            table="returns",
            filters={"order_id; drop table": "x"},
            expected_count=0,
        )


def test_invalid_fixture_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_fixture.json"
    path.write_text(
        json.dumps(
            {
                "task_id": "bad_fixture",
                "task_version": "1.0.0",
                "title": "Bad",
                "business_description": "desc",
                "user_request": "req",
                "fixture_id": "no_such_fixture",
                "policy_tags": [],
                "maximum_steps": 5,
                "expected_outcome": "x",
                "expected_final_state": [],
                "expected_tool_calls": [],
                "forbidden_tool_calls": [],
                "critical_ordering_constraints": [],
            }
        ),
        encoding="utf-8",
    )
    loader = TaskLoader(tmp_path)
    with pytest.raises(ValueError, match="invalid task definition"):
        loader.load("bad_fixture")


def test_unknown_tool_in_expected_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad_tool.json"
    path.write_text(
        json.dumps(
            {
                "task_id": "bad_tool",
                "task_version": "1.0.0",
                "title": "Bad",
                "business_description": "desc",
                "user_request": "req",
                "fixture_id": "eligible_return",
                "policy_tags": [],
                "maximum_steps": 5,
                "expected_outcome": "x",
                "expected_final_state": [],
                "expected_tool_calls": [
                    {"tool_name": "hack_db", "critical_arguments": {}}
                ],
                "forbidden_tool_calls": [],
                "critical_ordering_constraints": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid task definition"):
        TaskLoader(tmp_path).load("bad_tool")
