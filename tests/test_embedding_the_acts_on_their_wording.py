"""The Acts are embedded on their own wording (plan AN.45, D91 and D106; owner, 5 Nov 2026: "labels shouldn't be used for similarity check,
rather it should be the sections wording"). A passage's vector is made from what follows the line that names it; vector n is passage n; the
passages, the word index and the earlier vector file are untouched; the candidate lineage record agrees with the files it names; and the swap
that puts it into the search is refused while the server is up or the files disagree. An invented Act, a stand-in for the model's vectors
(different for every text), and the real word index (bm25s) on a tiny corpus."""
import hashlib
import json
import sqlite3

import numpy as np
import pytest

from nm.Archives.legal_brain.retrieve import hybrid_sections as hybrid
from pipeline import embed_acts_wording as job
from pipeline.build_judgments_v3 import BM25_PARAMS, EMBED_MODEL, Places
from tests.test_appending_bare_acts_never_mismaps import _encode, _vector

pytestmark = pytest.mark.class_a

NAME = "The Imagined Relief Act, 1907"
ROWS = [  # (section, atom, heading, words, clause)
    ("1", "section_head", "Short title.", "1. Short title.\nThis Act may be called the Imagined Relief Act, 1907.", ""),
    ("2", "section_head", "Relief.", "2. Relief.\nThe court may grant relief against forfeiture, on such terms as it thinks fit.", ""),
    ("2", "clause", "Relief.", "(a) where the lessee pays the rent due;", "(a)"),
    ("2", "clause", "Relief.", "(b) where the breach is capable of remedy.", "(b)"),
    ("3", "section_head", "Costs.", "3. Costs.\nCosts follow the event.", ""),
    ("3", "proviso", "Costs.", "Provided that no costs are payable by a minor.", ""),
    ("4", "section_head", "Heading with no words", "", ""),
]


def full(section, heading, words, clause=""):
    return f"{NAME},  — s.{section}{clause}: {heading}" + (f"\n{words}" if words else "")


def library(tmp_path):
    """An invented Act store as the search reads it: passages, vectors made from each whole passage, a word index and the record."""
    import bm25s
    import faiss

    store = tmp_path / "vector_store" / "acts_t"
    store.mkdir(parents=True)
    texts = [full(section, heading, words, clause) for section, _, heading, words, clause in ROWS]
    con = sqlite3.connect(store / "acts_t.db")
    con.execute("create table chunks (doc_type text, pos integer, chunk_id text, act_id text, case_id text, parent_chunk_id text, "
                "atom_type text, section_number text, blob text, primary key (doc_type, pos))")
    for pos, ((section, atom, heading, _, clause), text) in enumerate(zip(ROWS, texts)):
        blob = {"chunk_id": f"A_S{section}_{pos}", "doc_type": "bare_act", "act_id": "A", "act_name": NAME, "section_number": section,
                "section_title": heading, "atom_type": atom, "full_text": text}
        con.execute("insert into chunks values ('bare_act', ?, ?, 'A', null, null, ?, ?, ?)",
                    (pos, blob["chunk_id"], atom, section, json.dumps(blob)))
    con.commit()
    con.close()
    index = faiss.IndexFlatIP(1024)
    index.add(_encode(texts))
    faiss.write_index(index, str(store / "acts_t.index"))
    words = bm25s.BM25(**BM25_PARAMS)
    words.index([text.lower().split() for text in texts], show_progress=False)
    words.save(str(store / "acts_t_bm25s"))
    digest = hashlib.sha256((store / "acts_t_bm25s" / "params.index.json").read_bytes()).hexdigest()
    record = {"schema": 1, "doc_type": "bare_act", "model": EMBED_MODEL, "dimensions": 1024, "passages": len(texts),
              "vector_index": {"path": "acts_t/acts_t.index", "vectors": len(texts), "bytes": (store / "acts_t.index").stat().st_size,
                               "sha256": "earlier"},
              "bm25": {"path": "acts_t/acts_t_bm25s", "num_docs": len(texts), "params_sha256": digest},
              "passage_store": {"path": "acts_t/acts_t.db", "count": len(texts), "max_pos": len(texts) - 1},
              "corrected": [{"acts": {"A": {"held": 7}}}]}
    retrieval = tmp_path / ".nm" / "retrieval"
    retrieval.mkdir(parents=True)
    (retrieval / "bare_acts.lineage.json").write_text(json.dumps(record), encoding="utf-8")
    places = Places(vector_store=tmp_path / "vector_store", retrieval=retrieval, models=tmp_path / "models")
    return places, texts


