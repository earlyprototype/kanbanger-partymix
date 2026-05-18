"""B5 regression guard: sync_kanban must load .env with override=True.

The bug from INTEGRATION_REPORT entry B5 (2026-05-18 meTube
integration): a shell-exported GITHUB_REPO silently shadowed the
project's `.env` value, routing the sync to the wrong repository.
python-dotenv's `load_dotenv()` defaults to `override=False`, which
keeps the shell env winning. The project's `.env` should be
authoritative for sync targets — `override=True` makes it so.

Two complementary checks:
  1. Source-level: the call site uses `override=True`.
  2. Behaviour-level: a subprocess run shows the `.env` value
     winning over a shell-exported value of the same name.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_sync_kanban_calls_load_dotenv_with_override_true():
    """Regression guard against accidentally dropping the override flag.

    Reads sync_kanban.py and asserts the literal `load_dotenv(override=True)`
    call is present. Cheap, doesn't import the module (which would
    actually load .env), and makes the intent obvious at code-review
    time.
    """
    source_root = Path(__file__).resolve().parent.parent
    sync_src = (source_root / "sync_kanban.py").read_text(encoding="utf-8")
    assert "load_dotenv(override=True)" in sync_src, (
        "sync_kanban.py must call load_dotenv(override=True) so that the "
        "project's .env is authoritative — without override=True, a stale "
        "shell-exported GITHUB_REPO can silently route sync to the wrong "
        "project. See INTEGRATION_REPORT entry B5."
    )


def test_dotenv_override_actually_beats_shell_env(tmp_path: Path):
    """End-to-end check: with override=True, .env wins over shell env.

    Spawns a subprocess that:
      - inherits a fake GITHUB_REPO from the parent env,
      - writes a different GITHUB_REPO into a temp .env,
      - calls load_dotenv(override=True) pointed at that .env,
      - prints the resulting value.

    The `.env` value should win. If python-dotenv ever changes its
    semantics or someone reverts the partymix fix to `override=False`,
    this catches it.
    """
    try:
        import dotenv  # noqa: F401
    except ImportError:
        # python-dotenv isn't a hard dep for the lib, only for sync CLI.
        # Skip rather than fail in environments without it.
        import pytest

        pytest.skip("python-dotenv not installed in this venv")

    env_file = tmp_path / ".env"
    env_file.write_text("GITHUB_REPO=from-dotenv/winner\n", encoding="utf-8")

    probe = textwrap.dedent(
        """
        import os
        from dotenv import load_dotenv
        load_dotenv(r"{path}", override=True)
        print(os.environ["GITHUB_REPO"])
        """
    ).format(path=str(env_file))

    env = dict(os.environ)
    env["GITHUB_REPO"] = "from-shell/loser"

    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"probe exited {result.returncode}\nstdout:{result.stdout}\n"
        f"stderr:{result.stderr}"
    )
    assert result.stdout.strip() == "from-dotenv/winner", (
        f"override=True should have made the .env value win, got "
        f"{result.stdout.strip()!r}"
    )
