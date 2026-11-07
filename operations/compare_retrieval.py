"""Compare the search on the Acts' earlier vectors with the same search on vectors made from the passages' own wording (plan AN.45, D107).
A MEASUREMENT FOR THE OWNER TO READ BEFORE THE SWAP; IT CHANGES NOTHING. It reads the live Act store and writes a small sample library
(and a report) in a folder of its own.

    .venv-arrive\\Scripts\\python.exe operations\\compare_retrieval.py --out outputs\\compare-acts [--distractors 40 --seed 5]

What it does. The questions are in operations/retrieval_questions.json: legal questions an advocate's research would put to the Acts, each
with the provisions that answer it, written once in plain words and once naming the Act, composed from the golden set's verified authority
(docs/GOLDEN_SET.md section 6) - composed, not sampled, so provisional (that document's section 7). The sample library is every passage of
the Acts the questions expect plus a number of other Acts chosen at random, in the store's own form (passages, word index, vectors) -
built twice from the same passages: with the vectors the live search reads, and with vectors made from each passage's wording. Each question
is then put to both, three ways: the vectors alone, the words alone (the control: the same for both), and the product's own search (words
and vectors fused, then the reranker; a question that names its Act is searched with the Act named, as research names the Acts of its plan,
which also looks in that Act by words and by vectors). The rank of the first expected provision, counting each section once, is what is
compared. The reranker, the fusion and the word index are the product's; only the vectors differ.

What it cannot show. The library is a sample, so a rank here is not a rank in the whole library; the questions are mine and the Acts they
name are the golden set's; a model's own search phrases are not these. A result worse for the new vectors is the owner's to weigh and does
not change D91 (the vectors are made from what a passage says); a result better is no reason to skip the owner's look at real questions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.shared.citation_contracts import bm25_tokens  # noqa: E402
from pipeline.build_judgments_v3 import BM25_PARAMS, DIMENSIONS, EMBED_MODEL, Places, real_encoder  # noqa: E402
from pipeline.embed_acts_wording import wording  # noqa: E402

QUESTIONS = Path(__file__).with_name("retrieval_questions.json")
DOC_TYPE = "bare_act"
#: How deep the vectors-alone and words-alone lists are read.
DEPTH = 100
#: How many provisions the product's search returns for a question.
RETURNED = 20
LABELS = ("earlier", "wording")
COLUMNS = "pos, chunk_id, act_id, parent_chunk_id, atom_type, section_number, blob"


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    """The questions, each checked to be what the comparison needs: an id used once, its words, its style, and the provisions that answer it."""
    questions = json.loads(path.read_text(encoding="utf-8"))["questions"]
    seen = set()
    for question in questions:
        if question["id"] in seen:
            raise ValueError(f"question {question['id']} is listed twice")
        seen.add(question["id"])
        if question["style"] not in ("plain", "named") or not question["asked"].strip() or not question["expect"]:
            raise ValueError(f"question {question['id']} is not a question with an answer")
        if any(not item.get("act", "").strip() or not str(item.get("section", "")).strip() for item in question["expect"]):
            raise ValueError(f"question {question['id']} has a provision with no Act or no section")
    return questions


def _title_key(title: str) -> str:
    return " ".join(str(title).lower().split())


def resolve_acts(store: Path, questions: list[dict]) -> dict[str, str]:
    """The act_id of each Act the questions name, by its exact title: one Act, or the comparison stops and says which."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        by_title: dict[str, list[str]] = {}
        for act_id, record in con.execute("select act_id, record from acts"):
            by_title.setdefault(_title_key(json.loads(record).get("title") or act_id), []).append(act_id)
    finally:
        con.close()
    found, problems = {}, []
    for title in sorted({item["act"] for question in questions for item in question["expect"]}):
        ids = by_title.get(_title_key(title), [])
        if len(ids) == 1:
            found[title] = ids[0]
        else:
            problems.append(f"{title!r}: {'not held' if not ids else 'held ' + str(len(ids)) + ' times'}")
    if problems:
        raise SystemExit("the questions name Acts the store does not hold once: " + "; ".join(problems))
    return found


