"""B-093 — a document's content was handed to the model as the advocate's claim.

THE MEASURED DEFECT
---------------------
Measured on the bytes, 5 September 2026. `MatterSummary.as_context()` -- which
its own docstring describes as given to EVERY extraction and EVERY derivation
-- produced byte-identical output for:

    the advocate saying     "the agreement was registered"
    page 3 of a sale deed reading the same words

under a heading that said "WHAT THE ADVOCATE HAS ALREADY TOLD ME ON THIS
MATTER". The provenance was recorded, persisted, and never shown to anything
that reasons.

WHY THIS IS NOT A COSMETIC LOSS
---------------------------------
A claim is what the client says happened. A document is what will be put to a
court. The whole of the product's grounding posture rests on the difference,
and the model could not see it -- so a derivation could rely on a documented
fact believing it was untested, or on a claim believing it was evidenced, and
nothing in the output would look wrong either way.

IT WAS NOT REACHING AN ADVOCATE, AND THAT IS WHY IT WAS FIXED NOW
-------------------------------------------------------------------
`nm.core.intake` is UNWIRED, so no document-sourced fact exists yet. Once it
lands the failure is silent: the first person to notice would be someone
relying in court on a "documented" fact that was never in a document.

FOUND BY THE SAME QUESTION AS B-092, ASKED OF A SECOND POPULATION
--------------------------------------------------------------------
B-091 asked which fields on the record nothing WRITES. This asks which fields
the record holds and the model is never TOLD -- the same shape one layer out,
and the answer to "what does this product actually remember".
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from nm.domain import summary
from nm.domain.matter import Basis, Fact, Matter, Posture, Provenance, Role, Thread

pytestmark = pytest.mark.class_a

SAID = Provenance(kind="advocate_statement", turn="t1")
DEED = Provenance(kind="document", turn="t1",
                  document="sale_deed.pdf", page=3)
STATEMENT = "the agreement was registered"


def _loose(**over) -> Fact:
    """A `document` provenance the constructor would REFUSE.

    `Provenance.__post_init__` demands a document and a page for that kind, so
    this cannot arrive through the front door -- and the renderer must not
    rely on a guard that lives somewhere else. A guard right in the core and
    assumed at the edge is CLAUDE.md 8, which is how 40/40 offline passed
    while every served turn crashed.
    """
    prov = Provenance.__new__(Provenance)
    for name, value in {"kind": "document", "turn": "t1", "document": None,
                        "page": None, "span": None, **over}.items():
        object.__setattr__(prov, name, value)
    return Fact(id="f1", statement=STATEMENT, provenance=prov)


def _context(provenance: Provenance) -> str:
    fact = Fact(id="f1", statement=STATEMENT, provenance=provenance)
    thread = replace(Thread.create(label="the sale"),
                     posture=Posture(role=Role.PLAINTIFF, basis=Basis.STATED),
                     chronology=("f1",))
    matter = replace(Matter.create(advocate_id="adv_1", title="a sale"),
                     facts=(fact,), threads=(thread,))
    return summary.build(matter, thread.id).as_context()


def test_a_documented_fact_and_a_claimed_one_are_not_the_same_bytes():
    """THE DEFECT, STATED AS A RULE.

    Not "the account contains 'sale_deed.pdf'" -- that would pass on an
    account that names the document while still presenting it as something
    the advocate said. Two inputs that differ in a way the model must act on
    have to differ in what the model is given.
    """
    assert _context(SAID) != _context(DEED), (
        "the file note is identical whether the advocate said it or a "
        "document did:\n" + _context(SAID))


def test_the_document_and_the_page_are_both_named():
    """A page number is what makes it checkable. `sale_deed.pdf` alone tells
    a reader a document exists; `p.3` tells them where to look, which is the
    difference between an attribution and a claim of one."""
    context = _context(DEED)
    assert "sale_deed.pdf" in context and "p.3" in context, context


def test_an_advocate_statement_carries_no_prefix():
    """THE BOUND, and it is a budget question and not a tidiness one.

    Marking the ordinary case would put four words on every line of every
    account to say the ordinary thing, and those words come out of a measured
    character budget -- paid for in facts that then do not fit.
    """
    assert _context(SAID).count(STATEMENT) == 1
    assert f": {STATEMENT}" not in _context(SAID), (
        "an ordinary advocate statement was given a source prefix")


def test_the_heading_is_true_of_every_line_under_it():
    """A heading that names a source is a claim about everything beneath it.

    It said "WHAT THE ADVOCATE HAS ALREADY TOLD ME" with document-sourced
    facts sitting under it unmarked. A heading that is WRONG about provenance
    is worse than no heading, because a reader who trusts it stops looking.
    """
    context = _context(DEED)
    heading = context.splitlines()[0]
    assert "ADVOCATE HAS ALREADY TOLD ME" not in heading.upper(), (
        f"the heading still asserts the advocate said all of this: {heading}")
    assert "source" in heading.lower(), (
        f"the heading does not say a source may be named: {heading}")


def test_a_document_provenance_with_no_page_still_names_the_document():
    """Provenance refuses a document kind without a page, so this cannot
    arrive through the constructor -- but the renderer must not depend on
    that guard holding somewhere else. A guard that is right in the core and
    assumed at the edge is CLAUDE.md 8.
    """
    assert summary._source(_loose(document="sale_deed.pdf"))         == "sale_deed.pdf: "


def test_a_document_kind_with_no_name_says_so_rather_than_nothing():
    """The third state. A document-sourced fact whose document was lost must
    not silently render as the advocate's word -- that is the exact defect,
    arriving through the degraded path instead of the ordinary one."""
    assert summary._source(_loose()) == "a document: "
