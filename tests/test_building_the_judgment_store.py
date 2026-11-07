"""The judgment store is built anew from the raw judgments (plan AN.45, D97-D105): each passage a stretch of a judgment cut on its own
paragraphs, carrying the case, its court as the Telangana forum's, its own citations, the cases and provisions it cites and its kind;
vector n is passage n; the word index is built from the same passages; the candidate lineage record agrees with the files it names;
and the swap that puts it into the search is refused while the server is up or the files disagree. A synthetic library of three
invented judgments, a stand-in for the model's vectors, and the real word index (bm25s) on a tiny corpus."""
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from nm.Archives.legal_brain.retrieve import hybrid_sections as hybrid
from nm.shared.citation_contracts import find_reporter_citations
from pipeline import build_judgments_v3 as job
from tests.test_appending_bare_acts_never_mismaps import _encode, _vector

pytestmark = pytest.mark.class_a


def words(texts):
    return [len(text.split()) for text in texts]


@pytest.fixture(autouse=True)
def small_limits(monkeypatch):
    monkeypatch.setattr(job.cut_judgments, "LIMIT", 40)
    monkeypatch.setattr(job.cut_judgments, "WINDOW", 25)
    monkeypatch.setattr(job.cut_judgments, "PARAGRAPH_MOST", 120)


def sentences(count, tag):
    return " ".join(f"The court held point {tag}{n} proved." for n in range(1, count + 1))


FIRST_CITATION = "1990 AIR 100"
FIRST = (f"[Cites\n3\n, Cited by\n12\n]\nSupreme Court of India\nAlpha vs Beta on 1 January, 1990\nEquivalent citations: {FIRST_CITATION}, "
         "(1990) 1 SCR 5\nBench: Gamma, J.\nJUDGMENT\n"
         + "\n".join(f"{n}. {sentences(2, f'a{n}')}" for n in range(1, 5))
         + f"\n5. {sentences(9, 'long')}\n6. The deed is under section 3 of the Imagined Relief Act, 1907 and section 10 of the NI Act. "
         "Convicted under section 302 IPC.\n7. Appeal dismissed.\n")
SECOND = ("[Cites\n1\n, Cited by\n0\n]\nHigh Court of Andhra Pradesh\nDelta vs Epsilon on 2 February, 1995\n"
          f"The petitioner relies on {FIRST_CITATION}. " + sentences(14, "b") + " Section 4 of the Imagined Relief Act applies. "
          "This is reported at (1999) 9 SCC 999.")
THIRD = "Supreme Court of India\nZeta vs Eta on 3 March, 1960\n" + sentences(6, "c")


