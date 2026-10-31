"""Only the failing piece is looked at again, and only it is blocked (plan AN.28, D2; owner, 31 Oct 2026).

"if a small part of the answer is not grounded or not verified, lets remove only that piece ... we should never
reject a complete section of the answer just because one specific detail has failed the verification"; "send only
those portions back to the model ... so that there is another round to verify it"; "if it is genuinely
unverifiable let's block it, if model thinks it's a clerical mismatch and is actually the same thing it should be
kept".

Writer v14 sends only the paragraphs that code's checks or the review find at fault back to the writer, with the
words at fault; the writer rewrites, keeps (the same thing written another way) or withdraws each; what still
fails is blocked sentence by sentence. Review v12 copies the words that mislead. Scripted fixtures with invented
papers exercise code's loop, admission and replay; they do not show how a real writer or reviewer behaves.
"""
import json
import threading

import pytest

from nm.core_engine import answer_sections, calculation, response_rendering, response_review, response_writer, turn
from nm.core_engine.calls import TurnCalls
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage
from tests.test_core_response_writer import two_disputes

pytestmark = pytest.mark.class_a

V14 = response_writer.REPAIRED_CONTRACT


def _result(data, tier):
    return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def para(kind, text, place):
    return {"kind": kind, "text": text, "uses": [], "place": place}


def section_of(dispute, middle):
    return [para("summary", f"In short for {dispute}.", "row_action"), para("limitation", middle, "risks"),
            para("next_step", f"Take the next step for {dispute}.", "next_steps")]


class Looking:
    """Writes each section from its script, reviews by markers, and answers each second look as the test says.

    A paragraph holding FAULT misleads: the review copies the sentence holding it as its words, or gives no words
    where the paragraph also holds WORDLESS. looks(dispute, round, to_check) returns the repairs."""

    knows_second_look = True

    def __init__(self, writes, looks=None):
        self.writes, self.looks_for = writes, looks or (lambda dispute, round_, to_check: [])
        self.lock, self.calls, self.rounds, self.second_looks, self.reviews = threading.Lock(), [], {}, [], []

    def context_budget(self, tier): return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        with self.lock:
            self.calls.append(prompt.operation)
        dispute = ((payload.get("this_part") or {}).get("dispute") or {}).get("id")
        if prompt.operation == "core_response_writer":
            units = self.writes.get(dispute, lambda: section_of(dispute, "Nothing more is known."))()
            return _result({"units": units, "checklist": [], "time_limit_ids": [], "by_when": None}, tier)
        if prompt.operation == "core_response_overview":
            return _result({"units": [{"kind": "next_step", "text": "Start with the first dispute.", "uses": []}]}, tier)
        if prompt.operation == "core_response_review":
            with self.lock:
                self.reviews.append(payload)
            misleading = []
            for unit in payload["complete_draft_proposal"]["units"]:
                if "FAULT" in unit["text"]:
                    words = [] if "WORDLESS" in unit["text"] else [
                        next(s for s in response_writer.sentences(unit["text"]) if "FAULT" in s).strip()]
                    misleading.append({"kind": "unsupported", "where": [unit["id"]], "evidence": [],
                                       "why": "Not borne out by the papers.", "words": words})
            return _result({"misleading": misleading, "could_be_better": [], "keep_shown": []}, tier)
        if prompt.operation == "core_response_cross_check":
            return _result({"conflicts": []}, tier)
        if prompt.operation == "core_response_repair":
            with self.lock:
                self.rounds[dispute] = self.rounds.get(dispute, 0) + 1
                self.second_looks.append((dispute, payload))
                round_ = self.rounds[dispute]
            return _result({"repairs": self.looks_for(dispute, round_, payload["to_check"])}, tier)
        raise AssertionError(prompt.operation)


def answered(model):
    """The two-dispute matter answered through the live loop (writer v14, review v12), rendered as v19, and replayed
    as a turn v9 saves it."""
    ctx, record, sources = two_disputes()
    calls, worked, execution = TurnCalls(model), calculation.skipped(), turn.execution_record(record)
    sections, crossed, overview = answer_sections.answer(
        calls, ctx, record, sources, interpretation={"units": []}, execution=execution, worked=worked, contract=V14)
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=crossed,
                                                  overview=overview, time_limits=worked,
                                                  contract=response_rendering.REPAIRED_CONTRACT)
    activity = {"contract": turn.CONTRACT, "interpretation": {"units": []}, "research": record, "sources": sources,
                "execution": execution, "calculation": worked, "rendering_contract": response_rendering.REPAIRED_CONTRACT,
                "sections": sections, "cross_check": crossed, "overview": overview}
    assert turn.validate_activity(activity, ctx, elements) == activity
    return ctx, elements, activity


