"""Build the judgment store anew: every judgment cut on its own paragraphs, each passage carrying what is known of it. AN OFFLINE JOB;
THE OWNER RUNS IT. THE READ AND INDEX STAGES WRITE ONLY A NEW FOLDER AND A CANDIDATE LINEAGE RECORD; THE SWAP STAGE IS THE ONLY ONE THAT
CHANGES WHAT THE SEARCH READS, AND IT RUNS WITH THE SERVER STOPPED.

    .venv-arrive\\Scripts\\python.exe pipeline\\build_judgments_v3.py --stage read    (cut, name, cite: passages.jsonl, a report)
    .venv-arrive\\Scripts\\python.exe pipeline\\build_judgments_v3.py --stage index   (store, vectors, word index, candidate lineage)
    .venv-arrive\\Scripts\\python.exe pipeline\\build_judgments_v3.py --stage swap    (the search reads the new store; the old record kept)

`--only 300 --seed 5 --out judgments_trial` builds a store of 300 judgments chosen at random beside the real one, to look at.

Plan AN.45 (owner, 5-7 Nov 2026). What it does, and why:

  * CUT (pipeline/cut_judgments.py). The judgments were cut into fixed lengths numbered in the order cut: "paragraph 12" was often not the
    court's, and a quarter of the passages began mid-sentence. Now a paragraph is the court's, with its printed number; one longer than
    the search model reads is split at sentence ends under the same number; a judgment printing no numbers is cut at sentence ends into
    passages called "passage N". Not a word is changed.
  * COURT. Every Andhra Pradesh High Court judgment is a Telangana judgment (citation_contracts.court_title); the court's own name stays
    in court_as_filed.
  * CITATIONS. The judgment's own citations are read from its heading and confirmed against the case index; each passage lists the cases
    it cites by reporter citation, with the held judgment each leads to, and the provisions it cites with the Act they name and which
    held Act that is - exactly, or by an alias the owner has CHECKED (pipeline/act_aliases.json). What is not decided stays as written.
  * KINDS. The old passages carried a kind (facts, arguments, reasoning, ratio, order ...) from an automatic labeller. A new passage takes
    the kind of the old passage whose words it overlaps most; else "unknown". The kinds still unknown are for a separate model reading
    (pipeline/classify_judgment_paragraphs.py), which needs the owner's word on its cost.
  * VECTORS from the passage's words alone, the word index likewise, with the frozen legal tokens of citation_contracts.bm25_tokens. The
    vectors are made in half precision (3.3 times faster; see make_encoder) unless --single-precision is given.

Long (hours: the vectors), changes the library, and the owner runs it: nothing in the repository does.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sqlite3
import sys
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.shared.citation_contracts import (  # noqa: E402
    ActResolver, act_alias_index, bm25_tokens, cited_provisions, court_title, find_reporter_citations,
)
from pipeline import cut_judgments  # noqa: E402

DOC_TYPE = "case_law"
EMBED_MODEL = "BAAI/bge-large-en-v1.5"
DIMENSIONS = 1024
#: The word index's parameters, as the Act store's and the earlier judgment store's were built.
BM25_PARAMS = {"k1": 1.5, "b": 0.75, "delta": 0.5, "method": "robertson", "idf_method": "robertson"}
#: A passage the search model would not read whole: the cutter keeps ten tokens clear of 512; more than this is a fault to report.
MODEL_TOKENS = 510
#: How many judgments a worker takes at a time.
BATCH = 40
KINDS = ("facts", "arguments", "argument", "reasoning", "ratio", "order", "headnote", "holding", "issue", "other", "unknown")
_SPEC = re.compile(r"[A-Za-z0-9]+")
_COUNTS = re.compile(r"\[\s*Cites\s+(\d+)\s*,\s*Cited by\s+(\d+)\s*\]")


@dataclass(frozen=True)
class Places:
    """Where everything is. The defaults are the project's own; a test gives its own."""
    raw_data: Path = ROOT / "legal_database" / "raw_data"
    vector_store: Path = ROOT / "legal_database" / "vector_store"
    old_store: Path = ROOT / "legal_database" / "vector_store" / "chunks.db"
    identity: Path = ROOT / ".nm" / "identity.db"
    register: Path = ROOT / "pipeline" / "instrument_copies.json"
    aliases: Path = ROOT / "pipeline" / "act_aliases.json"
    retrieval: Path = ROOT / ".nm" / "retrieval"
    models: Path = ROOT / ".nm" / "models"

    def folder(self, out: str) -> Path:
        return self.vector_store / out

    def candidate(self, out: str) -> Path:
        return self.retrieval / "candidates" / f"{out}.lineage.json"

    @property
    def live(self) -> Path:
        return self.retrieval / "judgments.lineage.json"


