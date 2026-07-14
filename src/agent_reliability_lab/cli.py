"""Command-line interface for Agent Reliability Lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from agent_reliability_lab import __version__
from agent_reliability_lab.agents import build_agent
from agent_reliability_lab.harness.runner import TrialRunner
from agent_reliability_lab.harness.tasks import TaskLoader

app = typer.Typer(
    name="arl",
    help=(
        "Agent Reliability Lab — deterministic evaluation harness "
        "(Phase 1 Checkpoints 0–7)."
    ),
    add_completion=False,
    no_args_is_help=True,
)

AgentOption = Annotated[
    str,
    typer.Option(
        "--agent",
        help="Agent to evaluate: reference, skip_verification, approval_bypass, "
        "duplicate_refund.",
    ),
]
OutputDirOption = Annotated[
    Path,
    typer.Option("--output-dir", help="Directory for JSON result artifacts."),
]


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show package version and exit.",
    ),
) -> None:
    """Show help when no subcommand is given; support --version."""
    if version:
        typer.echo(f"agent-reliability-lab {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


@app.command("list-tasks")
def list_tasks() -> None:
    """List available evaluation task IDs in stable order."""
    loader = TaskLoader()
    for task_id in loader.list_task_ids():
        typer.echo(task_id)


@app.command("run-task")
def run_task(
    task_id: Annotated[str, typer.Argument(help="Task ID to evaluate.")],
    agent: AgentOption = "reference",
    output_dir: OutputDirOption = Path("artifacts"),
) -> None:
    """Run one evaluation task and print a summary."""
    runner = TrialRunner(output_dir=output_dir)
    agent_obj = build_agent(agent)
    # Failing demos are wired to specific fixtures/tasks.
    effective_task = task_id
    if agent == "skip_verification":
        effective_task = "eligible_full_return"
    elif agent == "approval_bypass":
        effective_task = "high_value_refund_approval"
    elif agent == "duplicate_refund":
        effective_task = "eligible_full_return"

    result = runner.run(effective_task, agent_obj)
    typer.echo(f"task: {result.task_id}")
    typer.echo(f"agent: {result.agent_name}")
    typer.echo(
        f"overall: {'PASS' if result.passed else 'FAIL'} "
        f"(score={result.overall_score:.2f}, outcome={result.runner_outcome})"
    )
    for grader in result.grader_results:
        status = "pass" if grader.passed else "fail"
        typer.echo(f"  grader {grader.grader_name}: {status} ({grader.explanation})")
    typer.echo(f"steps: {result.step_count}")
    typer.echo(f"artifact: {result.artifact_path}")
    raise typer.Exit(0 if result.passed else 1)


@app.command("run-suite")
def run_suite(
    agent: AgentOption = "reference",
    output_dir: OutputDirOption = Path("artifacts"),
) -> None:
    """Run all tasks (reference) or demo failing agents on their target tasks."""
    runner = TrialRunner(output_dir=output_dir)
    loader = TaskLoader()

    if agent == "reference":
        task_ids = list(loader.list_task_ids())
    elif agent == "skip_verification":
        task_ids = ["eligible_full_return"]
    elif agent == "approval_bypass":
        task_ids = ["high_value_refund_approval"]
    elif agent == "duplicate_refund":
        task_ids = ["eligible_full_return"]
    else:
        typer.echo(f"unknown agent: {agent}", err=True)
        raise typer.Exit(2)

    passed_ids: list[str] = []
    failed_ids: list[str] = []
    for task_id in task_ids:
        # Fresh agent instance per task so scripts reset.
        result = runner.run(task_id, build_agent(agent))
        if result.passed:
            passed_ids.append(task_id)
        else:
            failed_ids.append(task_id)

    total = len(task_ids)
    passed_n = len(passed_ids)
    rate = (passed_n / total) if total else 0.0
    typer.echo(f"passed tasks: {passed_n}")
    typer.echo(f"failed tasks: {len(failed_ids)}")
    typer.echo(f"total tasks: {total}")
    typer.echo(f"pass rate: {rate:.0%}")
    if passed_ids:
        typer.echo("passed: " + ", ".join(passed_ids))
    if failed_ids:
        typer.echo("failed: " + ", ".join(failed_ids))
    typer.echo(f"artifact directory: {output_dir}")
    raise typer.Exit(0 if not failed_ids else 1)


@app.command("show-result")
def show_result(
    result_file: Annotated[
        Path, typer.Argument(help="Path to a JSON result artifact.")
    ],
) -> None:
    """Pretty-print a saved trial result artifact."""
    if not result_file.is_file():
        typer.echo(f"file not found: {result_file}", err=True)
        raise typer.Exit(2)
    payload = json.loads(result_file.read_text(encoding="utf-8"))
    typer.echo(f"task_id: {payload.get('task_id')}")
    typer.echo(f"agent: {payload.get('agent_name')}")
    typer.echo(f"passed: {payload.get('passed')}")
    typer.echo(f"overall_score: {payload.get('overall_score')}")
    typer.echo(f"runner_outcome: {payload.get('runner_outcome')}")
    typer.echo(f"step_count: {payload.get('step_count')}")
    graders = payload.get("grader_results") or []
    for grader in graders:
        typer.echo(
            f"  {grader.get('grader_name')}: "
            f"{'pass' if grader.get('passed') else 'fail'} — "
            f"{grader.get('explanation')}"
        )


if __name__ == "__main__":
    app()
