"""
Kanbanger MCP Tools

Callable functions that LLMs can use to interact with kanban boards.
"""

import os
import re
import sys
import json
import difflib
import subprocess
import threading
from pathlib import Path
from typing import Optional, Tuple
from mcp.server.fastmcp import FastMCP

from kanban_io import (
    atomic_write_text,
    discover_columns,
    kanban_lock,
    parse_task_title_with_description as _parse_task_title_with_description,
)

# S6: title-injection guard. Lines beginning with `* [` are kanban
# task entries and `## ` are column headers; allowing those patterns
# at the start of a stored title would let a malicious or careless
# add_task call create or shadow board structure.
_TASK_LINE_PREFIX_RE = re.compile(r"^\*\s+\[")
TITLE_MAX_LEN = 500

# E2: stable snake_case error codes for structured MCP tool error
# returns. Stable identifiers let clients branch on failure category
# without parsing free-text messages. New codes are append-only.
ERROR_KANBAN_NOT_FOUND = "kanban_not_found"
ERROR_INVALID_COLUMN = "invalid_column"
ERROR_COLUMN_NOT_IN_BOARD = "column_not_in_board"
ERROR_INVALID_TITLE = "invalid_title"
ERROR_TASK_NOT_FOUND = "task_not_found"
ERROR_READ_FAILED = "read_failed"
ERROR_WRITE_FAILED = "write_failed"
ERROR_MISSING_GITHUB_TOKEN = "missing_github_token"
ERROR_MISSING_GITHUB_REPO = "missing_github_repo"
ERROR_SYNC_SUBPROCESS_FAILED = "sync_subprocess_failed"
ERROR_SYNC_TIMEOUT = "sync_timeout"
ERROR_GITHUB_API = "github_api_error"
ERROR_PROJECT_NOT_FOUND = "project_not_found"
ERROR_CONFIGURATION = "configuration_error"
# Review-gate primitives use this for "task exists but is in the wrong
# column for the operation." Used by propose_done, approve_done, and
# reject_review.
ERROR_INVALID_STATE = "invalid_state"
# reject_review demands a non-empty reason — empty rejections would
# create a Rework task with no actionable context.
ERROR_MISSING_REASON = "missing_reason"
# Bundle 1b: move_task -> DONE is reserved for the REVIEW-gate happy path.
# Direct calls from any non-REVIEW column return this code; the canonical
# path is propose_done(title) followed by approve_done(title).
ERROR_GATE_VIOLATION = "gate_violation"


def _error(code: str, message: str, **context) -> str:
    """E2: render a structured MCP error return as JSON.

    Shape: {"success": False, "error_code": code, "message": message,
    "context": {...optional recovery-aiding fields}}. Only error paths
    use this shape; success returns keep their existing shape to
    minimise client churn.
    """
    payload = {
        "success": False,
        "error_code": code,
        "message": message,
    }
    if context:
        payload["context"] = context
    return json.dumps(payload, indent=2)


def _ok(**payload) -> str:
    """Render a structured MCP tool success return as JSON.

    Mirrors `_error`'s shape with `success: True`. Used by the
    review-gate primitives where a structured return (task, transition,
    optional reason) is more useful than a plain success string. The
    audit-era tools (add_task, move_task, delete_task) keep their
    plain-string success returns to avoid client churn; only the new
    coordination primitives use this richer shape.
    """
    return json.dumps({"success": True, **payload}, indent=2)


def _classify_sync_stderr(stderr: str) -> str:
    """E2: map sync_kanban subprocess stderr to a structured error_code.

    The subprocess raises typed exceptions from E1 and the CLI wrapper
    formats them as 'Error: <message>' on stderr. This mirror table
    avoids clients parsing free-text. Append-only: add a new branch
    for any new E1 exception class introduced in sync_kanban.
    """
    if not stderr:
        return ERROR_SYNC_SUBPROCESS_FAILED
    # Inspect each error line; first match wins.
    for line in stderr.splitlines():
        line = line.strip()
        if not line.startswith("Error:"):
            continue
        body = line[len("Error:"):].strip()
        if "GITHUB_TOKEN" in body:
            return ERROR_MISSING_GITHUB_TOKEN
        if "GITHUB_REPO" in body or "--repo" in body:
            return ERROR_MISSING_GITHUB_REPO
        if body.startswith("File not found"):
            return ERROR_KANBAN_NOT_FOUND
        if "GitHub API returned status" in body or body.startswith("GraphQL errors"):
            return ERROR_GITHUB_API
        if "No projects found" in body or "Project #" in body:
            return ERROR_PROJECT_NOT_FOUND
        if body.startswith("requests not installed"):
            return ERROR_CONFIGURATION
        if "No 'Status' field" in body:
            return ERROR_GITHUB_API
        return ERROR_CONFIGURATION  # generic Error: line we don't recognise
    return ERROR_SYNC_SUBPROCESS_FAILED


