"""Tests for kanban_io.ensure_review_column (REVIEW auto-injection)."""

from __future__ import annotations

from pathlib import Path


def _write_board(workspace: Path, columns: list[str]) -> None:
    body = "# Test Kanban\n\n" + "".join(f"## {c}\n\n" for c in columns)
    (workspace / "_kanban.md").write_text(body, encoding="utf-8")


def test_migrates_four_column_board(kanban_workspace):
    # Overwrite the fixture's 5-column board with a 4-column v2.x shape.
    _write_board(kanban_workspace,
                 ["BACKLOG", "TODO", "DOING", "DONE"])

    import kanban_io

    migrated = kanban_io.ensure_review_column(kanban_workspace)

    assert migrated is True
    text = (kanban_workspace / "_kanban.md").read_text(encoding="utf-8")
    assert text.index("## REVIEW") > text.index("## DOING")
    assert text.index("## REVIEW") < text.index("## DONE")


def test_no_op_on_five_column_board(kanban_workspace):
    # The fixture default IS 5-column. Migration should report no work.
    import kanban_io

    before = (kanban_workspace / "_kanban.md").read_text(encoding="utf-8")
    migrated = kanban_io.ensure_review_column(kanban_workspace)
    after = (kanban_workspace / "_kanban.md").read_text(encoding="utf-8")

    assert migrated is False
    assert before == after


def test_no_board_returns_false(kanban_workspace):
    (kanban_workspace / "_kanban.md").unlink()
    import kanban_io

    migrated = kanban_io.ensure_review_column(kanban_workspace)

    assert migrated is False
