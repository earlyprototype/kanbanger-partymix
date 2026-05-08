"""
Kanbanger MCP Server

Model Context Protocol server for kanbanger task management.
Provides tools, resources, and prompts for LLM-assisted kanban management.
"""

__version__ = "2.1.0"
__author__ = "earlyprototype"

from .server import create_server, main

__all__ = ["create_server", "main"]
