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
import json
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


def test_status_field_requires_review_option(monkeypatch: pytest.MonkeyPatch):
    """5-column partymix release requires Review.

    B4 fix: a project missing Review should FAIL with Review listed
    in the missing set; the success message should say "all five".
    """
    import kanban_doctor

    monkeypatch.delenv("GITHUB_PROJECT_NUMBER", raising=False)

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


def test_status_field_passes_on_full_five_column_project(monkeypatch: pytest.MonkeyPatch):
    """All five options present -> PASS with the 'all five' wording."""
    import kanban_doctor

    monkeypatch.delenv("GITHUB_PROJECT_NUMBER", raising=False)

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


# --- issue #22: dist rename (kanbanger-partymix -> kanbanger) --------------
# The install-collision check must treat the canonical dist as healthy,
# flag pre-rename installs as stale/legacy with a pip uninstall
# remediation, and keep warning on true multi-dist collisions.


def _fake_dist_versions(monkeypatch: pytest.MonkeyPatch, installed: dict) -> None:
    """Patch importlib.metadata.version to a fixed installed-dists mapping."""
    import importlib.metadata as md

    def fake_version(name: str) -> str:
        try:
            return installed[name]
        except KeyError:
            raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", fake_version)


def test_collision_passes_on_single_canonical_dist(monkeypatch: pytest.MonkeyPatch):
    """Only the renamed `kanbanger` dist installed -> PASS, no collision."""
    import kanban_doctor

    _fake_dist_versions(monkeypatch, {"kanbanger": "3.0.0"})
    out, counts = _capture_check(kanban_doctor.check_install_collision)
    assert counts["pass"] == 1, out
    assert "only kanbanger==3.0.0 installed" in out


def test_collision_flags_lone_legacy_partymix_dist(monkeypatch: pytest.MonkeyPatch):
    """A machine still carrying the pre-rename dist is a stale install:
    WARN (even with no other dist present) and remediation says
    `pip uninstall kanbanger-partymix`."""
    import kanban_doctor

    _fake_dist_versions(monkeypatch, {"kanbanger-partymix": "3.0.0"})
    out, counts = _capture_check(kanban_doctor.check_install_collision)
    assert counts["warn"] == 1, out
    assert counts["pass"] == 0, out
    assert "legacy dist kanbanger-partymix==3.0.0" in out
    assert "pip uninstall kanbanger-partymix" in out
    assert "pipx install kanbanger" in out


def test_collision_flags_lone_legacy_v2_dist(monkeypatch: pytest.MonkeyPatch):
    """The v2-era kanban-project-sync dist gets the same stale-install WARN."""
    import kanban_doctor

    _fake_dist_versions(monkeypatch, {"kanban-project-sync": "2.1.0"})
    out, counts = _capture_check(kanban_doctor.check_install_collision)
    assert counts["warn"] == 1, out
    assert "legacy dist kanban-project-sync==2.1.0" in out
    assert "pip uninstall kanban-project-sync" in out


def test_collision_warns_on_canonical_plus_legacy(monkeypatch: pytest.MonkeyPatch):
    """Renamed dist + pre-rename dist both installed -> collision WARN naming
    both, with the uninstall pointed at the legacy dist only."""
    import kanban_doctor

    _fake_dist_versions(
        monkeypatch, {"kanbanger": "3.0.0", "kanbanger-partymix": "3.0.0"}
    )
    out, counts = _capture_check(kanban_doctor.check_install_collision)
    assert counts["warn"] == 1, out
    assert "multiple kanbanger dists installed" in out
    assert "kanbanger==3.0.0" in out
    assert "kanbanger-partymix==3.0.0" in out
    assert "pip uninstall kanbanger-partymix" in out
    assert "pip uninstall kanbanger`" not in out  # never uninstall the canonical dist


def test_version_consistency_prefers_canonical_dist(monkeypatch: pytest.MonkeyPatch):
    """With old and new dists both present, the version-consistency check
    reads the canonical `kanbanger` dist (repointed for issue #22)."""
    import kanban_doctor

    _fake_dist_versions(
        monkeypatch, {"kanbanger": "3.0.0", "kanbanger-partymix": "2.9.0"}
    )
    out, counts = _capture_check(kanban_doctor.check_version_consistency, "3.0.0")
    assert counts["pass"] == 1, out
    assert "kanbanger dist==3.0.0" in out


# --- ADR 0002 binding triple (issue #15 step 5) ---------------------------
# The doctor header must render `workspace resolved = X -> board = Y ->
# key = Z` from one resolve_binding() call. KANBANGER_WORKSPACE is pinned
# to the temp dir in each probe so resolution is deterministic (no walk-up
# past tmp_path into the runner's filesystem).


