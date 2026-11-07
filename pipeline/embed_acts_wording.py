"""Embed the Acts anew from their own wording. AN OFFLINE JOB; THE OWNER RUNS IT. THE CHECK STAGE WRITES NOTHING; THE INDEX STAGE WRITES ONLY
A NEW INDEX FILE BESIDE THE ACT STORE'S AND A CANDIDATE LINEAGE RECORD; THE SWAP STAGE IS THE ONLY ONE THAT CHANGES WHAT THE SEARCH READS,
AND IT RUNS WITH THE SERVER STOPPED.

    .venv-arrive\\Scripts\\python.exe pipeline\\embed_acts_wording.py --stage check [--only 2000]   (look first: a sample; nothing written)
    .venv-arrive\\Scripts\\python.exe pipeline\\embed_acts_wording.py --stage index                (the vectors; a candidate lineage record)
    .venv-arrive\\Scripts\\python.exe pipeline\\embed_acts_wording.py --stage swap                 (the search reads them; the earlier record kept)

Plan AN.45, D91 and D106 (owner, 5 Nov 2026: "labels shouldn't be used for similarity check, rather it should be the sections wording").
Every Act passage was embedded as it is shown, its first line included: the line that names it ("The Imagined Relief Act, 1907, - s.5:
Revocation of proposals"). That line says the Act, the section and its heading, so every passage of a section resembled the others of its
section and Act for that alone, and a clause could be found by its label and not by what it says. Now a passage's vector is made from its
own words - what follows that line; a section head keeps its number and heading as printed, which are the section's words. The passages,
their order and their text are not changed (the line stays in the text the pane, the answer and the word index use); only the vector file
differs, the same passages in the same positions. The live search moves to it by a new lineage record, the earlier kept. The reranker is
not changed.

Long (the vectors of every Act passage - 351,182 at the last count; the check stage reports how fast this machine makes them; about 1.4 GB
written beside the earlier file), it changes the library, and the owner runs it: nothing in the repository does.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.build_judgments_v3 import (  # noqa: E402 - the library's own model, vector writer and swap
    DIMENSIONS, MODEL_TOKENS, Places, _sha256, _tokenizer_counter, encode_texts, real_encoder, swap_record,
)

DOC_TYPE = "bare_act"
#: What the new vectors are made from, as the lineage record says it and the new files are named.
KIND = "wording"


def wording(full_text: str) -> str:
    """What a passage says, apart from the line that names it. The first line of an Act passage names it - the Act, the section or other
    division, its heading - and what follows is the statute's own words; a passage with nothing after its first line is embedded whole."""
    whole = str(full_text).strip()
    return whole.partition("\n")[2].strip() or whole


def live_path(places: Places) -> Path:
    return places.retrieval / "bare_acts.lineage.json"


def candidate_path(places: Places) -> Path:
    return places.retrieval / "candidates" / f"bare_acts.{KIND}.lineage.json"


def _live_record(places: Places) -> dict:
    """The record the search reads now, after it is found to agree with the files it names."""
    from nm.Archives.legal_brain.retrieve.hybrid_sections import check_lineage

    path = live_path(places)
    if not path.is_file():
        raise SystemExit(f"{path} is not there")
    record = json.loads(path.read_text(encoding="utf-8"))
    problems = check_lineage(record, places.vector_store, doc_type=DOC_TYPE)
    if problems:
        raise SystemExit("the Act store does not agree with its record; nothing done: " + "; ".join(problems))
    if record.get("vector_text") == KIND:
        raise SystemExit("the Act vectors are already made from the passages' wording; nothing to do")
    return record


def _wordings(store: Path, total: int):
    """The wording of every passage in position order; a missing or repeated position stops the run."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        expected = 0
        for pos, blob in con.execute("select pos, blob from chunks where doc_type=? order by pos", (DOC_TYPE,)):
            if pos != expected:
                raise SystemExit(f"the Act store has no passage at position {expected}")
            yield wording(json.loads(blob)["full_text"])
            expected += 1
        if expected != total:
            raise SystemExit(f"the Act store holds {expected:,} passages; its record gives {total:,}")
    finally:
        con.close()


def _at(ordered: list, share: float):
    """The value a share of the way up an ordered list."""
    return ordered[min(len(ordered) - 1, int(len(ordered) * share))]


def check_stage(places: Places, encode: Callable, count: Callable, *, only: int = 2000, seed: int = 5) -> dict:
    """What the change does to a random sample of passages, writing nothing: how much of a passage is the line that names it, how long
    the texts are against what the model reads, how far a passage's vector moves, and how fast this machine makes them."""
    import faiss
    import numpy as np

    record = _live_record(places)
    total = record["passages"]
    positions = sorted(random.Random(seed).sample(range(total), min(only, total)))
    con = sqlite3.connect(f"file:{places.vector_store / record['passage_store']['path']}?mode=ro", uri=True)
    held = {}
    try:
        for start in range(0, len(positions), 500):
            part = positions[start:start + 500]
            for pos, blob in con.execute(f"select pos, blob from chunks where doc_type=? and pos in ({','.join('?' * len(part))})",
                                         (DOC_TYPE, *part)):
                held[pos] = json.loads(blob)["full_text"]
    finally:
        con.close()
    whole = [held[pos] for pos in positions]
    own = [wording(text) for text in whole]
    named = sorted(1 - len(words) / max(1, len(text.strip())) for text, words in zip(whole, own))
    before, after = sorted(count(whole)), sorted(count(own))
    started = time.time()
    fresh = np.asarray(encode(own), dtype="float32")
    seconds = max(time.time() - started, 1e-9)
    index = faiss.read_index(str(places.vector_store / record["vector_index"]["path"]), faiss.IO_FLAG_MMAP)
    moved = np.sort((fresh * np.stack([index.reconstruct(pos) for pos in positions])).sum(axis=1))
    return {"passages in the store": total, "looked at": len(positions),
            "share of a passage's characters taken out (median, 90th percentile)": [round(_at(named, .5), 3), round(_at(named, .9), 3)],
            "tokens as embedded now (median, 90th percentile, over the model's limit)": [
                _at(before, .5), _at(before, .9), sum(n > MODEL_TOKENS for n in before)],
            "tokens as embedded from the wording (median, 90th percentile, over the limit)": [
                _at(after, .5), _at(after, .9), sum(n > MODEL_TOKENS for n in after)],
            "similarity of the new vector to the vector now held (mean, 10th percentile, lowest)": [
                round(float(moved.mean()), 4), round(float(_at(list(moved), .1)), 4), round(float(moved[0]), 4)],
            "passages made a second": round(len(positions) / seconds, 1),
            "first three, as embedded now and from the wording": [
                {"now": " ".join(whole[k].split())[:140], "wording": " ".join(own[k].split())[:140]} for k in range(min(3, len(own)))]}


