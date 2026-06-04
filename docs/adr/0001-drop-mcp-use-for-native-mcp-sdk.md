# ADR 0001: Drop mcp-use; build the MCP server on the native mcp SDK (FastMCP)

## Status

Accepted

## Date

2026-06-04

## Context

The kanbanger MCP server was built on the third-party `mcp-use` wrapper.
`mcp-use/__init__.py` eagerly imports `mcp_use.agents.mcpagent`, which pulls in
langchain and, transitively, transformers and torch at import time — even
though the server only used the `MCPServer` symbol from the package.

As a result, importing `kanbanger_mcp.server` took roughly 24–48s warm and
203–257s cold (the cold cost being a one-time `.pyc` compile of the ML
dependency tree). MCP clients such as Claude Code time out the server
handshake at 30,000 ms, so the board became unusable mid-session whenever
`/mcp` reconnected and re-imported the server.

Root cause was verified by an `importtime` trace plus a `faulthandler` spike,
recorded in `briefs/DECISION-drop-mcp_use_2026-06-03.md` in the planning
workspace.

## Decision

Stop importing `mcp_use`. Re-implement `create_server()` and the
`register_tools` / `register_resources` / `register_prompts` surface directly
on the official `mcp` SDK's FastMCP:

```python
from mcp.server.fastmcp import FastMCP
```

FastMCP imports only `mcp.*` — no langchain, transformers, or torch. Behaviour
parity is preserved: 9 tools, 4 resources, 5 prompts.

## Consequences

- Handshake-ready in ~2.3s (measured via a real MCP stdio `initialize`), well
  under the 30s client timeout.
- The langchain / transformers / torch transitive tail is gone from the
  runtime path, yielding a smaller and faster install.
- The R12 `sys.stdout = sys.stderr` import shim — which existed to mask
  `mcp_use`'s stdout telemetry banner — is removed; FastMCP is import-clean.
- `MCP_USE_ANONYMIZED_TELEMETRY=false` is no longer needed; it is dropped from
  the generated `.mcp.json` and from kanban-doctor.
- The `mcp` dependency is pinned `>=1.12.0,<2.0.0`: mcp v2 renames
  `FastMCP` -> `MCPServer` and moves transport parameters onto `run()`, which
  would break the current bootstrap. Bump deliberately when porting to v2.
- `serverInfo.version` parity is preserved: FastMCP takes no `version=`
  parameter, so `create_server()` sets the kanbanger package `__version__` on
  the low-level server explicitly. The handshake still advertises `"2.1.0"`,
  matching the previous `MCPServer(version=...)` behaviour.

## Alternatives Considered

All rejected:

1. **Narrow the import.** Impossible — importing any `mcp_use.*` name runs the
   package's `__init__` side effects, which include the langchain import chain.
2. **`sys.modules` pre-stub of `mcp_use.agents`.** Saves only ~13s and leaves a
   ~14.6s floor; it also depends on `mcp_use`'s private module layout under an
   uncapped pin, making it fragile.
3. **Raise the client startup timeout.** Makes reconnect reliable but not fast;
   it redefines success as "doesn't get killed" rather than removing the cost.

## Evidence

- **Before:** import ~24–48s warm / 203–257s cold;
  `mcp_use.agents.mcpagent` accounted for ~94% of importtime.
- **After:** `kanbanger_mcp.server` import ~5s; real MCP stdio handshake ~2.3s;
  full test suite 67 passed (including a new FastMCP surface-inventory test).
