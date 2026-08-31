"""D1 — the threshold map, and its three NEVER clauses.

E-044's counterexample is the one that names the shape: *a twelve-year clock
applied to a one-day-old trespass.* The absurdity is not the twelve years —
that is what Article 65 gives. It is that the expiry was computed from an
accrual the file's own chronology does not contain, and nothing compared the
two.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.limitation import compute, not_computed, period_in
from nm.core.thresholds import (
    Threshold,
    ThresholdAnswer,
    ThresholdState,
    absurd,
    for_thread,
    from_limitation,
    silent,
)
from nm.domain.matter import Side
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

TODAY = date(2026, 8, 31)
YEARS_12 = period_in("For possession of immovable property... twelve years.")


# ================================== D1.0 — never leave a threshold silent ===


@refuses("D1", 0)
@pytest.mark.eval_id("E-044")
def test_every_threshold_appears_on_the_map_even_when_nobody_assessed_it():
    """D1: *Never leave a threshold silent. Silence is not a not-applicable
    finding.*

    An advocate reading a map with eight rows believes the ninth was checked
    and found irrelevant. It was not checked. Absence is invisible; a row is
    not.
    """
    # The caller assessed exactly one threshold.
    partial = for_thread({
        Threshold.JURISDICTION: ThresholdAnswer(
            threshold=Threshold.JURISDICTION, state=ThresholdState.ANSWERED,
            reason="Telangana, and the corpus is scoped to it",
            finding="Code of Civil Procedure, 1908 s.16")})

    assert len(partial) == len(Threshold), (
        "the map is shorter than the threshold list — the missing ones read as "
        "checked and irrelevant")
    assert silent(partial) == ()

    unassessed = [a for a in partial if a.threshold is not Threshold.JURISDICTION]
    assert all(a.state is ThresholdState.BLOCKED for a in unassessed)
    for a in unassessed:
        assert "not assessed" in a.reason and "not a finding" in a.reason, (
            f"{a.threshold.value} reads as a finding rather than a gap")


@refuses("D1", 0)
@pytest.mark.eval_id("E-044")
def test_not_applicable_is_a_finding_and_blocked_is_a_question():
    """Collapsing the two is the silence D1 forbids.

    NOT_APPLICABLE means somebody looked and it does not arise — nothing more
    is owed. BLOCKED means an answer is owed. Rendering them the same makes the
    second invisible among the first.
    """
    found = ThresholdAnswer(
        threshold=Threshold.ARBITRATION_CLAUSE,
        state=ThresholdState.NOT_APPLICABLE,
        reason="there is no agreement between these parties, so no clause")
    gap = ThresholdAnswer(
        threshold=Threshold.VALUATION, state=ThresholdState.BLOCKED,
        reason="the relief claimed has not been quantified")

    assert found.state is not gap.state
    # And NOT_APPLICABLE needs no citation, because nothing was decided about
    # the law -- while ANSWERED does.
    assert found.finding == ""


# ======================= D1.2 — not a thinner pipeline ======================


@refuses("D1", 2)
@pytest.mark.eval_id("E-044")
def test_an_answered_threshold_cannot_be_built_without_its_provision():
    """D1: *Never let a threshold issue receive a thinner pipeline than a
    merits issue. A threshold issue gets a cited provision, a computed date and
    authority.*

    An answer from memory is thinner by definition, so the type refuses it —
    the same rule `Factor` applies to an extending provision.
    """
    with pytest.raises(ValueError) as exc:
        ThresholdAnswer(threshold=Threshold.COURT_FEES,
                        state=ThresholdState.ANSWERED,
                        reason="ad valorem on the relief claimed")
    assert "thinner pipeline" in str(exc.value)

    # WITH a provision it constructs, so this is not a blanket refusal.
    ok = ThresholdAnswer(threshold=Threshold.COURT_FEES,
                         state=ThresholdState.ANSWERED,
                         reason="ad valorem on the relief claimed",
                         finding="Telangana Court Fees Act s.7")
    assert ok.finding


# ================ D1.1 — never arithmetically absurd on the file's dates ====


@refuses("D1", 1)
@pytest.mark.eval_id("E-044")
def test_a_threshold_answer_inconsistent_with_the_file_s_own_dates_is_caught():
    """D1: *Never return a threshold answer that is arithmetically absurd on
    the file's own dates.*

    The measured counterexample is a twelve-year clock applied to a one-day-old
    trespass. The twelve years are right — that is Article 65. What is wrong is
    that the expiry was computed from an accrual the chronology does not
    contain, and nothing compared the two.
    """
    chronology = (date(2026, 8, 30), date(2026, 8, 31))

    # A period that expired before anything on the file had happened.
    stale = (ThresholdAnswer(
        threshold=Threshold.LIMITATION, state=ThresholdState.ANSWERED,
        reason="accrual: dispossession in 2010",
        finding="Limitation Act, 1963 Article 65",
        expires_on=date(2022, 4, 15)),)
    problems = absurd(stale, chronology)
    assert problems, "an expiry predating the whole file was not caught"
    assert "different matter" in problems[0]

    # And one that expires between the file's own events.
    mid = (ThresholdAnswer(
        threshold=Threshold.LIMITATION, state=ThresholdState.ANSWERED,
        reason="accrual", finding="Article 65",
        expires_on=date(2026, 8, 30)),)
    assert absurd(mid, chronology), (
        "an expiry earlier than events the file already records was accepted")

    # THE POSITIVE CONTROL IS THE OTHER DIRECTION. A twelve-year clock on a
    # one-day-old trespass is CORRECT arithmetic and must not be flagged --
    # a check that fires on the right answer teaches the advocate to ignore it.
    right = (ThresholdAnswer(
        threshold=Threshold.LIMITATION, state=ThresholdState.ANSWERED,
        reason="accrual: dispossession yesterday",
        finding="Limitation Act, 1963 Article 65",
        expires_on=date(2038, 8, 30)),)
    assert absurd(right, chronology) == ()

    # A BLOCKED row has no date and cannot be absurd.
    assert absurd((ThresholdAnswer(
        threshold=Threshold.VALUATION, state=ThresholdState.BLOCKED,
        reason="not quantified"),), chronology) == ()

    # And with no chronology there is nothing to be inconsistent WITH, which is
    # a different state from consistent -- so nothing is claimed.
    assert absurd(stale, ()) == ()


# ===================== the limitation row has ONE owner =====================


@pytest.mark.eval_id("E-044")
def test_the_limitation_row_comes_from_the_computation_and_not_beside_it():
    """Two owners for "is this claim in time" would be the second-copy defect
    on the most consequential question the map asks."""
    lim = compute(for_side=Side.MOVING,
                  article="Limitation Act, 1963 Article 65",
                  accrual="fact_1", accrual_on=date(2019, 4, 15),
                  accrual_reason="dispossession", chronology=("fact_1",),
                  period=YEARS_12)
    row = from_limitation(lim)
    assert row.state is ThresholdState.ANSWERED
    assert row.finding == lim.article
    assert row.expires_on == lim.expires_on

    # AND AN UNCOMPUTED POSITION BLOCKS THE ROW rather than answering it. A
    # limitation nobody computed must not read as a limitation that is fine.
    none = from_limitation(not_computed(Side.MOVING, "no Article retrieved"))
    assert none.state is ThresholdState.BLOCKED
    assert none.expires_on is None
    assert "no Article retrieved" in none.reason