def index_stage(places: Places, encode: Callable, *, keep_vectors: bool = False, block: int = 20_000) -> dict:
    import faiss
    import numpy as np

    from nm.Archives.legal_brain.retrieve.hybrid_sections import check_lineage

    record = _live_record(places)
    total = record["passages"]
    store = places.vector_store / record["passage_store"]["path"]
    earlier = places.vector_store / record["vector_index"]["path"]
    folder, stem = earlier.parent, earlier.stem
    index_path = folder / f"{stem}_{KIND}.index"
    if index_path.exists():
        raise SystemExit(f"{index_path} exists; move it aside first, rather than overwrite")
    stamp = {"passages": total, "store_bytes": store.stat().st_size, "dimensions": DIMENSIONS, "text": KIND}
    vectors_path = encode_texts(_wordings(store, total), encode, total, folder / f"{stem}_{KIND}.vectors.f32",
                                folder / f"{stem}_{KIND}.progress.json", stamp, block)
    vectors = np.memmap(vectors_path, dtype="float32", mode="r", shape=(total, DIMENSIONS))
    index = faiss.IndexFlatIP(DIMENSIONS)
    for start in range(0, total, 100_000):
        index.add(np.ascontiguousarray(vectors[start:start + 100_000]))
    faiss.write_index(index, str(index_path))
    # A sample of passages encoded again must be the vectors stored.
    sample = list(range(0, total, max(1, total // 60)))[:60]
    wanted = set(sample)
    texts = {pos: text for pos, text in enumerate(_wordings(store, total)) if pos in wanted}
    again = np.asarray(encode([texts[pos] for pos in sample]), dtype="float32")
    similarity = (again * np.stack([index.reconstruct(pos) for pos in sample])).sum(axis=1)
    del vectors, index
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new = {**record,
           "vector_index": {"path": f"{folder.name}/{index_path.name}", "vectors": total, "bytes": index_path.stat().st_size,
                            "sha256": _sha256(index_path)},
           "verified": {"sampled": len(sample), "same_vector": int((similarity > 0.99).sum()),
                        "lowest_similarity": round(float(similarity.min()), 4), "mean_similarity": round(float(similarity.mean()), 4),
                        "at": now},
           "vector_text": KIND, "vectors_earlier": {**record["vector_index"], "text": "the passage as shown, its naming line included"},
           "recorded_by": "pipeline/embed_acts_wording.py", "recorded_at": now}
    problems = check_lineage(new, places.vector_store, doc_type=DOC_TYPE)
    target = candidate_path(places)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(new, indent=2), encoding="utf-8")
    if not keep_vectors:
        vectors_path.unlink(missing_ok=True)
        (folder / f"{stem}_{KIND}.progress.json").unlink(missing_ok=True)
    return {"passages": total, "verified": new["verified"], "lineage_problems": problems, "candidate": str(target)}


def swap_stage(places: Places, **keywords) -> dict:
    """The search reads the new vectors from now on: see build_judgments_v3.swap_record."""
    return swap_record(candidate_path(places), live_path(places), places.vector_store, DOC_TYPE, **keywords)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=("check", "index", "swap"), required=True)
    parser.add_argument("--only", type=int, default=2000, help="check: how many passages, chosen at random, to look at")
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--single-precision", action="store_true",
                        help="make the vectors in single precision (slower; they differ from half precision by under 0.0005)")
    parser.add_argument("--keep-vectors", action="store_true")
    args = parser.parse_args(argv)
    places = Places()
    if args.stage == "check":
        print(json.dumps(check_stage(places, real_encoder(places.models, half=not args.single_precision), _tokenizer_counter(places.models),
                                     only=args.only, seed=args.seed), indent=1))
    elif args.stage == "index":
        print(json.dumps(index_stage(places, real_encoder(places.models, half=not args.single_precision), keep_vectors=args.keep_vectors),
                         indent=1))
    else:
        print(json.dumps(swap_stage(places), indent=1))
        print("Start the server again to search the new vectors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
