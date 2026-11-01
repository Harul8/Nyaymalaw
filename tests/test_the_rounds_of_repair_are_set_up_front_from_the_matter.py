"""The rounds of repair a piece of the answer may make are set up front from the matter, and stop when they change nothing (plan
AN.33, D21).

The owner, 1 Nov 2026: "let's put a meaningful limit on this up front, this can may be dynamic based on documents length, complexity
or disputes identified so that we are certain of costs", and "we should ensure there are no perpetual loops and based on the matter
complexity put a limit of some sort". From research v14 every point the papers' reading set out is on the coverage list, so a piece
may have many to account for. Before any piece is written, code sets how many rounds of repair - a take-up of what the review found
passed over and a second look at what it found at fault, then one review - each piece may make: one, and one more for every ten items
beyond the first ten of each piece's share of the list, four at most, and no more than let the pieces' allowances together fit within
the turn's durable allowance of corrections. One round is the allowance before. A take-up asks only about what no earlier one of the
piece asked, so a review that finds nothing new ends the rounds. A saved answer is checked against the allowance its own record gives.
The papers are synthetic.
"""
import json
from copy import deepcopy

import pytest

from nm.core_engine import answer_sections, calculation, research, response_rendering, response_writer, turn
from nm.core_engine.calls import ALLOWANCE, SECTION_ALLOWANCE, TurnCalls
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import V14, Covering, _result, added, matter

pytestmark = pytest.mark.class_a

ONE = [{"dispute_id": None, "work_ids": None}]


def with_items(record, context, total):
    """The record with facts of the understanding added until its coverage list holds `total` items."""
    record = deepcopy(record)
    facts = record["plan"]["proposal"]["understanding"]["facts"]
    while len(response_writer.coverage_items(record, {}, context)) < total:
        number = len(facts) + 1
        facts.append({"id": f"F{number}", "fact": f"The advocate reports fact {number}.", "advocate_words": "",
                      "certainty": "reported"})
    assert len(response_writer.coverage_items(record, {}, context)) == total
    return record


def test_the_rounds_are_one_and_one_more_for_every_ten_items_beyond_ten_of_each_pieces_share_four_at_most():
    ctx, record, sources = matter()
    assert (answer_sections.ROUND_ITEMS, answer_sections.MAX_ROUNDS, answer_sections.TAKE_UPS, SECTION_ALLOWANCE) == (10, 4, 1, 2)
    for total, allowed in ((7, 1), (10, 1), (11, 2), (20, 2), (21, 3), (31, 4), (240, 4)):
        assert answer_sections.rounds(with_items(record, ctx, total), ONE, ctx) == allowed, total
    three = ONE * 3
    assert answer_sections.rounds(with_items(record, ctx, 31), three, ctx) == 2, "31 items among three pieces: 11 each"
    assert answer_sections.rounds(with_items(record, ctx, 90), three, ctx) == 3
    earlier = {**with_items(record, ctx, 240), "contract": research.WHOLE_FILE_CONTRACT}
    assert answer_sections.rounds(earlier, ONE, ctx) == 1, "a record before v14 keeps the one round its answers were made with"


def test_one_round_is_the_allowance_before_and_the_pieces_allowances_fit_within_the_turns_durable_allowance():
    assert answer_sections.allowances(1) == (SECTION_ALLOWANCE, answer_sections.TAKE_UPS) == (2, 1)
    assert answer_sections.allowances(4) == (5, 4), "each further round a second look and a take-up"
    ctx, record, sources = matter()
    many = with_items(record, ctx, 400)
    found = {pieces: answer_sections.rounds(many, ONE * pieces, ctx) for pieces in (1, 3, 4, 5, 6, 7, 8, 16)}
    assert found == {1: 4, 3: 4, 4: 3, 5: 2, 6: 2, 7: 1, 8: 1, 16: 1}
    for pieces, allowed in found.items():
        if allowed > 1:
            assert pieces * sum(answer_sections.allowances(allowed)) <= ALLOWANCE, pieces


def answer(model):
    """The one-section matter answered through the live loop (writer v14, review v12), rendered and replayed as a turn saves it."""
    ctx, record, sources = matter()
    calls, worked, execution = TurnCalls(model), calculation.skipped(), turn.execution_record(record)
    sections, crossed, overview = answer_sections.answer(calls, ctx, record, sources, interpretation={"units": []},
                                                         execution=execution, worked=worked, contract=V14)
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=crossed, overview=overview,
                                                  time_limits=worked, contract=response_rendering.REPAIRED_CONTRACT)
    activity = {"contract": turn.CONTRACT, "interpretation": {"units": []}, "research": record, "sources": sources,
                "execution": execution, "calculation": worked, "rendering_contract": response_rendering.REPAIRED_CONTRACT,
                "sections": sections, "cross_check": crossed, "overview": overview}
    assert turn.validate_activity(activity, ctx, elements) == activity, "the turn replays as saved"
    return ctx, sections, elements, activity