def library(tmp_path):
    """An invented library: raw judgments, the case index, an earlier store, the register and the owner's aliases."""
    raw = tmp_path / "raw_data"
    cases = {}
    for case_id, folder, name, text, court, year, title in (
            ("SC_1990_A_V_B", "Supreme Court", "SC_1990_A_V_B.txt", FIRST, "Supreme Court of India", 1990, "Alpha vs Beta"),
            ("HC_1995_D_V_E", "Telangana HC", "HC_1995_D_V_E.txt", SECOND, "High Court of Andhra Pradesh", 1995, "Delta vs Epsilon"),
            ("SC_1960_Z_V_H", "Supreme Court", "SC_1960_Z_V_H.txt", THIRD, "Supreme Court of India", 1960, "Zeta vs Eta")):
        (raw / "CaseLaws" / folder).mkdir(parents=True, exist_ok=True)
        (raw / "CaseLaws" / folder / name).write_text(text, encoding="utf-8")
        cases[case_id] = (case_id, f"{folder}\\{name}", court, year, title)     # as the case index names the file
    cases["SC_2000_GONE"] = ("SC_2000_GONE", "Supreme Court\\SC_2000_GONE.txt", "Supreme Court of India", 2000, "Gone vs Away")
    (tmp_path / ".nm").mkdir()
    identity = sqlite3.connect(tmp_path / ".nm" / "identity.db")
    identity.execute("create table cases (case_id text primary key, source_file text, court text, year integer, title text)")
    identity.execute("create table citations (citation_key text, case_id text, primary key (citation_key, case_id))")
    identity.executemany("insert into cases values (?,?,?,?,?)", list(cases.values()))
    for citation in find_reporter_citations(f"{FIRST_CITATION}, (1990) 1 SCR 5"):
        identity.executemany("insert or ignore into citations values (?,?)", [(key, "SC_1990_A_V_B") for key in citation.keys])
    identity.commit()
    identity.close()
    # The earlier store: the first judgment as the old cut had it - the first half "facts", the rest "ratio"; the third is not in it.
    store = tmp_path / "vector_store"
    store.mkdir()
    old = sqlite3.connect(store / "chunks.db")
    old.execute("create table chunks (doc_type text, pos integer, chunk_id text, act_id text, case_id text, parent_chunk_id text, "
                "atom_type text, section_number text, blob text, primary key (doc_type, pos))")
    half = FIRST.index("5. ")
    pieces = [(FIRST[:half], "facts"), (FIRST[half:], "ratio")]
    for pos, (text, kind) in enumerate(pieces):
        blob = {"case_id": "SC_1990_A_V_B", "case_name": "Alpha vs Beta", "court": "Supreme Court of India", "year": "1990",
                "cites_count": 3, "cited_by_count": 12, "paragraph_type": kind, "full_text": text}
        old.execute("insert into chunks values ('case_law', ?, ?, null, 'SC_1990_A_V_B', null, ?, null, ?)",
                    (pos, f"old{pos}", kind, json.dumps(blob)))
    old.execute("insert into chunks values ('case_law', 9, 'oldhc', null, 'HC_1995_D_V_E', null, 'reasoning', null, ?)",
                (json.dumps({"case_id": "HC_1995_D_V_E", "case_name": "Delta vs Epsilon", "court": "High Court of Andhra Pradesh",
                             "year": "1995", "cites_count": 1, "cited_by_count": 0, "paragraph_type": "reasoning",
                             "full_text": SECOND}),))
    old.commit()
    old.close()
    (tmp_path / "pipeline").mkdir()
    (tmp_path / "pipeline" / "instrument_copies.json").write_text(json.dumps({"documents": {
        "ACT1": {"role": "kept", "group": "imagined relief act 1907"}, "ACT2": {"role": "kept", "group": "negotiable instruments act 1881"},
        "ACT3": {"role": "kept", "group": "indian penal code 1860"}}}), encoding="utf-8")
    (tmp_path / "pipeline" / "act_aliases.json").write_text(json.dumps({"schema": 1, "aliases": [
        {"as_written": ["NI Act"], "checked": True, "acts": [{"key": "negotiable instruments act 1881",
                                                             "title": "Negotiable Instruments Act, 1881", "from": 1881, "to": None}]},
        {"as_written": ["IPC"], "checked": False, "acts": [{"key": "indian penal code 1860", "title": "Indian Penal Code, 1860",
                                                           "from": 1860, "to": None}]}]}), encoding="utf-8")
    return job.Places(raw_data=raw, vector_store=store, old_store=store / "chunks.db", identity=tmp_path / ".nm" / "identity.db",
                      register=tmp_path / "pipeline" / "instrument_copies.json", aliases=tmp_path / "pipeline" / "act_aliases.json",
                      retrieval=tmp_path / ".nm" / "retrieval", models=tmp_path / ".nm" / "models")


def rows_of(places, out="trial"):
    return [json.loads(line) for line in (places.folder(out) / "passages.jsonl").read_text(encoding="utf-8").splitlines()]


