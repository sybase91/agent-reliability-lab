"""Unit tests for presentation formatters without Streamlit."""

from __future__ import annotations

from pathlib import Path

from agent_reliability_lab.agents.failing import SkipVerificationAgent
from agent_reliability_lab.agents.reference import ScriptedReferenceAgent
from agent_reliability_lab.harness.runner import TrialRunner
from agent_reliability_lab.harness.tasks import TaskLoader
from agent_reliability_lab.harness.trace import REDACTED, redact_text_pii
from agent_reliability_lab.presentation import (
    DETERMINISTIC_MODE_CAPTION,
    default_request_for_scenario,
    list_agent_ids,
    list_scenario_ids,
)
from agent_reliability_lab.presentation.formatters import (
    KNOWN_SENSITIVE_FRAGMENTS,
    build_dashboard_view,
    build_failure_insight,
    contains_known_sensitive_fragment,
    format_latency_ms,
    status_label,
)


def test_status_and_latency_formatters() -> None:
    assert status_label(True) == "PASS"
    assert status_label(False) == "FAIL"
    assert format_latency_ms(12) == "12 ms"
    assert "s" in format_latency_ms(1500)


def test_redact_text_pii() -> None:
    text = "Contact alice@example.test or +1-555-0100"
    scrubbed = redact_text_pii(text)
    assert "alice@example.test" not in scrubbed
    assert "+1-555-0100" not in scrubbed
    assert REDACTED in scrubbed


def test_default_request_redacts_pii() -> None:
    request = default_request_for_scenario("eligible_full_return")
    assert not contains_known_sensitive_fragment(request)


def test_list_helpers() -> None:
    assert len(list_scenario_ids()) == 10
    assert "reference" in list_agent_ids()
    assert "skip_verification" in list_agent_ids()
    assert "LLM" in DETERMINISTIC_MODE_CAPTION


def test_build_dashboard_view_pass(tmp_path: Path) -> None:
    task = TaskLoader().load("expired_return_window")
    result = TrialRunner(output_dir=tmp_path).run_task(task, ScriptedReferenceAgent())
    view = build_dashboard_view(task, result)
    assert view.summary.passed
    assert view.summary.status_label == "PASS"
    assert len(view.graders) == 3
    assert view.failure is None
    assert view.artifact_path
    for fragment in KNOWN_SENSITIVE_FRAGMENTS:
        assert fragment not in view.artifact_json
        assert fragment not in view.user_request_display


def test_build_dashboard_view_failure_insight(tmp_path: Path) -> None:
    task = TaskLoader().load("eligible_full_return")
    result = TrialRunner(output_dir=tmp_path).run_task(task, SkipVerificationAgent())
    view = build_dashboard_view(task, result)
    assert not view.summary.passed
    assert view.failure is not None
    assert view.failure.catching_grader
    assert view.failure.why_failed
    insight = build_failure_insight(result)
    assert insight is not None
    for fragment in KNOWN_SENSITIVE_FRAGMENTS:
        assert fragment not in view.failure.why_failed
        assert fragment not in insight.point_of_failure
