"""Unit tests for Checkpoint 0 package foundation."""

from __future__ import annotations

from typer.testing import CliRunner

from agent_reliability_lab import __version__
from agent_reliability_lab.cli import app


def test_package_import_and_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Agent Reliability Lab" in result.stdout
