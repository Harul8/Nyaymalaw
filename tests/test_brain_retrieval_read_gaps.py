"""Unread ranked evidence stays partial; declared filters and empty hits do not."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from datetime import date

import pytest

from nm.brain.retrieval import (
    ATTRIBUTABLE_PARAGRAPHS,
    EMBED_MODEL,
    LEG_DEPTH,
    PER_QUERY_POOL,
    RERANK_MODEL,
    RESULTS_PER_KIND,
    HybridSearcher,
    LocalCollection,
)


class Collection:
    def __init__(self, rows=None, lexical=None, semantic=None):
        self.rows = rows or {}
        self.lexical_hits = list(self.rows) if lexical is None else lexical
        self.semantic_hits = [] if semantic is None else semantic
        self.reranked = []
        self.read_positions = []

    def revision(self):
        return "unchanged-corpus-artifacts"

    def lexical(self, query, depth):
        return deepcopy(self.lexical_hits)

    def semantic(self, query, depth):
        return deepcopy(self.semantic_hits)

    def read(self, positions):
        self.read_positions.extend(positions)
        return {
            position: deepcopy(self.rows[position])
            for position in positions
            if position in self.rows
        }

    def rerank(self, pairs):
        self.reranked.extend(pairs)
        return [1.0 - index / 100 for index, pair in enumerate(pairs)]


def _row(kind, name, **metadata):
    row = {"chunk_id": name, "full_text": f"Exact {name} words.\nSecond line."}
    if kind == "provision":
        row.update(act_name=f"Act {name}", section_number="1")
    else:
        row.update(case_name=f"Case {name}", paragraph_type="reasoning", paragraph_num="1")
    return {**row, **metadata}


def _collections():
    return {
        kind: Collection({0: _row(kind, f"{kind}-peer"), 1: _row(kind, f"{kind}-second")})
        for kind in ("provision", "judgment")
    }


@pytest.mark.parametrize("kind", ["provision", "judgment"])
@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "not_mapping",
        "chunk",
        "text",
        "blank_text",
        "title",
        "blank_title",
    ],
)
def test_unread_ranked_passage_keeps_valid_same_collection_and_other_collection(kind, fault):
    collections = _collections()
    broken = collections[kind]
    if fault == "missing":
        del broken.rows[1]
    elif fault == "not_mapping":
        broken.rows[1] = ["unread row"]
    elif fault == "chunk":
        broken.rows[1]["chunk_id"] = " "
    elif fault == "text":
        broken.rows[1]["full_text"] = ["unread text"]
    elif fault == "blank_text":
        broken.rows[1]["full_text"] = " \n"
    else:
        title = "act_name" if kind == "provision" else "case_name"
        if fault == "title":
            del broken.rows[1][title]
        else:
            broken.rows[1][title] = " "

    result = HybridSearcher(collections).search_subject({}, ("owned enquiry",))

    assert result["state"] == "partial"
    expected = {
        f"{kind}-peer",
        f"{'judgment' if kind == 'provision' else 'provision'}-peer",
        f"{'judgment' if kind == 'provision' else 'provision'}-second",
    }
    assert {row["source_chunk_id"] for row in result["candidates"]} == expected
    assert all(
        row["text"] == f"Exact {row['source_chunk_id']} words.\nSecond line."
        for row in result["candidates"]
    )
    assert broken.reranked == [("owned enquiry", f"Exact {kind}-peer words.\nSecond line.")]
    assert any(
        note.startswith(f"{kind} search could not read attributable passages at positions [1]")
        for note in result["diagnostics"]
    )
    reason = {
        "missing": "missing or malformed passage row",
        "not_mapping": "missing or malformed passage row",
        "chunk": "missing or malformed source chunk ID",
        "text": "missing or malformed exact passage text",
        "blank_text": "missing or malformed exact passage text",
        "title": "missing attributable title or locator",
        "blank_title": "missing attributable title or locator",
    }[fault]
    assert any(reason in note for note in result["diagnostics"])


@pytest.mark.parametrize("leg", ["lexical", "semantic"])
@pytest.mark.parametrize("fault", ["not-a-position", None, True, 1.5, -1, ["nested"]])
def test_malformed_rank_entry_cannot_erase_valid_positions_or_other_collection(leg, fault):
    collections = _collections()
    broken = collections["provision"]
    setattr(broken, f"{leg}_hits", [0, fault, 1])

    result = HybridSearcher(collections).search_subject({}, ("owned enquiry",))

    assert result["state"] == "partial"
    assert {row["source_chunk_id"] for row in result["candidates"]} == {
        "provision-peer",
        "provision-second",
        "judgment-peer",
        "judgment-second",
    }
    assert broken.read_positions == [0, 1]
    assert "provision search returned 1 malformed ranked positions" in result["diagnostics"]


def test_read_gap_below_output_limit_still_marks_search_partial():
    sections = Collection(
        {position: _row("provision", f"section-{position}") for position in range(8)}
    )
    del sections.rows[7]["act_name"]

    result = HybridSearcher({"provision": sections, "judgment": Collection()}).search_subject(
        {}, ("owned enquiry",)
    )

    assert result["state"] == "partial"
    assert len(result["candidates"]) == RESULTS_PER_KIND
    assert len(sections.reranked) == 7
    assert any(
        note.startswith("provision search could not read attributable passages at positions [7]")
        for note in result["diagnostics"]
    )


def test_complete_empty_rankings_are_ok_without_invented_sources_or_read_gaps():
    result = HybridSearcher({"provision": Collection(), "judgment": Collection()}).search_subject(
        {}, ("owned enquiry",), jurisdiction="Requested forum"
    )

    assert result["state"] == "ok"
    assert result["candidates"] == []
    assert not any(
        "could not read" in note or "malformed" in note for note in result["diagnostics"]
    )


def test_declared_role_and_year_filters_do_not_turn_excluded_passages_into_read_gaps():
    judgments = Collection(
        {
            0: _row("judgment", "held", year="2020"),
            1: _row("judgment", "party", paragraph_type="arguments", case_name=""),
            2: _row("judgment", "later", paragraph_type="order", year="2030", case_name=""),
        }
    )

    result = HybridSearcher({"provision": Collection(), "judgment": judgments}).search_subject(
        {}, ("owned enquiry",), as_of=date(2026, 10, 6)
    )

    assert result["state"] == "ok"
    assert [row["source_chunk_id"] for row in result["candidates"]] == ["held"]
    assert "judgment search excluded 2 non-attributable or later passages" in result["diagnostics"]
    assert not any("could not read" in note for note in result["diagnostics"])


@pytest.mark.parametrize("role", [None, "", " ", 7, ["reasoning"], {"role": "reasoning"}])
def test_unknown_paragraph_role_is_unread_and_retains_readable_peers(role):
    collections = _collections()
    if role is None:
        del collections["judgment"].rows[1]["paragraph_type"]
    else:
        collections["judgment"].rows[1]["paragraph_type"] = role

    result = HybridSearcher(collections).search_subject({}, ("owned enquiry",))

    assert result["state"] == "partial"
    assert {row["source_chunk_id"] for row in result["candidates"]} == {
        "provision-peer",
        "provision-second",
        "judgment-peer",
    }
    assert any(
        "positions [1]" in note and "missing or malformed paragraph role" in note
        for note in result["diagnostics"]
    )
    assert not any("excluded" in note for note in result["diagnostics"])


def test_known_excluded_role_is_complete_without_currency_or_title_requirements():
    judgments = Collection({0: {"paragraph_type": "arguments"}})

    result = HybridSearcher({"provision": Collection(), "judgment": judgments}).search_subject(
        {}, ("owned enquiry",), as_of=date(2026, 10, 6)
    )

    assert result["state"] == "ok"
    assert result["candidates"] == []
    assert "judgment search excluded 1 non-attributable or later passages" in result["diagnostics"]
    assert not any("could not read" in note for note in result["diagnostics"])


@pytest.mark.parametrize("kind", ["provision", "judgment"])
def test_source_date_and_jurisdiction_remain_exact_and_separate_from_requested_scope(kind):
    collections = _collections()
    original = _row(
        kind,
        "metadata",
        date=" 2020-07-09 ",
        year="2020",
        jurisdiction=" Source jurisdiction — unassessed ",
    )
    collections[kind] = Collection({0: original})
    before = deepcopy(original)

    result = HybridSearcher(collections).search_subject(
        {}, ("owned enquiry",), jurisdiction="Different requested forum"
    )

    candidate = next(row for row in result["candidates"] if row["source_chunk_id"] == "metadata")
    assert result["state"] == "ok"
    assert result["requested_jurisdiction"] == "Different requested forum"
    assert candidate["date"] == before["date"]
    assert candidate["jurisdiction"] == before["jurisdiction"]
    assert candidate["text"] == before["full_text"]
    assert original == before
    assert not {"governing", "binding", "binding_for", "in_force"}.intersection(candidate)


@pytest.mark.parametrize(
    "jurisdiction",
    [
        ["Original territory", "Another territory"],
        {"territories": ["Original territory"], "scope": {"status": "unassessed"}},
    ],
)
def test_structured_source_jurisdiction_is_preserved_without_aliasing_or_applicability_claim(
    jurisdiction,
):
    source = _row("provision", "structured", jurisdiction=jurisdiction)
    collection = Collection({0: source})
    collection.read = lambda positions: {
        position: collection.rows[position] for position in positions
    }
    result = HybridSearcher({"provision": collection, "judgment": Collection()}).search_subject(
        {}, ("owned enquiry",), jurisdiction="Requested forum"
    )

    assert result["state"] == "ok"
    candidate = result["candidates"][0]
    assert candidate["jurisdiction"] == jurisdiction
    assert candidate["jurisdiction"] is not jurisdiction
    assert result["requested_jurisdiction"] == "Requested forum"
    assert not {"governing", "binding", "binding_for", "in_force"}.intersection(candidate)
    json.dumps(result)
    if isinstance(candidate["jurisdiction"], list):
        candidate["jurisdiction"].append("Downstream-only mutation")
        assert jurisdiction == ["Original territory", "Another territory"]
    else:
        candidate["jurisdiction"]["scope"]["status"] = "Downstream-only mutation"
        assert jurisdiction["scope"]["status"] == "unassessed"


@pytest.mark.parametrize("metadata,expected_date", [({}, ""), ({"year": "2019"}, "2019")])
def test_missing_currency_metadata_and_year_only_sources_remain_readable(metadata, expected_date):
    collections = {
        kind: Collection({0: _row(kind, kind, **metadata)}) for kind in ("provision", "judgment")
    }

    result = HybridSearcher(collections).search_subject(
        {}, ("owned enquiry",), jurisdiction="Requested forum", as_of=date(2026, 10, 6)
    )

    assert result["state"] == "ok"
    assert len(result["candidates"]) == 2
    assert all(
        row["date"] == expected_date and row.get("jurisdiction", "") == ""
        for row in result["candidates"]
    )


@pytest.mark.parametrize("blob", ["null", "[]", "42", '"unread"', "not-json"])
def test_malformed_stored_blob_retains_readable_local_peer_and_marks_gap(
    tmp_path, monkeypatch, blob
):
    database = tmp_path / "chunks.db"
    good = _row("provision", "stored-peer")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table chunks (pos integer, doc_type text, chunk_id text, blob text)"
        )
        connection.executemany(
            "insert into chunks values (?, ?, ?, ?)",
            [
                (0, "bare_act", "stored-peer", json.dumps(good)),
                (1, "bare_act", "unread", blob),
            ],
        )
    local = LocalCollection(
        corpus_dir=tmp_path, lineage=tmp_path / "unused.json", doc_type="bare_act", models=None
    )
    monkeypatch.setattr(local, "_open", lambda: (None, None, database, 2))
    sections = Collection({0: good}, lexical=[0, 1])
    sections.read = local.read

    result = HybridSearcher({"provision": sections, "judgment": Collection()}).search_subject(
        {}, ("owned enquiry",)
    )

    assert result["state"] == "partial"
    assert [row["source_chunk_id"] for row in result["candidates"]] == ["stored-peer"]
    assert result["candidates"][0]["text"] == good["full_text"]
    assert any(
        note.startswith("provision search could not read attributable passages at positions [1]")
        for note in result["diagnostics"]
    )


def test_requested_scope_is_retained_even_when_no_search_can_run():
    result = HybridSearcher({}).search_subject({}, (), jurisdiction="Requested forum")

    assert result["state"] == "unavailable"
    assert result["requested_jurisdiction"] == "Requested forum"
    assert result["candidates"] == []


def test_changed_read_contract_cannot_reuse_a_previous_revision_with_unchanged_corpora():
    searcher = HybridSearcher(_collections())
    old_identity = {
        "collections": {kind: "unchanged-corpus-artifacts" for kind in ("provision", "judgment")},
        "contract": "hybrid_passage_v2",
        "embedding": EMBED_MODEL,
        "reranking": RERANK_MODEL,
        "depth": LEG_DEPTH,
        "pool": PER_QUERY_POOL,
        "per_kind": RESULTS_PER_KIND,
        "judgment_roles": sorted(ATTRIBUTABLE_PARAGRAPHS),
    }
    old_revision = hashlib.sha256(json.dumps(old_identity, sort_keys=True).encode()).hexdigest()

    assert searcher.revision() is not None
    assert searcher.revision() != old_revision
    assert searcher.revision() == searcher.revision()
