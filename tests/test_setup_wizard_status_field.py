"""Unit tests for setup_wizard.check_status_field.

Locks in the 5-column (partymix) Status requirement that the setup
wizard must keep in lockstep with kanban_doctor.check_status_field.
Without these, a revert of the `Review` requirement in setup_wizard
would pass unnoticed.
"""

import setup_wizard


def _project(option_names):
    """Build a minimal Projects-V2 dict with a Status single-select field."""
    return {
        "fields": {
            "nodes": [
                {
                    "name": "Status",
                    "options": [{"name": n} for n in option_names],
                }
            ]
        }
    }


def test_check_status_field_requires_review():
    """A 4-column board (no Review) must be rejected."""
    project = _project(["Backlog", "Todo", "InProgress", "Done"])
    assert setup_wizard.check_status_field(project) is False


def test_check_status_field_passes_on_full_five():
    """All five partymix columns present -> accepted."""
    project = _project(["Backlog", "Todo", "InProgress", "Review", "Done"])
    assert setup_wizard.check_status_field(project) is True
