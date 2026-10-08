"""Ranked source identity and original parent/child context across the shipped boundary."""
from copy import deepcopy
import json
import sqlite3

import pytest

from nm.brain import retrieval as R
from nm.brain.turn import saved_rows
from tests.test_current_brain_app import Harness, MIXED_MESSAGE, WiredModel, assert_ok, mixed_outputs
from tests.test_current_brain_research_turn import plan
from tests.test_current_brain_retrieval import Collection, QUERIES


def source(identity, text, parent="", section="4", act="act"):
    return {"doc_type": "bare_act", "chunk_id": identity, "act_id": act,
            "act_name": "Source Act", "section_number": section,
            "parent_chunk_id": parent, "full_text": text}


def collection(tmp_path, rows=None, hits=None):
    rows = rows or {
        0: source("root", "This section governs records of registered associations.\n"
                  "A member may request copies, subject to confidentiality."),
        1: source("child", "A member may request copies.", "root"),
        2: source("peer", "Independent duties concerning a returned deposit.", section="5"),
    }
    database = tmp_path / "parents.db"
    with sqlite3.connect(database) as db:
        db.execute("create table chunks(doc_type text,pos integer,chunk_id text,act_id text,section_number text,blob text)")
        db.executemany("insert into chunks values (?,?,?,?,?,?)", [
            ("bare_act", p, r["chunk_id"], r["act_id"], r["section_number"], json.dumps(r))
            for p, r in rows.items()])
    result = R.LocalCollection(corpus_dir=tmp_path, lineage=tmp_path / "unused",
                               doc_type="bare_act", models=None)
    result._open = lambda: ({}, database, max(rows) + 1)
    result.revision = lambda: "fixed-corpus"
    result.lexical = lambda query, depth: hits or [1, 2]
    result.semantic = lambda query, depth: hits or [1, 2]
    result.pairs = []
    result.rerank = lambda pairs: result.pairs.extend(pairs) or [0.5] * len(pairs)
    return result


def search(value):
    result = R.HybridSearcher({"provision": value, "judgment": Collection("judgment")}).search(QUERIES)
    return R.validate_search(result, QUERIES)


def test_score_and_return_the_same_root_retaining_original_child_words(tmp_path):
    c = collection(tmp_path)
    result = search(c)
    root = next(x for x in result["candidates"] if x["kind"] == "provision" and x["position"] == 0)
    assert result["state"] == "ready" and result["contract"] == "hybrid_retrieval_v2"
    assert c.pairs[0][1] == "Source Act\n" + root["text"]
    assert "subject to confidentiality" in root["text"]
    assert root["context"]["scope"] == "exact_parent_tree"
    assert [s["position"] for s in root["context"]["segments"]] == [0, 1]
    assert not any(x["kind"] == "provision" and x["position"] == 1 for x in result["candidates"])


@pytest.mark.parametrize("first_hits", [[2, 0], [0, 2]])
def test_shared_ancestors_rank_once_and_preserve_every_query_and_fragment(tmp_path, first_hits):
    rows = {0: source("root", "Whole section and qualifications."),
            1: source("middle", "Intermediate heading.", "root"),
            2: source("first", "First original condition.", "middle"),
            3: source("second", "Other original condition absent from the stored root.", "root")}
    c = collection(tmp_path, rows, [0, 2, 3])
    c.lexical = c.semantic = lambda query, depth: first_hits if query == QUERIES[0]["text"] else [3]
    result = search(c)
    roots = [x for x in result["candidates"] if x["kind"] == "provision"]
    assert len(c.pairs) == len(roots) == 1
    assert set(roots[0]["query_ids"]) == {q["query_id"] for q in QUERIES}
    assert {s["position"] for s in roots[0]["context"]["segments"]} == set(rows)
    assert next(s["row"] for s in roots[0]["context"]["segments"] if s["position"] == 3) == rows[3]


