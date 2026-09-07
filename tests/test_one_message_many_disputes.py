"""A message describing N disputes produces N threads. BK-27.

THE RULE, NOT THE SCENARIO. The defect was found on a brief about an agreement
of sale, two dishonoured cheques and a trespass -- but nothing here mentions
any of those, because the rule is about COUNTING and not about land or cheques.
A test that asserted "the Ravi Kumar brief makes three threads" would pass on a
special case and teach nothing about the fourth dispute.

WHAT WENT WRONG, AND WHERE IT ACTUALLY LIVED
----------------------------------------------
`threading.bind` answered WHICH thread a message belongs to. It never answered
HOW MANY the message describes. Rule 4 -- the empty matter -- returned exactly
one thread unconditionally, and the engine did not even make the dispute read
there. The justification was a comment in `turn.py`:

    with no thread yet, there is nothing to confuse it with

There is. The disputes inside the message, with each other. So any brief that
opened `first ... second ... third ...` produced ONE thread carrying ONE
posture, ONE chronology and ONE limitation across all of them -- on the first
turn of every matter, in every practice area.

Measured on the served turn that found it: `cause_reads: 1`, three issues
emitted, all three carrying the limitation computed from the first dispute's
accrual, and the thread labelled `'My client is Ravi Kumar, a retired bank
employee'` -- the opening words of the brief, naming no dispute at all.

WHY THE DIRECTION MATTERS, and it is `threading.py`'s own argument: a wrong
SPLIT duplicates work, is visible, and the advocate corrects it in a turn. A
wrong MERGE attaches one thread's posture and limitation to facts they do not
govern, every citation stays correct, and the advice inverts silently.
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
    return tuple(Described(quoted=q, label=name)
                 for q, name in pairs)


# --------------------------------------------------------------- the rule ---

@pytest.mark.parametrize("n", [2, 3, 5])
def test_a_message_describing_n_disputes_opens_n_threads(n):
    """THE INVARIANT. Not two, not `n` capped at some number -- n."""
    described = _described(*((f"the {i}th thing that happened",
                              f"dispute {i}") for i in range(n)))
    result = bind(_matter(), "several things have happened",
                  _fact("several things have happened"), described=described)

    assert result.thread is not None
    made = [result.thread, *result.others]
    assert len(made) == n, (
        f"{n} disputes described and {len(made)} thread(s) opened. A message "
        f"that describes several disputes must not put one posture and one "
        f"limitation across all of them.")
    assert len({t.id for t in made}) == n, "the threads are not distinct"


def test_each_thread_is_labelled_from_its_own_dispute():
    """THE LABEL IS NOT THE FIRST LINE OF THE MESSAGE.

    `_label` took the opening words, so a three-dispute brief was filed under
    'My client is Ravi Kumar, a retired bank employee' -- a label naming no
    dispute, on a thread holding three.
    """
    described = _described(
        ("he was put into possession and no sale deed followed", "sale deed"),
        ("two cheques came back unpaid", "dishonoured cheques"),
    )
    result = bind(_matter(), "My client is a retired bank employee. First, ...",
                  _fact("My client is a retired bank employee. First, ..."),
                  described=described)

    labels = [result.thread.label, *(t.label for t in result.others)]
    assert labels == ["sale deed", "dishonoured cheques"], labels
    for label in labels:
        assert "retired bank employee" not in label


def test_the_other_disputes_are_returned_and_not_discarded():
    """They must reach the caller, or the split is invisible and the advocate
    is advised on one dispute having asked about three."""
    described = _described(("thing one happened", "one"),
                           ("thing two happened", "two"))
    result = bind(_matter(), "two things", _fact("two things"),
                  described=described)
    assert result.others, "the extra disputes were dropped inside bind"
    assert result.created is True


# ------------------------------------------- the third state, S1 and §9 -----

def test_a_read_that_did_not_run_still_produces_a_thread():
    """AN ABSENT COUNT MUST NOT REMOVE THE THREAD.

    Falling back to one thread is right -- a turn needs something to bind to.
    What is not right is that fallback being indistinguishable from a message
    that really described one dispute, which is what `counted` records.
    """
    result = bind(_matter(), "something happened", _fact("something happened"),
                  described=())
    assert result.thread is not None
    assert not result.others
    assert result.counted is False, (
        "a bind with no count reported itself as counted, so a fallback thread "
        "is indistinguishable from a found one -- defect shape S1")


def test_one_described_dispute_is_a_finding_not_a_fallback():
    """The distinction the previous test protects, from the other side."""
    result = bind(_matter(), "one thing", _fact("one thing"),
                  described=_described(("one thing happened", "the thing")))
    assert result.thread is not None
    assert not result.others


# ------------------------------------------------- the quotation guard ------

def test_a_dispute_the_advocate_did_not_describe_opens_no_thread():
    """A THREAD IS CREATED FROM THESE SPANS, so a span nobody wrote must not
    reach `bind`. The guard drops the item rather than keeping it with a
    warning: a thread invented from words the advocate never said is worse
    than a thread not created."""
    said = "First, the wall came down. Second, the cheque bounced."
    quotable = Quotable(turn=said)
    read = interpret(quotable, {
        "verdict": "cannot_tell", "quoted": "", "why": "no file yet",
        "disputes": [
            {"quoted": "the wall came down", "label": "trespass"},
            {"quoted": "the cheque bounced", "label": "cheque"},
            {"quoted": "he also assaulted the watchman", "label": "assault"},
        ]})
    labels = [d.label for d in read.described]
    assert labels == ["trespass", "cheque"], (
        f"a fabricated dispute survived the guard: {labels}")


def test_the_guard_can_be_seen_to_pass_something():
    """POSITIVE CONTROL. A guard that dropped everything would satisfy the
    test above for the wrong reason -- S11, a check that cannot fail."""
    said = "First, the wall came down. Second, the cheque bounced."
    read = interpret(Quotable(turn=said), {
        "verdict": "cannot_tell", "quoted": "", "why": "no file yet",
        "disputes": [{"quoted": "the wall came down", "label": "trespass"}]})
    assert len(read.described) == 1


def test_the_count_is_read_whatever_the_verdict_says():
    """`verdict` is this message against the FILE; `described` is this message
    against ITSELF. A brief on an empty matter has no useful verdict and may
    still describe three disputes, which is exactly the case that broke."""
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
        assert len(read.described) == 2, (
            f"the count was lost on verdict={verdict!r}")
