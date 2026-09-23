"""A SPAN ACCEPTED AS THE ADVOCATE'S WORDS IS KEPT AS THE ADVOCATE'S WORDS.

THE MEASURED DEFECT, 23 September 2026, live matter 2 -- a landlord's three
disputes, one already before the Rent Controller. The posture gate had just
been repaired and the turn got one gate further, where it was WITHHELD:

    output withheld by G-QUOTE: quoted text is not verbatim in any retrieved
    span: 'The tenant Prakash Rao has been in occupation since 1 August 2019
    under a registered lease for three years.'

That sentence is the ADVOCATE'S, word for word. The proof read returned it as
HELD material wrapped in quotation marks; `Quotable.accepts` rightly accepted
it, because folding removes the marks; and the MODEL'S COPY -- marks and all --
was kept and rendered as `It is held on "The tenant Prakash Rao ...".` G-QUOTE
reads a double-quoted span as a claim about RETRIEVED text, found none, and the
advocate got nothing.

The renderer, `f"It is held on {'; '.join(pos.material)}."`, holds no quote
mark at all, which is why the `repr` sweep of 0df3b79 could not see it: the
claim arrived inside the data. And it is the string section 3.1 of the dated
review recorded for matter 2 on 22 September -- the one noted there as carrying
no apostrophe and so not explained by `repr`. This is what it was.

THE RULE: `accepts` answers "is this their words?" and folds typography to do
it; `verbatim` answers "then what exactly did they write?". A read keeps the
second.
"""
from __future__ import annotations

import pytest

from nm.domain.quotable import Quotable

pytestmark = pytest.mark.class_a

SENTENCE = ("The tenant Prakash Rao has been in occupation since 1 August 2019 "
            "under a registered lease for three years")
BRIEF = Quotable(turn=f"One, eviction.\n{SENTENCE}.\nHe holds over.")

#: How models wrap a quotation. Every one of these folds to the advocate's
#: words, and every one of them is a mark the advocate did not write.
WRAPPED = (f'"{SENTENCE}."', f"“{SENTENCE}”", f"'{SENTENCE}'",
           f"‘{SENTENCE}.’")


@pytest.mark.parametrize("copy", WRAPPED)
def test_the_marks_a_model_adds_are_not_kept(copy):
    """THE REGRESSION. Accepted, and returned without the model's marks."""
    assert BRIEF.accepts(copy)
    kept = BRIEF.verbatim(copy)
    assert kept == SENTENCE, f"kept {kept!r}"
    for mark in ('"', "“", "”"):
        assert mark not in kept, (
            "a double quotation mark the MODEL supplied reached the kept span; "
            "rendered, it is read by G-QUOTE as a claim about retrieved text")


def test_the_advocates_capitals_come_back_when_the_model_changed_them():
    """The same rule for case: what is kept is what they WROTE."""
    assert BRIEF.verbatim("the tenant prakash rao has been in occupation") == \
        "The tenant Prakash Rao has been in occupation"


def test_what_the_advocate_did_not_write_is_not_returned():
    """`verbatim` is not a way round the guard: it answers only where `accepts`
    does, and returns nothing otherwise."""
    assert BRIEF.verbatim("The landlord has been in occupation since 2019") == ""
    assert BRIEF.verbatim("") == ""


def test_the_proof_read_keeps_the_advocates_words(monkeypatch):
    """AT THE SITE THAT RENDERED IT. `ProofPosition.material` is the one
    accepted-advocate span that reaches prose -- as "It is held on ..." in the
    answer and as an ESTABLISHED line in the file memory -- so both renderers
    are covered by keeping the right string once, here."""
    from nm.core import proof_read

    source = proof_read.__loader__.get_source(proof_read.__name__)
    assert "quotable.verbatim(" in source, (
        "the proof read no longer keeps the advocate's words for HELD material; "
        "the model's copy -- quotation marks and all -- will reach the screen")
