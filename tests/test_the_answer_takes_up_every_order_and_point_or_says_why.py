"""The answer takes up every order, point and fact the record holds, or says why not (plan AN.28, stage 5; AN.29, D10; findings A1-A7,
A12, A13).

The writers were shown nearly two hundred timeline events and used fewer than twenty; an order that keeps a predecessor's name in the
records was called only "pending", a member of the client's family among an appeal's respondents went unsaid, and a review's finding
that something important was missing was a suggestion that lapsed. Now code lists every order, direction and proceeding still pending
in the papers' timeline, every point the papers read side by side show and every fact the understanding took from the papers; the
writer v14 and its overview take up each that bears on their part or say why not; the review v12 holds an item passed over in silence
- or mentioned without what the advice needs - a must-fix; and for the items it finds, one call shown only them (the take-up) gives
a paragraph for each or a reason for declining, which code admits as it admits any paragraph and the review judges again. What still
stays out is said beside the piece. The papers are synthetic.
"""
import json

import pytest

from nm.core_engine import (answer_sections, answer_sources, calculation, research, response_authorities, response_rendering,
                            response_review, response_writer, turn)
from nm.core_engine.calls import TurnCalls
from nm.core_engine.research import plan, retrieve
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage
from tests.test_core_research import Model, searcher
from tests.test_only_the_failing_piece_is_looked_at_again_and_blocked import (
    answered as answered_two,
    section_of,
)
from tests.test_the_chronology_of_each_document import SCRIPT
from tests.test_the_plan_records_the_chronology import Beside, bundle
from tests.test_the_plan_records_the_transfers import SOLD
from tests.test_the_writer_and_review_are_shown_copies_read_differently import quiet
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a

V14 = response_writer.REPAIRED_CONTRACT


