"""Regression guards for the pre-commit hook in non-TTY contexts.

The hook previously used interactive `read -p "Commit anyway? (y/N)"`
prompts in two override branches: (A) `.kanban.json` missing
("never synced") and (B) `_kanban.md` newer than `.kanban.json`
("unsaved changes"). When stdin is not a terminal (CI, AI-agent
commits, scripted git workflows), `read` blocks forever waiting for
input that will never arrive — the commit hangs indefinitely.

The fix wraps each prompt in `[ -t 0 ]` so:
  - human at a terminal: same behaviour as before (prompt + override)
  - non-TTY:              hard-fail with a clear remediation message

These tests run the hook in a subprocess with stdin redirected from
/dev/null (no terminal) and assert:
  1. The process exits non-zero (commit blocked).
  2. It exits within a few seconds (the pre-patch hook would hang
     in CI where stdin is a pipe with no writer; `timeout=5` proves
     the fix on platforms where pipe-stdin actually blocks `read`).
  3. The output names the non-interactive context so the human
     reading the CI log knows the remediation.

Discovered during meTube integration follow-up 2026-05-18, third in
the post-merge bug class alongside PRs #1 (override=True) and #2
(find_dotenv usecwd).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "git-hooks" / "pre-commit"
# Duplicate of HOOK_PATH bundled into the kanbanger-dist install package.
# kanbanger-dist/INSTALL.sh invokes kanbanger-dist/git-hooks/install-hooks.sh,
# which copies *this* file into the consumer's .git/hooks/, so any TTY-guard
# fix to the source hook MUST be mirrored here or the bug ships unfixed.
DIST_HOOK_PATH = REPO_ROOT / "kanbanger-dist" / "git-hooks" / "pre-commit"

# Generous enough to absorb cold-start subprocess overhead on Windows
# msys/Git Bash but short enough that a hanging `read` is caught
# quickly. The pre-patch hook waits forever in any environment where
# pipe-stdin doesn't immediately EOF; any value here proves the fix
# in those environments.
NON_TTY_TIMEOUT_SECS = 5


def _resolve_bash() -> str:
    """Find a bash that runs POSIX shell scripts correctly.

    On Linux/macOS, `which bash` is canonical. On Windows the picture
    is muddier: `shutil.which("bash")` may return WSL's
    `C:\\Windows\\System32\\bash.exe`, which runs in a Linux VFS and
    cannot read Windows paths handed to it through subprocess argv.
    We prefer Git Bash (`C:\\Program Files\\Git\\usr\\bin\\bash.exe`)
    when present — it ships with git-for-windows and handles the
    repo's CRLF line endings + Windows paths correctly. Falls back
    to PATH bash otherwise.
    """
    if sys.platform == "win32":
        git_bash = Path(r"C:\Program Files\Git\usr\bin\bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    found = shutil.which("bash")
    if found:
        return found
    pytest.skip("no bash on PATH; pre-commit hook tests require a POSIX shell")


def _run_hook_without_tty(cwd: Path) -> subprocess.CompletedProcess:
    """Invoke the pre-commit hook with stdin detached from any TTY.

    Strategy:
      - Copy the hook into the workspace's tmpdir so we invoke it
        with a relative path (`bash pre-commit`). This sidesteps
        Windows path-translation issues that bite when bash receives
        a `C:\\Users\\...` arg through subprocess argv.
      - `stdin=subprocess.DEVNULL` gives the child a closed stdin —
        the closest portable proxy for "no terminal".
      - `timeout=NON_TTY_TIMEOUT_SECS` is the load-bearing safety
        net. On environments where pipe-stdin blocks `read` rather
        than returning EOF, the pre-patch hook hangs and pytest
        raises `TimeoutExpired`; we catch that and re-raise as a
        clear assertion failure.
      - `encoding="utf-8", errors="replace"` — the hook prints emoji
        (🔍, ⚠️, etc.); on Windows the default cp1252 codec crashes
        decoding them. Force UTF-8 with a fallback so the captured
        output is always inspectable.
    """
    bash = _resolve_bash()
    # Copy the hook in so subprocess invokes `bash pre-commit` from
    # inside `cwd`. No absolute path crosses the subprocess argv
    # boundary; line endings + execute bits stay intact via
    # shutil.copy2.
    shutil.copy2(HOOK_PATH, cwd / "pre-commit")
    return subprocess.run(
        [bash, "pre-commit"],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=NON_TTY_TIMEOUT_SECS,
    )


@pytest.fixture
def minimal_kanban_workspace_never_synced(tmp_path: Path) -> Path:
    """Workspace with `_kanban.md` but no `.kanban.json` (branch A).

    Triggers the hook's "Kanban has never been synced to GitHub"
    override prompt — the first of the two `read -p` sites we're
    guarding.
    """
    (tmp_path / "_kanban.md").write_text(
        "# Test Kanban\n\n## BACKLOG\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def minimal_kanban_workspace_unsaved(tmp_path: Path) -> Path:
    """Workspace where `_kanban.md` is newer than `.kanban.json` (branch B).

    The hook uses `[ "_kanban.md" -nt ".kanban.json" ]` to gate
    branch B. We write `.kanban.json` first, then `_kanban.md`, then
    explicitly bump the kanban mtime to be strictly newer in case
    the filesystem's mtime resolution is coarse (FAT32, some
    network mounts, fast tmpdirs that don't guarantee monotonic
    mtimes between two writes inside the same second).
    """
    state = tmp_path / ".kanban.json"
    state.write_text("{}", encoding="utf-8")
    # Backdate the state file so `-nt` is unambiguous.
    old_time = time.time() - 60
    os.utime(state, (old_time, old_time))

    kanban = tmp_path / "_kanban.md"
    kanban.write_text(
        "# Test Kanban\n\n## BACKLOG\n- New task\n", encoding="utf-8"
    )
    # Touch kanban with current time to be strictly newer than state.
    now = time.time()
    os.utime(kanban, (now, now))
    return tmp_path


def test_hook_file_exists():
    """Sanity: the hook lives where we think it does.

    Cheap, but if someone moves `git-hooks/pre-commit` the failure
    here is louder and more useful than a confusing subprocess
    error from later tests.
    """
    assert HOOK_PATH.is_file(), (
        f"pre-commit hook not found at {HOOK_PATH}; tests below assume "
        f"its location and will spuriously fail without it."
    )


def test_non_tty_never_synced_blocks_commit_without_hanging(
    minimal_kanban_workspace_never_synced: Path,
):
    """Branch A: `.kanban.json` missing, no terminal -> hard fail fast.

    Pre-patch behaviour: hook hits `read -p "Commit anyway? (y/N)"`
    on line ~24 and (a) blocks indefinitely on platforms where pipe
    stdin doesn't EOF, or (b) reads empty and falls through with no
    explicit "non-interactive" message. Post-patch: hook detects
    `[ -t 0 ]` is false and exits 1 immediately with the documented
    message naming the remediation.

    The timeout on subprocess.run is the proof-of-fix for (a). The
    "non-interactive" message assertion is the proof for (b).
    Together they cover both failure modes.
    """
    try:
        result = _run_hook_without_tty(
            minimal_kanban_workspace_never_synced
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"pre-commit hook hung for >{NON_TTY_TIMEOUT_SECS}s in a "
            f"non-TTY context (branch A: never-synced). The TTY-check "
            f"fix has regressed — `read -p` is blocking on closed "
            f"stdin again. Hook path: {HOOK_PATH}.\n"
            f"Partial stdout: {exc.stdout!r}\n"
            f"Partial stderr: {exc.stderr!r}"
        )

    assert result.returncode != 0, (
        f"hook should refuse to let the commit through in non-TTY "
        f"context with no .kanban.json, but exited 0. "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "non-interactive" in combined, (
        f"hook must explain the non-interactive refusal so a human "
        f"reading CI logs knows what to do. Expected the string "
        f"'non-interactive' in combined output. Got:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_non_tty_unsaved_changes_blocks_commit_without_hanging(
    minimal_kanban_workspace_unsaved: Path,
):
    """Branch B: kanban newer than state, no terminal -> hard fail fast.

    Same shape as branch A but exercises the second `read -p`
    block in the hook (around line 38, the "unsaved changes"
    override). Pre-patch this also hung (or fell through silently);
    post-patch it must exit non-zero with the clear message.
    """
    try:
        result = _run_hook_without_tty(
            minimal_kanban_workspace_unsaved
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"pre-commit hook hung for >{NON_TTY_TIMEOUT_SECS}s in a "
            f"non-TTY context (branch B: unsaved-changes). The "
            f"TTY-check fix has regressed — `read -p` is blocking on "
            f"closed stdin again. Hook path: {HOOK_PATH}.\n"
            f"Partial stdout: {exc.stdout!r}\n"
            f"Partial stderr: {exc.stderr!r}"
        )

    assert result.returncode != 0, (
        f"hook should refuse to let the commit through in non-TTY "
        f"context when kanban is newer than state, but exited 0. "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "non-interactive" in combined, (
        f"hook must explain the non-interactive refusal so a human "
        f"reading CI logs knows what to do. Expected the string "
        f"'non-interactive' in combined output. Got:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_hook_source_contains_tty_guards():
    """Source-level guard: the hook checks `[ -t 0 ]` in both branches.

    Cheap belt-and-braces check on top of the behavioural tests.
    If someone replaces the TTY guard with a different non-TTY
    detector (e.g. test on `$CI`), the behavioural tests still
    pass; this one catches the loss of the canonical POSIX idiom
    we documented in the commit message.
    """
    src = HOOK_PATH.read_text(encoding="utf-8")
    # Two prompt blocks -> at least two `[ -t 0 ]` checks expected.
    occurrences = src.count("[ -t 0 ]")
    assert occurrences >= 2, (
        f"pre-commit hook must guard each `read -p` block with "
        f"`[ -t 0 ]` (POSIX TTY check). Found {occurrences} "
        f"occurrence(s); expected at least 2 (one per override "
        f"prompt). Hook contents:\n{src}"
    )


def test_source_and_dist_pre_commit_hooks_stay_in_sync():
    """Drift guard: kanbanger-dist/git-hooks/pre-commit must mirror the source.

    The dist copy is what `kanbanger-dist/INSTALL.sh` actually ships to
    consumers (via `git-hooks/install-hooks.sh` → `cp` into `.git/hooks/`).
    History: when the original TTY-guard fix landed it patched only the
    source hook, leaving the dist duplicate broken for every downstream
    installer. This test exists so that bug class can't recur silently —
    any future edit to one hook forces an edit to the other or the test
    fails with a clear diff pointer.

    Read via `read_text` (universal-newlines on Python text mode) so
    Windows autocrlf doesn't cause spurious CRLF-vs-LF failures in the
    working tree; the comparison is on logical content, not byte order.
    """
    assert HOOK_PATH.is_file(), f"source hook missing at {HOOK_PATH}"
    assert DIST_HOOK_PATH.is_file(), (
        f"dist hook missing at {DIST_HOOK_PATH}; if kanbanger-dist/ has "
        f"been removed, delete this test and DIST_HOOK_PATH together."
    )
    source = HOOK_PATH.read_text(encoding="utf-8")
    dist = DIST_HOOK_PATH.read_text(encoding="utf-8")
    assert source == dist, (
        f"pre-commit hook has drifted between source ({HOOK_PATH}) and "
        f"dist ({DIST_HOOK_PATH}). The dist copy is what INSTALL.sh ships "
        f"to consumers — any divergence means downstream installs get a "
        f"different hook than the repo claims. Sync them or delete this "
        f"test if the divergence is intentional.\n"
        f"--- source ({len(source)} chars) ---\n{source}\n"
        f"--- dist ({len(dist)} chars) ---\n{dist}"
    )
