"""
kanbanger.binding — collision-proof board binding (ADR 0002, issue #15 step 4).

Board binding = DERIVED DISCOVERY + MINTED IDENTITY:

  * DISCOVERY answers "which board?" by walking UP from a start directory to
    the NEAREST ancestor containing `_kanban.md` (zero-config, like git
    finding its repo root — but with no dependency on `.git` or any VCS).
  * IDENTITY comes from the stable board key minted into the board file at
    provision time (see kanban_io.mint_board_key / kanbanger.provision) —
    never from the folder path, which breaks on move/clone, and never from
    a name-derived key (ADR 0002 non-goals).

Resolution precedence (back-compat critical — order is load-bearing):

  1. `KANBANGER_WORKSPACE` env var, when set and non-blank: the explicit
     pin wins, exactly as before ADR 0002. Every `.mcp.json` written by
     provisioning sets it, so existing projects resolve identically.
     An empty / whitespace-only value is treated as UNSET (a degenerate
     config, not a real pin).
  2. Walk-up discovery from the start directory (default: the server
     process cwd): nearest ancestor — including the start dir itself —
     whose `_kanban.md` is a regular file.
  3. Fallback: the start directory itself (unprovisioned workspace;
     `board_path` resolves to None).

This module lives in the `kanbanger` package (alongside provision.py, the
step-3 convention) because resolution is a server-side concern; the key
PRIMITIVES live in the root `kanban_io` module so `sync_kanban` can share
them without importing the mcp SDK (same D8 reasoning that put the task
parser there).

`resolve_binding()` exposes the full `workspace -> board -> key` triple so
kanban-doctor (issue #15 step 5) can print it without re-deriving anything.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kanban_io import read_board_key

KANBAN_FILENAME = "_kanban.md"
WORKSPACE_ENV_VAR = "KANBANGER_WORKSPACE"


@dataclass(frozen=True)
class Binding:
    """The resolved workspace -> board -> key triple.

    workspace:  absolute, symlink-resolved directory the server operates in.
                Always present (falls back to the start dir when nothing is
                provisioned).
    board_path: absolute path to `<workspace>/_kanban.md`, or None when the
                workspace has no board (unprovisioned).
    board_key:  the stable identity minted into the board at provision time,
                or None when the board is absent OR predates minting (old
                unkeyed boards keep working everywhere — None is a normal
                state, not an error).
    """

    workspace: str
    board_path: Optional[str]
    board_key: Optional[str]


def find_board_dir(start_dir) -> Optional[Path]:
    """Walk UP from `start_dir` to the nearest directory holding `_kanban.md`.

    Checks `start_dir` itself first, then each ancestor toward the
    filesystem root; the FIRST hit wins, which makes resolution
    deterministic in a monorepo holding several boards (the sub-project's
    board shadows the repo-root board for anything started inside the
    sub-project).

    Defined behavior for the ADR 0002 resolution matrix:

      * Nested subfolder — starting anywhere under a provisioned project
        resolves that project's board.
      * Monorepo (>= 2 boards) — the NEAREST enclosing board wins,
        deterministically; siblings without their own board resolve the
        repo-root board.
      * Git worktree — discovery is PURE path-walking: `.git` (dir or
        pointer file) is never consulted, so a worktree containing its own
        checked-out `_kanban.md` resolves that copy, never the main
        working tree's.
      * Symlinked path — symlinks are resolved FIRST (`Path.resolve()`):
        the PHYSICAL path governs both the walk and the returned
        workspace. Rationale: the codebase already canonicalizes every
        workspace path this way (the S2 convention in get_workspace), so a
        board reached through any number of symlink aliases has exactly
        ONE workspace identity — and `os.getcwd()` already returns the
        physical path on POSIX, so a logical-path walk would not even be
        reliably observable.
      * No `.git` anywhere — irrelevant by construction; only
        `_kanban.md` presence is consulted.
      * Moved folder — the walk re-finds the board at its new location;
        identity continuity comes from the in-board minted key, which
        travels with the file (see resolve_binding).
      * Copied board — each copy is discovered independently (local board
        ops act on whichever copy encloses the start dir). The shared key
        is intentional: it is how SYNC STATE detects that a state file and
        a board belong to different boards (see
        sync_kanban.StateManager.verify_board_key).

    A directory named `_kanban.md` does not count — the board must be a
    regular file. Returns None when no ancestor holds a board.
    """
    start = Path(start_dir).resolve()
    for candidate in (start, *start.parents):
        if (candidate / KANBAN_FILENAME).is_file():
            return candidate
    return None


def resolve_workspace(start_dir=None) -> Path:
    """Resolve the workspace directory by the ADR 0002 precedence chain.

    env pin (`KANBANGER_WORKSPACE`, blank treated as unset) > walk-up
    discovery from `start_dir` (default: process cwd) > `start_dir` itself
    as the unprovisioned fallback. Always returns an absolute,
    symlink-resolved path (S2 property preserved).
    """
    env_value = os.getenv(WORKSPACE_ENV_VAR)
    if env_value is not None and env_value.strip():
        return Path(env_value).resolve()

    start = Path(start_dir) if start_dir is not None else Path(os.getcwd())
    found = find_board_dir(start)
    if found is not None:
        return found
    return start.resolve()


def resolve_binding(start_dir=None) -> Binding:
    """Resolve the full `workspace -> board -> key` triple (ADR 0002).

    The single observability entry point: the MCP server derives its
    workspace from the same chain (via resolve_workspace), and
    kanban-doctor (step 5) can render `workspace resolved = X -> board = Y
    -> key = Z` from one call. board_path/board_key are None for an
    unprovisioned workspace; board_key alone is None for a keyless legacy
    board (still fully operable).
    """
    workspace = resolve_workspace(start_dir)
    board = workspace / KANBAN_FILENAME
    if board.is_file():
        return Binding(
            workspace=str(workspace),
            board_path=str(board),
            board_key=read_board_key(board),
        )
    return Binding(workspace=str(workspace), board_path=None, board_key=None)
