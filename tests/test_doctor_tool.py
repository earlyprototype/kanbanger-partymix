"""Tests for the `doctor` MCP tool (issue #23).

The tool shares ONE implementation with the kanban-doctor CLI:
kanban_doctor.run_doctor() produces structured results; the CLI echoes
them progressively, the tool renders them verdict-first via
render_report(). These tests pin:

  * healthy keyed local-only board -> "healthy (local-only)" verdict with
    the ADR 0002 binding triple,
  * unkeyed legacy board -> healthy, key reported absent/legacy,
  * unprovisioned dir -> reported (board = none + WARN), never a crash,
  * half-configured sync -> "problems found" with the failing check named,
  * network checks NEVER run unless network=True (default mirrors the
    CLI's --no-network),
  * tool output == CLI output, line for line (the anti-drift parity gate),
  * the structured core's contract (results/counts/verdict/local-only),
  * run_doctor never prints with echo off, never touches the legacy
    module counters, and never mutates os.environ (safe to embed in a
    long-lived stdio server).
"""

from __future__ import annotations

import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from kanban_io import insert_board_key, mint_board_key

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


def _clear_github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dev shell running pytest may carry real GitHub config; clear it
    so local-only detection is deterministic."""
    for var in ("GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_PROJECT_NUMBER"):
        monkeypatch.delenv(var, raising=False)


def _first_line(text: str) -> str:
    return text.splitlines()[0]


# --- healthy boards (local-only is a HEALTHY verdict, issue #18) ----------


def test_doctor_healthy_keyed_board_local_only(
    registered_tools, kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """Keyed board, no GitHub config anywhere -> healthy (local-only)
    verdict with the full binding triple, minted key verbatim."""
    _clear_github_env(monkeypatch)
    key = mint_board_key()
    (kanban_workspace / "_kanban.md").write_text(
        insert_board_key(VALID_BOARD, key), encoding="utf-8"
    )

    out = registered_tools["doctor"]()

    assert out.startswith("verdict: healthy (local-only)"), out
    resolved = kanban_workspace.resolve()
    assert (
        f"workspace resolved = {resolved} "
        f"-> board = {resolved / '_kanban.md'} -> key = {key}"
    ) in out, out
    assert "local-only mode" in out
    # no FAIL check line ("[FAIL] <name>"); the summary's "[FAIL]: 0" is fine
    assert "[FAIL] " not in out


def test_doctor_unkeyed_board_healthy_key_reported_legacy(
    registered_tools, kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """Legacy unkeyed board (the conftest default) stays a healthy verdict;
    the key is reported absent/legacy, not failed."""
    _clear_github_env(monkeypatch)

    out = registered_tools["doctor"]()

    assert out.startswith("verdict: healthy (local-only)"), out
    assert "key = none (legacy unkeyed board)" in out
    # no FAIL check line ("[FAIL] <name>"); the summary's "[FAIL]: 0" is fine
    assert "[FAIL] " not in out


def test_doctor_unprovisioned_dir_reported_not_crashed(
    registered_tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Pointing the workspace at an empty dir is REPORTED (board = none in
    the triple, WARN on the board check), never a crash / error envelope."""
    _clear_github_env(monkeypatch)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(empty))

    out = registered_tools["doctor"]()

    assert out.startswith("verdict: healthy (local-only)"), out
    assert "board = none -> key = none" in out
    assert "[WARN] _kanban.md in workspace: not at" in out


# --- problems must surface -------------------------------------------------


@pytest.mark.parametrize(
    "var,value",
    [
        ("GITHUB_REPO", "owner/repo"),
        ("GITHUB_TOKEN", "ghp_" + "A" * 36),
    ],
)
def test_doctor_half_configured_sync_surfaces_problem(
    registered_tools,
    kanban_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    var: str,
    value: str,
):
    """One GitHub var without the other is a real defect (issue #18 rule):
    the verdict must lead with 'problems found' and name the FAIL."""
    _clear_github_env(monkeypatch)
    monkeypatch.setenv(var, value)

    out = registered_tools["doctor"]()

    assert out.startswith("verdict: problems found"), out
    missing = "GITHUB_TOKEN" if var == "GITHUB_REPO" else "GITHUB_REPO"
    assert f"[FAIL] {missing}: not set" in out
    assert "local-only mode" not in out


# --- network gating ---------------------------------------------------------


def _trap_requests(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    """Replace the requests module with a booby trap: any .post() raises.

    The doctor tool catches exceptions into an error envelope, so a
    triggered trap shows up as a non-verdict return (network=False case)
    or a 'connection error' FAIL line (network=True case, because
    check_token_works wraps the call in its own try/except).
    """

    def _boom(*args, **kwargs):
        raise AssertionError(message)

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=_boom))


