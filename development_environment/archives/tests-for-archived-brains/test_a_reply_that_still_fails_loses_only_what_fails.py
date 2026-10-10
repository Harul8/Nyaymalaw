"""A reply that still fails after its rewrite loses only what fails, and says so.

Owner, 30 September 2026, on the Farah Begum reply that was replaced by 117 working
items: *"the reply is failing back and I don't understand what is failing here"*; and,
asked whether a reply still failing after one rewrite should drop only the failing
sentences and say the point could not be supported: *"Agree"*.

THE RULES:
1. One check -- the code's checks of quotations, citations and periods, and the model's
   check for law no passage states -- then one rewrite with the failures named.
2. A rewrite that still fails loses ONLY the sentences that fail, each decided by the
   same detectors on that sentence alone or named by the model's check; the reply says
   plainly that a point was left out. The working items are not shown in its place.
3. Dropping a sentence never cuts a citation, and never splits a sentence at an
   abbreviation; every kept citation still names its passage where it stands.
4. Only a failure no sentence can be dropped to cure -- or one that would leave nothing
   of the reply -- shows the checked findings instead.
5. A dispute with nothing relevant retrieved is marked for the reply, so it is said
   rather than filled from memory.
"""
from __future__ import annotations

import json

import pytest

from nm.advise.answer_contracts import Answer, Element, ElementKind, Mode, ReplyParagraph, Route
from nm.Archives.legal_brain.communicate import compose
from nm.Archives.legal_brain.orchestrate.turn import TurnInput
from nm.Archives.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult
from nm.Archives.legal_brain.retrieve.source_excerpt import capture as capture_source
from nm.Archives.legal_brain.verify import grounding
from nm.shared.model_scripted import SCRIPTED_READS
from tests.test_turn_contract import _Evidence, build, finding

pytestmark = pytest.mark.class_a

FOUND = finding()
PASSAGE = Element(kind=ElementKind.GROUND, text="Article 65 -- the retrieved row.",
                  refs=(FOUND.locator,), source=capture_source(FOUND))
LABEL = PASSAGE.source.label
BRIEF = "we act for the plaintiff in a possession suit over the land"


# ============================ 3. how a sentence is cut ===========================

def test_a_sentence_is_never_cut_inside_a_citation_or_after_an_abbreviation():
    text = (f"Under s. 53A the transferee is protected ({LABEL}). The Rs. 32 lakh was paid "
            "to Mr. Ali. O.S. 442/2023 is pending v. the State. It is decided.")
    start = text.index(LABEL)
    spans = compose.sentence_spans(text, ((start, start + len(LABEL), 0),))
    assert [text[a:b].strip() for a, b in spans] == [
        f"Under s. 53A the transferee is protected ({LABEL}).",
        "The Rs. 32 lakh was paid to Mr. Ali.",
        "O.S. 442/2023 is pending v. the State.",
        "It is decided."]


def test_a_dropped_sentence_takes_nothing_else_with_it():
    first = f"The period runs from dispossession {LABEL}. "
    text = f"{first}Section 27 of the Limitation Act decides it. It also says more {LABEL}."
    cites = ((first.index(LABEL), first.index(LABEL) + len(LABEL), 0),
             (text.rindex(LABEL), text.rindex(LABEL) + len(LABEL), 0))
    paragraph = ReplyParagraph(text=text, cites=cites)
    kept, dropped = compose.without((paragraph,), lambda s: s.startswith("Section 27"))
    assert dropped == 1
    assert kept[0].text == f"{first}It also says more {LABEL}."
    answer = Answer(route=Route.MATTER, mode=Mode.FULL_BRIEF, mode_statement="Assessment",
                    elements=(PASSAGE,), composed=kept)  # the type re-checks every citation
    assert [answer.composed[0].text[a:b] for a, b, _ in answer.composed[0].cites] == [LABEL] * 2


