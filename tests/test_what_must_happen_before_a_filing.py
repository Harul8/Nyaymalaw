"""LB-121. WHAT A STATUTE REQUIRES BEFORE A PROCEEDING CAN BE INSTITUTED.

THE DEFECT THIS FILE IS ABOUT. `statutory_notice` has been a declared threshold
since D1, and on every turn it answered BLOCKED with the map's generic sentence
because nothing assessed it. An advocate reading that learned nothing about
their own file, and a suit that skips a step the statute required first fails
before its merits are ever reached.

WHAT IS AND IS NOT CLAIMED HERE. This slice establishes which conditions a
cause and an opponent ENGAGE. Whether the file shows one DONE is a question
about the advocate's own words that nothing yet reads, so the honest answer is
that it is not assessed -- named, with its source, rather than silent. These
tests hold that line in both directions: an engaged condition is never reported
as satisfied, and an unestablished key is never reported as inapplicable.
"""
from __future__ import annotations

import pytest
from nm.core import thresholds
from nm.core.turn import TurnInput
from nm.domain.citation import provision_label
from nm.domain.matter import CauseOfAction
from nm.knowledge import institution as curated
from nm.ports.institution import Against

from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a


# ======================================= the table, and what it may not do ==

def test_every_curated_condition_says_where_it_came_from():
    """`curated_from` IS THE WHOLE ARGUMENT FOR A CURATED TABLE.

    A routing decision that cannot say where it came from is one somebody
    remembered, and a remembered pre-institution condition stops an advocate
    filing on a rule nobody can check. The type refuses a blank, so this reads
    the population rather than the type: a row added tomorrow is covered.
    """
    assert curated.CONDITIONS, "the table is empty, so this checks nothing"
    for key, condition in curated.CONDITIONS.items():
        assert condition.key == key, f"{key}: keyed under another name"
        assert condition.curated_from.strip(), key
        assert condition.act.strip() and condition.provision.strip(), key
        # THE CORPUS'S OWN KEY, not prose. A row that wrote "section 80 CPC"
        # would look up nothing and report a gap in an Act held in full.
        assert " " not in condition.provision, (
            f"{key}: {condition.provision!r} is prose, not the store's key")


def test_a_condition_is_reached_by_an_exact_key_and_never_by_words():
    """CLAUDE.md section 5, where it bites hardest.

    Engagement is decided by membership of the closed `CauseOfAction`
    vocabulary and of the closed `Against` vocabulary. Nothing in the tables
    is matched approximately, so there is no route by which a description that
    merely reads like a tenancy engages a lease-termination notice.
    """
    for cause in curated.BY_CAUSE:
        assert isinstance(cause, CauseOfAction)
    for against in curated.BY_OPPONENT:
        assert isinstance(against, Against)
    for keys in (*curated.BY_CAUSE.values(), *curated.BY_OPPONENT.values()):
        for key in keys:
            assert key in curated.CONDITIONS, (
                f"{key} is engaged by something and is not in the table")


def test_a_cause_this_product_does_not_hold_engages_nothing_and_says_so():
    """THE THIRD STATE, AT THE TABLE. An unestablished cause engages nothing
    through the cause -- and that is not a finding that nothing is required,
    which is why `undecided` answers rather than leaving silence."""
    assert curated.engaged(CauseOfAction.NOT_ESTABLISHED, Against.UNKNOWN) == ()
    undecided = curated.undecided(CauseOfAction.NOT_ESTABLISHED, Against.UNKNOWN)
    assert undecided, (
        "an unestablished cause reported no engaged conditions and nothing "
        "undecided, which reads as a finding that none arises")


def test_one_condition_engaged_by_two_routes_is_reported_once():
    """A duplicate row is noise the advocate learns to skip, and what they
    skip is the list of what has not been done."""
    engaged = curated.engaged(CauseOfAction.CHEQUE_DISHONOUR, Against.GOVERNMENT)
    keys = [e.condition.key for e in engaged]
    assert len(keys) == len(set(keys)), keys


def test_every_engagement_says_what_brought_it_into_play():
    """A wrong engagement must be correctable at a glance, not after the
    advocate has acted on it."""
    for against in (Against.PRIVATE, Against.GOVERNMENT, Against.UNKNOWN):
        for cause in CauseOfAction:
            for engagement in curated.engaged(cause, against):
                assert engagement.why.strip()


# ==================================== the threshold row, in all three states ==