def adding(payload):
    """A writer that takes up every item it is asked about, in one paragraph of its own each time."""
    asked = [item["id"] for item in payload["to_take_up"]]
    return {"additions": [{"items": asked, "paragraph": added(f"The papers record a further matter, as item {len(asked)} of the list.")}],
            "declined": []}


def test_a_piece_whose_reviews_find_new_items_takes_them_up_round_by_round_until_its_rounds_are_spent(monkeypatch):
    monkeypatch.setattr(answer_sections, "ROUND_ITEMS", 3)  # seven items on one piece: three rounds
    ctx, record, sources = matter()
    assert answer_sections.rounds(record, response_writer.parts(record), ctx) == 3
    texts = iter(f"The papers record further matter {n}." for n in range(1, 9))
    model = Covering(lambda round_, payload: [{"id": payload["coverage"][round_ - 1]["id"], "why": f"Reason {round_}."}],
                     lambda payload: {"additions": [{"items": [item["id"] for item in payload["to_take_up"]],
                                                     "paragraph": added(next(texts))}], "declined": []})
    ctx, sections, elements, activity = answer(model)
    coverage = [item["id"] for item in model.seen[0]["coverage"]]
    assert [[item["id"] for item in asked["to_take_up"]] for asked in model.take_ups] == [[identity] for identity in coverage[:3]]
    assert model.reviews == 4 and len(model.writes) == 1, "three take-ups, each reviewed; the fourth item found is not taken up"
    (section,) = sections
    assert len(section[answer_sections.LOOKS]) == 3 and section["fallback"] is None
    assert [unit["text"] for unit in section["reviewed"]["draft"]["units"]][-3:] == [
        "The papers record further matter 1.", "The papers record further matter 2.", "The papers record further matter 3."]
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert "Reason 4." in note["text"] and "Reason 3." not in note["text"], "what the rounds could not reach is said beside"


def test_a_take_up_asks_only_what_no_earlier_one_asked_so_a_review_that_finds_nothing_new_ends_the_rounds(monkeypatch):
    monkeypatch.setattr(answer_sections, "ROUND_ITEMS", 3)

    def found(round_, payload):
        first, second = (item["id"] for item in payload["coverage"][:2])
        return [{"id": first, "why": "It is the order in issue."}] + (
            [{"id": second, "why": "It decides who holds the stock."}] if round_ > 1 else [])
    model = Covering(found, lambda payload: {"additions": [], "declined": [
        {"items": [item["id"] for item in payload["to_take_up"]], "why": "It adds nothing."}]})
    ctx, sections, elements, activity = answer(model)
    first, second = (item["id"] for item in model.seen[0]["coverage"][:2])
    assert [[item["id"] for item in asked["to_take_up"]] for asked in model.take_ups] == [[first], [second]]
    assert model.reviews == 3, "the third review found nothing new: no take-up, and the rounds end with one of three unused"
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert "does not take up 2 things your papers record" in note["text"]


class Mending(Covering):
    """As Covering, and every review finds the summary misleading; each second look writes it again, still misleading."""

    knows_second_look = True

    def __init__(self, missing, taking=None):
        super().__init__(missing, taking)
        self.looks = []

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        if prompt.operation == "core_response_repair":
            self.looks.append(payload)
            return _result({"repairs": [{"paragraph": entry["paragraph"], "action": "rewrite", "why": "Written again.",
                                         "page_words": None, "question": None,
                                         "rewritten": {"kind": "summary", "text": f"In short, the claim was allowed ({len(self.looks)}).",
                                                       "uses": [], "place": "row_action"}}
                                        for entry in payload["to_check"]]}, tier)
        result = super().structured(prompt, schema, tier, **kwargs)
        if prompt.operation == "core_response_review":
            result.data["misleading"] = [{"kind": "unsupported", "where": [unit["id"]], "evidence": [], "why": "Not borne out.",
                                          "words": [unit["text"]]}
                                         for unit in payload["complete_draft_proposal"]["units"] if unit["text"].startswith("In short")]
        return result


def test_each_further_round_is_also_a_further_second_look_and_a_saved_answer_is_checked_against_its_own_records_allowance(monkeypatch):
    plain = Mending(lambda round_, payload: [])
    answer(plain)
    assert len(plain.looks) == SECTION_ALLOWANCE, "one round: the second looks there were before"
    monkeypatch.setattr(answer_sections, "ROUND_ITEMS", 3)  # three rounds: four second looks of its own
    model = Mending(lambda round_, payload: [])
    ctx, sections, elements, activity = answer(model)
    (section,) = sections
    assert len(model.looks) == 4 and len(section[answer_sections.LOOKS]) == 4 and not model.take_ups
    assert all(look["faults"][0]["kind"] == "review" for look in section[answer_sections.LOOKS])
    assert [unit["text"] for unit in section["trims"][-1]["draft"]["units"]] == ["Check the records."], "then what still fails goes"
    monkeypatch.setattr(answer_sections, "ROUND_ITEMS", 10)  # the same record now allows one round: three looks in all
    with pytest.raises(ValueError, match="second looks"):
        turn.validate_activity(activity, ctx, elements)