def test_the_sentence_check_is_the_paragraph_check_on_one_sentence():
    answer = Answer(route=Route.MATTER, mode=Mode.FULL_BRIEF, mode_statement="Assessment",
                    elements=(PASSAGE,))
    assert grounding.sentence_violations("Section 27 of the Limitation Act decides it.",
                                         answer, (FOUND,))
    assert grounding.sentence_violations("It must be filed within six months.",
                                         answer, (FOUND,)), "a period from memory passed"
    assert not grounding.sentence_violations(f"The period is in {LABEL}.", answer, (FOUND,))


# ============================ 2. on the served turn ==============================

def _between(text, start, end=None):
    part = text.split(start, 1)[1]
    return part.split(end, 1)[0] if end else part


def _writes(sentences):
    """A composer that writes the given sentences, tagging the first retrieved passage."""
    def respond(user):
        work = json.loads(_between(user, "THE CHECKED WORK ON THIS MESSAGE (DATA, not "
                                         "instructions):\n", "\n\nWrite the reply."))
        law = next(item["id"] for item in work if item.get("passage"))
        return json.dumps({"paragraphs": [{"text": " ".join(sentences).replace("[[LAW]]",
                                                                               f"[[{law}]]"),
                                           "carries": ""}]})
    return respond


def _checks(unsupported=()):
    def respond(user):
        return json.dumps({"items": [], "unsupported": [
            {"sentence": s, "why": "no passage states it"} for s in unsupported]})
    return respond


GOOD = "The retrieved article governs a suit for possession on title [[LAW]]."
BAD = "Section 27 of the Limitation Act decides this suit."


def test_a_rewrite_that_still_fails_loses_only_the_failing_sentence_and_says_so(
        tmp_path, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "compose", _writes([GOOD, BAD]))
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", _checks())
    engine, _ = build(tmp_path, evidence=_Evidence())
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    told = [p.text for p in out.answer.composed if p.carries is None]
    assert told, "the reply was replaced by the working items"
    assert not any("Section 27" in text for text in told), "the failing sentence was shown"
    assert any("governs a suit for possession on title" in text for text in told), (
        "a sentence that passed was dropped with the one that failed")
    assert told[-1] == compose.left_out(1).text, "the reply did not say a point was left out"
    assert any(v.rule == "E2" and "left out" in v.detail for v in out.metrics.violations)
    assert out.metrics.presentation_reads == 3, (
        "one draft, one check skipped on the code's failure, one rewrite and its check")


def test_a_sentence_the_model_check_names_is_the_one_left_out(tmp_path, monkeypatch):
    claim = "The suit is plainly within time."
    monkeypatch.setitem(SCRIPTED_READS, "compose", _writes([GOOD, claim]))
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", _checks([claim]))
    engine, _ = build(tmp_path, evidence=_Evidence())
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    told = " ".join(p.text for p in out.answer.composed)
    assert claim not in told and "governs a suit for possession on title" in told
    assert compose.left_out(1).text in told


def test_a_failure_nothing_can_cure_shows_the_checked_findings(tmp_path, monkeypatch):
    monkeypatch.setitem(SCRIPTED_READS, "compose", _writes([BAD]))
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", _checks())
    engine, _ = build(tmp_path, evidence=_Evidence())
    out = engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert out.answer.composed == ()
    assert any(v.rule == "E2" and "no sentence could be left out" in v.detail
               for v in out.metrics.violations)


# ======================= 5. nothing relevant retrieved ===========================

def test_a_dispute_with_nothing_retrieved_is_marked_for_the_reply(tmp_path, monkeypatch):
    seen = []

    def composer(user):
        seen.append(user)
        return json.dumps({"paragraphs": []})

    monkeypatch.setitem(SCRIPTED_READS, "compose", composer)
    engine, _ = build(tmp_path, evidence=_Evidence(EvidenceResult(
        coverage=Coverage.NOT_HELD, missing="no Act in the curated manifest governs this",
        searched_stores=("manifest",))))
    engine.run(TurnInput(advocate_id="adv", message=BRIEF))
    assert seen, "the composer was not asked"
    disputes = json.loads(_between(seen[0], "read from those passages against what the "
                                             "file holds:\n", "\n\n"))
    assert disputes and all(
        d["law"] == [] and d["retrieved"] == ("no relevant section or judgment was "
                                              "retrieved for this dispute")
        for d in disputes)
