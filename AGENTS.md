# AGENTS.md

Guidance for AI agents working in this repository.

## Cursor Cloud specific instructions

### What this repo is

Single Python package (`kanbanger-partymix`): MCP server for markdown kanban (`_kanban.md`) with optional GitHub Projects sync. No Docker, databases, or long-running dev servers required for tests.

### PATH

Editable install puts CLI entry points in `~/.local/bin`. Ensure it is on `PATH` before calling `kanban-sync`, `kanban-doctor`, or `kanbanger-mcp`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Install and test (repo development)

From `/workspace`:

```bash
python3 -m pip install -e ".[mcp]"
python3 -m pip install pytest pytest-cov
python3 -m pytest --cov --cov-report=term-missing --cov-fail-under=25
```

There is no configured linter (ruff/black/mypy); follow PEP 8 per `CONTRIBUTING.md`.

### Run the MCP server (development)

Stdio (default, for MCP clients):

```bash
export KANBANGER_WORKSPACE=/path/to/project   # directory containing _kanban.md
python3 -m kanbanger
```

HTTP transport (optional):

```bash
python3 -m kanbanger --transport streamable-http --host 127.0.0.1 --port 8000
```

### Consumer setup (install once + provision per project)

Install globally once — `pipx install <path-to-this-clone>` or
`pipx install git+https://github.com/earlyprototype/kanbanger-partymix.git`
(plain `pip` works too). Then provision each project from its root with
`kanbanger init`: scaffolds `_kanban.md`, writes `.mcp.json` targeting the
global `kanbanger-mcp` command, and adds the agent touchpoint (rationale:
[docs/adr/0002](docs/adr/0002-single-install-and-collision-proof-binding.md)).
The in-MCP `setup_project` tool does the same from inside a session.

### GitHub sync (optional)

`kanban-sync` and MCP `sync_to_github` need `GITHUB_TOKEN`, `GITHUB_REPO`, and `GITHUB_PROJECT_NUMBER` in the environment or `.env`. CI and most unit tests do not need them. `kanban-doctor` reports missing credentials as FAIL for sync-related checks but MCP/board checks can still pass.

### Services summary

| Component | Required for `pytest` | Notes |
|-----------|----------------------|--------|
| Python 3.10+ + editable `[mcp]` install | Yes | |
| `kanbanger` subprocess | Only `tests/test_stdio_e2e.py` | Test spawns it automatically |
| GitHub API | No | Optional for sync demos |
| MCP IDE host | No | Optional for manual MCP E2E |
