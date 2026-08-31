"""D2 — limitation as a computed date, and its four NEVER clauses.

E-042 IS THE ONE THAT WAS MEASURED FAILING, and it is the reason this file
leads with the coverage record rather than with the arithmetic. An
acknowledgment in writing on 12 June 2024 sat in the chronology, was repeated
back to the advocate, and never reached the computation. The claim was reported
time-barred and it was not.

Nothing about that was visible. The citation was right, the period was right,
the accrual date was right, and one fact in the chart was never asked about.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.limitation import (
    Applied,
    Factor,
    FactorKind,
    LimitationState,
    Period,
    add_months,
    add_years,
    compute,
    not_computed,
    period_in,
)
from nm.domain.matter import Side
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a

TODAY = date(2026, 8, 31)

# THROUGH THE PRODUCTION DOOR. These are built by `period_in` from real
# statutory text rather than by hand, because a test that constructs its
# period some other way is not exercising the path the engine uses -- and the
# defect this type exists for lived exactly in that gap.
YEARS_12 = period_in("For possession of immovable property... twelve years.")
YEARS_3 = period_in("For compensation for breach of contract... three years.")


# ================================ D2.0 — a date, never a narration ==========


@refuses("D2", 0)
@pytest.mark.eval_id("E-043")
def test_every_computed_position_yields_a_date_and_a_day_count():
    """D2: *Never narrate limitation. "Roughly three years from the invoices"
    is not an output. A date is.*

    An advocate cannot file against a sentence, cannot advise against one, and
    cannot tell whether it is right. A date can be checked.
    """
    lim = compute(
        for_side=Side.MOVING, article="Limitation Act, 1963 Article 65",
        accrual="fact_1", accrual_on=date(2019, 4, 15),
        accrual_reason="dispossession", chronology=("fact_1",),
        period=YEARS_12)

    assert lim.state is LimitationState.COMPUTED
    assert lim.expires_on == date(2031, 4, 15), "the date is not computed"
    assert lim.days_remaining(TODAY) == (date(2031, 4, 15) - TODAY).days
    assert lim.expired(TODAY) is False

    # A POSITION THAT COULD NOT BE COMPUTED SAYS SO, and carries no date at
    # all rather than a plausible one.
    none = not_computed(Side.MOVING, "no Article was retrieved for this cause")
    assert none.state is LimitationState.NOT_COMPUTED
    assert none.expires_on is None
    assert none.days_remaining(TODAY) is None
    assert none.not_computed_because


def test_a_position_that_could_not_be_computed_never_reads_as_alive():
    """`expired` returns THREE STATES and the third is why it is optional.

    `False` for "we could not compute it" reads as "the claim is alive", which
    is the most expensive false reassurance this product could give — the
    advocate does nothing, and the period runs out while they wait.
    """
    none = not_computed(Side.MOVING, "the accrual event has not been given")
    assert none.expired(TODAY) is None, (
        "an uncomputed position reported a bar status. `False` here would tell "
        "the advocate the claim is alive.")


@refuses("D2", 3)
@pytest.mark.eval_id("E-043")
def test_a_period_is_counted_by_the_calendar_and_never_in_days():
    """D2: *Never count a period in days where the statute counts by the
    calendar.*

    Three years from 15 April 2019 is 15 April 2022, not 1,095 days later. The
    difference is one day across a leap year, and one day is the whole of a
    limitation argument.
    """
    assert add_years(date(2019, 4, 15), 3) == date(2022, 4, 15)

    # 1,095 days from that date lands a day EARLIER, because 2020 is a leap
    # year. A product counting in days would report the claim dead a day
    # before it was.
    from datetime import timedelta
    assert date(2019, 4, 15) + timedelta(days=365 * 3) == date(2022, 4, 14)

    # 29 February clamps DOWN. Rolling to 1 March would silently extend it.
    assert add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)
    # And 31 January plus a month is 28 February, not 3 March.
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2025, 11, 30), 3) == date(2026, 2, 28)


# ================== D2.2 — an extending provision is retrieved ==============


@refuses("D2", 2)
@pytest.mark.eval_id("E-042")
def test_an_extending_factor_cannot_be_constructed_without_its_provision():
    """D2: *Never assert an extending provision from memory.*

    Acknowledgment, part payment, exclusion, disability, fraud, notice periods,
    continuing breach and continuing wrongs are each a SECTION. The type
    refuses a factor with no retrieved provision behind it, so one asserted
    from memory cannot be built at all — which is stronger than a check that
    has to be remembered at each call site.
    """
    with pytest.raises(TypeError):
        Factor(kind=FactorKind.ACKNOWLEDGMENT, fact="fact_2")  # no finding

    with pytest.raises(ValueError):
        Factor(kind=FactorKind.ACKNOWLEDGMENT, fact="fact_2", finding="   ")

    # WITH the provision it constructs, so the guard is not a blanket refusal.
    ok = Factor(kind=FactorKind.ACKNOWLEDGMENT, fact="fact_2",
                finding="Limitation Act, 1963 s.18",
                restarts_from=date(2024, 6, 12))
    assert ok.finding


# ============ E-042 — THE INVARIANT: every entry appears in the record =======


@pytest.mark.eval_id("E-042")
def test_every_chronology_entry_appears_in_the_coverage_record():
    """THE MEASURED DEFECT, made impossible.

    An acknowledgment in writing on 12 June 2024 sat in the chronology, was
    repeated back, and never reached the arithmetic. The claim was reported
    time-barred and it was not. Every other part of the answer was correct.
    """
    chronology = ("fact_1", "fact_2", "fact_3")
    lim = compute(
        for_side=Side.MOVING, article="Limitation Act, 1963 Article 55",
        accrual="fact_1", accrual_on=date(2021, 1, 10),
        accrual_reason="breach of contract", chronology=chronology, period=YEARS_3,
        factors=(Factor(kind=FactorKind.ACKNOWLEDGMENT, fact="fact_2",
                        finding="Limitation Act, 1963 s.18",
                        restarts_from=date(2024, 6, 12)),),
        considered={"fact_3": "a letter of complaint; it acknowledges no debt"})

    assert lim.accounts_for_every_entry(chronology) == (), (
        "an entry in the chronology never reached the computation")
    assert {e.fact for e in lim.covered} == set(chronology)
    by_fact = {e.fact: e for e in lim.covered}
    assert by_fact["fact_2"].applied is Applied.APPLIED
    assert by_fact["fact_3"].applied is Applied.NO_EFFECT
    assert "acknowledges no debt" in by_fact["fact_3"].reason

    # THE RESTART MOVED THE DATE. Three years from 12 June 2024, not from the
    # 2021 accrual -- which is the difference between alive and dead.
    assert lim.expires_on == date(2027, 6, 12)
    assert lim.expired(TODAY) is False


@pytest.mark.eval_id("E-042")
def test_an_entry_nobody_examined_is_reported_as_not_assessed():
    """THE POSITIVE CONTROL for the invariant above.

    Asserting that nothing was missed proves nothing about the record — a
    record that always claims full coverage passes it identically. So an entry
    is deliberately left unexamined, and the gap must be NAMED.
    """
    chronology = ("fact_1", "fact_2", "fact_lost")
    lim = compute(
        for_side=Side.MOVING, article="Limitation Act, 1963 Article 55",
        accrual="fact_1", accrual_on=date(2021, 1, 10),
        accrual_reason="breach", chronology=chronology, period=YEARS_3,
        considered={"fact_2": "a reminder; no acknowledgment of liability"})

    missed = lim.accounts_for_every_entry(chronology)
    assert missed == ("fact_lost",), (
        "an unexamined entry was reported as covered. The measured defect was "
        "exactly one such entry, and every other part of the answer was right.")
    row = next(e for e in lim.covered if e.fact == "fact_lost")
    assert row.applied is Applied.NOT_ASSESSED
    assert "not examined" in row.reason


@pytest.mark.eval_id("E-042")
def test_an_uncomputed_position_still_accounts_for_the_chronology():
    """A thread with no computation must not report full coverage by default.

    `not_computed` with an empty record would satisfy the invariant vacuously —
    nothing in, nothing missed — and that is the shape where a bar is never
    computed and nobody notices.
    """
    chronology = ("fact_1", "fact_2")
    none = not_computed(Side.MOVING, "no Article retrieved", chronology)
    assert none.accounts_for_every_entry(chronology) == chronology, (
        "an uncomputed position claimed to have covered the chronology")
    assert all(e.applied is Applied.NOT_ASSESSED for e in none.covered)


# ================ E-045 — the opponent's limitation is computed =============


@refuses("D2", 1)
@pytest.mark.eval_id("E-045")
def test_on_a_defending_thread_the_opponents_limitation_is_computed():
    """D2: *Compute limitation for the opponent's claims too.*

    Where we defend, THEIR limitation is often the whole answer — it disposes
    of the claim without reaching the merits. A defence that never checks
    whether the claim against it is time-barred has skipped the cheapest
    argument on the file.

    And D2.1: a bar is not a verdict. Where it is genuinely dead, the position
    says so plainly and the file turns to what else it offers.
    """
    theirs = compute(
        for_side=Side.DEFENDING, article="Limitation Act, 1963 Article 55",
        accrual="fact_1", accrual_on=date(2019, 1, 10),
        accrual_reason="the breach they plead", chronology=("fact_1",),
        period=YEARS_3)

    assert theirs.for_side is Side.DEFENDING
    assert theirs.expires_on == date(2022, 1, 10)
    assert theirs.expired(TODAY) is True, (
        "the opponent's claim is four years out of time and was not reported "
        "as barred")
    # THE DAY COUNT IS NEGATIVE AND STAYS NEGATIVE. Rounding to zero would hide
    # how far gone it is, which is what tells the advocate how safe the point
    # is to run.
    assert theirs.days_remaining(TODAY) < -1600


def test_our_side_and_theirs_are_separate_computations():
    """One thread, two positions. Collapsing them would apply our accrual date
    to their claim, which is the same error as a shared posture."""
    ours = compute(for_side=Side.MOVING, article="A", accrual="f1",
                   accrual_on=date(2025, 1, 1), accrual_reason="ours",
                   chronology=("f1",), period=YEARS_3)
    theirs = compute(for_side=Side.DEFENDING, article="A", accrual="f2",
                     accrual_on=date(2019, 1, 1), accrual_reason="theirs",
                     chronology=("f2",), period=YEARS_3)
    assert ours.expired(TODAY) is False
    assert theirs.expired(TODAY) is True
    assert ours.for_side is not theirs.for_side


# ============= D2.2 — the PERIOD is retrieved too, and it was not ===========


@refuses("D2", 2)
@pytest.mark.eval_id("E-043")
def test_the_period_cannot_be_supplied_by_the_product():
    """THE MEASURED DEFECT, found by running a turn end to end on 31 August
    2026: the engine passed `years=3` into every computation it made.

    On a turn that had just retrieved *Article 65 — twelve years* it produced a
    bar three years after accrual and reported the claim dead. The Article was
    right. The accrual date was right. Every citation on the turn was right.
    The answer was wrong by nine years, and nothing in the output distinguished
    the retrieved part from the invented part.

    So the period is a TYPE that carries the span it was read out of and checks
    itself against it — the same mechanism `Factor.finding` uses one screen
    above, for the same reason. There is no signature left through which an
    invented period reaches the arithmetic.
    """
    # The span must be there at all.
    with pytest.raises(TypeError):
        Period(12, 0, 0)

    # AND IT MUST ACTUALLY SAY IT. Without this the field is decoration: any
    # string satisfies a required-text check, and the invented period would
    # travel with a real-looking citation beside it.
    with pytest.raises(ValueError) as exc:
        Period(3, 0, 0, read_from="For possession of immovable property... "
                                  "twelve years.")
    assert "not what the retrieved text says" in str(exc.value)

    # THE POSITIVE CONTROL. The right period against the same span builds --
    # a type that refused everything would prove nothing.
    ok = Period(12, 0, 0, read_from="For possession of immovable property... "
                                    "twelve years.")
    assert (ok.years, ok.months, ok.days) == (12, 0, 0)


@refuses("D2", 2)
@pytest.mark.eval_id("E-043")
def test_a_period_of_zero_is_refused_rather_than_computed():
    """Zero was reachable and it read as an answer.

    `years`, `months` and `days` each defaulted to zero, so a caller who
    supplied none of them got an expiry equal to the accrual date — state
    COMPUTED, a real date, a real day count, and every claim barred the day it
    arose. That is defect shape S1: the absent input produced the shape of a
    clean result.
    """
    with pytest.raises(ValueError) as exc:
        Period(0, 0, 0, read_from="no period is stated here")
    assert "expires on the accrual date" in str(exc.value)

    with pytest.raises(ValueError):
        Period(-3, 0, 0, read_from="minus three years")


@pytest.mark.eval_id("E-043")
def test_text_that_states_no_period_yields_the_third_state_and_not_a_guess():
    """`None` is not failure. An Article whose text does not state a period is
    ordinary, and it must be distinguishable from a period of zero."""
    assert period_in("") is None
    assert period_in("Nothing in this section states how long anyone has.") is None

    # THE UNITS THE SCHEDULE ACTUALLY USES, in words and in figures.
    for span, expect in (
            ("... twelve years.", (12, 0, 0)),
            ("... three years.", (3, 0, 0)),
            ("... six months.", (0, 6, 0)),
            ("... thirty days.", (0, 0, 30)),
            ("... 90 days from the date of the order.", (0, 0, 90)),
            ("... one year.", (1, 0, 0)),
    ):
        got = period_in(span)
        assert got is not None, f"{span!r} states a period and none was read"
        assert (got.years, got.months, got.days) == expect, span
        # AND IT CARRIES THE SPAN, so the number can be checked against the
        # text the advocate is shown.
        assert got.read_from == span
