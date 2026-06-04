from setuptools import setup, find_packages

setup(
    name="kanbanger-partymix",
    version="0.0.1",
    description="Sync markdown kanban boards to GitHub Projects with MCP server support",
    author="Fab2",
    packages=find_packages(),
    py_modules=["sync_kanban", "kanban_io", "kanban_doctor"],
    install_requires=[
        "requests>=2.25.0",
        "python-dotenv>=0.19.0",
    ],
    extras_require={
        # Native MCP SDK (FastMCP). Capped below 2.0 on purpose: mcp v2
        # renames FastMCP -> MCPServer and moves transport params onto
        # run(), which would break kanbanger_mcp.server. Bump
        # deliberately when porting to the v2 API. (Replaced mcp-use,
        # dropped 2026-06-04 — see DECISION-drop-mcp_use.)
        "mcp": [
            "mcp>=1.12.0,<2.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "kanban-sync=sync_kanban:main",
            "kanban-doctor=kanban_doctor:main",
            "kanbanger-mcp=kanbanger_mcp.server:main",
        ],
    },
    python_requires=">=3.10",
)
