"""Research plan/source handoffs and independent search outcomes, not semantic proof."""
from copy import deepcopy
import json

import pytest

from nm.core_engine.research import accept, plan, retrieve, search_queries, validate
from nm.core_engine.retrieval import HybridSearcher, SearchUnavailable
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, Usage
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


def work(quote="Find the applicable law."):
    return {"purpose": "Find relevant authority", "outcome": "Source-backed analysis",
            "sources": [{"source_id": "t2:advocate", "quote": quote}],
            "constraints": ["No external contact"], "unresolved": [], "enquiries": [
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
