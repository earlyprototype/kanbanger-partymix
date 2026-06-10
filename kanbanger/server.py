"""
Kanbanger MCP Server

Main server implementation providing tools, resources, and prompts
for LLM-assisted kanban management.
"""

import os
import sys
import argparse
from mcp.server.fastmcp import FastMCP

from .tools import register_tools
from .resources import register_resources
from .prompts import register_prompts


def create_server(*, host=None, port=None, debug=False) -> FastMCP:
    """Create and configure the Kanbanger MCP server.

    host/port/debug are only meaningful for the HTTP/SSE transports; the
    default stdio transport ignores them. They are accepted here so main()
    can configure them on the FastMCP instance — the native `mcp` SDK takes
    them on the constructor, not on run().
    """
    settings = {}
    if host is not None:
        settings["host"] = host
    if port is not None:
        settings["port"] = port
    if debug:
        settings["debug"] = debug
    server = FastMCP(
        name="kanbanger",
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
Kanbanger up here. If they agree, call the `setup_project` tool: it
provisions the project idempotently - scaffolds the canonical 5-column
board (BACKLOG -> TODO -> DOING -> REVIEW -> DONE), writes a `.mcp.json`
targeting the global `kanbanger-mcp` command, and adds the agent
touchpoint. (`kanbanger init` run from the project root is the CLI
equivalent.) Never hand-create or hand-edit the board.

If `_kanban.md` already exists, proceed normally.

## Capabilities
- Tools: add, move, delete, list tasks; propose_done / approve_done /
  reject_review (the REVIEW gate); sync to GitHub; setup_project.
- Resources: current board (kanban://current-board), stats, sync status,
  config.
- Prompts: kanban awareness, task planning, daily standup, review-gate
  etiquette, sync check.

## REVIEW gates DONE
AI-completed work moves to REVIEW, never straight to DONE. A human approves
REVIEW -> DONE.
        """.strip(),
        **settings,
    )
    
    # Register all capabilities
    register_tools(server)
    register_resources(server)
    register_prompts(server)
    
    # FastMCP has no version= parameter, so serverInfo.version would
    # otherwise default to the mcp SDK version. Set it on the low-level
    # server so the handshake keeps advertising the kanbanger package
    # version -- parity with the previous MCPServer(version="2.1.0").
    from . import __version__
    server._mcp_server.version = __version__

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
    args = parser.parse_args()
    
    # Validate workspace via the ADR 0002 binding precedence (env pin >
    # walk-up discovery > cwd fallback) — the SAME resolution the tools and
    # resources use, so startup validation, the REVIEW-column migration
    # below, and every later tool call all target one and the same board.
    # S2 property preserved: absolute canonical path, symlinks collapsed.
    from .binding import resolve_workspace
    workspace = str(resolve_workspace())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    if not os.path.exists(kanban_path):
        print(f"Warning: No _kanban.md found in workspace: {workspace}", file=sys.stderr)
        print("The server will start but tools may fail until a kanban board is created.", file=sys.stderr)

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

    # Create and run server. The native SDK takes host/port/debug on the
    # constructor (not on run()), so configure them here for HTTP/SSE; the
    # default stdio transport ignores them.
    server = create_server(host=args.host, port=args.port, debug=args.debug)

    print("Starting Kanbanger MCP Server...", file=sys.stderr)
    print(f"Workspace: {workspace}", file=sys.stderr)
    print(f"Transport: {args.transport}", file=sys.stderr)

    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        print(f"Server running on {args.host}:{args.port}", file=sys.stderr)
        server.run(transport=args.transport)


if __name__ == "__main__":
    main()
