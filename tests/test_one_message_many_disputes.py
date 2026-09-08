"""A message describing N disputes opens ONE thread and SAYS it looked like N.

THIS FILE ONCE ASSERTED THE OPPOSITE, and the reversal is the point.

BK-27 found a real defect: a brief opening `first ... second ... third ...`
produced one thread carrying one posture, one chronology and one limitation
across three disputes, and the advocate was told every deadline on the file
had passed while a trespass five days old sat in it. The fix read a COUNT and
opened a thread per dispute. These tests asserted that.

THEN THE READ WAS MEASURED, on six briefs with known counts, three runs:

    committed prompt, run 1     3/6
    committed prompt, run 2     2/6
    a rewritten prompt          2/6

It is unstable on identical input -- the three-dispute brief returned 3 on one
run and 0 on the next -- and it missed a four-dispute enumeration entirely,
which is the shape BK-27 exists for. Acting on a read that is right a third to
a half of the time is a coin flip whichever way it defaults.

WHY THE ASYMMETRY NO LONGER DECIDES IT
----------------------------------------
`threading.py` says a wrong SPLIT is visible and recoverable while a wrong
MERGE inverts the advice SILENTLY. That is right, and the word carrying it is
`silently`. A merge the advocate is TOLD about is not silent: they see the
count and one sentence corrects it, and `opens_new_dispute` already opens the
second thread the moment they describe one.

And a wrong split costs more than that docstring assumed. Three threads from
one claim means three posture gates -- which is why every matter in the
advocate's own file list read `2 THREAD(S) AWAITING POSTURE` -- and the
cross-file pass then argued across the fragments, reporting a contradiction
between two halves of one transaction.

So the rule is now: ONE thread, and the count is stated. What is kept from
BK-27 is everything that measured well -- the per-item quotation guard, the
label taken from the read rather than from the opening words, and `counted`,
because `nobody counted` and `one dispute` are still different facts.
"""
from __future__ import annotations

import pytest

from nm.core.dispute import Described, interpret
from nm.core.threading import bind
from nm.domain.matter import Fact, Matter, Provenance
from nm.domain.quotable import Quotable


def _matter() -> Matter:
    return Matter.create(advocate_id="adv", title="file")


def _fact(text: str) -> Fact:
    return Fact.create(
        statement=text,
        provenance=Provenance(kind="advocate_statement", turn="t1"))


def _described(*pairs: tuple[str, str]) -> tuple[Described, ...]:
    return tuple(Described(quoted=q, label=name) for q, name in pairs)


# --------------------------------------------------------------- the rule ---

@pytest.mark.parametrize("n", [2, 3, 5])
def test_a_message_describing_n_disputes_still_opens_one_thread(n):
    """THE INVARIANT, and it is the reverse of what this file used to assert.

    The count is not good enough to split a file on. It is good enough to
    mention.
    """
    described = _described(*((f"the {i}th thing that happened",
                              f"dispute {i}") for i in range(n)))
    result = bind(_matter(), "several things have happened",
                  _fact("several things have happened"), described=described)

    assert result.thread is not None
    assert not result.others, (
        "the file was split on a read that measures 2-3 of 6 across six "
        "briefs and is unstable on identical input")
    assert result.looks_like == n, (
        f"the count was neither acted on NOR reported, so the advocate has no "
        f"way to know the message read as {n} disputes")


def test_the_thread_is_labelled_from_the_first_dispute_read():
    """KEPT FROM BK-27. `_label` took the opening words, so a three-dispute
    brief was filed under 'My client is Ravi Kumar, a retired bank employee'
    -- a label naming no dispute at all."""
    described = _described(
        ("he was put into possession and no sale deed followed", "sale deed"),
        ("two cheques came back unpaid", "dishonoured cheques"),
    )
    result = bind(_matter(), "My client is a retired bank employee. First, ...",
                  _fact("My client is a retired bank employee. First, ..."),
                  described=described)
    assert result.thread.label == "sale deed"
    assert "retired bank employee" not in result.thread.label


def test_a_single_described_dispute_reports_one():
    described = _described(("one thing happened", "the thing"))
    result = bind(_matter(), "one thing", _fact("one thing"),
                  described=described)
    assert result.looks_like == 1
    assert not result.others


# ------------------------------------------- the third state, S1 and §9 -----

def test_a_read_that_did_not_run_still_produces_a_thread():
    """AN ABSENT COUNT MUST NOT REMOVE THE THREAD, and must not read as one.

    `counted` survives the reversal because the distinction it carries does:
    a fallback thread and a thread from a message that really described one
    dispute are different facts, and G-SPLIT has to be able to say which.
    """
    result = bind(_matter(), "something happened", _fact("something happened"),
                  described=())
    assert result.thread is not None
    assert result.counted is False, (
        "a bind with no count reported itself as counted, so a fallback is "
        "indistinguishable from a finding -- defect shape S1")
    assert result.looks_like == 0


# ------------------------------------------------- the quotation guard ------

def test_a_dispute_the_advocate_did_not_describe_is_not_counted():
    """KEPT FROM BK-27, and it matters more now not less.

    The count is stated to the advocate. A fabricated span inflating it would
    put a number in front of them that nothing in their own words supports.
    """
    said = "First, the wall came down. Second, the cheque bounced."
    read = interpret(Quotable(turn=said), {
        "verdict": "cannot_tell", "quoted": "", "why": "no file yet",
        "disputes": [
            {"quoted": "the wall came down", "label": "trespass"},
            {"quoted": "the cheque bounced", "label": "cheque"},
            {"quoted": "he also assaulted the watchman", "label": "assault"},
        ]})
    assert [d.label for d in read.described] == ["trespass", "cheque"]


def test_the_guard_can_be_seen_to_pass_something():
    """POSITIVE CONTROL. A guard that dropped everything would satisfy the
    test above for the wrong reason -- S11."""
    said = "First, the wall came down. Second, the cheque bounced."
    read = interpret(Quotable(turn=said), {
        "verdict": "cannot_tell", "quoted": "", "why": "no file yet",
        "disputes": [{"quoted": "the wall came down", "label": "trespass"}]})
    assert len(read.described) == 1


def test_the_count_is_read_whatever_the_verdict_says():
    """`verdict` is this message against the FILE; `described` is this message
    against ITSELF. Still two questions, and the second still has no file in
    it."""
    said = "First, the wall came down. Second, the cheque bounced."
    for verdict in ("continues", "opens", "cannot_tell"):
        read = interpret(Quotable(turn=said), {
            "verdict": verdict,
            "quoted": "the wall came down" if verdict == "opens" else "",
            "why": "because",
            "disputes": [
                {"quoted": "the wall came down", "label": "trespass"},
                {"quoted": "the cheque bounced", "label": "cheque"},
            ]})
        assert len(read.described) == 2, f"the count was lost on {verdict!r}"
