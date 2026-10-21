"""Exact source ownership and answer projections, without model or corpus calls."""
from copy import deepcopy
import json

import pytest

from nm.core_engine.answer_sources import CONTRACT, aliases, build, presentation, select, shown_context
from nm.core_engine.research import accept, retrieve, validate
from nm.core_engine.retrieval import HybridSearcher, _candidate, _digest
from nm.shared.model_port import SchemaViolation
from tests.test_core_research import Model, proposal
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection

pytestmark = pytest.mark.class_a


class AdjacentJudgment(Collection):
    def __init__(self, *, bounded=False, hit=0):
        super().__init__("judgment")
        self.bounded, self.hit = bounded, hit
        self.rows[0].update(full_text="Counsel submitted that the amount was payable.",
                            atom_type="holding", paragraph_type="court_holding")
        self.rows[1].update(full_text="The Court rejected that submission because its condition was unmet.",
                            paragraph_num="13", atom_type="argument")

    def lexical(self, query, depth): return [self.hit]
    def semantic(self, query, depth): return [self.hit]

    def context(self, position, source):
        return {"scope": "adjacent_indexed_segments", "bounded": self.bounded,
                "unread_positions": [2] if self.bounded else [],
                "segments": [{"position": p, "row": deepcopy(row)} for p, row in self.rows.items()]}


def fixture(*, work_count=1, history=None, judgment=None):
    ctx = context("Find the applicable law.", history)
    plan = accept(proposal(work_count), ctx)
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    searcher = HybridSearcher({"provision": statute, "judgment": judgment or AdjacentJudgment()})
    return ctx, retrieve(plan, searcher, ctx, model=Model())


def presented_coverage(displayed, identity):
    row = deepcopy(displayed["coverage_by_id"][identity])
    if "gap_ids" in row:
        row["gaps"] = [deepcopy(displayed["gaps_by_id"][gap]) for gap in row.pop("gap_ids")]
    return row


def reconstruct_passage(displayed, row):
    restored = deepcopy(row)
    restored["context_ids"] = [identity for identity in displayed["context_groups"][
        restored.pop("context_group_id")] if identity != row["id"]]
    restored["coverage"] = [presented_coverage(displayed, identity)
                            for identity in restored.pop("coverage_ids")]
    return restored


def without_storage_proof(row):
    retained = deepcopy(row)
    retained.pop("digest")
    retained["source_identity"] = {key: value for key, value in retained["source_identity"].items()
                                   if key not in {"chunk_id", "corpus_revision"}}
    return retained


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
    displayed = presentation(sources)
    legal = displayed["passages"]
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
    # The saved judgment pick named the paragraph at this place in the list (v8).
    record["judgment_picks"]["D1"]["chosen"]["t2:w2"] = [search["candidates"][i]["id"] if c == prior["id"] else c
                                                   for c in record["judgment_picks"]["D1"]["chosen"]["t2:w2"]]
    assert validate(record, record["plan"], ctx) == record
    with pytest.raises(ValueError, match="conflicting saved source"): build(ctx, record)


def test_original_source_id_cannot_overwrite_a_legal_source_tag():
    ctx, first = fixture()
    legal_id = first["searches"]["t2:w1"]["candidates"][0]["id"]
    ctx["latest"]["source_id"] = legal_id
    plan = accept(proposal(), ctx)  # v7 work selects the whole latest message
    statute = Collection()
    statute.rows[0]["section_number"] = "Article_64"
    record = retrieve(plan, HybridSearcher({"provision": statute, "judgment": AdjacentJudgment()}), ctx, model=Model())
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


