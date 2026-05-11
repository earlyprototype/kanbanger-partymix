"""Shared pytest fixtures for kanbanger-partymix tests."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Callable

import pytest


# --- mcp_use stub --------------------------------------------------
# kanbanger_mcp.tools and kanbanger_mcp.prompts both import
# `mcp_use.server.MCPServer` at module scope. The real mcp_use
# package emits an INFO telemetry line on stdout at import (R12
# pattern, audit-cluster T1 finding) and pulls in a full server
# runtime. For unit tests we want neither. Stubbing mcp_use in
# sys.modules BEFORE the kanbanger imports lets us import the
# tool/prompt modules cleanly. The stub MCPServer captures decorator
# registrations so tests can call the registered functions directly.


class _StubMCPServer:
    """Captures @server.tool() / @server.prompt() registrations.

    The decorators in the real mcp_use return the decorated function
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


def _install_mcp_use_stub() -> None:
    """Install a stub `mcp_use.server` module into sys.modules.

    Idempotent — re-importing in the same process is safe.
    """
    existing = sys.modules.get("mcp_use")
    if (isinstance(existing, types.ModuleType)
            and getattr(existing, "_kanbanger_test_stub", False)):
        return
    mcp_use = types.ModuleType("mcp_use")
    mcp_use._kanbanger_test_stub = True
    server_mod = types.ModuleType("mcp_use.server")
    server_mod.MCPServer = _StubMCPServer
    mcp_use.server = server_mod
    sys.modules["mcp_use"] = mcp_use
    sys.modules["mcp_use.server"] = server_mod


_install_mcp_use_stub()


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

    The mcp_use stub is already in place at import time (installed at
    module top). `register_tools(stub)` populates `stub.tools` with
    each decorated function; the test calls them directly
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
