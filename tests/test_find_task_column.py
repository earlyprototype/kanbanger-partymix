"""Tests for _find_task_column helper (D9, Bundle 1b item 1)."""

from __future__ import annotations


def test_find_task_in_doing(kanban_workspace):
    """Helper locates a seeded task in the DOING column."""
    board = kanban_workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    board.write_text(
        text.replace("## DOING\n", "## DOING\n*   [ ] Task A\n", 1),
        encoding="utf-8",
    )

    from kanbanger.tools import _find_task_column

    lines = board.read_text(encoding="utf-8").split("\n")
    column, index, line = _find_task_column(lines, "Task A")

    assert column == "DOING"
    assert index is not None and index >= 0
    assert line is not None and "Task A" in line


def test_find_task_in_review(kanban_workspace):
    """Helper visits all columns -- finds a task seeded in REVIEW."""
    board = kanban_workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    board.write_text(
        text.replace("## REVIEW\n", "## REVIEW\n*   [ ] Task B\n", 1),
        encoding="utf-8",
    )

    from kanbanger.tools import _find_task_column

    lines = board.read_text(encoding="utf-8").split("\n")
    column, index, line = _find_task_column(lines, "Task B")

    assert column == "REVIEW"
    assert "Task B" in line


def test_find_task_not_found(kanban_workspace):
    """Not-found returns the (None, None, None) tuple."""
    board = kanban_workspace / "_kanban.md"

    from kanbanger.tools import _find_task_column

    lines = board.read_text(encoding="utf-8").split("\n")
    column, index, line = _find_task_column(lines, "Nonexistent")

    assert column is None
    assert index is None
    assert line is None


def test_find_task_first_match_wins_in_document_order(kanban_workspace):
    """Duplicate titles: earlier column (in section order) wins."""
    board = kanban_workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    text = text.replace("## BACKLOG\n", "## BACKLOG\n*   [ ] Dup\n", 1)
    text = text.replace("## DOING\n", "## DOING\n*   [ ] Dup\n", 1)
    board.write_text(text, encoding="utf-8")

    from kanbanger.tools import _find_task_column

    lines = board.read_text(encoding="utf-8").split("\n")
    column, _, _ = _find_task_column(lines, "Dup")

    assert column == "BACKLOG"
