"""
Kanbanger MCP I/O helpers — atomic file writes and cross-process locking.

Audit-driven foundation for tools.py mutations:
- R1: atomic_write_text / atomic_write_json (temp + fsync + os.replace).
- R2: kanban_lock (msvcrt on Windows, fcntl on POSIX) — stdlib only.
- D1: state-file read/update/remove helpers used under the same lock as
  markdown writes so the kanban + sidecar pair stay coherent across crashes.
- ADR 0002 (issue #15 step 4): board identity key primitives (mint /
  extract / insert / read). They live HERE — not in kanbanger.binding —
  for the same reason parse_task_title_with_description does (D8):
  sync_kanban (a root module) needs them too, and importing the
  `kanbanger` package from sync_kanban would drag the mcp SDK into a
  module that is otherwise runnable with just requests + dotenv.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Tuple


_LOCK_FILENAME = ".kanban.lock"
_STATE_FILENAME = ".kanban.json"
_KANBAN_FILENAME = "_kanban.md"


# ---------------------------------------------------------------------------
# Board identity key (ADR 0002, issue #15 step 4)
#
# A board's identity is a stable ID MINTED INTO THE BOARD FILE at provision
# time — never the folder path (breaks on move/clone) and never a
# name-derived key (ADR 0002 non-goals). The key rides in an HTML comment
# directly under the board title, so it is invisible to humans reading the
# rendered markdown and ignored by every board parser (task lines start
# with `*`, column headers with `## ` — a `<!-- ... -->` line is neither).
#
# Marker shape (one line):   <!-- kanbanger:board-id: <key> -->
# Namespace matches the existing `<!-- kanbanger:start/end -->` touchpoint
# markers in kanbanger.provision.
# ---------------------------------------------------------------------------

# Tolerant reader: accept 8-64 chars of [A-Za-z0-9-] so hand-pasted dashed
# UUIDs (and future key formats) still read back; the canonical minted form
# is uuid4().hex (32 lowercase hex chars). The length floor stops the reader
# from latching onto arbitrary short junk in a lookalike comment.
_BOARD_KEY_RE = re.compile(
    r"^\s*<!--\s*kanbanger:board-id:\s*([0-9A-Za-z-]{8,64})\s*-->\s*$"
)


def mint_board_key() -> str:
    """Return a freshly minted board key: uuid4 as 32 lowercase hex chars.

    uuid4 gives 122 bits of randomness — collision-proof for board identity
    without any registry. The undashed hex form is a single regex-friendly
    token; a shortened form would save nothing (the marker is an invisible
    comment) while weakening the collision guarantee.
    """
    return uuid.uuid4().hex


def format_board_key_marker(board_key: str) -> str:
    """Render the single-line HTML-comment marker carrying `board_key`."""
    return f"<!-- kanbanger:board-id: {board_key} -->"


def extract_board_key(text: str) -> Optional[str]:
    """Return the board key found in `text`, or None if no marker present.

    Old boards without a key keep working everywhere — None simply means
    "unkeyed", never an error. First marker wins if several are present.
    """
    for line in text.splitlines():
        match = _BOARD_KEY_RE.match(line)
        if match:
            return match.group(1)
    return None


def read_board_key(board_path) -> Optional[str]:
    """Extract the board key from the board file at `board_path`.

    Returns None for: missing file, unreadable file, undecodable file, or a
    readable board that simply has no marker. Resolution must never crash on
    a sick board file — the board operations themselves surface read errors
    through their own structured-error paths.
    """
    try:
        text = Path(board_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return extract_board_key(text)


def insert_board_key(text: str, board_key: str) -> str:
    """Insert the board-key marker into board `text`; pure, byte-preserving.

    Placement: directly under the FIRST `# ` title line; at the very top if
    the board has no title line. Every existing byte of `text` is preserved
    — the only change is the one inserted marker line (terminated with the
    file's own newline style, CRLF or LF, so a CRLF board stays uniformly
    CRLF). The caller is responsible for checking the text is not already
    keyed (extract_board_key) — this function inserts unconditionally.
    """
    marker = format_board_key_marker(board_key)
    lines = text.splitlines(keepends=True)
    if not lines:
        return marker + "\n"

    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    insert_at = 0
    for i, line in enumerate(lines):
        # lstrip a BOM (U+FEFF escape below) so a BOM-prefixed title still
        # counts as the title.
        if line.lstrip("﻿").startswith("# "):
            insert_at = i + 1
            break

    if insert_at > 0 and not lines[insert_at - 1].endswith(("\n", "\r")):
        # Title is the last line and unterminated: terminate it, then add
        # the marker WITHOUT a trailing newline — purely additive, the
        # original's no-trailing-newline shape is preserved.
        lines.insert(insert_at, newline + marker)
    else:
        lines.insert(insert_at, marker + newline)
    return "".join(lines)


def discover_columns(workspace: str) -> list:
    """Return the column names from `_kanban.md` in document order.

    column-config: single source of truth for "what columns exist on
    this board." Reads the kanban file and yields each `## section`
    header in the order they appear. The MCP tools' validation paths
    consult this so a board with REVIEW (or any custom-named column)
    can be added-to / moved-from / deleted-from without the validator
    falsely rejecting it; resources.get_kanban_stats consults the same
    helper to keep stats and validation aligned.

    The board is the only configuration — there's no separate column-
    config file. The "configurable column set" feature (required vs
    optional, transition gates, etc.) lives in the Phase 1
    coordination-primitives bundle. This helper just makes validation
    permissive in the same way the parser already is.

    Returns an empty list if the file is missing; callers handle
    that by returning their own structured error.
    """
    kanban_path = os.path.join(workspace, _KANBAN_FILENAME)
    if not os.path.exists(kanban_path):
        return []
    with open(kanban_path, "r", encoding="utf-8") as f:
        content = f.read()
    columns = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            name = stripped[3:].strip()
            if name and name not in columns:
                columns.append(name)
    return columns


def ensure_review_column(workspace) -> bool:
    """Insert REVIEW into the board between DOING and DONE if absent.

    Returns True if migration was applied (4-column board upgraded
    to 5-column), False if REVIEW was already present (no-op) or
    the board doesn't exist.

    Acquires the kanban lock for the full read-modify-write so the
    migration is atomic against any other writer. Accepts either
    `str` or `pathlib.Path` for `workspace` so callers (server.py
    uses `str`; tests pass `Path` via the `kanban_workspace`
    fixture) don't need to coerce at the call site.
    """
    workspace = Path(workspace)
    kanban_path = workspace / _KANBAN_FILENAME
    if not kanban_path.exists():
        # No board to migrate; let downstream tools surface
        # kanban_not_found on their own terms.
        return False

    with kanban_lock(str(workspace)):
        text = kanban_path.read_text(encoding="utf-8")
        columns = discover_columns(str(workspace))
        if "REVIEW" in columns:
            return False

        # Insert `## REVIEW\n\n` before `## DONE` so column order
        # becomes BACKLOG -> TODO -> DOING -> REVIEW -> DONE. If
        # DONE is missing too (atypical), append REVIEW at the end
        # and let downstream operations handle the resulting board.
        done_marker = "## DONE"
        if done_marker in text:
            new_text = text.replace(done_marker,
                                    "## REVIEW\n\n" + done_marker, 1)
        else:
            new_text = text.rstrip() + "\n\n## REVIEW\n"

        atomic_write_text(str(kanban_path), new_text)
        return True


def parse_task_title_with_description(
    line: str,
) -> Optional[Tuple[str, Optional[str]]]:
    """Extract `(title, description_or_None)` from a markdown task line.

    D8: shared parser hoisted out of `kanbanger.tools` so both the
    MCP-tools code path AND the `sync_kanban.LocalBoard.parse` code path
    can use the same canonical helper. Without sharing, the two parsers
    drifted: tools.py stripped ` - description` from titles for dedup,
    sync_kanban kept the full post-checkbox text — so `* [ ] X` and
    `* [ ] X - extra` collapsed to one task on the MCP side but pushed
    as two separate items on the sync side.

    Description is whatever follows the FIRST ` - ` on the line; None
    if no separator. Returns None for non-task lines.
    """
    stripped = line.strip()
    if not stripped.startswith("*"):
        return None
    title = stripped[1:].strip()  # remove leading *
    if title.startswith("[ ]") or title.startswith("[x]"):
        title = title[3:].strip()  # remove checkbox
    if " - " in title:
        title_part, desc_part = title.split(" - ", 1)
        return title_part.strip(), desc_part.strip()
    return title, None


def atomic_write_text(
    path: str,
    content: str,
    encoding: str = "utf-8",
    newline: Optional[str] = None,
) -> None:
    """Write text to path atomically.

    Pattern: write to a sibling tempfile in the same directory, fsync the
    bytes to disk, then os.replace() onto the final name. os.replace is
    atomic at the filesystem level (Windows since Python 3.3, POSIX always)
    when both paths are on the same volume — placing the tempfile alongside
    the target guarantees that.

    `newline` is passed straight to open(): the default None keeps the
    historical behavior (\\n translated to the platform line separator);
    pass "" for no translation when the content's own line endings must be
    preserved byte-for-byte (e.g. the board-key mint into an existing
    board, ADR 0002).
    """
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".tmp.",
        dir=target_dir,
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, data: object, indent: int = 2) -> None:
    """Atomic-write JSON. Same guarantees as atomic_write_text."""
    atomic_write_text(path, json.dumps(data, indent=indent))


def _lock_path(workspace: str) -> str:
    return os.path.join(workspace, _LOCK_FILENAME)


def state_path(workspace: str) -> str:
    return os.path.join(workspace, _STATE_FILENAME)


@contextmanager
def kanban_lock(workspace: str) -> Iterator[None]:
    """Cross-process exclusive lock on <workspace>/.kanban.lock.

    Stdlib-only: msvcrt on Windows, fcntl on POSIX. Blocking acquire so
    contending mutators serialize rather than fail. The lock file is
    created if absent and left in place after release (presence is
    harmless and avoids race-on-creation between contenders).

    Used to serialize mutations in tools.py and StateManager.save() in
    sync_kanban.py so concurrent writers can't interleave a lost-update.
    Atomic writes (R1) protect against torn writes; the lock (R2)
    protects against lost updates.
    """
    os.makedirs(workspace, exist_ok=True)
    lock_path = _lock_path(workspace)
    # Open r+ if it already exists, else create. Keep the descriptor for the
    # platform lock primitive; no content is written.
    flags = os.O_RDWR | os.O_CREAT
    fd = os.open(lock_path, flags)
    try:
        if sys.platform == "win32":
            import msvcrt
            # Lock 1 byte at offset 0; LK_LOCK blocks until acquired.
            # msvcrt.locking requires a non-empty file region, so write a
            # placeholder byte if the file is empty.
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def read_state(workspace: str) -> dict:
    """Read .kanban.json if present; return default schema if absent.

    Schema matches sync_kanban.StateManager:
        {"repo_node_id": None, "project_id": None, "board_key": None,
         "tasks": {...}}
    """
    path = state_path(workspace)
    if not os.path.exists(path):
        return {
            "repo_node_id": None,
            "project_id": None,
            "board_key": None,
            "tasks": {},
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_state(workspace: str, state: dict) -> None:
    """Atomic-write state to .kanban.json under workspace."""
    atomic_write_json(state_path(workspace), state)


def state_exists(workspace: str) -> bool:
    return os.path.exists(state_path(workspace))


def upsert_task_placeholder(state: dict, title: str, status: str) -> None:
    """Add or update a task entry in state. Preserves item_id if already set."""
    tasks = state.setdefault("tasks", {})
    existing = tasks.get(title)
    if existing is None:
        tasks[title] = {"item_id": None, "status": status}
    else:
        existing["status"] = status


def remove_task_entry(state: dict, title: str) -> None:
    tasks = state.get("tasks", {})
    if title in tasks:
        del tasks[title]
