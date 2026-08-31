"""D9 — issue facets and disposition, and its three NEVER clauses.

THE MEASURED COUNTEREXAMPLE, which is the whole reason this feature exists:
classification discarded **20.1% of all issue labels ever spotted — 641 of
3,192** — led by limitation (122), bail (86) and forum or jurisdiction (58).
The three things an advocate can least afford to lose were the three most
often lost, and the advocate saw a shorter list with no way to know it was
shorter.
"""
from __future__ import annotations

import pytest

from nm.domain.issue import (
    Disposition,
    DispositionState,
    Effect,
    Issue,
    IssueKind,
    accounted_for,
    classify,
    considered_not_pursued,
    facet,
)
from nm.domain.matter import Basis, Posture, Role, Side
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a


def _spotted() -> tuple[Issue, ...]:
    """The three the measured failure lost most often, plus one to keep."""
    return (
        Issue(thread="thr_1", statement="limitation on the recovery claim",
              kind=IssueKind.THRESHOLD, runs_against=Side.MOVING),
        Issue(thread="thr_1", statement="bail under section 437",
              kind=IssueKind.PROCEDURAL, runs_against=Side.DEFENDING),
        Issue(thread="thr_1", statement="territorial jurisdiction of the court",
              kind=IssueKind.THRESHOLD, runs_against=Side.MOVING),
        Issue(thread="thr_1", statement="the agreement is unregistered",
              kind=IssueKind.SUBSTANTIVE, runs_against=Side.MOVING),
    )


# =================== D9.0 — there is no delete path =========================


@refuses("D9", 0)
@pytest.mark.eval_id("E-060")
def test_every_issue_that_enters_classification_comes_out_of_it():
    """D9: *Never delete an issue.*

    E-060's counterexample is a filter that discards 20.1% of spotted issues.
    Conservation is asserted on the IDENTITIES, not on the count: a classifier
    that dropped one issue and duplicated another would keep the count and
    still have lost the thing the advocate needed.
    """
    spotted = _spotted()
    out = classify(spotted)

    assert accounted_for(spotted, out) == (), "an issue was lost in classification"
    assert {i.id for i in out} == {i.id for i in spotted}

    # AND PARKING ONE KEEPS IT. That is the whole distinction: an issue that
    # will not be run is still an issue on the file.
    parked = classify(spotted, {
        spotted[1].id: Disposition(DispositionState.PARKED,
                                   reason="no custody question arises yet")})
    assert accounted_for(spotted, parked) == ()
    assert len(parked) == len(spotted)


@refuses("D9", 0)
@pytest.mark.eval_id("E-060")
def test_the_conservation_check_names_what_was_lost():
    """THE POSITIVE CONTROL, and it is the reason this returns statements
    rather than a number.

    A count that dropped tells the reader something is wrong and nothing about
    what. The measured failure lost limitation, bail and forum — and WHICH
    three were lost is the whole difference between a rounding error and an
    advocate missing a deadline.
    """
    spotted = _spotted()
    # A classifier that filtered, which is what the original did.
    filtered = tuple(i for i in spotted if i.kind is not IssueKind.THRESHOLD)

    lost = accounted_for(spotted, filtered)
    assert len(lost) == 2
    assert any("limitation" in x for x in lost)
    assert any("jurisdiction" in x for x in lost)


@refuses("D9", 0)
@pytest.mark.eval_id("E-060")
def test_an_issue_stopped_without_a_reason_cannot_be_constructed():
    """A deletion with extra steps is still a deletion.

    `parked` with no reason renders as a line the advocate cannot act on, and
    the next person to read the code sees a disposition where there is none.
    """
    with pytest.raises(ValueError) as exc:
        Disposition(DispositionState.PARKED)
    assert "no delete path" in str(exc.value)

    with pytest.raises(ValueError):
        Disposition(DispositionState.CLOSED, reason="   ")

    # BLOCKED must say what it NEEDS, which is a different question from why.
    with pytest.raises(ValueError) as exc2:
        Disposition(DispositionState.BLOCKED, reason="waiting")
    assert "what it needs" in str(exc2.value)

    # THE VALID SHAPES CONSTRUCT, so this is not a blanket refusal.
    assert Disposition(DispositionState.RUN).reason == ""
    assert Disposition(DispositionState.BLOCKED, needs=("the sale deed",)).needs


@pytest.mark.eval_id("E-060")
def test_a_parked_issue_appears_on_the_considered_not_pursued_line():
    """D9's class-B eval. A disposition that never reaches the advocate is a
    deletion they cannot see."""
    spotted = _spotted()
    out = classify(spotted, {
        spotted[1].id: Disposition(
            DispositionState.PARKED,
            reason="the client is not in custody, so it does not arise yet")})

    line = considered_not_pursued(out)
    assert len(line) == 1
    assert "bail" in line[0]
    assert "not pursued" in line[0]
    assert "not in custody" in line[0]

    # AND NOTHING ELSE APPEARS THERE. A line that listed every issue would be
    # as useless as one that listed none.
    assert considered_not_pursued(classify(spotted)) == ()


# ============ D9.1 — the same issue, opposite postures, opposite effect =====