def _set_doctor_env(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(workspace))
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)


def test_doctor_prints_binding_triple_for_keyed_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Keyed board: the triple shows resolved workspace, board path and the
    minted key verbatim."""
    from kanban_io import insert_board_key, mint_board_key

    key = mint_board_key()
    (tmp_path / "_kanban.md").write_text(
        insert_board_key(VALID_BOARD, key), encoding="utf-8"
    )
    _set_doctor_env(monkeypatch, tmp_path)
    result = _run_doctor(tmp_path)
    assert result.returncode == 0, result.stdout
    resolved = tmp_path.resolve()
    expected = (
        f"workspace resolved = {resolved} "
        f"-> board = {resolved / '_kanban.md'} -> key = {key}"
    )
    assert expected in result.stdout, (
        f"binding triple missing/wrong.\nExpected: {expected}\n"
        f"STDOUT:\n{result.stdout}"
    )


def test_doctor_prints_binding_triple_for_unkeyed_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Legacy unkeyed board: key rendered as absent/legacy, and the doctor
    must NOT fail over it (keyless boards are valid -- exit stays 0)."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    _set_doctor_env(monkeypatch, tmp_path)
    result = _run_doctor(tmp_path)
    assert result.returncode == 0, result.stdout
    resolved = tmp_path.resolve()
    expected = (
        f"workspace resolved = {resolved} "
        f"-> board = {resolved / '_kanban.md'} "
        f"-> key = none (legacy unkeyed board)"
    )
    assert expected in result.stdout, (
        f"binding triple missing/wrong.\nExpected: {expected}\n"
        f"STDOUT:\n{result.stdout}"
    )


def test_doctor_prints_binding_triple_when_no_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Unprovisioned dir: board and key both none, no crash. Missing board
    stays a WARN under existing policy, so exit is still 0."""
    _set_doctor_env(monkeypatch, tmp_path)
    result = _run_doctor(tmp_path)
    assert result.returncode == 0, result.stdout
    expected = (
        f"workspace resolved = {tmp_path.resolve()} -> board = none -> key = none"
    )
    assert expected in result.stdout, (
        f"binding triple missing/wrong.\nExpected: {expected}\n"
        f"STDOUT:\n{result.stdout}"
    )


# --- issue #18: local-only mode + config-source transparency --------------
# The doctor subprocess inherits this process's environment, so each probe
# below pins KANBANGER_WORKSPACE to the temp dir and explicitly clears the
# GitHub vars (the dev shell running pytest may have them set).


def _clear_github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_PROJECT_NUMBER"):
        monkeypatch.delenv(var, raising=False)


