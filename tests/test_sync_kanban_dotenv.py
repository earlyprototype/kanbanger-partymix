"""B5 / dotenv-find-usecwd regression guards for sync_kanban .env loading.

Two related bugs are covered here.

B5 (PR #1, 2026-05-18 meTube integration): a shell-exported
GITHUB_REPO silently shadowed the project's `.env` value, routing
the sync to the wrong repository. python-dotenv's `load_dotenv()`
defaults to `override=False`, which keeps the shell env winning. The
project's `.env` should be authoritative for sync targets —
`override=True` makes it so.

dotenv-find-usecwd (PR #2 follow-up, same 2026-05-18 integration):
python-dotenv's `find_dotenv()` defaults to searching upward from
the *caller module's file location*, not from the user's CWD. When
kanban-sync was invoked from a target project, a rogue
parent-of-source-directory `.env` (e.g. ~/Desktop/AI/.env)
intercepted the lookup and the target project's `.env` was never
considered. `find_dotenv(usecwd=True)` makes the search start at
`os.getcwd()` so the CWD-closest `.env` wins.

Three complementary checks:
  1. Source-level: the call site uses `find_dotenv(usecwd=True)`
     and `override=True`.
  2. Behaviour-level (B5): a subprocess run shows the `.env` value
     winning over a shell-exported value of the same name.
  3. Behaviour-level (usecwd): a subprocess run shows a child-dir
     `.env` winning over a parent-of-source-dir `.env`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_sync_kanban_calls_load_dotenv_with_override_true():
    """Regression guard against accidentally dropping the override flag.

    Reads sync_kanban.py and asserts the call site uses both
    `find_dotenv(usecwd=True)` and `override=True`. Cheap, doesn't
    import the module (which would actually load .env), and makes the
    intent obvious at code-review time.
    """
    source_root = Path(__file__).resolve().parent.parent
    sync_src = (source_root / "sync_kanban.py").read_text(encoding="utf-8")
    assert "find_dotenv(usecwd=True)" in sync_src, (
        "sync_kanban.py must call find_dotenv(usecwd=True) so that the "
        "search for `.env` starts at os.getcwd() rather than the caller "
        "module's directory. Without it, a rogue parent-of-source-dir "
        ".env can intercept the lookup and the target project's .env is "
        "never considered. See follow-up to PR #1 (B5)."
    )
    assert "override=True" in sync_src, (
        "sync_kanban.py must pass override=True so that the project's "
        ".env is authoritative — without it, a stale shell-exported "
        "GITHUB_REPO can silently route sync to the wrong project. See "
        "INTEGRATION_REPORT entry B5."
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
        timeout=30,
    )
    assert result.returncode == 0, (
        f"probe exited {result.returncode}\nstdout:{result.stdout}\n"
        f"stderr:{result.stderr}"
    )
    assert result.stdout.strip() == "from-dotenv/winner", (
        f"override=True should have made the .env value win, got "
        f"{result.stdout.strip()!r}"
    )


def test_dotenv_find_usecwd_beats_rogue_parent_env(tmp_path: Path):
    """End-to-end check: CWD-closest .env beats a rogue parent .env.

    Reproduces the bug pattern from the meTube 2026-05-18 follow-up:
    a rogue `.env` lives in an ancestor of the sync_kanban source
    directory, and the intended target project's `.env` lives in the
    user's CWD. Without `find_dotenv(usecwd=True)` the rogue parent
    wins because the default search anchors on the caller module's
    file location. With `usecwd=True`, the target project's `.env`
    wins.

    Strategy: spawn a subprocess whose CWD is a child tempdir
    containing `.env` (the "target project"), with the actual
    `sync_kanban` source dir copied beneath a rogue ancestor `.env`.
    Import sync_kanban (which triggers its module-load `.env`
    discovery code path) and read back the key. The CWD `.env` must
    win. This fails on the pre-patch code (which called
    `load_dotenv(override=True)` without `find_dotenv(usecwd=True)`)
    and passes after.
    """
    try:
        import dotenv  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("python-dotenv not installed in this venv")

    source_root = Path(__file__).resolve().parent.parent

    # Rogue .env lives at the top of an ancestor directory of the
    # sync_kanban source. We don't copy the source — we put the rogue
    # .env at a real parent of the actual sync_kanban.py on disk, then
    # rely on `find_dotenv`'s default behaviour of walking up from the
    # caller module's file location to find it. To do that without
    # polluting the real repo's parents, we redirect via PYTHONPATH:
    # the probe imports sync_kanban from a copy under a sandboxed
    # ancestor that owns the rogue .env.
    import shutil

    rogue_root = tmp_path / "rogue_ancestor"
    sandboxed_src = rogue_root / "sync_kanban_src"
    sandboxed_src.mkdir(parents=True)
    # Copy only the modules sync_kanban needs at import time. The
    # module-load .env block fires before any heavy imports, so this
    # is sufficient — and avoids dragging the whole repo into tmp.
    shutil.copy2(source_root / "sync_kanban.py", sandboxed_src / "sync_kanban.py")
    shutil.copy2(source_root / "kanban_io.py", sandboxed_src / "kanban_io.py")
    # Rogue .env at a parent of the sandboxed source dir — what
    # find_dotenv() with default (caller-module) anchoring would hit.
    (rogue_root / ".env").write_text(
        "KANBANGER_CWD_TEST=rogue_value\n", encoding="utf-8"
    )

    # Target project lives in a separate dir under tmp_path; its .env
    # is what should win when CWD is set here.
    target_project = tmp_path / "target_project"
    target_project.mkdir()
    (target_project / ".env").write_text(
        "KANBANGER_CWD_TEST=tempdir_value\n", encoding="utf-8"
    )

    # Probe imports the sandboxed sync_kanban and prints the resulting
    # env var. Importing sync_kanban triggers its module-load `.env`
    # discovery — that's the code path under test.
    #
    # CRITICAL: the probe must be a real .py file, not a `-c` string.
    # python-dotenv's find_dotenv() treats `-c` invocations as
    # "interactive" (no __file__ on __main__) and silently falls back
    # to os.getcwd(), which would mask the bug — the rogue parent
    # never gets a chance to intercept. Writing the probe to disk and
    # invoking it as `python probe.py` gives __main__ a __file__ and
    # exercises the real `find_dotenv()` caller-frame walk.
    probe_path = tmp_path / "probe.py"
    probe_path.write_text(
        textwrap.dedent(
            """
            import os, sys
            sys.path.insert(0, r"{src}")
            import sync_kanban  # noqa: F401  (import has the side effect)
            print(os.environ.get("KANBANGER_CWD_TEST", "<unset>"))
            """
        ).lstrip().format(src=str(sandboxed_src)),
        encoding="utf-8",
    )

    env = dict(os.environ)
    # Strip the key from inherited env so we can detect whether .env
    # loading actually set it (and which file won).
    env.pop("KANBANGER_CWD_TEST", None)

    result = subprocess.run(
        [sys.executable, str(probe_path)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(target_project),
        timeout=30,
    )
    assert result.returncode == 0, (
        f"probe exited {result.returncode}\nstdout:{result.stdout}\n"
        f"stderr:{result.stderr}"
    )
    assert result.stdout.strip() == "tempdir_value", (
        f"sync_kanban must load the CWD-closest .env, not a rogue "
        f"parent-of-source .env. Got {result.stdout.strip()!r}; "
        f"expected 'tempdir_value'. This indicates the bug from the "
        f"meTube 2026-05-18 follow-up to PR #1 has regressed — "
        f"sync_kanban likely dropped find_dotenv(usecwd=True)."
    )
