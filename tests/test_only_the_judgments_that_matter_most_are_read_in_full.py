"""Only the judgments that matter most are read in full; every other one chosen stands by its passages (plan AN.36, D34; research
v17; pieces 36a-36c).

The owner, 2 Nov 2026, after AN.35's runs found a dispute's section cost about $0.50: "reading 35 judgments is way too much ... At
the same time, we should be able to look at all the relevant judgments ... Let the model read only the retrieved passages, and then
let the model decide which of those passages are relevant, and let the model decide those top 2, 3, 4, or 5 judgments which are
most relevant, and then the model can read the full judgment of only those". Agreed (D34): at most five judgments a dispute are
read in full, the model naming them; every other judgment chosen stands by the paragraphs chosen of it, each with the paragraph
either side; each label around the held passages is said once; the second looks and the take-ups are shown only the law the
section relies on. The judgments are invented.
"""
from copy import deepcopy

import pytest

from nm.core_engine import answer_sources, research, response_writer
from nm.core_engine.retrieval import HybridSearcher
from tests.test_core_research import Model, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a

CASES = ("first case", "second case", "third case", "fourth case")


def library():
    """Four judgments of three paragraphs each; a search finds the middle paragraph of each."""
    provisions = Collection()
    provisions.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held = Collection("judgment")
    held.rows = {3 * n + k: {"chunk_id": f"j{n}{k}", "full_text": f"Paragraph {k} of {case}: the court holds rule {n}.",
                             "case_id": case, "case_name": case.title(), "paragraph_num": str(k + 1),
                             "court": "Supreme Court of India", "year": "1996", "cited_by_count": 10, "paragraph_type": "reasoning"}
                 for n, case in enumerate(CASES) for k in range(3)}
    held.lexical = held.semantic = lambda query, depth: [1, 4, 7, 10]
    held.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held.judgment_paragraphs = lambda case_id: [(p, deepcopy(row)) for p, row in held.rows.items() if row["case_id"] == case_id]
    held.context = lambda position, source: {"scope": "selected_indexed_segment", "bounded": False, "unread_positions": [],
                                             "segments": [{"position": p, "row": deepcopy(held.rows[p])}
                                                          for p in (position - 1, position, position + 1) if p in held.rows]}
    return HybridSearcher({"provision": provisions, "judgment": held})


def researched(model):
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 1), ctx)
    return ctx, plan, research.retrieve(plan, library(), ctx, model=model)


def test_the_judgment_pick_names_the_few_to_read_in_full_and_says_the_rest_stand_by_their_passages():
    words = " ".join(research.JUDGMENT_PICK_V17.split())
    assert "name in read_in_full the judgments a lawyer would read in full" in words and "the two to five" in words
    assert "every other judgment stands by the paragraphs you chose" in words
    assert "Each judgment whose paragraph you choose is then read whole" not in words
    assert set(research.CHOICE_V17["properties"]) == {"questions", "read_in_full"} and research.IN_FULL == 5
    assert research.PICK_SCHEMAS["judgment"] is research.CHOICE_V17 and research.PICK_SCHEMAS["provision"] is research.CHOICE


def test_only_the_judgments_named_are_read_in_full_and_the_others_stand_by_their_passages():
    model = Model(full=lambda chosen: chosen[:2])
    ctx, plan, record = researched(model)
    assert record["contract"] == "core_research_v18"
    assert [entry["case_id"] for entry in record["judgments"]["D1"]] == ["first case", "second case"]
    sources = answer_sources.build(ctx, record)
    by_case = {}
    for row in sources.values():
        if row["kind"] == "judgment":
            by_case.setdefault(row["source_identity"]["case_id"], []).append(row)
    # Read in full: all three paragraphs; by its passages: the paragraph chosen with the one either side, never as the whole.
    assert {case: len(rows) for case, rows in by_case.items()} == {case: 3 for case in CASES}
    assert {row["coverage"][0]["scope"] for case in CASES[:2] for row in by_case[case]} == {"whole_judgment"}
    assert {row["coverage"][0]["scope"] for case in CASES[2:] for row in by_case[case]} == {"adjacent_indexed_segments"}
    told = response_writer._research_context(record, None)["judgments_read_in_full"]
    assert told["judgments"] == ["First Case", "Second Case"] and "never its whole view" in told["every_other_judgment"]
    # Replayed exactly; a judgment read beyond those named, or one of them dropped, is refused.
    assert research.validate(record, plan, ctx) == record
    for change in (lambda r: r["judgments"]["D1"].pop(),
                   lambda r: r["judgment_picks"]["D1"]["proposal"].update(read_in_full=[]),
                   lambda r: r["judgment_picks"]["D1"]["proposal"].pop("read_in_full")):
        changed = deepcopy(record)
        change(changed)
        with pytest.raises((ValueError, research.SchemaViolation)):
            research.validate(changed, plan, ctx)