def rewrite(text):
    return lambda dispute, round_, to_check: [{"paragraph": entry["paragraph"], "action": "rewrite",
                                               "rewritten": para("limitation", text, "risks"), "why": "Corrected.",
                                               "page_words": None, "question": None} for entry in to_check]


def test_only_the_paragraph_at_fault_goes_back_and_the_rest_stays_as_written():
    model = Looking({"D1": lambda: section_of("D1", "The deed was signed in a year the papers give. A FAULT claim here. "
                                                    "It binds both parties.")},
                    rewrite("The deed was signed in a year the papers give. It binds both parties."))
    ctx, elements, activity = answered(model)
    (dispute, looked), = model.second_looks
    entry, = looked["to_check"]
    assert dispute == "D1" and entry["paragraph"] == "U2" and entry["words_at_fault"] == ["A FAULT claim here."]
    assert entry["why"] == ["Not borne out by the papers."]
    # The writer is shown the whole piece as written beside the paragraph at fault.
    assert [p["id"] for p in looked["your_paragraphs"]] == ["U1", "U2", "U3"]
    first = activity["sections"][0]
    texts = [unit["text"] for unit in first["reviewed"]["draft"]["units"]]
    assert texts == ["In short for D1.", "The deed was signed in a year the papers give. It binds both parties.",
                     "Take the next step for D1."]
    assert first["trims"] == [] and first["fallback"] is None and len(first[answer_sections.LOOKS]) == 1
    assert not [element for element in elements if element["kind"] in ("NOTE", "FALLBACK")]


def test_a_date_that_stays_unsupported_costs_only_its_sentence_never_the_paragraph_or_section():
    # Invented: the writer keeps a date from its own memory through both second looks.
    middle = ("For acts before 1 March 2019 the earlier code applies. Its second section defines the offence. "
              "The papers do not say when the acts took place.")
    model = Looking({"D1": lambda: section_of("D1", middle)}, rewrite(middle))
    ctx, elements, activity = answered(model)
    first = activity["sections"][0]
    assert len(first[answer_sections.LOOKS]) == 2 and first["fallback"] is None
    assert [look["faults"][0]["words"] for look in first[answer_sections.LOOKS]] == [["1 March 2019"], ["1 March 2019"]]
    trimmed, = first["trims"]
    shown = [unit["text"] for unit in trimmed["draft"]["units"]]
    assert shown[1] == "Its second section defines the offence. The papers do not say when the acts took place."
    assert trimmed["draft"]["cut"] == {"t2:s1b2": ["For acts before 1 March 2019 the earlier code applies. "]}
    assert "1 March 2019" not in json.dumps(elements)
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert note["text"].startswith("Left out of this section: 1 statement from its paragraphs, because NM's check of "
                                   "dates still found a problem in it after NM looked at it again. What was found:")
    assert "What remains was checked again without it." in note["text"]


def test_a_paragraph_whose_fault_names_no_words_is_the_last_thing_left_out_and_the_section_stays():
    model = Looking({"D1": lambda: section_of("D1", "WORDLESS FAULT in this paragraph.")},
                    rewrite("WORDLESS FAULT in this paragraph."))
    ctx, elements, activity = answered(model)
    first = activity["sections"][0]
    trimmed, = first["trims"]
    assert trimmed["draft"]["dropped"] == ["t2:s1b2"] and first["fallback"] is None
    assert [unit["text"] for unit in trimmed["draft"]["units"]] == ["In short for D1.", "Take the next step for D1."]
    assert any(element["kind"] == "HEADING" and "Dispute 1" in element["text"] for element in elements)


def test_a_withdrawn_point_is_blocked_at_once_and_its_question_joins_the_asks():
    def withdraw(dispute, round_, to_check):
        return [{"paragraph": entry["paragraph"], "action": "withdraw", "rewritten": None, "why": "Not in the papers.",
                 "page_words": None, "question": "When was the notice served on your client?"} for entry in to_check]
    model = Looking({"D1": lambda: section_of("D1", "The notice was served on the client. A FAULT about the date.")},
                    withdraw)
    ctx, elements, activity = answered(model)
    first = activity["sections"][0]
    draft = first["reviewed"]["draft"]
    assert draft["cut"] == {"t2:s1b2": ["A FAULT about the date."]} and len(first[answer_sections.LOOKS]) == 1
    assert [unit["text"] for unit in draft["units"]][1] == "The notice was served on the client."
    assert draft["units"][-1]["place"] == "ask" and draft["units"][-1]["text"] == "When was the notice served on your client?"
    assert any(element["text"] == "When was the notice served on your client?" for element in elements)
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert note["text"] == ("Left out of this section: 1 statement from its paragraphs, because NM's checks found a problem "
                            "in it that a second look could not settle. The rest was checked without it.")


