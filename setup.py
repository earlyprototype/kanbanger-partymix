import re
from pathlib import Path

from setuptools import setup, find_packages


def read_version() -> str:
    """Single source of truth for the version: kanbanger/__init__.py.

    setup.py must NOT hardcode a version (it drifted from the package for a
    while: 0.0.1 here vs 2.1.0 in the package). Parse __version__ out of the
    package's __init__.py without importing it — importing would require the
    package's runtime deps (mcp, etc.) to be present just to read the version,
    which breaks a clean `pip install .` from a bare source tree.
    """
    init_path = Path(__file__).resolve().parent / "kanbanger" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not find __version__ in {init_path}")
    return match.group(1)


setup(
    name="kanbanger-partymix",
    version=read_version(),
    description="Sync markdown kanban boards to GitHub Projects with MCP server support",
    author="Fab2",
    packages=find_packages(exclude=["tests", "tests.*"]),
    py_modules=["sync_kanban", "kanban_io", "kanban_doctor"],
    install_requires=[
        "requests>=2.25.0",
        "python-dotenv>=0.19.0",
        # Native MCP SDK (FastMCP) is a HARD runtime dependency, not optional:
        # the kanbanger-mcp console script (kanbanger.server:main) imports
        # `mcp.server.fastmcp` at module load, so a base `pip install .` must
        # pull it or the entry point ImportErrors. Capped below 2.0 on purpose:
        # mcp v2 renames FastMCP -> MCPServer and moves transport params onto
        # run(), which would break kanbanger.server. Bump deliberately when
        # porting to the v2 API. (Replaced mcp-use, dropped 2026-06-04 — see
        # DECISION-drop-mcp_use.)
        "mcp>=1.12.0,<2.0.0",
    ],
    extras_require={
        # Back-compat alias: `mcp` is now a base dependency (above), but the
        # `[mcp]` extra is retained as a no-op-ish alias so existing docs /
        # commands that say `pip install .[mcp]` keep working.
        "mcp": [
            "mcp>=1.12.0,<2.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "kanban-sync=sync_kanban:main",
            "kanban-doctor=kanban_doctor:main",
            "kanbanger-mcp=kanbanger.server:main",
            # CLI-parity sibling of the in-MCP setup_project tool:
            # `kanbanger init` provisions a project via kanbanger.provision.
            "kanbanger=kanbanger.cli:main",
        ],
    },
    python_requires=">=3.10",
)
