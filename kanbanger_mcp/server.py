"""
Kanbanger MCP Server

Main server implementation providing tools, resources, and prompts
for LLM-assisted kanban management.
"""

import os
import sys
import argparse
from pathlib import Path
from mcp_use.server import MCPServer

from .tools import register_tools
from .resources import register_resources
from .prompts import register_prompts


def create_server() -> MCPServer:
    """Create and configure the Kanbanger MCP server."""
    server = MCPServer(
        name="kanbanger",
        version="2.1.0",
        instructions="""
Kanbanger MCP Server - Task Management via Kanban Boards

This server manages a markdown kanban board (`_kanban.md`) for the current
project, optionally synced to GitHub Projects V2.

## Workspace
The board is `<workspace>/_kanban.md`. <workspace> is the KANBANGER_WORKSPACE
environment variable, or the current working directory if it is unset.

## First contact - is Kanbanger set up in this project?
Before using any other tool, check whether the board exists: read the
`kanban://current-board` resource (or look for `_kanban.md` in the workspace).

If `_kanban.md` does NOT exist, Kanbanger is not set up in this project yet.
Do NOT silently create it. Tell the user, and ask if they want to set
Kanbanger up here. If they agree, install it locally in this project:

1. If the project is not provisioned yet (no `.venv` / `.mcp.json`), run the
   local installer from the Kanbanger source (idempotent - reuses an existing
   venv, backs up any existing .mcp.json):
       python <kanbanger_source>/scripts/setup-venv.py <project_dir>
2. Create `_kanban.md` with the canonical 5-column schema
   (BACKLOG -> TODO -> DOING -> REVIEW -> DONE):

   # <Project Name> Kanban

   ## BACKLOG
   *   [ ] Future / unprioritised work

   ## TODO
   *   [ ] Ready to start, prioritised

   ## DOING
   *   [ ] In progress (keep to 1-3 items)

   ## REVIEW
   *   [ ] AI-completed work awaiting human approval

   ## DONE
   *   [x] Completed, human-approved work

If `_kanban.md` already exists, proceed normally.

## Capabilities
- Tools: add, move, delete, list tasks; sync to GitHub.
- Resources: current board (kanban://current-board), stats, sync status.
- Prompts: kanban awareness, task planning, daily standup.

## REVIEW gates DONE
AI-completed work moves to REVIEW, never straight to DONE. A human approves
REVIEW -> DONE.
        """.strip()
    )
    
    # Register all capabilities
    register_tools(server)
    register_resources(server)
    register_prompts(server)
    
    return server


def main():
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        description="Kanbanger MCP Server - Task management via kanban boards"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport protocol to use (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for HTTP transports (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP transports (default: 8000)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with development tools"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Auto-reload on code changes (development only)"
    )
    
    args = parser.parse_args()
    
    # Validate workspace
    # S2: resolve to absolute canonical path so `..` segments and
    # symlinks collapse predictably regardless of the process cwd.
    workspace = str(Path(os.getenv("KANBANGER_WORKSPACE", os.getcwd())).resolve())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    if not os.path.exists(kanban_path):
        print(f"Warning: No _kanban.md found in workspace: {workspace}", file=sys.stderr)
        print(f"The server will start but tools may fail until a kanban board is created.", file=sys.stderr)

    # REVIEW-gate primitives (propose_done / approve_done / reject_review)
    # assume REVIEW is on the board. Auto-migrate any 4-column v2.x board
    # in place before tools register, so downstream code paths can rely
    # on REVIEW being present. Idempotent no-op on 5-column boards.
    from kanban_io import ensure_review_column
    if ensure_review_column(workspace):
        print(
            f"kanbanger: added REVIEW column to {os.path.join(workspace, '_kanban.md')} "
            f"(5-column schema required by review-gate primitives)",
            file=sys.stderr,
        )

    # Create and run server
    server = create_server()
    
    print(f"Starting Kanbanger MCP Server...", file=sys.stderr)
    print(f"Workspace: {workspace}", file=sys.stderr)
    print(f"Transport: {args.transport}", file=sys.stderr)
    
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        print(f"Server running on {args.host}:{args.port}", file=sys.stderr)
        server.run(
            transport=args.transport,
            host=args.host,
            port=args.port,
            reload=args.reload,
            debug=args.debug
        )


if __name__ == "__main__":
    main()
