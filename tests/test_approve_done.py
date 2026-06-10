"""Tests for approve_done (REVIEW -> DONE)."""

from __future__ import annotations

import json


def _seed_review_task(workspace, title="Task A"):
    board = workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    text = text.replace("## REVIEW\n",
                        f"## REVIEW\n*   [ ] {title}\n", 1)
    board.write_text(text, encoding="utf-8")


def _seed_task_in_column(workspace, title, column):
    board = workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    text = text.replace(f"## {column}\n",
                        f"## {column}\n*   [ ] {title}\n", 1)
    board.write_text(text, encoding="utf-8")


def test_approve_done_happy_path(registered_tools, kanban_workspace):
    _seed_review_task(kanban_workspace, "Task A")
    approve_done = registered_tools["approve_done"]

    result = json.loads(approve_done("Task A"))

    assert result["success"] is True
    assert result["task"]["title"] == "Task A"
    assert result["task"]["from_column"] == "REVIEW"
    assert result["task"]["to_column"] == "DONE"

    board = (kanban_workspace / "_kanban.md").read_text(encoding="utf-8")
    done_section = board.split("## DONE")[1]
    assert "*   [x] Task A" in done_section
    review_section = board.split("## REVIEW")[1].split("##")[0]
    assert "Task A" not in review_section


def test_approve_done_task_not_found(registered_tools, kanban_workspace):
    approve_done = registered_tools["approve_done"]

    result = json.loads(approve_done("Nonexistent"))

    assert result["success"] is False
    assert result["error_code"] == "task_not_found"


def test_approve_done_invalid_state_when_in_doing(registered_tools,
                                                  kanban_workspace):
    _seed_task_in_column(kanban_workspace, "Task A", "DOING")
    approve_done = registered_tools["approve_done"]

    result = json.loads(approve_done("Task A"))

    assert result["success"] is False
    assert result["error_code"] == "invalid_state"
    assert result["context"]["current_column"] == "DOING"


def test_approve_done_invalid_state_when_in_todo(registered_tools,
                                                 kanban_workspace):
    _seed_task_in_column(kanban_workspace, "Task A", "TODO")
    approve_done = registered_tools["approve_done"]

    result = json.loads(approve_done("Task A"))

    assert result["success"] is False
    assert result["error_code"] == "invalid_state"
    assert result["context"]["current_column"] == "TODO"


def test_approve_done_kanban_not_found(registered_tools, kanban_workspace):
    (kanban_workspace / "_kanban.md").unlink()
    approve_done = registered_tools["approve_done"]

    result = json.loads(approve_done("Task A"))

    assert result["success"] is False
    assert result["error_code"] == "kanban_not_found"


def test_approve_done_write_failed(registered_tools, kanban_workspace,
                                   monkeypatch):
    _seed_review_task(kanban_workspace, "Task A")
    import kanbanger.tools as tools_mod

    def _boom(*_args, **_kwargs):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(tools_mod, "atomic_write_text", _boom)
    approve_done = registered_tools["approve_done"]

    result = json.loads(approve_done("Task A"))

    assert result["success"] is False
    assert result["error_code"] == "write_failed"
