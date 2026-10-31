"""The take-up adds a paragraph or gives a reason for each item it is asked about (plan AN.29, D10; findings A3, A4, A7, A2, A5).

Where the independent review finds that a piece passes over items of the record - or mentions them without what the advice needs -
one call shown only those items, in full, beside everything the piece was written from, gives a paragraph for each or a reason for
declining. Code admits a paragraph as it admits any (the piece is admitted again afterwards), takes nothing from a call that names an
item not asked about or an item twice, adds no paragraph of a kind the piece has its one of already, and keeps a reason for the review
to weigh. The papers here are invented.
"""
import json
from copy import deepcopy

import pytest

from nm.core_engine import response_writer
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import items_of, matter

pytestmark = pytest.mark.class_a


def unit(kind, text, place, *uses):
    return {"kind": kind, "text": text, "uses": list(uses), "place": place}


PROPOSAL = {"units": [unit("summary", "In short, the claim was allowed.", "row_action"), unit("next_step", "Check the records.", "next_steps")]}


def add(items, paragraph):
    return {"items": items, "paragraph": paragraph}


def test_a_paragraph_for_an_item_asked_about_is_added_to_the_piece_and_the_piece_given_is_not_changed():
    given = deepcopy(PROPOSAL)
    made, decisions, aside = response_writer.apply_take_up(
        given, {"additions": [add(["E2", "E5"], unit("limitation", "Two orders are not taken up here.", "risks"))], "declined": []},
        ["E2", "E5", "E6"])
    assert given == PROPOSAL, "the piece it was given is untouched"
    assert [u["text"] for u in made["units"]][-1] == "Two orders are not taken up here." and len(made["units"]) == 3
    assert decisions == [{"item": "E2", "action": "added", "unit": 3}, {"item": "E5", "action": "added", "unit": 3}] and aside == []


def test_a_reason_for_declining_is_kept_for_the_review_and_an_answer_for_each_item_is_in_the_order_it_was_asked():
    made, decisions, aside = response_writer.apply_take_up(
        PROPOSAL, {"additions": [add(["E6"], unit("summary", "Suits are pending.", "advice"))],
                   "declined": [{"items": ["E5", "E2"], "why": "The first paragraph already says it."}]}, ["E2", "E5", "E6"])
    assert decisions == [{"item": "E2", "action": "declined", "why": "The first paragraph already says it."},
                         {"item": "E5", "action": "declined", "why": "The first paragraph already says it."},
                         {"item": "E6", "action": "added", "unit": 3}] and aside == [] and len(made["units"]) == 3


@pytest.mark.parametrize("returned,wanted,where,why", [
    ({"additions": [add(["E9"], unit("summary", "x", "advice"))], "declined": []}, ["E2"], "addition 1",
     "takes up no item asked about, or none not already answered"),
    ({"additions": [add([], unit("summary", "x", "advice"))], "declined": []}, ["E2"], "addition 1",
     "takes up no item asked about, or none not already answered"),
    ({"additions": [add(["E2"], None)], "declined": []}, ["E2"], "addition 1", "gives no paragraph"),
    ({"additions": [add(["E2"], unit("summary", "x", "row_action"))], "declined": []}, ["E2"], "addition 1",
     "a paragraph placed 'row_action' is not one a take-up adds"),
    ({"additions": [add(["E2"], unit("summary", "x", "row_ready"))], "declined": []}, ["E2"], "addition 1",
     "a paragraph placed 'row_ready' is not one a take-up adds"),
    ({"additions": [add(["E2"], unit("summary", "x", "ask"))], "declined": []}, ["E2"], "addition 1",
     "a paragraph placed 'ask' is not one a take-up adds"),
    ({"additions": [], "declined": [{"items": ["E2"], "why": "  "}]}, ["E2"], "reason 1", "'E2' is declined with no reason"),
    ({"additions": [], "declined": [{"items": ["E9"], "why": "It is not in the record."}]}, ["E2"], "reason 1",
     "'E9' is not an item asked about, or is already answered"),
    ({"additions": [add(["E2"], unit("summary", "x", "advice"))], "declined": [{"items": ["E2"], "why": "Twice."}]}, ["E2"], "reason 1",
     "'E2' is not an item asked about, or is already answered"),
])
def test_what_code_can_use_nothing_of_is_set_aside_with_why_and_never_a_reason_to_refuse_the_rest(returned, wanted, where, why):
    made, decisions, aside = response_writer.apply_take_up(PROPOSAL, returned, wanted)
    assert {"where": where, "why": why} in aside
    if where == "addition 1" or "Twice" in str(returned):
        assert [entry["action"] for entry in decisions] in ([], ["added"]), "an item answered once is answered once"
    assert len(made["units"]) in (2, 3)


