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
from mcp_use.server import MCPServer

from kanban_io import atomic_write_text, kanban_lock

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
    """
    parsed = _parse_task_title_with_description(line)
    return parsed[0] if parsed is not None else None


def _parse_task_title_with_description(
    line: str,
) -> Optional[Tuple[str, Optional[str]]]:
    """Extract `(title, description_or_None)` from a markdown task line.

    D3: shared parser used by both `_parse_task_title` (titles only,
    R5 path) and `list_tasks(verbose=True)` (titles + descriptions).
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


def register_tools(server: MCPServer):
    """Register all tools with the MCP server."""
    
    @server.tool()
    def add_task(title: str, column: str = "TODO", description: str = "") -> str:
        """
        Add a new task to the kanban board.
        
        Args:
            title: Task title (required, should be concise and action-oriented)
            column: Target column - must be one of: BACKLOG, TODO, DOING, DONE (default: TODO)
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

        # Validate column
        valid_columns = ["BACKLOG", "TODO", "DOING", "DONE"]
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

            # Insert after column header
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.strip() == column_header:
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

        return f"Successfully added task '{title}' to {column}"
    
    @server.tool()
    def move_task(title: str, from_column: str, to_column: str) -> str:
        """
        Move a task from one column to another.
        
        Args:
            title: Exact title of the task to move
            from_column: Source column (BACKLOG, TODO, DOING, DONE)
            to_column: Destination column (BACKLOG, TODO, DOING, DONE)
        
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

        # Validate columns
        valid_columns = ["BACKLOG", "TODO", "DOING", "DONE"]
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
            column: Column containing the task (BACKLOG, TODO, DOING, DONE)
        
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

        # Filter by column if specified
        if column:
            if column in tasks:
                return json.dumps({column: tasks[column]}, indent=2)
            else:
                return json.dumps({column: []}, indent=2)

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
