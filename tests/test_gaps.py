"""S9 — multi-thread files, the gap queue, the correction cascade, quarantine.

*Five disputes on one file is the normal case, not the edge case.*

Three of the five evals here are about the product NOT doing something an
agreeable system does by default: asking a question to keep the conversation
moving, finishing its own thread before following the advocate, and quietly
recomputing a number that moved.
"""
from __future__ import annotations

import pytest

from nm.core.cascade import (
    Change,
    Derived,
    PriorAdvice,
    advice_at_risk,
    changes,
    dependents,
    report,
    unresolved_undo,
)
from nm.core.gaps import (
    Gap,
    GapKind,
    Question,
    batched,
    follows,
    leads,
    rank,
    still_missing,
)
from nm.core.quarantine import (
    AlreadyReleased,
    Clearance,
    Quarantined,
    reachable_substance,
)
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a


# =============== E-090 — every question traces to a gap ====================


@pytest.mark.eval_id("E-090")
def test_a_question_cannot_exist_without_the_gap_it_fills():
    """E-090's counterexample: *a question asked to keep the conversation
    moving.*

    §5.2 states the mechanism and it is the whole design: *there is no
    obligation to ask something in order to advance, because there is nothing
    to advance. This removes the manufactured question BY CONSTRUCTION rather
    than by prohibition.*

    So this is not a check that runs. It is a sentence that cannot be written —
    a question asked to fill silence has nowhere to get a `Gap` from.
    """
    with pytest.raises(TypeError):
        Question(text="and how did that make your client feel?")

    with pytest.raises(ValueError):
        Gap(what="the date of the notice", blocks="   ", thread="thr_1",
            kind=GapKind.DEADLINE)

    # AND A GAP WITH NO KIND CANNOT BE BUILT. The kind IS the rank, so a
    # default is a rank nobody chose -- and the one that reads as neutral
    # sorts THIRD, which would queue an unclassified blocking gate below
    # every deadline.
    with pytest.raises(TypeError):
        Gap(what="the date", blocks="the window", thread="thr_1")

    real = Question(
        text="when was the statutory notice served?",
        gap=Gap(what="the date of the notice",
                blocks="computing whether the s.138 proviso window was met",
                thread="thr_1", kind=GapKind.DEADLINE))
    assert real.blocks


@pytest.mark.eval_id("E-090")
def test_nothing_blocked_means_nothing_is_owed():
    """`leads` returning `None` IS AN ANSWER.

    A queue that always yields something is the manufactured question with a
    data structure behind it — the advocate is asked because the code had a
    slot to fill, which is exactly what §5.2 removes.
    """
    assert leads(()) is None
    assert still_missing(()) == ()


@pytest.mark.eval_id("E-090")
def test_the_queue_ranks_a_blocking_gate_above_everything_interesting():
    """*An unresolved posture makes everything below it worthless, however
    interesting.* A correctness mechanism before it is a cost one."""
    interesting = Gap(what="whether the guarantor was solvent",
                      blocks="deciding whether to join him",
                      thread="thr_1", kind=GapKind.INFORMATION_VALUE)
    urgent = Gap(what="the date of the notice", blocks="the s.138 window",
                 thread="thr_1", kind=GapKind.DEADLINE)
    blocking = Gap(what="which side we act for",
                   blocks="every directive step on this thread",
                   thread="thr_1", kind=GapKind.BLOCKING_GATE)

    ordered = rank((interesting, urgent, blocking))
    assert [g.kind for g in ordered] == [
        GapKind.BLOCKING_GATE, GapKind.DEADLINE, GapKind.INFORMATION_VALUE]
    assert leads((interesting, urgent, blocking)) is blocking

    # STABLE WITHIN A KIND. An arbitrary tiebreak would read as a judgement
    # nobody made.
    a = Gap(what="a", blocks="x", thread="t", kind=GapKind.CONSEQUENCE)
    b = Gap(what="b", blocks="y", thread="t", kind=GapKind.CONSEQUENCE)
    assert rank((a, b)) == (a, b)


@pytest.mark.eval_id("E-090")
def test_questions_are_batched_one_thread_at_a_time():
    """§5.2: *a single batched question per thread, not an interrogation across
    all of them. Serial single questions make the advocate do the scheduling.*
    """
    one = Gap(what="the notice date", blocks="the s.138 window",
              thread="thr_cheque", kind=GapKind.DEADLINE)
    two = Gap(what="the ledger", blocks="proving the debt",
              thread="thr_cheque", kind=GapKind.INFORMATION_VALUE)
    other = Gap(what="the quit notice", blocks="the eviction defence",
                thread="thr_tenancy", kind=GapKind.DEADLINE)

    mine = batched((one, two, other), "thr_cheque")
    assert mine == (one, two), "the batch crossed into another thread"
    assert batched((one, two, other), "thr_tenancy") == (other,)


# =============== E-091 — the advocate navigates ============================


