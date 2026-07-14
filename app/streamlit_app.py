"""Streamlit dashboard for Agent Reliability Lab.

Rendering only — evaluation logic lives in the presentation and harness layers.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from agent_reliability_lab.presentation import (
    DETERMINISTIC_MODE_CAPTION,
    default_request_for_scenario,
    list_agent_ids,
    list_scenario_ids,
    run_dashboard_evaluation,
)
from agent_reliability_lab.presentation.formatters import format_latency_ms
from agent_reliability_lab.presentation.view_models import DashboardViewModel

PROJECT_PURPOSE = (
    "Evaluate whether agents use tools correctly, follow policy, and leave "
    "retail data in the right final state."
)


def _ensure_session() -> None:
    scenarios = list_scenario_ids()
    if "scenario_id" not in st.session_state:
        st.session_state.scenario_id = scenarios[0]
    if "agent_name" not in st.session_state:
        st.session_state.agent_name = "reference"
    if "request_area" not in st.session_state:
        st.session_state.request_area = default_request_for_scenario(
            st.session_state.scenario_id
        )
    if "view_model" not in st.session_state:
        st.session_state.view_model = None


def _sync_request_for_scenario(scenario_id: str) -> None:
    if st.session_state.get("_bound_scenario") != scenario_id:
        st.session_state.request_area = default_request_for_scenario(scenario_id)
        st.session_state._bound_scenario = scenario_id


def _render_header() -> None:
    st.title("Agent Reliability Lab")
    st.write(PROJECT_PURPOSE)
    st.caption(DETERMINISTIC_MODE_CAPTION)


def _render_controls() -> None:
    scenarios = list_scenario_ids()
    agents = list_agent_ids()
    with st.sidebar:
        st.header("Evaluation controls")
        scenario = st.selectbox(
            "Scenario",
            options=scenarios,
            index=scenarios.index(st.session_state.scenario_id),
            help="Each scenario maps to a fixed fixture and expected outcome.",
        )
        st.session_state.scenario_id = scenario
        _sync_request_for_scenario(scenario)

        agent = st.selectbox(
            "Agent",
            options=agents,
            index=agents.index(st.session_state.agent_name),
            help="Reference should pass; failing agents demonstrate grader catches.",
        )
        st.session_state.agent_name = agent

        st.text_area(
            "Customer request",
            key="request_area",
            height=140,
            help=(
                "Recorded on the run. Deterministic agents do not semantically "
                "interpret free-form text via an LLM."
            ),
        )

        if st.button("Run evaluation", type="primary"):
            with st.spinner("Running evaluation..."):
                _task, _result, view = run_dashboard_evaluation(
                    task_id=st.session_state.scenario_id,
                    agent_name=st.session_state.agent_name,
                    user_request=st.session_state.request_area,
                    output_dir="artifacts",
                )
            st.session_state.view_model = view


def _render_summary(view: DashboardViewModel) -> None:
    summary = view.summary
    color = "#0B7A3B" if summary.passed else "#B42318"
    st.markdown(
        f"### Overall result: "
        f"<span style='color:{color};font-weight:700'>{summary.status_label}</span>",
        unsafe_allow_html=True,
    )
    cols = st.columns(5)
    cols[0].metric("Task", summary.task_id)
    cols[1].metric("Agent", summary.agent_name)
    cols[2].metric("Steps", str(summary.step_count))
    cols[3].metric("Latency", format_latency_ms(summary.total_latency_ms))
    cols[4].metric(
        "Graders",
        f"{summary.grader_pass_count}/{summary.grader_total}",
    )
    st.caption(
        f"Runner outcome: {summary.runner_outcome} · overall score "
        f"{summary.overall_score:.2f}"
    )


def _render_graders(view: DashboardViewModel) -> None:
    st.subheader("Grader results")
    st.caption(
        "A task passes only when every critical grader passes. "
        "Score is for display and cannot average away a critical failure."
    )
    for grader in view.graders:
        badge = "PASS" if grader.passed else "FAIL"
        with st.container(border=True):
            st.markdown(
                f"**{grader.display_name}** — {badge} (score {grader.score:.2f})"
            )
            st.write(grader.explanation)
            st.caption(grader.evidence_summary)
            with st.expander("Evidence details"):
                st.code(str(grader.evidence))


def _render_trace(view: DashboardViewModel) -> None:
    st.subheader("Agent execution")
    st.caption(
        "Ordered decisions from the harness trace. Arguments are redacted; "
        "business denials are distinct from system failures."
    )
    for step in view.steps:
        title = (
            f"Step {step.step_number}: {step.tool_name or step.action_type} "
            f"[{step.status}]"
        )
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.write(step.decision_reason)
            meta = st.columns(3)
            meta[0].write(f"Result code: `{step.tool_result_code or '—'}`")
            meta[1].write(f"Latency: {format_latency_ms(step.latency_ms)}")
            meta[2].write(f"Action: `{step.action_type}`")
            st.write(step.result_summary)
            with st.expander("Redacted arguments"):
                st.code(step.arguments_display, language="json")
            with st.expander("Relevant state changes"):
                st.text(step.state_changes_display)
            if step.error_display:
                st.warning(step.error_display)


def _render_state(view: DashboardViewModel) -> None:
    st.subheader("State comparison")
    st.caption(
        "Expected assertions versus targeted actual state. "
        "This is not a full database dump."
    )
    left, right = st.columns(2)
    with left:
        st.markdown("**Expected final state**")
        st.code(view.state.expected_display, language="json")
    with right:
        st.markdown("**Actual relevant final state**")
        st.code(view.state.actual_display, language="json")
    st.markdown("**Concise diff**")
    st.text(view.state.diff_display)


def _render_failure(view: DashboardViewModel) -> None:
    if view.failure is None:
        return
    st.subheader("Failure analysis")
    failure = view.failure
    st.error(f"Point of failure: {failure.point_of_failure}")
    st.write(f"**Caught by:** {failure.catching_grader}")
    st.write(f"**Why:** {failure.why_failed}")
    st.write(f"**State consequence:** {failure.state_consequence}")


def _render_artifact(view: DashboardViewModel) -> None:
    st.subheader("Artifact")
    path = view.artifact_path or "artifacts/<result>.json"
    st.write(f"Result path: `{path}`")
    filename = Path(path).name if view.artifact_path else "result.json"
    st.download_button(
        label="Download JSON result",
        data=view.artifact_json.encode("utf-8"),
        file_name=filename,
        mime="application/json",
        key="download_result_json",
    )


def main() -> None:
    st.set_page_config(
        page_title="Agent Reliability Lab",
        layout="wide",
    )
    _ensure_session()
    _render_header()
    _render_controls()

    view: DashboardViewModel | None = st.session_state.view_model
    if view is None:
        st.info("Select a scenario and agent, then run an evaluation to see results.")
        return

    _render_summary(view)
    _render_graders(view)
    _render_trace(view)
    _render_state(view)
    _render_failure(view)
    _render_artifact(view)


main()
