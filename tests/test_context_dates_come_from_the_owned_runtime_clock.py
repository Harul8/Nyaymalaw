"""Compaction/recovery do not silently switch from the captured forum clock."""
import json
from datetime import date

import pytest

from nm.legal_brain.understand.brain_context import (
    ContextPolicy,
    ContextRefused,
    ContextSession,
    assemble_brief,
)
from tests.test_brain_context_is_a_checked_file_projection import file_fixture, snapshot, tools

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("recovered", [False, True])
def test_live_and_restored_compaction_use_the_supplied_clock_not_saved_or_wall_date(recovered):
    matter = file_fixture()
    policy = ContextPolicy()
    original_day, next_day = date(2031, 1, 2), date(2031, 1, 3)
    ticks = []

    def today():
        ticks.append(next_day)
        return next_day

    session = ContextSession(snapshot(), tools(), assemble_brief(
        matter, (), policy, advocate_id=matter.advocate_id, as_of=original_day),
        provider="scripted", model="clock-control", policy=policy, today=today)
    if recovered:
        original = session.to_record()
        session = ContextSession.from_record(original, matter, advocate_id=matter.advocate_id,
                                              policy=policy, today=today)
        assert session.to_record() == original and not ticks
    session.compact(matter, reason="Owned runtime date control")
    assert ticks == [next_day]
    assert json.loads(session.brief.text)["data"]["checklist_context_as_of"] == next_day.isoformat()
    assert matter == file_fixture(), "Clock observation must not establish any case date"


def test_non_callable_clock_is_not_restored_from_model_or_journal_data():
    matter = file_fixture()
    with pytest.raises(ContextRefused, match="forum date"):
        ContextSession(snapshot(), tools(), assemble_brief(matter, (), advocate_id=matter.advocate_id),
                       provider="scripted", model="clock-control", today="2031-01-03")