def test_doctor_local_only_unconfigured_workspace_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Issue #18 item 1: healthy board, no GitHub config anywhere (shell env,
    .env, .mcp.json) -> local-only mode: exit 0 with an explicit mode line,
    and the credential/repo not-set checks SKIP instead of FAIL."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    result = _run_doctor(tmp_path)
    assert result.returncode == 0, (
        f"doctor exit {result.returncode} on healthy local-only workspace.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "local-only mode" in result.stdout
    assert "GitHub sync not configured" in result.stdout
    assert "GITHUB_TOKEN: not set" in result.stdout


@pytest.mark.parametrize(
    "var,value",
    [
        ("GITHUB_REPO", "owner/repo"),
        ("GITHUB_TOKEN", "ghp_" + "A" * 36),
    ],
)
def test_doctor_half_configured_sync_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, var: str, value: str
):
    """Issue #18 item 1 guard: one GitHub var set without the other is a
    half-configured sync -- a real problem, so still FAIL / exit 1."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    monkeypatch.setenv(var, value)
    result = _run_doctor(tmp_path)
    assert result.returncode == 1, (
        f"expected exit 1 for half-configured sync ({var} only), got "
        f"{result.returncode}.\nSTDOUT:\n{result.stdout}"
    )
    assert "local-only mode" not in result.stdout


def test_doctor_fully_configured_unchanged_and_attributes_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Issue #18 item 1 guard + item 2 minimum bar: with both vars in the
    shell env the doctor behaves as before (exit 0, no local-only line)
    and states where each GitHub value came from."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)
    result = _run_doctor(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "local-only mode" not in result.stdout
    assert "GITHUB_REPO: shell env ('owner/repo')" in result.stdout
    assert "GITHUB_TOKEN: shell env" in result.stdout
    # the raw token value must never appear (only the masked ghp_...AAAA form)
    assert ("ghp_" + "A" * 36) not in result.stdout


def test_doctor_notes_ambient_vs_mcp_json_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Issue #18 item 2: ambient env supplies GITHUB_REPO while the
    project's .mcp.json slot is an empty `${GITHUB_REPO:-}` placeholder
    (the shape kanbanger.provision writes) -> explicit divergence note."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "kanbanger": {
                        "command": "kanbanger-mcp",
                        "env": {
                            "KANBANGER_WORKSPACE": "${KANBANGER_WORKSPACE:-"
                            + str(tmp_path)
                            + "}",
                            "GITHUB_TOKEN": "${GITHUB_TOKEN:-}",
                            "GITHUB_REPO": "${GITHUB_REPO:-}",
                            "GITHUB_PROJECT_NUMBER": "${GITHUB_PROJECT_NUMBER:-}",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("GITHUB_REPO", "owner/leaked")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)
    result = _run_doctor(tmp_path)
    assert result.returncode == 0, result.stdout
    assert (
        "ambient env supplies GITHUB_REPO but this project's .mcp.json "
        "does not -- a launched server may see different config"
    ) in result.stdout, f"divergence note missing.\nSTDOUT:\n{result.stdout}"


def test_doctor_mcp_pinned_default_disables_local_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A non-empty .mcp.json default counts as sync config: local-only must
    NOT trigger (missing token stays FAIL -> exit 1) and the project-supplies
    direction of the divergence note appears."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "kanbanger": {
                        "command": "kanbanger-mcp",
                        "env": {
                            "GITHUB_TOKEN": "${GITHUB_TOKEN:-}",
                            "GITHUB_REPO": "${GITHUB_REPO:-owner/pinned}",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    result = _run_doctor(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "local-only mode" not in result.stdout
    assert (
        "this project's .mcp.json supplies GITHUB_REPO but the ambient env "
        "does not" in result.stdout
    ), f"project-supplies note missing.\nSTDOUT:\n{result.stdout}"


def test_doctor_env_file_supplying_repo_counts_as_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A workspace .env supplying GITHUB_REPO disables local-only (so the
    missing token stays FAIL) and the source line attributes the value to
    the .env, not the shell."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    (tmp_path / ".env").write_text("GITHUB_REPO=owner/envrepo\n", encoding="utf-8")
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    result = _run_doctor(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "local-only mode" not in result.stdout
    assert "GITHUB_REPO: workspace .env ('owner/envrepo')" in result.stdout


def test_read_mcp_project_env_parses_placeholders(tmp_path: Path):
    """`${VAR:-default}` -> default, `${VAR}` -> '', plain string -> itself."""
    import kanban_doctor

    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "kanbanger": {
                        "env": {
                            "GITHUB_REPO": "${GITHUB_REPO:-owner/pinned}",
                            "GITHUB_TOKEN": "${GITHUB_TOKEN:-}",
                            "GITHUB_PROJECT_NUMBER": "${GITHUB_PROJECT_NUMBER}",
                            "KANBANGER_WORKSPACE": "C:/literal/path",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    exists, literals = kanban_doctor.read_mcp_project_env(tmp_path)
    assert exists is True
    assert literals == {
        "GITHUB_REPO": "owner/pinned",
        "GITHUB_TOKEN": "",
        "GITHUB_PROJECT_NUMBER": "",
        "KANBANGER_WORKSPACE": "C:/literal/path",
    }


def test_read_mcp_project_env_handles_missing_and_unparseable(tmp_path: Path):
    """No .mcp.json -> (False, {}); invalid JSON -> (True, None)."""
    import kanban_doctor

    assert kanban_doctor.read_mcp_project_env(tmp_path) == (False, {})
    (tmp_path / ".mcp.json").write_text("{ not json", encoding="utf-8")
    assert kanban_doctor.read_mcp_project_env(tmp_path) == (True, None)


def test_doctor_flags_corrupt_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A `.kanban.json` that isn't valid JSON should produce a FAIL,
    causing the doctor to exit 1."""
    (tmp_path / "_kanban.md").write_text(VALID_BOARD, encoding="utf-8")
    (tmp_path / ".kanban.json").write_text("{ this is not valid json", encoding="utf-8")

    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "A" * 36)
    result = _run_doctor(tmp_path)
    assert result.returncode == 1, (
        f"expected exit 1 (FAIL on corrupt state), got {result.returncode}.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )
    assert "not valid JSON" in result.stdout, (
        f"Expected doctor to mention 'not valid JSON', got:\n{result.stdout}"
    )
