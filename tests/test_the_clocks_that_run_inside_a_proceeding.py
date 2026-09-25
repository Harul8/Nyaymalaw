"""LB-124. THE PERIODS THAT RUN INSIDE A PROCEEDING, NOT ONLY THE ONE TO FILE.

THE DEFECT THIS FILE IS ABOUT. Limitation decides whether a claim can be
brought at all, and it was the only clock this product computed. A proceeding
has others, and missing one of those loses the DEFENCE rather than the claim:
the written statement, leave to defend a summary suit, the life of a caveat. An
advocate who read a limitation position and nothing else had been told about
the clock least likely to be the one about to run out.

WHAT IS AND IS NOT CLAIMED HERE. This slice establishes which periods a ROLE
brings into play, whether each binds, and whether it can be extended. It
computes NO DATE: every period runs from a trigger -- service, an order, a
listing -- and whether that trigger happened, and when, is a fact about the
advocate's own file that nothing here reads. These tests hold that line in both
directions: a period never arrives with a guessed date, and never goes missing
because its date could not be computed.

AND THE TRACK IS NEVER PICKED. Order VIII r.1 reads one way on a commercial
suit of a specified value and another on an ordinary one. Choosing between them
because nobody said which is one sentence of confident wrong advice either way,
so the row is UNDECIDED and says so.
"""
from __future__ import annotations

from datetime import date

import pytest
from nm.core import deadlines
from nm.core.turn import TurnInput
from nm.domain.matter import Role
from nm.knowledge import procedural_period as curated
from nm.ports.procedural_period import Bindingness, Extension, Track

from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a


# ======================================= the table, and what it may not do ==

def test_every_curated_period_says_where_it_came_from():
    """`curated_from` IS THE WHOLE ARGUMENT FOR A CURATED TABLE. A period that
    cannot say where it came from is one somebody remembered, and a remembered
    procedural period loses a defence on a rule nobody can check."""
    assert curated.PERIODS, "the table is empty, so this checks nothing"
    for key, period in curated.PERIODS.items():
        assert period.key == key, f"{key}: keyed under another name"
        assert period.curated_from.strip(), key
        assert period.act.strip() and period.provision.strip(), key
        assert period.runs_from.strip(), key
        # THE CORPUS'S OWN KEY, not prose. A row that wrote "Order VIII rule 1
        # CPC" would look up nothing and report a gap in a Code held in full.
        assert " " not in period.provision, (
            f"{key}: {period.provision!r} is prose, not the store's key")


def test_no_row_states_a_number_of_days():
    """A PERIOD RECITED FROM MEMORY IS THE DEFECT THIS TABLE EXISTS TO REFUSE.

    Every row points at the provision that fixes the period; none of them
    states it. A figure written here would be a figure nobody retrieved, on
    the one question where being a fortnight out loses the pleading.
    """
    import re

    for key, period in curated.PERIODS.items():
        for field in (period.period_said, period.extension_said, period.said,
                      period.runs_from):
            assert not re.search(r"\b\d+\s*(day|days|week|weeks|month|months)\b",
                                 field), f"{key}: {field!r} recites a period"


def test_no_row_offers_section_5_as_the_extension_route():
    """LIMITATION ACT s.5 CONDONES DELAY IN INSTITUTING, not delay inside a
    suit already on foot. Offering it would send an advocate to make an
    application the court has no occasion to entertain. Each period is
    extended, if at all, by its own provision."""
    for key, period in curated.PERIODS.items():
        assert curated.NOT_THE_EXTENSION_ROUTE not in period.extension_said, key
        assert "s.5" not in period.extension_said, key


def test_a_period_is_reached_by_an_exact_key_and_never_by_words():
    """CLAUDE.md section 5. Engagement is decided by membership of the closed
    `Role` vocabulary. Nothing is matched approximately, so no description
    that merely reads like a defence engages the written-statement period."""
    for role in curated.BY_ROLE:
        assert isinstance(role, Role)
    for keys in curated.BY_ROLE.values():
        for key in keys:
            assert key in curated.PERIODS, key


# ===================================== bindingness and extension are two ====

def test_binding_and_extendable_are_separate_answers_and_the_table_proves_it():
    """THE PAIR IS WHAT THE ADVOCATE ACTS ON. If the two always moved
    together, one field would do and this row would be decoration. Order
    XXXVII r.3 is the counterexample the design exists for: the period binds
    AND the court may excuse the delay."""
    leave = curated.PERIODS["cpc_o37_r3_leave_to_defend"]
    assert leave.bindingness is Bindingness.MANDATORY
    assert leave.extension is Extension.AVAILABLE