def distractor_acts(store: Path, exclude: set[str], count: int, seed: int) -> list[str]:
    """Other Acts, chosen at random (the same for a seed), to be looked through as well."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        others = sorted(act_id for (act_id,) in con.execute("select act_id from acts") if act_id not in exclude)
    finally:
        con.close()
    return sorted(random.Random(seed).sample(others, min(count, len(others))))


def sample_rows(store: Path, act_ids) -> list[tuple]:
    """Every passage of these Acts, in the store's own order: (position, chunk_id, act_id, parent, atom, section, blob)."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        ids = sorted(set(act_ids))
        return con.execute(f"select {COLUMNS} from chunks where doc_type=? and act_id in ({','.join('?' * len(ids))}) order by pos",
                           (DOC_TYPE, *ids)).fetchall()
    finally:
        con.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(matrix, texts: list[str], encode: Callable, count: int = 20) -> dict:
    """The check the search requires of a vector index: a sample of the passages' texts encoded again must be the vectors held."""
    import numpy as np

    sample = list(range(0, len(texts), max(1, len(texts) // count)))[:count]
    again = np.asarray(encode([texts[pos] for pos in sample]), dtype="float32")
    similarity = (again * np.asarray([matrix[pos] for pos in sample], dtype="float32")).sum(axis=1)
    return {"sampled": len(sample), "same_vector": int((similarity > 0.99).sum()), "lowest_similarity": round(float(similarity.min()), 4),
            "mean_similarity": round(float(similarity.mean()), 4)}


def write_sample(folder: Path, rows: list[tuple], vectors: dict, verified: dict) -> dict[str, Path]:
    """The sample library in the form the search reads: one passage store and one word index, and for each label its own vector index and
    lineage record (position n of the sample is vector n of each; verified: each label's check, see verify). Returns each label's record."""
    import bm25s
    import faiss
    import numpy as np

    folder.mkdir(parents=True, exist_ok=True)
    db_path = folder / "sample.db"
    if db_path.exists():
        raise SystemExit(f"{db_path} exists; give a new folder rather than overwrite")
    con = sqlite3.connect(db_path)
    con.execute("create table chunks (doc_type text, pos integer, chunk_id text, act_id text, case_id text, parent_chunk_id text, "
                "atom_type text, section_number text, blob text, primary key (doc_type, pos))")
    con.executemany("insert into chunks values (?,?,?,?,?,?,?,?,?)", [
        (DOC_TYPE, pos, row[1], row[2], None, row[3], row[4], row[5], row[6]) for pos, row in enumerate(rows)])
    con.execute("create index idx_chunks_chunk_id on chunks(chunk_id)")
    con.execute("create index idx_chunks_doc_act on chunks(doc_type, act_id, section_number)")
    con.execute("create index idx_chunks_doc_parent on chunks(doc_type, parent_chunk_id)")
    con.commit()
    con.close()
    words = bm25s.BM25(**BM25_PARAMS)
    words.index([bm25_tokens(json.loads(row[6])["full_text"]) for row in rows], show_progress=False)
    words.save(str(folder / "sample_bm25s"))
    records = {}
    for label, matrix in vectors.items():
        if len(matrix) != len(rows):
            raise ValueError(f"{label}: {len(matrix)} vectors for {len(rows)} passages")
        index = faiss.IndexFlatIP(DIMENSIONS)
        index.add(np.ascontiguousarray(matrix, dtype="float32"))
        path = folder / f"{label}.index"
        faiss.write_index(index, str(path))
        record = {"schema": 1, "doc_type": DOC_TYPE, "model": EMBED_MODEL, "dimensions": DIMENSIONS,
                  "metric": "inner product on normalised vectors", "passages": len(rows),
                  "vector_index": {"path": f"{folder.name}/{path.name}", "vectors": len(rows), "bytes": path.stat().st_size,
                                   "sha256": _sha256(path)},
                  "bm25": {"path": f"{folder.name}/sample_bm25s", "num_docs": len(rows),
                           "params_sha256": _sha256(folder / "sample_bm25s" / "params.index.json")},
                  "passage_store": {"path": f"{folder.name}/sample.db", "count": len(rows), "max_pos": len(rows) - 1},
                  "verified": verified[label]}
        records[label] = folder / f"{label}.lineage.json"
        records[label].write_text(json.dumps(record, indent=2), encoding="utf-8")
    return records


def first_rank(ordered: list[tuple[str, str]], expected: set[tuple[str, str]]) -> int | None:
    """Where the first expected provision stands in an ordered list of (act_id, section), each section counted once; None if it is not there."""
    seen: list[tuple[str, str]] = []
    for place in ordered:
        if place not in seen:
            seen.append(place)
        if place in expected:
            return seen.index(place) + 1
    return None


def summarise(results: list[dict]) -> dict:
    """For each way of searching and each label: how many questions found an expected provision in the first 1, 3, 5, 10, the mean of
    1/rank, and how many were found at all; and, label against label, how many ranked better, the same, worse."""
    out = {}
    for mode in sorted({mode for result in results for mode in result["ranks"]}):
        entry = {}
        for label in LABELS:
            ranks = [result["ranks"][mode][label] for result in results if mode in result["ranks"]]
            entry[label] = {"questions": len(ranks), **{f"in the first {n}": sum(r is not None and r <= n for r in ranks) for n in (1, 3, 5, 10)},
                            "found at all": sum(r is not None for r in ranks),
                            "mean of 1/rank": round(sum(1 / r for r in ranks if r) / max(1, len(ranks)), 4)}
        pairs = [(result["ranks"][mode]["earlier"], result["ranks"][mode]["wording"]) for result in results if mode in result["ranks"]]
        worth = lambda rank: float("inf") if rank is None else rank  # noqa: E731
        entry["wording against earlier"] = {"better": sum(worth(w) < worth(e) for e, w in pairs),
                                            "same": sum(worth(w) == worth(e) for e, w in pairs),
                                            "worse": sum(worth(w) > worth(e) for e, w in pairs)}
        out[mode] = entry
    return out


def by_style(results: list[dict]) -> dict:
    return {style: summarise([r for r in results if r["style"] == style]) for style in ("plain", "named")}


def named_acts(question: dict) -> list[str] | None:
    """The Act a question names, as a plan would name it to the search; none for a question in plain words."""
    return [question["expect"][0]["act"]] if question["style"] == "named" else None


def search_all(questions, collections: dict, places_of: dict, searcher: Callable[[str, str, list[str] | None], list[tuple[str, str]]]) -> list[dict]:
    """Every question put to every label three ways. collections: label -> a collection (lexical/semantic by text and depth);
    places_of: position -> (act_id, section); searcher(label, text, named Acts) -> the product's ordered (act_id, section) list."""
    results = []
    for question in questions:
        expected = {(question["_ids"][item["act"]], str(item["section"])) for item in question["expect"]}
        ranks = {"vectors alone": {}, "words alone": {}, "the product's search": {}}
        for label in LABELS:
            collection = collections[label]
            ranks["vectors alone"][label] = first_rank([places_of[p] for p in collection.semantic(question["asked"], DEPTH)], expected)
            ranks["words alone"][label] = first_rank([places_of[p] for p in collection.lexical(question["asked"], DEPTH)], expected)
            ranks["the product's search"][label] = first_rank(searcher(label, question["asked"], named_acts(question)), expected)
        results.append({"id": question["id"], "style": question["style"], "asked": question["asked"], "ranks": ranks})
    return results


def text_report(results: list[dict], info: dict) -> str:
    lines = [f"Search on the Acts' earlier vectors against vectors made from each passage's wording - {info['passages']:,} passages of "
             f"{info['acts']} Acts ({info['expected_acts']} the questions name, {info['distractors']} others at random, seed {info['seed']}); "
             f"{len(results)} questions.",
             "Named Acts the search did not match to a held Act: " + (", ".join(info["named Acts the search did not match to a held Act"]) or "none")]
    for style, summary in (("all", summarise(results)), *by_style(results).items()):
        lines.append(f"\n== {style} questions ({sum(1 for r in results if style == 'all' or r['style'] == style)})")
        for mode, entry in summary.items():
            lines.append(f"  {mode}")
            for label in LABELS:
                e = entry[label]
                lines.append(f"    {label:8s} first 1: {e['in the first 1']:3d}  first 3: {e['in the first 3']:3d}  first 5: {e['in the first 5']:3d}  "
                             f"first 10: {e['in the first 10']:3d}  found: {e['found at all']:3d}  mean 1/rank: {e['mean of 1/rank']:.3f}")
            lines.append(f"    wording against earlier: {entry['wording against earlier']}")
    lines.append("\n== each question: rank of the first expected provision (earlier -> wording), vectors alone | product's search")
    for r in results:
        vectors, searched = r["ranks"]["vectors alone"], r["ranks"]["the product's search"]
        lines.append(f"  {r['id']:5s} {r['style']:5s} {vectors['earlier']!s:>5} -> {vectors['wording']!s:<5} | "
                     f"{searched['earlier']!s:>5} -> {searched['wording']!s:<5}  {r['asked'][:90]}")
    return "\n".join(lines)


def run(out: Path, *, distractors: int, seed: int, places: Places | None = None, half: bool = True) -> dict:
    """The comparison on the live Act store (read only). Writes the sample library and the report under out."""
    import faiss
    import numpy as np

    from nm.core_engine.retrieval import HybridSearcher, LocalCollection, _Models
    from pipeline.embed_acts_wording import live_path

    places = places or Places()
    record = json.loads(live_path(places).read_text(encoding="utf-8"))
    store = places.vector_store / record["passage_store"]["path"]
    questions = load_questions()
    ids = resolve_acts(store, questions)
    for question in questions:
        question["_ids"] = ids
    chosen = sorted(set(ids.values()) | set(distractor_acts(store, set(ids.values()), distractors, seed)))
    rows = sample_rows(store, chosen)
    texts = [json.loads(row[6])["full_text"] for row in rows]
    print(f"{len(rows):,} passages of {len(chosen)} Acts; making the vectors from each passage's wording", flush=True)
    earlier = faiss.read_index(str(places.vector_store / record["vector_index"]["path"]), faiss.IO_FLAG_MMAP)
    encode = real_encoder(places.models, half=half)
    started = time.time()
    fresh = np.vstack([np.asarray(encode([wording(t) for t in texts[i:i + 2000]]), dtype="float32") for i in range(0, len(texts), 2000)])
    print(f"   {len(texts) / (time.time() - started):.0f} passages a second", flush=True)
    sample = out / "sample"
    held = np.stack([earlier.reconstruct(row[0]) for row in rows])
    checks = {"earlier": verify(held, texts, encode), "wording": verify(fresh, [wording(t) for t in texts], encode)}
    print(f"   the vectors held, made again from the passages: mean similarity {checks['earlier']['mean_similarity']}, "
          f"lowest {checks['earlier']['lowest_similarity']}", flush=True)
    lineages = write_sample(sample, rows, {"earlier": held, "wording": fresh}, checks)
    models = _Models(places.models)
    # The one-copy register is the product's own: a copy it does not keep never takes a place, and it is what a named Act is looked up in.
    collections = {label: LocalCollection(corpus_dir=sample.parent, lineage=path, doc_type=DOC_TYPE, models=models, copies=places.register)
                   for label, path in lineages.items()}
    places_of = {pos: (row[2], str(row[5])) for pos, row in enumerate(rows)}
    searchers = {label: HybridSearcher({"provision": collection}) for label, collection in collections.items()}

    unmatched: list[str] = []

    def product(label: str, text: str, acts: list[str] | None) -> list[tuple[str, str]]:
        found = searchers[label].search([{"query_id": "q1", "text": text}], acts, results={"provision": RETURNED, "judgment": 1})
        unmatched.extend(f"{label}: {entry['name']}" for entry in found["instruments"] if not entry["candidates"])
        return [(c["source"]["act_id"], str(c["source"]["section_number"])) for c in found["candidates"] if c["kind"] == "provision"]
    results = search_all(questions, collections, places_of, product)
    info = {"passages": len(rows), "acts": len(chosen), "expected_acts": len(ids), "distractors": len(chosen) - len(ids), "seed": seed,
            "named Acts the search did not match to a held Act": sorted(set(unmatched))}
    report = text_report(results, info)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.txt").write_text(report, encoding="utf-8")
    (out / "results.json").write_text(json.dumps({"info": info, "results": results, "summary": summarise(results),
                                                   "by style": by_style(results)}, indent=1), encoding="utf-8")
    return {"info": info, "summary": summarise(results), "report": str(out / "report.txt")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="a new folder for the sample library and the report")
    parser.add_argument("--distractors", type=int, default=40, help="how many other Acts, chosen at random, to look through as well")
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--single-precision", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    done = run(args.out, distractors=args.distractors, seed=args.seed, half=not args.single_precision)
    print((args.out / "report.txt").read_text(encoding="utf-8"))
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
