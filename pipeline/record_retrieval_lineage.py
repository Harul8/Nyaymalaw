"""Record, and verify, what built the bare-act search index. AN OFFLINE JOB.

    python pipeline/record_retrieval_lineage.py            # verify 60 samples, write
    python pipeline/record_retrieval_lineage.py --check    # verify and report; write nothing

LB-106 (owner, 29 September 2026): the existing bare-act vector index, BM25 index and
passage store are reused as they are. Nothing on disk said which model built the
vectors, and querying an index with a different model does not error -- it returns
plausible, confidently wrong neighbours (defect shape S11). So before the search may
use them, this job:

  1. reads the three members' own counts -- the index header, the BM25 parameters, the
     passage store -- and refuses if they disagree;
  2. ENCODES stored passages with the model the search will query with and compares
     each with the vector stored AT ITS OWN POSITION. That is what establishes the model
     and that vector n is passage n; a name written in a file would only assert it;
  3. writes `.nm/retrieval/bare_acts.lineage.json`: the model, the dimensions, the
     counts, the index's size and sha256, and the verification.

The search refuses to run on a set that no longer agrees with this record. After an
append (`pipeline/append_bare_acts.py`) the append job rewrites it.

It is short (a minute), but it is still a job the owner starts; nothing runs it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()
from nm.legal_brain.retrieve.hybrid_sections import (  # noqa: E402
    DIMENSIONS,
    DOC_TYPE,
    EMBED_MODEL,
    check_lineage,
    faiss_header,
)

VECTOR_STORE = ROOT / "legal_database" / "vector_store"
INDEX, BM25_DIR, STORE = "bareacts_v3.index", "bareacts_v3_bm25s", "chunks.db"
OUT = ROOT / ".nm" / "retrieval" / "bare_acts.lineage.json"
MODELS = ROOT / ".nm" / "models"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


#: How close a fresh encoding must be to the stored vector at the same position.
#: Measured 29 September 2026 on 60 samples: mean 0.998; short passages 0.999+; the
#: lowest 0.939, on long section heads of 300+ tokens, where the earlier builder cut
#: the text differently. A different model or a shifted position gives an unrelated
#: vector, nowhere near either bound.
SAME_VECTOR = 0.90
SAME_ON_AVERAGE = 0.99


def verify(samples: int) -> dict:
    """Encode `samples` stored passages and compare each with the vector STORED AT ITS
    OWN POSITION. A nearest-neighbour test would be fooled by the corpus's duplicate
    passages (one Act held under two identifiers has twin vectors); the stored vector
    at the passage's own position cannot be."""
    os.environ.pop("SSLKEYLOGFILE", None)
    import faiss
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(str(MODELS / EMBED_MODEL.replace("/", "__")), device=device,
                                local_files_only=True)
    index = faiss.read_index(str(VECTOR_STORE / INDEX))
    con = sqlite3.connect(f"file:{VECTOR_STORE / STORE}?mode=ro", uri=True)
    positions = sorted(random.Random(29).sample(range(index.ntotal), samples))
    texts = [json.loads(con.execute("select blob from chunks where doc_type=? and pos=?",
                                    (DOC_TYPE, p)).fetchone()[0]).get("full_text", "")
             for p in positions]
    con.close()
    fresh = np.asarray(model.encode(texts, normalize_embeddings=True, convert_to_numpy=True),
                       dtype="float32")
    stored = np.stack([index.reconstruct(int(p)) for p in positions])
    similarity = (fresh * stored).sum(axis=1)
    return {"sampled": samples, "same_vector": int((similarity >= SAME_VECTOR).sum()),
            "lowest_similarity": round(float(similarity.min()), 4),
            "mean_similarity": round(float(similarity.mean()), 4), "device": device,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="verify and report; write nothing")
    ap.add_argument("--samples", type=int, default=60)
    args = ap.parse_args(argv)

    index = VECTOR_STORE / INDEX
    _, dims, vectors = faiss_header(index)
    docs = json.loads((VECTOR_STORE / BM25_DIR / "params.index.json").read_text(encoding="utf8"))
    con = sqlite3.connect(f"file:{VECTOR_STORE / STORE}?mode=ro", uri=True)
    count, top = con.execute("select count(*), max(pos) from chunks where doc_type=?",
                             (DOC_TYPE,)).fetchone()
    con.close()
    print(f"vectors {vectors:,} x {dims}; BM25 documents {docs.get('num_docs'):,}; "
          f"passages {count:,} (positions 0-{top})")
    if not (vectors == docs.get("num_docs") == count and top == count - 1 and dims == DIMENSIONS):
        print("REFUSED: the three members do not agree; nothing written.")
        return 1

    checked = verify(args.samples)
    print(f"{checked['same_vector']}/{checked['sampled']} sampled passages, encoded with "
          f"{EMBED_MODEL}, match the vector stored at their own position (lowest "
          f"{checked['lowest_similarity']}, mean {checked['mean_similarity']}; "
          f"{checked['device']})")
    if (checked["same_vector"] < checked["sampled"]
            or checked["mean_similarity"] < SAME_ON_AVERAGE):
        print("REFUSED: the index does not answer to this model at every sampled position; "
              "nothing written.")
        return 1

    record = {
        "schema": 1, "doc_type": DOC_TYPE, "model": EMBED_MODEL, "dimensions": DIMENSIONS,
        "metric": "inner product on normalised vectors", "passages": count,
        "vector_index": {"path": INDEX, "vectors": vectors, "bytes": index.stat().st_size,
                         "sha256": sha256(index)},
        "bm25": {"path": BM25_DIR, "num_docs": docs.get("num_docs"),
                 "params_sha256": sha256(VECTOR_STORE / BM25_DIR / "params.index.json")},
        "passage_store": {"path": STORE, "count": count, "max_pos": top},
        "verified": checked,
        "recorded_by": "pipeline/record_retrieval_lineage.py",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    problems = check_lineage(record, VECTOR_STORE)
    if problems:
        print("REFUSED: " + "; ".join(problems))
        return 1
    if args.check:
        print("consistent; --check writes nothing")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2), encoding="utf8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
