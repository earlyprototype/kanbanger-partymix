"""
Kanbanger MCP Resources

Read-only data that LLMs can access for context and awareness.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from kanban_io import discover_columns


# O3 reachability cache: maps token-suffix (last 6 chars; never the
# full token) to (expiry_timestamp, reachable_bool). Module-level so
# repeated `kanban://config` calls within the TTL don't hammer the
# GraphQL endpoint. Keying on suffix lets a token rotation invalidate
# the cache naturally (different suffix → different key).
_REACHABLE_CACHE: dict = {}
_REACHABLE_TTL_SEC = 30.0
_REACHABLE_TIMEOUT_SEC = 5.0
_GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
_REACHABLE_QUERY = '{"query":"{ viewer { login } }"}'


def _check_github_reachable(token: str) -> bool:
    """Single `viewer { login }` GraphQL ping with 30s memoization.

    O3 reachability sub-item: the env-resolution half of O3 (commit
    `ddfe741`) reports whether a token is configured; this helper
    answers the harder question of whether the configured token can
    actually reach GitHub. Returns True on a successful viewer query
    (HTTP 200 + non-null `data.viewer`); False on auth failure,
    network failure, timeout, or any non-200. Caller must handle
    `token is None / empty` itself — we don't ping with an empty
    token.

    Cache keyed by the last 6 chars of the token (never logged)
    keeps repeated `kanban://config` calls cheap; TTL is intentionally
    short (30s) so a freshly-rotated token reflects within the same
    interaction. The 5s connect/read timeout keeps a flaky network
    from blocking resource calls.
    """
    cache_key = token[-6:] if len(token) >= 6 else token
    now = time.time()
    cached = _REACHABLE_CACHE.get(cache_key)
    if cached is not None and cached[0] > now:
        return cached[1]

    req = urllib.request.Request(
        _GITHUB_GRAPHQL_URL,
        data=_REACHABLE_QUERY.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "kanbanger-mcp",
        },
        method="POST",
    )
    reachable = False
    try:
        with urllib.request.urlopen(req, timeout=_REACHABLE_TIMEOUT_SEC) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                viewer = payload.get("data", {}).get("viewer") if isinstance(payload, dict) else None
                reachable = viewer is not None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(
            f"Warning: github_reachable ping failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        reachable = False

    _REACHABLE_CACHE[cache_key] = (now + _REACHABLE_TTL_SEC, reachable)
    return reachable


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


def register_resources(server: FastMCP):
    """Register all resources with the MCP server."""
    
    @server.resource(
        "kanban://current-board",
        name="current_kanban_board",
        title="Current Kanban Board",
        description="Real-time view of the _kanban.md file in the current workspace",
        mime_type="text/markdown"
    )
    def get_current_board() -> str:
        """Return the current kanban board content."""
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return f"# No Kanban Board Found\n\nNo _kanban.md file exists in workspace: {get_workspace()}\n\nCreate one with:\n```\n# Project Kanban\n\n## BACKLOG\n\n## TODO\n\n## DOING\n\n## REVIEW\n\n## DONE\n```"
        
        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"# Error Reading Kanban Board\n\nError: {str(e)}"
    
    @server.resource(
        "kanban://stats",
        name="kanban_statistics",
        title="Kanban Board Statistics",
        description="Task counts and distribution across columns",
        mime_type="application/json"
    )
    def get_kanban_stats() -> str:
        """Return JSON statistics about the current board."""
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return json.dumps({
                "error": "Kanban board not found",
                "workspace": get_workspace()
            }, indent=2)
        
        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return json.dumps({"error": f"Error reading board: {str(e)}"}, indent=2)
        
        # D5: discover columns dynamically from the markdown rather
        # than the previous hardcoded {BACKLOG, TODO, DOING, DONE}
        # initializer. column-config: column discovery is hoisted to
        # `kanban_io.discover_columns` so this resource and the
        # validation paths in `tools.py` share a single source of
        # truth. Convenience aliases (in_progress / completed /
        # pending) stay for back-compat callers but tolerate missing
        # columns via .get(..., 0).
        columns = discover_columns(get_workspace())
        stats: dict = {col: 0 for col in columns}
        column_set = set(columns)
        current_column = None

        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith("## "):
                name = stripped[3:].strip()
                current_column = name if name in column_set else None
            elif current_column and stripped.startswith("*"):
                stats[current_column] += 1

        stats["total"] = sum(v for v in stats.values() if isinstance(v, int))
        stats["in_progress"] = stats.get("DOING", 0)
        stats["completed"] = stats.get("DONE", 0)
        stats["pending"] = stats.get("BACKLOG", 0) + stats.get("TODO", 0)

        return json.dumps(stats, indent=2)
    
    @server.resource(
        "kanban://sync-status",
        name="github_sync_status",
        title="GitHub Sync Status",
        description="Information about the last sync with GitHub Projects",
        mime_type="application/json"
    )
    def get_sync_status() -> str:
        """Return sync status from .kanban.json state file."""
        workspace = get_workspace()
        state_path = os.path.join(workspace, ".kanban.json")
        
        if not os.path.exists(state_path):
            return json.dumps({
                "synced": False,
                "synced_tasks": 0,
                "message": "No sync state found. Board has not been synced to GitHub yet."
            }, indent=2)
        
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            items = state.get("items", {})
            
            return json.dumps({
                "synced": True,
                "synced_tasks": len(items),
                "state_file": state_path,
                "github_item_ids": list(items.values()),
                "local_task_titles": list(items.keys())
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error reading sync state: {str(e)}"
            }, indent=2)
    
    @server.resource(
        "kanban://config",
        name="kanbanger_configuration",
        title="Kanbanger Configuration",
        description="Current environment configuration for kanbanger",
        mime_type="application/json"
    )
    def get_config() -> str:
        """Return current configuration (without exposing secrets).

        O3: every value below is computed at call time, never cached
        from import. For the GitHub vars we additionally consult the
        workspace `.env` so the reported config matches what the next
        `sync_kanban` subprocess would actually see — the MCP server
        process doesn't `load_dotenv()` itself, so its inherited env
        and the subprocess's resolved env can diverge. Subprocess
        precedence is os.environ-then-.env (sync_kanban calls
        load_dotenv() with default override=False); we mirror that.
        """
        env_path = os.path.join(get_workspace(), ".env")
        # Read .env into a local dict at call time WITHOUT mutating
        # os.environ (avoids surprising side effects on the running
        # MCP process). Tolerate missing python-dotenv gracefully.
        try:
            from dotenv import dotenv_values
            dotenv_overlay = dotenv_values(env_path) if os.path.exists(env_path) else {}
        except ImportError:
            dotenv_overlay = {}

        def _runtime_value(name: str, default: str) -> str:
            return os.getenv(name) or dotenv_overlay.get(name) or default

        token = os.getenv("GITHUB_TOKEN") or dotenv_overlay.get("GITHUB_TOKEN")
        token_present = bool(token)

        # O3 reachability sub-item: ping GitHub iff a token is
        # actually configured. None when not configured (no point
        # pinging with no token); True on a successful `viewer`
        # query; False on any failure. Cached 30s.
        github_reachable = _check_github_reachable(token) if token else None

        config = {
            "workspace": get_workspace(),
            "kanban_file": get_kanban_path(),
            "kanban_exists": os.path.exists(get_kanban_path()),
            "github_token_set": token_present,
            "github_reachable": github_reachable,
            "github_repo": _runtime_value("GITHUB_REPO", "not set"),
            "github_project_number": _runtime_value("GITHUB_PROJECT_NUMBER", "auto-detect"),
            "env_file": env_path,
            "env_file_exists": os.path.exists(env_path),
        }

        return json.dumps(config, indent=2)
