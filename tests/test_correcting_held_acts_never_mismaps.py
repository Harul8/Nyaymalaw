"""Correcting Acts the store holds never maps a vector onto the wrong passage (plan AN.32; owner, 5 Nov 2026: "do 2"). The job,
pipeline/correct_held_acts.py, puts an Act's passages as the build reads it now in place of those held - more or fewer of them
- and the owner runs it. Vector n is passage n after it, as before; the positions run on without a gap; every other passage keeps
its words and its vector; the word index is rebuilt over every passage in order; the lineage record agrees and says what was
corrected; the earlier members are kept beside the new ones. A refusal, or a dry run, changes nothing. Invented Acts."""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from nm.Archives.legal_brain.retrieve import hybrid_sections as hybrid
from pipeline import correct_held_acts as job
from pipeline.append_bare_acts import Store
from tests.test_appending_bare_acts_never_mismaps import _BM25, _encode, _vector

pytestmark = pytest.mark.class_a


def _row(act, section, words, atom="section_head", parent=None, mark=None):
    chunk_id = f"{act}_SECTION_{section}" + ("" if atom == "section_head" else f"_{atom}")
    blob = {"chunk_id": chunk_id, "doc_type": "bare_act", "act_id": act, "section_number": section, "atom_type": atom,
            "parent_chunk_id": parent or "", "full_text": f"{act} s.{section}: {words}"}
    if mark:
        blob["standing"] = mark
    return {"chunk_id": chunk_id, "parent_chunk_id": parent, "atom_type": atom, "section_number": section, "blob": blob}


HELD = {"ACT_A": [_row("ACT_A", "1", "Short title."), _row("ACT_A", "2", "Definitions.")],
        "ACT_B": [_row("ACT_B", "1", "Short title."), _row("ACT_B", "3", "Repeal of Act."), _row("ACT_B", "4", "Savings.")],
        "ACT_C": [_row("ACT_C", "1", "Short title.", mark="not in force"), _row("ACT_C", "2", "Penalty.", mark="not in force")]}


def _library(tmp_path):
    """Three Acts held one after another - A at 0-1, B at 2-4, C at 5-6 - with their records and a lineage that agrees."""
    import faiss

    store = tmp_path / "store"
    store.mkdir()
    rows = [row for act in HELD.values() for row in act]
    index = faiss.IndexFlatIP(hybrid.DIMENSIONS)
    index.add(_encode([row["blob"]["full_text"] for row in rows]))
    faiss.write_index(index, str(store / "bare.index"))
    (store / "bm25").mkdir()
    params = store / "bm25" / "params.index.json"
    params.write_text(json.dumps({"num_docs": len(rows)}))
    with sqlite3.connect(store / "chunks.db") as con:
        con.execute("create table chunks (doc_type text, pos integer, chunk_id text, act_id text, case_id text, "
                    "parent_chunk_id text, atom_type text, section_number text, blob text, primary key (doc_type, pos))")
        con.execute("create table acts (act_id text primary key, record text)")
        for pos, row in enumerate(rows):
            con.execute("insert into chunks values ('bare_act', ?, ?, ?, null, ?, ?, ?, ?)",
                        (pos, row["chunk_id"], row["blob"]["act_id"], row["parent_chunk_id"], row["atom_type"],
                         row["section_number"], json.dumps(row["blob"])))
        for act, held in HELD.items():
            con.execute("insert into acts values (?, ?)", (act, json.dumps({"act_id": act, "sections": len(held),
                                                                           "passages": len(held)})))
    con.close()
    record = {"schema": 1, "doc_type": "bare_act", "model": hybrid.EMBED_MODEL, "dimensions": hybrid.DIMENSIONS,
              "passages": len(rows),
              "vector_index": {"path": "bare.index", "vectors": len(rows), "bytes": (store / "bare.index").stat().st_size},
              "bm25": {"path": "bm25", "num_docs": len(rows), "params_sha256": hashlib.sha256(params.read_bytes()).hexdigest()},
              "passage_store": {"path": "chunks.db", "count": len(rows), "max_pos": len(rows) - 1}}
    lineage = tmp_path / "lineage.json"
    lineage.write_text(json.dumps(record))
    assert hybrid.check_lineage(record, store) == []
    return Store(store, lineage)


def _held(store):
    with sqlite3.connect(store.vector_store / "chunks.db") as con:
        rows = con.execute("select pos, chunk_id, act_id, blob from chunks order by pos").fetchall()
        acts = {act: json.loads(record) for act, record in con.execute("select act_id, record from acts")}
    con.close()
    return rows, acts


def _state(store):
    rows, acts = _held(store)
    return (rows, acts, (store.vector_store / "bare.index").read_bytes(), store.lineage.read_text(),
            sorted(path.name for path in store.vector_store.iterdir()))


def _corrected_b():
    return [_row("ACT_B", "1", "Short title."), _row("ACT_B", "2", "Repeal of Act."), _row("ACT_B", "3", "Savings."),
            _row("ACT_B", "4", "Abatement of legal proceedings.")]


