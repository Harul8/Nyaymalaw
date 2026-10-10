"""Record, and verify, what built the search indexes. AN OFFLINE JOB.

    python pipeline/record_retrieval_lineage.py                         # both, verify, write
    python pipeline/record_retrieval_lineage.py --collection judgments  # one of them
    python pipeline/record_retrieval_lineage.py --check                 # verify, write nothing

LB-106 (owner, 29 September 2026; judgments 30 September 2026): the existing vector
indexes, word indexes and passage store are reused as they are, for bare acts and for
judgments alike. Nothing on disk said which model built the vectors, and querying an
index with a different model does not error -- it returns plausible, confidently wrong
neighbours (defect shape S11). So before a search may use a collection, this job:

  1. reads the three members' own counts -- the index header, the word index's
     parameters, the passage store -- and refuses if they disagree. Vectors PAST the
     last passage are counted and recorded (the judgment index holds 63); they map to
     nothing and the search drops them. Fewer vectors than passages is refused;
  2. ENCODES stored passages with the model the search will query with and compares
     each with the vector stored AT ITS OWN POSITION -- sampled across the whole store
     and, where appends land, at its last positions. That is what establishes the model
     and that vector n is passage n; a name written in a file would only assert it. Each
     passage is encoded at every length the builder is known to have cut at (the
     judgment builder cut at 256 tokens, and its later appends at 512), and the closer
     counts: a different model or a shifted position matches neither;
  3. checks the WORD index the same way: for each sampled passage, every one of its
     rarest indexed words must list the passage's own position. Measured 30 September
     2026: 42 of 42 in each collection;
  4. writes `.nm/retrieval/<collection>.lineage.json`: the model, the dimensions, the
     counts, the index's size and sha256, and the verification. Retained contextual
     parent records are declared separately by path, format and SHA-256; they are
     not searchable vector positions. Existing declarations survive regeneration,
     and a missing or changing declared store prevents overwriting its manifest.

The search refuses to run on a set that no longer agrees with its record. After a
bare-act append (`pipeline/append_bare_acts.py`) the append job rewrites that record.

It takes a few minutes (the judgment index is 4.2 GB to hash), and it is a job the owner
starts; nothing runs it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()
from nm.Archives.legal_brain.retrieve.hybrid_sections import (  # noqa: E402
    DIMENSIONS,
    EMBED_MODEL,
    bm25_tokens,
    check_lineage,
    faiss_header,
)

VECTOR_STORE = ROOT / "legal_database" / "vector_store"
STORE = "chunks.db"
LINEAGE = ROOT / ".nm" / "retrieval"
MODELS = ROOT / ".nm" / "models"


@dataclass(frozen=True)
class Collection:
    name: str
    doc_type: str
    index: str
    bm25: str
    #: The lengths, in tokens, the builder cut passages at before encoding. `None` is
    #: the model's own default.
    cut_at: tuple[int | None, ...]
    context_store: str | None = None

    @property
    def out(self) -> Path:
        return LINEAGE / f"{self.name}.lineage.json"


COLLECTIONS = {
    "bare_acts": Collection("bare_acts", "bare_act", "bareacts_v3.index", "bareacts_v3_bm25s",
                            (None,), "bareacts_v3_parents.json"),
    "judgments": Collection("judgments", "case_law", "caselaws_v2.index", "caselaws_bm25s",
                            (256, 512)),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def context_store(collection: Collection) -> dict | None:
    """Bind retained parent words separately from searchable vector positions."""
    previous = json.loads(collection.out.read_text(encoding="utf-8")) if collection.out.exists() else {}
    declared = previous.get("context_store")
    if declared is not None:
        if (not isinstance(declared, dict) or declared.get("format") != "parent_map_v1"
                or not isinstance(declared.get("path"), str) or not declared["path"]):
            raise ValueError("Existing contextual store has an unknown format or path")
        name = declared["path"]
    else:
        name = collection.context_store
    if name is None:
        return None
    path = (VECTOR_STORE / name).resolve()
    if not path.is_relative_to(VECTOR_STORE.resolve()):
        raise ValueError("Contextual source store is outside this corpus")
    if not path.is_file():
        if declared is not None:
            raise ValueError("Previously declared contextual source store is missing")
        return None
    return {"path": name, "format": "parent_map_v1", "sha256": sha256(path)}


#: How close a fresh encoding must be to the stored vector at the same position.
#: Measured 29 September 2026 on 60 bare-act samples: mean 0.998; short passages 0.999+;
#: the lowest 0.939, on long section heads of 300+ tokens, where the earlier builder cut
#: the text differently. Measured 30 September 2026 on judgments at the builder's own
#: lengths: 1.000 at every sampled position. A different model or a shifted position
#: gives an unrelated vector, nowhere near either bound.
SAME_VECTOR = 0.90
SAME_ON_AVERAGE = 0.99
#: The last positions of the store are always checked: an append lands there, and a
#: shift anywhere before them moves them too.
TAIL = 30
RAREST = 5


def positions(passages: int, samples: int, seed: int) -> list[int]:
    return sorted(set(random.Random(seed).sample(range(passages), min(samples, passages)))
                  | set(range(max(0, passages - TAIL), passages)))


def texts_at(collection: Collection, at: list[int]) -> dict[int, str]:
    con = sqlite3.connect(f"file:{VECTOR_STORE / STORE}?mode=ro", uri=True)
    try:
        return {p: json.loads(con.execute("select blob from chunks where doc_type=? and pos=?",
                                          (collection.doc_type, p)).fetchone()[0]
                              ).get("full_text", "") or ""
                for p in at}
    finally:
        con.close()


def verify_vectors(collection: Collection, passages: int, samples: int) -> dict:
    """Encode stored passages and compare each with the vector STORED AT ITS OWN
    POSITION. A nearest-neighbour test would be fooled by the corpus's duplicate
    passages (one Act held under two identifiers has twin vectors); the stored vector at
    the passage's own position cannot be."""
    os.environ.pop("SSLKEYLOGFILE", None)
    import faiss
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(str(MODELS / EMBED_MODEL.replace("/", "__")), device=device,
                                local_files_only=True)
    default_cut = model.max_seq_length
    index = faiss.read_index(str(VECTOR_STORE / collection.index),
                             faiss.IO_FLAG_MMAP_IFC | faiss.IO_FLAG_READ_ONLY)
    at = positions(passages, samples, 29)
    texts = texts_at(collection, at)
    stored = np.stack([index.reconstruct(int(p)) for p in at])
    best = np.full(len(at), -1.0, dtype="float32")
    for cut in collection.cut_at:
        model.max_seq_length = cut or default_cut
        fresh = np.asarray(model.encode([texts[p] for p in at], normalize_embeddings=True,
                                        convert_to_numpy=True), dtype="float32")
        best = np.maximum(best, (fresh * stored).sum(axis=1))
    return {"sampled": len(at), "same_vector": int((best >= SAME_VECTOR).sum()),
            "lowest_similarity": round(float(best.min()), 4),
            "mean_similarity": round(float(best.mean()), 4),
            "cut_at": [c or default_cut for c in collection.cut_at], "device": device,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def verify_words(collection: Collection, passages: int, samples: int) -> dict:
    """Each sampled passage's rarest indexed words must each list its own position."""
    import bm25s
    import numpy as np

    bm = bm25s.BM25.load(str(VECTOR_STORE / collection.bm25), mmap=True)
    vocab, indptr, indices = bm.vocab_dict, bm.scores["indptr"], bm.scores["indices"]
    at = positions(passages, samples, 30)
    texts = texts_at(collection, at)
    held = without_words = 0
    for p in at:
        ids = {vocab[token] for token in bm25_tokens(texts[p]) if token in vocab}
        if not ids:
            without_words += 1
            continue
        rarest = sorted(ids, key=lambda i: int(indptr[i + 1] - indptr[i]))[:RAREST]
        if all(p in set(np.asarray(indices[indptr[i]:indptr[i + 1]]).tolist())
               for i in rarest):
            held += 1
    return {"sampled": len(at), "own_position": held, "no_indexed_words": without_words}


def record_one(collection: Collection, *, samples: int, check: bool) -> int:
    print(f"\n== {collection.name}")
    try:
        context = context_store(collection)
    except (OSError, ValueError) as exc:
        print(f"REFUSED: contextual source identity cannot be recorded: {exc}")
        return 1
    index = VECTOR_STORE / collection.index
    _, dims, vectors = faiss_header(index)
    docs = json.loads((VECTOR_STORE / collection.bm25 / "params.index.json")
                      .read_text(encoding="utf8"))
    con = sqlite3.connect(f"file:{VECTOR_STORE / STORE}?mode=ro", uri=True)
    count, top = con.execute("select count(*), max(pos) from chunks where doc_type=?",
                             (collection.doc_type,)).fetchone()
    con.close()
    print(f"vectors {vectors:,} x {dims}; word-index documents {docs.get('num_docs'):,}; "
          f"passages {count:,} (positions 0-{top})")
    if not (docs.get("num_docs") == count and top == count - 1 and dims == DIMENSIONS
            and vectors >= count):
        print("REFUSED: the three members do not agree; nothing written.")
        return 1
    tail = vectors - count
    if tail:
        print(f"{tail} vector(s) past the last passage: recorded, never used.")

    checked = verify_vectors(collection, count, samples)
    print(f"{checked['same_vector']}/{checked['sampled']} sampled passages, encoded with "
          f"{EMBED_MODEL} (cut at {checked['cut_at']}), match the vector stored at their own "
          f"position (lowest {checked['lowest_similarity']}, mean "
          f"{checked['mean_similarity']}; {checked['device']})")
    if (checked["same_vector"] < checked["sampled"]
            or checked["mean_similarity"] < SAME_ON_AVERAGE):
        print("REFUSED: the index does not answer to this model at every sampled position; "
              "nothing written.")
        return 1
    words = verify_words(collection, count, samples)
    print(f"{words['own_position']}/{words['sampled'] - words['no_indexed_words']} sampled "
          f"passages: every one of their {RAREST} rarest words lists their own position in "
          f"the word index ({words['no_indexed_words']} had no indexed word)")
    if words["no_indexed_words"] or words["own_position"] < words["sampled"]:
        print("REFUSED: the word index did not verify every sampled passage at its own "
              "position; nothing written.")
        return 1

    record = {
        "schema": 1, "doc_type": collection.doc_type, "model": EMBED_MODEL,
        "dimensions": DIMENSIONS, "metric": "inner product on normalised vectors",
        "passages": count, "vectors_without_passage": tail,
        "vector_index": {"path": collection.index, "vectors": vectors,
                         "bytes": index.stat().st_size, "sha256": sha256(index)},
        "bm25": {"path": collection.bm25, "num_docs": docs.get("num_docs"),
                 "params_sha256": sha256(VECTOR_STORE / collection.bm25 / "params.index.json")},
        "passage_store": {"path": STORE, "count": count, "max_pos": top},
        "verified": {**checked, "words": words},
        "recorded_by": "pipeline/record_retrieval_lineage.py",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if context is not None:
        record["context_store"] = context
    try:
        if context_store(collection) != context:
            raise ValueError("Contextual source store changed during verification")
    except (OSError, ValueError) as exc:
        print(f"REFUSED: {exc}; nothing written.")
        return 1
    problems = check_lineage(record, VECTOR_STORE, doc_type=collection.doc_type)
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 1
    if check:
        print("consistent; --check writes nothing")
        return 0
    collection.out.parent.mkdir(parents=True, exist_ok=True)
    collection.out.write_text(json.dumps(record, indent=2), encoding="utf8")
    print(f"wrote {collection.out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--collection", choices=(*COLLECTIONS, "both"), default="both")
    ap.add_argument("--check", action="store_true", help="verify and report; write nothing")
    ap.add_argument("--samples", type=int, default=60)
    args = ap.parse_args(argv)
    chosen = COLLECTIONS.values() if args.collection == "both" else (COLLECTIONS[args.collection],)
    failed = [c.name for c in chosen
              if record_one(c, samples=args.samples, check=args.check)]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