def test_an_unknown_source_names_itself_and_what_can_be_named():
    # 16 Oct 2026: the owner's end-to-end matter was withheld twice for this; a
    # correction told only that a source was unknown repeated the same mistake.
    sources = {
        "provision:a": {"id": "provision:a", "kind": "provision", "text": "A rule."},
        "provision:b": {"id": "provision:b", "kind": "provision", "text": "Another rule."},
        "judgment:c": {"id": "judgment:c", "kind": "judgment", "text": "A holding."},
        "t1:advocate": {"id": "t1:advocate", "kind": "account", "text": "We act for the buyer."},
        "t1:doc_1:page:2": {"id": "t1:doc_1:page:2", "kind": "document", "text": "Page two."}}
    with pytest.raises(SchemaViolation) as refused:
        select({"source_id": "context:3", "quote": None}, sources)
    why = str(refused.value)
    assert "'context:3' is not in the owned answer catalogue" in why
    assert "P1 to P2; J1; M1; DOC1: provisions, judgments, messages, document pages" in why
    assert "context, coverage, gap, fact, dispute and reply-unit labels are not sources" in why


def test_messages_and_document_pages_are_named_by_short_ids_and_mapped_back():
    # 16 Oct 2026: owned IDs embed a long random turn identifier a writer miscopied.
    sources = {
        "turn_9f3c-4c8d:advocate": {"id": "turn_9f3c-4c8d:advocate", "kind": "account", "text": "We act."},
        "provision:a": {"id": "provision:a", "kind": "provision", "text": "A rule."},
        "turn_9f3c-4c8d:d1p1": {"id": "turn_9f3c-4c8d:d1p1", "kind": "document", "text": "Page one."},
        "turn_9f3c-4c8d:d1p2": {"id": "turn_9f3c-4c8d:d1p2", "kind": "document", "text": "Page two."}}
    named = aliases(sources)
    assert named == {"P1": "provision:a", "M1": "turn_9f3c-4c8d:advocate",
                     "DOC1": "turn_9f3c-4c8d:d1p1", "DOC2": "turn_9f3c-4c8d:d1p2"}
    context = {"latest": {"source_id": "turn_9f3c-4c8d:advocate", "turn_id": "turn_9f3c-4c8d", "text": "We act."},
               "documents": [{"source_id": "turn_9f3c-4c8d:d1p2", "text": "Page two."}]}
    shown = shown_context(context, sources)
    assert shown["latest"]["source_id"] == "M1" and shown["documents"][0]["source_id"] == "DOC2"
    assert shown["latest"]["turn_id"] == "turn_9f3c-4c8d" and shown["latest"]["text"] == "We act."


def test_a_held_passage_line_break_is_layout_and_the_selection_keeps_the_held_words():
    # Open items round, 16 Oct 2026: the live written statement answer was withheld
    # because a reviewer's quote met the passage's line break with a space.
    sources = {
        "P": {"id": "P", "kind": "provision", "text": "within thirty days from the date of service of \nsummons on him"},
        "A": {"id": "A", "kind": "account", "text": "served on\n4 September"}}
    assert select({"source_id": "P", "quote": "service of summons on him"}, sources) == {
        "source_id": "P", "start": 36, "end": 62, "text": "service of \nsummons on him"}
    with pytest.raises(SchemaViolation, match="not exact"):
        select({"source_id": "A", "quote": "served on 4 September"}, sources)


def test_partial_context_keeps_readable_sources_and_explicit_coverage_gaps():
    # The returned paragraph's later neighbour could not be read (v8 reads one either side).
    ctx, record = fixture(judgment=AdjacentJudgment(bounded=True, hit=1))
    sources = build(ctx, record)
    assert record["state"] == "partial"
    displayed = presentation(sources)
    for row in displayed["passages"]:
        coverage = presented_coverage(displayed, row["coverage_ids"][0])
        if row["kind"] == "judgment":
            assert coverage["bounded"] is True and coverage["unread_positions"] == [2]
            assert coverage["gaps"] and coverage["selected_source_id"] in sources
        else:
            assert coverage["bounded"] is False and coverage["gaps"] == []


def test_search_failure_preserves_original_sources_without_inventing_legal_coverage():
    ctx = context("Find the applicable law.")
    plan = accept(proposal(), ctx)
    record = retrieve(plan, None, ctx, model=Model())
    sources = build(ctx, record)
    assert list(sources) == [ctx["latest"]["source_id"]]
    assert presentation(sources) == {"passages": [], "coverage_by_id": {},
                                     "gaps_by_id": {}, "context_groups": {}}
    assert record["failures"]


