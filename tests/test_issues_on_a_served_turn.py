"""D9 — the issue register, REACHED. E-060 and E-061 on a served turn.

The register itself has been right since slice 6: `classify` has no filter in
it, `accounted_for` returns what was lost rather than a count, and
`effect_for` derives the effect from the posture so a stale reading cannot be
stored. Nothing ever produced an `Issue`, so none of it ran (B-079) — a full
unit suite over a module the product never called.

These tests drive the ENGINE. What they assert is not that the register works
but that the turn reaches it, accounts for what it spotted, and puts the
result where an advocate reads it.
"""
from __future__ import annotations

from datetime import date

import pytest

from nm.core.turn import TurnInput
from nm.domain.answer import ElementKind
from nm.domain.issue import Disposition, DispositionState, Issue, IssueKind
from nm.domain.matter import Side
from nm.domain.quotable import Quotable
from tests.test_turn_contract import build

pytestmark = pytest.mark.class_a

FOR_PLAINTIFF = ("We act for the plaintiff, a supplier at Hyderabad. Goods "
                 "were supplied against invoices on 14 March 2023 and were "
                 "never paid for.")
FOR_DEFENDANT = ("We act for the defendant in a suit at Hyderabad. Goods were "
                 "supplied against invoices on 14 March 2023 and were never "
                 "paid for.")


def _run(tmp_path, message):
    engine, _ = build(tmp_path)
    return engine.run(TurnInput(advocate_id="adv_1", message=message,
                                today=date(2026, 9, 4)))


def _findings(out):
    """The ISSUE findings, not every finding on the turn.

    This took all of them, and it was wrong the moment a second feature
    emitted one: C7's inventory rows are findings too, and the next test
    asserted every finding carries a posture version. An inventory row has no
    posture and should not.

    `runs against` is the issue renderer's own vocabulary, asserted in this
    same file, so the filter and the format cannot drift apart silently. The
    deeper point is that FINDING elements from different features are
    indistinguishable to any consumer — worth a marker on `Element` if a third
    feature needs to tell them apart.
    """
    return [e.text for e in out.answer.elements
            if e.kind is ElementKind.FINDING and "runs against" in e.text]


@pytest.mark.eval_id("E-060")
def test_a_served_turn_puts_issues_in_front_of_the_advocate(tmp_path):
    """THE WIRING, asserted first. Everything below is about issues that
    reached the answer, and none of it means anything if none did."""
    findings = _findings(_run(tmp_path, FOR_PLAINTIFF))
    assert findings, (
        "no issue reached the answer. `nm/domain/issue.py` had a complete "
        "unit suite and no production caller for three slices.")


@pytest.mark.eval_id("E-061")
def test_the_same_issue_runs_the_other_way_on_the_opposite_posture(tmp_path):
    """E-061'S INVARIANT, ON THE WIRE.

    D9's second NEVER: *never build "this obstructs us" into the vocabulary*.
    A limitation point is not "a bar" — ours obstructs us, theirs disposes of
    their claim without our touching the merits.

    Asserted across two SERVED turns on the same facts, because the property
    that matters is what the advocate reads, and the effect is composed at
    render time from two things neither of which knows the answer alone.
    """
    plaintiff = " ".join(_findings(_run(tmp_path / "p", FOR_PLAINTIFF)))
    defendant = " ".join(_findings(_run(tmp_path / "d", FOR_DEFENDANT)))

    assert plaintiff and defendant
    assert plaintiff != defendant, (
        "the same issues read identically for both sides. The effect is "
        "supposed to be derived from the posture, so it cannot be.")
    assert "supports" in plaintiff or "opposes" in plaintiff
    assert ("opposes" in defendant) != ("opposes" in plaintiff) or \
           ("supports" in defendant) != ("supports" in plaintiff), (
        f"the effect did not flip between postures.\n"
        f"plaintiff: {plaintiff[:300]}\ndefendant: {defendant[:300]}")


@pytest.mark.eval_id("E-061")
def test_every_rendered_issue_carries_the_posture_version_it_was_computed_on(
        tmp_path):
    """A reading recorded WITHOUT its basis is one nobody can later tell is
    stale — which is the whole reason `effect` is not a stored field. The
    version has to travel to the advocate, not merely exist in the type."""
    for text in _findings(_run(tmp_path, FOR_PLAINTIFF)):
        assert "posture v" in text, (
            f"an issue was rendered with no posture version: {text}")


@pytest.mark.eval_id("E-060")
def test_an_issue_the_reading_offered_and_the_product_refused_is_disclosed(
        tmp_path):
    """A REFUSED ISSUE IS SAID, not dropped.

    Dropping it silently IS the measured defect — 641 of 3,192 labels
    discarded by a filter that decided what was relevant enough — with a
    better excuse attached.
    """
    from nm.core import issues

    read = issues.read(
        {"issues": [{"statement": "An issue from nowhere",
                     "kind": "substantive", "runs_against": "moving",
                     "quoted": "words the advocate never wrote"}]},
        "th_1", Quotable(file="the advocate wrote something else entirely"))
    assert read.refused, "an ungrounded issue was accepted"
    assert read.issues == ()


@pytest.mark.eval_id("E-060")
def test_one_refused_issue_does_not_discard_the_others():
    """THE MEASURED DEFECT WEARING A DIFFERENT HAT. A per-read refusal would
    be a filter with a good excuse: four sound issues lost because a fifth was
    not quotable."""
    from nm.core import issues

    account = "Goods were supplied against invoices and were never paid for."
    read = issues.read({"issues": [
        {"statement": "Sound one", "kind": "substantive",
         "runs_against": "moving", "quoted": "Goods were supplied"},
        {"statement": "Ungrounded", "kind": "substantive",
         "runs_against": "moving", "quoted": "never said this"},
        {"statement": "Sound two", "kind": "threshold",
         "runs_against": "moving", "quoted": "never paid for"},
    ]}, "th_1", Quotable(file=account))

    assert len(read.issues) == 2
    assert len(read.refused) == 1


@pytest.mark.eval_id("E-060")
def test_a_parked_issue_is_visible_rather_than_deleted():
    """THERE IS NO DELETE PATH, and the reason is that deleting is silent.

    An issue that will not be run appears on the considered-not-pursued line
    with its reason. This asserts the line renders, since a disposition
    nobody reads is a deletion with extra steps.
    """
    from nm.domain.issue import classify, considered_not_pursued

    spotted = (Issue(thread="th_1", statement="A point not worth running",
                     kind=IssueKind.SUBSTANTIVE, runs_against=Side.MOVING),)
    parked = classify(spotted, {spotted[0].id: Disposition(
        DispositionState.PARKED, reason="the client will not fund it")})

    lines = considered_not_pursued(parked)
    assert lines and "will not fund" in lines[0]


@pytest.mark.eval_id("E-060")
def test_nothing_spotted_is_a_different_answer_from_nothing_read():
    """THREE STATES. "No issues on this file" and "nobody read it for issues"
    are different sentences, and only one of them is a finding."""
    from nm.core import issues

    none_spotted = issues.read({"issues": []}, "th_1",
                               Quotable(file="an account"))
    assert none_spotted.state == "none_spotted"
    assert issues.UNREAD.state == "not_assessed"
