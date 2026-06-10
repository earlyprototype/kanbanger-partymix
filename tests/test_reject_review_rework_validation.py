"""Tests for reject_review Rework title validation (S7, Bundle 1b item 3)."""

from __future__ import annotations

import json


def _seed_review_task(workspace, title):
    """Seed a task in the REVIEW column of the fixture board."""
    board = workspace / "_kanban.md"
    text = board.read_text(encoding="utf-8")
    text = text.replace(
        "## REVIEW\n",
        f"## REVIEW\n*   [ ] {title}\n",
        1,
    )
    board.write_text(text, encoding="utf-8")


def test_reject_review_happy_normal_title_unchanged(registered_tools, kanban_workspace):
    """Normal-length title -> normal Rework title; no regression on existing happy path."""
    _seed_review_task(kanban_workspace, "Task A")
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review("Task A", reason="needs more tests"))

    assert result["success"] is True
    assert result["rework"]["title"] == "Rework: Task A"


def test_reject_review_rework_title_over_cap_fails(registered_tools, kanban_workspace):
    """Original near 500-char cap -> Rework exceeds cap -> invalid_title."""
    from kanbanger.tools import TITLE_MAX_LEN

    long_title = "X" * (TITLE_MAX_LEN - 4)
    _seed_review_task(kanban_workspace, long_title)
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review(long_title, reason="x"))

    assert result["success"] is False
    assert result["error_code"] == "invalid_title"
    assert result["context"]["original_title_length"] == TITLE_MAX_LEN - 4
    assert result["context"]["rework_title_length"] > TITLE_MAX_LEN
    assert result["context"]["max_length"] == TITLE_MAX_LEN


def test_reject_review_rework_title_at_cap_passes(registered_tools, kanban_workspace):
    """Boundary: Rework title exactly at cap is still valid (validator uses >, not >=)."""
    from kanbanger.tools import TITLE_MAX_LEN

    boundary_title = "X" * (TITLE_MAX_LEN - 8)
    _seed_review_task(kanban_workspace, boundary_title)
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review(boundary_title, reason="x"))

    assert result["success"] is True
    assert len(result["rework"]["title"]) == TITLE_MAX_LEN


def test_reject_review_rework_failure_does_not_mutate_board(registered_tools, kanban_workspace):
    """invalid_title return leaves the original in REVIEW (atomic property)."""
    from kanbanger.tools import TITLE_MAX_LEN

    long_title = "X" * (TITLE_MAX_LEN - 4)
    _seed_review_task(kanban_workspace, long_title)
    board = kanban_workspace / "_kanban.md"
    before = board.read_text(encoding="utf-8")

    reject_review = registered_tools["reject_review"]
    reject_review(long_title, reason="x")

    after = board.read_text(encoding="utf-8")
    assert before == after, (
        "S7 invalid_title must not mutate the board; the original "
        "task must remain in REVIEW"
    )


def test_reject_review_rework_validation_preserves_other_rules(
    registered_tools, kanban_workspace
):
    """underlying_error reaches the caller -- proves the validator's full rule set
    is applied uniformly, not just the length cap."""
    from kanbanger.tools import TITLE_MAX_LEN

    long_title = "X" * (TITLE_MAX_LEN - 4)
    _seed_review_task(kanban_workspace, long_title)
    reject_review = registered_tools["reject_review"]

    result = json.loads(reject_review(long_title, reason="x"))

    assert "character limit" in result["context"]["underlying_error"]
