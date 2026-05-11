"""Tests for reject_review (Pattern C - REVIEW -> DONE + TODO Rework)."""

from __future__ import annotations

import json


def _seed_review_task(workspace, title="Task A", description=None):
    """Append a task to REVIEW. Optional description after ` - `."""
    board = workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    if description:
        line = f"*   [ ] {title} - {description}\n"
    else:
        line = f"*   [ ] {title}\n"
    text = text.replace("## REVIEW\n", f"## REVIEW\n{line}", 1)
    board.write_text(text, encoding="utf-8")


def test_reject_review_happy_path(registered_tools, kanban_workspace):
    _seed_review_task(kanban_workspace, "Task A")
    reject_review = registered_tools["reject_review"]

    result = json.loads(
        reject_review("Task A", reason="needs more tests")
    )

    assert result["success"] is True
    assert result["original"]["from_column"] == "REVIEW"
    assert result["original"]["to_column"] == "DONE"
    assert "REJECTED: needs more tests" in result["original"]["annotation"]
    assert result["rework"]["title"] == "Rework: Task A"
    assert result["rework"]["column"] == "TODO"
    assert result["rework"]["reason"] == "needs more tests"

    board = (kanban_workspace / "_kanban.md").read_text(encoding="utf-8")
    done = board.split("## DONE")[1]
    assert "*   [x] Task A - REJECTED: needs more tests" in done
    assert "rework: Rework: Task A" in done
    todo = board.split("## TODO")[1].split("##")[0]
    assert "*   [ ] Rework: Task A - Reason: needs more tests" in todo
    assert "Original task: Task A" in todo
    review = board.split("## REVIEW")[1].split("##")[0]
    assert "Task A" not in review


def test_reject_review_with_existing_description(registered_tools,
                                                 kanban_workspace):
    _seed_review_task(kanban_workspace, "Task A",
                      description="original work notes")
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Task A", reason="needs polish"))

    assert result["success"] is True
    board = (kanban_workspace / "_kanban.md").read_text(encoding="utf-8")
    done = board.split("## DONE")[1]
    assert "REJECTED: needs polish" in done
    assert "rework: Rework: Task A" in done


def test_reject_review_task_not_found(registered_tools, kanban_workspace):
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Nonexistent", reason="x"))

    assert result["success"] is False
    assert result["error_code"] == "task_not_found"


def test_reject_review_invalid_state_when_in_doing(registered_tools,
                                                   kanban_workspace):
    board = kanban_workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    board.write_text(text.replace("## DOING\n",
                                  "## DOING\n*   [ ] Task A\n", 1),
                     encoding="utf-8")
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Task A", reason="x"))

    assert result["success"] is False
    assert result["error_code"] == "invalid_state"
    assert result["context"]["current_column"] == "DOING"


def test_reject_review_missing_reason_none(registered_tools, kanban_workspace):
    _seed_review_task(kanban_workspace, "Task A")
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Task A", reason=None))

    assert result["success"] is False
    assert result["error_code"] == "missing_reason"


def test_reject_review_missing_reason_empty(registered_tools, kanban_workspace):
    _seed_review_task(kanban_workspace, "Task A")
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Task A", reason=""))

    assert result["success"] is False
    assert result["error_code"] == "missing_reason"


def test_reject_review_missing_reason_whitespace(registered_tools,
                                                 kanban_workspace):
    _seed_review_task(kanban_workspace, "Task A")
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Task A", reason="   "))

    assert result["success"] is False
    assert result["error_code"] == "missing_reason"


def test_reject_review_kanban_not_found(registered_tools, kanban_workspace):
    (kanban_workspace / "_kanban.md").unlink()
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Task A", reason="x"))

    assert result["success"] is False
    assert result["error_code"] == "kanban_not_found"
