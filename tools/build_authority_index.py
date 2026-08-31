"""Build the authority index. AN OFFLINE JOB — run it deliberately.

    python tools/build_authority_index.py

WHY THIS IS NOT RUN AUTOMATICALLY
----------------------------------
It is an index build over 1,015,780 case paragraphs. Index builds, training and
backtests are jobs the user starts; nothing in this repository kicks one off on
its own. `tools/check.py` stays cheap enough that there is never an excuse to
skip it, and that only works if it never triggers a job like this one.

Until it has run, `CorpusEvidenceAdapter` returns HELD_NOT_FOUND on every
authority need, NAMING this tool. It does not fall back to scanning
`chunks.db`: a fallback with different recall, swapped in silently, is the
"three stores, three answers" defect wearing a helpful face — the advocate
would have no way to know which retrieval answered them.

WHAT GOES IN, AND WHAT DOES NOT
--------------------------------
ONLY ratio, reasoning and order paragraphs. Counsel's submission is 14.8% of
the corpus and reads exactly like a holding, so it is excluded HERE, at build
time, as well as at use. Two independent exclusions for the same rule is
deliberate: a filter at use can be bypassed by a new call site, and a filter at
build cannot.

Chunks on the corpus's own contamination denylist are excluded too. A denylist
that ships beside the data and is never applied is worse than none — it records
that someone knew the text was bad.

IT WRITES ITS OWN IDENTITY (defect shape S11)
----------------------------------------------
The index records the corpus VERSION and the row counts it was built from. The
previous build's 437MB dense index is only KNOWABLE as unusable because it
shipped an `identity.json` — it was built with a 384-dimensional model against a
product that queries at 3072, and querying across embedding models does not
error, it returns plausible and confidently wrong neighbours. Every derived
artefact in this project therefore records what it came from, and
`nm/knowledge/artefact.py` refuses one whose identity does not match.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402

utf8_console()
CORPUS = ROOT / "legal_database" / "vector_store"
OUT = ROOT / ".nm" / "authority.db"

ATTRIBUTABLE = ("ratio", "reasoning", "order")

SCHEMA = """
create virtual table paras using fts5(
    case_id, case_name, court, year UNINDEXED, para_type UNINDEXED,
    chunk_id UNINDEXED, text,
    tokenize = 'porter unicode61'
);
create table identity (key text primary key, value text);
"""


def denylist() -> set[str]:
    path = CORPUS / "contamination_denylist.json"
    if not path.exists():
        return set()
    doc = json.loads(path.read_text(encoding="utf8", errors="replace"))
    return set(doc.get("chunk_ids") or ())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N attributable paragraphs (for a smoke build)")
    args = ap.parse_args()

    src = CORPUS / "chunks.db"
    if not src.exists():
        sys.exit(f"the corpus is not attached: {src}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        # Refused, not overwritten. A half-written index that replaced a good
        # one is a worse outcome than a build that would not start.
        sys.exit(f"{out} already exists. Delete it deliberately to rebuild.")

    version = ((CORPUS / "VERSION").read_text(encoding="utf8").strip()
               if (CORPUS / "VERSION").exists() else "unrecorded")
    denied = denylist()

    t0 = time.time()
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst = sqlite3.connect(str(out))
    dst.executescript(SCHEMA)

    seen = kept = skipped_kind = skipped_denied = 0
    batch: list[tuple] = []
    try:
        for chunk_id, blob in con.execute(
                "select chunk_id, blob from chunks where doc_type='case_law'"):
            seen += 1
            b = json.loads(blob)
            kind = (b.get("paragraph_type") or "").strip()
            if kind not in ATTRIBUTABLE:
                skipped_kind += 1
                continue
            if chunk_id in denied:
                skipped_denied += 1
                continue
            text = " ".join((b.get("full_text") or "").split())
            if not text:
                continue
            batch.append((b.get("case_id"), b.get("case_name"), b.get("court"),
                          str(b.get("year") or ""), kind, chunk_id, text))
            kept += 1
            if len(batch) >= 5000:
                dst.executemany("insert into paras values (?,?,?,?,?,?,?)", batch)
                batch.clear()
                print(f"  {kept:>7,} indexed  ({time.time() - t0:.0f}s)", flush=True)
            if args.limit and kept >= args.limit:
                break
        if batch:
            dst.executemany("insert into paras values (?,?,?,?,?,?,?)", batch)

        dst.executemany("insert into identity values (?,?)", [
            ("built_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
            ("source", str(src)),
            ("corpus_version", version),
            ("source_paragraphs", str(seen)),
            ("indexed_paragraphs", str(kept)),
            ("excluded_not_attributable", str(skipped_kind)),
            ("excluded_denylisted", str(skipped_denied)),
            ("attributable_kinds", ",".join(ATTRIBUTABLE)),
            ("partial", "yes" if args.limit else "no"),
        ])
        dst.commit()
    finally:
        con.close()
        dst.close()

    print()
    print(f"  source paragraphs      {seen:>9,}")
    print(f"  indexed                {kept:>9,}")
    print(f"  excluded, not ratio/reasoning/order  {skipped_kind:>9,}")
    print(f"  excluded, denylisted   {skipped_denied:>9,}")
    print(f"  corpus version         {version}")
    print(f"  built in {time.time() - t0:.0f}s -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
