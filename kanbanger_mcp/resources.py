"""
Kanbanger MCP Resources

Read-only data that LLMs can access for context and awareness.
"""

import os
import json
from pathlib import Path
from mcp_use.server import MCPServer


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


def register_resources(server: MCPServer):
    """Register all resources with the MCP server."""
    
    @server.resource(
        uri="kanban://current-board",
        name="current_kanban_board",
        title="Current Kanban Board",
        description="Real-time view of the _kanban.md file in the current workspace",
        mime_type="text/markdown"
    )
    def get_current_board() -> str:
        """Return the current kanban board content."""
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return f"# No Kanban Board Found\n\nNo _kanban.md file exists in workspace: {get_workspace()}\n\nCreate one with:\n```\n# Project Kanban\n\n## BACKLOG\n\n## TODO\n\n## DOING\n\n## DONE\n```"
        
        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"# Error Reading Kanban Board\n\nError: {str(e)}"
    
    @server.resource(
        uri="kanban://stats",
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
        # initializer. Mirrors the parser in tools.list_tasks so any
        # column the parser accepts (REVIEW, custom names) is counted
        # in both per-column figures and the total. Convenience aliases
        # (in_progress / completed / pending) stay for back-compat
        # callers but tolerate missing columns via .get(..., 0).
        lines = content.split('\n')
        stats: dict = {}
        current_column = None

        for line in lines:
            if line.strip().startswith("## "):
                current_column = line.strip()[3:].strip()
                stats.setdefault(current_column, 0)
            elif current_column and line.strip().startswith("*"):
                stats[current_column] = stats.get(current_column, 0) + 1

        stats["total"] = sum(v for v in stats.values() if isinstance(v, int))
        stats["in_progress"] = stats.get("DOING", 0)
        stats["completed"] = stats.get("DONE", 0)
        stats["pending"] = stats.get("BACKLOG", 0) + stats.get("TODO", 0)

        return json.dumps(stats, indent=2)
    
    @server.resource(
        uri="kanban://sync-status",
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
        uri="kanban://config",
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

        token_present = bool(os.getenv("GITHUB_TOKEN") or dotenv_overlay.get("GITHUB_TOKEN"))

        config = {
            "workspace": get_workspace(),
            "kanban_file": get_kanban_path(),
            "kanban_exists": os.path.exists(get_kanban_path()),
            "github_token_set": token_present,
            "github_repo": _runtime_value("GITHUB_REPO", "not set"),
            "github_project_number": _runtime_value("GITHUB_PROJECT_NUMBER", "auto-detect"),
            "env_file": env_path,
            "env_file_exists": os.path.exists(env_path),
        }

        return json.dumps(config, indent=2)
