"""Command-line interface for Agent Reliability Lab.

Checkpoint 0 provides packaging and ``--help`` only. Task execution commands
are planned for later Phase 1 checkpoints.
"""

from __future__ import annotations

import typer

from agent_reliability_lab import __version__

app = typer.Typer(
    name="arl",
    help=(
        "Agent Reliability Lab — deterministic evaluation harness "
        "(Phase 1 in progress; Checkpoint 0 foundation only)."
    ),
    add_completion=False,
    no_args_is_help=True,
)


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


if __name__ == "__main__":
    app()
