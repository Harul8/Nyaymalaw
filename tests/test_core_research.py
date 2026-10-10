"""Research plan/source handoffs and independent search outcomes, not semantic proof."""
from copy import deepcopy
import json

import pytest

from nm.core_engine.research import accept, plan, retrieve, search_queries, validate
from nm.core_engine import answer_sources
from nm.core_engine.retrieval import HybridSearcher, SearchUnavailable
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, Usage
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


def work(quote="Find the applicable law."):
    return {"sources": [{"source_id": "t2:advocate", "quote": quote}],
            "search_account": [{"source_id": "t2:advocate", "quote": quote}],
            "enquiries": [
                {"text": "legal prerequisites and exceptions", "purpose": "Locate elements",
                 "basis": "conditional"},
                {"text": "available relief and contrary positions", "purpose": "Test remedies",
                 "basis": "conditional"}]}


class Model:
    def __init__(self, value, budget=100_000, completion=Completion.COMPLETE):
        self.value, self.budget, self.completion, self.calls = value, budget, completion, []

    def context_budget(self, tier): return self.budget

    def structured(self, prompt, schema, tier, **kwargs):
        self.calls.append(prompt)
        return ModelResult(None, deepcopy(self.value), tier, "synthetic", "fixture",
                           Usage(1, 1, 0), 0, completion=self.completion)


def test_planner_sees_original_history_and_does_not_route_only_from_interpretation():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account", "text": "I dispute authorship; no admission was made."}
    ctx = context("Find the applicable law.", [earlier])
    ctx["current_records"] = {"restriction": "No external contact"}
    proposal = work()
    proposal["sources"].append({"source_id": earlier["source_id"], "quote": earlier["text"]})
    proposal["search_account"] = [{"source_id": earlier["source_id"], "quote": None}]
    model = Model({"work": [proposal]})
    admitted = plan(model, ctx, {"units": [], "issues": ["missed request"]})
    assert len(model.calls) == 1
    assert json.loads(model.calls[0].user)["original_context"] == ctx
    queries = search_queries(admitted["work"][0])
    assert all(earlier["text"] in q["context"] for q in queries)
    assert admitted["semantic_review"] == "pending"


def test_invalid_source_is_held_without_losing_independent_work():
    bad = work()
    bad["sources"][0]["source_id"] = "different-matter"
    admitted = accept({"work": [bad, work()]}, context("Find the applicable law."))
    assert len(admitted["work"]) == len(admitted["issues"]) == 1
    assert admitted["work"][0]["id"] == "t2:w2"


def test_complete_source_selection_preserves_original_words_and_attribution_without_copying():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account",
               "text": "The other party alleges authorisation; our client denies it.\nThe original record is not supplied."}
    ctx = context("Examine the position conditionally. Keep the allegation disputed; do not contact anyone.",
                  [earlier])
    item = work(None)
    item["sources"].append({"source_id": earlier["source_id"], "quote": None})
    item["search_account"] = [{"source_id": earlier["source_id"], "quote": None}]
    admitted = accept({"work": [item]}, ctx)
    assert admitted["issues"] == [] and admitted["semantic_review"] == "pending"
    assert admitted["proposal"]["work"][0]["sources"] == item["sources"]
    for selected, original in zip(admitted["work"][0]["sources"], [ctx["latest"], earlier], strict=True):
        assert selected == {**original, "start": 0, "end": len(original["text"])}
    queries = search_queries(admitted["work"][0])
    assert queries[0]["text"] == queries[0]["context"] == earlier["text"]
    assert ctx["latest"]["text"] not in queries[0]["text"]


def test_explicit_changed_quote_is_held_while_complete_source_peer_survives():
    ctx = context("the requested review remains conditional; the allegation is disputed.")
    damaged = work("The requested review remains conditional")
    admitted = accept({"work": [damaged, work(None)]}, ctx)
    assert [item["id"] for item in admitted["work"]] == ["t2:w2"]
    assert admitted["work"][0]["sources"][0]["text"] == ctx["latest"]["text"]
    assert admitted["issues"][0]["work_id"] == "t2:w1"
    assert "exact" in admitted["issues"][0]["mismatch"]
    assert admitted["issues"][0]["proposal"]["sources"][0]["quote"] == damaged["sources"][0]["quote"]


def test_empty_work_remains_a_proposal_not_proof_of_coverage():
    assert accept({"work": []}, context())["semantic_review"] == "pending"


@pytest.mark.parametrize("failure", [SearchUnavailable("Unread work"), RuntimeError("Adapter failed"),
                                   KeyError("missing snapshot field")])
