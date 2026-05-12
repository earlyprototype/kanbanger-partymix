"""Smoke tests for the partymix port of kanban-doctor.

Two probes:
  1. Clean install + valid 5-column workspace -> doctor exits 0.
  2. Deliberately-corrupted .kanban.json -> doctor exits 1 (FAIL).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


VALID_BOARD = (
    "# Test\n"
    "\n"
    "## BACKLOG\n"
    "\n"
    "## TODO\n"
    "\n"
    "## DOING\n"
    "\n"
    "## REVIEW\n"
    "\n"
    "## DONE\n"
)


def _run_doctor(workspace: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "kanban_doctor",
            "--workspace",
            str(workspace),
            "--no-network",
        ],
        capture_output=True,
        text=True,
    )


def test_doctor_module_importable():
    """Doctor module imports without side effects that break tests."""
    import kanban_doctor

    assert callable(kanban_doctor.main)


def test_doctor_passes_on_clean_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A workspace with a valid 5-column board and a real-shaped token should
    pass preflight (exit 0). WARN is permitted (e.g. no .env, no Projects V2)."""
    board = tmp_path / "_kanban.md"
    board.write_text(VALID_BOARD, encoding="utf-8")

    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)
    monkeypatch.setenv("MCP_USE_ANONYMIZED_TELEMETRY", "false")

    result = _run_doctor(tmp_path)
    assert result.returncode == 0, (
        f"doctor exit {result.returncode} on clean workspace.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
    assert "Python version" in result.stdout
    assert "_kanban.md in workspace" in result.stdout
    assert "Install collision detector" in result.stdout


def test_doctor_flags_corrupt_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A `.kanban.json` that isn't valid JSON should produce a FAIL,
    causing the doctor to exit 1."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    (tmp_path / ".kanban.json").write_text("{ this is not valid json", encoding="utf-8")

    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)
    monkeypatch.setenv("MCP_USE_ANONYMIZED_TELEMETRY", "false")

    result = _run_doctor(tmp_path)
    assert result.returncode == 1, (
        f"expected exit 1 (FAIL on corrupt state), got {result.returncode}.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
    assert "not valid JSON" in result.stdout, (
        f"Expected doctor to mention 'not valid JSON', got:\n{result.stdout}"
    )
