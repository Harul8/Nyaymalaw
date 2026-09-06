"""B-091 — the other side is on the record, and stays there.

THE MEASURED DEFECT
---------------------
`Posture.opponent` was declared, typed, persisted, and written by NOTHING. Two
consumers read it, and both had a fallback:

    nm/edge/projections.py   "against": posture.opponent or "unknown"
    nm/domain/summary.py     omits the line when it is empty

So an advocate who wrote "we act for the plaintiff against Sharma" saw
`against: unknown` on the record for the life of the matter, and every model
call after that reasoned about the matter without the other side's name in
front of it. Nothing failed. Nothing was logged. The field simply never filled.

It was found by an ENUMERATOR and not by hand -- see
test_every_persisted_field_has_a_writer, which is the general mechanism. This
file is the one field that had to be wired rather than declared.

WHY IT IS ON THE READ THAT ALREADY EXISTS
--------------------------------------------
B-086's lesson. The posture read is already looking at the sentence that names
the opponent; a second read reconstructing it from the account would throw the
evidence away and ask a harder question without it.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core import posture
from nm.core.turn import TurnInput
from nm.domain.quotable import Quotable
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

TODAY = date(2026, 9, 5)


def _read(message: str, **over):
    data = {"states_client": True, "role": "plaintiff", "role_basis": "stated",
            "client_described_as": "", "opponent": "", "quoted": message}
    return posture.interpret(Quotable(turn=message), {**data, **over})


# ============================== the read ===================================

def test_the_opponent_is_taken_from_what_the_advocate_said():
    stated = _read("we act for the plaintiff against Sharma",
                   opponent="Sharma")
    assert stated.opponent == "Sharma"


def test_no_opponent_named_is_none_and_not_an_empty_string():
    """`None` and `''` both read as absent HERE, so this is not a three-state
    question -- it is that the record must not carry a name-shaped blank that
    renders as an empty cell beside a populated one."""
    assert _read("we act for the plaintiff").opponent is None


def test_a_value_that_names_nobody_is_not_recorded():
    """THE SAME MECHANISM AS THE DESCRIPTOR, not a second one.

    "the opposite party" is a grammatical placeholder, and recording it makes
    the record say the opponent is known while telling the advocate nothing
    they did not write. `names_nobody` is the one place that judgement lives;
    a fourth private copy of it is the B-084 shape.
    """
    assert _read("we act for the plaintiff against the opposite party",
                 opponent="the opposite party").opponent is None


def test_an_account_that_states_no_client_names_no_opponent():
    """`states_client` gates the whole read. A message that merely describes
    events -- 'the landlord issued a quit notice' -- states nothing about
    sides, and pulling an opponent out of it would be the inference C3
    forbids arriving through a different field."""
    assert _read("the landlord issued a quit notice against the tenant",
                 states_client=False).opponent is None


# ========================== on a served turn ===============================

def test_the_opponent_reaches_the_record(tmp_path):
    """VERIFIED ON THE BYTES (CLAUDE.md 8).

    The read returning it proves nothing: this defect lived entirely between
    a correct read and a record that never received the value.
    """
    engine, store = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff against Sharma on an agreement of "
                 "sale at Hyderabad.")))

    saved = store.load(out.matter.id)
    assert saved.threads[0].posture.opponent == "Sharma", (
        "the opponent was read and did not reach the persisted posture: "
        f"{saved.threads[0].posture}")


def test_the_record_shown_to_the_advocate_says_who_they_are_against(tmp_path):
    """The projection is what an advocate actually reads. It had `unknown`
    hard-wired into it by a field nothing filled."""
    from nm.edge import projections

    engine, store = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff against Sharma on an agreement of "
                 "sale at Hyderabad.")))

    saved = store.load(out.matter.id)
    board = projections.board_projection(saved, deadlines=None, today=TODAY)
    against = [row["against"] for row in board["threads"]]
    assert against == ["Sharma"], (
        f"the board still says the opponent is unknown: {against}")


def test_the_opponent_survives_the_next_turn(tmp_path):
    """MONOTONIC, and this is the half that makes it memory rather than a
    field that happened to be set once.

    The turn-5 reversal was a stated value silently changing later. The
    opponent is a party, so the first name recorded stands; a later turn that
    does not mention them must not blank it, and one that names someone else
    must not overwrite it silently.
    """
    engine, store = build(tmp_path)
    first = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff against Sharma on an agreement of "
                 "sale at Hyderabad.")))
    engine.run(TurnInput(
        advocate_id="adv_1", matter_id=first.matter.id, today=TODAY,
        message="The agreement is dated 15 April 2024."))

    saved = store.load(first.matter.id)
    assert saved.threads[0].posture.opponent == "Sharma", (
        "a turn that said nothing about the other side erased them")


def test_the_summary_carries_the_opponent_into_the_next_call(tmp_path):
    """The account is what every downstream model call sees. An opponent on
    the record and absent from the account is memory the product holds and
    does not use, which is the leak this was found inside."""
    from nm.domain import summary

    engine, store = build(tmp_path)
    out = engine.run(TurnInput(
        advocate_id="adv_1", today=TODAY,
        message=("We act for the plaintiff against Sharma on an agreement of "
                 "sale at Hyderabad.")))

    saved = store.load(out.matter.id)
    account = summary.build(saved, saved.threads[0].id).account
    assert "Sharma" in account, (
        "the opponent is on the record and not in the account sent to the "
        f"model:\n{account}")
