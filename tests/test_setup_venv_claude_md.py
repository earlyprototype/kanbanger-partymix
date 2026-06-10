"""Tests for the CLAUDE.md onboarding stanza written by scripts/setup-venv.py.

setup-venv.py lives outside the importable package (it's a hyphenated script in
scripts/), so it's loaded by file path via importlib rather than `import`.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP_VENV_PATH = REPO_ROOT / "scripts" / "setup-venv.py"


@pytest.fixture(scope="module")
def setup_venv():
    spec = importlib.util.spec_from_file_location("setup_venv", SETUP_VENV_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_creates_claude_md_when_absent(setup_venv, tmp_path):
    setup_venv.ensure_claude_md_has_kanbanger(tmp_path)

    claude_md = tmp_path / "CLAUDE.md"
    assert claude_md.exists()
    text = claude_md.read_text(encoding="utf-8")

    assert setup_venv.CLAUDE_MD_START in text
    assert setup_venv.CLAUDE_MD_END in text
    # The directives that fix the two reported symptoms must be present.
    assert "Never hand-edit `_kanban.md`" in text   # use the MCP, not file edits
    assert "project-scoped" in text                  # not user/global scope
    assert "REVIEW gates DONE" in text


def test_appends_without_clobbering_existing_content(setup_venv, tmp_path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My Project\n\nProject-specific guidance.\n", encoding="utf-8")

    setup_venv.ensure_claude_md_has_kanbanger(tmp_path)

    text = claude_md.read_text(encoding="utf-8")
    assert "Project-specific guidance." in text     # original content preserved
    assert setup_venv.CLAUDE_MD_START in text         # stanza appended


def test_idempotent_no_duplicate_block(setup_venv, tmp_path):
    setup_venv.ensure_claude_md_has_kanbanger(tmp_path)
    setup_venv.ensure_claude_md_has_kanbanger(tmp_path)
    setup_venv.ensure_claude_md_has_kanbanger(tmp_path)

    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count(setup_venv.CLAUDE_MD_START) == 1
    assert text.count(setup_venv.CLAUDE_MD_END) == 1


def test_recovery_command_points_at_in_mcp_provisioning(setup_venv, tmp_path):
    setup_venv.ensure_claude_md_has_kanbanger(tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    # Recovery now points at the in-MCP provisioning path (issue #15 step 3):
    # the `setup_project` tool, or `kanbanger init` for CLI parity — NOT the
    # deprecated scripts/setup-venv.py.
    assert "setup_project" in text
    assert "kanbanger init" in text