def test_the_commercial_outer_limit_is_mandatory_and_not_extendable():
    """LB-124's NEVER, at the table. A defendant told the commercial outer
    limit can be extended files a pleading the court cannot take on record."""
    commercial = curated.PERIODS["cpc_o8_r1_written_statement_commercial"]
    assert commercial.bindingness is Bindingness.MANDATORY
    assert commercial.extension is Extension.BARRED
    assert commercial.track is Track.COMMERCIAL


def test_the_ordinary_reading_is_not_the_commercial_one():
    """THE TWO READINGS DIFFER IN BOTH FIELDS, which is why the track is part
    of the key rather than a footnote on one answer."""
    ordinary = curated.PERIODS["cpc_o8_r1_written_statement_ordinary"]
    commercial = curated.PERIODS["cpc_o8_r1_written_statement_commercial"]
    assert ordinary.bindingness is not commercial.bindingness
    assert ordinary.extension is not commercial.extension
    assert ordinary.track is Track.ORDINARY


# ================================================= engagement and silence ====

def test_an_unestablished_track_leaves_both_readings_undecided():
    """THE RULE LB-124 EXISTS FOR. Neither reading is served because nobody
    said which suit this is, and BOTH are named as undecided -- an advocate
    who reads nothing about the written statement concludes no such period
    runs."""
    running = curated.engaged(Role.DEFENDANT, Track.NOT_ESTABLISHED)
    keys = {r.period.key for r in running}
    assert "cpc_o8_r1_written_statement_ordinary" not in keys
    assert "cpc_o8_r1_written_statement_commercial" not in keys
    undecided = {p.key for p in curated.undecided(Role.DEFENDANT,
                                                  Track.NOT_ESTABLISHED)}
    assert undecided == {"cpc_o8_r1_written_statement_ordinary",
                         "cpc_o8_r1_written_statement_commercial"}


def test_a_stated_track_reaches_exactly_one_reading():
    for track, wanted in ((Track.COMMERCIAL,
                           "cpc_o8_r1_written_statement_commercial"),
                          (Track.ORDINARY,
                           "cpc_o8_r1_written_statement_ordinary")):
        keys = {r.period.key for r in curated.engaged(Role.DEFENDANT, track)}
        assert wanted in keys
        assert len(keys & {"cpc_o8_r1_written_statement_ordinary",
                           "cpc_o8_r1_written_statement_commercial"}) == 1
        assert curated.undecided(Role.DEFENDANT, track) == ()


def test_a_period_that_reads_the_same_on_both_tracks_is_engaged_either_way():
    """`Track.NOT_ESTABLISHED` ON A ROW MEANS THE ROW DOES NOT TURN ON THE
    TRACK -- it does not mean the track is unknown. The two would collapse
    into one silence if the same value carried both meanings."""
    for track in Track:
        keys = {r.period.key for r in curated.engaged(Role.DEFENDANT, track)}
        assert "cpc_o37_r3_leave_to_defend" in keys, track


def test_a_role_this_product_does_not_hold_leaves_every_period_undecided():
    """AN UNESTABLISHED ROLE IS NOT A FINDING THAT NO PERIOD RUNS. It is the
    absent-input shape (CLAUDE.md section 9): the answer is that nobody knows
    yet, named, never that nothing arises."""
    assert curated.engaged(Role.UNKNOWN, Track.NOT_ESTABLISHED) == ()
    undecided = curated.undecided(Role.UNKNOWN, Track.NOT_ESTABLISHED)
    assert {p.key for p in undecided} == set(curated.PERIODS)


def test_every_engagement_says_what_brought_it_into_play():
    for role in curated.BY_ROLE:
        for track in Track:
            for running in curated.engaged(role, track):
                assert running.why.strip()


# ======================================================= on the register ====

BRIEF = ("We act for the defendant at Hyderabad. A suit for the price of "
         "goods was filed against our client and the summons has come.")


def _rows(out):
    (thread,) = out.matter.threads
    return [deadlines.from_stored(r, thread=thread.id)
            for r in thread.deadlines]


def _procedural(out):
    return [r for r in _rows(out)
            if r.kind is deadlines.DeadlineKind.PROCEDURAL_PERIOD]


