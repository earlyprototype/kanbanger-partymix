"""Smoke tests for the partymix port of kanban-doctor.

Two probes:
  1. Clean install + valid 5-column workspace -> doctor exits 0.
  2. Deliberately-corrupted .kanban.json -> doctor exits 1 (FAIL).

Plus in-process unit checks for the token-format and status-field
classification (added 2026-05-18 in response to INTEGRATION_REPORT
entries B3 + B4 — gho_ tokens functionally work, REVIEW is a
required column for the 5-column partymix release).
"""

from __future__ import annotations

import io
import subprocess
import sys
from contextlib import redirect_stdout
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


def _capture_check(fn, *args, **kwargs) -> tuple[str, dict]:
    """Run a single _emit-emitting check and return (stdout, result-counts).

    Each check writes to stdout and increments kanban_doctor._results in
    place. We snapshot + reset the counters so individual unit checks
    don't bleed into each other.
    """
    import kanban_doctor

    saved = dict(kanban_doctor._results)
    for k in kanban_doctor._results:
        kanban_doctor._results[k] = 0
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            fn(*args, **kwargs)
        counts = dict(kanban_doctor._results)
    finally:
        for k, v in saved.items():
            kanban_doctor._results[k] = v
    return buf.getvalue(), counts


def test_token_format_accepts_classic_pat():
    """ghp_ + 36 chars -> PASS (existing behaviour, regression guard)."""
    import kanban_doctor

    out, counts = _capture_check(
        kanban_doctor.check_token_format,
        "ghp_" + "A" * 36,
    )
    assert counts["pass"] == 1, out
    assert counts["fail"] == 0


def test_token_format_warns_on_gho_oauth_token():
    """gho_ (gh-issued OAuth user token) -> WARN, not FAIL.

    B3 fix: gh auth tokens functionally work for Projects V2. Demote
    FAIL to WARN so doctor stops blocking on a working token.
    """
    import kanban_doctor

    # Realistic gho_ token length is variable; just needs the prefix.
    out, counts = _capture_check(
        kanban_doctor.check_token_format,
        "gho_" + "B" * 36,
    )
    assert counts["warn"] == 1, out
    assert counts["fail"] == 0, out
    assert "gh auth login" in out


def test_token_format_still_fails_on_ghs_server_to_server():
    """ghs_ (GitHub App server-to-server token) -> still FAIL.

    Distinct from gho_ — App tokens are not user-personal and should
    not be used for personal-project kanbanger automation.
    """
    import kanban_doctor

    out, counts = _capture_check(
        kanban_doctor.check_token_format,
        "ghs_" + "C" * 36,
    )
    assert counts["fail"] == 1, out


def test_token_format_still_fails_on_fine_grained():
    """github_pat_ (fine-grained PAT) -> still FAIL.

    Fine-grained PATs cannot access Projects V2 GraphQL, so the FAIL
    is load-bearing. Regression guard around the B3 fix.
    """
    import kanban_doctor

    out, counts = _capture_check(
        kanban_doctor.check_token_format,
        "github_pat_" + "D" * 50,
    )
    assert counts["fail"] == 1, out


def test_status_field_requires_review_option():
    """5-column partymix release requires Review.

    B4 fix: a project missing Review should FAIL with Review listed
    in the missing set; the success message should say "all five".
    """
    import kanban_doctor

    project_without_review = {
        "number": 1,
        "title": "TestProj",
        "fields": {
            "nodes": [
                {
                    "name": "Status",
                    "options": [
                        {"name": "Backlog"},
                        {"name": "Todo"},
                        {"name": "InProgress"},
                        {"name": "Done"},
                    ],
                }
            ]
        },
    }
    out, counts = _capture_check(
        kanban_doctor.check_status_field,
        [project_without_review],
    )
    assert counts["fail"] == 1, out
    assert "Review" in out


def test_status_field_passes_on_full_five_column_project():
    """All five options present -> PASS with the 'all five' wording."""
    import kanban_doctor

    project_full = {
        "number": 1,
        "title": "TestProj",
        "fields": {
            "nodes": [
                {
                    "name": "Status",
                    "options": [
                        {"name": "Backlog"},
                        {"name": "Todo"},
                        {"name": "InProgress"},
                        {"name": "Review"},
                        {"name": "Done"},
                    ],
                }
            ]
        },
    }
    out, counts = _capture_check(
        kanban_doctor.check_status_field,
        [project_full],
    )
    assert counts["pass"] == 1, out
    assert "all five" in out


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