def test_presentation_deduplicates_full_coverage_without_changing_canonical_proof():
    ctx, record = fixture(work_count=2, judgment=AdjacentJudgment(bounded=True))
    sources = build(ctx, record)
    original, proof = deepcopy(sources), _digest(sources)
    displayed = presentation(sources)
    rows, catalogue = displayed["passages"], displayed["coverage_by_id"]
    originals = [row for row in sources.values() if row["kind"] in {"provision", "judgment"}]
    assert {row["id"] for row in rows} == {row["id"] for row in originals}
    assert len(catalogue) < sum(len(row["coverage"]) for row in originals)
    assert len(catalogue) == len({json.dumps(entry, sort_keys=True) for entry in catalogue.values()})
    for row in rows:
        assert reconstruct_passage(displayed, row) == without_storage_proof(sources[row["id"]])
    assert sources == original and _digest(sources) == proof
    next(iter(displayed["context_groups"].values())).append("presentation-only")
    next(iter(displayed["gaps_by_id"].values()))["detail"] = "presentation-only"
    assert sources == original and _digest(sources) == proof


def test_coverage_dedup_keeps_distinct_missing_fields_gaps_and_work_associations():
    ctx, record = fixture(judgment=AdjacentJudgment(bounded=True))
    sources = build(ctx, record)
    legal = next(row for row in sources.values() if row["kind"] == "judgment")
    original = deepcopy(legal["coverage"][0])
    variants = [deepcopy(original) for _ in range(5)]
    variants[0].pop("gaps")
    variants[1]["gaps"] = []
    variants[2]["unread_positions"] = [3]
    variants[3]["work_id"] = "other-owned-work"
    variants[4]["gaps"][0]["detail"] = "A distinct unread-context explanation."
    legal["coverage"] = [original, *variants, dict(reversed(list(original.items())))]
    saved = deepcopy(sources)
    displayed = presentation(sources)
    row = next(row for row in displayed["passages"] if row["id"] == legal["id"])
    assert len(set(row["coverage_ids"])) == 6
    assert row["coverage_ids"][0] == row["coverage_ids"][-1]
    assert [presented_coverage(displayed, identity) for identity in row["coverage_ids"]] == legal["coverage"]
    assert sources == saved


def test_shared_context_reconstructs_neighbours_without_merging_order_or_partial_overlap():
    ctx, record = fixture()
    sources = build(ctx, record)
    legal = [row for row in sources.values() if row["kind"] in {"provision", "judgment"}]
    a, b, c, d = [row["id"] for row in legal]
    legal[0]["context_ids"] = [b, c]
    legal[1]["context_ids"] = [a, c]
    legal[2]["context_ids"] = [b, a]
    legal[3]["context_ids"] = [a]
    original = deepcopy(sources)
    displayed = presentation(sources)
    rows = displayed["passages"]
    assert rows[0]["context_group_id"] == rows[1]["context_group_id"]
    assert len(displayed["context_groups"]) == 3
    for row in rows:
        assert reconstruct_passage(displayed, row) == without_storage_proof(sources[row["id"]])
    assert sources == original


def test_empty_context_and_distinct_same_text_sources_keep_their_identity_and_provenance():
    ctx, record = fixture(work_count=2)
    sources = build(ctx, record)
    legal = [row for row in sources.values() if row["kind"] == "provision"]
    legal[1]["text"] = legal[0]["text"]
    legal[1]["locator"] = legal[0]["locator"]
    legal[1]["source_identity"]["act_id"] = "another-owned-act"
    for row in legal:
        row["context_ids"] = []
    displayed = presentation(sources)
    shown = [row for row in displayed["passages"] if row["kind"] == "provision"]
    assert len(shown) == 2 and shown[0]["id"] != shown[1]["id"]
    assert shown[0]["source_identity"]["act_id"] != shown[1]["source_identity"]["act_id"]
    for row in shown:
        assert reconstruct_passage(displayed, row) == without_storage_proof(sources[row["id"]])
        assert row["work_ids"] == ["t2:w1", "t2:w2"]
        assert set(row["source_identity"]) == {"position", "act_id"}