def test_an_engaged_period_reaches_the_register_with_no_date(tmp_path):
    """NOT_COMPUTED IS A ROW, NOT AN ABSENCE. The period is real and its
    trigger is not on the file, so it is entered saying so. Leaving it off
    would tell the advocate there is no such deadline, which is the opposite
    of what is known."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    rows = _procedural(out)
    assert rows, [r.kind.value for r in _rows(out)]
    for row in rows:
        assert row.on is None, row
        assert row.status(date.today()) is deadlines.DeadlineStatus.NOT_COMPUTED
        assert row.action.strip() and row.consequence.strip()


def test_no_procedural_period_ever_arrives_with_a_computed_date(tmp_path):
    """THE INVARIANT, NOT THE SCENARIO. Nothing in this slice reads a trigger
    date, so nothing in this slice may produce one -- on any matter, not only
    on the one above."""
    for brief in (BRIEF,
                  "We act for the defendant. The summons was served on our "
                  "client on 3 March 2026 at Hyderabad.",
                  "We act for the respondent to a caveat at Hyderabad."):
        engine, _ = build(tmp_path / brief[:12].replace(" ", "_"))
        out = engine.run(TurnInput(advocate_id="adv_1", message=brief))
        for row in _procedural(out):
            assert row.on is None, (brief, row)
            assert row.conditional_on is None, (brief, row)


def test_the_advocate_is_told_the_period_binds_and_whether_it_extends(tmp_path):
    """A GUARD THAT IS RIGHT IN THE KNOWLEDGE PLANE AND NEVER REACHES THE
    ANSWER IS NOT A GUARD (CLAUDE.md section 8)."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    said = " ".join(e.text for e in out.answer.elements)
    assert "A period runs inside this proceeding" in said, said[-1500:]
    assert "leave to defend" in said
    # THROUGH `said`, NEVER THE VALUE. `mandatory` and `not_recorded` on a
    # page are identifiers, and the advocate is the one person who cannot be
    # expected to read this product's internal vocabulary.
    assert Bindingness.MANDATORY.said in said
    assert Extension.AVAILABLE.said in said


def test_no_period_reaches_the_advocate_as_its_own_identifier(tmp_path):
    """THE INVARIANT BESIDE THE SCENARIO. `test_no_enum_value_reaches_the_
    advocate` sweeps the whole product for `.value` inside an `Element`; this
    holds the same line from the other end, on the served text, so a phrase
    rewritten to interpolate the member some other way is still caught.

    THE POPULATION IS THE UNDERSCORED VALUES, and the restriction is the whole
    of its honesty. `commercial` and `mandatory` are ordinary English words
    that the surrounding prose uses legitimately -- "whether this is a
    commercial suit" is a sentence, not a leaked identifier -- so asserting on
    them would fail on correct text and get relaxed away. `not_recorded` and
    `not_established` cannot be anything but this product's vocabulary.
    """
    engine, _ = build(tmp_path)
    said = " ".join(e.text for e in
                    engine.run(TurnInput(advocate_id="adv_1",
                                         message=BRIEF)).answer.elements)
    checked = 0
    for enum in (Bindingness, Extension, Track):
        for member in enum:
            if "_" not in member.value:
                continue
            checked += 1
            assert member.value not in said, f"{enum.__name__}.{member.name}"
    assert checked >= 3, "the population emptied out, so this checks nothing"


def test_neither_reading_of_the_written_statement_rule_is_picked(tmp_path):
    """LB-124's NEVER, SERVED. The two readings are named as undecided and
    neither is applied, because nothing establishes which track this suit is
    on."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    said = " ".join(e.text for e in out.answer.elements)
    assert "cannot be read on this thread until it is settled" in said
    assert "I will not pick one because nobody said" in said
    # AND NO WRITTEN-STATEMENT PERIOD IS ON THE REGISTER, because a row there
    # is a row the advocate acts on.
    for row in _procedural(out):
        assert "written statement" not in row.source


def test_an_unwired_installation_enters_no_period_and_claims_nothing(tmp_path):
    """AN ABSENT PORT IS NOT A FINDING (CLAUDE.md section 9). With no curated
    table an installation must not report that two readings cannot be chosen
    between -- that is a statement about this matter, and it has nothing to
    base it on."""
    engine, _ = build(tmp_path)
    engine._procedural = None
    out = engine.run(TurnInput(advocate_id="adv_1", message=BRIEF))
    assert _procedural(out) == []
    said = " ".join(e.text for e in out.answer.elements)
    assert "A period runs inside this proceeding" not in said
    assert "I will not pick one because nobody said" not in said
