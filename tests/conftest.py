"""Shared pytest fixtures for kanbanger-partymix tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest


# --- registration-capturing stub ----------------------------------
# kanbanger_mcp.tools / resources / prompts register their callables
# via decorators on a FastMCP server. Unit tests don't need a real
# server — only the decorated functions, so they can be called
# directly. _StubMCPServer mirrors FastMCP's tool()/resource()/
# prompt() decorators (each returns the function unchanged after
# recording it), so register_tools(stub) populates stub.tools with the
# raw callables. (The native `mcp`/FastMCP import is light, so no
# sys.modules stubbing is needed since mcp_use was dropped 2026-06-04.)


class _StubMCPServer:
    """Captures @server.tool() / @server.prompt() registrations.

    The decorators in the real FastMCP return the decorated function
    unchanged after registering it on the server. We mirror that so
    `register_tools(stub)` populates `stub.tools` with the decorated
    callables, and the test can invoke them directly.
    """

    def __init__(self, name: str = "test", version: str = "0.0.0",
                 instructions: str = "") -> None:
        self.name = name
        self.version = version
        self.instructions = instructions
        self.tools: dict[str, Callable] = {}
        self.prompts: dict[str, Callable] = {}
        self.resources: dict[str, Callable] = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator

    def prompt(self, *args, **kwargs):
        name = kwargs.get("name")

        def decorator(fn):
            self.prompts[name or fn.__name__] = fn
            return fn
        return decorator

    def resource(self, *args, **kwargs):
        name = kwargs.get("name") or kwargs.get("uri")

        def decorator(fn):
            self.resources[name or fn.__name__] = fn
            return fn
        return decorator


# --- kanban workspace fixture --------------------------------------


_FIVE_COLUMN_BOARD = """\
# Test Kanban

## BACKLOG

## TODO

## DOING

## REVIEW

## DONE
"""


@pytest.fixture
def kanban_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp workspace with a fresh 5-column `_kanban.md`.

    All Bundle 1 tools read KANBANGER_WORKSPACE via
    `tools.get_workspace()`. Setting the env var to `tmp_path`
    isolates the test from the dev's real dogfood board AND from
    other tests in the same session. The board includes all 5
    columns (BACKLOG/TODO/DOING/REVIEW/DONE) by default so
    discover_columns(workspace) returns the full set without
    extra setup. Tests that need a board without REVIEW (e.g.
    a migration probe) overwrite the file in-test.
    """
    board_path = tmp_path / "_kanban.md"
    board_path.write_text(_FIVE_COLUMN_BOARD, encoding="utf-8")
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    return tmp_path


@pytest.fixture
def registered_tools(kanban_workspace: Path) -> dict[str, Callable]:
    """Import kanbanger_mcp.tools and return the registered tool map.

    `register_tools(stub)` populates `stub.tools` with each decorated
    function; the test calls them directly
    (e.g. `tools["propose_done"]("My Task")`).

    Depends on `kanban_workspace` so KANBANGER_WORKSPACE points at
    the temp board before any tool is exercised.
    """
    from kanbanger_mcp.tools import register_tools

    stub = _StubMCPServer()
    register_tools(stub)
    return stub.tools


@pytest.fixture
def registered_prompts(kanban_workspace: Path) -> dict[str, Callable]:
    """Same as registered_tools, but for prompts."""
    from kanbanger_mcp.prompts import register_prompts

    stub = _StubMCPServer()
    register_prompts(stub)
    return stub.prompts
