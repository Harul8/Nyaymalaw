"""The cross-file pass: no ids at the advocate, and no arguing across a split.

TWO FINDINGS, ONE FUNCTION. J-5 and J-4(3) both live in `_exposure`, and the
served line that carried them is the same one:

    Across this file: The acknowledgement of debt asserts that the defendant
    recognizes a debt is due. on thr_016c52910d37 - This damages the defence
    in the non-payment case ...

Two things are wrong with that sentence.

J-5 -- `thr_016c52910d37` is one of this product's own keys. An advocate
cannot act on a question addressed to an identifier they have never seen
(B-103). The prompt SENT the ids, so the read answered in ids and the element
rendered them straight back out; sending labels removes it at source.

J-4(3) -- the two "disputes" being compared are halves of ONE transaction.
The count read had split a single claim -- goods supplied, unpaid,
acknowledged -- into three threads, and this pass then reported a
contradiction between them. An advocate has no way to know that conflict is
invented: it looks exactly like the product's most valuable output.

WHY A GUARD RATHER THAN A BETTER COUNT. The count read measures 2-3 of 6 and
is unstable on identical input; fixing it is a decision recorded in J-4. This
guard is independent of that decision and removes the worst consequence
whichever way it goes.

WHAT IS DELIBERATELY STILL COMPARED. A thread created this turn against every
thread already on the file. That is the feature working, and withholding it
would trade an invented conflict for a missed one -- which is the worse
direction, because a missed cross-thread exposure is the defect E-082 exists
for.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nm.core.adversarial import build_exposure_prompt
from nm.core.turn import _label_of

pytestmark = pytest.mark.class_a


def _t(tid: str, label: str):
    return SimpleNamespace(id=tid, label=label)


def _considered(threads, born):
    """The selection `_exposure` makes, in the same shape.

    Mirrored here rather than driven through a served turn because the
    behaviour under test is WHICH PAIRS are offered, and a served turn would
    additionally depend on what the model then says about them.
    """
    cons = tuple(t for t in threads if t.id not in born)
    if len(born) == 1:
        cons = tuple(threads)
    elif born:
        first = next((t for t in threads if t.id in born), None)
        if first is not None:
            cons = (*cons, first)
    return [t.id for t in cons]


# ------------------------------------------------------------------ J-5 ---

def test_the_exposure_prompt_carries_no_internal_ids():
    """THE LEAK AT ITS SOURCE. A prompt that sends ids gets ids back."""
    prompt = build_exposure_prompt(
        (("thr_abc123def456", "Supply of steel"),
         ("thr_999888777666", "Cheque bounce")))
    assert "thr_" not in prompt.user, (
        f"the prompt sends this product's own keys, so the read will answer "
        f"in them:\n{prompt.user}")
    assert "Supply of steel" in prompt.user, (
        "the disputes are not named at all, so the read has nothing to "
        "distinguish them by")


def test_a_thread_is_named_to_the_advocate_by_its_label():
    labels = {"thr_abc": "Supply of steel"}
    assert _label_of("thr_abc", labels) == "'Supply of steel'"
    assert _label_of("Supply of steel", labels) == "'Supply of steel'"


def test_an_unrecognised_id_is_never_shown_raw():
    """THE FALLBACK MATTERS MORE THAN THE HAPPY PATH.

    A read that answers with an id anyway must not put one in front of an
    advocate. Nor may it say `unknown`, which names no dispute at all -- the
    advocate would be left worse off than with the id.
    """
    said = _label_of("thr_zzz999", {"thr_abc": "Supply of steel"})
    assert "thr_" not in said, f"a raw id reached the advocate: {said}"
    assert said.strip(), "the fallback says nothing at all"


# --------------------------------------------------------------- J-4(3) ---

def test_threads_born_from_one_message_are_not_argued_across():
    """THE INVARIANT. Three threads from one message leave no pair."""
    new = [_t("n1", "a"), _t("n2", "b"), _t("n3", "c")]
    considered = _considered(new, frozenset(t.id for t in new))
    assert len(considered) < 2, (
        f"the pass would compare threads created by one message with each "
        f"other, which is how two halves of one transaction were reported as "
        f"a contradiction: {considered}")


def test_a_new_thread_is_still_weighed_against_the_standing_file():
    """THE HALF THAT MUST NOT BE LOST.

    Withholding the new threads entirely would trade an invented conflict for
    a missed one, and a missed cross-thread exposure is the defect E-082
    exists for.
    """
    standing = [_t("old1", "Kukatpally tenancy"), _t("old2", "Recovery suit")]
    new = [_t("n1", "a"), _t("n2", "b"), _t("n3", "c")]
    considered = _considered(standing + new, frozenset(t.id for t in new))
    assert "old1" in considered and "old2" in considered
    assert any(t.startswith("n") for t in considered), (
        "no new thread was weighed against the standing file at all")


def test_one_new_thread_is_not_a_split():
    """A single new dispute is not a split and nothing is held back."""
    standing = [_t("old1", "x"), _t("old2", "y")]
    considered = _considered(standing + [_t("n1", "z")], frozenset({"n1"}))
    assert considered == ["old1", "old2", "n1"]


def test_a_file_with_no_new_threads_is_untouched():
    """POSITIVE CONTROL. A guard that changed the ordinary case would be worse
    than the defect: every multi-thread file goes through this path."""
    standing = [_t("old1", "x"), _t("old2", "y")]
    assert _considered(standing, frozenset()) == ["old1", "old2"]
