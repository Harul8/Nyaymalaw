"""Both engines screen the recorded party set, never their inferred actor."""
from __future__ import annotations

from dataclasses import replace

import pytest

from nm.legal_brain.understand.parties import on_file
from nm.legal_brain.orchestrate.turn import TurnEngine
from nm.work_the_file.matter_contracts import Matter, Posture, Thread

pytestmark = pytest.mark.class_a


def test_all_intake_and_dispute_parties_are_preserved_in_the_same_projection():
    matter = Matter("mat_projection", "adv_Actor", "The invented title must not be screened",
                    intake_parties={"Our Client": "client", "Their Company": "adverse"},
                    threads=(Thread("thr_one", "Recorded first dispute",
                                    parties={"Related Guarantor": "related"}),
                             Thread("thr_two", "Recorded second dispute",
                                    parties={"Another Opponent": "adverse"})))
    projected = on_file(matter)
    assert tuple((row.name, row.side) for row in projected.parties) == (
        ("Our Client", "client"), ("Their Company", "adverse"),
        ("Related Guarantor", "related"), ("Another Opponent", "adverse"))
    assert projected.names == frozenset({"our client", "their company",
                                         "related guarantor", "another opponent"})
    assert projected.display_for("another opponent") == "Another Opponent"
    assert projected.why == "4 party(ies) recorded on this matter"
    assert object.__new__(TurnEngine)._parties_of(matter) == projected


def test_a_title_actor_or_posture_is_not_an_admitted_party():
    matter = Matter("mat_projection", "adv_Actor", "Someone vs a Company",
                    threads=(Thread("thr_one", "An unadmitted Party in a label",
                                    posture=Posture(opponent="An unadmitted Party")),))
    projected = on_file(matter)
    assert not projected.named and not projected.names
    assert projected.why == "no party is recorded on this matter"
    assert object.__new__(TurnEngine)._parties_of(matter) == projected


def test_duplicate_and_distinct_recorded_sides_are_not_silently_rewritten():
    matter = Matter("mat_projection", "adv_Actor", "Recorded matter",
                    intake_parties={"Original Name": "client"},
                    threads=(Thread("thr_one", "Recorded dispute",
                                    parties={"Original Name": "related"}),))
    projected = on_file(matter)
    assert tuple(row.side for row in projected.parties) == ("client", "related")
    assert projected.side_of("original name") == "client"
    changed = replace(matter, threads=())
    assert len(on_file(changed).parties) == 1
    assert len(projected.parties) == 2
