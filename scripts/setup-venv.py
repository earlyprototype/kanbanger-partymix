#!/usr/bin/env python3
"""
setup-venv.py — Provision a per-project Kanbanger MCP environment.

Creates `<PROJECT>/.venv`, installs the partymix package editable into it,
writes `<PROJECT>/.mcp.json` pinned to that venv's python.exe, and ensures
`.venv/` is gitignored.

This is the cure for the v2.1.0/partymix `kanbanger_mcp` import collision:
each project gets its own isolated kanbanger install, so there is no
system-wide pip surgery and no silent shadowing.

Usage:
    python <partymix>/scripts/setup-venv.py [PROJECT_DIR]

PROJECT_DIR defaults to the current working directory.

Exit codes:
    0 - success
    1 - usage / preflight error
    2 - subprocess failure (venv creation, pip install)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PARTYMIX_SOURCE = Path(__file__).resolve().parent.parent
GITIGNORE_ENTRY = ".venv/"
GITIGNORE_HEADER = "# Per-project venv created by kanbanger-partymix/scripts/setup-venv.py"


def venv_python_path(venv_dir: Path) -> Path:
    """Return the path to the venv's python interpreter for the host platform."""
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def to_forward_slashes(p) -> str:
    return str(p).replace("\\", "/")


def build_mcp_config(project_dir: Path, venv_python: Path) -> dict:
    project_path_fwd = to_forward_slashes(project_dir)
    return {
        "mcpServers": {
            "kanbanger": {
                "command": to_forward_slashes(venv_python),
                "args": ["-m", "kanbanger_mcp"],
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


def run(cmd, **kwargs):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        sys.exit(2)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision a per-project venv with kanbanger-partymix installed.",
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
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: project directory not found: {project_dir}", file=sys.stderr)
        return 1
    if not PARTYMIX_SOURCE.is_dir() or not (PARTYMIX_SOURCE / "setup.py").is_file():
        print(f"ERROR: partymix source not found at {PARTYMIX_SOURCE}", file=sys.stderr)
        return 1

    venv_dir = project_dir / ".venv"
    venv_python = venv_python_path(venv_dir)

    print("kanbanger-partymix per-project venv setup")
    print(f"  project: {project_dir}")
    print(f"  venv:    {venv_dir}")
    print(f"  source:  {PARTYMIX_SOURCE}")
    print()

    if venv_dir.exists():
        print("Step 1: venv already exists, reusing.")
    else:
        print("Step 1: creating venv...")
        run([sys.executable, "-m", "venv", str(venv_dir)])

    print("\nStep 2: upgrading pip in venv...")
    run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"])

    print("\nStep 3: installing partymix editable with [mcp] extras...")
    run([str(venv_python), "-m", "pip", "install", "-e", f"{PARTYMIX_SOURCE}[mcp]", "--quiet"])

    print("\nStep 4: verifying kanbanger_mcp resolves to partymix source...")
    check = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import kanbanger_mcp, os; "
            "print(os.path.dirname(os.path.abspath(kanbanger_mcp.__file__)))",
        ],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        print("  FAIL: could not import kanbanger_mcp in the venv", file=sys.stderr)
        print(check.stderr, file=sys.stderr)
        return 2
    resolved = Path(check.stdout.strip())
    expected = (PARTYMIX_SOURCE / "kanbanger_mcp").resolve()
    if resolved.resolve() == expected:
        print(f"  OK: kanbanger_mcp -> {resolved}")
    else:
        print(f"  WARN: expected {expected}")
        print(f"        got      {resolved}")
        print("  (editable installs can show site-packages paths; verify manually.)")

    if not args.no_mcp_json:
        mcp_json = project_dir / ".mcp.json"
        print(f"\nStep 5: writing {mcp_json}")
        if mcp_json.exists():
            backup = project_dir / ".mcp.json.backup"
            print(f"  existing file backed up to {backup}")
            backup.write_text(mcp_json.read_text(encoding="utf-8"), encoding="utf-8")
        config = build_mcp_config(project_dir, venv_python)
        mcp_json.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote .mcp.json with command pinned to {venv_python}")

    if not args.no_gitignore:
        print("\nStep 6: ensuring .venv/ is gitignored")
        ensure_gitignore_has_venv(project_dir)

    print("\nDone.")
    print("Next:")
    print(f"  - Open a fresh Claude Code session in {project_dir}")
    print("  - Confirm kanbanger MCP loads (paste '/mcp' or call list_tasks)")
    print("  - Run `kanban-doctor` (after Step 3 of MVP plan ports it to partymix)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
