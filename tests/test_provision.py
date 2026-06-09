"""Tests for kanbanger.provision and the `setup_project` MCP tool.

Covers the issue #15 step 3 provisioning contract:
  - board scaffolded with the canonical 5-column schema when absent,
  - board NEVER clobbered when already present,
  - the agent touchpoint (CLAUDE.md) added idempotently (re-run is a no-op),
  - GitHub-sync slots written as EMPTY placeholders only (no secrets),
  - the `setup_project` MCP tool drives the same shared code,
  - the `kanbanger init` CLI parity entry point.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kanban_io import extract_board_key, format_board_key_marker
from kanbanger import provision
from kanbanger.provision import (
    CLAUDE_MD_END,
    CLAUDE_MD_START,
    build_kanban_board,
    provision_project,
)

CANONICAL_COLUMNS = ["BACKLOG", "TODO", "DOING", "REVIEW", "DONE"]


# --- helpers ---------------------------------------------------------------


def _columns_in(board_text: str) -> list[str]:
    return [
        line.strip()[3:].strip()
        for line in board_text.splitlines()
        if line.strip().startswith("## ")
    ]


# --- board scaffold --------------------------------------------------------


def test_build_kanban_board_has_canonical_five_columns():
    board = build_kanban_board("Demo")
    assert _columns_in(board) == CANONICAL_COLUMNS
    assert board.startswith("# Demo Kanban")


def test_board_scaffolded_when_absent(tmp_path: Path):
    result = provision_project(tmp_path)

    board = tmp_path / "_kanban.md"
    assert board.exists()
    assert _columns_in(board.read_text(encoding="utf-8")) == CANONICAL_COLUMNS
    # The board uses the directory name as the project title.
    assert board.read_text(encoding="utf-8").startswith(f"# {tmp_path.name} Kanban")
    assert any("_kanban.md" in note for note in result.created)


def test_board_not_clobbered_when_present(tmp_path: Path):
    """Existing board content survives provisioning.

    Step-4 amendment (ADR 0002): an existing board LACKING a board key
    receives exactly ONE additive marker comment line — the single
    sanctioned modification. Every original byte is preserved: removing
    that one line reproduces the original exactly.
    """
    board = tmp_path / "_kanban.md"
    sentinel = "# Pre-existing Board\n\n## BACKLOG\n*   [ ] do not delete me\n"
    board.write_text(sentinel, encoding="utf-8")

    result = provision_project(tmp_path)

    after = board.read_text(encoding="utf-8")
    key = extract_board_key(after)
    assert key is not None  # the one sanctioned addition happened
    marker_line = format_board_key_marker(key) + "\n"
    # Removing the single added marker line reproduces the original
    # byte-for-byte — nothing else was touched.
    assert after.replace(marker_line, "", 1) == sentinel
    assert after.count("kanbanger:board-id") == 1
    # Reported as updated ("minted board key"), not created.
    assert any(
        "_kanban.md" in note and "minted board key" in note
        for note in result.updated
    )
    assert all("_kanban.md" not in note for note in result.created)


# --- board key minting (ADR 0002, issue #15 step 4) -------------------------


def test_new_board_scaffolded_with_minted_key(tmp_path: Path):
    """A fresh scaffold carries a uuid4-hex board key under the title."""
    result = provision_project(tmp_path)

    text = (tmp_path / "_kanban.md").read_text(encoding="utf-8")
    key = extract_board_key(text)
    assert key is not None
    assert len(key) == 32 and all(c in "0123456789abcdef" for c in key)
    # Marker sits directly under the title line.
    lines = text.splitlines()
    assert lines[0].startswith("# ")
    assert lines[1] == format_board_key_marker(key)
    # The created note mentions the mint.
    assert any(
        "_kanban.md" in note and "board key" in note for note in result.created
    )


def test_existing_keyed_board_untouched_byte_for_byte(tmp_path: Path):
    """A board that already carries a key is NEVER modified on re-provision."""
    board = tmp_path / "_kanban.md"
    keyed = (
        "# Keyed Board\n"
        "<!-- kanbanger:board-id: aabbccddeeff00112233445566778899 -->\n"
        "\n## BACKLOG\n*   [ ] keep me\n"
    )
    board.write_text(keyed, encoding="utf-8")

    result = provision_project(tmp_path)

    assert board.read_text(encoding="utf-8") == keyed
    assert any(
        "_kanban.md" in note and "already" in note.lower()
        for note in result.already_present
    )
    assert all("_kanban.md" not in note for note in result.updated)


def test_minted_key_stable_across_reruns(tmp_path: Path):
    """The key is minted ONCE; re-provisioning never re-mints or duplicates."""
    provision_project(tmp_path)
    board = tmp_path / "_kanban.md"
    first = board.read_text(encoding="utf-8")
    key_first = extract_board_key(first)

    provision_project(tmp_path)
    provision_project(tmp_path)

    final = board.read_text(encoding="utf-8")
    assert final == first  # byte-identical across re-runs
    assert extract_board_key(final) == key_first
    assert final.count("kanbanger:board-id") == 1


def test_minting_existing_board_preserves_crlf_bytes(tmp_path: Path):
    """Minting into a CRLF board preserves every original byte and uses the
    board's own newline style for the one added marker line."""
    board = tmp_path / "_kanban.md"
    original = b"# CRLF Board\r\n\r\n## BACKLOG\r\n*   [ ] item\r\n"
    board.write_bytes(original)

    provision_project(tmp_path)

    after = board.read_bytes()
    key = extract_board_key(after.decode("utf-8"))
    assert key is not None
    marker_bytes = (format_board_key_marker(key) + "\r\n").encode("utf-8")
    assert after.replace(marker_bytes, b"", 1) == original