def test_at_most_five_are_read_in_full_and_a_named_judgment_the_pick_did_not_choose_is_not():
    ctx, plan, record = researched(Model(choose_judgments=lambda ids: ids[:3], full=lambda chosen: [*chosen, "Q1.4"]))
    # "Q1.4" is the fourth judgment's paragraph, shown but not chosen: it is not read in full.
    assert [entry["case_id"] for entry in record["judgments"]["D1"]] == ["first case", "second case", "third case"]
    searches, pick = record["searches"], record["judgment_picks"]["D1"]
    assert research._in_full(plan, searches, pick) == ["first case", "second case", "third case"]
    assert [case for case, _, _ in research._chosen_cases(plan, searches, pick, limit=2)] == ["first case", "second case"]
    assert [case for case, _, _ in research._chosen_cases(plan, searches, pick, limit=0)] == []
    assert [case for case, _, _ in research._chosen_cases(plan, searches, pick, research.FURTHER_CONTRACT)] == [
        "first case", "second case", "third case"], "a v16 record reads every judgment chosen, as it did"


def test_a_pick_that_cannot_be_made_reads_none_in_full_and_its_paragraphs_stand_by_their_passages():
    ctx, plan, record = researched(Model(fail={"core_research_judgment_pick"}))
    assert record["judgment_picks"]["D1"]["state"] == "unavailable" and record["judgments"]["D1"] == []
    rows = [row for row in answer_sources.build(ctx, record).values() if row["kind"] == "judgment"]
    assert rows and {row["coverage"][0]["scope"] for row in rows} <= {"adjacent_indexed_segments", "selected_indexed_segment"}
    assert research.validate(record, plan, ctx) == record


def test_each_label_is_said_once_in_what_the_models_read_and_the_record_is_unchanged():
    ctx, plan, record = researched(Model(full=lambda chosen: chosen[:1]))
    sources = answer_sources.build(ctx, record)
    compact = answer_sources.presentation(sources, aliased=True, compact=True)
    assert compact["passages"] and not any("work_ids" in passage for passage in compact["passages"])
    assert all(passage["context_group_id"].startswith("g") for passage in compact["passages"])
    assert all(identity.startswith("c") for identity in compact["coverage_by_id"])
    assert all("work_id" in entry for entry in compact["coverage_by_id"].values()), "the question a passage serves stays said"
    titles = compact["group_titles"]
    assert {titles[passage["context_group_id"]] for passage in compact["passages"] if passage["kind"] == "judgment"} >= {"First Case"}
    assert not any("title" in passage for passage in compact["passages"]), "each title once, on its group"
    full = answer_sources.presentation(sources, aliased=True)
    assert all("work_ids" in passage and "title" in passage for passage in full["passages"])
    assert all(passage["context_group_id"].startswith("context:") for passage in full["passages"])


def test_a_second_look_or_a_take_up_is_shown_only_the_law_the_section_relies_on():
    ctx, plan, record = researched(Model(full=lambda chosen: chosen[:1]))
    sources = answer_sources.build(ctx, record)
    held = answer_sources.presentation(sources, aliased=True, compact=True)
    judgment = next(p for p in held["passages"] if p["kind"] == "judgment" and "Paragraph 1 of third case" in p["text"])
    provision = next(p for p in held["passages"] if p["kind"] == "provision")
    shown = response_writer._relied_on(held, {"units": [{"uses": [{"source_id": judgment["id"]}, {"source_id": provision["id"]}]}]})
    texts = [p["text"] for p in shown["passages"]]
    # What the section cites, what is read with it, and the judgment read in full - not the fourth judgment's passages.
    assert any("third case" in t for t in texts) and any("first case" in t for t in texts)
    assert not any("fourth case" in t for t in texts) and not any("second case" in t for t in texts)
    assert set(shown["context_groups"]) == {p["context_group_id"] for p in shown["passages"]}
    assert set(shown["coverage_by_id"]) == {c for p in shown["passages"] for c in p.get("coverage_ids", ())}
    assert response_writer.RELIED_ON.startswith("the held law this section's paragraphs rely on")


