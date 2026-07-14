"""Validate CI workflow triggers for checkpoint branches."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_runs_on_all_branch_pushes_and_pull_requests() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "on:" in text
    assert "pull_request:" in text
    assert "push:" in text
    # Must not restrict pushes to only main / phase-1-retail-harness.
    assert "branches: [main, phase-1-retail-harness]" not in text
    assert 'python-version: ["3.12"]' in text or "python-version: ['3.12']" in text
    assert "ruff check" in text
    assert "mypy src" in text
    assert "pytest -q" in text