def test_searches_bind_queries_and_preserve_independent_work_when_one_fails(failure):
    admitted = accept({"work": [work(), work()]}, context("Find the applicable law."))
    searcher = HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")})
    original = searcher.search
    seen = []

    def search(queries):
        seen.append(queries)
        if len(seen) == 1: raise failure
        return original(queries)

    searcher.search = search
    ctx = context("Find the applicable law.")
    record = retrieve(admitted, searcher, ctx)
    assert record["state"] == "partial"
    assert set(record["searches"]) == {"t2:w2"}
    assert set(record["failures"]) == {"t2:w1"}
    assert validate(record, admitted, ctx) == record
    broken = deepcopy(record)
    broken["failures"] = {}
    with pytest.raises(ValueError, match="disposition"): validate(broken, admitted, ctx)
    broken = deepcopy(record)
    broken["searches"]["t2:w2"]["queries"][0]["context"] = "Qualification dropped"
    with pytest.raises(ValueError): validate(broken, admitted, ctx)


def test_not_needed_search_does_not_load_corpus_or_invent_execution():
    item = work("Hello.")
    item["enquiries"] = []
    admitted = accept({"work": [item]}, context())
    record = retrieve(admitted, None, context())
    assert record["searches"] == record["failures"] == {}
    assert record["state"] == "evaluated" and record["plan"]["semantic_review"] == "pending"


@pytest.mark.parametrize("distinct_authority_needed", [False, True])
def test_independent_results_survive_shared_or_distinct_authority_plans(distinct_authority_needed):
    """Supplied proposals prove handoffs, not the model's judgment of legal need."""
    ctx = context("Assess the reported position and prepare internal questions. Do not contact anyone.")
    analysis = work(None)
    questions = work(None)
    questions.update(enquiries=[])
    if distinct_authority_needed:
        questions["enquiries"] = [{"text": "legal requirements for disclosure of relevant records",
                                  "purpose": "Find the separately needed disclosure conditions",
                                  "basis": "conditional"}]
    model = Model({"work": [analysis, questions]})
    admitted = plan(model, ctx, {"units": []})
    assert len(model.calls) == 1 and len(admitted["work"]) == 2
    assert admitted["work"][1]["sources"][0]["text"] == ctx["latest"]["text"]

    searcher = HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")})
    search = searcher.search
    requests = []

    def capture(queries):
        requests.append(queries)
        return search(queries)

    searcher.search = capture
    record = retrieve(admitted, searcher, ctx)
    assert validate(record, admitted, ctx) == record
    assert len(requests) == (2 if distinct_authority_needed else 1)
    assert record["plan"]["work"] == admitted["work"]
    assert record["plan"]["semantic_review"] == "pending"
    assert ("t2:w2" in record["searches"]) == distinct_authority_needed
    assert record["failures"] == {}

    sources = answer_sources.build(ctx, record)
    assert sources[ctx["latest"]["source_id"]]["work_ids"] == ["t2:w1", "t2:w2"]
    legal = [row for row in sources.values() if row["kind"] in {"provision", "judgment"}]
    assert legal
    # The same turn's checked catalogue remains selectable by later requested work.
    # No new search or completion is invented for a work item with empty enquiries.
    assert answer_sources.select({"source_id": legal[0]["id"], "quote": None}, sources)["text"] == legal[0]["text"]
    if not distinct_authority_needed:
        assert all(row["work_ids"] == ["t2:w1"] for row in legal)


def test_unconfigured_search_is_a_gap_and_not_empty_success():
    admitted = accept({"work": [work()]}, context("Find the applicable law."))
    record = retrieve(admitted, None, context("Find the applicable law."))
    assert record["state"] == "partial" and record["failures"]


def test_context_overflow_never_trims_or_calls_provider():
    model = Model({"work": []}, budget=1)
    with pytest.raises(ContextOverflow): plan(model, context(), {})
    assert model.calls == []


def test_incomplete_output_is_never_salvaged():
    model = Model({"work": [work()]}, completion=Completion.LENGTH_LIMITED)
    with pytest.raises(ModelError): plan(model, context("Find the applicable law."), {})


def test_replay_rebinds_source_provenance_to_original_context():
    ctx = context("Find the applicable law.")
    admitted = accept({"work": [work()]}, ctx)
    record = retrieve(admitted, None, ctx)
    for damage in ("text", "speaker", "start", "record_role"):
        changed = deepcopy(admitted)
        changed["work"][0]["sources"][0][damage] = "unowned alteration"
        forged = {**record, "plan": changed}
        with pytest.raises(ValueError, match="original sources"): validate(forged, changed, ctx)


@pytest.mark.parametrize("failure", [None, {"stage": "saved", "reason": "ok"},
                                   {"stage": "search", "reason": ""}])
def test_malformed_failed_work_receipt_cannot_pass_replay(failure):
    ctx = context("Find the applicable law.")
    admitted = accept({"work": [work()]}, ctx)
    record = retrieve(admitted, None, ctx)
    record["failures"]["t2:w1"] = failure
    with pytest.raises(ValueError): validate(record, admitted, ctx)


