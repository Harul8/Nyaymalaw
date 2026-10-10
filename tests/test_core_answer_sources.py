"""Exact source ownership and answer projections, without model or corpus calls."""
from copy import deepcopy
import json

import pytest

from nm.core_engine.answer_sources import CONTRACT, build, presentation, select
from nm.core_engine.research import accept, retrieve, validate
from nm.core_engine.retrieval import HybridSearcher, _candidate, _digest
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import work
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


class AdjacentJudgment(Collection):
    def __init__(self, *, bounded=False):
        super().__init__("judgment")
        self.bounded = bounded
        self.rows[0].update(full_text="Counsel submitted that the amount was payable.",
                            atom_type="holding", paragraph_type="court_holding")
        self.rows[1].update(full_text="The Court rejected that submission because its condition was unmet.",
                            paragraph_num="13", atom_type="argument")

    def lexical(self, query, depth): return [0]
    def semantic(self, query, depth): return [0]

    def context(self, position, source):
        return {"scope": "adjacent_indexed_segments", "bounded": self.bounded,
                "unread_positions": [2] if self.bounded else [],
                "segments": [{"position": p, "row": deepcopy(row)} for p, row in self.rows.items()]}


def fixture(*, work_count=1, history=None, judgment=None):
    ctx = context("Find the applicable law.", history)
    plan = accept({"work": [work() for _ in range(work_count)]}, ctx)
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    searcher = HybridSearcher({"provision": statute, "judgment": judgment or AdjacentJudgment()})
    return ctx, retrieve(plan, searcher, ctx)


def test_each_adjacent_passage_has_its_own_exact_selectable_tag_and_shared_context():
    ctx, record = fixture()
    original = deepcopy(record)
    sources = build(ctx, record)
    chosen = next(c for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "judgment")
    argument = sources[chosen["id"]]
    rejection = next(s for s in sources.values() if s["kind"] == "judgment" and s["id"] != argument["id"])
    adjacent = next(s for s in chosen["context"]["segments"] if s["position"] == 1)
    expected = _candidate("judgment", 1, adjacent["row"], chosen["corpus_revision"], None, [], {})
    assert rejection["id"] == expected["id"]
    assert rejection["digest"] == _digest(adjacent["row"])
    assert rejection["id"] in argument["context_ids"]
    assert argument["id"] in rejection["context_ids"]
    assert argument["id"] not in argument["context_ids"]
    assert select({"source_id": rejection["id"], "quote": rejection["text"]}, sources) == {
        "source_id": rejection["id"], "start": 0, "end": len(rejection["text"]), "text": rejection["text"]}
    assert record == original


def test_duplicate_sources_across_work_keep_one_record_and_all_owned_memberships():
    ctx, record = fixture(work_count=2)
    sources = build(ctx, record)
    assert len(sources) == 5  # Original message, two provisions, two judgment segments.
    for row in sources.values():
        assert row["work_ids"] == ["t2:w1", "t2:w2"]
        if row["kind"] in {"provision", "judgment"}:
            assert {c["work_id"] for c in row["coverage"]} == {"t2:w1", "t2:w2"}
            assert len(row["coverage"]) == 2


def test_presentation_preserves_exact_provenance_but_does_not_promote_parser_roles():
    history = [
        {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
         "record_role": "original_account", "text": "The allegation remains disputed."},
        {"source_id": "t1:nm", "turn_id": "t1", "speaker": "nm",
         "record_role": "nm_interpretation", "text": "An earlier NM interpretation."},
        {"source_id": "t1:service", "turn_id": "t1", "speaker": "service",
         "record_role": "service_status", "text": "Earlier delivery interrupted."},
    ]
    ctx, record = fixture(history=history)
    sources = build(ctx, record)
    assert CONTRACT == "core_answer_sources_v1"
    assert [sources[r["source_id"]]["kind"] for r in history] == ["account", "nm_context", "service"]
    assert sources["t1:advocate"]["digest"] == _digest(history[0])
    legal = presentation(sources)
    assert len(legal) == 4 and {r["kind"] for r in legal} == {"provision", "judgment"}
    assert all(r["record_role"] == "retrieved_candidate" and r["speaker"] is None for r in legal)
    assert "paragraph_type" not in json.dumps(legal) and "court_holding" not in json.dumps(legal)
    assert any(r["locator"] == "Article 64" for r in legal)
    assert all(set(r) == {"id", "kind", "text", "speaker", "record_role", "title", "locator",
                          "digest", "context_ids", "work_ids", "coverage", "source_identity"} for r in sources.values())
    legal[0]["text"] = "Presentation-only change"
    assert sources[legal[0]["id"]]["text"] != legal[0]["text"]


