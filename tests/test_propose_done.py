"""Tests for propose_done (DOING -> REVIEW)."""

from __future__ import annotations

import json


def _seed_doing_task(workspace, title="Task A"):
    """Append a task to DOING in the fixture board. Returns nothing."""
    board = workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    text = text.replace("## DOING\n",
                        f"## DOING\n*   [ ] {title}\n", 1)
    board.write_text(text, encoding="utf-8")


def test_propose_done_happy_path(registered_tools, kanban_workspace):
    _seed_doing_task(kanban_workspace, "Task A")
    propose_done = registered_tools["propose_done"]

    result = json.loads(propose_done("Task A"))

    assert result["success"] is True
    assert result["task"]["title"] == "Task A"
    assert result["task"]["from_column"] == "DOING"
    assert result["task"]["to_column"] == "REVIEW"

    board = (kanban_workspace / "_kanban.md").read_text(encoding="utf-8")
    doing_section = board.split("## DOING")[1].split("##")[0]
    review_section = board.split("## REVIEW")[1].split("##")[0]
    assert "Task A" not in doing_section
    assert "Task A" in review_section


def test_propose_done_task_not_found(registered_tools, kanban_workspace):
    propose_done = registered_tools["propose_done"]

    result = json.loads(propose_done("Nonexistent"))

    assert result["success"] is False
    assert result["error_code"] == "task_not_found"


def test_propose_done_invalid_state_when_in_todo(registered_tools,
                                                 kanban_workspace):
    board = kanban_workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    board.write_text(text.replace("## TODO\n",
                                  "## TODO\n*   [ ] Task A\n", 1),
                     encoding="utf-8")
    propose_done = registered_tools["propose_done"]

    result = json.loads(propose_done("Task A"))

    assert result["success"] is False
    assert result["error_code"] == "invalid_state"
    assert result["context"]["current_column"] == "TODO"


def test_propose_done_kanban_not_found(registered_tools, kanban_workspace):
    (kanban_workspace / "_kanban.md").unlink()
    propose_done = registered_tools["propose_done"]

    result = json.loads(propose_done("Task A"))

    assert result["success"] is False
    assert result["error_code"] == "kanban_not_found"


def test_propose_done_write_failed(registered_tools, kanban_workspace,
                                   monkeypatch):
    _seed_doing_task(kanban_workspace, "Task A")
    import kanbanger.tools as tools_mod

    def _boom(*_args, **_kwargs):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(tools_mod, "atomic_write_text", _boom)
    propose_done = registered_tools["propose_done"]

    result = json.loads(propose_done("Task A"))

    assert result["success"] is False
    assert result["error_code"] == "write_failed"
