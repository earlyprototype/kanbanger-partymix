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
python3 -m kanbanger_mcp
```

HTTP transport (optional):

```bash
python3 -m kanbanger_mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

### Per-project consumer setup (`setup-venv.py`)

`scripts/setup-venv.py` creates a project `.venv` and `.mcp.json`. It requires the system `venv` module:

```bash
sudo apt-get install -y python3.12-venv   # Ubuntu/Debian if venv creation fails
```

Point it at this repo clone: `python3 /workspace/scripts/setup-venv.py /path/to/your/project`.

### GitHub sync (optional)

`kanban-sync` and MCP `sync_to_github` need `GITHUB_TOKEN`, `GITHUB_REPO`, and `GITHUB_PROJECT_NUMBER` in the environment or `.env`. CI and most unit tests do not need them. `kanban-doctor` reports missing credentials as FAIL for sync-related checks but MCP/board checks can still pass.

### Services summary

| Component | Required for `pytest` | Notes |
|-----------|----------------------|--------|
| Python 3.10+ + editable `[mcp]` install | Yes | |
| `kanbanger_mcp` subprocess | Only `tests/test_stdio_e2e.py` | Test spawns it automatically |
| GitHub API | No | Optional for sync demos |
| MCP IDE host | No | Optional for manual MCP E2E |
