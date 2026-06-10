"""End-to-end test: drive real tool calls through the live stdio server.

The other tests prove the tool *functions* (via a stub) and that the surface
*registers* (on a real FastMCP instance). This proves the part users actually
depend on: a tool invoked over the MCP stdio wire against a spawned
`python -m kanbanger` parses its arguments, runs, mutates the board, and
returns correctly — and the REVIEW gate is enforced on that wire path.

It spawns a subprocess and speaks real MCP, so it is slower than the unit
tests; it is the regression guard for "the board actually works in a client",
not just "the code imports".

(Formerly spawned ``python -m kanbanger_mcp``; updated to ``python -m kanbanger``
after the ADR 0002 module rename.)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BOARD = "# E2E\n\n## BACKLOG\n\n## TODO\n\n## DOING\n\n## REVIEW\n\n## DONE\n"


def _payload(result):
    """Tools return JSON (or plain) strings as text content; decode them."""
    text = result.content[0].text
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


async def _drive(workspace: str) -> dict:
    env = dict(os.environ)
    env["KANBANGER_WORKSPACE"] = workspace
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "kanbanger"], env=env
    )
    out: dict = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("add_task", {"title": "E2E task", "column": "TODO"})
            out["after_add"] = _payload(await session.call_tool("list_tasks", {}))
            await session.call_tool(
                "move_task",
                {"title": "E2E task", "from_column": "TODO", "to_column": "DOING"},
            )
            out["propose"] = _payload(await session.call_tool("propose_done", {"title": "E2E task"}))
            out["approve"] = _payload(await session.call_tool("approve_done", {"title": "E2E task"}))
            out["after_approve"] = _payload(await session.call_tool("list_tasks", {}))
            await session.call_tool("add_task", {"title": "Gate test", "column": "TODO"})
            out["gate"] = _payload(await session.call_tool(
                "move_task",
                {"title": "Gate test", "from_column": "TODO", "to_column": "DONE"},
            ))
            board = await session.read_resource("kanban://current-board")
            out["board"] = board.contents[0].text
    return out


def test_stdio_tool_lifecycle_and_gate(tmp_path: Path):
    """Full lifecycle + gate enforcement over the real stdio transport."""
    (tmp_path / "_kanban.md").write_text(BOARD, encoding="utf-8")
    out = asyncio.run(_drive(str(tmp_path)))

    # add_task -> list_tasks: the task is in TODO over the wire
    assert "E2E task" in out["after_add"]["TODO"]
    # propose_done / approve_done succeed through the gate
    assert out["propose"]["success"] is True
    assert out["approve"]["success"] is True
    # the task lands in DONE
    assert "E2E task" in out["after_approve"]["DONE"]
    # a direct move to DONE is rejected on the wire (gate enforced)
    assert out["gate"]["success"] is False
    assert out["gate"]["error_code"] == "gate_violation"
    # the read-only resource reflects board state
    assert "E2E task" in out["board"]
