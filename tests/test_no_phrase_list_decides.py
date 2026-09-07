"""A phrase list may ROUTE. It may not DECIDE, and its miss may not be silent.

THE AUDIT THAT PRODUCED THIS, 7 September 2026
------------------------------------------------
Asked for a forensic sweep of hard-coding, the population came from the code:
every module-level literal collection in `nm/`. Most of it is correct and some
of it is REQUIRED —

    CURATED     `LIMITATION_ARTICLE`, `ELEMENTS`, `SECTION_FOR`. CLAUDE.md §5
                mandates these: exact match decides which Act, and fuzzy may
                never identify. Removing them is the previous build's failure.
    THE DOUBLE  every `_SCRIPTED_*` list in `nm/adapters/model/scripted.py`.
                A test double's whole job is to be scenario-shaped.
    VOCABULARY  enum values, feature ids, format fragments.

— and two were real defects, both measured before they were touched.

ONE: `_ABOUT_NM` DISCARDED MATTERS
------------------------------------
A bare substring test on common English, checked BEFORE the matter signals.
Four of five realistic matter questions were routed away as questions about
the product:

    "what can you do about the limitation period on this suit?"
    "who are you going to say served the notice?"
    "what areas of the decree are still open?"
    "how do you work out the period for a possession suit?"

Each contains a matter signal — suit, notice, decree, possession — and each
got "Taking this as a question about what I do."

TWO: `_WANTS_AUTHORITY` MISSED FOUR OF SIX WAYS TO ASK FOR AUTHORITY
----------------------------------------------------------------------
    False  "is there anything from the High Court on this?"
    False  "has any court decided this point?"
    False  "what have the courts said about section 18?"
    False  "any decisions I can rely on?"

A miss meant NO SEARCH, and an answer with provisions and no authorities reads
as "there are none". Defect shape S1.

NEITHER WAS FIXED BY ADDING PHRASES. Every list anybody writes leaves out the
next phrasing — B-031 is the standing proof, where the posture reader was ten
exact phrases and "we act for the workman" was not among them.
"""
from __future__ import annotations

import pytest

from nm.core.turn import TurnEngine, classify_route
from nm.domain.answer import Route

pytestmark = pytest.mark.class_a


# ===================== a phrase list may not discard a matter ===============

@pytest.mark.parametrize("message", [
    "what can you do about the limitation period on this suit?",
    "who are you going to say served the notice?",
    "what areas of the decree are still open?",
    "how do you work out the period for a possession suit?",
])
def test_a_matter_is_never_routed_away_by_a_phrase_inside_it(message):
    """THE DEFECT, AS A RULE. Not "these four strings route correctly" —
    the rule is that a message DISCLOSING A MATTER is a matter, whatever
    else it happens to contain."""
    route, _, _ = classify_route(message)
    assert route is Route.MATTER, (
        f"{message!r} discloses a matter and was routed as a question about "
        f"the product. The advocate's matter is discarded on a phrase that "
        f"happened to be embedded in it.")


@pytest.mark.parametrize("message", [
    "what can you do",
    "who are you",
    "what areas do you cover?",
    "how do you work",
])
def test_a_question_about_the_product_is_still_answered_as_one(message):
    """THE BOUND. A rule that routed everything to MATTER would pass every
    test above and run a full workup on "who are you"."""
    route, _, _ = classify_route(message)
    assert route is Route.NON_MATTER


def test_the_two_lists_compose_rather_than_racing():
    """WHY IT IS A RULE AND NOT AN ORDERING TWEAK.

    Swapping the order would fix these four and leave the shape: a message
    with no matter signal and an embedded product phrase would still be
    decided by whichever list was consulted first. The product-question
    branch REQUIRES the absence of a matter, which is the rule the phrase
    list was standing in for.
    """
    import inspect

    body = inspect.getsource(classify_route)
    assert "discloses_a_matter" in body
    assert "and not discloses_a_matter" in body, (
        "the product-question branch no longer requires the absence of a "
        "matter, so it can win against a message that discloses one")


# ================= a phrase list's MISS may not be silent ===================

@pytest.mark.parametrize("message", [
    "is there anything from the High Court on this?",
    "has any court decided this point?",
    "what have the courts said about section 18?",
    "any decisions I can rely on?",
])
def test_these_ways_of_asking_for_authority_are_not_recognised(message):
    """THE MEASUREMENT, PINNED — and it is deliberately asserting the MISS.

    The keyword list does not catch these. That is not the defect being fixed
    here and a longer list is not the fix: every list leaves out the next
    phrasing. This pins what the list actually does, so the disclosure below
    is known to be doing real work rather than covering a case that never
    arises.
    """
    assert not TurnEngine._wants_authority(message)


def test_a_recognised_request_still_searches():
    """THE BOUND on the pinning above: the list must still catch what it was
    written for, or the disclosure would fire on every turn."""
    assert TurnEngine._wants_authority("is there any judgment on this?")
    assert TurnEngine._wants_authority("show me some case law")


def test_a_turn_that_did_not_search_for_authority_says_so():
    """THE DEFECT, AS A RULE. An answer carrying provisions and no
    authorities reads as "there are none" — S1, an absent input reading as a
    result. The miss becomes a stated limit, and four words from the advocate
    get them the search.
    """
    import inspect

    body = inspect.getsource(TurnEngine._derive)
    assert "I did not search for authority on this turn" in body
    assert "if not wants_authority" in body, (
        "the disclosure is not on the miss branch, so it either never fires "
        "or fires when the search DID run")


def test_the_disclosure_is_bounded_to_a_turn_that_retrieved_something():
    """E-093 is about length growing, and a line on every turn is how that
    starts. A turn that retrieved nothing has a bigger problem and already
    says so; a side-blind turn may not present an authority set at all."""
    import inspect

    body = inspect.getsource(TurnEngine._derive)
    assert "not wants_authority and not side_blind and result.findings" in body