def test_doctor_default_makes_no_network_calls(
    registered_tools, kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """Default network=False mirrors --no-network: even with full GitHub
    config the network checks report skipped and requests is never used."""
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    _trap_requests(monkeypatch, "network attempted with network=False")

    out = registered_tools["doctor"]()

    assert out.startswith("verdict: healthy"), out
    assert "local-only" not in _first_line(out)
    assert "skipped (--no-network)" in out
    assert "network attempted" not in out


def test_doctor_network_param_runs_network_checks(
    registered_tools, kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """network=True actually exercises the network path (positive control
    for the trap above: the trapped requests.post IS reached)."""
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    _trap_requests(monkeypatch, "network attempted")

    out = registered_tools["doctor"](network=True)

    assert "connection error: network attempted" in out, out
    assert "skipped (--no-network)" not in out


# --- one implementation, no drift -------------------------------------------


def test_doctor_tool_output_matches_cli_line_for_line(
    registered_tools, kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """The anti-drift gate: the tool's body (after the verdict line and its
    blank separator) must equal the CLI's stdout, line for line."""
    _clear_github_env(monkeypatch)

    out = registered_tools["doctor"]()
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "kanban_doctor",
            "--workspace",
            str(kanban_workspace),
            "--no-network",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert cli.returncode == 0, f"STDOUT:\n{cli.stdout}\nSTDERR:\n{cli.stderr}"
    assert out.splitlines()[2:] == cli.stdout.splitlines(), (
        f"tool body diverged from CLI output.\nTOOL:\n{out}\nCLI:\n{cli.stdout}"
    )


# --- structured core contract ------------------------------------------------


def test_run_doctor_returns_structured_results(
    kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """run_doctor's DoctorReport: section-attributed results, counts that
    match them, the binding triple, and local-only awareness."""
    import kanban_doctor

    _clear_github_env(monkeypatch)
    report = kanban_doctor.run_doctor(kanban_workspace, no_network=True)

    assert report.local_only is True
    assert report.verdict == "healthy (local-only)"
    assert report.binding is not None
    assert report.binding["board_path"] == str(kanban_workspace / "_kanban.md")
    assert report.binding["board_key"] is None  # conftest board is unkeyed
    assert report.results, "no structured results collected"
    assert {r.status for r in report.results} <= {"PASS", "WARN", "FAIL", "SKIP"}
    for status in ("pass", "warn", "fail", "skip"):
        assert report.counts[status] == sum(
            1 for r in report.results if r.status.lower() == status
        )
    assert report.counts["fail"] == 0
    sections = {r.section for r in report.results}
    assert "Environment" in sections
    assert "Workspace" in sections
    assert "Install integrity (partymix additions)" in sections


def test_run_doctor_echo_off_prints_nothing(
    kanban_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
):
    """echo=False must be silent: in the MCP server, stdout is the stdio
    transport and any stray print corrupts protocol framing."""
    import kanban_doctor

    _clear_github_env(monkeypatch)
    kanban_doctor.run_doctor(kanban_workspace, no_network=True)

    assert capsys.readouterr().out == ""


def test_run_doctor_leaves_legacy_counters_untouched(
    kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """run_doctor collects into its own context; the module-level _results
    dict (kept for direct-call unit tests) must not grow inside a
    long-lived server process."""
    import kanban_doctor

    _clear_github_env(monkeypatch)
    before = dict(kanban_doctor._results)
    kanban_doctor.run_doctor(kanban_workspace, no_network=True)

    assert dict(kanban_doctor._results) == before


def test_run_doctor_does_not_mutate_process_env(
    kanban_workspace: Path, monkeypatch: pytest.MonkeyPatch
):
    """PR #24 review: run_doctor executes inside the long-lived MCP server
    process, so reading a workspace .env must never write os.environ --
    one run would otherwise leak that workspace's config into every later
    tool call and sync_to_github subprocess. The report must still
    REFLECT the .env values: they reach the checks via the per-run
    effective env (.env overrides shell), and the source line attributes
    them to 'workspace .env'."""
    import kanban_doctor

    _clear_github_env(monkeypatch)
    (kanban_workspace / ".env").write_text(
        "GITHUB_REPO=owner/envrepo\nDOCTOR_ENV_SENTINEL=leaked\n",
        encoding="utf-8",
    )
    before = dict(os.environ)

    report = kanban_doctor.run_doctor(kanban_workspace, no_network=True)

    assert "DOCTOR_ENV_SENTINEL" not in os.environ, ".env leaked into os.environ"
    assert dict(os.environ) == before, "run_doctor mutated os.environ"
    body = "\n".join(report.body_lines)
    assert "GITHUB_REPO: workspace .env ('owner/envrepo')" in body
    assert "[PASS] GITHUB_REPO: owner/envrepo" in body
    # .env supplies the repo but no token: half-configured sync must keep
    # FAILing (local-only must not engage just because os.environ is bare).
    assert report.local_only is False
    assert "[FAIL] GITHUB_TOKEN: not set" in body