def test_each_judgment_is_cut_on_its_paragraphs_and_each_passage_carries_what_is_known_of_it(tmp_path):
    places = library(tmp_path)
    summary = job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    assert (summary["judgments"], summary["printed"], summary["unnumbered"], summary["without text"]) == (4, 1, 2, 1)
    assert summary["not in the earlier store"] == 2 and summary["passages"] == len(rows_of(places))
    rows = rows_of(places)
    first = [r["blob"] for r in rows if r["case_id"] == "SC_1990_A_V_B"]
    assert [b["locator"] for b in first][:3] == ["opening", "1", "2"] and "5 (part 1 of 2)" in [b["locator"] for b in first]
    assert all(b["numbering"] == "printed" and b["doc_type"] == "case_law" and b["court"] == "Supreme Court of India" for b in first)
    assert all(b["case_name"] == "Alpha vs Beta" and (b["cites_count"], b["cited_by_count"]) == (3, 12) for b in first)
    assert {b["source_file"] for b in first} == {"CaseLaws\\Supreme Court\\SC_1990_A_V_B.txt"}, "as the earlier store names it"
    assert [r["chunk_id"] for r in rows if r["case_id"] == "SC_1990_A_V_B"] == [b["chunk_id"] for b in first]
    assert len({r["chunk_id"] for r in rows}) == len(rows), "no identifier twice"
    assert all(r["atom_type"] == r["blob"]["paragraph_type"] for r in rows)
    # The words are the judgment's: nothing lost, in order.
    assert "".join("".join(b["full_text"].split()) for b in first) == "".join(FIRST.split())


