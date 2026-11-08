"""Correct Acts the store holds: each read again as the Act store's build reads it, its passages put in place of those held. AN
OFFLINE JOB; THE OWNER RUNS IT, WITH THE SERVER STOPPED.

    .venv-arrive\\Scripts\\python.exe pipeline\\correct_held_acts.py --act "<the Act's id in the store>" --dry-run

Plan AN.32 (owner, 5 Nov 2026: "do 2"). The store the search reads was built by pipeline/build_acts_v4.py on 20-21 Oct 2026.
Two Acts are held wrongly. India Code's section records number the Urban Land (Ceiling and Regulation) Repeal Act, 1999 1, 3,
4, 5, 6 where the Act prints 1 to 5, and an answer cited its sections one too high; the build now takes the printed numbers
(build_acts_v4.printed_numbers). The Legislative Councils Act, 1957 prints its sections 9 and 10 with their first sub-section
on the heading's line, and the reader kept them as words of section 8; it reads that form now (append_bare_acts). A whole new
build would re-read every Act and take hours; this job changes only the Acts it is given.

For the Acts given, each by its id in the store:
  1. it refuses unless the passage store, the vector index and the word index agree with the lineage record, each Act is held
     in one run of positions, and - unless it is a dry run - the three can be replaced (a running server holds them open);
  2. it reads each Act from where the build's record says it came from, as the build reads it, and cuts its passages as the
     build cut them - with the mark the store gives an Act not in force - and refuses passages that do not hold together;
  3. it prints each Act's sections as held and as read now, and how many of its passages stay word for word as they are.
     A DRY RUN STOPS HERE AND CHANGES NOTHING;
  4. it encodes the Acts' passages with the index's own model; writes a new passage store with each Act's passages in place of
     those held (every later passage moved by the difference), a new vector index (every other passage's vector as it was)
     and a new word index over every passage, all beside the current ones;
  5. only then it swaps the three in, keeping the earlier ones beside them as '.before-<time>', and rewrites the lineage record
     with what was corrected, keeping the earlier record beside it as '.before-<time>' too.

To undo: stop the server, and put each '.before-<time>' member back under its own name - the passage store, the vector index,
the word index and the lineage record.

Saved conversations are not changed: an answer keeps the words of the passages it read, and opening the whole Act from one says
that the held law has changed since. Start the server again after.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import build_acts_v4 as build  # noqa: E402 - the build's own reading and cutting
from pipeline.embed_acts_wording import wording  # noqa: E402 - what the Acts' vectors are made from once they are made from wording
from pipeline.append_bare_acts import (  # noqa: E402
    DOC_TYPE, LINEAGE, VECTOR_STORE, Store, _can_swap, _real_bm25, _real_encoder, _sha256, bm25_tokens, check_lineage,
)


def held_record(store: Store, act_id: str) -> dict:
    """The store's own record of an Act: where it came from and how it stands."""
    record = json.loads(store.lineage.read_text(encoding="utf8"))
    db = store.vector_store / record["passage_store"]["path"]
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        found = con.execute("select record from acts where act_id=?", (act_id,)).fetchone()
    con.close()
    if found is None:
        raise RuntimeError(f"the store holds no Act {act_id!r}; nothing corrected")
    return json.loads(found[0])


def read_again(held: dict, selection: list[dict], words) -> tuple[list[dict], dict]:
    """An Act as the build reads it now, from the build's own entry for it: (its passages, what it reads as)."""
    entries = [entry for entry in selection
               if (entry.get("jurisdiction"), entry.get("india_act_id"), entry.get("file"))
               == (held.get("jurisdiction"), held.get("india_act_id"), held.get("file"))]
    if len(entries) != 1:
        raise RuntimeError(f"{held['act_id']}: the build's selection has {len(entries)} entries for it; nothing corrected")
    act, articles, record = build.read_entry(entries[0], words)
    if act.act_id != held["act_id"]:
        raise RuntimeError(f"{held['act_id']} reads now as {act.act_id!r}; nothing corrected")
    rows = build.cited(build.passages_for(act)) + build.article_rows(act, articles)
    problems = build.check(rows)
    if problems:
        raise RuntimeError(f"{held['act_id']}: its passages do not hold together; nothing corrected: " + "; ".join(problems[:5]))
    return rows, {"sections": [(section.number, section.title) for section in act.sections],
                  "renumbered": record.get("renumbered", [])}