def test_a_passage_is_embedded_by_what_follows_the_line_that_names_it():
    head = full("5", "Revocation.", "5. Revocation.\nA proposal may be revoked at any time before the acceptance is complete.")
    assert job.wording(head) == "5. Revocation.\nA proposal may be revoked at any time before the acceptance is complete."
    assert job.wording(full("2", "Relief.", "(a) where the lessee pays the rent due;", "(a)")) == "(a) where the lessee pays the rent due;"
    assert job.wording(f"{NAME},  — s.1: Short title.\r\n  1. Short title.\r\nThis Act may be called so. \r\n") == (
        "1. Short title.\r\nThis Act may be called so."), "spaces round it go; the statute's own lines stay"
    only_a_line = full("4", "Heading with no words", "")
    assert job.wording(only_a_line) == only_a_line, "a passage that is only its line is embedded whole"
    assert job.wording("") == ""


def test_every_passage_is_embedded_on_its_wording_in_its_own_position_and_nothing_else_is_touched(tmp_path):
    import faiss

    places, texts = library(tmp_path)
    before = {name: (places.vector_store / "acts_t" / name).read_bytes() for name in ("acts_t.db", "acts_t.index")}
    live_before = (places.retrieval / "bare_acts.lineage.json").read_bytes()
    result = job.index_stage(places, _encode)
    assert result["lineage_problems"] == [] and result["passages"] == len(texts)
    index = faiss.read_index(str(places.vector_store / "acts_t" / "acts_t_wording.index"))
    assert index.ntotal == len(texts)
    for pos, text in enumerate(texts):
        assert float(index.reconstruct(pos) @ _vector(job.wording(text))) > 0.999, f"vector {pos} is not passage {pos}'s wording"
    assert any(float(index.reconstruct(pos) @ _vector(text)) < 0.9 for pos, text in enumerate(texts) if job.wording(text) != text), (
        "a vector is no longer the whole passage's")
    for name, was in before.items():
        assert (places.vector_store / "acts_t" / name).read_bytes() == was, f"{name} is as it was"
    assert (places.retrieval / "bare_acts.lineage.json").read_bytes() == live_before, "the search still reads the earlier record"
    candidate = json.loads(job.candidate_path(places).read_text(encoding="utf-8"))
    live = json.loads(live_before)
    assert candidate["vector_index"]["path"] == "acts_t/acts_t_wording.index" and candidate["vector_text"] == "wording"
    assert candidate["vectors_earlier"]["path"] == "acts_t/acts_t.index" and candidate["vectors_earlier"]["sha256"] == "earlier"
    assert {k: candidate[k] for k in ("bm25", "passage_store", "passages", "corrected")} == {
        k: live[k] for k in ("bm25", "passage_store", "passages", "corrected")}, "the words and the passages are the same"
    assert hybrid.check_lineage(candidate, places.vector_store, doc_type="bare_act") == []
    assert candidate["verified"]["sampled"] == candidate["verified"]["same_vector"] > 0
    assert not list((places.vector_store / "acts_t").glob("*.f32")), "the working file of vectors is removed once the index is written"


