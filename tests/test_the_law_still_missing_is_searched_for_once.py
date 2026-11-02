"""The law still missing for a dispute is named and searched for once (plan AN.35, D30 A3; research v16; piece 35d).

The owner, 2 Nov 2026, agreeing the round and setting its bounds: "we are only retrieving the relevant passages and reading only the
relevant judgments ... We don't want to get into a spiral where we retrieve umpteen number of passages which are not at all relevant
and then keep on reading all of them." After a dispute's two picks one call is shown each question with what was chosen for it and
what the picks said was missing, and names, for a question whose governing law is still missing, the sections to read by their
number and the phrases to search; code searches once for those, the picks choose among only what was not already offered for that
question, and the judgments chosen are read with the rest, each once. A question with nothing missing searches nothing; there is no
second round. The matter and its law are invented.
"""
import re
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, reasoning, research
from nm.core_engine.retrieval import HybridSearcher
from tests.test_core_research import Model, operations, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a

FURTHER_WORDS = "when time runs for the suit"


def library():
    """A first search finds sections 0 and 1 and judgment 0; a search for when time runs finds sections 2 and 3 and judgment 2."""
    provisions = Collection()
    provisions.rows = {p: {"chunk_id": f"s{p}", "full_text": f"Section {p}\nProvision {p} text.", "act_id": "act",
                           "act_name": "Act", "section_number": str(p)} for p in range(4)}
    provisions.lexical = provisions.semantic = lambda query, depth: [2, 3] if "time runs" in query else [0, 1]
    provisions.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held = Collection("judgment")
    held.rows = {p: {"chunk_id": f"j{p}", "full_text": f"Paragraph {p}:\n the court holds rule {p}.", "case_id": f"case{p}",
                     "case_name": f"Case {p} v State", "paragraph_num": str(p + 1), "court": "Supreme Court of India",
                     "year": "2001", "cited_by_count": 10, "paragraph_type": "reasoning"} for p in range(4)}
    held.lexical = held.semantic = lambda query, depth: [2] if "time runs" in query else [0]
    held.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    searcher = HybridSearcher({"provision": provisions, "judgment": held})
    asked, many = [], searcher.search_many
    searcher.search_many = lambda searches, **kwargs: asked.append(searches) or many(searches, **kwargs)
    return searcher, asked


def missing_time(user):
    label = re.search(r"^(Q\d+): ", user, re.M).group(1)
    return {"questions": [{"question_id": label, "missing": "When time runs for the suit.", "sections": [],
                           "phrases": [FURTHER_WORDS], "cited": []}]}


def researched(model):
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 1), ctx)
    searcher, asked = library()
    return ctx, plan, research.retrieve(plan, searcher, ctx, model=model), asked


def test_the_law_still_missing_is_searched_for_once_and_only_what_is_new_is_chosen_from():
    model = Model(further=missing_time)
    ctx, plan, record, asked = researched(model)
    assert record["contract"] == research.CONTRACT == "core_research_v16"
    assert operations(model).count("core_research_further") == 1, "once for the dispute"
    assert len(asked) == 2, "the first searches, then the one further search"
    further, work_id = record["further"]["D1"], plan["work"][0]["id"]
    assert further["state"] == "evaluated" and set(further["searches"]) == {work_id}
    assert [query["text"] for query in further["searches"][work_id]["queries"]] == [FURTHER_WORDS]
    # The picks were offered only what was new to the question.
    before = {candidate["id"] for candidate in record["searches"][work_id]["candidates"]}
    fresh = dict(research.further_searches(record))[work_id]
    assert fresh["candidates"] and not {candidate["id"] for candidate in fresh["candidates"]} & before
    shown = next(prompt.user for prompt in model.calls if prompt.operation == "core_research_pick"
                 and "Provision 2" in prompt.user)
    assert "Provision 0" not in shown, "what the first pick saw is not offered again"
    # What they chose joins what the dispute reads; each judgment is read once.
    assert set(further["picks"]["provision"]["chosen"][work_id]) <= set(research.chosen(record)[work_id])
    assert [entry["case_id"] for entry in record["judgments"]["D1"]] == ["case0"]
    assert [entry["case_id"] for entry in further["judgments"]] == ["case2"]
    assert [entry["case_id"] for entry in research.judgments_read(record)["D1"]] == ["case0", "case2"]
    sources = answer_sources.build(ctx, record)
    assert any(row["kind"] == "provision" and "Provision 2 text." in row["text"] for row in sources.values())
    # Saved and replayed exactly; a changed answer of the further search is refused.
    assert research.validate(record, plan, ctx) == record
    changed = deepcopy(record)
    changed["further"]["D1"]["proposal"]["questions"][0]["phrases"] = ["another way in"]
    with pytest.raises(ValueError):
        research.validate(changed, plan, ctx)
    part = research.part_of(record, "D1")
    assert part["further"] == {"D1": further}


def test_a_dispute_whose_law_is_there_searches_nothing_further():
    ctx, plan, record, asked = researched(Model())
    further = record["further"]["D1"]
    assert further["state"] == "evaluated" and further["searches"] == {} and further["judgments"] == []
    assert {kind: pick["state"] for kind, pick in further["picks"].items()} == {"provision": "not_needed",
                                                                                "judgment": "not_needed"}
    assert len(asked) == 1 and research.validate(record, plan, ctx) == record


def test_a_further_search_that_cannot_be_made_is_said_and_the_rest_stands():
    model = Model(fail={"core_research_further"})
    ctx, plan, record, asked = researched(model)
    further = record["further"]["D1"]
    assert (further["state"], further["reason"], further["searches"]) == ("unavailable", "SchemaViolation", {})
    assert record["picks"]["D1"]["state"] == "evaluated" and len(asked) == 1
    assert research.validate(record, plan, ctx) == record


def test_the_further_search_is_asked_for_in_plain_words_and_each_section_it_names_is_read_by_its_number():
    words = " ".join(research.FURTHER.split())
    for part in ("Purpose:", "Outcome:", "Work in a loop", "This is the one further search for the dispute",
                 "nothing is searched again", "ask only for law the question needs"):
        assert part in words, part
    assert reasoning.STEPS["further"] == ("medium", False)
    assert research.FURTHER_LAW == (research.CONTRACT,) and research.NAMED_CONTRACT in research.NAMED_LAW
    assert research.NAMED_CONTRACT not in research.FURTHER_LAW and research.NAMED_CONTRACT in research.EVERY_CHOSEN
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 1), ctx)
    work_id = plan["work"][0]["id"]
    asked = {"questions": [
        {"question_id": "Q1", "missing": "The limitation.", "phrases": [],
         "sections": [{"act": "Imagined Relief Act, 1907", "section": "Sections 3 and 5"}]},
        {"question_id": "Q1", "missing": "Asked twice.", "phrases": ["kept once"], "sections": []},
        {"question_id": "Q9", "missing": "No such question.", "phrases": ["never searched"], "sections": []}]}
    wanted = research._further_wanted(asked, plan, {work_id: "Q1"})
    work, = wanted.values()
    assert work["named"] == [{"act": "Imagined Relief Act, 1907", "section": "3"},
                             {"act": "Imagined Relief Act, 1907", "section": "5"}]
    assert [enquiry["text"] for enquiry in work["enquiries"]] == ["The limitation."], "named sections are searched with what is missing"
    assert research._further_wanted({"questions": [{"question_id": "Q1", "missing": "", "phrases": [], "sections": []}]},
                                    plan, {work_id: "Q1"}) == {}