def test_shared_gaps_preserve_distinct_reasons_missing_fields_and_original_order():
    ctx, record = fixture()
    sources = build(ctx, record)
    legal = next(row for row in sources.values() if row["kind"] == "judgment")
    base = deepcopy(legal["coverage"][0])
    one = {"kind": "judgment", "reason": "A source is unread", "positions": [4, 5]}
    changed = {**one, "reason": "A different source is unread"}
    absent = {"kind": "judgment", "positions": [4, 5]}
    empty = {**absent, "reason": ""}
    legal["coverage"] = [{**base, "gaps": [one, changed, absent, empty, one]},
                         {**base, "gaps": [changed, one]}]
    displayed = presentation(sources)
    row = next(row for row in displayed["passages"] if row["id"] == legal["id"])
    assert len(displayed["gaps_by_id"]) == 4
    assert reconstruct_passage(displayed, row) == without_storage_proof(legal)


def test_missing_passage_coverage_is_not_silently_replaced_with_empty_coverage():
    ctx, record = fixture()
    sources = build(ctx, record)
    legal = next(row for row in sources.values() if row["kind"] == "judgment")
    del legal["coverage"]
    with pytest.raises(KeyError):
        presentation(sources)


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


def test_statutes_are_presented_under_their_shown_name_while_the_catalogue_keeps_the_stored_one():
    """Owner decisions, 10-11 Oct 2026: AP State laws are shown as Telangana laws; words unchanged."""
    ctx = context("Find the applicable law.")
    plan = accept(proposal(), ctx)
    statute = Collection()
    stored = "Telangana 1960 0 Andhra Pradesh Buildings (Lease, Rent And Eviction) Control Act, 1960"
    for row in statute.rows.values():
        row.update(act_name=stored,
                   act_id="TELANGANA_1960_0_ANDHRA PRADESH BUILDINGS (LEASE, RENT AND EVICTION) CONTROL ACT, 1960")
    record = retrieve(plan, HybridSearcher({"provision": statute, "judgment": AdjacentJudgment()}), ctx, model=Model())
    sources = build(ctx, record)
    provisions = [row for row in sources.values() if row["kind"] == "provision"]
    assert provisions and all(row["title"] == stored for row in provisions)
    shown = [row for row in presentation(sources)["passages"] if row["kind"] == "provision"]
    assert {row["title"] for row in shown} == {"Telangana Buildings (Lease, Rent And Eviction) Control Act, 1960"}
    assert [row["text"] for row in shown] == [sources[row["id"]]["text"] for row in shown]


def test_aliases_name_each_legal_passage_once_in_catalogue_order():
    from nm.core_engine.answer_sources import aliases
    ctx, record = fixture()
    sources = build(ctx, record)
    offered = aliases(sources)
    legal = [identity for identity, row in sources.items() if row["kind"] in {"provision", "judgment"}]
    assert [identity for alias, identity in offered.items() if alias[0] in "PJ"] == legal
    assert len(set(offered)) == len(offered) == len(set(offered.values()))
    for alias, identity in offered.items():
        assert alias.rstrip("0123456789") == {"provision": "P", "judgment": "J", "account": "M", "nm_context": "M",
                                              "service": "M", "document": "DOC"}[sources[identity]["kind"]]
        assert len(alias) < 6
    assert aliases(deepcopy(sources)) == offered, "replay re-derives the same map"
    # Messages are named by M ids from 16 Oct 2026; every conversation source has one.
    assert {i for i, row in sources.items() if row["kind"] == "account"} <= set(offered.values())