def _parse_task_title(line: str) -> Optional[str]:
    """Extract the title portion of a markdown task line, or None.

    Mirrors the parsing list_tasks already does: strip the leading bullet,
    optional `[ ]` / `[x]` checkbox, and any ` - description` suffix.
    Returns None for lines that aren't task entries.

    R5: this is the canonical title extraction used by move_task /
    delete_task for exact-equality comparison and near-match suggestions.
    D8: delegates to the shared `kanban_io.parse_task_title_with_description`
    so MCP-tools and sync_kanban use the same parser.
    """
    parsed = _parse_task_title_with_description(line)
    return parsed[0] if parsed is not None else None


def _format_rework_entries(title: str, reason: str) -> Tuple[str, str]:
    """Return the (done-line, rework-line) pair for a Pattern C reject.

    done-line:   re-emits the original task with [x] checkbox and a
                 REJECTED annotation + pointer to the Rework task.
                 Title is preserved verbatim so downstream parsers
                 still match the same key.
    rework-line: the new Rework task with the reason as its description
                 plus a pointer back to the original.

    Lines are returned WITHOUT trailing newlines so they slot directly
    into a `content.split("\\n")` list — `'\\n'.join(...)` reconstitutes
    the file. Caller has already validated that `reason` is non-empty.
    """
    done_line = (
        f"*   [x] {title} - REJECTED: {reason}; "
        f"rework: Rework: {title}"
    )
    rework_line = (
        f"*   [ ] Rework: {title} - "
        f"Reason: {reason}; Original task: {title}"
    )
    return done_line, rework_line


