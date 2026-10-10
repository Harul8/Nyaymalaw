"""A retired board cannot report successful empty work or break other readers."""
from datetime import date

import pytest

from nm.work_the_file.projections_api import _deadline_window, board_projection, latest_first

pytestmark = pytest.mark.class_a


def test_retired_board_refuses_before_reading_or_mutating_the_matter():
    class UnreadableMatter:
        def __getattribute__(self, name):
            raise AssertionError("A retired board must not inspect saved state")

    with pytest.raises(NotImplementedError, match="historical matter board is retired"):
        board_projection(UnreadableMatter(), None)


def test_retained_reader_does_not_promote_unknown_deadlines_to_an_empty_assessment():
    result = _deadline_window(None, date(2026, 10, 10))
    assert result["deadline_assessment"] == "not_assessed"
    assert result["next_deadline_status"] == "not_assessed"


def test_independent_empty_list_reader_remains_available():
    assert latest_first([]) == []