def test_aliased_presentation_renames_only_passage_tags_and_context_members():
    from nm.core_engine.answer_sources import aliases
    ctx, record = fixture()
    sources = build(ctx, record)
    plain, aliased = presentation(sources), presentation(sources, aliased=True)
    offered = {tag: alias for alias, tag in aliases(sources).items()}
    assert [row["id"] for row in aliased["passages"]] == [offered[row["id"]] for row in plain["passages"]]
    for row_plain, row_aliased in zip(plain["passages"], aliased["passages"]):
        assert {**row_aliased, "id": row_plain["id"]} == row_plain
    assert aliased["context_groups"] == {identity: [offered.get(m, m) for m in members]
                                         for identity, members in plain["context_groups"].items()}
    assert presentation(sources) == plain, "the owned-tag presentation is unchanged"
    assert "provision:" not in json.dumps(aliased) and "judgment:" not in json.dumps(aliased)


# --- research v8: picked judgments read with their neighbours; compact part views ----------

class LongJudgment(Collection):
    """Seven stored paragraphs of one judgment; the search returns the second and fifth."""
    def __init__(self):
        super().__init__("judgment")
        self.rows = {p: {"chunk_id": f"para{p}", "full_text": f"Paragraph {p} of the judgment.",
                         "case_id": "case", "case_name": "Judgment", "paragraph_num": str(p + 1)} for p in range(7)}

    def lexical(self, query, depth): return [1, 4]
    def semantic(self, query, depth): return [1, 4]

    def context(self, position, source):
        near = [p for p in self.rows if abs(p - position) <= 2]
        return {"scope": "adjacent_indexed_segments", "bounded": False, "unread_positions": [],
                "segments": [{"position": p, "row": deepcopy(self.rows[p])} for p in near]}


def test_a_picked_judgment_is_read_with_one_paragraph_either_side_and_every_other_alone():
    ctx = context("Find the applicable law.")
    plan = accept(proposal(), ctx)
    searcher = HybridSearcher({"provision": Collection(), "judgment": LongJudgment()})
    record = retrieve(plan, searcher, ctx, model=Model(choose_judgments=lambda ids: ids[:1]))
    returned = [c for c in record["searches"]["t2:w1"]["candidates"] if c["kind"] == "judgment"]
    picked = next(c for c in returned if c["id"] in record["judgment_picks"]["D1"]["chosen"]["t2:w1"])
    other = next(c for c in returned if c["id"] != picked["id"])
    sources = build(ctx, record)
    read = sorted(int(r["source_identity"]["position"]) for r in sources.values() if r["kind"] == "judgment")
    assert read == sorted({picked["position"] - 1, picked["position"], picked["position"] + 1, other["position"]})
    assert sources[other["id"]]["context_ids"] == []  # the unpicked paragraph is still there, alone
    scopes = {c["selected_source_id"]: c["scope"] for r in sources.values() for c in r["coverage"]}
    assert scopes[picked["id"]] == "adjacent_indexed_segments" and scopes[other["id"]] == "selected_indexed_segment"


class PerQuestion(Collection):
    """Each legal question's phrases find a different stored paragraph."""
    def __init__(self):
        super().__init__("judgment")
        self.rows[1]["case_id"] = "other case"

    def lexical(self, query, depth):
        return [0] if "D1Q1" in query else [1] if "D1Q2" in query else []
    semantic = lexical

    def context(self, position, source):
        return {"scope": "selected_indexed_segment", "bounded": False, "unread_positions": [],
                "segments": [{"position": position, "row": deepcopy(source)}]}


def test_a_compact_part_view_shows_only_that_parts_passages_under_the_whole_answers_ids():
    ctx = context("Find the applicable law.")
    plan = accept(proposal(2), ctx)
    searcher = HybridSearcher({"provision": Collection(), "judgment": PerQuestion()})
    sources = build(ctx, retrieve(plan, searcher, ctx, model=Model()))
    whole = presentation(sources, aliased=True)
    part = presentation(sources, aliased=True, compact=True, work_ids=["t2:w1"])
    first = {p["id"] for p in whole["passages"] if "t2:w1" in p["work_ids"]}
    assert {p["id"] for p in part["passages"]} == first < {p["id"] for p in whole["passages"]}
    assert all(not {"source_identity", "record_role", "speaker"} & set(p) for p in part["passages"])
    shown = {p["id"] for p in part["passages"]}
    assert all(set(members) <= shown for members in part["context_groups"].values())
