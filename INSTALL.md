# Install — kanbanger-partymix

## TL;DR

```
python C:\Users\Fab2\Desktop\AI\_tools\kanbanger-partymix\scripts\setup-venv.py
```

(Adjust the path to wherever you cloned this repo.) Run that command from
any project's root directory. It creates `.venv/`, installs partymix into
it, writes `.mcp.json` pointed at that venv, and gitignores `.venv/`.

Then open a fresh Claude Code session in that project. The kanbanger MCP
server should load automatically.

## Why a per-project venv?

Both the original `kanban-project-sync` (v2.1.0, source at `_kanbanger/`)
and `kanbanger-partymix` (the v3.0 successor) declare the same importable
Python package name: `kanbanger_mcp`. When both are pip-installed
system-wide, the editable install silently shadows the other, and
`python -m kanbanger_mcp` can resolve to the wrong source. This causes
"Server not connected" errors in MCP clients with no clear diagnosis.

A per-project venv solves the collision by isolating each project's
kanbanger install. The project's `.mcp.json` pins an absolute path to its
own venv's `python.exe`, so Claude Code (or any MCP client) always spawns
the right kanbanger.

## What the script does

1. `python -m venv <project>/.venv`
2. `<venv>/python -m pip install --upgrade pip`
3. `<venv>/python -m pip install -e <partymix-source>[mcp]`
4. Verifies that `import kanbanger_mcp` in the venv resolves to the
   partymix source.
5. Writes `<project>/.mcp.json` with:
   - `command` = absolute path to `<venv>/Scripts/python.exe` (Windows)
     or `<venv>/bin/python` (Unix)
   - `args` = `["-m", "kanbanger_mcp"]`
   - `env` block with `KANBANGER_WORKSPACE` and GitHub credentials slots
6. Appends `.venv/` to `.gitignore` (creating the file if missing).

If `.mcp.json` already exists in the target project, it is backed up to
`.mcp.json.backup` before being overwritten.

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

After the script finishes, in the project's `.venv`:

```
.venv\Scripts\python -c "import kanbanger_mcp; print(kanbanger_mcp.__file__)"
```

Expected output:

```
<partymix-source>\kanbanger_mcp\__init__.py
```

If the file path is anywhere else (e.g. `site-packages` or another
project's `.venv`), the install pointed at the wrong source. Re-run
`setup-venv.py` from a fresh shell.

(Step 3 of the MVP plan ports `kanban-doctor` to partymix — once that
lands, run `kanban-doctor` for a richer preflight check.)

## Uninstalling

Delete the project's `.venv/` directory. That's it — the install is
local to the project.

## What this does NOT do

- It does not install partymix system-wide. Each project's venv is
  independent. If you want partymix available globally, install it
  manually with `pip install -e .[mcp]` from the partymix root.
- It does not write `.claude/settings.local.json` (secrets). You do
  that once per project, manually.
- It does not configure GitHub Projects V2 sync. That's a separate
  step (set `GITHUB_PROJECT_NUMBER` and link a project to the repo).
- It does not migrate existing `_kanban.md` data. Boards are
  per-project; the script doesn't touch your kanban file.

## Troubleshooting

**"ERROR: partymix source not found"** — The script computes its own
location and looks for `setup.py` in the parent directory. If you moved
or renamed `scripts/`, fix it back.

**"Could not import kanbanger_mcp in the venv"** — The `pip install`
failed silently. Re-run with `--quiet` removed from the script for a
verbose trace.

**".mcp.json is loaded but server reports 'not connected'"** —
Usually means the venv's python has a broken dependency. Activate the
venv manually and run `python -m kanbanger_mcp --help` to see the real
error.

**"I want to use the same venv for multiple projects"** — Don't.
The whole point is per-project isolation; this lets you have different
versions of partymix on different projects, and keeps Phase 1+
development independent of dogfood.
