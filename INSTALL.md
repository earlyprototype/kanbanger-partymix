# Install — kanbanger-partymix

## TL;DR

Once per machine:

```
pipx install git+https://github.com/earlyprototype/kanbanger-partymix.git
```

Once per project, from the project's root directory:

```
kanbanger init
```

Then open a fresh Claude Code session in that project. The kanbanger MCP
server loads via the project's `.mcp.json`.

(Not on PyPI yet — install from git or a local clone for now. Plain `pip`
and `uv tool install` work the same way if you don't use pipx.)

## The model: install once, provision per project

Kanbanger separates two concerns:

1. **Install** — once, globally, like any other MCP server. This puts four
   commands on PATH: `kanbanger-mcp` (the MCP server), `kanbanger` (CLI,
   currently `kanbanger init`), `kanban-sync`, and `kanban-doctor`.
2. **Register** — each project's `.mcp.json` points at the global
   `kanbanger-mcp` command. Provisioning writes it for you.
3. **Provision** — once per project: scaffold the board and wire the
   touchpoints. Lightweight and idempotent.
4. **Bind** — at runtime the server resolves the project's own `_kanban.md`,
   so boards never mix.

There is no per-project venv.

## Install (once per machine)

pipx is recommended — isolated install, commands on PATH:

```
pipx install git+https://github.com/earlyprototype/kanbanger-partymix.git
```

From a local clone instead:

```
pipx install C:/path/to/kanbanger-partymix
```

Plain `pip install` (or `uv tool install`) of either form works too. No git
client on the machine? Install straight from the source zip:

```bash
pip install https://github.com/earlyprototype/kanbanger-partymix/archive/refs/heads/main.zip
```

PATH notes: with pipx, run `pipx ensurepath` if the commands don't resolve.
With `pip install --user` on Windows, the commands land in Python's user
`Scripts` directory — pip prints the exact path in a warning if it isn't on
PATH; add it and restart your shell.

## Provision (once per project)

Two equivalent paths — both run the exact same provisioning code:

- **CLI:** from the project root, run `kanbanger init`
- **In-session:** if the kanbanger MCP server is already available, ask the
  assistant to run the `setup_project` tool. (On first contact with an
  unprovisioned project, the assistant offers this itself.)

What provisioning writes — idempotent, safe to re-run:

1. `_kanban.md` — the canonical 5-column board
   (BACKLOG → TODO → DOING → REVIEW → DONE). Scaffolded only if absent;
   **an existing board is never clobbered** — the only change provisioning
   ever makes to one is inserting the `<!-- kanbanger:board-id: ... -->`
   marker comment when it's missing (enables collision detection); every
   other byte is preserved. (Separately, the running MCP server adds a
   REVIEW column to a 4-column board at startup — the review-gate
   tools require it.)
2. `.mcp.json` — wires the project to the global `kanbanger-mcp` command,
   with empty `${VAR:-}` GitHub-sync placeholders. Left untouched if the
   project already has one.
3. `CLAUDE.md` — the Kanbanger agent touchpoint stanza (created, appended,
   or refreshed in place between its markers). `AGENTS.md` gets the same
   stanza only if that file already exists.
4. `.gitignore` — ensures a stray `.venv/` stays out of version control.

After provisioning, **restart the Claude session** — `.mcp.json` is read at
session start, so the kanbanger tools only appear in a fresh session.

## Credentials

Don't put real `GITHUB_TOKEN` / `GITHUB_REPO` values in `.mcp.json`. The
config uses `${VAR:-default}` substitution. Provide actual values via
`<project>/.claude/settings.local.json` (gitignored), like this:

```json
{
  "env": {
    "GITHUB_TOKEN": "ghp_...",
    "GITHUB_REPO": "owner/repo",
    "GITHUB_PROJECT_NUMBER": "12"
  }
}
```

Claude Code injects this `env` block into MCP server spawns.

### Windows users — save `.env` as UTF-8 *without* BOM

If you hand-edit `.env` in a Windows editor (Notepad, some IDE defaults)
that saves UTF-8 *with* a BOM, the Python CLI path is fine —
`python-dotenv` strips the BOM automatically. But if you `source ./.env`
from Git Bash or any POSIX shell, you will get:

```text
./.env: line 1: $'\357\273\277#': command not found
```

That `\357\273\277` is the UTF-8 BOM. Resave the file as **UTF-8
(without BOM)** — in VS Code, click the encoding indicator in the
status bar and pick "Save with Encoding -> UTF-8". Notepad++ has
"Encoding -> UTF-8" (vs "UTF-8 with BOM"). Notepad on Windows 11 lets
you set the encoding in the Save As dialog.

## Verifying the install

```
kanban-doctor
```

reports the state of the install, board, and sync config. A board with no
GitHub sync configured is a healthy, fully supported state — the doctor
reports "local-only mode" and exits 0. For a quick PATH check,
`kanbanger-mcp --help` (or `pipx list`) should resolve the global install.

## Upgrading / Uninstalling

```
pipx upgrade kanbanger-partymix     # pull the latest from the install source
pipx uninstall kanbanger-partymix   # remove the global install
```

Provisioned files (`_kanban.md`, `.mcp.json`, the `CLAUDE.md` stanza) are
project-local — delete them per project if you want them gone. Your board
data only ever lives in the project.

## What provisioning does NOT do

- It does not write secrets anywhere. The GitHub slots in `.mcp.json` are
  empty `${VAR:-}` placeholders; you supply real values via the
  environment or `.claude/settings.local.json`.
- It does not configure GitHub Projects V2 sync. That's a separate step —
  see the [GitHub Projects V2 sync guide](README.md#github-projects-v2-sync)
  in the README.
- It does not migrate or restructure existing `_kanban.md` data — an
  existing board is never clobbered. The one change it may make is adding
  the board-key marker comment when absent (enables collision detection);
  every other byte is preserved.

## Migrating from a per-project `.venv` install

If a project's `.mcp.json` points at a per-project `.venv` instead of the
global `kanbanger-mcp` command:

1. Delete the project's `.venv/`.
2. Move the existing `.mcp.json` aside so a fresh one can be written.
3. Run `kanbanger init` from the project root.
4. Restart the Claude session.

If a `kanban-project-sync` dist is installed on the machine,
`pip uninstall kanban-project-sync` removes it (the install-collision check
in `kanban-doctor` flags it).

## Troubleshooting

**"MCP tools not showing in my session"** — Is kanbanger installed on this
machine (`pipx list`)? Is the project provisioned (`.mcp.json` present)?
Restart Claude Code after any `.mcp.json` change, then run `kanban-doctor`.

**"`kanbanger-mcp` not found" when the server should spawn** — The global
install isn't on PATH. With pipx, run `pipx ensurepath` and restart your
shell/IDE.

**".mcp.json is loaded but server reports 'not connected'"** — Run
`kanbanger-mcp --help` in a terminal to surface the real error (usually a
broken dependency).