def test_a_run_stopped_part_way_through_goes_on_from_the_last_block_written(tmp_path):
    places, texts = library(tmp_path)
    calls = []

    def stopping(batch):
        calls.append(len(batch))
        if len(calls) == 2:
            raise KeyboardInterrupt
        return _encode(batch)
    with pytest.raises(KeyboardInterrupt):
        job.index_stage(places, stopping, block=3)
    seen = []
    result = job.index_stage(places, lambda batch: (seen.append(len(batch)) or _encode(batch)), block=3)
    assert result["lineage_problems"] == []
    assert sum(seen[:-1]) == len(texts) - 3, "the first block was not encoded again"
    assert seen[-1] == len(texts), "the last call is the check of a sample, here every passage of a small store"
    import faiss
    index = faiss.read_index(str(places.vector_store / "acts_t" / "acts_t_wording.index"))
    for pos, text in enumerate(texts):
        assert float(index.reconstruct(pos) @ _vector(job.wording(text))) > 0.999


def test_the_job_will_not_overwrite_a_file_nor_repeat_what_is_done(tmp_path):
    places, _ = library(tmp_path)
    job.index_stage(places, _encode)
    with pytest.raises(SystemExit, match="exists"):
        job.index_stage(places, _encode)
    live = places.retrieval / "bare_acts.lineage.json"
    live.write_text(json.dumps({**json.loads(live.read_text(encoding="utf-8")), "vector_text": "wording"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="already made from the passages' wording"):
        job.index_stage(places, _encode)


def test_a_store_that_does_not_agree_with_its_record_is_not_embedded(tmp_path):
    places, _ = library(tmp_path)
    with (places.vector_store / "acts_t" / "acts_t.index").open("ab") as handle:
        handle.write(b"x")
    with pytest.raises(SystemExit, match="does not agree"):
        job.index_stage(places, _encode)
    assert not (places.vector_store / "acts_t" / "acts_t_wording.index").exists()


def test_the_swap_makes_the_new_record_the_live_one_keeps_the_earlier_and_is_refused_while_the_server_is_up(tmp_path):
    places, _ = library(tmp_path)
    live = places.retrieval / "bare_acts.lineage.json"
    earlier = live.read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="run the index stage first"):
        job.swap_stage(places, running=lambda: False)
    job.index_stage(places, _encode)
    with pytest.raises(SystemExit, match="server is up"):
        job.swap_stage(places, running=lambda: True)
    assert live.read_text(encoding="utf-8") == earlier
    done = job.swap_stage(places, running=lambda: False)
    now = json.loads(live.read_text(encoding="utf-8"))
    assert now["vector_index"]["path"] == "acts_t/acts_t_wording.index" and "swapped_in" in now and done["passages"] == now["passages"]
    kept = [p for p in places.retrieval.iterdir() if p.name.startswith("bare_acts.lineage.json.before-")]
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == earlier
    assert hybrid.check_lineage(now, places.vector_store, doc_type="bare_act") == []


def test_the_check_looks_at_a_sample_and_writes_nothing(tmp_path):
    places, texts = library(tmp_path)
    folder = places.vector_store / "acts_t"
    names = sorted(p.name for p in folder.iterdir()) + sorted(p.name for p in places.retrieval.iterdir())
    report = job.check_stage(places, _encode, lambda batch: [len(text.split()) for text in batch], only=5, seed=3)
    assert sorted(p.name for p in folder.iterdir()) + sorted(p.name for p in places.retrieval.iterdir()) == names
    assert report["passages in the store"] == len(texts) and report["looked at"] == 5
    assert report["similarity of the new vector to the vector now held (mean, 10th percentile, lowest)"][2] < 0.5, (
        "the stand-in's vectors differ for every text, so the new vector is not the old one")
    assert report["share of a passage's characters taken out (median, 90th percentile)"][0] > 0
    now, own = report["tokens as embedded now (median, 90th percentile, over the model's limit)"], \
        report["tokens as embedded from the wording (median, 90th percentile, over the limit)"]
    assert own[0] < now[0], "the wording is shorter than the whole passage"
    assert report["first three, as embedded now and from the wording"][0]["now"].startswith(NAME)
    assert not report["first three, as embedded now and from the wording"][0]["wording"].startswith(NAME)
