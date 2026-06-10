"""
Kanbanger MCP Server

Model Context Protocol server for kanbanger task management.
Provides tools, resources, and prompts for LLM-assisted kanban management.
"""

__version__ = "3.0.0"
__author__ = "earlyprototype"

# Native `mcp` SDK (FastMCP) is import-clean: it has no stdout side-effects
# at import, so the R12 sys.stdout→sys.stderr shim that guarded the old
# mcp_use import is no longer needed. (mcp_use dropped 2026-06-04; see the
# ADR in docs/adr/ and briefs/DECISION-drop-mcp_use_2026-06-03.md.)
from .server import create_server, main

__all__ = ["create_server", "main"]
