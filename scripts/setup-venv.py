#!/usr/bin/env python3
"""
setup-venv.py — [DEPRECATED INSTALLER] per-project Kanbanger provisioning.

DEPRECATED (ADR 0002, issue #15): this script NO LONGER installs anything.

The supported install path is now a SINGLE GLOBAL install, like any other MCP
server:

    pipx install <path-to-kanbanger-partymix>      # recommended
    # or
    pip install <path-to-kanbanger-partymix>

That gives you a working `kanbanger-mcp` server on PATH with no per-project
`.venv`. The old per-project venv only existed to dodge the `kanbanger_mcp`
import collision; the v3 module rename (`kanbanger_mcp` -> `kanbanger`) removed
that cause, so per-project installs are no longer needed.

What this script still does (for now): the PROVISIONING half only — write
`<PROJECT>/.mcp.json`, ensure `.gitignore` hygiene, and drop the Kanbanger
onboarding stanza into `<PROJECT>/CLAUDE.md`. It creates NO venv and runs NO
pip install.

NOTE: this remaining provisioning role is itself slated for replacement by
in-MCP provisioning (issue #15 step 3 — an `init` / first-contact flow inside
the server). When that lands, this script can be retired entirely. Do not
extend it; prefer the in-MCP path.

Usage:
    python <partymix>/scripts/setup-venv.py [PROJECT_DIR]

PROJECT_DIR defaults to the current working directory.

Exit codes:
    0 - success
    1 - usage / preflight error
"""
import argparse
import json
import sys
from pathlib import Path

PARTYMIX_SOURCE = Path(__file__).resolve().parent.parent
GITIGNORE_ENTRY = ".venv/"
GITIGNORE_HEADER = "# Local virtualenv (if any) — kanbanger installs globally; see ADR 0002"
CLAUDE_MD_START = "<!-- kanbanger:start -->"
CLAUDE_MD_END = "<!-- kanbanger:end -->"


def to_forward_slashes(p) -> str:
    return str(p).replace("\\", "/")


def build_mcp_config(project_dir: Path) -> dict:
    """Build a project `.mcp.json` that targets the GLOBAL kanbanger install.

    Post-ADR-0002 there is no per-project venv to pin to, so the command is the
    `kanbanger-mcp` console script installed globally (pipx/pip) and resolved on
    PATH — exactly how any other MCP server is wired. (Previously this pinned to
    `<project>/.venv/Scripts/python.exe -m kanbanger`.)
    """
    project_path_fwd = to_forward_slashes(project_dir)
    return {
        "mcpServers": {
            "kanbanger": {
                "command": "kanbanger-mcp",
                "args": [],
                "env": {
                    "KANBANGER_WORKSPACE": "${KANBANGER_WORKSPACE:-" + project_path_fwd + "}",
                    "GITHUB_TOKEN": "${GITHUB_TOKEN:-}",
                    "GITHUB_REPO": "${GITHUB_REPO:-}",
                    "GITHUB_PROJECT_NUMBER": "${GITHUB_PROJECT_NUMBER:-}",
                },
            }
        }
    }


def ensure_gitignore_has_venv(project_dir: Path) -> None:
    gitignore = project_dir / ".gitignore"
    block = f"\n{GITIGNORE_HEADER}\n{GITIGNORE_ENTRY}\n"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if GITIGNORE_ENTRY in content:
            return
        sep = "" if content.endswith("\n") else "\n"
        gitignore.write_text(content + sep + block, encoding="utf-8")
        print(f"  appended {GITIGNORE_ENTRY} to {gitignore}")
    else:
        gitignore.write_text(block.lstrip("\n"), encoding="utf-8")
        print(f"  created {gitignore} with {GITIGNORE_ENTRY}")


def build_claude_md_block(project_dir: Path) -> str:
    """The Kanbanger onboarding stanza injected into a project's CLAUDE.md.

    This is the always-loaded, pre-launch touchpoint. The server's own
    `instructions` string carries the same intent, but an LLM can't see it
    until the server is already running -- so in a project where the MCP isn't
    loaded yet, this stanza is the only thing telling the agent to (a) drive
    the board through the MCP tools rather than hand-editing `_kanban.md`,
    (b) keep the board project-scoped, and (c) how to recover when the
    per-project venv isn't provisioned (e.g. on a fresh clone).
    """
    return f"""{CLAUDE_MD_START}
## Kanbanger: task board for this project

This project tracks work on a Kanban board managed by the **Kanbanger MCP
server**. The board lives at `_kanban.md` in the project root and is
**project-scoped** -- configured here via `.mcp.json` + `.venv`, not globally.
Don't install or move Kanbanger to user/global scope; the board belongs to
this project.

**For AI agents:**
- **Always use the Kanbanger MCP tools** (`list_tasks`, `add_task`, `move_task`,
  `delete_task`, `sync_to_github`, `get_sync_status`) to read or change the
  board. **Never hand-edit `_kanban.md`** -- direct edits bypass validation,
  locking, and atomic writes and will eventually corrupt the board or its
  GitHub sync.
- On first contact, read the `kanban://current-board` resource before acting.
- **REVIEW gates DONE.** AI-completed work goes to REVIEW via `propose_done`,
  never straight to DONE; a human approves REVIEW -> DONE via `approve_done`.
  Never move your own work directly to DONE.

**If the Kanbanger tools aren't available** in this session, the per-project
`.venv` is probably not provisioned on this machine (it's gitignored, so a
fresh clone won't have it). Re-provision and restart the session:

```
python <partymix>/scripts/setup-venv.py
```
{CLAUDE_MD_END}
"""