@pytest.mark.eval_id("E-091")
def test_the_advocate_changes_subject_and_nm_follows_in_the_same_turn():
    """E-091's counterexample: *NM asking to finish the current thread first.*

    §5.3: *if the advocate asks about another thread, NM answers on that thread
    in that turn. It does not finish anything first and does not ask to come
    back.* The eval is pointed — a build that passes its stages by railroading
    the advocate through them has failed.
    """
    queue_wants = Gap(what="which side we act for",
                      blocks="every directive step",
                      thread="thr_cheque", kind=GapKind.BLOCKING_GATE)
    elsewhere = Gap(what="the quit notice date", blocks="the eviction defence",
                    thread="thr_tenancy", kind=GapKind.DEADLINE)

    answer_on, preference = follows((queue_wants, elsewhere), "thr_tenancy")

    assert answer_on == "thr_tenancy", (
        "NM went where the queue wanted rather than where the advocate asked")
    # THE QUEUE'S PREFERENCE SURVIVES AS STATE, carried so the answer can note
    # it -- a note, never a redirection.
    assert preference is queue_wants

    # AND IT FOLLOWS EVEN ONTO A THREAD THE QUEUE HAS NOTHING TO SAY ABOUT.
    assert follows((queue_wants,), "thr_new")[0] == "thr_new"


# =============== E-092 — the correction cascade ============================


@pytest.mark.eval_id("E-092")
def test_a_corrected_fact_re_derives_dependents_and_reports_the_prior_value():
    """E-092's counterexample: *a limitation date silently recomputed with no
    note that it moved.*

    Both halves are defects. Recomputing is right; recomputing SILENTLY is the
    failure — a value that changes with no history is one the advocate cannot
    reconcile against what they remember, and they will assume they misread it.
    """
    before = (
        Derived(name="limitation", value="2026-03-14",
                from_facts=("fact_invoice",)),
        Derived(name="forum", value="the District Court",
                from_facts=("fact_value",)),
    )
    after = (
        Derived(name="limitation", value="2027-06-12",
                from_facts=("fact_invoice",)),
        Derived(name="forum", value="the District Court",
                from_facts=("fact_value",)),
    )

    touched = dependents(before, ("fact_invoice",))
    assert [d.name for d in touched] == ["limitation"], (
        "the cascade recomputed something the corrected fact does not touch")

    moved = changes(before, after)
    assert len(moved) == 1, "an unchanged value was reported as a change"
    assert moved[0].was == "2026-03-14" and moved[0].now == "2027-06-12"

    # THE PRIOR VALUE IS REQUIRED BY THE TYPE.
    with pytest.raises(ValueError):
        Change(name="limitation", was="   ", now="2027-06-12")


@pytest.mark.eval_id("E-092")
def test_advice_already_given_is_reported_as_superseded():
    """§5.4's THIRD PART, and the one a silent recompute loses.

    *Where earlier advice is affected, that is said in terms, including whether
    anything already done needs undoing.* An advocate who filed on Tuesday
    against a date that moved on Thursday needs to be TOLD. Showing them a
    corrected number is not telling them.
    """
    moved = (Change(name="limitation", was="2026-03-14", now="2027-06-12"),)
    prior = (
        PriorAdvice(what="file the recovery suit before 14 March",
                    given_at_turn="turn_2", rested_on=("limitation",)),
        PriorAdvice(what="serve the notice at the registered office",
                    given_at_turn="turn_3", rested_on=("forum",)),
    )

    at_risk = advice_at_risk(prior, moved)
    assert len(at_risk) == 1 and "recovery suit" in at_risk[0].what

    lines = report(moved, at_risk)
    assert any("was 2026-03-14, now 2027-06-12" in x for x in lines)
    assert any("superseded" in x for x in lines)

    # WHETHER ANYTHING NEEDS UNDOING IS A QUESTION SOMEBODY ANSWERS. An empty
    # `undo` is not "nothing does" -- it is nobody having said.
    assert unresolved_undo(moved) == ("limitation",)
    answered = (Change(name="limitation", was="2026-03-14", now="2027-06-12",
                       undo="nothing filed yet, so nothing to withdraw"),)
    assert unresolved_undo(answered) == ()


@pytest.mark.eval_id("E-092")
def test_where_re_derivation_changes_nothing_the_answer_is_one_line():
    """§5.4'S BOUND, and it protects the rule above it.

    A product that announced a cascade every turn would train the advocate to
    skip the section — and the real one would then arrive in a place they had
    learned to ignore.
    """
    lines = report(())
    assert len(lines) == 1
    assert "nothing changed" in lines[0]


@pytest.mark.eval_id("E-092")
def test_a_value_computed_for_the_first_time_is_a_change_with_no_prior():
    """Silently ADDING a limitation date is the same defect as silently moving
    one. "This was not computed before" is information."""
    before = ()
    after = (Derived(name="limitation", value="2027-06-12",
                     from_facts=("fact_invoice",)),)
    moved = changes(before, after)
    assert len(moved) == 1
    assert moved[0].was == "not computed before"