@refuses("D9", 1)
@pytest.mark.eval_id("E-061")
def test_the_same_issue_on_opposite_postures_yields_opposite_effect():
    """D9: *Never build "this obstructs us" into the vocabulary. A limitation
    point is not "a bar" — ours obstructs us, theirs disposes of their claim
    without our touching the merits.*

    E-061's counterexample is a limitation point labelled `bar` regardless of
    side. The label is an opinion about whose problem it is, and it is wrong
    for half the advocates who read it.
    """
    issue = Issue(thread="thr_1", runs_against=Side.MOVING,
                  statement="the claim is out of time under Article 14")

    moving = Posture(role=Role.PLAINTIFF, basis=Basis.STATED, version=3)
    defending = Posture(role=Role.DEFENDANT, basis=Basis.STATED, version=3)

    assert issue.effect_for(moving)[0] is Effect.OPPOSES
    assert issue.effect_for(defending)[0] is Effect.SUPPORTS

    # THE VERSION TRAVELS WITH THE ANSWER. A caller that recorded the effect
    # without it has recorded a value it cannot later tell is stale.
    assert issue.effect_for(moving)[1] == 3


@refuses("D9", 1)
@pytest.mark.eval_id("E-061")
def test_an_effect_is_never_stored_and_so_cannot_survive_its_own_reversal():
    """The advocate corrects the posture on turn 4 and every effect flips.

    A field written on turn 2 would still say `opposes`, which is the failure
    `Deadline.status` is a method for and `Posture.side` is a property for.
    """
    assert not hasattr(Issue(thread="t", statement="x"), "effect"), (
        "`effect` is a stored field again; it cannot detect a posture change")

    issue = Issue(thread="t", statement="x", runs_against=Side.MOVING)
    before = issue.effect_for(Posture(role=Role.PLAINTIFF, basis=Basis.STATED))
    after = issue.effect_for(Posture(role=Role.DEFENDANT, basis=Basis.STATED,
                                     version=1))
    assert before[0] is not after[0], "the effect did not follow the posture"

    # AN UNRESOLVED POSTURE YIELDS NOT_ASSESSED, never `neutral`. `neutral` is
    # a finding that the issue helps nobody, which nobody established.
    assert issue.effect_for(Posture())[0] is Effect.NOT_ASSESSED


# ============ D9.3 — an out-of-vocabulary facet never propagates ============


@refuses("D9", 3)
@pytest.mark.eval_id("E-062")
def test_an_out_of_vocabulary_facet_value_is_blanked_whichever_path_supplied_it():
    """D9: *Never accept an out-of-vocabulary facet value. It is blanked and
    re-derived, exactly as if none had been supplied.*

    The measured counterexample is `tracks {'civil': 2, 'revenue': 1}` passing
    unvalidated and emptying the charge map. It entered through the path nobody
    had guarded, which is why this has ONE owner rather than a `try: Enum(v)`
    at each call site.
    """
    assert facet(IssueKind, "threshold",
                 default=IssueKind.NOT_ESTABLISHED) is IssueKind.THRESHOLD
    # Case and whitespace are normalised, not rejected -- a real value in odd
    # dress is still a real value.
    assert facet(IssueKind, "  SUBSTANTIVE ",
                 default=IssueKind.NOT_ESTABLISHED) is IssueKind.SUBSTANTIVE

    # OUT OF VOCABULARY LANDS ON THE DEFAULT, never on a member that happens
    # to be first, and never propagating the raw string.
    for bad in ("revenue", "civil", "", None, 7, ["threshold"]):
        got = facet(IssueKind, bad, default=IssueKind.NOT_ESTABLISHED)
        assert got is IssueKind.NOT_ESTABLISHED, f"{bad!r} propagated as {got!r}"

    # AND IT WORKS FOR EVERY FACET ENUM, which is what "one owner" buys.
    assert facet(Effect, "wibble", default=Effect.NOT_ASSESSED) is Effect.NOT_ASSESSED
    assert facet(DispositionState, "deleted", default=None) is None
    assert facet(Effect, "supports", default=Effect.NOT_ASSESSED) is Effect.SUPPORTS


@refuses("D9", 2)
@pytest.mark.eval_id("E-062")
def test_a_threshold_issue_is_not_given_a_thinner_pipeline():
    """D9: *Never give a threshold or procedural issue a thinner pipeline than
    a substantive one.*

    A threshold disposes of a claim without reaching the merits, so ranking it
    below one is exactly backwards. Asserted as a property of the TYPE: every
    kind carries the same fields and the same disposition vocabulary, so there
    is no shape a substantive issue can take that a threshold one cannot.
    """
    fields_by_kind = {}
    for kind in IssueKind:
        i = Issue(thread="t", statement="x", kind=kind,
                  provisions=("Limitation Act, 1963 Article 14",),
                  authorities=("Some case (2003)",), deadline="2027-06-12")
        fields_by_kind[kind] = (i.provisions, i.authorities, i.deadline)
    assert len(set(fields_by_kind.values())) == 1, (
        "some kind of issue carries a different set of facets from the others")

    # AND VISIBILITY IS THE DISPOSITION'S, NOT THE KIND'S.
    assert Disposition(DispositionState.RUN).visible
    assert Disposition(DispositionState.PARKED, reason="r").visible
