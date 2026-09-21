"""A phrase list may ROUTE. It may not DECIDE, and its miss may not be silent.

THE AUDIT THAT PRODUCED THIS, 7 September 2026
------------------------------------------------
Asked for a forensic sweep of hard-coding, the population came from the code:
every module-level literal collection in `backend/nm/`. Most of it is correct and some
of it is REQUIRED —

    CURATED     `LIMITATION_ARTICLE`, `ELEMENTS`, `SECTION_FOR`. CLAUDE.md §5
                mandates these: exact match decides which Act, and fuzzy may
                never identify. Removing them is the previous build's failure.
    THE DOUBLE  every `_SCRIPTED_*` list in `backend/nm/adapters/model/scripted.py`.
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

import pathlib

import pytest
from nm.core.turn import TurnEngine, TurnInput
from nm.domain.answer import Route

pytestmark = pytest.mark.class_a


# ===================== a phrase list may not discard a matter ===============

@pytest.mark.parametrize("message", [
    "what can you do about the limitation period on this suit?",
    "who are you going to say served the notice?",
    "what areas of the decree are still open?",
    "how do you work out the period for a possession suit?",
])
def test_a_matter_is_never_routed_away_by_a_phrase_inside_it(
        message, tmp_path):
    """THE DEFECT, AS A RULE. Not "these four strings route correctly" —
    the rule is that a message DISCLOSING A MATTER is a matter, whatever
    else it happens to contain."""
    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv", message=message))
    assert out.answer.route is Route.MATTER, (
        f"{message!r} discloses a matter and was routed as a question about "
        f"the product. The advocate's matter is discarded on a phrase that "
        f"happened to be embedded in it.")


@pytest.mark.parametrize("message", [
    "what can you do",
    "who are you",
    "what areas do you cover?",
    "how do you work",
])
def test_a_question_about_the_product_is_still_answered_as_one(message,
                                                               tmp_path):
    """THE BOUND. A rule that routed everything to MATTER would pass every
    test above and run a full workup on "who are you".

    DRIVEN THROUGH THE READ. `classify_route` is the fallback now and always
    says MATTER, so asserting against it would assert nothing -- which it
    would have done silently, since the assertion above it would still pass.
    """
    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    out = engine.run(TurnInput(advocate_id="adv", message=message))
    assert out.answer.route is Route.NON_MATTER


def test_the_route_is_read_and_never_counted():
    """WHY IT IS A READ AND NOT A BETTER LIST.

    B-124 composed the two keyword lists so the product-question branch
    required the absence of a matter. That fixed four measured phrasings and
    LEFT THE SHAPE: whichever list is consulted first still decides, on words
    somebody thought of.

    The advocate settled it on 7 September 2026 — *even if one word or two
    words, it need not be a greeting; it can be the actual dispute. Let the
    model decide.* Both lists and both length rules are gone.
    """
    from nm.core import turn as turn_module

    src = (pathlib.Path(turn_module.__file__)).read_text(encoding="utf-8")
    code = chr(10).join(ln for ln in src.splitlines()
                        if not ln.lstrip().startswith("#"))
    assert "_MATTER_SIGNALS" not in code, (
        "the matter keyword list is back; a list decides on the words "
        "somebody thought of, and the next phrasing is not among them")
    assert "_ABOUT_NM" not in code
    assert "len(text.split()) <= 3" not in code, (
        "the route counts words again. 'bail' is one word and a case fact")
    assert "len(text.split()) > 25" not in code, (
        "the mode counts words again. A long question is a question")


# ================= a phrase list's MISS may not be silent ===================

@pytest.mark.parametrize("message", [
    "is there anything from the High Court on this?",
    "has any court decided this point?",
    "what have the courts said about section 18?",
    "any decisions I can rely on?",
])
def test_former_phrase_list_misses_reach_the_investigation_model(message):
    """BK-91-AC5 replaces the measured miss, not with a longer phrase list."""
    from tests.test_bounded_judgment_investigation import offer, run
    observed = []
    def read(prompt, schema):
        import json
        observed.append(json.loads(prompt.user)['basis']['instruction']['text'])
        return offer(prompt, schema)
    result = run(read=read, message=message)
    assert observed == [message] and len(result.results) == 1


def test_a_recognised_request_still_searches():
    """Existing wording can still produce an admitted search."""
    from tests.test_bounded_judgment_investigation import run
    for message in ("is there any judgment on this?", "show me some case law"):
        assert len(run(message=message).results) == 1


def test_a_turn_that_did_not_search_for_authority_says_so():
    """THE DEFECT, AS A RULE. An answer carrying provisions and no
    authorities reads as "there are none" — S1, an absent input reading as a
    result. The miss becomes a stated limit, and four words from the advocate
    get them the search.
    """
    import inspect

    body = inspect.getsource(TurnEngine._investigate)
    assert "text=run.disclosure()" in body
    from tests.test_bounded_judgment_investigation import run
    result = run(round_budget=0)
    assert "0 retrieval round(s) returned" in result.disclosure()
    assert "does not establish complete legal coverage" in result.disclosure()


def test_side_blind_turns_cannot_enter_the_investigation_lane():
    """Lack of provisions is no longer a reason to hide an unsearched need;
    the posture restriction remains a real boundary."""
    import inspect

    body = inspect.getsource(TurnEngine._derive)
    assert "if not side_blind:\n            self._investigate(" in body
    assert "_wants_authority" not in body