@pytest.mark.parametrize("damage", ["speaker", "record_role", "quote", "legal_source", "corpus_revision"])
def test_changed_source_or_research_provenance_is_rejected_before_cataloguing(damage):
    ctx, record = fixture()
    if damage in {"speaker", "record_role", "quote"}:
        field = "text" if damage == "quote" else damage
        record["plan"]["work"][0]["sources"][0][field] = "Unowned alteration"
    else:
        source = record["searches"]["t2:w1"]["candidates"][0]
        if damage == "legal_source": source["source"]["full_text"] = "Changed stored passage"
        else: source["corpus_revision"] = "other snapshot"
    with pytest.raises(ValueError): build(ctx, record)


def test_same_corpus_position_cannot_supply_contradictory_passages_across_work():
    ctx, record = fixture(work_count=2)
    search = record["searches"]["t2:w2"]
    i = next(i for i, c in enumerate(search["candidates"]) if c["kind"] == "judgment")
    prior = search["candidates"][i]
    changed = deepcopy(prior["source"])
    changed["full_text"] = "A contradictory snapshot at the same position."
    window = deepcopy(prior["context"])
    for segment in window["segments"]:
        if segment["position"] == prior["position"]:
            segment.update(row=changed, content_digest=_digest(changed))
    search["candidates"][i] = _candidate("judgment", prior["position"], changed,
        prior["corpus_revision"], prior["score"], prior["query_ids"], window)
    assert validate(record, record["plan"], ctx) == record
    with pytest.raises(ValueError, match="conflicting saved source"): build(ctx, record)


def test_original_source_id_cannot_overwrite_a_legal_source_tag():
    ctx, first = fixture()
    legal_id = first["searches"]["t2:w1"]["candidates"][0]["id"]
    ctx["latest"]["source_id"] = legal_id
    item = work()
    item["sources"][0]["source_id"] = legal_id
    plan = accept({"work": [item]}, ctx)
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    record = retrieve(plan, HybridSearcher({"provision": statute, "judgment": AdjacentJudgment()}), ctx)
    with pytest.raises(ValueError, match="conflicting content or provenance"): build(ctx, record)


def test_exact_selection_rejects_unknown_ambiguous_and_normalised_words():
    earlier = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
               "record_role": "original_account", "text": "First yes. Second yes."}
    ctx, record = fixture(history=[earlier])
    sources = build(ctx, record)
    for ref in ({"source_id": "foreign", "quote": "yes."},
                {"source_id": "t1:advocate", "quote": "yes."},
                {"source_id": "t1:advocate", "quote": "First  yes."}):
        with pytest.raises(SchemaViolation): select(ref, sources)
    assert select({"source_id": "t1:advocate", "quote": "Second yes."}, sources) == {
        "source_id": "t1:advocate", "start": 11, "end": 22, "text": "Second yes."}


def test_partial_context_keeps_readable_sources_and_explicit_coverage_gaps():
    ctx, record = fixture(judgment=AdjacentJudgment(bounded=True))
    sources = build(ctx, record)
    assert record["state"] == "partial"
    for row in presentation(sources):
        coverage = row["coverage"][0]
        if row["kind"] == "judgment":
            assert coverage["bounded"] is True and coverage["unread_positions"] == [2]
            assert coverage["gaps"] and coverage["selected_source_id"] in sources
        else:
            assert coverage["bounded"] is False and coverage["gaps"] == []


def test_search_failure_preserves_original_sources_without_inventing_legal_coverage():
    ctx = context("Find the applicable law.")
    plan = accept({"work": [work()]}, ctx)
    record = retrieve(plan, None, ctx)
    sources = build(ctx, record)
    assert list(sources) == [ctx["latest"]["source_id"]]
    assert presentation(sources) == [] and record["failures"]


@pytest.mark.parametrize("field,value", [("record_role", "unknown"), ("speaker", None), ("turn_id", "")])
def test_unowned_original_provenance_cannot_be_presented_as_account(field, value):
    prior = {"source_id": "t1:advocate", "turn_id": "t1", "speaker": "advocate",
             "record_role": "original_account", "text": "Earlier attributed words."}
    prior[field] = value
    ctx, record = fixture(history=[prior])
    with pytest.raises(ValueError, match="owned provenance"): build(ctx, record)


def test_document_title_alone_cannot_supply_legal_document_ownership():
    judgment = AdjacentJudgment()
    for row in judgment.rows.values():
        del row["case_id"]
    ctx, record = fixture(judgment=judgment)
    assert validate(record, record["plan"], ctx) == record
    with pytest.raises(ValueError, match="owned document identity"): build(ctx, record)
