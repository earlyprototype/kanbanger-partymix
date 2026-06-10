"""
kanbanger.cli — thin console entry points.

`kanbanger init` is the CLI-parity sibling of the in-MCP `setup_project` tool:
both call `kanbanger.provision.provision_project`, so behaviour is identical.
Use it to provision a project from a terminal when you'd rather not go through
an MCP client.

    kanbanger init [PROJECT_DIR]      # default: current working directory
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .provision import provision_project


def init(argv=None) -> int:
    """Provision a project (default: cwd) for kanbanger. Idempotent.

    Mirrors the MCP `setup_project` tool via the shared provisioning code.
    Returns a process exit code (0 success, 1 on a bad project dir).
    """
    parser = argparse.ArgumentParser(
        prog="kanbanger init",
        description="Provision a project for kanbanger (idempotent). Scaffolds "
                    "_kanban.md, the CLAUDE.md agent touchpoint, .mcp.json with "
                    "empty GitHub-sync placeholders, and .gitignore hygiene. "
                    "Identical to the in-MCP setup_project tool.",
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory to provision (default: current working directory)",
    )
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: project directory not found: {project_dir}", file=sys.stderr)
        return 1

    try:
        result = provision_project(project_dir)
    except FileNotFoundError as e:
        # TOCTOU window: the directory passed the is_dir() pre-check above
        # but vanished before provisioning ran (provision_project re-checks
        # and raises). Report it like any other bad-project-dir error.
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(result.summary())
    return 0


def main(argv=None) -> int:
    """Dispatch `kanbanger <subcommand>`. Currently: `init`.

    Kept tiny on purpose — the server has its own `kanbanger-mcp` entry point;
    this is the human-facing CLI surface for provisioning parity.
    """
    parser = argparse.ArgumentParser(
        prog="kanbanger",
        description="Kanbanger command-line interface.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "init",
        help="Provision the current (or given) project for kanbanger.",
        add_help=False,
    )

    args, rest = parser.parse_known_args(argv)
    if args.command == "init":
        return init(rest)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