def test_an_andhra_pradesh_judgment_is_a_telangana_judgment_and_keeps_the_courts_own_name(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    blobs = [r["blob"] for r in rows_of(places) if r["case_id"] == "HC_1995_D_V_E"]
    assert blobs and all(b["court"] == "High Court of Telangana" and b["court_as_filed"] == "High Court of Andhra Pradesh" for b in blobs)
    assert all(b["numbering"] == "none" and b["locator"].startswith("passage ") and b["paragraph_num"] == "" for b in blobs)


def test_the_kinds_are_those_of_the_old_passages_the_new_ones_overlap_and_unknown_where_none_does(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    rows = rows_of(places)
    first = {r["blob"]["locator"]: r["atom_type"] for r in rows if r["case_id"] == "SC_1990_A_V_B"}
    assert first["1"] == first["2"] == "facts" and first["6"] == first["7"] == "ratio" and first["5 (part 1 of 2)"] == "ratio"
    assert {r["atom_type"] for r in rows if r["case_id"] == "HC_1995_D_V_E"} == {"reasoning"}
    assert {r["atom_type"] for r in rows if r["case_id"] == "SC_1960_Z_V_H"} == {"unknown"}


def test_the_judgments_own_citations_are_read_from_its_heading_and_confirmed_by_the_case_index(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    blob = next(r["blob"] for r in rows_of(places) if r["case_id"] == "SC_1990_A_V_B")
    assert blob["own_citations"] == [{"text": FIRST_CITATION, "confirmed": True}, {"text": "(1990) 1 SCR 5", "confirmed": True}]
    assert blob["citation"] == f"{FIRST_CITATION} | (1990) 1 SCR 5"
    other = next(r["blob"] for r in rows_of(places) if r["case_id"] == "HC_1995_D_V_E")
    assert other["own_citations"] == [] and other["citation"] == ""


def test_the_cases_a_passage_cites_lead_to_the_held_judgment_or_are_said_not_to(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    cited = [c for r in rows_of(places) if r["case_id"] == "HC_1995_D_V_E" for c in r["blob"]["cited_cases"]]
    assert {"citation": FIRST_CITATION, "case_ids": ["SC_1990_A_V_B"]} in cited
    assert {"citation": "(1999) 9 SCC 999", "case_ids": []} in cited, "a case not held is listed, with no judgment"
    own = [c for r in rows_of(places) if r["case_id"] == "SC_1990_A_V_B" for c in r["blob"]["cited_cases"]]
    assert own == [], "a judgment's own citation, printed in its heading, is not a case it cites"


def test_the_provisions_a_passage_cites_name_the_act_and_which_held_act_that_is_only_where_it_is_decided(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    sections = [s for r in rows_of(places) if r["case_id"] == "SC_1990_A_V_B" for s in r["blob"]["sections_cited"]]
    by_act = {s["act_as_written"]: s for s in sections}
    assert by_act["Imagined Relief Act, 1907"]["keys"] == ["imagined relief act 1907"]
    assert by_act["NI Act"]["state"] == "held" and by_act["NI Act"]["keys"] == ["negotiable instruments act 1881"]
    assert "IPC" not in by_act, "an abbreviation the owner has not checked is not even read"
    again = job.read_stage(places, "draft", only=None, seed=1, aliases="draft", workers=1, counter=words)
    drafted = [s for r in rows_of(places, "draft") if r["case_id"] == "SC_1990_A_V_B" for s in r["blob"]["sections_cited"]]
    assert {s["act_as_written"]: s["state"] for s in drafted}["IPC"] == "held" and again["judgments"] == 4
    nothing = job.read_stage(places, "bare", only=None, seed=1, aliases="none", workers=1, counter=words)
    exact = [s for r in rows_of(places, "bare") if r["case_id"] == "SC_1990_A_V_B" for s in r["blob"]["sections_cited"]]
    assert {s["act_as_written"]: s["state"] for s in exact}["NI Act"] == "unresolved" and nothing["judgments"] == 4


def test_a_judgment_whose_text_cannot_be_read_is_reported_and_the_rest_are_built(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    reports = json.loads((places.folder("trial") / "judgments.json").read_text(encoding="utf-8"))
    gone = next(r for r in reports if r["case_id"] == "SC_2000_GONE")
    assert gone["passages"] == 0 and any("could not be read" in p for p in gone["problems"])
    assert any(r["case_id"] == "SC_1960_Z_V_H" and any("not in the earlier store" in n for n in r["notes"]) for r in reports)
    assert not [r for r in rows_of(places) if r["case_id"] == "SC_2000_GONE"]


def test_a_trial_takes_a_random_few_judgments_the_same_few_for_the_same_seed(tmp_path):
    places = library(tmp_path)
    one = job.read_stage(places, "a", only=2, seed=7, aliases="checked", workers=1, counter=words)
    two = job.read_stage(places, "b", only=2, seed=7, aliases="checked", workers=1, counter=words)
    assert one["judgments"] == two["judgments"] == 2
    assert {r["case_id"] for r in rows_of(places, "a")} == {r["case_id"] for r in rows_of(places, "b")}


def built(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    return places, job.index_stage(places, "trial", _encode, keep_vectors=False)


def test_vector_n_is_passage_n_the_store_holds_every_passage_in_order_and_the_lineage_agrees_with_the_files(tmp_path):
    import faiss

    places, result = built(tmp_path)
    rows = rows_of(places)
    assert result["lineage_problems"] == [] and result["passages"] == len(rows)
    record = json.loads(places.candidate("trial").read_text(encoding="utf-8"))
    assert hybrid.check_lineage(record, places.vector_store, doc_type="case_law") == []
    assert record["verified"]["sampled"] == record["verified"]["same_vector"] > 0
    assert (record["passages"], record["passage_store"]["max_pos"]) == (len(rows), len(rows) - 1)
    con = sqlite3.connect(places.folder("trial") / "trial.db")
    stored = con.execute("select pos, chunk_id, case_id, atom_type, blob from chunks where doc_type='case_law' order by pos").fetchall()
    assert [s[0] for s in stored] == list(range(len(rows))) and [s[1] for s in stored] == [r["chunk_id"] for r in rows]
    assert all(s[3] == json.loads(s[4])["paragraph_type"] and s[2] == json.loads(s[4])["case_id"] for s in stored)
    index = faiss.read_index(str(places.folder("trial") / "trial.index"))
    assert index.ntotal == len(rows)
    for pos, row in enumerate(rows):
        assert float(index.reconstruct(pos) @ _vector(row["blob"]["full_text"])) > 0.999, f"vector {pos} is not passage {pos}'s"
    assert not (places.folder("trial") / "vectors.f32").exists(), "the working file of vectors is removed once the index is written"


def test_the_word_index_is_the_one_bm25s_builds_from_the_same_passages_as_strings(tmp_path):
    import bm25s

    from nm.shared.citation_contracts import bm25_tokens

    places, _ = built(tmp_path)
    rows = rows_of(places)
    loaded = bm25s.BM25.load(str(places.folder("trial") / "trial_bm25s"))
    assert json.loads((places.folder("trial") / "trial_bm25s" / "params.index.json").read_text())["num_docs"] == len(rows)
    direct = bm25s.BM25(**job.BM25_PARAMS)
    direct.index([bm25_tokens(r["blob"]["full_text"]) for r in rows], show_progress=False)
    for query in ("Imagined Relief Act section 3", "appeal dismissed", "point long4 proved"):
        tokens = bm25_tokens(query)
        assert np.allclose(loaded.get_scores(tokens), direct.get_scores(tokens)), query
    scores = loaded.get_scores(bm25_tokens("appeal dismissed"))
    assert "Appeal dismissed" in rows[int(np.argmax(scores))]["blob"]["full_text"]


def test_a_store_is_never_built_over_one_already_there(tmp_path):
    places, _ = built(tmp_path)
    with pytest.raises(SystemExit, match="exists"):
        job.index_stage(places, "trial", _encode)


def test_a_run_stopped_part_way_through_the_vectors_goes_on_from_the_last_block_written(tmp_path):
    places = library(tmp_path)
    job.read_stage(places, "trial", only=None, seed=1, aliases="checked", workers=1, counter=words)
    folder, total = places.folder("trial"), len(rows_of(places))
    calls = []

    def stopping(texts):
        calls.append(len(texts))
        if len(calls) == 2:
            raise KeyboardInterrupt
        return _encode(texts)
    with pytest.raises(KeyboardInterrupt):
        job.encode_all(folder, stopping, total, block=5)
    seen = []
    path = job.encode_all(folder, lambda texts: (seen.append(len(texts)) or _encode(texts)), total, block=5)
    assert sum(seen) == total - 5, "the first block was not encoded again"
    vectors = np.memmap(path, dtype="float32", mode="r", shape=(total, job.DIMENSIONS))
    for pos, row in enumerate(rows_of(places)):
        assert float(vectors[pos] @ _vector(row["blob"]["full_text"])) > 0.999


def test_the_swap_makes_the_new_record_the_live_one_keeps_the_earlier_and_is_refused_while_the_server_is_up(tmp_path):
    places, _ = built(tmp_path)
    places.retrieval.mkdir(parents=True, exist_ok=True)
    places.live.write_text(json.dumps({"earlier": True}), encoding="utf-8")
    with pytest.raises(SystemExit, match="server is up"):
        job.swap_stage(places, "trial", running=lambda: True)
    assert json.loads(places.live.read_text()) == {"earlier": True}
    done = job.swap_stage(places, "trial", running=lambda: False)
    live = json.loads(places.live.read_text(encoding="utf-8"))
    assert live["vector_index"]["path"] == "trial/trial.index" and "swapped_in" in live and done["passages"] == live["passages"]
    kept = [p for p in places.retrieval.iterdir() if p.name.startswith("judgments.lineage.json.before-")]
    assert len(kept) == 1 and json.loads(kept[0].read_text()) == {"earlier": True}


def test_a_new_store_that_does_not_agree_with_its_record_is_not_swapped_in(tmp_path):
    places, _ = built(tmp_path)
    places.retrieval.mkdir(parents=True, exist_ok=True)
    places.live.write_text(json.dumps({"earlier": True}), encoding="utf-8")
    with (places.folder("trial") / "trial.index").open("ab") as handle:
        handle.write(b"x")
    with pytest.raises(SystemExit, match="does not agree"):
        job.swap_stage(places, "trial", running=lambda: False)
    assert json.loads(places.live.read_text()) == {"earlier": True}
    with pytest.raises(SystemExit, match="index stage first"):
        job.swap_stage(places, "never_built", running=lambda: False)


def test_the_encoder_gives_unit_vectors_in_single_precision_whatever_the_model_returns():
    """A model run in half precision returns vectors a hair long or short and in half precision; the encoder makes them unit length in
    single precision, and puts the model into half precision only when asked."""
    class Model:
        def __init__(self):
            self.halved, self.seen = False, []

        def half(self):
            self.halved = True

        def encode(self, texts, **options):
            self.seen.append(options)
            return np.stack([_vector(text) * 1.0004 for text in texts]).astype("float16")
    model = Model()
    vectors = job.make_encoder(model, half=True)(["one text", "another text"])
    assert model.halved and vectors.dtype == np.float32 and vectors.shape == (2, job.DIMENSIONS)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-6)
    assert model.seen[0]["normalize_embeddings"] is False and model.seen[0]["show_progress_bar"] is False
    plain = Model()
    job.make_encoder(plain, half=False)(["one text"])
    assert not plain.halved
