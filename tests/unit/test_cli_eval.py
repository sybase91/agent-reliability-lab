"""CLI smoke tests for evaluation commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agent_reliability_lab.cli import app

runner = CliRunner()


def test_list_tasks() -> None:
    result = runner.invoke(app, ["list-tasks"])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 10
    assert lines == sorted(lines)


def test_run_suite_reference(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["run-suite", "--agent", "reference", "--output-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stdout
    assert "passed tasks: 10" in result.stdout
    assert "total tasks: 10" in result.stdout
    assert "pass rate: 100%" in result.stdout


def test_run_suite_failing_agent_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run-suite",
            "--agent",
            "skip_verification",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "failed tasks: 1" in result.stdout


def test_run_task_and_show_result(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run-task",
            "expired_return_window",
            "--agent",
            "reference",
            "--output-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "overall: PASS" in result.stdout
    assert "grader final_state: pass" in result.stdout
    artifact_line = [
        line for line in result.stdout.splitlines() if line.startswith("artifact:")
    ][0]
    artifact = Path(artifact_line.split("artifact:", 1)[1].strip())
    show = runner.invoke(app, ["show-result", str(artifact)])
    assert show.exit_code == 0
    assert "passed: True" in show.stdout