def test_after_a_correction_vector_n_is_still_passage_n_and_every_other_passage_is_as_it_was(tmp_path):
    import faiss

    store = _library(tmp_path)
    bm25 = _BM25()
    summary = job.correct({"ACT_B": _corrected_b()}, store, encode=_encode, build_bm25=bm25)
    assert summary["passages"] == 8 and summary["acts"]["ACT_B"]["sections_held"] == ["1", "3", "4"]
    assert summary["acts"]["ACT_B"]["sections_now"] == ["1", "2", "3", "4"] and summary["acts"]["ACT_B"]["unchanged"] == 1
    rows, acts = _held(store)
    assert [pos for pos, _, _, _ in rows] == list(range(8)), "positions have a gap"
    assert [chunk for _, chunk, _, _ in rows] == [
        "ACT_A_SECTION_1", "ACT_A_SECTION_2", "ACT_B_SECTION_1", "ACT_B_SECTION_2", "ACT_B_SECTION_3", "ACT_B_SECTION_4",
        "ACT_C_SECTION_1", "ACT_C_SECTION_2"], "the Act's passages are in its place, every later one moved by the difference"
    assert json.loads(rows[6][3])["standing"] == "not in force", "a later Act's passages keep their words and marks"
    index = faiss.read_index(str(store.vector_store / "bare.index"))
    for pos, _, _, blob in rows:
        assert float(index.reconstruct(pos) @ _vector(json.loads(blob)["full_text"])) > 0.999, f"vector {pos} is not passage {pos}'s"
    assert bm25.tokens == [hybrid.bm25_tokens(json.loads(blob)["full_text"]) for _, _, _, blob in rows]
    assert acts["ACT_B"]["passages"] == 4 and acts["ACT_B"]["sections"] == 4
    assert acts["ACT_B"]["corrected"][0]["sections_held"] == ["1", "3", "4"] and acts["ACT_A"] == {
        "act_id": "ACT_A", "sections": 2, "passages": 2}
    record = json.loads(store.lineage.read_text())
    assert record["passages"] == 8 and record["passage_store"] == {"path": "chunks.db", "count": 8, "max_pos": 7}
    assert record["corrected"][0]["acts"]["ACT_B"]["now"] == 4
    assert hybrid.check_lineage(record, store.vector_store) == [], "the corrected set does not agree"
    names = [path.name for path in store.vector_store.iterdir()]
    assert all(any(name.startswith(f"{member}.before-") for name in names) for member in ("chunks.db", "bare.index", "bm25"))


def test_two_acts_corrected_at_once_one_shorter_one_longer(tmp_path):
    import faiss

    store = _library(tmp_path)
    shorter = [_row("ACT_A", "1", "Short title and definitions.")]
    longer = [*HELD["ACT_C"], _row("ACT_C", "3", "Repeal.")]
    for row in longer:
        row["blob"].pop("standing", None)
    job.correct({"ACT_C": longer, "ACT_A": shorter}, store, encode=_encode, build_bm25=_BM25())
    rows, _ = _held(store)
    assert [chunk for _, chunk, _, _ in rows] == [
        "ACT_A_SECTION_1", "ACT_B_SECTION_1", "ACT_B_SECTION_3", "ACT_B_SECTION_4", "ACT_C_SECTION_1", "ACT_C_SECTION_2",
        "ACT_C_SECTION_3"]
    assert json.loads(rows[6][3])["standing"] == "not in force", "the Act's own mark is given to its passages as held"
    index = faiss.read_index(str(store.vector_store / "bare.index"))
    assert index.ntotal == 7 and all(float(index.reconstruct(pos) @ _vector(json.loads(blob)["full_text"])) > 0.999
                                     for pos, _, _, blob in rows)


def test_a_dry_run_changes_nothing_and_says_what_would_change(tmp_path):
    store = _library(tmp_path)
    before = _state(store)
    summary = job.correct({"ACT_B": _corrected_b()}, store, encode=_encode, build_bm25=_BM25(), dry_run=True)
    assert summary["dry_run"] and summary["passages"] == 8 and summary["acts"]["ACT_B"]["sections_now"] == ["1", "2", "3", "4"]
    assert _state(store) == before


@pytest.mark.parametrize("why, given, refused", [
    ("not held", {"ACT_Z": [_row("ACT_Z", "1", "Short title.")]}, "not held in one run"),
    ("another Act's passage", {"ACT_B": [_row("ACT_A", "1", "Short title.")]}, "name another Act"),
    ("a repeated identifier", {"ACT_B": [_row("ACT_B", "1", "One."), _row("ACT_B", "1", "Two.")]}, "repeat an identifier"),
])
def test_what_cannot_be_put_in_place_is_refused_and_nothing_changes(tmp_path, why, given, refused):
    store = _library(tmp_path)
    before = _state(store)
    with pytest.raises(RuntimeError, match=refused):
        job.correct(given, store, encode=_encode, build_bm25=_BM25())
    assert _state(store) == before, why


def test_a_set_that_does_not_agree_or_a_short_word_index_is_refused_and_nothing_changes(tmp_path):
    store = _library(tmp_path)
    before = _state(store)
    with pytest.raises(RuntimeError, match="does not hold every passage"):
        job.correct({"ACT_B": _corrected_b()}, store, encode=_encode, build_bm25=_BM25(short=True))
    assert _state(store) == before, "a refused correction left a passage, a file or a record"
    (store.vector_store / "bm25" / "params.index.json").write_text(json.dumps({"num_docs": 9}))
    before = _state(store)
    with pytest.raises(RuntimeError, match="not consistent"):
        job.correct({"ACT_B": _corrected_b()}, store, encode=_encode, build_bm25=_BM25())
    assert _state(store) == before