@pytest.mark.parametrize("damage", ["missing", "ambiguous", "foreign_section", "foreign_act", "cycle", "unread"])
def test_bad_parent_is_unranked_and_readable_independent_work_survives(tmp_path, damage):
    rows = {0: source("root", "Parent scope."), 1: source("child", "Child text.", "root"),
            2: source("peer", "Independent readable source.", section="5")}
    if damage == "missing": rows[0]["chunk_id"] = "unrelated"
    elif damage == "ambiguous": rows[3] = deepcopy(rows[0])
    elif damage == "foreign_section": rows[0]["section_number"] = "99"
    elif damage == "foreign_act": rows[0]["act_id"] = "other"
    elif damage == "cycle": rows[0]["parent_chunk_id"] = "child"
    elif damage == "unread": rows[0]["full_text"] = ""
    c = collection(tmp_path, rows)
    result = search(c)
    assert result["state"] == "partial"
    provisions = [x for x in result["candidates"] if x["kind"] == "provision"]
    assert [x["position"] for x in provisions] == [2, 1]
    assert provisions[-1]["score"] is None
    assert provisions[-1]["context"]["bounded"] is True
    assert len(provisions[-1]["context"]["segments"]) == 1
    assert c.pairs == [(c.pairs[0][0], "Source Act\nIndependent readable source.")]
    assert any(i["stage"] == "context" and i.get("position") == 1 for i in result["issues"])


def test_long_root_is_not_replaced_by_a_matching_child_or_truncated_before_rank(tmp_path):
    text = "Only registered bodies.\n" + "Other original content.\n" * 800 + "Final exception applies."
    c = collection(tmp_path, {0: source("root", text),
                             1: source("child", "Short attractive clause.", "root")}, [1])
    root = next(x for x in search(c)["candidates"] if x["kind"] == "provision")
    assert c.pairs[0][1] == "Source Act\n" + text
    assert root["text"] == text and root["context"]["segments"][-1]["row"]["full_text"] == "Short attractive clause."


@pytest.mark.parametrize("damage", ["detached", "cycle", "legacy", "duplicate_position"])
def test_replay_checks_parent_ownership_not_just_self_consistent_digests(tmp_path, damage):
    result = search(collection(tmp_path))
    candidate = next(x for x in result["candidates"] if x["context"]["scope"] == "exact_parent_tree")
    context = candidate["context"]
    if damage in ("detached", "cycle"):
        child = context["segments"][-1]
        child["row"]["parent_chunk_id"] = "absent" if damage == "detached" else child["row"]["chunk_id"]
        child["content_digest"] = R._digest(child["row"])
    elif damage == "duplicate_position": context["segments"].append(deepcopy(context["segments"][-1]))
    else: result["contract"] = "hybrid_retrieval_v1"
    candidate["context_digest"] = R._digest(context)
    with pytest.raises(ValueError): R.validate_search(result, QUERIES)


def test_duplicate_leaf_names_do_not_create_an_ambiguous_parent_reference(tmp_path):
    c = collection(tmp_path, {0: source("root", "Complete parent."),
                             1: source("child", "First stored wording.", "root"),
                             2: source("child", "Second stored wording.", "root")}, [1, 2])
    result = search(c)
    assert result["state"] == "ready"
    assert len(next(x for x in result["candidates"] if x["kind"] == "provision")["context"]["segments"]) == 3


def test_v1_snapshot_replays_unchanged_without_new_parent_reads():
    result = R.HybridSearcher({"provision": Collection(), "judgment": Collection("judgment")}).search(QUERIES)
    result["contract"] = "hybrid_retrieval_v1"
    assert R.validate_search(result, QUERIES) == result


def test_authenticated_turn_saves_parent_sources_and_reopens_without_extra_calls(tmp_path):
    c = collection(tmp_path)
    model = WiredModel(*mixed_outputs(MIXED_MESSAGE), plan())
    app = Harness(tmp_path, model)
    app.application.legal_search = R.HybridSearcher({"provision": c, "judgment": Collection("judgment")})
    try:
        result = assert_ok(app.post(MIXED_MESSAGE))
        assert result["metrics"]["llm_calls"] == 4
        saved = saved_rows(app.held(result["chat_id"]), "adv_wiring")[0]
        research = saved["research"]["searches"]["dispute:1"]
        root = next(x for x in research["candidates"] if x["kind"] == "provision" and x["position"] == 0)
        assert root["context"]["scope"] == "exact_parent_tree"
        reopened = assert_ok(app.client.get("/api/chats/" + result["chat_id"]))
        assert reopened["turns"][0]["elements"] == result["elements"]
        assert "research" not in result
        assert assert_ok(app.post(MIXED_MESSAGE))["replayed"] is True
        assert len(model.calls) == 4
    finally:
        app.client.close()
