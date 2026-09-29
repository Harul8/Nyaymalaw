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

from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.understand import dispute
from nm.legal_brain.understand.dispute import Described, interpret
from nm.legal_brain.understand.threading import bind
from tests.test_every_dispute_is_cleanly_identified import labelled
from nm.work_the_file.matter_contracts import Fact, Matter, Provenance


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
def test_a_source_bound_inventory_opens_each_dispute_without_shared_state(n):
    """THE INVARIANT, and it is the reverse of what this file used to assert.

    The count is not good enough to split a file on. It is good enough to
    mention.
    """
    described = _described(*((f"the {i}th thing that happened",
                              f"dispute {i}") for i in range(n)))
    message = "; ".join(d.quoted for d in described)
    result = bind(_matter(), message, _fact(message), described=described)

    assert result.thread is not None
    assert len(result.others) == n - 1
    assert len({t.id for t in (result.thread, *result.others)}) == n
    assert len(result.allocations) == n
    assert all(not t.chronology and not t.posture.resolved for t in result.others)
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
    message = "My client is a retired bank employee. " + "; ".join(d.quoted for d in described)
    result = bind(_matter(), message, _fact(message), described=described)
    assert result.thread.label == "sale deed"
    assert "retired bank employee" not in result.thread.label


def test_a_single_described_dispute_reports_one():
    described = _described(("one thing happened", "the thing"))
    result = bind(_matter(), "one thing happened", _fact("one thing happened"),
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

SAID = "First, the wall came down. Second, the cheque bounced."


def test_a_dispute_the_advocate_did_not_describe_is_not_counted():
    """KEPT FROM BK-27, and it matters more now not less.

    The count is stated to the advocate. A label pointing at a sentence the
    advocate did not write would put a number in front of them that nothing in
    their own words supports -- so the reading is refused, and what it had found
    before the unsupported label is kept to show them.
    """
    data = labelled(SAID, [("", "the wall", "possession_of_property", ["First,"]),
                           ("", "the cheque", "cheque", ["Second,"])])
    data["sentences"].append({"unit": "S3", "role": "act", "about": [
        {"other_side": 0, "thing": 1, "kind": "bodily_harm", "dispute": "new"}]})
    read = interpret(Quotable(turn=SAID), data)
    assert read.refused and "not in the message" in read.refused
    assert read.found == ("the wall", "the cheque") and not read.described


def test_the_guard_can_be_seen_to_pass_something():
    """POSITIVE CONTROL. A guard that dropped everything would satisfy the
    test above for the wrong reason -- S11."""
    read = interpret(Quotable(turn=SAID), labelled(
        SAID, [("", "the wall", "possession_of_property", ["First,"]),
               ("", "the cheque", "cheque", ["Second,"])]))
    assert [d.label for d in read.described] == ["the wall", "the cheque"]


def test_the_verdict_is_derived_from_the_labels_never_asked():
    """`verdict` was a separate answer, and a reading that listed new disputes
    while saying the file merely continued contradicted itself. Where every
    sentence sits decides it: any new dispute opens new work."""
    read = interpret(Quotable(turn=SAID), labelled(
        SAID, [("", "the wall", "possession_of_property", ["First,"]),
               ("", "the cheque", "cheque", ["Second,"])]))
    assert read.opens and len(read.described) == 2


# ===== the schema names only the disputes this matter actually holds =======

def test_no_label_may_name_a_dispute_that_is_not_on_this_matter():
    """THE RULE: the model is never shown an ID it could offer wrongly.

    `interpret` refuses a sentence placed on a dispute the matter does not
    hold. Listing the permitted values in the schema means the answer cannot
    be formed in the first place -- the guard and the contract agreeing rather
    than the guard cleaning up after it. `new` and `cannot_tell` always belong.
    """
    about = dispute.schema_for(Quotable(turn="x"), thread_ids=frozenset({"th_1", "th_2"})
                               )["properties"]["sentences"]["items"]["properties"]["about"]
    assert about["items"]["properties"]["dispute"]["enum"] == [
        "new", "cannot_tell", "th_1", "th_2"]
    empty = dispute.schema_for(Quotable(turn="x"))["properties"]["sentences"]["items"]
    assert empty["properties"]["about"]["items"]["properties"]["dispute"]["enum"] == [
        "new", "cannot_tell"]


def test_an_ordinary_continuing_message_describes_nothing_and_continues():
    """THE NEGATIVE CONTROL, and it records a fix that was WRONG once.

    A message that adds nothing contested is how an ordinary single-dispute
    matter opens: nothing is described, and `bind` creates the first thread. A
    reading with no dispute must continue, not refuse and not open.
    """
    said = "Please continue with the work."
    read = interpret(Quotable(turn=said), labelled(said, [], instructions=["Please"]))
    assert read.continues and not read.described and not read.refused
