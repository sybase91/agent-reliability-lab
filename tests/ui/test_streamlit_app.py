"""Headless Streamlit AppTest coverage for the evaluation dashboard."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent_reliability_lab.presentation import DETERMINISTIC_MODE_CAPTION
from agent_reliability_lab.presentation.formatters import KNOWN_SENSITIVE_FRAGMENTS

APP_PATH = Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py"


def _collect_text(at: AppTest) -> str:
    chunks: list[str] = []
    for attr in ("title", "markdown", "text", "caption", "info", "error", "warning"):
        widgets = getattr(at, attr, None)
        if widgets is None:
            continue
        for widget in widgets:
            value = getattr(widget, "value", None)
            if value is not None:
                chunks.append(str(value))
            body = getattr(widget, "body", None)
            if body is not None:
                chunks.append(str(body))
    for metric in at.metric:
        chunks.append(str(metric.label))
        chunks.append(str(metric.value))
    for code in at.code:
        chunks.append(str(code.value))
    return "\n".join(chunks)


@pytest.fixture
def app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    assert not at.exception
    return at


def test_app_loads_without_exception(app: AppTest) -> None:
    assert not app.exception


def test_title_and_project_explanation_render(app: AppTest) -> None:
    text = _collect_text(app)
    assert "Agent Reliability Lab" in text
    assert "tools correctly" in text or "final state" in text


def test_deterministic_mode_disclosure_renders(app: AppTest) -> None:
    text = _collect_text(app)
    assert "Deterministic MVP mode" in text
    assert DETERMINISTIC_MODE_CAPTION[:40] in text


def test_exactly_ten_scenarios_available(app: AppTest) -> None:
    scenario = app.sidebar.selectbox[0]
    assert len(scenario.options) == 10


def test_reference_and_failing_agents_available(app: AppTest) -> None:
    agent = app.sidebar.selectbox[1]
    options = set(agent.options)
    assert "reference" in options
    assert "skip_verification" in options
    assert "approval_bypass" in options
    assert "duplicate_refund" in options


def test_selecting_scenario_updates_request(app: AppTest) -> None:
    scenario = app.sidebar.selectbox[0]
    scenario.set_value("high_value_refund_approval")
    app.run()
    assert not app.exception
    request = app.sidebar.text_area[0].value
    assert "hv_ord_1001" in request or "55000" in request


def test_running_reference_task_renders_pass(app: AppTest) -> None:
    app.sidebar.selectbox[0].set_value("expired_return_window")
    app.run()
    app.sidebar.selectbox[1].set_value("reference")
    app.run()
    app.sidebar.button[0].click()
    app.run(timeout=60)
    assert not app.exception
    text = _collect_text(app)
    assert "PASS" in text
    assert "Overall result" in text or "expired_return_window" in text


def test_grader_results_and_trace_render(app: AppTest) -> None:
    app.sidebar.selectbox[0].set_value("expired_return_window")
    app.run()
    app.sidebar.button[0].click()
    app.run(timeout=60)
    text = _collect_text(app)
    assert "Final State" in text
    assert "Tool Calls" in text
    assert "Policy Compliance" in text
    assert "Agent execution" in text or "Step 1" in text


def test_failing_agent_renders_fail_and_explanation(app: AppTest) -> None:
    app.sidebar.selectbox[0].set_value("eligible_full_return")
    app.run()
    app.sidebar.selectbox[1].set_value("skip_verification")
    app.run()
    app.sidebar.button[0].click()
    app.run(timeout=60)
    assert not app.exception
    text = _collect_text(app)
    assert "FAIL" in text
    assert "Failure analysis" in text or "Point of failure" in text
    assert "Caught by" in text or "Why" in text or "verification" in text.lower()


def test_no_sensitive_fixture_values_rendered(app: AppTest) -> None:
    app.sidebar.selectbox[0].set_value("eligible_full_return")
    app.run()
    app.sidebar.button[0].click()
    app.run(timeout=60)
    text = _collect_text(app)
    for fragment in KNOWN_SENSITIVE_FRAGMENTS:
        assert fragment not in text


def test_download_result_section_available(app: AppTest) -> None:
    app.sidebar.selectbox[0].set_value("expired_return_window")
    app.run()
    app.sidebar.button[0].click()
    app.run(timeout=60)
    text = _collect_text(app)
    assert "Artifact" in text or "Result path" in text
    assert len(app.download_button) >= 1
    assert "Download JSON" in app.download_button[0].label
