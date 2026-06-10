"""Smoke test: kanban_io + kanbanger.tools import cleanly."""

from __future__ import annotations


def test_kanban_io_imports():
    import kanban_io

    assert hasattr(kanban_io, "discover_columns")
    assert hasattr(kanban_io, "parse_task_title_with_description")
    assert hasattr(kanban_io, "atomic_write_text")
    assert hasattr(kanban_io, "kanban_lock")


def test_tools_register_against_stub(registered_tools):
    for name in ("add_task", "move_task", "delete_task", "list_tasks"):
        assert name in registered_tools, f"missing {name}"
        assert callable(registered_tools[name])


def test_prompts_register_against_stub(registered_prompts):
    for name in ("kanban_awareness", "task_planning", "daily_standup",
                 "github_sync_check"):
        assert name in registered_prompts, f"missing {name}"
        assert callable(registered_prompts[name])