# =============== E-089 — quarantine ========================================


@refuses("B4", 0)
@pytest.mark.eval_id("E-089")
def test_quarantined_substance_is_unreachable_until_a_human_clears_it():
    """E-089's counterexample: *substance merged onto a file no conflict check
    had cleared.*

    Unreachable is a property of the TYPE. A public field with a comment saying
    "do not read this before clearance" is a comment.
    """
    q = Quarantined("the client says he paid the supplier in cash",
                    held_because="registry hit on the counterparty")

    assert q.reachable is False
    assert q.clearance is None
    assert reachable_substance((q,)) == ()

    # THE SUBSTANCE IS IN NO REPR, so it cannot arrive in a log line.
    assert "cash" not in repr(q)
    assert "registry hit" in repr(q)

    # AND THERE IS NO ACCESSOR. `release` is the only way out and it needs a
    # clearance, which a caller that has not cleared the matter cannot produce.
    assert not hasattr(q, "substance")

    released = q.release(Clearance(by="Priya", against="the conflict registry"))
    assert "cash" in released
    assert q.reachable is True
    assert reachable_substance((q,)) == ("registry hit on the counterparty",)


@refuses("B4", 1)
@pytest.mark.eval_id("E-089")
def test_a_quarantine_releases_exactly_once_and_the_second_call_raises():
    """*Release the quarantine EXACTLY ONCE.*

    Raised, not ignored. A second release is a caller that believes it is
    clearing something, and telling it nothing happened would leave that belief
    in place — while the thing being protected is a conflict check that
    actually ran, which is the absence nobody notices.
    """
    q = Quarantined("substance", held_because="a registry hit")
    q.release(Clearance(by="Priya", against="the registry"))

    with pytest.raises(AlreadyReleased) as exc:
        q.release(Clearance(by="Someone Else", against="nothing in particular"))
    assert "EXACTLY ONCE" in str(exc.value)
    assert "Priya" in str(exc.value), "the first clearance is not named"

    # THE FIRST CLEARANCE STANDS. A refused second release must not overwrite
    # who actually cleared it.
    assert q.clearance is not None and q.clearance.by == "Priya"


@refuses("B4", 2)
@pytest.mark.eval_id("E-089")
def test_a_clearance_names_who_what_and_against_what():
    """B4 names three and `against` is the one that gets dropped.

    "Cleared by Priya on Tuesday" records that somebody said yes and not what
    they looked at, which is unauditable the moment anyone asks.
    """
    with pytest.raises(TypeError):
        Clearance(by="Priya")
    with pytest.raises(ValueError):
        Clearance(by="Priya", against="   ")

    ok = Clearance(by="Priya", against="the conflict registry, 31 August")
    assert ok.at is not None, "a clearance with no time cannot be audited"

    # AND A QUARANTINE WITH NO REASON has nothing for a clearance to clear.
    with pytest.raises(ValueError) as exc:
        Quarantined("substance", held_because="  ")
    assert "nothing to be a clearance of" in str(exc.value)


# =============== E-093 — length tracks threads, not turns ==================


@pytest.mark.eval_id("E-093")
def test_answer_length_is_a_function_of_live_threads_not_turn_number(tmp_path):
    """E-093's counterexample: *length growing with turn count — recitation
    bloat returning.*

    THE FAILURE MODE IS AGREEABLE. Each turn recites a little more of what is
    established, because restating context reads as thorough, and by turn eight
    the advocate is scrolling past their own file to find the answer. Nothing
    is wrong in any single turn, which is why it needs a check across them.
    """
    from datetime import date as _date

    from nm.core.turn import TurnInput
    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    matter = None
    lengths: list[int] = []
    for message in (
            "we act for the plaintiff. the goods were supplied against "
            "invoices dated 14 March 2023 and nothing was paid.",
            "the defendant wrote on 12 June 2024 admitting the amount",
            "is the claim still in time",
            "what does that letter have to say for it to count",
            "and what should we file",
    ):
        out = engine.run(TurnInput(
            advocate_id="adv", message=message, matter_id=matter,
            today=_date(2026, 8, 31)))
        matter = out.matter.id if out.matter else matter
        lengths.append(len(out.answer.elements))

    assert len(lengths) == 5
    # ONE THREAD THROUGHOUT, so the last turn may not be longer than the
    # first. A bound rather than equality: retrieval legitimately produces a
    # ground on one turn and not another, and pinning the exact count would be
    # a test of the fixture rather than of the rule.
    assert lengths[-1] <= lengths[0] + 1, (
        f"the answer grew with the conversation: {lengths}. Length must track "
        f"live threads, not turn number.")
    assert max(lengths) - min(lengths) <= 2, (
        f"answer length is drifting turn on turn: {lengths}")