def test_an_engaged_condition_is_blocked_and_named_never_answered():
    """THE RULE. `ANSWERED` disposes of a threshold, and nothing here has read
    whether the condition was satisfied. Reporting it answered would be the
    absent input reading as a clean result -- defect shape S1, on the question
    of whether a suit can be filed at all."""
    engaged = curated.engaged(CauseOfAction.CHEQUE_DISHONOUR, Against.UNKNOWN)
    assert engaged, "the fixture cause engages nothing, so this proves nothing"

    row = thresholds.from_institution(engaged, ())
    assert row.state is thresholds.ThresholdState.BLOCKED
    assert row.state is not thresholds.ThresholdState.ANSWERED
    for engagement in engaged:
        assert engagement.condition.said in row.reason, engagement.condition.key
        # RENDERED BY THE ONE OWNER, so a Schedule Article never
        # arrives as `s.Article_64` (23 September 2026).
        assert provision_label(engagement.condition.act,
                               engagement.condition.provision) in row.reason
    assert "not assessed" in row.reason, (
        "the row does not say that whether it was done is unread, so an "
        "advocate may read a named condition as a satisfied one")


def test_an_unestablished_key_is_undecided_and_never_not_applicable():
    """`NOT_APPLICABLE` IS A FINDING -- somebody looked and it does not arise.
    Returning it because the cause is unknown is the silence D1 forbids
    wearing a finding's clothes."""
    row = thresholds.from_institution(
        (), curated.undecided(CauseOfAction.NOT_ESTABLISHED, Against.UNKNOWN))
    assert row.state is thresholds.ThresholdState.BLOCKED
    assert row.state is not thresholds.ThresholdState.NOT_APPLICABLE
    assert "undecided, not inapplicable" in row.reason


def test_not_applicable_is_reached_only_when_nothing_is_left_undecided():
    """AND THE FINDING IS AVAILABLE, or the map could never close this row.

    It is reached from an established cause and an established opponent that
    between them engage nothing -- and it says the table is what answered,
    not a search of every statute."""
    row = thresholds.from_institution((), ())
    assert row.state is thresholds.ThresholdState.NOT_APPLICABLE
    assert "curated table" in row.reason


# =========================================== on the served turn, end to end ==

CHEQUE = ("We act for the payee. A cheque for 4,00,000 rupees given towards "
          "the price of goods was returned unpaid by the bank on 3 March 2026.")


def _notice_row(out):
    said = " ".join(e.text for e in out.answer.elements)
    return said


def test_the_served_turn_names_the_condition_a_cheque_matter_engages(tmp_path):
    """THE GOLDEN CASE, on the served path rather than in the table.

    A guard that is right in the knowledge plane and never reaches the answer
    is not a guard (CLAUDE.md section 8). What the advocate must be able to see
    is the demand notice, named, before anything recommends a complaint.
    """
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=CHEQUE))
    said = _notice_row(out)
    assert "written demand" in said, (
        "a dishonoured-cheque matter reached the advocate without naming the "
        "demand the section requires:\n" + said[:900])
    assert "Negotiable Instruments Act, 1881 s.138" in said


def test_the_served_turn_never_reports_the_condition_as_done(tmp_path):
    """THE PLANTED NEGATIVE. Nothing has read whether the demand was made, so
    no wording may suggest it was."""
    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=CHEQUE))
    said = _notice_row(out).lower()
    for claimed in ("notice was given", "notice has been given",
                    "the demand was made", "requirement is satisfied",
                    "requirement is met"):
        assert claimed not in said, (
            f"the turn asserted {claimed!r} and nothing read the file for it")


def test_an_unwired_installation_keeps_the_maps_own_reason(tmp_path):
    """AN ABSENT PORT IS NOT A FINDING. With no curated table the row must read
    exactly as it did before this work existed -- never as one that looked and
    found nothing (CLAUDE.md section 9)."""
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.store.file_store import FileMatterStore
    from nm.core.turn import TurnEngine

    from tests.test_turn_contract import KEY, _Evidence, _model_config, briefed

    engine = briefed(TurnEngine(
        store=FileMatterStore(tmp_path, key=KEY), evidence=_Evidence(),
        model=ScriptedModelAdapter(_model_config(),
                                   responses={"__default__": "File the suit."})))
    assert engine._pre_institution is None
    assert engine._pre_institution_row("cheque_dishonour") is None, (
        "an unwired installation produced a threshold row, so it reports on a "
        "table it does not have")


def test_a_threshold_with_its_own_renderer_is_not_said_twice(tmp_path):
    """WHAT REFUSES THE SECOND COPY. `_limitation_elements` renders the
    limitation position in full -- its Article, its accrual, its alternatives.
    The map carrying a reason for the same threshold made the turn say it
    twice, the second time in the map's clipped words ("no reason was recorded
    for this"), which reads as a second finding about the same question.

    Declared rather than written inline, so the next threshold to get a
    dedicated renderer is an entry in that set rather than a duplicated line.
    """
    from nm.core.turn import _THRESHOLDS_RENDERED_ELSEWHERE

    assert thresholds.Threshold.LIMITATION in _THRESHOLDS_RENDERED_ELSEWHERE

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv_1", message=CHEQUE))
    filed = [e.text for e in out.answer.elements
             if e.text.startswith("Before this can be filed")]
    assert len(filed) == 1, filed
    assert "no reason was recorded" not in " ".join(filed)