def test_original_queries_preserve_order_boundaries_and_repeated_words_across_turns():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account", "text": "The account remains disputed."}
    ctx = context("The account remains disputed.", [earlier])
    item = work(None)
    item["search_account"] = [item["sources"][0],
        {"source_id": "t1:advocate", "quote": None}, item["sources"][0]]
    admitted = accept({"work": [item]}, ctx)
    account = admitted["work"][0]["search_account"]
    assert [s["turn_id"] for s in account] == ["t1", "t2"]
    query = search_queries(admitted["work"][0])[0]
    assert query["text"].count(earlier["text"]) == 2
    assert "Advocate passage 1:" in query["text"] and "Advocate passage 2:" in query["text"]
    assert query["text"] == query["context"]


@pytest.mark.parametrize("role,speaker", [("nm_interpretation", "nm"), ("service", "service")])
def test_nonoriginal_search_basis_cannot_hide_independent_valid_work(role, speaker):
    previous = {"source_id": "old", "turn_id": "t1", "speaker": speaker,
                "record_role": role, "text": "A prior derived explanation."}
    ctx = context("Review this explanation against my account.", [previous])
    bad, good = work(None), work(None)
    bad["search_account"] = [{"source_id": "old", "quote": None}]
    admitted = accept({"work": [bad, good]}, ctx)
    assert [w["id"] for w in admitted["work"]] == ["t2:w2"]
    assert "original advocate" in admitted["issues"][0]["mismatch"]


def test_concepts_are_not_silently_truncated_and_empty_search_account_is_not_invented():
    ctx = context("Explain the legal relationship in general.")
    item = work(None)
    item["search_account"] = []
    admitted = accept({"work": [item]}, ctx)
    queries = search_queries(admitted["work"][0])
    assert len(queries) == 2 and all(q["context"] == "" for q in queries)
    item["enquiries"] *= 2
    rejected = accept({"work": [item]}, ctx)
    assert rejected["work"] == [] and rejected["issues"]
    assert len(rejected["proposal"]["work"][0]["enquiries"]) == 4


def test_real_frozen_v2_search_replays_without_new_query_construction():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "outputs/core-engine-build-20261010"
    captured = json.loads((root / "live-served-capacity-remeasurement-writer-1-input.json").read_text(encoding="utf-8"))
    record = captured["research"]
    assert record["contract"] == "core_research_v2"
    assert validate(record, record["plan"], captured["context"]) == record
    unknown = {**record, "contract": "unknown_research_version"}
    with pytest.raises(ValueError, match="Unknown"): validate(unknown, record["plan"], captured["context"])
    changed = deepcopy(record)
    first = next(iter(changed["searches"].values()))
    first["queries"][0]["text"] += " unowned addition"
    with pytest.raises(ValueError): validate(changed, changed["plan"], captured["context"])


def test_offered_passage_id_resolves_original_spelling_offsets_and_ownership():
    from nm.core_engine.research import _source_windows
    ctx = context("Hello. Separately, the technician retains the drive. The client disputes a right to retain it.")
    _, _, offered = _source_windows(ctx)
    item = work(None)
    item["search_account"] = [{"source_id": p["source_id"], "quote": None} for p in offered[1:]]
    admitted = accept({"work": [item]}, ctx)
    assert admitted["issues"] == []
    for source in admitted["work"][0]["search_account"]:
        assert source["source_id"] == ctx["latest"]["source_id"]
        assert source["text"] == ctx["latest"]["text"][source["start"]:source["end"]]
        assert source["speaker"] == "advocate" and source["record_role"] == "original_account"
    query = search_queries(admitted["work"][0])[0]["text"]
    assert "Hello." not in query and "Separately, the technician" in query
    assert "The client disputes" in query
    item["search_account"][0]["source_id"] += ":unknown"
    assert accept({"work": [item]}, ctx)["issues"]


def test_briefly_served_v3_broad_plan_preserves_captured_query_serialization():
    from pathlib import Path
    from nm.core_engine.research import PREVIOUS_CONTRACT
    root = Path(__file__).resolve().parents[1] / "outputs/core-engine-build-20261010"
    inputs = json.loads((root / "research-v3-runtime-ready-inputs.json").read_text(encoding="utf-8"))
    outputs = json.loads((root / "research-v3-runtime-ready-results.json").read_text(encoding="utf-8"))
    case, result = inputs["cases"][1], outputs["calls"][1]
    plan = result["admitted_plan"]
    assert accept(plan["proposal"], case["context"], contract=PREVIOUS_CONTRACT) == plan
    assert {w["id"]: search_queries(w, contract=PREVIOUS_CONTRACT) for w in plan["work"]} == result["constructed_queries"]