def test_a_question_may_be_placed_asked_and_a_paragraph_that_is_not_a_unit_is_set_aside():
    made, decisions, aside = response_writer.apply_take_up(
        PROPOSAL, {"additions": [add(["E2"], unit("question", "Do you want this taken up?", "ask"))], "declined": []}, ["E2"])
    assert decisions == [{"item": "E2", "action": "added", "unit": 3}] and aside == [] and made["units"][-1]["place"] == "ask"
    made, decisions, aside = response_writer.apply_take_up(PROPOSAL, {"additions": [add(["E2"], "text")], "declined": []}, ["E2"])
    assert decisions == [] and aside == [{"where": "addition 1", "why": "gives no paragraph"}]


def test_the_overview_takes_up_only_in_the_kinds_it_adds_and_each_is_placed_for_it():
    overview = {"units": [unit("greeting", "Hello.", "ties"), unit("next_step", "Do this first.", "do_first")]}
    made, decisions, aside = response_writer.apply_take_up(
        overview, {"additions": [add(["E2"], {"kind": "limitation", "text": "A thing is left out.", "uses": []}),
                                 add(["E5"], {"kind": "greeting", "text": "Hi.", "uses": []}),
                                 add(["E6"], {"kind": "next_step", "text": "Do more.", "uses": []})], "declined": []},
        ["E2", "E5", "E6"], overview=True)
    assert [d["item"] for d in decisions] == ["E2"] and made["units"][-1]["kind"] == "limitation" and "place" in made["units"][-1]
    assert [entry["why"] for entry in aside] == ["a paragraph of kind 'greeting' is not one the overview adds",
                                                  "a paragraph of kind 'next_step' is not one the overview adds"]


@pytest.mark.parametrize("returned", [None, {}, {"additions": "none", "declined": []}, {"additions": [], "declined": "none"}, [1]])
def test_an_answer_with_neither_additions_nor_reasons_is_refused_as_a_shape_that_cannot_be_used(returned):
    with pytest.raises(SchemaViolation, match="neither additions nor reasons"):
        response_writer.apply_take_up(PROPOSAL, returned, ["E2"])


def test_a_paragraph_is_cited_by_the_paragraphs_whose_uses_rest_on_a_page_the_item_rests_on():
    item = {"cite": ["DOC1", "DOC2"]}
    proposal = {"units": [unit("analysis", "One.", "advice", {"source_id": "DOC1"}), unit("analysis", "Two.", "advice", {"source_id": "M1"}),
                          unit("analysis", "Three.", "advice", {"source_id": "DOC2"}, "not a use")]}
    assert response_writer.cited_by(proposal, item) == ["U1", "U3"]
    assert response_writer.cited_by(proposal, {"cite": []}) == [] and response_writer.cited_by(proposal, {}) == []


class Taking:
    """A model that keeps what it is asked and answers a take-up as `data` says (or is not usable)."""

    def __init__(self, data, completion=Completion.COMPLETE, budget=1_000_000):
        self.data, self.completion, self.budget, self.seen = data, completion, budget, []

    def context_budget(self, tier):
        return self.budget

    def structured(self, prompt, schema, tier, **kwargs):
        self.seen.append((prompt, schema, tier, kwargs))
        return ModelResult(None, deepcopy(self.data), tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=self.completion)


