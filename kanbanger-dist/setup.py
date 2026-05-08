from setuptools import setup

setup(
    name="kanban-project-sync",
    version="0.1.0",
    description="Sync markdown kanban boards to GitHub Projects",
    author="Fab2",
    py_modules=["sync_kanban", "setup_wizard"],
    install_requires=[
        "requests>=2.25.0",
        "python-dotenv>=0.19.0",
    ],
    entry_points={
        "console_scripts": [
            "kanban-sync=sync_kanban:main",
            "kanban-sync-setup=setup_wizard:main",
        ],
    },
    python_requires=">=3.8",
)
