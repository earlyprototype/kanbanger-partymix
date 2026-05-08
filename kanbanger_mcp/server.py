"""
Kanbanger MCP Server

Main server implementation providing tools, resources, and prompts
for LLM-assisted kanban management.
"""

import os
import sys
import argparse
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

This server provides tools for managing markdown-based kanban boards
that sync with GitHub Projects V2.

## Workspace Awareness
The server operates on the workspace defined by KANBANGER_WORKSPACE
environment variable (typically set to ${workspaceFolder} by IDE).

## Available Capabilities:
- Tools: Add, move, delete, list tasks; sync to GitHub
- Resources: View current board, stats, sync status
- Prompts: Kanban awareness, task planning, daily standup

## Typical Workflow:
1. Check current board state (kanban://current-board resource)
2. Add tasks as needed (add_task tool)
3. Move tasks through workflow (move_task tool)
4. Sync to GitHub Projects (sync_to_github tool)

See individual tools and resources for detailed usage.
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
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    if not os.path.exists(kanban_path):
        print(f"Warning: No _kanban.md found in workspace: {workspace}", file=sys.stderr)
        print(f"The server will start but tools may fail until a kanban board is created.", file=sys.stderr)
    
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