# ----------------------------------------------------------------------------- what is known of a judgment

def _words(text: str) -> str:
    return "".join(_SPEC.findall(text.lower()))


def heading_citations(raw: str) -> list[str]:
    """The judgment's own citations as its heading prints them: the reporter citations in its "Equivalent citations" line and its
    "CITATION" block - never in what the judgment says after."""
    lines = raw[:4000].replace("\r\n", "\n").split("\n")
    found: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        region = ""
        if stripped.lower().startswith("equivalent citations"):
            region = stripped.partition(":")[2]
        elif stripped.upper().startswith("CITATION:"):
            block = [stripped.partition(":")[2]]
            for after in lines[index + 1:index + 5]:
                if not after.strip() or after.strip().endswith(":"):
                    break
                block.append(after)
            region = "\n".join(block)
        for citation in find_reporter_citations(region):
            text = " ".join(citation.text.split())
            if text not in found:
                found.append(text)
    return found


def heading_counts(raw: str) -> tuple[int | None, int | None]:
    """The "[Cites N, Cited by M]" the heading opens with, or None, None."""
    match = _COUNTS.search(raw[:300].replace("\n", " "))
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)


def inherited_kinds(raw: str, passages, old: list[tuple[str, str]]) -> list[str]:
    """The kind of each new passage: that of the old passage its words overlap most. Old passages are placed in the raw text by the
    letters and digits of their first words (91% of them were placed in a trial), the new ones by where they stand; a new passage no
    placed old passage overlaps is "unknown"."""
    if not passages or not old:
        return ["unknown"] * len(passages)
    norm = _words(raw)
    placed, hint = [], 0
    for text, kind in old:
        words = _words(text)
        if len(words) < 30:
            continue
        at = norm.find(words[:60], hint)
        if at < 0:
            at = norm.find(words[:60])
        if at < 0:
            continue
        placed.append((at, at + len(words), kind))
        hint = max(hint, at)
    if not placed:
        return ["unknown"] * len(passages)
    placed.sort()
    starts = [item[0] for item in placed]
    longest = max(end - start for start, end, _ in placed)
    offsets = sorted({0, *(p.start for p in passages), *(p.end for p in passages)})
    before, count, previous = {}, 0, 0
    for offset in offsets:
        count += len(re.sub(r"[^A-Za-z0-9]", "", raw[previous:offset]))
        before[offset] = count
        previous = offset
    kinds = []
    for passage in passages:
        low, high = before[passage.start], before[passage.end]
        tally: dict[str, int] = {}
        first = max(0, bisect_right(starts, low - longest) - 1)
        for start, end, kind in placed[first:]:
            if start >= high:
                break
            overlap = min(end, high) - max(start, low)
            if overlap > 0:
                tally[kind] = tally.get(kind, 0) + overlap
        kinds.append(max(tally, key=lambda kind: (tally[kind], -list(tally).index(kind))) if tally else "unknown")
    return kinds


class Library:
    """What the read stage consults: the case index (each case's own citation keys and which case a citation leads to), the Acts the
    library holds, and the owner's checked aliases."""

    def __init__(self, places: Places, aliases: str = "checked"):
        con = sqlite3.connect(f"file:{places.identity}?mode=ro", uri=True)
        self.own_keys: dict[str, set[str]] = {}
        self.key_cases: dict[str, list[str]] = {}
        for key, case_id in con.execute("select citation_key, case_id from citations"):
            self.own_keys.setdefault(case_id, set()).add(key)
            self.key_cases.setdefault(key, []).append(case_id)
        # The case index names a judgment's file from the CaseLaws folder ("Supreme Court\1950\X.txt"); the earlier store, and this one,
        # from the raw data folder ("CaseLaws\Supreme Court\1950\X.txt").
        self.cases = {row[0]: (row[0], row[1] if row[1].startswith("CaseLaws") else f"CaseLaws\\{row[1]}", *row[2:])
                      for row in con.execute("select case_id, source_file, court, year, title from cases order by source_file")}
        con.close()
        register = json.loads(places.register.read_text(encoding="utf-8"))["documents"]
        held = sorted({entry["group"] for entry in register.values() if entry.get("role") == "kept" and entry.get("group")})
        index = {}
        if aliases != "none":
            document = json.loads(places.aliases.read_text(encoding="utf-8"))
            index = act_alias_index(document, checked_only=(aliases == "checked"))
        self.aliases = index
        self.resolver = ActResolver(held, index)