def test_the_judgments_the_papers_cite_have_first_claim_on_the_five():
    """D35 (owner, 3 Nov 2026: "cited judgments always get first claim"): a held judgment the papers cite that the further call
    chooses is read in full first; the pick's named judgments fill what is left of the five; the rest stand by their passages."""
    import re
    from tests.test_the_judgments_the_papers_cite_are_read_by_their_citation import MESSAGE, Index
    found = ("case a", "case b", "case c", "case d", "case e", "case f")
    provisions = Collection()
    provisions.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held = Collection("judgment")
    held.rows = {3 * n + k: {"chunk_id": f"j{n}{k}", "full_text": f"Paragraph {k} of {case}: the court holds rule {n}.",
                             "case_id": case, "case_name": case.title(), "paragraph_num": str(k + 1),
                             "court": "Supreme Court of India", "year": "1996", "cited_by_count": 10, "paragraph_type": "reasoning"}
                 for n, case in enumerate([*found, "cited case"]) for k in range(3)}
    held.lexical = held.semantic = lambda query, depth: [1, 4, 7, 10, 13, 16]
    held.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held.judgment_paragraphs = lambda case_id: [(p, deepcopy(row)) for p, row in held.rows.items() if row["case_id"] == case_id]
    held.context = lambda position, source: {"scope": "selected_indexed_segment", "bounded": False, "unread_positions": [],
                                             "segments": [{"position": p, "row": deepcopy(held.rows[p])}
                                                          for p in (position - 1, position, position + 1) if p in held.rows]}

    def name_the_cited(user):
        label = re.search(r"^(Q\d+): ", user, re.M).group(1)
        return {"questions": [{"question_id": label, "missing": "", "sections": [], "phrases": [], "cited": ["CJ1"]}]}
    ctx = context(MESSAGE)
    plan = research.accept(proposal(1, 1), ctx)
    record = research.retrieve(plan, HybridSearcher({"provision": provisions, "judgment": held}), ctx,
                               model=Model(further=name_the_cited), case_index=Index())
    assert [entry["case_id"] for entry in record["further"]["D1"]["cited_read"]] == ["cited case"]
    assert [entry["case_id"] for entry in record["judgments"]["D1"]] == ["case a", "case b", "case c", "case d"]
    assert [entry["case_id"] for entry in record["further"]["D1"]["judgments"]] == []
    by_passages = {row["source_identity"]["case_id"] for row in answer_sources.build(ctx, record).values()
                   if row["kind"] == "judgment" and row["coverage"][0]["scope"] == "adjacent_indexed_segments"}
    assert by_passages == {"case e", "case f"}
    assert research.validate(record, plan, ctx) == record
    for change in (lambda r: r["further"]["D1"]["cited_read"].clear(),
                   lambda r: r["judgments"]["D1"].append(deepcopy(r["further"]["D1"]["cited_read"][0]))):
        changed = deepcopy(record)
        change(changed)
        with pytest.raises(ValueError):
            research.validate(changed, plan, ctx)


def sections_library():
    """Eight sections a first search finds and four more a search for when time runs finds, one judgment paragraph each time."""
    provisions = Collection()
    provisions.rows = {p: {"chunk_id": f"s{p}", "full_text": f"Section {p}\nProvision {p} text.", "act_id": "act",
                           "act_name": "Act", "section_number": str(p)} for p in range(12)}
    provisions.lexical = provisions.semantic = lambda query, depth: [8, 9, 10, 11] if "time runs" in query else list(range(8))
    provisions.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    held = Collection("judgment")
    held.rerank = lambda pairs, *, anchors=None: [1.0] * len(pairs)
    return HybridSearcher({"provision": provisions, "judgment": held})


def test_each_question_keeps_at_most_five_sections_the_pick_names_the_two_to_five_that_govern():
    """D36 (owner, 3 Nov 2026: "there won't be more than lets say 2-5 relevants section"): the pick is asked for the two to five
    provisions that govern each question; code keeps at most five, in the pick's order; named and linked ones count within them."""
    words = " ".join(research.PICK_V18.split())
    assert "choose the two to five provisions that govern it" in words and "no more than five are read for a question" in words
    assert research.PICKS["provision"][1] is research.PICK_V18 and research.SECTIONS_A_QUESTION == 5
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 1), ctx)
    record = research.retrieve(plan, sections_library(), ctx, model=Model())
    work_id = plan["work"][0]["id"]
    chosen = record["picks"]["D1"]["chosen"][work_id]
    returned = [c["id"] for c in record["searches"][work_id]["candidates"] if c["kind"] == "provision"]
    assert len(returned) == 8 and chosen == returned[:5], "the pick named all eight; the first five it named are kept"
    assert research.validate(record, plan, ctx) == record
    changed = deepcopy(record)
    changed["picks"]["D1"]["chosen"][work_id] = returned[:6]
    with pytest.raises(ValueError, match="differs from its proposal"):
        research.validate(changed, plan, ctx)
    # A v17 pick kept every provision it named, and replays so.
    labels = research._labels(plan, record["searches"])
    proposal_ = record["picks"]["D1"]["proposal"]
    assert research._resolve_picks(proposal_, plan, record["searches"], labels)[0][work_id] == returned


def test_the_further_pick_keeps_only_what_is_left_of_each_questions_five():
    import re

    def time_missing(user):
        label = re.search(r"^(Q\d+): ", user, re.M).group(1)
        return {"questions": [{"question_id": label, "missing": "When time runs.", "sections": [], "phrases": ["when time runs"],
                               "cited": []}]}
    ctx = context("Find the applicable law.")
    plan = research.accept(proposal(1, 1), ctx)
    record = research.retrieve(plan, sections_library(), ctx, model=Model(choose=lambda ids: ids[:4], further=time_missing))
    work_id = plan["work"][0]["id"]
    assert len(record["picks"]["D1"]["chosen"][work_id]) == 4
    further = record["further"]["D1"]
    assert len(further["picks"]["provision"]["chosen"][work_id]) == 1, "four first, so one more"
    assert research.validate(record, plan, ctx) == record
    changed = deepcopy(record)
    fresh = dict(research.further_searches(record))[work_id]
    changed["further"]["D1"]["picks"]["provision"]["chosen"][work_id] = [c["id"] for c in fresh["candidates"]
                                                                          if c["kind"] == "provision"][:2]
    with pytest.raises(ValueError):
        research.validate(changed, plan, ctx)
