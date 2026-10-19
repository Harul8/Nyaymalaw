"""A held Act India Code does not list as in force (owner decision P21, 19 Oct 2026): the Act
store marks each of its passages, and the mark travels with the passage to the provision
pick, the writer, the independent review, the page, the reading pane and the research note;
the saved answer replays with it. Scripted fixtures exercise where the mark goes; they do
not show that a real pick, writer or reviewer heeds it."""
import json

import pytest

from nm.core_engine import (answer_sources, calculation, research, research_note, response_authorities,
                            response_rendering, response_review, response_writer, turn)
from nm.core_engine.retrieval import in_force
from tests.test_core_linked_words import LinkedModel
from tests.test_core_research import Model as ResearchModel, proposal
from tests.test_core_response_review import Model as ReviewModel, positive, request
from tests.test_core_response_writer import TwoDisputeLibrary
from tests.test_core_understanding import context

pytestmark = pytest.mark.class_a

MARK = "not in force according to India Code (checked 19 Oct 2026)"


def researched():
    """Two disputes researched in a library whose first provision is of an Act India Code
    does not list as in force."""
    ctx = context("Find the applicable law.")
    library = TwoDisputeLibrary.searcher()
    library.collections["provision"].rows[0]["standing"] = MARK
    library.collections["judgment"].rows[0]["standing"] = "a judgment's own field"
    model = ResearchModel()
    record = research.retrieve(research.accept(proposal(1, 2), ctx), library, ctx, model=model)
    return ctx, model, record, answer_sources.build(ctx, record)


def answered():
    ctx, _, record, sources = researched()
    writer = LinkedModel(sources)
    draft = response_writer.write(writer, ctx, record, sources)
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    reviewer = ReviewModel(positive(draft, requests=[request(ctx, draft)]))
    review = response_review.review(reviewer, ctx, record, sources, draft, execution,
                                    authority_evidence=authorities)
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities)
    activity = {"contract": turn.CONTRACT, "interpretation": {"units": []}, "research": record,
                "sources": sources, "draft": draft, "review": review, "execution": execution,
                "rendering_contract": response_rendering.CONTRACT, "authority_evidence": authorities,
                "calculation": calculation.skipped(), "release": None}
    return ctx, sources, writer, reviewer, elements, activity


def test_only_the_stores_own_words_are_a_mark():
    assert in_force({"standing": MARK}) == MARK
    assert [in_force(row) for row in ({}, {"standing": " "}, {"standing": None}, {"standing": 1}, None)] == [None] * 5


def test_the_pick_is_shown_which_provisions_are_of_an_act_india_code_does_not_list():
    ctx, model, record, _ = researched()
    shown = [prompt.user for prompt in model.calls if prompt.operation == "core_research_pick"]
    assert shown, "the provision pick ran"
    lines = [line for line in shown[0].splitlines() if line.startswith("  Q")]
    marked = [line for line in lines if MARK in line]
    assert marked and len(marked) < len(lines)
    assert all(f", section {line.split(', section ')[1].split(' [')[0]} [{MARK}]: " in line for line in marked)
    assert "marked not in force" in research.PICK
    assert research.validate(record, record["plan"], ctx) == record


def test_the_catalogue_and_every_model_view_of_it_carry_the_mark_of_a_marked_provision_only():
    _, _, record, sources = researched()
    marked = [row for row in sources.values() if "in_force" in row]
    assert marked and {row["kind"] for row in marked} == {"provision"}
    assert {row["in_force"] for row in marked} == {MARK}
    rows = [candidate["source"] for search in record["searches"].values() for candidate in search["candidates"]
            if candidate["kind"] == "provision"]
    assert {row["full_text"] for row in rows if row.get("standing") == MARK} == {row["text"] for row in marked}
    for shown in (answer_sources.presentation(sources),
                  answer_sources.presentation(sources, aliased=True, compact=True)):
        passages = [passage for passage in shown["passages"] if "in_force" in passage]
        assert len(passages) == len(marked) and {passage["in_force"] for passage in passages} == {MARK}


def test_the_writer_and_the_review_see_the_mark_and_are_told_what_it_means():
    _, _, writer, reviewer, _, _ = answered()
    for prompt in (response_writer.SYSTEM, response_review.SYSTEM):
        said = " ".join(prompt.split())
        assert "A held passage whose in_force says it is not in force" in said and "current law" in said
    seen = [passage for payload in writer.seen for passage in payload["held_passages"]["passages"]]
    assert {passage.get("in_force") for passage in seen if passage["kind"] == "provision"} >= {MARK}
    legal = json.loads(reviewer.calls[0][0].user)["legal_sources"]["passages"]
    assert {passage.get("in_force") for passage in legal} == {MARK, None}


def test_the_page_shows_the_mark_with_the_passage_and_the_saved_answer_replays_with_it():
    ctx, sources, _, _, elements, activity = answered()
    shown = [source for element in elements for source in element.get("sources") or []]
    marked = [source for source in shown if "in_force" in source]
    assert marked, "the writer's first passage of each part is the marked provision"
    assert all(source["in_force"] == MARK == sources[source["id"]]["in_force"] for source in marked)
    assert all("in_force" not in sources[source["id"]] for source in shown if "in_force" not in source)
    assert turn.validate_activity(activity, ctx, elements) == activity
    changed = json.loads(json.dumps(elements))
    next(source for element in changed for source in element.get("sources") or [] if "in_force" in source).pop("in_force")
    with pytest.raises(ValueError, match="admitted rendering"):
        turn.validate_activity(activity, ctx, changed)


def test_the_research_note_describes_the_provision_as_not_in_force():
    _, _, _, _, elements, _ = answered()
    note = research_note.note({"turn_id": "t2", "message": "Find the applicable law.", "documents": [],
                               "response": {"elements": elements, "at": "2026-10-19T10:00:00+05:30"}},
                              prepared_for="A. Advocate")
    described = {source["title"] + " " + source["locator"]: source["described"] for source in note["sources"]}
    assert f"Statute, {MARK}" in described.values()
    assert any(source["heading"].endswith(f"— Statute, {MARK}") for source in note["sources"])