def test_the_same_thing_written_another_way_is_kept_and_the_review_is_told_why():
    def same(dispute, round_, to_check):
        return [{"paragraph": entry["paragraph"], "action": "same_thing", "rewritten": None,
                 "why": "The papers write the same figure with a long dash.", "page_words": "Ac 3 - 12",
                 "question": None} for entry in to_check]
    model = Looking({"D1": lambda: section_of("D1", "A FAULT extent of 3 acres 12 guntas.")}, same)
    answered(model)
    told = [review.get("writer_notes") for review in model.reviews if review["what_you_review"].get("dispute") == "Dispute 1"]
    assert told[0] is None and told[1] == [{"words": "A FAULT extent of 3 acres 12 guntas.",
                                            "why": "The papers write the same figure with a long dash."}]


def test_what_the_writer_returns_on_a_second_look_is_admitted_for_what_code_can_use():
    proposal = {"units": [para("summary", "In short.", "row_action"), para("limitation", "A point.", "risks")],
                "checklists": [{"checklist": [], "time_limit_ids": [], "by_when": None}]}
    faults = [{"position": 2, "kind": "check", "words": ["A point."], "why": "A quotation not found.", "near": None}]
    returned = {"repairs": [
        {"paragraph": "U2", "action": "same_thing", "rewritten": None, "why": "Same.", "page_words": "A point",
         "question": None},
        {"paragraph": "U2", "action": "withdraw", "rewritten": None, "why": "", "page_words": None, "question": None},
        {"paragraph": "U9", "action": "withdraw", "rewritten": None, "why": "", "page_words": None, "question": None},
        {"paragraph": "U2", "action": "rewrite", "rewritten": None, "why": "", "page_words": None, "question": None}]}
    out, decisions, aside = response_writer.apply_repairs(proposal, returned, faults)
    # A quotation code refused is never the same thing as other words; the second repair then decides it.
    assert decisions == [{"position": 2, "action": "withdraw", "why": "", "page_words": None, "question": None}]
    assert [entry["repair"] for entry in aside] == [1, 3, 4] and out == proposal
    with pytest.raises(SchemaViolation):
        response_writer.apply_repairs(proposal, {"repairs": "none"}, faults)


@pytest.mark.parametrize("text,pieces", [
    ("One. Two? Three!", ["One. ", "Two? ", "Three!"]),
    ("Smt. A. Sharma signed it under W.P.No.123/2020. The court agreed.",
     ["Smt. A. Sharma signed it under W.P.No.123/2020. ", "The court agreed."]),
    ("See No. 5 of the list. Mohd. Iqbal agreed. It ends here", ["See No. 5 of the list. ", "Mohd. Iqbal agreed. ",
                                                                  "It ends here"]),
    ("He said “it is done.” Then he left.", ["He said “it is done.” ", "Then he left."]),
    ("The sum was Rs. 500 i.e. five hundred. Paid.", ["The sum was Rs. 500 i.e. five hundred. ", "Paid."]),
])
def test_a_paragraph_s_sentences_join_to_it_again_and_never_end_on_a_short_form(text, pieces):
    assert response_writer.sentences(text) == pieces and "".join(pieces) == text


def test_blocking_cuts_the_sentences_holding_the_words_and_leaves_out_a_paragraph_it_cannot_place():
    proposal = {"units": [para("summary", "First. Second holds X here. Third.", "row_action"),
                          para("limitation", "Only one sentence.", "risks")]}
    cut, left = response_writer.block(proposal, [{"position": 1, "words": ["holds X"]},
                                                 {"position": 2, "words": ["not in it"]}], {})
    assert cut == {1: ["Second holds X here. "]} and left == [2]
    # Words that run over two sentences take both; a paragraph none of whose sentences would remain is left out.
    cut, left = response_writer.block(proposal, [{"position": 1, "words": ["First. Second"]}], {}, cut, [])
    assert cut == {1: ["First. ", "Second holds X here. "]} and left == []
    cut, left = response_writer.block(proposal, [{"position": 1, "words": ["Third"]}], {}, cut, [])
    assert cut == {} and left == [1]