def case_fields(entry, old_rows, raw) -> dict:
    """The fields of a judgment its passages share: from its first old passage where it has one, else the case index and its heading."""
    case_id, source_file, court, year, title = entry
    first = old_rows[0] if old_rows else {}
    cites, cited_by = heading_counts(raw)
    return {
        "case_id": case_id,
        "case_name": first.get("case_name") or title or case_id,
        "court": first.get("court") or court or "",
        "year": first.get("year") if first.get("year") not in (None, "") else (str(year) if year else ""),
        "cites_count": first.get("cites_count") if isinstance(first.get("cites_count"), int) else cites,
        "cited_by_count": first.get("cited_by_count") if isinstance(first.get("cited_by_count"), int) else cited_by,
        "source_file": source_file,
    }


def judgment_rows(entry, raw: str, old_rows: list[dict], library: Library, count: Callable[[list[str]], list[int]]):
    """One judgment as passage rows and a report. Pure: reads nothing of the disk."""
    case = case_fields(entry, old_rows, raw)
    case_id, year = case["case_id"], case["year"]
    result = cut_judgments.cut(raw, count)
    report = {"case_id": case_id, "source_file": case["source_file"], "numbering": result.numbering, "paragraphs": result.paragraphs,
              "passages": len(result.passages), "old_passages": len(old_rows), "problems": [], "notes": list(result.notes)}
    if not result.passages:
        report["problems"].append("the judgment has no text to cut")
        return [], report
    texts = [p.text for p in result.passages]
    over = [n for n in count(texts) if n > MODEL_TOKENS]
    if over:
        report["problems"].append(f"{len(over)} passage(s) pass {MODEL_TOKENS} tokens after the cut")
    if not old_rows:
        report["notes"].append("not in the earlier store: every kind is unknown")
    kinds = inherited_kinds(raw, result.passages, [(row["full_text"], row.get("paragraph_type") or "unknown") for row in old_rows])
    judged = int(year) if str(year).isdigit() else None
    own = []
    keys_own = library.own_keys.get(case_id, set())
    for text in heading_citations(raw):
        keys = [key for citation in find_reporter_citations(text) for key in citation.keys]
        own.append({"text": text, "confirmed": bool(keys_own.intersection(keys))})
    report["own_citations"] = [len(own), sum(item["confirmed"] for item in own)]
    rows, cited_cases, cited_sections, resolved = [], 0, 0, Counter()
    for passage, kind in zip(result.passages, kinds):
        cases = []
        for citation in find_reporter_citations(passage.text):
            held = sorted({other for key in citation.keys for other in library.key_cases.get(key, ())} - {case_id})
            if held or not keys_own.intersection(citation.keys):
                cases.append({"citation": " ".join(citation.text.split()), "case_ids": held})
        sections = []
        for item in cited_provisions(passage.text, library.aliases):
            answer = library.resolver.resolve(item["act_as_written"], judged)
            sections.append({"reference": item["reference"], "through": item["through"], "act_as_written": item["act_as_written"],
                             "state": answer["state"], "keys": answer["keys"], "named": answer["named"]})
            resolved[answer["state"]] += 1
        cited_cases += len(cases)
        cited_sections += len(sections)
        rows.append({"chunk_id": f"{case_id}_P{passage.order:04d}", "case_id": case_id, "atom_type": kind, "blob": {
            "chunk_id": f"{case_id}_P{passage.order:04d}", "case_id": case_id, "case_name": case["case_name"],
            "citation": " | ".join(item["text"] for item in own), "own_citations": own,
            "court": court_title(case["court"]), "court_as_filed": case["court"], "year": case["year"],
            "cites_count": case["cites_count"], "cited_by_count": case["cited_by_count"],
            "paragraph_num": passage.paragraph, "part": passage.part, "parts": passage.parts, "section": passage.section,
            "passage_no": passage.order, "locator": passage.locator, "numbering": result.numbering,
            "paragraph_type": kind, "sections_cited": sections, "cited_cases": cases, "keywords": [],
            "source_file": case["source_file"], "full_text": passage.text, "doc_type": DOC_TYPE}})
    report["kinds"] = dict(Counter(kinds))
    report["cited_cases"], report["sections_cited"] = cited_cases, dict(resolved)
    return rows, report