def ensure_claude_md_has_kanbanger(project_dir: Path) -> None:
    """Idempotently add (or refresh) the Kanbanger stanza in <project>/CLAUDE.md.

    - File absent          -> create it with the stanza.
    - File present, no tag  -> append the stanza (existing content preserved).
    - File present, tagged  -> replace the block between the markers, so a
      re-run after a partymix upgrade refreshes the stanza without duplicating.
    """
    claude_md = project_dir / "CLAUDE.md"
    block = build_claude_md_block(project_dir)
    if not claude_md.exists():
        claude_md.write_text(block, encoding="utf-8")
        print(f"  created {claude_md} with the kanbanger stanza")
        return

    content = claude_md.read_text(encoding="utf-8")
    start_idx = content.find(CLAUDE_MD_START)
    if start_idx != -1:
        end_idx = content.find(CLAUDE_MD_END, start_idx + len(CLAUDE_MD_START))
        if end_idx != -1:
            end_idx += len(CLAUDE_MD_END)
            new_content = content[:start_idx] + block.rstrip("\n") + content[end_idx:]
            if new_content != content:
                claude_md.write_text(new_content, encoding="utf-8")
                print(f"  refreshed the kanbanger stanza in {claude_md}")
            else:
                print(f"  kanbanger stanza in {claude_md} already up to date")
            return
        else:
            print(f"  found orphan start marker in {claude_md}, replacing from that point")
            new_content = content[:start_idx] + block
            claude_md.write_text(new_content, encoding="utf-8")
            print(f"  replaced orphan stanza in {claude_md}")
            return

    sep = "" if content.endswith("\n") else "\n"
    claude_md.write_text(content + sep + "\n" + block, encoding="utf-8")
    print(f"  appended kanbanger stanza to {claude_md}")


DEPRECATION_BANNER = """\
============================================================================
  setup-venv.py is DEPRECATED as an installer and installs NOTHING.

  Install kanbanger ONCE, globally, like any other MCP server:

      pipx install "{source}"
      # or:  pip install "{source}"

  That puts `kanbanger-mcp` on your PATH. No per-project .venv is needed
  (the venv only ever existed to dodge the old kanbanger_mcp import
  collision, which the module rename removed — see ADR 0002).

  This script now only PROVISIONS a project (writes .mcp.json + the
  CLAUDE.md touchpoint, tends .gitignore). That role is itself being
  replaced by in-MCP provisioning (issue #15 step 3); prefer that once it
  lands. Pass --no-provision to skip provisioning entirely.
============================================================================
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="[DEPRECATED installer] Provision a project for the GLOBAL "
                    "kanbanger install. Creates no venv and installs nothing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory (default: current working directory)",
    )
    parser.add_argument(
        "--no-mcp-json",
        action="store_true",
        help="Skip writing .mcp.json (useful if you maintain your own).",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Skip appending .venv/ to .gitignore.",
    )
    parser.add_argument(
        "--no-claude-md",
        action="store_true",
        help="Skip adding the Kanbanger stanza to the project's CLAUDE.md.",
    )
    parser.add_argument(
        "--no-provision",
        action="store_true",
        help="Print the deprecation/install banner and exit without provisioning.",
    )
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: project directory not found: {project_dir}", file=sys.stderr)
        return 1
    if not PARTYMIX_SOURCE.is_dir() or not (PARTYMIX_SOURCE / "setup.py").is_file():
        print(f"ERROR: partymix source not found at {PARTYMIX_SOURCE}", file=sys.stderr)
        return 1

    # Deprecation / install banner — always shown, because this script no
    # longer installs anything (ADR 0002). Global install is the supported path.
    print(DEPRECATION_BANNER.format(source=to_forward_slashes(PARTYMIX_SOURCE)))

    if args.no_provision:
        print("--no-provision set: nothing to do (and nothing was installed).")
        return 0

    print("Provisioning project (no install — global kanbanger-mcp expected on PATH):")
    print(f"  project: {project_dir}")
    print(f"  source:  {PARTYMIX_SOURCE}")
    print()

    if not args.no_mcp_json:
        mcp_json = project_dir / ".mcp.json"
        print(f"Writing {mcp_json}")
        if mcp_json.exists():
            backup = project_dir / ".mcp.json.backup"
            print(f"  existing file backed up to {backup}")
            backup.write_text(mcp_json.read_text(encoding="utf-8"), encoding="utf-8")
        config = build_mcp_config(project_dir)
        mcp_json.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print("  wrote .mcp.json targeting the global `kanbanger-mcp` command")

    if not args.no_gitignore:
        print("\nEnsuring .venv/ is gitignored (harmless if you never make one)")
        ensure_gitignore_has_venv(project_dir)

    if not args.no_claude_md:
        print("\nAdding the Kanbanger stanza to CLAUDE.md")
        ensure_claude_md_has_kanbanger(project_dir)

    print("\nDone (provisioning only — no install performed).")
    print("Next:")
    print(f"  - Ensure kanbanger is installed globally: pipx install \"{to_forward_slashes(PARTYMIX_SOURCE)}\"")
    print(f"  - Open a fresh Claude Code session in {project_dir}")
    print("  - Confirm kanbanger MCP loads (paste '/mcp' or call list_tasks)")
    print("  - CLAUDE.md now tells agents to use the MCP tools, not hand-edit the board")
    print("  - NOTE: this provisioning role is slated for replacement by in-MCP")
    print("    provisioning (issue #15 step 3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