def test_a_review_copies_the_words_that_mislead_or_they_are_set_aside():
    from nm.core_engine import response_authorities
    ctx, record, sources = two_disputes()
    draft = response_writer.accept({"units": [para("summary", "In short.", "row_action"),
                                              para("limitation", "One fine sentence. One wrong sentence.", "risks")],
                                    "checklists": [{"checklist": [], "time_limit_ids": [], "by_when": None}]},
                                   ctx, sources, contract=V14, parts=[{"dispute_id": "D1", "units": 2}], section=1)
    authorities = response_authorities.check(ctx, record, sources, draft)
    deps = response_review._dependencies(ctx, record, sources, draft, None, authority_evidence=authorities,
                                         contract=response_review.WORDED_CONTRACT)
    returned = {"misleading": [{"kind": "unsupported", "where": ["U2"], "evidence": [], "why": "Wrong.",
                                "words": ["one  WRONG sentence", "not there"]},
                               {"kind": "unsupported", "where": ["U1"], "evidence": [], "why": "No words."}],
                "could_be_better": [], "keep_shown": []}
    admitted = response_review._accept_v10(returned, deps, response_review.WORDED_CONTRACT)
    first, second = admitted["proposal"]["findings"]
    assert first["words"] == [{"unit_id": draft["units"][1]["id"], "text": "One wrong sentence"}]
    assert second["words"] == [] and admitted["accepted"] is False
    assert admitted["proposal"]["set_aside"] == [
        {"where": "misleading 1", "why": "its words are not found in the paragraph or item it names: 'not there'"}]
    # The prompt asks for the words, and speaks of the figures copies read differently in general terms.
    assert "words: the shortest stretch" in response_review.SYSTEM_V12 and "guntas" not in response_review.SYSTEM_V12


def test_a_v14_draft_replays_exactly_what_was_cut_and_left_out():
    ctx, record, sources = two_disputes()
    proposal = {"units": [para("summary", "In short.", "row_action"),
                          para("limitation", "Keep this. Cut this one. Keep that.", "risks"),
                          para("next_step", "A step to leave out.", "next_steps")],
                "checklists": [{"checklist": [], "time_limit_ids": [], "by_when": None}]}
    draft = response_writer.accept(proposal, ctx, sources, contract=V14, parts=[{"dispute_id": "D1", "units": 1}],
                                   section=1, left_out=[3], cut={2: ["Cut this one. "]})
    assert [unit["text"] for unit in draft["units"]] == ["In short.", "Keep this. Keep that."]
    assert draft["dropped"] == ["t2:s1b3"] and draft["cut"] == {"t2:s1b2": ["Cut this one. "]}
    assert response_writer.validate(draft, ctx, sources) == draft
    for forged in ({**draft, "cut": {"t2:s1b2": ["Not a sentence of it. "]}}, {**draft, "dropped": ["t2:s1b9"]}):
        with pytest.raises(ValueError):
            response_writer.validate(forged, ctx, sources)
    # The row's line left out after its second looks is no fault of the rest.
    left = response_writer.accept(proposal, ctx, sources, contract=V14, parts=[{"dispute_id": "D1", "units": 1}],
                                  section=1, left_out=[1])
    assert [unit["place"] for unit in left["units"]] == ["risks", "next_steps"]


def test_only_a_v14_draft_collects_its_paragraphs_faults():
    ctx, record, sources = two_disputes()
    proposal = {"units": [para("summary", "In short.", "row_action"),
                          {"kind": "law", "text": "A law with no source.", "uses": [], "place": "advice"}],
                "checklists": [{"checklist": [], "time_limit_ids": [], "by_when": None}]}
    with pytest.raises(response_writer.UnitFaults) as faults:
        response_writer.accept(proposal, ctx, sources, contract=V14, parts=[{"dispute_id": "D1", "units": 2}],
                               section=1, faults=[])
    fault, = faults.value.faults
    assert fault["position"] == 2 and fault["words"] == [] and "source dependencies" in fault["reason"]
    with pytest.raises(ValueError):
        response_writer.accept(proposal, ctx, sources, contract=response_writer.PRESENTED_CONTRACT,
                               parts=[{"dispute_id": "D1", "units": 2}], section=1, faults=[])


def test_a_date_the_writer_shows_is_the_papers_own_is_accepted_only_from_the_papers():
    ctx = {"conversation": [], "latest": {"text": "We were served on 5/7/21 by hand."}, "documents": []}
    faults = [{"position": 2, "kind": "date", "words": ["5 July 2021"], "why": "", "near": None}]
    keep = [{"position": 2, "action": "same_thing", "why": "Written as 5/7/21.", "page_words": "served on 5/7/21",
             "question": None}]
    assert response_writer.clerical_dates(ctx, faults, keep) == [
        {"position": 2, "date_words": "5 July 2021", "page_words": "served on 5/7/21"}]
    elsewhere = [{**keep[0], "page_words": "served on 5/7/22"}]
    assert response_writer.clerical_dates(ctx, faults, elsewhere) == []
    other = [{"position": 2, "kind": "date", "words": ["6 July 2021"], "why": "", "near": None}]
    assert response_writer.clerical_dates(ctx, other, keep) == []
