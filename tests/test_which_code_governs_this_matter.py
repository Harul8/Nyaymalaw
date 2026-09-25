"""LB-120. THE LAW IN FORCE ON THE DATE THAT GOVERNS, not the current one.

THE DEFECT. A statute that has been repealed and replaced does not stop
governing the matters that arose under it. Reading the replacing code because
it is the current one produces a confident answer under a law that does not
apply, and nothing downstream catches it: the citation is correctly formatted,
the provision is genuinely held, and the section number often even matches.

WHAT THESE TESTS HOLD. That the two limbs are answered separately and can
disagree; that an unestablished date or pending status NAMES NO ACT rather than
defaulting to either; and that no section is mapped across the codes by number.

NOT WIRED INTO A SERVED TURN, and the reason is recorded in `UNWIRED` in
`tests/test_reached_from_production.py`: `CauseOfAction` is a closed vocabulary
with no criminal cause in it, so nothing a turn can establish reaches this
table. These tests exercise the table, and say so rather than implying reach.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from nm.knowledge import governing_law as curated
from nm.ports.governing_law import Limb, Pending

pytestmark = pytest.mark.class_a

#: The commencement every curated succession shares today. Read from the table
#: rather than typed here, so a row that moves moves these tests with it.
COMMENCED = {s.limb: s.commenced_on for s in curated.SUCCESSIONS}


def test_every_succession_says_where_it_came_from_and_what_saves_it():
    """THE SAVING PROVISION IS THE ANSWER TO EVERY HARD CASE, so a row that
    does not name one is a row that would have to reason from the commencement
    date alone -- which is exactly the reasoning that gets a pending
    proceeding wrong."""
    assert curated.SUCCESSIONS, "the table is empty, so this checks nothing"
    for row in curated.SUCCESSIONS:
        assert row.curated_from.strip(), row.replacing
        assert row.saving.strip(), row.replacing
        assert row.replaced != row.replacing


def test_one_limb_per_succession_so_no_single_answer_can_be_forced():
    """The limbs turn on different facts. Two rows for one limb would let a
    lookup pick either; one row for two limbs would force one answer for
    both, which is the shape this module exists to refuse."""
    limbs = [row.limb for row in curated.SUCCESSIONS]
    assert len(limbs) == len(set(limbs)), limbs


# ================================================= LB-120-AC1, the golden ==

def test_an_offence_before_commencement_charged_after_it_splits_the_limbs():
    """LB-120-AC1. One matter, two codes, and that is correct rather than a
    contradiction: what the conduct was is fixed when it happened, and how the
    proceeding runs turns on whether it was already under way."""
    offence = COMMENCED[Limb.SUBSTANTIVE] - timedelta(days=21)

    substantive = curated.governing(Limb.SUBSTANTIVE, offence, Pending.UNKNOWN)
    assert substantive.act == "Indian Penal Code, 1860", substantive
    assert offence.isoformat() in substantive.because
    assert substantive.read_the_saving

    # The proceeding began after commencement, so nothing was pending.
    procedural = curated.governing(
        Limb.PROCEDURAL, COMMENCED[Limb.PROCEDURAL], Pending.NO)
    assert procedural.act == "Bharatiya Nagarik Suraksha Sanhita, 2023"
    assert procedural.read_the_saving

    assert substantive.act != procedural.act, (
        "both limbs answered with one Act, so the split the rule turns on is "
        "not being made")


# ============================================= LB-120-AC2, planted negative ==

def test_conduct_before_commencement_is_never_read_under_the_replacing_code():
    """LB-120-AC2. The whole point, driven across the boundary day by day.

    A replacing penal provision applied to earlier conduct is the answer an
    advocate would carry into court, and Article 20(1) is what it breaks.
    """
    commenced = COMMENCED[Limb.SUBSTANTIVE]
    day = timedelta(days=1)
    for on in (commenced - day * 400, commenced - day * 30, commenced - day):
        answer = curated.governing(Limb.SUBSTANTIVE, on, Pending.UNKNOWN)
        assert answer.act == "Indian Penal Code, 1860", (on, answer)
    for on in (commenced, commenced + day, commenced + day * 400):
        answer = curated.governing(Limb.SUBSTANTIVE, on, Pending.UNKNOWN)
        assert answer.act == "Bharatiya Nyaya Sanhita, 2023", (on, answer)


# ============================================= LB-120-AC3, planted negative ==

def test_no_section_is_mapped_across_the_codes_by_its_number():
    """LB-120-AC3, AS A TRIPWIRE rather than as an assertion about behaviour.

    The correspondence table the rule requires IS NOT HELD -- LB-120 records
    that as OPEN. So there is nothing to test the mapping of, and the honest
    form is the one this repository already uses for an unbuilt capability: a
    check that fails the DAY a mapping appears without a curated table behind
    it, rather than a check that passes because nothing happens.

    Equal section numbers across two codes mean nothing. A mapper written from
    them would be confidently wrong and every citation it produced would be
    correctly formatted.
    """
    assert not hasattr(curated, "CORRESPONDENCE"), (
        "a cross-code correspondence table has appeared. It needs its own "
        "curated_from, its own counsel review and its own tests before "
        "anything maps a section through it")
    assert not hasattr(curated, "corresponding"), (
        "something now maps sections across codes. LB-120 permits that only "
        "through a curated correspondence table, never by number")


# =================================== the third state, in both of its causes ==

def test_an_unestablished_date_names_no_act_at_all():
    """AN ABSENT INPUT MUST NEVER READ AS SUCCESS (CLAUDE.md section 9). With
    no date there is no answer, and naming either Act would be choosing the
    governing law by assumption."""
    for limb in Limb:
        answer = curated.governing(limb, None, Pending.UNKNOWN)
        assert not answer.established, (limb, answer)
        assert answer.act == ""
        assert "not established" in answer.because
        assert answer.read_the_saving, (
            "the advocate is told nothing can be settled and not which "
            "provision would settle it")


def test_an_unknown_pending_status_names_no_procedural_act():
    """THE CASE THE SAVING PROVISION EXISTS FOR. After commencement the
    procedural answer turns on whether a proceeding was already under way, so
    an unknown status is not a default to the new code."""
    for limb in (Limb.PROCEDURAL, Limb.EVIDENTIARY):
        after = COMMENCED[limb] + timedelta(days=30)
        answer = curated.governing(limb, after, Pending.UNKNOWN)
        assert not answer.established, (limb, answer)
        assert "not established" in answer.because
        assert answer.read_the_saving


def test_a_pending_proceeding_keeps_the_replaced_procedural_code():
    for limb in (Limb.PROCEDURAL, Limb.EVIDENTIARY):
        after = COMMENCED[limb] + timedelta(days=30)
        answer = curated.governing(limb, after, Pending.YES)
        assert answer.established
        assert answer.act == next(s.replaced for s in curated.SUCCESSIONS
                                  if s.limb is limb)


def test_the_substantive_limb_never_turns_on_the_pending_status():
    """What conduct was an offence is fixed at the conduct. A substantive
    answer that moved with the procedural posture would be reading the wrong
    fact, and it would move silently."""
    commenced = COMMENCED[Limb.SUBSTANTIVE]
    day = timedelta(days=1)
    for on in (commenced - day, commenced, commenced + day):
        answers = {curated.governing(Limb.SUBSTANTIVE, on, p).act
                   for p in Pending}
        assert len(answers) == 1, (on, answers)


def test_a_limb_no_succession_covers_says_the_table_answered():
    """NOT A SEARCH OF EVERY STATUTE, and it says so. A silent empty answer
    would read as a finding that nothing has replaced anything."""
    only_substantive = tuple(s for s in curated.SUCCESSIONS
                             if s.limb is Limb.SUBSTANTIVE)
    saved = curated.SUCCESSIONS
    try:
        curated.SUCCESSIONS = only_substantive
        answer = curated.governing(Limb.PROCEDURAL, date(2025, 1, 1),
                                   Pending.NO)
        assert not answer.established
        assert "curated table" in answer.because
    finally:
        curated.SUCCESSIONS = saved
    assert curated.SUCCESSIONS is saved