def _find_task_column(
    lines: list,
    title: str,
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Walk the board and locate the task by exact-title equality.

    Iterates `lines` looking for `## <column>` headers and task entries.
    For each task line, parses the title via `_parse_task_title` and
    compares for equality. Returns the first match in document order
    (BACKLOG -> TODO -> DOING -> REVIEW -> DONE per the canonical
    5-column schema).

    Args:
        lines: kanban file split on '\n' (typical caller pattern).
        title: exact title to locate.

    Returns:
        (column_name, line_index, line_text) if found.
        (None, None, None) if no match anywhere on the board.

    Behavior matches the inline walks in propose_done / approve_done /
    reject_review (Bundle 1). First match in document order wins -- on
    a board with duplicate titles across columns, the earlier column
    (in section order) is returned. Duplicate detection / dedup is a
    separate concern (D4); this helper does not warn or reject.
    """
    current_column: Optional[str] = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## "):
            current_column = s[3:].strip()
            continue
        if current_column is None:
            continue
        parsed = _parse_task_title(line)
        if parsed is not None and parsed == title:
            return current_column, i, line
    return None, None, None


def validate_task_title(title: str) -> Tuple[bool, Optional[str]]:
    """Return (ok, error_message) for a candidate task title.

    S6: pure validator (no normalization, no I/O) so callers can reuse
    it for E2's structured-error refactor and for future per-field
    validators. Rejects:
      - empty / whitespace-only titles
      - newlines (would split a task across markdown lines)
      - leading '## ' (would be parsed as a new column header)
      - leading '* [' patterns (would be parsed as a new task line)
      - titles over TITLE_MAX_LEN characters
    Caller is responsible for tab-to-space normalization before
    validation if desired.
    """
    if not title or not title.strip():
        return False, "title is empty"
    if "\n" in title:
        return False, "title contains a newline character"
    if title.startswith("## "):
        return False, (
            "title starts with '## ', which would be parsed as a new "
            "column header and corrupt the board"
        )
    if _TASK_LINE_PREFIX_RE.match(title):
        return False, (
            "title starts with '* [' (markdown task syntax), which "
            "would be parsed as a new task entry"
        )
    if len(title) > TITLE_MAX_LEN:
        return False, (
            f"title exceeds {TITLE_MAX_LEN} character limit "
            f"({len(title)} chars)"
        )
    return True, None


def get_workspace() -> str:
    """Get the current workspace directory.

    S2: returns an absolute canonical path. `Path.resolve()` collapses
    `..` segments and symlinks so a `KANBANGER_WORKSPACE=../foo` env
    var resolves predictably regardless of the process cwd.
    """
    return str(Path(os.getenv("KANBANGER_WORKSPACE", os.getcwd())).resolve())


def get_kanban_path() -> str:
    """Get the path to the kanban board file."""
    return os.path.join(get_workspace(), "_kanban.md")


def register_tools(server: FastMCP):
    """Register all tools with the MCP server."""
    
    @server.tool()
    def add_task(title: str, column: str = "TODO", description: str = "") -> str:
        """
        Add a new task to the kanban board.

        Args:
            title: Task title (required, should be concise and action-oriented)
            column: Target column - any column present in the board's
                ``## section`` headers (default: TODO). The set is whatever
                the board declares; common values are BACKLOG, TODO, DOING,
                REVIEW, DONE.
            description: Optional task description for additional context

        Returns:
            Success message or error description

        Example:
            add_task("Implement user authentication", "TODO", "Add JWT-based auth system")
        """
        kanban_path = get_kanban_path()

        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        # column-config: validate against the board's actual columns,
        # not a hardcoded whitelist. A board with REVIEW (or any custom
        # column) is fully operable via the MCP tools; the parser was
        # already permissive here, this aligns the validator with it.
        valid_columns = discover_columns(get_workspace())
        if column not in valid_columns:
            return _error(
                ERROR_INVALID_COLUMN,
                f"Invalid column '{column}'. Must be one of: {', '.join(valid_columns)}",
                column=column,
                valid_columns=valid_columns,
            )

        # S6: normalize tabs to spaces before validation so a tab-only
        # title isn't accepted as 'non-empty' but also isn't rejected
        # for containing a tab. Validation rejects empty, markdown-
        # injecting, and over-long titles.
        title = title.replace("\t", " ")
        ok, err = validate_task_title(title)
        if not ok:
            return _error(ERROR_INVALID_TITLE, err)

        # R2: serialize mutations cross-process so concurrent writers can't lost-update.
        with kanban_lock(get_workspace()):
            # Read current board
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                return _error(
                    ERROR_READ_FAILED,
                    f"Error reading kanban board: {str(e)}",
                )

            # Find column section
            column_header = f"## {column}"
            if column_header not in content:
                return _error(
                    ERROR_COLUMN_NOT_IN_BOARD,
                    f"Column '{column}' not found in kanban board",
                    column=column,
                )

            # Build task line
            task_line = f"*   [ ] {title}"
            if description:
                task_line += f" - {description}"

            # Bug A: canonical-rebuild the target column. Append (not prepend),
            # always pad header -> blank -> tasks -> blank. Existing tasks are
            # preserved in order; stray blank lines inside the section are
            # normalized away.
            lines = content.split('\n')
            col_start_idx = next(
                (i for i, line in enumerate(lines) if line.strip() == column_header),
                None,
            )
            if col_start_idx is None:
                return _error(
                    ERROR_COLUMN_NOT_IN_BOARD,
                    f"Column '{column}' not found in kanban board",
                    column=column,
                )
            col_end_idx = next(
                (i for i in range(col_start_idx + 1, len(lines))
                 if lines[i].strip().startswith("## ")),
                len(lines),
            )
            existing_tasks = [
                ln for ln in lines[col_start_idx + 1:col_end_idx]
                if ln.strip().startswith(("*", "-"))
            ]
            existing_tasks.append(task_line)
            new_section = [""] + existing_tasks + [""]
            lines = lines[:col_start_idx + 1] + new_section + lines[col_end_idx:]

            # R1: atomic markdown write (temp + fsync + os.replace).
            try:
                atomic_write_text(kanban_path, '\n'.join(lines))
            except Exception as e:
                return _error(
                    ERROR_WRITE_FAILED,
                    f"Error writing kanban board: {str(e)}",
                )

        return f"Successfully added task '{title}' to {column}"
    
    @server.tool()
    def move_task(title: str, from_column: str, to_column: str) -> str:
        """
        Move a task from one column to another.

        Args:
            title: Exact title of the task to move
            from_column: Source column — any column present in the board
            to_column: Destination column — any column present in the board

        Returns:
            Success message or error description

        Example:
            move_task("Implement user authentication", "TODO", "DOING")

        Note:
            - Task title must match exactly
            - Moving to DONE automatically marks task as completed [x]
            - Moving from DONE back unchecks the task [ ]
        """
        kanban_path = get_kanban_path()

        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        # column-config: validate both columns against the board's
        # actual columns rather than a hardcoded whitelist.
        valid_columns = discover_columns(get_workspace())
        if from_column not in valid_columns:
            return _error(
                ERROR_INVALID_COLUMN,
                f"Invalid from_column '{from_column}'",
                column=from_column,
                valid_columns=valid_columns,
            )
        if to_column not in valid_columns:
            return _error(
                ERROR_INVALID_COLUMN,
                f"Invalid to_column '{to_column}'",
                column=to_column,
                valid_columns=valid_columns,
            )

        # Bundle 1b: REVIEW-gate enforcement. The only legitimate path to
        # DONE is REVIEW -> DONE (via approve_done or reject_review's
        # Pattern C). Any other from_column -> DONE transition bypasses
        # the gate and is rejected with a structured error pointing the
        # caller at the canonical primitives.
        if to_column == "DONE" and from_column != "REVIEW":
            # Best-effort state peek using _find_task_column (D9 helper) so
            # the error context can name the actual current column rather
            # than only the column the caller claimed. Outside the lock --
            # this is a diagnostic-only read; the gate-violation is
            # determined by the (from_column, to_column) pair, not by
            # board state, so a racy read doesn't affect correctness.
            actual_column = None
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    _peek_content = f.read()
                _peek_lines = _peek_content.split('\n')
                actual_column, _, _ = _find_task_column(_peek_lines, title)
            except Exception:
                actual_column = None
            return _error(
                ERROR_GATE_VIOLATION,
                f"Direct move_task to DONE from {from_column} bypasses the "
                f"REVIEW gate. The canonical path is propose_done(title) "
                f"to move DOING -> REVIEW, then approve_done(title) to "
                f"land in DONE. Use reject_review(title, reason) if the "
                f"work needs rework.",
                title=title,
                from_column=from_column,
                to_column=to_column,
                actual_column=actual_column,
                canonical_path=["propose_done", "approve_done"],
            )

        # R2: serialize mutations cross-process so concurrent writers can't lost-update.
        with kanban_lock(get_workspace()):
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                return _error(
                    ERROR_READ_FAILED,
                    f"Error reading kanban board: {str(e)}",
                )

            lines = content.split('\n')

            # R5: find the task in from_column by exact title equality;
            # collect titles along the way so a miss can offer near-match hints.
            task_line = None
            task_index = None
            in_from_column = False
            seen_titles: list = []

            for i, line in enumerate(lines):
                s = line.strip()
                if s == f"## {from_column}":
                    in_from_column = True
                    continue
                if s.startswith("## ") and in_from_column:
                    break  # Entered next column

                if in_from_column:
                    parsed = _parse_task_title(line)
                    if parsed is not None:
                        seen_titles.append(parsed)
                        if parsed == title:
                            task_line = line
                            task_index = i
                            break

            if task_line is None:
                suggestions = difflib.get_close_matches(title, seen_titles, n=3, cutoff=0.6)
                if suggestions:
                    hint = ", ".join(repr(s) for s in suggestions)
                    return _error(
                        ERROR_TASK_NOT_FOUND,
                        f"Task '{title}' not found in {from_column}. "
                        f"Did you mean: {hint}?",
                        title=title,
                        column=from_column,
                        available_titles=seen_titles,
                        suggestions=suggestions,
                    )
                return _error(
                    ERROR_TASK_NOT_FOUND,
                    f"Task '{title}' not found in {from_column}",
                    title=title,
                    column=from_column,
                    available_titles=seen_titles,
                )

            # Remove from source column
            lines.pop(task_index)

            # Update checkbox based on destination
            if to_column == "DONE":
                task_line = task_line.replace("[ ]", "[x]")
            else:
                task_line = task_line.replace("[x]", "[ ]")

            # Find destination column and insert
            for i, line in enumerate(lines):
                if line.strip() == f"## {to_column}":
                    lines.insert(i + 1, task_line)
                    break

            # R1: atomic markdown write (temp + fsync + os.replace).
            try:
                atomic_write_text(kanban_path, '\n'.join(lines))
            except Exception as e:
                return _error(
                    ERROR_WRITE_FAILED,
                    f"Error writing kanban board: {str(e)}",
                )

        return f"Successfully moved '{title}' from {from_column} to {to_column}"
    
    @server.tool()
    def delete_task(title: str, column: str) -> str:
        """
        Delete a task from the kanban board.

        Args:
            title: Exact title of the task to delete
            column: Column containing the task — any column present in the board

        Returns:
            Success message or error description

        Example:
            delete_task("Old deprecated feature", "BACKLOG")

        Warning:
            This permanently removes the task from the local markdown file.
            Consider moving to DONE instead of deleting for record keeping.
        """
        kanban_path = get_kanban_path()

        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        # column-config: fail fast with a structured invalid_column
        # error if the caller asks for a column not on the board, rather
        # than silently returning task_not_found from the search loop.
        valid_columns = discover_columns(get_workspace())
        if column not in valid_columns:
            return _error(
                ERROR_INVALID_COLUMN,
                f"Invalid column '{column}'",
                column=column,
                valid_columns=valid_columns,
            )

        # R2: serialize mutations cross-process so concurrent writers can't lost-update.
        with kanban_lock(get_workspace()):
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                return _error(
                    ERROR_READ_FAILED,
                    f"Error reading kanban board: {str(e)}",
                )

            lines = content.split('\n')

            # R5: find by exact title equality; collect titles for near-match
            # hints if the lookup misses.
            task_index = None
            in_column = False
            seen_titles: list = []

            for i, line in enumerate(lines):
                s = line.strip()
                if s == f"## {column}":
                    in_column = True
                    continue
                if s.startswith("## ") and in_column:
                    break

                if in_column:
                    parsed = _parse_task_title(line)
                    if parsed is not None:
                        seen_titles.append(parsed)
                        if parsed == title:
                            task_index = i
                            break

            if task_index is None:
                suggestions = difflib.get_close_matches(title, seen_titles, n=3, cutoff=0.6)
                if suggestions:
                    hint = ", ".join(repr(s) for s in suggestions)
                    return _error(
                        ERROR_TASK_NOT_FOUND,
                        f"Task '{title}' not found in {column}. "
                        f"Did you mean: {hint}?",
                        title=title,
                        column=column,
                        available_titles=seen_titles,
                        suggestions=suggestions,
                    )
                return _error(
                    ERROR_TASK_NOT_FOUND,
                    f"Task '{title}' not found in {column}",
                    title=title,
                    column=column,
                    available_titles=seen_titles,
                )

            lines.pop(task_index)
            # Bug A round-trip: compact any consecutive blank lines created
            # at the deletion point so add_task -> delete_task is a no-op
            # on the markdown shape.
            while (
                0 < task_index < len(lines)
                and lines[task_index].strip() == ""
                and lines[task_index - 1].strip() == ""
            ):
                lines.pop(task_index)

            # R1: atomic markdown write (temp + fsync + os.replace).
            try:
                atomic_write_text(kanban_path, '\n'.join(lines))
            except Exception as e:
                return _error(
                    ERROR_WRITE_FAILED,
                    f"Error writing kanban board: {str(e)}",
                )

        return f"Successfully deleted task '{title}' from {column}"
    
    @server.tool()
    def list_tasks(column: Optional[str] = None, verbose: bool = False) -> str:
        """
        List tasks from the kanban board.

        Args:
            column: Optional column filter (BACKLOG, TODO, DOING, DONE).
                   If not provided, returns tasks from all columns.
            verbose: If True, return [{title, description}] per task instead
                   of titles-only. Description is the text after ` - ` on the
                   task line, or null if no separator. Default False keeps
                   the existing titles-only shape for back-compat.

        Returns:
            JSON string with task information

        Example:
            list_tasks()                        # All tasks, titles only
            list_tasks("DOING")                 # Filter; titles only
            list_tasks(verbose=True)            # All tasks with descriptions

        Output format (default):
            {"BACKLOG": ["Task 1"], "TODO": ["Task 3"], ...}

        Output format (verbose=True):
            {"BACKLOG": [{"title": "Task 1", "description": "details"}], ...}
        """
        kanban_path = get_kanban_path()

        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return _error(
                ERROR_READ_FAILED,
                f"Error reading kanban board: {str(e)}",
            )

        lines = content.split('\n')
        tasks: dict = {}
        # D4: per-column set of titles already added on this parse,
        # used to detect and dedupe same-title rows. Audit recommends
        # dedupe over keep-both because the sync path otherwise creates
        # duplicate GitHub items. First occurrence wins.
        seen_per_column: dict = {}
        current_column = None

        for line in lines:
            if line.strip().startswith("## "):
                current_column = line.strip()[3:].strip()
                tasks.setdefault(current_column, [])
                seen_per_column.setdefault(current_column, set())
            elif current_column:
                parsed = _parse_task_title_with_description(line)
                if parsed is not None:
                    title, description = parsed
                    if title in seen_per_column[current_column]:
                        print(
                            f"Warning: duplicate task title in column "
                            f"'{current_column}': '{title}'. Keeping first "
                            f"occurrence; dropping subsequent duplicate.",
                            file=sys.stderr,
                        )
                        continue
                    seen_per_column[current_column].add(title)
                    if verbose:
                        tasks[current_column].append(
                            {"title": title, "description": description}
                        )
                    else:
                        tasks[current_column].append(title)

        # Filter by column if specified. column-config: validate
        # against the columns actually present on the board (the
        # parser's source of truth) rather than silently returning an
        # empty list for typos / made-up names.
        if column:
            if column in tasks:
                return json.dumps({column: tasks[column]}, indent=2)
            return _error(
                ERROR_INVALID_COLUMN,
                f"Invalid column '{column}'",
                column=column,
                valid_columns=list(tasks.keys()),
            )

        return json.dumps(tasks, indent=2)
    
    @server.tool()
    def sync_to_github(dry_run: bool = False) -> str:
        """
        Sync the kanban board to GitHub Projects V2.
        
        Args:
            dry_run: If True, shows what would be synced without making changes (default: False)
        
        Returns:
            Sync results or error message
        
        Example:
            sync_to_github(dry_run=True)  # Preview changes
            sync_to_github()  # Actually sync
        
        Requirements:
            - GITHUB_TOKEN environment variable must be set
            - GITHUB_REPO environment variable must be set
            - GITHUB_PROJECT_NUMBER environment variable (optional, will auto-detect)
        
        Note:
            This creates/updates/archives draft issues in the GitHub Project.
            Local _kanban.md is the source of truth.
        """
        workspace = get_workspace()
        kanban_path = get_kanban_path()

        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        # Check for required environment variables
        if not os.getenv("GITHUB_TOKEN"):
            return _error(
                ERROR_MISSING_GITHUB_TOKEN,
                "GITHUB_TOKEN environment variable not set",
            )
        if not os.getenv("GITHUB_REPO"):
            return _error(
                ERROR_MISSING_GITHUB_REPO,
                "GITHUB_REPO environment variable not set",
            )
        
        TIMEOUT_SEC = int(os.getenv("KANBANGER_SYNC_TIMEOUT_SEC", "60"))

        # Audit R4: use sys.executable instead of bare "python" so the
        # subprocess always runs under the same interpreter as the MCP server.
        cmd = [sys.executable, "-m", "sync_kanban", kanban_path]
        if dry_run:
            cmd.append("--dry-run")

        def _drain(stream, sink):
            try:
                for chunk in iter(stream.readline, ''):
                    sink.append(chunk)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,   # R11: do NOT inherit MCP server's stdin pipe
            cwd=workspace,
            text=True,
            encoding='utf-8',
            errors='replace',           # R11: tolerate any byte the child writes
        )
        t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_chunks), daemon=True)
        t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_chunks), daemon=True)
        t_out.start()
        t_err.start()
        try:
            rc = proc.wait(timeout=TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            return _error(
                ERROR_SYNC_TIMEOUT,
                f"sync_to_github timed out after {TIMEOUT_SEC}s "
                f"(set KANBANGER_SYNC_TIMEOUT_SEC to override; check "
                f"GITHUB_REPO env var and network reachability)",
                timeout_sec=TIMEOUT_SEC,
            )
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        stdout = ''.join(stdout_chunks)
        stderr = ''.join(stderr_chunks)

        if rc == 0:
            mode = "preview" if dry_run else "complete"
            return f"Sync {mode}:\n\n{stdout}"

        # E2: subprocess failed. Translate the E1-prefixed stderr
        # ("Error: <msg>") back to a structured code so callers don't
        # parse free-text. Falls back to ERROR_SYNC_SUBPROCESS_FAILED
        # for unrecognised messages; full stderr always in context.
        return _error(
            _classify_sync_stderr(stderr),
            f"sync_to_github subprocess exited with code {rc}",
            return_code=rc,
            stderr=stderr,
            stdout=stdout,
        )
    
    @server.tool()
    def get_sync_status() -> str:
        """
        Get the current GitHub sync status.
        
        Returns:
            JSON string with sync status information
        
        Output format:
            {
                "synced_tasks": 15,
                "state_file": "/path/to/.kanban.json",
                "last_sync": "2026-01-21T02:30:00Z"  (if available)
            }
        
        Note:
            This reads the .kanban.json state file which tracks
            the mapping between local tasks and GitHub Project items.
        """
        workspace = get_workspace()
        state_path = os.path.join(workspace, ".kanban.json")
        
        if not os.path.exists(state_path):
            return json.dumps({
                "synced_tasks": 0,
                "state_file": "not found",
                "message": "No sync state found. Run sync_to_github() first."
            }, indent=2)
        
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # D6: read state["tasks"] to match StateManager writer convention
            # (sync_kanban.py:91,116,123). The legacy "items" key was never set,
            # so this previously reported zero synced tasks regardless of state.
            return json.dumps({
                "synced_tasks": len(state.get("tasks", {})),
                "state_file": state_path,
                "github_items": list(state.get("tasks", {}).keys())
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error reading sync state: {str(e)}"
            }, indent=2)

    @server.tool()
    def propose_done(title: str) -> str:
        """
        Propose a task as done, moving it from DOING to REVIEW.

        Args:
            title: Exact title of the task currently in DOING.

        Returns:
            JSON string. On success:
                {"success": true,
                 "task": {"title": str, "from_column": "DOING",
                          "to_column": "REVIEW"}}
            On error: {"success": false, "error_code": str,
                       "message": str, "context": {...}}

        Example:
            propose_done("Implement user authentication")

        Workflow:
            Workers call this when finishing a task. The board's human
            or PM reviewer then approves with approve_done(title) or
            sends back with reject_review(title, reason).

            Do NOT call move_task(title, "DOING", "DONE") directly. The
            direct path bypasses the review gate; approve_done is the
            only path that lands work in DONE.

        Errors:
            - kanban_not_found: _kanban.md missing in workspace
            - task_not_found: title doesn't match any task
            - invalid_state: task exists but is not in DOING (current
              column reported in context)
            - write_failed: atomic write failed
        """
        kanban_path = get_kanban_path()
        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        with kanban_lock(get_workspace()):
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                return _error(
                    ERROR_READ_FAILED,
                    f"Error reading kanban board: {str(e)}",
                )

            lines = content.split('\n')

            # D9: hoisted state-lookup helper (Bundle 1b item 1).
            found_in_column, found_index, found_line = _find_task_column(lines, title)

            if found_in_column is None:
                return _error(
                    ERROR_TASK_NOT_FOUND,
                    f"Task '{title}' not found in any column",
                    title=title,
                )
            if found_in_column != "DOING":
                return _error(
                    ERROR_INVALID_STATE,
                    f"Task '{title}' is in {found_in_column}, not DOING. "
                    f"propose_done moves DOING -> REVIEW only.",
                    title=title,
                    current_column=found_in_column,
                    expected_column="DOING",
                )

            # Move from DOING to REVIEW (insert immediately after the
            # `## REVIEW` header). Item 1.5's auto-migration guarantees
            # REVIEW is on the board.
            lines.pop(found_index)
            for i, line in enumerate(lines):
                if line.strip() == "## REVIEW":
                    lines.insert(i + 1, found_line)
                    break

            try:
                atomic_write_text(kanban_path, '\n'.join(lines))
            except Exception as e:
                return _error(
                    ERROR_WRITE_FAILED,
                    f"Error writing kanban board: {str(e)}",
                )

        return _ok(task={"title": title, "from_column": "DOING",
                         "to_column": "REVIEW"})

    @server.tool()
    def approve_done(title: str) -> str:
        """
        Approve a task in REVIEW, moving it to DONE.

        Args:
            title: Exact title of the task currently in REVIEW.

        Returns:
            JSON string. On success:
                {"success": true,
                 "task": {"title": str, "from_column": "REVIEW",
                          "to_column": "DONE"}}
            On error: {"success": false, "error_code": str,
                       "message": str, "context": {...}}

        Example:
            approve_done("Implement user authentication")

        Workflow:
            This is the gate-holder's side of the REVIEW primitive. The
            worker proposed completion via propose_done(title); the
            reviewer (human or PM) confirms the work is acceptable and
            approves with this tool.

            If the work needs changes, use reject_review(title, reason)
            instead.

        Errors:
            - kanban_not_found: _kanban.md missing in workspace
            - task_not_found: title doesn't match any task
            - invalid_state: task exists but is not in REVIEW
            - write_failed: atomic write failed
        """
        kanban_path = get_kanban_path()
        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        with kanban_lock(get_workspace()):
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                return _error(
                    ERROR_READ_FAILED,
                    f"Error reading kanban board: {str(e)}",
                )

            lines = content.split('\n')

            # D9: hoisted state-lookup helper (Bundle 1b item 1).
            found_in_column, found_index, found_line = _find_task_column(lines, title)

            if found_in_column is None:
                return _error(
                    ERROR_TASK_NOT_FOUND,
                    f"Task '{title}' not found in any column",
                    title=title,
                )
            if found_in_column != "REVIEW":
                return _error(
                    ERROR_INVALID_STATE,
                    f"Task '{title}' is in {found_in_column}, not REVIEW. "
                    f"approve_done moves REVIEW -> DONE only.",
                    title=title,
                    current_column=found_in_column,
                    expected_column="REVIEW",
                )

            # Flip checkbox to [x] (move_task convention for DONE) and
            # insert after the `## DONE` header.
            lines.pop(found_index)
            done_line = found_line.replace("[ ]", "[x]")
            for i, line in enumerate(lines):
                if line.strip() == "## DONE":
                    lines.insert(i + 1, done_line)
                    break

            try:
                atomic_write_text(kanban_path, '\n'.join(lines))
            except Exception as e:
                return _error(
                    ERROR_WRITE_FAILED,
                    f"Error writing kanban board: {str(e)}",
                )

        return _ok(task={"title": title, "from_column": "REVIEW",
                         "to_column": "DONE"})

    @server.tool()
    def reject_review(title: str, reason: str) -> str:
        """
        Reject work in REVIEW, recording the rejection and creating a new
        Rework task.

        Args:
            title: Exact title of the task currently in REVIEW.
            reason: Required human-readable reason for the rejection.
                Cannot be None or empty/whitespace; the reason is the
                context the Rework task carries forward.

        Returns:
            JSON string. On success:
                {"success": true,
                 "original": {"title": str, "from_column": "REVIEW",
                              "to_column": "DONE",
                              "annotation": "REJECTED: <reason>; rework: Rework: <title>"},
                 "rework":   {"title": "Rework: <title>", "column": "TODO",
                              "reason": str}}
            On error: {"success": false, "error_code": str, "message": str,
                       "context": {...}}

        Example:
            reject_review("Implement auth", reason="Missing rate limiting")

        Workflow (Pattern C - two-entry rejection):
            This is the gate-holder's pushback primitive. When the work
            proposed via propose_done needs changes, the reviewer rejects
            with a reason. The original task becomes a DONE record of
            "this shipped but was rejected at review" (with the reason
            annotated inline), and a NEW task "Rework: <original>" lands
            in TODO with the reason as its description and a link back
            to the original. The worker picks up the Rework task,
            addresses the feedback, and calls propose_done on the Rework
            task when ready for re-review.

        Errors:
            - kanban_not_found: _kanban.md missing in workspace
            - missing_reason: reason was None, empty, or whitespace-only
            - task_not_found: title doesn't match any task
            - invalid_state: task exists but is not in REVIEW (current
              column reported in context)
            - write_failed: atomic write failed
        """
        kanban_path = get_kanban_path()
        if not os.path.exists(kanban_path):
            return _error(
                ERROR_KANBAN_NOT_FOUND,
                f"Kanban board not found at {kanban_path}",
                kanban_path=kanban_path,
            )

        # Reason validation BEFORE board I/O — caller error, no lock needed.
        if reason is None or not str(reason).strip():
            return _error(
                ERROR_MISSING_REASON,
                "reject_review requires a non-empty reason. A rejection "
                "without context would create a Rework task with no "
                "actionable description.",
                title=title,
            )

        with kanban_lock(get_workspace()):
            try:
                with open(kanban_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                return _error(
                    ERROR_READ_FAILED,
                    f"Error reading kanban board: {str(e)}",
                )

            lines = content.split('\n')

            # D9: hoisted state-lookup helper (Bundle 1b item 1). reject_review
            # discards the line text -- _format_rework_entries generates fresh
            # lines from the title rather than reusing the source line.
            found_in_column, found_index, _ = _find_task_column(lines, title)

            if found_in_column is None:
                return _error(
                    ERROR_TASK_NOT_FOUND,
                    f"Task '{title}' not found in any column",
                    title=title,
                )
            if found_in_column != "REVIEW":
                return _error(
                    ERROR_INVALID_STATE,
                    f"Task '{title}' is in {found_in_column}, not REVIEW. "
                    f"reject_review moves REVIEW -> DONE (with REJECTED "
                    f"annotation) only.",
                    title=title,
                    current_column=found_in_column,
                    expected_column="REVIEW",
                )

            # S7: Re-validate the Rework title against the same rules add_task
            # applies. Without this, an original title near the 500-char cap
            # can produce a Rework title that exceeds the cap (or otherwise
            # violates the title-validation rules) once the "Rework: " prefix
            # is prepended. Defense-in-depth against future rule changes too.
            # Atomic property preserved -- no lines.pop / lines.insert has run
            # yet, so the board is untouched and the original stays in REVIEW.
            rework_title = f"Rework: {title}"
            ok, err = validate_task_title(rework_title)
            if not ok:
                return _error(
                    ERROR_INVALID_TITLE,
                    f"Rework task title would be invalid: {err}. The original "
                    f"title is too long (or contains a forbidden pattern) for "
                    f"the 'Rework: ' prefix to be appended. Original title "
                    f"length: {len(title)}; rework title length: "
                    f"{len(rework_title)}; cap: {TITLE_MAX_LEN}.",
                    title=title,
                    rework_title=rework_title,
                    original_title_length=len(title),
                    rework_title_length=len(rework_title),
                    max_length=TITLE_MAX_LEN,
                    underlying_error=err,
                )

            # Pattern C: two-entry atomic move.
            # 1. Remove the original line from REVIEW.
            # 2. Insert the REJECTED-annotated line at top of DONE.
            # 3. Insert the new Rework line at top of TODO.
            # All inside one lock + one atomic_write_text so the kanban
            # is never in a half-rejected state.
            done_line, rework_line = _format_rework_entries(title, reason)
            lines.pop(found_index)

            # Insert into DONE first. Since DONE comes after TODO in
            # canonical column order, inserting into DONE first does
            # not perturb the TODO header index for the second insert.
            for i, line in enumerate(lines):
                if line.strip() == "## DONE":
                    lines.insert(i + 1, done_line)
                    break
            for i, line in enumerate(lines):
                if line.strip() == "## TODO":
                    lines.insert(i + 1, rework_line)
                    break

            try:
                atomic_write_text(kanban_path, '\n'.join(lines))
            except Exception as e:
                return _error(
                    ERROR_WRITE_FAILED,
                    f"Error writing kanban board: {str(e)}",
                )

        annotation = f"REJECTED: {reason}; rework: Rework: {title}"
        return _ok(
            original={
                "title": title,
                "from_column": "REVIEW",
                "to_column": "DONE",
                "annotation": annotation,
            },
            rework={
                "title": f"Rework: {title}",
                "column": "TODO",
                "reason": reason,
            },
        )
