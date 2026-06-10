#!/usr/bin/env python3
"""
setup-venv.py — [DEPRECATED INSTALLER] per-project Kanbanger provisioning.

DEPRECATED (ADR 0002, issue #15): this script NO LONGER installs anything, and
its remaining provisioning role has moved IN-MCP.

The supported install path is now a SINGLE GLOBAL install, like any other MCP
server:

    pipx install <path-to-kanbanger-partymix>      # recommended
    # or
    pip install <path-to-kanbanger-partymix>

That gives you a working `kanbanger-mcp` server on PATH with no per-project
`.venv`. The old per-project venv only existed to dodge the `kanbanger_mcp`
import collision; the v3 module rename (`kanbanger_mcp` -> `kanbanger`) removed
that cause, so per-project installs are no longer needed.

The supported PROVISIONING path is now the in-MCP `setup_project` tool (issue
#15 step 3), or `kanbanger init` for CLI parity. This script is retained only
as a thin shim: it imports the SAME provisioning helpers from
`kanbanger.provision` and calls them, so it can never drift from the MCP tool.
Do not extend it — add to `kanbanger/provision.py` instead.

Usage:
    python <partymix>/scripts/setup-venv.py [PROJECT_DIR]

PROJECT_DIR defaults to the current working directory.

Exit codes:
    0 - success
    1 - usage / preflight error
"""
import argparse
import sys
from pathlib import Path

PARTYMIX_SOURCE = Path(__file__).resolve().parent.parent

# This script lives outside the package (hyphenated name in scripts/). When run
# directly from a source checkout the package may not be importable yet, so make
# the repo root importable before pulling the shared provisioning helpers. When
# kanbanger is installed (pipx/pip), the import resolves from site-packages.
if str(PARTYMIX_SOURCE) not in sys.path:
    sys.path.insert(0, str(PARTYMIX_SOURCE))

from kanbanger.provision import (  # noqa: E402  (sys.path tweak must precede)
    CLAUDE_MD_END,
    CLAUDE_MD_START,
    GITIGNORE_ENTRY,
    GITIGNORE_HEADER,
    build_claude_md_block,
    build_mcp_config,
    ensure_claude_md_has_kanbanger,
    ensure_gitignore_has_venv,
    provision_project,
    to_forward_slashes,
)

__all__ = [
    # Re-exported for back-compat: existing tests import these off this script
    # module by file path. The implementations now live in kanbanger.provision.
    "CLAUDE_MD_END",
    "CLAUDE_MD_START",
    "GITIGNORE_ENTRY",
    "GITIGNORE_HEADER",
    "build_claude_md_block",
    "build_mcp_config",
    "ensure_claude_md_has_kanbanger",
    "ensure_gitignore_has_venv",
    "main",
]


DEPRECATION_BANNER = """\
============================================================================
  setup-venv.py is DEPRECATED and installs NOTHING. Its provisioning role
  has moved IN-MCP.

  Install kanbanger ONCE, globally, like any other MCP server:

      pipx install "{source}"
      # or:  pip install "{source}"

  That puts `kanbanger-mcp` on your PATH. No per-project .venv is needed
  (the venv only ever existed to dodge the old kanbanger_mcp import
  collision, which the module rename removed — see ADR 0002).

  PREFER provisioning via the MCP `setup_project` tool, or `kanbanger init`
  for CLI parity. This script now only forwards to the same shared
  provisioning code (kanbanger.provision). Pass --no-provision to skip.
============================================================================
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="[DEPRECATED installer] Provision a project for the GLOBAL "
                    "kanbanger install. Creates no venv and installs nothing; "
                    "forwards to kanbanger.provision.",
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
        "--no-board",
        action="store_true",
        help="Skip scaffolding _kanban.md (leave the board to first-contact).",
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

    # Single shared code path — identical to the MCP `setup_project` tool.
    # AGENTS.md is augmented only if present (provision_project handles that),
    # so no separate flag is exposed here.
    result = provision_project(
        project_dir,
        scaffold_board=not args.no_board,
        write_mcp_json=not args.no_mcp_json,
        write_gitignore=not args.no_gitignore,
        write_claude_md=not args.no_claude_md,
        write_agents_md=True,
    )

    print(result.summary())

    print()
    print("Next:")
    print(f"  - Ensure kanbanger is installed globally: pipx install \"{to_forward_slashes(PARTYMIX_SOURCE)}\"")
    print(f"  - Open a fresh Claude Code session in {project_dir}")
    print("  - Confirm kanbanger MCP loads (paste '/mcp' or call list_tasks)")
    print("  - PREFER the in-MCP `setup_project` tool (or `kanbanger init`) next time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
