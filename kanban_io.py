"""
Kanbanger MCP I/O helpers — atomic file writes and cross-process locking.

Audit-driven foundation for tools.py mutations:
- R1: atomic_write_text / atomic_write_json (temp + fsync + os.replace).
- R2: kanban_lock (msvcrt on Windows, fcntl on POSIX) — stdlib only.
- D1: state-file read/update/remove helpers used under the same lock as
  markdown writes so the kanban + sidecar pair stay coherent across crashes.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple


_LOCK_FILENAME = ".kanban.lock"
_STATE_FILENAME = ".kanban.json"


def parse_task_title_with_description(
    line: str,
) -> Optional[Tuple[str, Optional[str]]]:
    """Extract `(title, description_or_None)` from a markdown task line.

    D8: shared parser hoisted out of `kanbanger_mcp.tools` so both the
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


def atomic_write_text(path: str, content: str, encoding: str = "utf-8") -> None:
    """Write text to path atomically.

    Pattern: write to a sibling tempfile in the same directory, fsync the
    bytes to disk, then os.replace() onto the final name. os.replace is
    atomic at the filesystem level (Windows since Python 3.3, POSIX always)
    when both paths are on the same volume — placing the tempfile alongside
    the target guarantees that.
    """
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".tmp.",
        dir=target_dir,
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
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
        {"repo_node_id": None, "project_id": None, "tasks": {...}}
    """
    path = state_path(workspace)
    if not os.path.exists(path):
        return {"repo_node_id": None, "project_id": None, "tasks": {}}
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