# ----------------------------------------------------------------------------- the read stage

_STATE: dict = {}


def _tokenizer_counter(models: Path):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(models / EMBED_MODEL.replace("/", "__")), local_files_only=True)
    return lambda texts: [len(ids) for ids in tokenizer(texts, add_special_tokens=False)["input_ids"]]


def _start_worker(places: Places, aliases: str, counter=None):
    _STATE["places"] = places
    _STATE["library"] = Library(places, aliases)
    _STATE["count"] = counter or _tokenizer_counter(places.models)
    _STATE["old"] = sqlite3.connect(f"file:{places.old_store}?mode=ro", uri=True) if places.old_store.is_file() else None


def _old_rows(case_id: str) -> list[dict]:
    con = _STATE["old"]
    if con is None:
        return []
    return [json.loads(blob) for (blob,) in con.execute(
        "select blob from chunks where doc_type=? and case_id=? order by pos", (DOC_TYPE, case_id))]


def _do_batch(entries):
    places, out = _STATE["places"], []
    for entry in entries:
        path = places.raw_data / entry[1].replace("\\", "/")
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            out.append(([], {"case_id": entry[0], "source_file": entry[1], "numbering": None, "passages": 0,
                             "problems": [f"the raw text could not be read: {type(exc).__name__}"]}))
            continue
        out.append(judgment_rows(entry, raw, _old_rows(entry[0]), _STATE["library"], _STATE["count"]))
    return out


