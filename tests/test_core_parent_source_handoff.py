"""Parent-store passages retain ownership through the served answer boundary.

Synthetic ranking and review decisions exercise wiring, never legal accuracy.
The actual local reader, source catalogue, authority check, storage and replay run.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest

from nm.core_engine import answer_sources, research, response_authorities
from nm.core_engine import response_writer, turn
from nm.core_engine.conversation import chat_matter_id
from nm.core_engine.retrieval import HybridSearcher, validate_search
from tests.test_core_answer_sources import fixture
from tests.test_core_research import work
from tests.test_core_response_writer import source_use_v2, unit
from tests.test_core_served import OWNER, served, source_url, successful
from tests.test_core_statute_readback import _local, _row
from tests.test_core_understanding import context
from tests.test_current_brain_retrieval import Collection


pytestmark = pytest.mark.class_a


def _parent_collection(tmp_path, monkeypatch):
    folder = tmp_path / "parent-handoff-corpus"
    folder.mkdir()
    parent = _row("synthetic-act", "4",
        "  A custodian must return the article.\n"
        "Except where the stated authority permits retention.  ",
        chunk_id="synthetic-act:section:4")
    child = _row("synthetic-act", "4",
        "Except where the stated authority permits retention.",
        chunk_id="synthetic-act:section:4:exception", parent=parent["chunk_id"])
    child["atom_type"] = "sub_section"
    collection = _local(folder, [child])
    raw = json.dumps({parent["chunk_id"]: parent}, ensure_ascii=False).encode("utf-8")
    (folder / "parents.json").write_bytes(raw)
    manifest = json.loads(collection.lineage.read_text(encoding="utf-8"))
    manifest["context_store"] = {"path": "parents.json", "format": "parent_map_v1",
        "sha256": hashlib.sha256(raw).hexdigest()}
    collection.lineage.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(collection, "lexical", lambda query, depth: [0])
    monkeypatch.setattr(collection, "semantic", lambda query, depth: [0])
    monkeypatch.setattr(collection, "semantic_many", lambda queries, depth: [[0] for _ in queries])
    monkeypatch.setattr(collection, "rerank", lambda pairs, *, anchors=None: [1.0] * len(pairs))
    return collection, parent, child


def _research(tmp_path, monkeypatch):
    collection, parent, child = _parent_collection(tmp_path, monkeypatch)
    ctx = context("Find the applicable law.")
    plan = research.accept({"work": [work()]}, ctx)
    searcher = HybridSearcher({"provision": collection, "judgment": Collection("judgment")})
    record = research.retrieve(plan, searcher, ctx)
    assert not record["failures"], record["failures"]
    assert research.validate(record, plan, ctx) == record
    return ctx, record, collection, parent, child


def _parent_source(sources, parent):
    return next(s for s in sources.values()
                if s["source_identity"].get("position") == "parent:" + parent["chunk_id"])


def test_parent_and_child_are_exact_selectable_sources_after_research_validation(tmp_path, monkeypatch):
    ctx, record, _, parent, child = _research(tmp_path, monkeypatch)
    before = deepcopy(record)
    sources = answer_sources.build(ctx, record)
    root = _parent_source(sources, parent)
    leaf = next(s for s in sources.values() if s["kind"] == "provision"
                and s["source_identity"]["position"] == 0)

    assert root["text"] == parent["full_text"]
    assert leaf["text"] == child["full_text"]
    assert root["id"] != leaf["id"]
    assert root["source_identity"]["act_id"] == leaf["source_identity"]["act_id"] == "synthetic-act"
    assert root["context_ids"] == [leaf["id"]]
    assert leaf["context_ids"] == [root["id"]]
    assert root["work_ids"] == leaf["work_ids"] == ["t2:w1"]
    assert not any(c["bounded"] or c["unread_positions"] for c in root["coverage"])
    assert answer_sources.select({"source_id": root["id"], "quote": None}, sources)["text"] == parent["full_text"]
    shown = answer_sources.presentation(sources)
    assert {s["id"]: s["text"] for s in shown["passages"]}[root["id"]] == parent["full_text"]
    assert record == before


def test_owned_provision_readback_includes_the_real_parent_store_source(tmp_path, monkeypatch):
    _, record, collection, parent, child = _research(tmp_path, monkeypatch)
    selected = next(s for search in record["searches"].values()
                    for s in search["candidates"] if s["kind"] == "provision")
    readback = collection.read_provision("synthetic-act", "section 4")

    assert readback["state"] == "found", readback
    by_location = {s["position"]: s for s in readback["sources"]}
    assert set(by_location) == {0, "parent:" + parent["chunk_id"]}
    assert by_location[0]["text"] == child["full_text"]
    root = by_location["parent:" + parent["chunk_id"]]
    assert root["id"] == selected["id"] and root["text"] == parent["full_text"]
    assert {s["position"] for s in root["context"]["segments"]} == set(by_location)
    assert readback["legal_version"] == "not_assessed"


def test_parent_source_matches_authority_readback_without_an_invented_vector_position(tmp_path, monkeypatch):
    ctx, record, collection, parent, _ = _research(tmp_path, monkeypatch)
    sources = answer_sources.build(ctx, record)
    source = _parent_source(sources, parent)
    draft = response_writer.accept({"units": [unit(sources, kind="law",
        text=parent["full_text"], uses=[source_use_v2(source)])]}, ctx, sources)
    evidence = response_authorities.check(ctx, record, sources, draft, provision_reader=collection)

    checked = evidence["units"][0]["selected_provisions"][0]
    assert checked["state"] == "matched"
    assert checked["position"] == "parent:" + parent["chunk_id"]
    assert checked["source_id"] == source["id"]
    assert checked["legal_version"] == "not_assessed"

    def no_lookup(*args, **kwargs):
        raise AssertionError("Replay must use its saved parent source, not reload the corpus")

    monkeypatch.setattr(collection, "read_provision", no_lookup)
    assert response_authorities.validate(evidence, ctx, record, sources, draft) == evidence


@pytest.mark.parametrize("version", ["hybrid_retrieval_v1", "hybrid_retrieval_v2", "hybrid_retrieval_v3"])
def test_legacy_snapshots_cannot_acquire_parent_locators_but_keep_their_numeric_projection(
    tmp_path, monkeypatch, version,
):
    ctx, old_record = fixture()
    for search in old_record["searches"].values():
        search["contract"] = version
    original = deepcopy(old_record)
    catalogue = answer_sources.build(ctx, old_record)
    assert research.validate(old_record, old_record["plan"], ctx) == original
    assert answer_sources.build(ctx, original) == catalogue
    assert all(type(s["source_identity"]["position"]) is int
               for s in catalogue.values() if s["kind"] in {"provision", "judgment"})

    _, new_record, _, _, _ = _research(tmp_path, monkeypatch)
    search = deepcopy(next(iter(new_record["searches"].values())))
    search["contract"] = version
    with pytest.raises(ValueError):
        validate_search(search, search["queries"])


def test_parent_source_is_saved_served_and_replayed_without_fresh_law_or_model_calls(
    served, tmp_path, monkeypatch,
):
    collection, parent, child = _parent_collection(tmp_path, monkeypatch)
    served.app.legal_search.collections["provision"] = collection
    original = served.model.structured

    def write_parent(prompt, *args, **kwargs):
        result = original(prompt, *args, **kwargs)
        if prompt.operation != "core_response_writer":
            return result
        data = json.loads(prompt.user)
        source = next(s for s in data["held_passages"]["passages"]
                      if s["source_identity"].get("position") == "parent:" + parent["chunk_id"])
        proposal = deepcopy(result.data)
        proposal["units"][0].update(kind="law", text=source["text"],
                                  uses=[source_use_v2(source)])
        return replace(result, data=proposal)

    monkeypatch.setattr(served.model, "structured", write_parent)
    reply = successful(served, message="Find the applicable law.")
    assert reply["metrics"]["llm_calls"] == 4 and len(served.model.calls) == 4
    source = reply["elements"][0]["source"]
    assert source["text"] == parent["full_text"]
    for operation, payload in served.model.calls:
        if operation not in {"core_response_writer", "core_response_review"}:
            continue
        catalogue = payload["held_passages" if operation == "core_response_writer" else "legal_sources"]
        texts = {s["text"] for s in catalogue["passages"]}
        assert parent["full_text"] in texts and child["full_text"] in texts

    stored = served.store.load(chat_matter_id(OWNER, reply["chat_id"]))
    before = deepcopy(stored)
    assert turn.saved_rows(stored, OWNER)[0]["response"] == reply

    def no_lookup(*args, **kwargs):
        raise AssertionError("Source reopening cannot perform a new corpus or authority check")

    monkeypatch.setattr(collection, "read_provision", no_lookup)
    monkeypatch.setattr(served.app.legal_search, "search", no_lookup)
    monkeypatch.setattr(response_authorities, "check", no_lookup)
    reopened = served.client.get(f"/api/chats/{reply['chat_id']}")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["turns"][0]["elements"] == reply["elements"]
    pane = served.client.get(source_url(reply))
    assert pane.status_code == 200, pane.text
    shown = pane.json()
    inspection = shown.pop("authority_inspection")
    assert shown == source
    assert inspection["provision_checks"][0]["state"] == "matched"
    assert inspection["provision_checks"][0]["position"] == "parent:" + parent["chunk_id"]
    replay = successful(served, message="Find the applicable law.", expected_version=0)
    assert replay == {**reply, "replayed": True}
    assert len(served.model.calls) == 4 and served.store.load(stored.id) == before