def matter():
    ctx = bundle()
    record = retrieve(plan(Beside(SCRIPT, transfers=SOLD), ctx), searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def _result(data, tier):
    return ModelResult(None, data, tier, "synthetic", "fixture", Usage(1, 1, 0), 0, completion=Completion.COMPLETE)


def items_of(record, ctx, sources):
    offered = {tag: alias for alias, tag in answer_sources.aliases(sources).items()}
    return response_writer.coverage_items(record, offered, ctx)


def test_the_writer_v14_is_given_every_order_pending_proceeding_point_and_fact_to_take_up_or_say_why():
    ctx, record, sources = matter()
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=V14)
    prompt, payload = model.seen[0]
    coverage = payload["coverage"]
    events = [item for item in coverage if item["kind"] in ("order", "pending")]
    facts = [item for item in coverage if item["kind"] == "fact"]
    assert events and facts and {item["kind"] for item in coverage} <= {"order", "pending", "fact", "other", "client_appears",
                                                                         "against_client", "after_death", "after_time_limit",
                                                                         "further_subject"}
    # An event by its ID and kind: its date, what it is and the pages to cite are in papers_chronology beside it.
    assert all(set(item) == {"id", "kind"} for item in events)
    assert all(set(item) == {"id", "kind", "what", "certainty"} for item in facts), "a fact in brief, as the understanding numbered it"
    leading = [key for key in response_writer.SHARED_KEYS if key in payload]
    assert list(payload)[:len(leading)] == leading and leading[-1] == "coverage", "what every part's call carries alike leads"
    assert [item["id"] for item in events] == [event["id"] for event in payload["papers_chronology"]
                                               if event["kind"] in ("order", "pending") and event["located"]]
    earlier = Writer(quiet)
    response_writer.write_section(earlier, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert "coverage" not in earlier.seen[0][1], "the v13 writer is shown what it was"
    writer = " ".join(response_writer.SYSTEM_V14.split())
    for part in ("Where coverage is given, it lists every order, direction and proceeding still pending",
                 "(each by its ID in papers_chronology, which holds its date, what it is and cite)",
                 "every point the papers read side by side show",
                 "and every fact the understanding took from the advocate's messages and the papers, each with what it is",
                 "Take up each whose absence would change or weaken what your part tells the advocate, citing its pages",
                 "say in one limitation unit, with why, which such items you leave out", "Pass over none of those in silence",
                 "one that would only add detail need not be named",
                 "Where you mention a proceeding that is pending, say who brought it and what it seeks, as papers_chronology records",
                 "Set out the papers' events once", "the chronology across the disputes is the opening overview's",
                 "keep a part's dated events together, in date order"):
        assert part in writer, part
    overview = " ".join(response_writer.OVERVIEW_SYSTEM_V14.split())
    assert "each whose absence would change or weaken what the answer tells the advocate and that no section took up" in overview
    assert "repeat nothing a section already says" in overview
    assert "Where coverage is given" not in response_writer.SYSTEM_V13 + response_writer.OVERVIEW_SYSTEM_V13


class Reviewing:
    """A review v12 that reports as missing what `missing(payload)` gives, and keeps what it was shown."""

    def __init__(self, missing):
        self.missing, self.seen = missing, []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        self.seen.append(payload)
        return _result({"misleading": [], "could_be_better": [], "keep_shown": [], "missing": self.missing(payload)}, tier)


def test_the_review_v12_holds_an_item_passed_over_in_silence_a_must_fix_said_by_what_it_is_and_keeps_the_item():
    ctx, record, sources = matter()
    draft = response_writer.write_section(Writer(quiet), ctx, record, sources, index=0, contract=V14)
    fact = next(item for item in items_of(record, ctx, sources) if item["kind"] == "fact")
    reviewer = Reviewing(lambda payload: [{"id": payload["coverage"][0]["id"], "why": "It decides who holds the stock."},
                                          {"id": fact["id"], "why": "The client states it in their own paper."},
                                          {"id": "E99", "why": "Something."}])
    reviewed = response_review.review(reviewer, ctx, record, sources, draft, research.execution(record),
                                      authority_evidence=response_authorities.check(ctx, record, sources, draft),
                                      contract=response_review.WORDED_CONTRACT)
    offered = {tag: alias for alias, tag in answer_sources.aliases(sources).items()}
    item = response_writer._coverage_shown(record, offered, ctx)[0]
    assert reviewer.seen[0]["coverage"][0] == {"id": item["id"], "kind": item["kind"]}, "the review is shown it as the writer is"
    left, stated = reviewed["proposal"]["findings"]
    assert left["category"] == response_review.LEFT_OUT and left["unit_ids"] == [] and not reviewed["accepted"]
    said = f"{item['date']} {item['kind']}: {item['what']}"
    assert left["mismatch"] == f"{said} - It decides who holds the stock."
    assert (left["items"], left["said"], left["reason"]) == ([item["id"]], said, "It decides who holds the stock.")
    assert (stated["items"], stated["said"], stated["reason"]) == ([fact["id"]], fact["what"], "The client states it in their own paper.")
    assert "names no item of the coverage list: 'E99'" in [entry["why"] for entry in reviewed["proposal"]["set_aside"]]
    assert "give it in missing" in response_review.SYSTEM_V12 and "missing" not in response_review.SYSTEM_V11
    review = " ".join(response_review.SYSTEM_V12.split())
    assert "An item whose absence would change or weaken what the piece tells the advocate" in review
    assert "every fact the understanding took from the advocate's messages and the papers" in review
    assert "mentions only in passing, without what the advocate needs to act on it (of a proceeding, who brought it and what it seeks)" in review
    assert "Do not give an item that would only add detail." in review
    assert "or why it did not take up an item of coverage found left out" in review


class Covering:
    """Writes the one section from a script, reviews it as `missing(round, payload)` says, round by round, and takes up the items it
    is asked about as `taking(payload)` says."""

    def __init__(self, missing, taking=None):
        self.missing, self.taking, self.writes, self.reviews, self.take_ups, self.seen = missing, taking, [], 0, [], []

    def context_budget(self, tier):
        return 1_000_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        if prompt.operation == "core_response_writer":
            self.writes.append(payload)
            units = [{"kind": "summary", "text": "In short, the claim was allowed.", "uses": [], "place": "row_action"},
                     {"kind": "next_step", "text": "Check the records.", "uses": [], "place": "next_steps"}]
            return _result({"units": units, "checklist": [], "time_limit_ids": [], "by_when": None}, tier)
        if prompt.operation == "core_response_review":
            self.reviews += 1
            self.seen.append(payload)
            return _result({"misleading": [], "could_be_better": [], "keep_shown": [],
                            "missing": self.missing(self.reviews, payload)}, tier)
        if prompt.operation == "core_response_take_up":
            self.take_ups.append(payload)
            return _result(self.taking(payload), tier)
        raise AssertionError(prompt.operation)


def added(text, place="risks"):
    return {"kind": "limitation", "text": text, "uses": [], "place": place}


def taking_up(payload):
    """A writer that takes up every item it is asked about, in one paragraph."""
    asked = [item["id"] for item in payload["to_take_up"]]
    return {"additions": [{"items": asked, "paragraph": added("The two suits are pending before the District Court.")}], "declined": []}


def answered(model):
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
    return sections, elements


def last_of(payload):
    """The last event of the coverage list (the facts of the understanding follow the events and the points)."""
    return [item["id"] for item in payload["coverage"] if item["kind"] in ("order", "pending")][-1]


def test_the_items_a_piece_passes_over_are_taken_up_in_one_call_shown_only_them_and_the_paragraph_is_added():
    model = Covering(lambda round_, payload: ([{"id": last_of(payload), "why": "The suits are still pending."}] if round_ == 1 else []),
                     taking_up)
    sections, elements = answered(model)
    assert len(model.writes) == 1 and len(model.take_ups) == 1 and model.reviews == 2, "no rewrite of the whole: a take-up and a review"
    asked = model.take_ups[0]
    (item,) = asked["to_take_up"]
    assert item["id"] == last_of(model.seen[0]) and item["why_the_review_says_it_matters"] == "The suits are still pending."
    assert item["papers_words"] and item["cite"], "the papers' own words and the pages to cite"
    assert [paragraph["id"] for paragraph in asked["your_paragraphs"]] == ["U1", "U2"] and "original_context" in asked
    assert asked["what_you_wrote"] == {"piece": "one dispute's section"} or asked["what_you_wrote"] == {"piece": "the overview that opens the answer"}
    (section,) = sections
    assert section["fallback"] is None and section["trims"] == [] and section["reviewed"]["review"]["accepted"] is True
    texts = [unit["text"] for unit in section["reviewed"]["draft"]["units"]]
    assert texts == ["In short, the claim was allowed.", "Check the records.", "The two suits are pending before the District Court."]
    (look,) = section[answer_sections.LOOKS]
    assert [entry["id"] for entry in look["faults"]] == [item["id"]] and look["decisions"] == [{"item": item["id"], "action": "added",
                                                                                                 "unit": 3}]
    assert not [element for element in elements if element["kind"] == "NOTE"], "what was taken up is said nowhere as left out"


def test_every_item_the_review_finds_is_taken_up_in_the_one_call_and_a_piece_has_one_take_up_only():
    two = lambda round_, payload: [{"id": payload["coverage"][0]["id"], "why": "It is the order in issue."},  # noqa: E731
                                   {"id": last_of(payload), "why": "The suits are still pending."}]
    model = Covering(two, lambda payload: {"additions": [], "declined": []})
    sections, elements = answered(model)
    assert len(model.take_ups) == 1 and [item["id"] for item in model.take_ups[0]["to_take_up"]] == [
        model.seen[0]["coverage"][0]["id"], last_of(model.seen[0])]
    assert model.reviews == 1, "a take-up that gave nothing code could use is not reviewed again"
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert "does not take up 2 things your papers record that bear on it" in note["text"]
    assert "(1) " in note["text"] and "(2) " in note["text"] and "The suits are still pending." in note["text"]
    (section,) = sections
    (look,) = section[answer_sections.LOOKS]
    assert look["decisions"] == [] and section["fallback"] is None


def test_an_item_the_writer_declines_with_a_reason_goes_to_the_next_review_with_it_and_a_reason_that_holds_leaves_nothing_beside():
    declined = lambda payload: {"additions": [], "declined": [{"items": [payload["to_take_up"][0]["id"]],  # noqa: E731
                                                                "why": "The first paragraph already says it."}]}
    model = Covering(lambda round_, payload: ([{"id": last_of(payload), "why": "The suits are still pending."}]
                                              if "writer_notes" not in payload else []), declined)
    sections, elements = answered(model)
    assert model.reviews == 2 and len(model.writes) == 1
    (note,) = model.seen[1]["writer_notes"]
    assert note["why"] == "The first paragraph already says it." and "pending" in note["words"], "the item, as the review was told it"
    assert not [element for element in elements if element["kind"] == "NOTE"]
    (section,) = sections
    assert section["reviewed"]["writer_notes"] == [note] and section["reviewed"]["review"]["accepted"] is True


def test_a_reason_the_review_does_not_accept_leaves_the_item_said_beside_the_piece_and_it_is_not_taken_up_twice():
    stubborn = lambda round_, payload: [{"id": last_of(payload), "why": "The suits are still pending."}]  # noqa: E731
    declined = lambda payload: {"additions": [], "declined": [{"items": [payload["to_take_up"][0]["id"]],  # noqa: E731
                                                                "why": "It adds nothing."}]}
    model = Covering(stubborn, declined)
    sections, elements = answered(model)
    assert len(model.take_ups) == 1 and model.reviews == 2
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert "does not take up something your papers record that bears on it" in note["text"] and "The suits are still pending." in note["text"]
    (section,) = sections
    assert section["fallback"] is None and section["trims"] == [], "an item passed over never withholds a section"


def test_a_take_up_that_cannot_be_used_leaves_the_piece_as_reviewed_with_what_it_left_out_said_beside_it():
    def broken(payload):
        raise SchemaViolation("scripted failure")
    model = Covering(lambda round_, payload: [{"id": last_of(payload), "why": "The suits are still pending."}], broken)
    sections, elements = answered(model)
    assert len(model.take_ups) == 1 and model.reviews == 1
    (section,) = sections
    assert section["fallback"] is None and section["reviewed"]["review"]["accepted"] is False
    assert [entry["step"] for entry in section[answer_sections.KEPT]] == ["writing"], "what code refused is kept as evidence"
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert "The suits are still pending." in note["text"]


def test_a_paragraph_the_take_up_adds_is_admitted_like_any_and_one_code_refuses_is_looked_at_again_then_left_out_alone():
    unknown = lambda payload: {"additions": [{"items": [payload["to_take_up"][0]["id"]],  # noqa: E731
                                              "paragraph": {"kind": "limitation", "text": "The suits are pending.", "place": "risks",
                                                            "uses": [{"source_kind": "document", "source_id": "ZZ9",
                                                                      "link_words": "suits are pending"}]}}], "declined": []}
    model = Covering(lambda round_, payload: ([{"id": last_of(payload), "why": "The suits are still pending."}] if round_ == 1 else []),
                     unknown)
    sections, elements = answered(model)
    (section,) = sections
    take, first, second = section[answer_sections.LOOKS]
    assert take["decisions"][0]["action"] == "added" and first["faults"][0]["position"] == second["faults"][0]["position"] == 3
    assert first["faults"][0]["kind"] == "check" and "not in the owned answer catalogue" in first["faults"][0]["why"]
    assert section["fallback"] is None and section["trims"] == [], "what was added is left out alone; the piece stands"
    assert [unit["text"] for unit in section["reviewed"]["draft"]["units"]] == ["In short, the claim was allowed.", "Check the records."]
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert note["text"].startswith("Left out of this answer: 1 paragraph")


def test_a_paragraph_that_is_a_rows_line_is_not_what_a_take_up_adds():
    row = lambda payload: {"additions": [{"items": [payload["to_take_up"][0]["id"]],  # noqa: E731
                                          "paragraph": {"kind": "summary", "text": "Another line.", "uses": [], "place": "row_action"}}],
                           "declined": []}
    model = Covering(lambda round_, payload: [{"id": last_of(payload), "why": "The suits are still pending."}], row)
    sections, _ = answered(model)
    (section,) = sections
    (look,) = section[answer_sections.LOOKS]
    assert look["decisions"] == [] and look["set_aside"] == [{"where": "addition 1", "why": "a paragraph placed 'row_action' is not one a take-up adds"}]


class Faulted(Covering):
    """As Covering, but the first draft also holds a statement the review finds misleading."""

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        if prompt.operation == "core_response_writer" and not self.writes:
            self.writes.append(payload)
            units = [{"kind": "summary", "text": "In short, a FAULT claim here.", "uses": [], "place": "row_action"},
                     {"kind": "next_step", "text": "Check the records.", "uses": [], "place": "next_steps"}]
            return _result({"units": units, "checklist": [], "time_limit_ids": [], "by_when": None}, tier)
        if prompt.operation == "core_response_review":
            self.reviews += 1
            self.seen.append(payload)
            misleading = [{"kind": "unsupported", "where": [unit["id"]], "evidence": [], "why": "Not borne out.",
                           "words": ["In short, a FAULT claim here."]}
                          for unit in payload["complete_draft_proposal"]["units"] if "FAULT" in unit["text"]]
            return _result({"misleading": misleading, "could_be_better": [], "keep_shown": [],
                            "missing": self.missing(self.reviews, payload)}, tier)
        return super().structured(prompt, schema, tier, **kwargs)


def test_the_take_up_comes_before_any_second_look_and_has_an_allowance_of_its_own():
    # The second paid replay: two second looks spent the section's allowance, and eleven items stayed out.
    model = Faulted(lambda round_, payload: ([{"id": payload["coverage"][0]["id"], "why": "It is the order in issue."}]
                                             if round_ == 1 else []), taking_up)
    sections, elements = answered(model)
    assert len(model.take_ups) == 1 and len(model.writes) == 2, "the take-up, then the second look at the faulty paragraph"
    (section,) = sections
    first, second = section[answer_sections.LOOKS]
    assert [entry["id"] for entry in first["faults"]] == [model.take_ups[0]["to_take_up"][0]["id"]], "the take-up comes first"
    assert first["decisions"][0]["action"] == "added" and second["faults"][0]["kind"] == "review"
    assert section["fallback"] is None and section["reviewed"]["review"]["accepted"] is True
    assert not [element for element in elements if element["kind"] == "NOTE"]


def test_the_take_up_and_its_looks_are_bounded_by_the_pieces_allowance():
    assert answer_sections.TAKE_UPS == 1 and answer_sections.SECTION_ALLOWANCE == 2
    assert not hasattr(answer_sections, "COVERAGE_REWRITES") and not hasattr(answer_sections, "COVERAGE_PURPOSE")
    saved = {answer_sections.LOOKS: [{"faults": [{"id": "E1"}], "returned": {}, "decisions": [], "set_aside": []}] * 3}
    answer_sections._looks_valid(saved)
    saved[answer_sections.LOOKS].append(saved[answer_sections.LOOKS][0])
    with pytest.raises(ValueError, match="second looks"):
        answer_sections._looks_valid(saved)


def test_the_take_up_prompt_and_schema_ask_for_a_paragraph_or_a_reason_for_every_item():
    system = " ".join(response_writer.TAKE_UP_SYSTEM.split())
    for part in ("You wrote a piece of NM's answer", "to_take_up", "cited_by", "Decide for each item", "add it: write a paragraph that takes it up",
                 "resting on the papers' own words exactly as they put it, citing its pages", "for a proceeding, say who brought it and what it seeks",
                 "decline it, in plain words: it is already taken up (say by which paragraph), or it does not bear on this piece",
                 "Work in a loop before you return", "Every item in to_take_up is in one of them",
                 "claim nothing NM saved, filed or did"):
        assert part in system, part
    schema = response_writer.TAKE_UP_SCHEMA
    assert set(schema["properties"]) == {"additions", "declined"}
    assert set(schema["properties"]["additions"]["items"]["properties"]) == {"items", "paragraph"}
    assert set(schema["properties"]["declined"]["items"]["properties"]) == {"items", "why"}


class Opening:
    """A two-dispute answer: sections that need nothing, and an overview the review finds passes over a fact - taken up, declined or
    neither as `taking(payload)` says."""

    knows_second_look = True

    def __init__(self, taking):
        self.taking, self.take_ups, self.reviews, self.writes = taking, [], [], []

    def context_budget(self, tier):
        return 100_000

    def structured(self, prompt, schema, tier, **kwargs):
        payload = json.loads(prompt.user)
        dispute = ((payload.get("this_part") or {}).get("dispute") or {}).get("id")
        if prompt.operation == "core_response_writer":
            return _result({"units": section_of(dispute, "Nothing more is known."), "checklist": [], "time_limit_ids": [],
                            "by_when": None}, tier)
        if prompt.operation == "core_response_overview":
            self.writes.append(payload)
            return _result({"units": [{"kind": "next_step", "text": "Start with the first dispute.", "uses": []}]}, tier)
        if prompt.operation == "core_response_review":
            overview = payload["what_you_review"]["piece"].startswith("the overview")
            self.reviews.append(payload)
            missing = ([{"id": payload["coverage"][0]["id"], "why": "The client states it in their own paper."}]
                       if overview and "writer_notes" not in payload and len(payload["complete_draft_proposal"]["units"]) == 1 else [])
            return _result({"misleading": [], "could_be_better": [], "keep_shown": [], "missing": missing}, tier)
        if prompt.operation == "core_response_cross_check":
            return _result({"conflicts": []}, tier)
        if prompt.operation == "core_response_take_up":
            self.take_ups.append(payload)
            return _result(self.taking(payload), tier)
        raise AssertionError(prompt.operation)


def test_the_overview_is_taken_up_like_a_section_and_what_it_adds_is_placed_for_it_by_code():
    model = Opening(lambda payload: {"additions": [{"items": [payload["to_take_up"][0]["id"]], "paragraph": {
        "kind": "limitation", "text": "The client states a fact that no section takes up.", "uses": []}}], "declined": []})
    ctx, elements, activity = answered_two(model)
    (asked,) = model.take_ups
    assert asked["what_you_wrote"] == {"piece": "the overview that opens the answer"}
    assert [entry["id"] for entry in asked["to_take_up"]] == [model.reviews[-1]["coverage"][0]["id"]] and "sections_shown" in asked
    overview = activity["overview"]
    (look,) = overview[answer_sections.LOOKS]
    assert look["decisions"] == [{"item": asked["to_take_up"][0]["id"], "action": "added", "unit": 2}]
    units = overview["reviewed"]["draft"]["units"]
    assert [unit["kind"] for unit in units] == ["next_step", "limitation"] and units[-1]["text"].startswith("The client states a fact")
    assert overview["fallback"] is None and overview["reviewed"]["review"]["accepted"] is True
    assert not [element for element in elements if element["kind"] == "NOTE"]
    assert all(not section[answer_sections.LOOKS] for section in activity["sections"]), "the sections needed nothing"


def test_an_overview_paragraph_of_a_kind_the_overview_does_not_add_is_set_aside_and_the_fact_is_said_beside_it():
    model = Opening(lambda payload: {"additions": [{"items": [payload["to_take_up"][0]["id"]], "paragraph": {
        "kind": "next_step", "text": "Do something else first.", "uses": []}}], "declined": []})
    ctx, elements, activity = answered_two(model)
    overview = activity["overview"]
    (look,) = overview[answer_sections.LOOKS]
    assert look["decisions"] == [] and look["set_aside"] == [
        {"where": "addition 1", "why": "a paragraph of kind 'next_step' is not one the overview adds"}]
    assert len(overview["reviewed"]["draft"]["units"]) == 1 and overview["fallback"] is None
