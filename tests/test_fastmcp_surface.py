"""Parity / inventory test for the native FastMCP server bootstrap.

After dropping `mcp_use` (2026-06-04), the server is built directly on the
native `mcp` SDK's FastMCP. The other unit tests exercise the tool /
resource / prompt *functions* via a registration-capturing stub; this test
is the complementary proof that `create_server()` actually wires the full
surface onto a real FastMCP instance — the part the stub cannot verify.

Acceptance gate for the port: a real FastMCP server exposing exactly
10 tools, 4 resources, and 5 prompts, by name. If the native SDK's
decorator API ever drifts, this fails loudly instead of silently
dropping a capability.
"""
from __future__ import annotations

import asyncio

import pytest

from mcp.server.fastmcp import FastMCP
from kanbanger.server import create_server


EXPECTED_TOOLS = {
    "add_task",
    "move_task",
    "delete_task",
    "list_tasks",
    "sync_to_github",
    "get_sync_status",
    "propose_done",
    "approve_done",
    "reject_review",
    "setup_project",
}

EXPECTED_RESOURCES = {
    "kanban://current-board",
    "kanban://stats",
    "kanban://sync-status",
    "kanban://config",
}

EXPECTED_PROMPTS = {
    "kanban_awareness",
    "task_planning",
    "daily_standup",
    "review_gate_etiquette",
    "github_sync_check",
}


@pytest.fixture(scope="module")
def server() -> FastMCP:
    """A real FastMCP server built by the production bootstrap."""
    return create_server()


def test_create_server_returns_fastmcp(server: FastMCP):
    assert isinstance(server, FastMCP)


def test_all_tools_registered(server: FastMCP):
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == EXPECTED_TOOLS


def test_all_resources_registered(server: FastMCP):
    uris = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert uris == EXPECTED_RESOURCES


def test_all_prompts_registered(server: FastMCP):
    names = {p.name for p in asyncio.run(server.list_prompts())}
    assert names == EXPECTED_PROMPTS


def test_server_advertises_kanbanger_version(server: FastMCP):
    """serverInfo.version reports the kanbanger package version, not the mcp
    SDK version. FastMCP has no version= param, so create_server() sets it on
    the low-level server; this guards that parity (and catches it if a future
    SDK rename removes the attribute)."""
    from kanbanger import __version__

    assert server._mcp_server.version == __version__