def read_stage(places: Places, out: str, *, only: int | None, seed: int, aliases: str, workers: int, counter=None) -> dict:
    """Cut every judgment (or a random `only`), write passages.jsonl and judgments.json to the new folder."""
    import random

    library = Library(places, aliases)
    entries = list(library.cases.values())
    if only:
        random.Random(seed).shuffle(entries)
        entries = sorted(entries[:only], key=lambda entry: entry[1])
    folder = places.folder(out)
    folder.mkdir(parents=True, exist_ok=True)
    batches = [entries[i:i + BATCH] for i in range(0, len(entries), BATCH)]
    reports, total, kinds, states = [], 0, Counter(), Counter()
    with (folder / "passages.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        def take(results):
            nonlocal total
            for rows, report in results:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                total += len(rows)
                reports.append(report)
                kinds.update(report.get("kinds", {}))
                states.update(report.get("sections_cited", {}))
        if workers <= 1:
            _start_worker(places, aliases, counter)
            for number, batch in enumerate(batches, 1):
                take(_do_batch(batch))
                if number % 50 == 0:
                    print(f"   {number}/{len(batches)} batches, {total:,} passages", flush=True)
        else:
            from concurrent.futures import ProcessPoolExecutor

            with ProcessPoolExecutor(max_workers=workers, initializer=_start_worker, initargs=(places, aliases)) as pool:
                for number, results in enumerate(pool.map(_do_batch, batches), 1):
                    take(results)
                    if number % 50 == 0:
                        print(f"   {number}/{len(batches)} batches, {total:,} passages", flush=True)
    problems = [(report["case_id"], problem) for report in reports for problem in report["problems"]]
    notes = [(report["case_id"], note) for report in reports for note in report.get("notes", ())]
    (folder / "judgments.json").write_text(json.dumps(reports, ensure_ascii=False), encoding="utf-8")
    (folder / "problems.json").write_text(json.dumps(problems, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {"judgments": len(reports), "passages": total, "printed": sum(r["numbering"] == "printed" for r in reports),
               "unnumbered": sum(r["numbering"] == "none" for r in reports), "without text": sum(not r["passages"] for r in reports),
               "not in the earlier store": sum(not r.get("old_passages") for r in reports), "kinds": dict(kinds),
               "sections cited, by what the Act resolved to": dict(states), "problems": len(problems), "notes": len(notes),
               "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "aliases": aliases}
    (folder / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


# ----------------------------------------------------------------------------- the index stage

def make_encoder(model, *, half: bool = True, batch_size: int = 32) -> Callable[[list[str]], "object"]:
    """texts -> unit vectors (float32) from a sentence-transformers model. In half precision the model runs about 3.3 times as fast on
    this machine's card (90 passages a second against 27, measured 7 Nov 2026 on 2,000 judgment passages) and its vectors are within
    0.9995 of the single-precision ones, the nearest ten passages of ten queries the same; they are made unit length again in single
    precision, so that a half-precision rounding never shows as a vector longer or shorter than one."""
    import numpy as np

    if half:
        model.half()

    def encode(texts):
        vectors = np.asarray(model.encode(texts, normalize_embeddings=False, batch_size=batch_size, convert_to_numpy=True,
                                          show_progress_bar=False), dtype="float32")
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return encode


def real_encoder(models: Path, *, half: bool = True):
    """The search model of the library (BAAI/bge-large-en-v1.5, from the local models folder), on the graphics card where there is one."""
    os.environ.pop("SSLKEYLOGFILE", None)
    import torch
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(str(models / EMBED_MODEL.replace("/", "__")), device="cuda" if torch.cuda.is_available() else "cpu",
                                local_files_only=True)
    return make_encoder(model, half=half and torch.cuda.is_available())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _passages(folder: Path):
    with (folder / "passages.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def write_passage_store(folder: Path, name: str) -> int:
    """passages.jsonl as the SQLite store the search reads: the earlier store's table, a row for every passage at the next position."""
    path = folder / name
    if path.exists():
        raise SystemExit(f"{path} exists; give a new folder rather than overwrite")
    con = sqlite3.connect(path)
    con.execute("create table chunks (doc_type text not null, pos integer not null, chunk_id text not null, act_id text, case_id text, "
                "parent_chunk_id text, atom_type text, section_number text, blob text not null, primary key (doc_type, pos))")
    batch, pos = [], 0
    for row in _passages(folder):
        batch.append((DOC_TYPE, pos, row["chunk_id"], None, row["case_id"], None, row["atom_type"], None,
                      json.dumps(row["blob"], ensure_ascii=False)))
        pos += 1
        if len(batch) == 50_000:
            con.executemany("insert into chunks values (?,?,?,?,?,?,?,?,?)", batch)
            batch.clear()
    if batch:
        con.executemany("insert into chunks values (?,?,?,?,?,?,?,?,?)", batch)
    con.execute("create index idx_chunks_chunk_id on chunks(chunk_id)")
    con.execute("create index idx_chunks_doc_case on chunks(doc_type, case_id)")
    con.execute("create index idx_chunks_doc_act on chunks(doc_type, act_id)")
    con.execute("create index idx_chunks_doc_parent on chunks(doc_type, parent_chunk_id)")
    con.commit()
    con.execute("analyze")
    con.commit()
    count, first, last = con.execute("select count(*), min(pos), max(pos) from chunks where doc_type=?", (DOC_TYPE,)).fetchone()
    con.close()
    if (count, first, last) != (pos, 0, pos - 1):
        raise SystemExit("the passage store does not hold every passage in order")
    return pos


def encode_texts(texts, encode: Callable[[list[str]], "object"], total: int, path: Path, progress: Path, stamp: dict,
                 block: int = 20_000) -> Path:
    """Every text's vector (text n is vector n), a block at a time, into one file; a run stopped part-way goes on from the last block
    written, when the progress file records the same stamp - what the texts are made from - and starts again when it does not."""
    import numpy as np

    done = 0
    if path.exists() and progress.exists():
        saved = json.loads(progress.read_text(encoding="utf-8"))
        if {k: saved.get(k) for k in stamp} == stamp:
            done = saved["done"]
    mode = "r+" if path.exists() and done else "w+"
    vectors = np.memmap(path, dtype="float32", mode=mode, shape=(total, DIMENSIONS))
    batch, start = [], 0
    for text in texts:
        batch.append(text)
        if len(batch) == block:
            if start >= done:
                vectors[start:start + len(batch)] = np.asarray(encode(batch), dtype="float32")
                vectors.flush()
                progress.write_text(json.dumps({**stamp, "done": start + len(batch)}), encoding="utf-8")
                print(f"   {start + len(batch):,}/{total:,} vectors", flush=True)
            start += len(batch)
            batch = []
    if batch and start >= done:
        vectors[start:start + len(batch)] = np.asarray(encode(batch), dtype="float32")
        vectors.flush()
        progress.write_text(json.dumps({**stamp, "done": total}), encoding="utf-8")
    del vectors
    return path


def texts_fingerprint(folder: Path) -> str:
    """A hash of every passage's words, in order, and of nothing else. The vectors are made from the words alone, so they are the same for
    any reading of the judgments that cuts them the same way, whatever the reading attached to each passage (the Acts an alias names,
    a kind, a court's name) - which is what changes when the owner checks an Act alias and the read stage is run again."""
    digest = hashlib.sha256()
    for row in _passages(folder):
        words = row["blob"]["full_text"].encode("utf-8")
        digest.update(len(words).to_bytes(8, "big"))
        digest.update(words)
    return digest.hexdigest()


def encode_all(folder: Path, encode: Callable[[list[str]], "object"], total: int, block: int = 20_000) -> Path:
    """Every passage's vector, a block at a time, into one file; a run stopped part-way goes on from the last block written.

    THE RESUME IS KEYED ON THE WORDS, NOT ON THE FILE (owner, 7 Nov 2026: the Act aliases are still to be checked, and checking them means the
    read stage is run again and writes a passages file that differs in what each passage cites while its words are the same). Kept with
    --keep-vectors, an earlier run's vectors serve any later folder whose passages have the same words in the same order: copy
    vectors.f32 and vectors.progress.json into the new folder before the index stage and it encodes nothing. One changed word anywhere
    and it starts again."""
    stamp = {"passages": total, "texts_sha256": texts_fingerprint(folder), "dimensions": DIMENSIONS}
    return encode_texts((row["blob"]["full_text"] for row in _passages(folder)), encode, total, folder / "vectors.f32",
                        folder / "vectors.progress.json", stamp, block)


def build_word_index(folder: Path, name: str, build: Callable | None = None) -> int:
    """The word index over every passage: each passage's tokens become ids as they are cut (a token's id is shared, so a long judgment
    store is not held as strings), then bm25s builds from the ids."""
    import bm25s

    vocab: dict[str, int] = {}
    ids = []
    for row in _passages(folder):
        ids.append([vocab.setdefault(token, len(vocab)) for token in bm25_tokens(row["blob"]["full_text"])])
    target = folder / name
    if target.exists():
        raise SystemExit(f"{target} exists; give a new folder rather than overwrite")
    retriever = bm25s.BM25(**BM25_PARAMS)
    retriever.index(bm25s.tokenization.Tokenized(ids=ids, vocab=vocab), show_progress=False)
    retriever.save(str(target))
    return int(json.loads((target / "params.index.json").read_text(encoding="utf-8"))["num_docs"])


def index_stage(places: Places, out: str, encode: Callable, *, keep_vectors: bool = False) -> dict:
    import faiss
    import numpy as np

    from nm.Archives.legal_brain.retrieve.hybrid_sections import check_lineage

    folder = places.folder(out)
    store = f"{out}.db"
    total = write_passage_store(folder, store)
    print(f"   {total:,} passages in the store", flush=True)
    vectors_path = encode_all(folder, encode, total)
    vectors = np.memmap(vectors_path, dtype="float32", mode="r", shape=(total, DIMENSIONS))
    index = faiss.IndexFlatIP(DIMENSIONS)
    for start in range(0, total, 100_000):
        index.add(np.ascontiguousarray(vectors[start:start + 100_000]))
    index_path = folder / f"{out}.index"
    if index_path.exists():
        raise SystemExit(f"{index_path} exists; give a new folder rather than overwrite")
    faiss.write_index(index, str(index_path))
    words = f"{out}_bm25s"
    documents = build_word_index(folder, words)
    if documents != total:
        raise SystemExit("the word index does not hold every passage")
    # Verification: a sample of passages encoded again must be the vectors stored.
    sample = list(range(0, total, max(1, total // 60)))[:60]
    wanted = set(sample)
    texts = {pos: row["blob"]["full_text"] for pos, row in enumerate(_passages(folder)) if pos in wanted}
    again = np.asarray(encode([texts[pos] for pos in sample]), dtype="float32")
    similarity = (again * np.stack([index.reconstruct(pos) for pos in sample])).sum(axis=1)
    del vectors, index
    record = {"schema": 1, "doc_type": DOC_TYPE, "model": EMBED_MODEL, "dimensions": DIMENSIONS,
              "metric": "inner product on normalised vectors", "passages": total,
              "vector_index": {"path": f"{out}/{index_path.name}", "vectors": total, "bytes": index_path.stat().st_size,
                               "sha256": _sha256(index_path)},
              "bm25": {"path": f"{out}/{words}", "num_docs": total, "params_sha256": _sha256(folder / words / "params.index.json")},
              "passage_store": {"path": f"{out}/{store}", "count": total, "max_pos": total - 1},
              "verified": {"sampled": len(sample), "same_vector": int((similarity > 0.99).sum()),
                           "lowest_similarity": round(float(similarity.min()), 4), "mean_similarity": round(float(similarity.mean()), 4),
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
              "recorded_by": "pipeline/build_judgments_v3.py",
              "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "built_from": {"decisions": "Owner decisions D90-D93 (plan AN.44) and AN.45, 5-7 Nov 2026",
                             "summary": json.loads((folder / "summary.json").read_text(encoding="utf-8"))}}
    problems = check_lineage(record, places.vector_store, doc_type=DOC_TYPE)
    candidate = places.candidate(out)
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(record, indent=2), encoding="utf-8")
    if not keep_vectors:
        vectors_path.unlink(missing_ok=True)
        (folder / "vectors.progress.json").unlink(missing_ok=True)
    return {"passages": total, "verified": record["verified"], "lineage_problems": problems, "candidate": str(candidate)}


# ----------------------------------------------------------------------------- the swap

def server_is_up(port: int = 8071) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def swap_stage(places: Places, out: str, *, running: Callable[[], bool] = server_is_up) -> dict:
    """The search reads the new judgment store from now on: see swap_record."""
    return swap_record(places.candidate(out), places.live, places.vector_store, DOC_TYPE, running=running)


def swap_record(candidate: Path, live: Path, vector_store: Path, doc_type: str, *,
                running: Callable[[], bool] = server_is_up) -> dict:
    """The search reads the new store from now on: the candidate lineage record becomes the live one, the earlier kept beside it as
    .before-<time>. Refuses while the server is up or the candidate does not agree with the files it names."""
    from nm.Archives.legal_brain.retrieve.hybrid_sections import check_lineage

    if not candidate.is_file():
        raise SystemExit(f"{candidate} is not there: run the index stage first")
    record = json.loads(candidate.read_text(encoding="utf-8"))
    problems = check_lineage(record, vector_store, doc_type=doc_type)
    if problems:
        raise SystemExit("the new store does not agree with its record; nothing swapped: " + "; ".join(problems))
    if running():
        raise SystemExit("the server is up; stop it first, then swap - nothing swapped")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    aside = live.with_name(f"{live.name}.before-{stamp}")
    os.replace(live, aside)
    staged = live.with_name(live.name + ".new")
    staged.write_text(json.dumps({**record, "swapped_in": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2),
                      encoding="utf-8")
    os.replace(staged, live)
    return {"live": str(live), "earlier": str(aside), "passages": record["passages"]}


# ----------------------------------------------------------------------------- the command

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", choices=("read", "index", "swap"), required=True)
    parser.add_argument("--out", default="judgments_v3", help="the new folder under legal_database/vector_store")
    parser.add_argument("--only", type=int, help="a trial: this many judgments chosen at random")
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--aliases", choices=("checked", "draft", "none"), default="checked",
                        help="which of the owner's Act aliases resolve a short form (checked: only those the owner has checked)")
    parser.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 4) - 2)))
    parser.add_argument("--single-precision", action="store_true",
                        help="make the vectors in single precision (about 12 hours instead of 4; the vectors differ by under 0.0005)")
    parser.add_argument("--keep-vectors", action="store_true")
    args = parser.parse_args(argv)
    places = Places()
    if args.stage == "read":
        print(json.dumps(read_stage(places, args.out, only=args.only, seed=args.seed, aliases=args.aliases, workers=args.workers),
                         indent=1))
    elif args.stage == "index":
        print(json.dumps(index_stage(places, args.out, real_encoder(places.models, half=not args.single_precision),
                                     keep_vectors=args.keep_vectors), indent=1))
    else:
        print(json.dumps(swap_stage(places, args.out), indent=1))
        print("Start the server again to search the new store.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
