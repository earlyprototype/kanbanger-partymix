"""
Kanbanger MCP Server

Model Context Protocol server for kanbanger task management.
Provides tools, resources, and prompts for LLM-assisted kanban management.
"""

__version__ = "2.1.0"
__author__ = "earlyprototype"

# R12: swap sys.stdout→sys.stderr around the mcp_use import chain so its at-import
# StreamHandler (mcp_use/logging.py:95) binds to stderr; keeps MCP stdout framing clean.
import sys as _sys
_real_stdout = _sys.stdout
_sys.stdout = _sys.stderr
try:
    from .server import create_server, main
finally:
    _sys.stdout = _real_stdout

__all__ = ["create_server", "main"]