# --- CLAUDE.md touchpoint idempotency --------------------------------------


def test_touchpoint_created_when_absent(tmp_path: Path):
    provision_project(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8")
    assert CLAUDE_MD_START in text
    assert CLAUDE_MD_END in text
    assert "Never hand-edit `_kanban.md`" in text
    assert "project-scoped" in text
    assert "REVIEW gates DONE" in text


def test_touchpoint_idempotent_second_run_is_noop(tmp_path: Path):
    provision_project(tmp_path)
    claude_after_first = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    board_after_first = (tmp_path / "_kanban.md").read_text(encoding="utf-8")
    mcp_after_first = (tmp_path / ".mcp.json").read_text(encoding="utf-8")

    result2 = provision_project(tmp_path)

    # Files are byte-identical after a second run.
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == claude_after_first
    assert (tmp_path / "_kanban.md").read_text(encoding="utf-8") == board_after_first
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == mcp_after_first

    # Exactly one stanza — no duplication.
    assert claude_after_first.count(CLAUDE_MD_START) == 1
    assert claude_after_first.count(CLAUDE_MD_END) == 1

    # Second run created nothing new.
    assert result2.created == []


def test_touchpoint_appended_without_clobbering_existing(tmp_path: Path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nProject-specific guidance.\n", encoding="utf-8")

    provision_project(tmp_path)

    text = claude_md.read_text(encoding="utf-8")
    assert "Project-specific guidance." in text
    assert CLAUDE_MD_START in text


# --- AGENTS.md: augment only if present ------------------------------------


def test_agents_md_not_created_when_absent(tmp_path: Path):
    provision_project(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()


def test_agents_md_augmented_when_present(tmp_path: Path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# AGENTS\n\nExisting agent guidance.\n", encoding="utf-8")

    provision_project(tmp_path)

    text = agents_md.read_text(encoding="utf-8")
    assert "Existing agent guidance." in text
    assert CLAUDE_MD_START in text


# --- GitHub sync config: empty placeholders, no secrets --------------------


def test_mcp_json_sync_slots_are_empty_placeholders(tmp_path: Path):
    provision_project(tmp_path)
    text = (tmp_path / ".mcp.json").read_text(encoding="utf-8")
    assert "${GITHUB_TOKEN:-}" in text
    assert "${GITHUB_REPO:-}" in text
    assert "${GITHUB_PROJECT_NUMBER:-}" in text
    # Targets the GLOBAL command, not a per-project venv interpreter.
    assert "kanbanger-mcp" in text
    assert ".venv" not in text


def test_mcp_json_not_clobbered_when_present(tmp_path: Path):
    mcp_json = tmp_path / ".mcp.json"
    sentinel = '{"mcpServers": {"kanbanger": {"command": "custom"}}}\n'
    mcp_json.write_text(sentinel, encoding="utf-8")

    result = provision_project(tmp_path)

    assert mcp_json.read_text(encoding="utf-8") == sentinel
    assert any(".mcp.json" in note for note in result.already_present)


# --- error handling --------------------------------------------------------


def test_provision_raises_on_missing_dir(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        provision_project(missing)


# --- summary ---------------------------------------------------------------


def test_summary_mentions_secret_safety(tmp_path: Path):
    result = provision_project(tmp_path)
    summary = result.summary()
    assert "no secrets" in summary.lower()
    assert "GITHUB_TOKEN" in summary


# --- the setup_project MCP tool --------------------------------------------


def _setup_project_tool(workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """Register tools against a stub with KANBANGER_WORKSPACE=workspace and
    return the `setup_project` callable. Importing here (not at module top)
    keeps the env var set before tools read it."""
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(workspace))
    from tests.conftest import _StubMCPServer
    from kanbanger.tools import register_tools

    stub = _StubMCPServer()
    register_tools(stub)
    return stub.tools["setup_project"]


def test_setup_project_tool_scaffolds_board(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tool = _setup_project_tool(tmp_path, monkeypatch)
    out = tool()

    board = tmp_path / "_kanban.md"
    assert board.exists()
    assert _columns_in(board.read_text(encoding="utf-8")) == CANONICAL_COLUMNS
    assert "Provisioned kanbanger in:" in out
    assert "_kanban.md" in out


def test_setup_project_tool_does_not_clobber_existing_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Existing board content survives the MCP setup_project tool.

    Step-4 amendment (ADR 0002): the tool's one sanctioned modification is
    minting the board-key marker into an unkeyed board; removing that one
    line reproduces the original byte-for-byte, and the summary reports the
    mint as an update.
    """
    board = tmp_path / "_kanban.md"
    sentinel = "# Existing\n\n## BACKLOG\n*   [ ] keep me\n"
    board.write_text(sentinel, encoding="utf-8")

    tool = _setup_project_tool(tmp_path, monkeypatch)
    out = tool()

    after = board.read_text(encoding="utf-8")
    key = extract_board_key(after)
    assert key is not None
    assert after.replace(format_board_key_marker(key) + "\n", "", 1) == sentinel
    assert "minted board key" in out


def test_setup_project_tool_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tool = _setup_project_tool(tmp_path, monkeypatch)
    tool()
    board_after_first = (tmp_path / "_kanban.md").read_text(encoding="utf-8")
    claude_after_first = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    tool()  # second run

    assert (tmp_path / "_kanban.md").read_text(encoding="utf-8") == board_after_first
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == claude_after_first
    assert claude_after_first.count(CLAUDE_MD_START) == 1


# --- kanbanger init CLI parity ---------------------------------------------


def test_cli_init_provisions_dir(tmp_path: Path):
    from kanbanger.cli import init

    rc = init([str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "_kanban.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_cli_init_rejects_missing_dir(tmp_path: Path):
    from kanbanger.cli import init

    rc = init([str(tmp_path / "nope")])
    assert rc == 1