def test_the_call_is_shown_only_the_items_asked_about_in_full_beside_everything_the_piece_was_written_from():
    ctx, record, sources = matter()
    held = {item["id"]: item for item in items_of(record, ctx, sources)}
    ids = [item["id"] for item in held.values() if item["kind"] in ("order", "pending")][:2]
    fact = next(item for item in held.values() if item["kind"] == "fact")
    model = Taking({"additions": [], "declined": []})
    wanted = [{"id": ids[0], "why": "It decides the matter."}, {"id": fact["id"], "why": "The client states it."}]
    returned = response_writer.take_up(model, ctx, record, sources, PROPOSAL, wanted, section=0)
    assert returned == {"additions": [], "declined": []}
    (prompt, schema, tier, kwargs), = model.seen
    assert prompt.system == response_writer.TAKE_UP_SYSTEM and prompt.operation == "core_response_take_up"
    assert prompt.effort == response_writer.SECOND_LOOK_EFFORT and schema == response_writer.TAKE_UP_SCHEMA
    assert tier == Tier.HARD and kwargs == {"max_tokens": response_writer.TAKE_UP_OUTPUT}
    payload = json.loads(prompt.user)
    asked = payload["to_take_up"]
    assert [entry["id"] for entry in asked] == [ids[0], fact["id"]] and ids[1] not in prompt.user.split('"to_take_up"')[1]
    assert asked[0]["why_the_review_says_it_matters"] == "It decides the matter." and asked[1]["why_the_review_says_it_matters"] == (
        "The client states it.")
    assert {"date", "kind", "what", "said_by", "cite", "papers_words"} <= set(asked[0]) and asked[0]["cited_by"] == []
    assert {"kind", "what", "certainty", "papers_words"} <= set(asked[1])
    assert [p["id"] for p in payload["your_paragraphs"]] == ["U1", "U2"] and payload["what_you_wrote"] == {"piece": "one dispute's section"}
    for key in ("original_context", "setting", "research", "held_passages"):
        assert key in payload, key
    assert 0 < prompt.cache_through < len(prompt.user), "what every call of the turn carries alike is marked for the cache"


def test_the_overview_is_taken_up_in_its_own_schema_and_an_unknown_item_is_not_asked_about():
    ctx, record, sources = matter()
    held = items_of(record, ctx, sources)
    model = Taking({"additions": [], "declined": []})
    response_writer.take_up(model, ctx, record, sources, {"units": [unit("summary", "S.", "ties")]},
                            [{"id": held[0]["id"], "why": "Why."}, {"id": "E99", "why": "Nowhere."}], section=response_writer.OVERVIEW,
                            sections={"sections": []})
    (prompt, schema, _, _), = model.seen
    payload = json.loads(prompt.user)
    assert schema == response_writer.OVERVIEW_TAKE_UP_SCHEMA and payload["what_you_wrote"] == {"piece": "the overview that opens the answer"}
    assert [entry["id"] for entry in payload["to_take_up"]] == [held[0]["id"]]


def test_a_call_with_nothing_to_ask_or_over_the_model_budget_or_unfinished_is_not_made_or_not_used():
    ctx, record, sources = matter()
    wanted = [{"id": items_of(record, ctx, sources)[0]["id"], "why": "Why."}]
    with pytest.raises(ValueError, match="items of the record that a piece passes over"):
        response_writer.take_up(Taking({}), ctx, record, sources, PROPOSAL, [], section=0)
    with pytest.raises(ValueError, match="sources differ"):
        response_writer.take_up(Taking({}), ctx, record, {}, PROPOSAL, wanted, section=0)
    with pytest.raises(ContextOverflow):
        response_writer.take_up(Taking({}, budget=1000), ctx, record, sources, PROPOSAL, wanted, section=0)
    with pytest.raises(ModelError, match="did not complete"):
        response_writer.take_up(Taking({"additions": [], "declined": []}, completion=Completion.LENGTH_LIMITED), ctx, record, sources,
                                PROPOSAL, wanted, section=0)