def correct(replacements: dict[str, list[dict]], store: Store, *, encode: Callable[[list[str]], "object"],
            build_bm25: Callable[[list[list[str]], Path], int], dry_run: bool = False) -> dict:
    """Put each Act's passages (replacements: act_id -> its rows, as the build cuts them) in place of those the store holds, in
    the order that leaves the search refusing - never mis-mapping - if it stops part-way."""
    import faiss
    import numpy as np

    if not replacements:
        raise RuntimeError("no Act to correct")
    record = json.loads(store.lineage.read_text(encoding="utf8"))
    problems = check_lineage(record, store.vector_store)
    if problems:
        raise RuntimeError("the current set is not consistent; nothing corrected: " + "; ".join(problems))
    base = int(record["passages"])
    db = store.vector_store / record["passage_store"]["path"]
    index_path = store.vector_store / record["vector_index"]["path"]
    bm25_dir = store.vector_store / record["bm25"]["path"]
    wal = db.with_name(db.name + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError(f"{wal.name} holds writes not yet in the store; nothing corrected")
    spans, summary = {}, {}
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        for act_id, rows in replacements.items():
            identifiers = [row["chunk_id"] for row in rows]
            if not rows or len(identifiers) != len(set(identifiers)) or any(
                    row["blob"]["act_id"] != act_id for row in rows):
                raise RuntimeError(f"{act_id}: its passages are empty, repeat an identifier or name another Act; "
                                   "nothing corrected")
            held = con.execute("select pos, chunk_id, blob from chunks where doc_type=? and act_id=? order by pos",
                               (DOC_TYPE, act_id)).fetchall()
            positions = [pos for pos, _, _ in held]
            if not positions or positions != list(range(positions[0], positions[-1] + 1)):
                raise RuntimeError(f"{act_id}: not held in one run of positions; nothing corrected")
            blobs = [json.loads(blob) for _, _, blob in held]
            # The mark the store gives every passage of an Act not in force (P21) - as held.
            marks = {blob.get("standing") for blob in blobs}
            if len(marks) != 1:
                raise RuntimeError(f"{act_id}: its passages are marked differently; nothing corrected")
            mark = marks.pop()
            for row in rows:
                if mark is not None:
                    row["blob"]["standing"] = mark
            same = {(chunk_id, blob["full_text"]) for (_, chunk_id, _), blob in zip(held, blobs)}
            spans[act_id] = (positions[0], positions[-1] + 1)
            summary[act_id] = {"held": len(held), "now": len(rows),
                               "unchanged": sum((row["chunk_id"], row["blob"]["full_text"]) in same for row in rows),
                               "sections_held": [blob.get("section_number") for blob in blobs
                                                 if blob.get("atom_type") == "section_head"],
                               "sections_now": [row["section_number"] for row in rows if row["atom_type"] == "section_head"]}
    con.close()
    ordered = sorted(spans, key=lambda act_id: spans[act_id][0])
    if any(spans[a][1] > spans[b][0] for a, b in zip(ordered, ordered[1:])):
        raise RuntimeError("two of the Acts given share positions; nothing corrected")
    total = base + sum(len(replacements[a]) - (spans[a][1] - spans[a][0]) for a in ordered)
    if dry_run:
        return {"acts": summary, "passages": total, "dry_run": True}
    _can_swap(index_path, bm25_dir, db)
    new_db, new_index = db.with_name(db.name + ".new"), index_path.with_name(index_path.name + ".new")
    new_bm25 = bm25_dir.with_name(bm25_dir.name + ".new")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        # THE VECTORS: every other passage's as it was, each Act's encoded afresh, in the new order - from what the index's vectors are
        # made from: the passage as shown, or, once the Acts' vectors were swapped for those made from the passages' own wording
        # (plan AN.45 D91; the record says vector_text "wording"), the wording. A mixed index would put a corrected Act beside the rest
        # by a different measure.
        text_of = wording if record.get("vector_text") == "wording" else (lambda text: text)
        vectors = {act_id: np.asarray(encode([text_of(row["blob"]["full_text"]) for row in replacements[act_id]]), dtype="float32")
                   for act_id in ordered}
        index = faiss.read_index(str(index_path))
        if index.ntotal != base or any(v.shape != (len(replacements[a]), index.d) for a, v in vectors.items()):
            raise RuntimeError("the new vectors do not fit the index; nothing corrected")
        held_vectors, dimensions = index.reconstruct_n(0, base), index.d
        del index
        fresh, cursor = faiss.IndexFlatIP(dimensions), 0
        for act_id in ordered:
            start, end = spans[act_id]
            fresh.add(held_vectors[cursor:start])
            fresh.add(vectors[act_id])
            cursor = end
        fresh.add(held_vectors[cursor:])
        del held_vectors
        if fresh.ntotal != total:
            raise RuntimeError("the new index does not hold every passage; nothing corrected")
        faiss.write_index(fresh, str(new_index))
        del fresh
        # THE PASSAGES: a copy of the store, each Act's in place of those held, last Act first so that the earlier positions stand.
        shutil.copyfile(db, new_db)
        with sqlite3.connect(new_db) as con:
            for act_id in reversed(ordered):
                start, end = spans[act_id]
                rows = replacements[act_id]
                shift = len(rows) - (end - start)
                con.execute("delete from chunks where doc_type=? and act_id=?", (DOC_TYPE, act_id))
                if shift:
                    # Through negative positions, so that no position is taken twice on the way.
                    con.execute("update chunks set pos=-(pos+?)-1 where doc_type=? and pos>=?", (shift, DOC_TYPE, end))
                    con.execute("update chunks set pos=-pos-1 where doc_type=? and pos<0", (DOC_TYPE,))
                con.executemany(
                    "insert into chunks (doc_type, pos, chunk_id, act_id, case_id, parent_chunk_id, atom_type, section_number, "
                    "blob) values (?,?,?,?,?,?,?,?,?)",
                    [(DOC_TYPE, start + offset, row["chunk_id"], act_id, None, row["parent_chunk_id"], row["atom_type"],
                      row["section_number"], json.dumps(row["blob"], ensure_ascii=False)) for offset, row in enumerate(rows)])
                kept = con.execute("select record from acts where act_id=?", (act_id,)).fetchone()
                if kept is not None:
                    entry = json.loads(kept[0])
                    entry["passages"], entry["sections"] = len(rows), len(summary[act_id]["sections_now"])
                    entry["corrected"] = [*entry.get("corrected", ()), {
                        "at": at, "plan": "AN.32", "passages_held": summary[act_id]["held"],
                        "sections_held": summary[act_id]["sections_held"]}]
                    con.execute("update acts set record=? where act_id=?", (json.dumps(entry, ensure_ascii=False), act_id))
            count, first, last = con.execute("select count(*), min(pos), max(pos) from chunks where doc_type=?",
                                             (DOC_TYPE,)).fetchone()
            if (count, first, last) != (total, 0, total - 1):
                raise RuntimeError("the new passage store does not hold every passage in order; nothing corrected")
            texts = [json.loads(blob).get("full_text", "") for (blob,) in con.execute(
                "select blob from chunks where doc_type=? order by pos", (DOC_TYPE,))]
        con.close()
        # THE WORDS: rebuilt over every passage, in the new order.
        if new_bm25.exists():
            shutil.rmtree(new_bm25)
        if build_bm25([bm25_tokens(text) for text in texts], new_bm25) != total:
            raise RuntimeError("the rebuilt word index does not hold every passage; nothing corrected")
    except BaseException:
        new_db.unlink(missing_ok=True)
        new_index.unlink(missing_ok=True)
        shutil.rmtree(new_bm25, ignore_errors=True)
        raise
    # THE SWAP. The earlier members stay beside the new ones, under a name of their own.
    moved = []
    try:
        for member, new in ((db, new_db), (index_path, new_index), (bm25_dir, new_bm25)):
            aside = member.with_name(f"{member.name}.before-{stamp}")
            os.replace(member, aside)
            moved.append((member, aside))
            os.replace(new, member)
    except OSError as exc:
        for member, aside in reversed(moved):
            if member.exists():
                shutil.rmtree(member) if member.is_dir() else member.unlink()
            os.replace(aside, member)
        raise RuntimeError(f"the swap failed ({exc}); the earlier store, index and word index are back in place") from exc
    record = {**record, "passages": total,
              "vector_index": {**record["vector_index"], "vectors": total, "bytes": index_path.stat().st_size,
                               "sha256": _sha256(index_path)},
              "bm25": {**record["bm25"], "num_docs": total, "params_sha256": _sha256(bm25_dir / "params.index.json")},
              "passage_store": {**record["passage_store"], "count": total, "max_pos": total - 1},
              "corrected": [*record.get("corrected", ()), {"acts": summary, "at": at, "plan": "AN.32",
                                                            "before": f".before-{stamp}"}]}
    problems = check_lineage(record, store.vector_store)
    if problems:
        raise RuntimeError("corrected, but the set does not agree - the search will refuse it until the '.before-"
                           f"{stamp}' members are put back: " + "; ".join(problems))
    shutil.copyfile(store.lineage, store.lineage.with_name(f"{store.lineage.name}.before-{stamp}"))
    store.lineage.write_text(json.dumps(record, indent=2), encoding="utf8")
    return {"acts": summary, "passages": total, "before": f".before-{stamp}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--act", action="append", required=True, help="the Act's id as the store holds it")
    ap.add_argument("--dry-run", action="store_true", help="read and compare; change nothing")
    args = ap.parse_args(argv)
    store = Store(VECTOR_STORE, LINEAGE)
    record = json.loads(store.lineage.read_text(encoding="utf8"))
    folder = (store.vector_store / record["passage_store"]["path"]).parent
    selection = json.loads((folder / "selection.json").read_text(encoding="utf-8"))
    words = build.vocabulary()
    replacements = {}
    for act_id in dict.fromkeys(args.act):
        held = held_record(store, act_id)
        rows, read = read_again(held, selection, words)
        replacements[act_id] = rows
        print(f"\n{held['title']} ({held['jurisdiction']}), {held['source']}:")
        print(f"  sections now: " + "; ".join(f"{number} {title[:50]}" for number, title in read["sections"]))
        for change in read["renumbered"]:
            print(f"  India Code's section {change['india_code']} is the Act's section {change['printed']}")
    summary = correct(replacements, store, encode=(lambda texts: []) if args.dry_run else _real_encoder(),
                      build_bm25=_real_bm25, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    if not args.dry_run:
        print("Start the server again to search the corrected Acts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
