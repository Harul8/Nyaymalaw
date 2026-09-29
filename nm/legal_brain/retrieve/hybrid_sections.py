"""HYBRID BARE-ACT SEARCH over the existing artefacts. LB-106 (owner, 29 September 2026).

WHAT IS REUSED, AS IT IS. Measured 29 September 2026:
  * `bareacts_v3.index` -- 414,710 vectors of 1,024, inner product on normalised
    vectors. 60 of 60 sampled passages, encoded with BAAI/bge-large-en-v1.5, find
    their own position first: that is the model it was built with, and vector n is
    passage n of the store.
  * `bareacts_v3_bm25s` -- the native BM25 index over the same 414,710 passages.
  * `chunks.db`, doc_type bare_act -- positions 0 to 414,709.
  * BAAI/bge-reranker-v2-m3 for reranking.
The earlier system's CODE is not reused (the project rule stands); this is the same
mechanism rebuilt behind `SectionSearchPort`.

WHAT IS NOT CARRIED -- the earlier system's recorded defects:
  * B-25: a summary gate chose five Acts before searching, so a governing Act that
    missed it was unrecoverable. Here every leg ranks the whole population and
    nothing is removed before ranking.
  * The type-priors table that sent Limitation Article 59 from rank 1 to 53: an
    unlisted passage type scored below every listed one. There are no priors.
  * B-05: a stale BM25 index answered for weeks. Here a lineage record states what
    the three members must hold, and a set that disagrees is refused at load.

THE SEARCH, for one dispute: the advocate's words and their similar wordings
(`understand.similar_words`), each to BM25 and to the vectors; the ranked lists merged
by reciprocal rank; the merged head reranked against every wording, the best score
counting; passages grouped into their sections; sections from Acts outside the curated
list, or not in force on the date, set aside and SAID; the rest read word for word
through the one reader of provisions (`read_provision`, S9) and returned as candidates:
ranked, with no support verdict, never the Act that governs.

HEAVY LIBRARIES ARE IMPORTED ONLY WHEN THE SEARCH FIRST RUNS, so the product and its
tests import this module on a machine without them; the search then says it did not
run, and why.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import struct
import threading
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Callable

from nm.legal_brain.retrieve.evidence_port import (
    Coverage,
    EvidenceResult,
    Finding,
    Origin,
)
from nm.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.legal_brain.retrieve.section_search_port import SectionSearch

log = logging.getLogger(__name__)

EMBED_MODEL = "BAAI/bge-large-en-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DIMENSIONS = 1024
DOC_TYPE = "bare_act"
#: The query instruction bge-large-en-v1.5's authors give for searching passages.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
LEG_DEPTH = 100      # each leg's list, for each wording
RERANK_POOL = 60     # the merged head the reranker judges
RRF_K = 60
MAX_WORDINGS = 7
RERANK_CHARS = 2000

#: The legal tokens the BM25 index was built with, beside the lowercase whitespace
#: split: "Section 138" is also `section_138`. A query must be cut the same way as the
#: passages were, or its words and the index's never meet.
_NGRAMS = (
    re.compile(r"\bsection\s+\d+[a-z]{0,3}\b", re.I),
    re.compile(r"\bart(?:icle)?\.?\s+\d+[a-z]{0,3}\b", re.I),
    re.compile(r"\border\s+[ivx]+\s+rule\s+\d+\b", re.I),
    re.compile(r"\bair\s+\d{4}\s+(?:sc|hc|all|bom|cal|del|mad|kar|ker|gau|p&h)\s+\d+\b", re.I),
    re.compile(r"\(?\d{4}\)?\s+\(?\d+\)?\s+scc\s+\d+\b", re.I),
    re.compile(r"\b(?:ipc|crpc|cpc|ibc|sarfaesi|fema|cgst|sgst|igst|gst|ni\s+act|hma|hindu\s+marriage"
               r"|special\s+marriage|companies\s+act|negotiable\s+instruments|consumer\s+protection"
               r"|arbitration(?:\s+and\s+conciliation)?)\b", re.I),
)


class Unavailable(RuntimeError):
    """The search cannot run: a library, a model or a consistent artefact set is missing."""


def bm25_tokens(text: str) -> list[str]:
    """The index's own tokenisation: lowercase whitespace split plus legal n-grams."""
    text = text or ""
    return text.lower().split() + [
        m.group(0).lower().replace(" ", "_").replace(".", "")
        for pattern in _NGRAMS for m in pattern.finditer(text)]


def like(pattern: str, value: str) -> bool:
    """SQLite LIKE, exactly as the evidence adapter reads the same manifest patterns:
    `%` any run, `_` any one character, ASCII case-insensitive. An exact key, never a
    similarity (CLAUDE.md section 5)."""
    regex = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in pattern)
    return re.fullmatch(regex, value or "", re.IGNORECASE | re.DOTALL) is not None


def fused(lists: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion: each list adds 1/(k + rank) for every position it holds.
    A position on no list scores nothing; none is removed."""
    scores: dict[int, float] = {}
    for ranked in lists:
        for rank, position in enumerate(ranked):
            scores[position] = scores.get(position, 0.0) + 1.0 / (k + rank + 1)
    return scores


def faiss_header(path: Path) -> tuple[bytes, int, int]:
    """(kind, dimensions, vectors) from a FAISS flat index's own header."""
    with path.open("rb") as fh:
        head = fh.read(16)
    if len(head) < 16:
        raise Unavailable(f"{path.name} is not a readable vector index")
    return head[:4], struct.unpack("<i", head[4:8])[0], struct.unpack("<q", head[8:16])[0]


@dataclass(frozen=True)
class Passage:
    position: int
    act_id: str
    act_name: str
    section: str
    text: str


def check_lineage(record: dict, vector_store: Path) -> list[str]:
    """What stops this artefact set being searched, from its lineage record. Empty when
    the record, the three members and the model agree.

    The record's sha256 is taken by the lineage job; each load checks the index's size
    and header, the BM25 count and the passage count, which a rebuild, an append or a
    swap cannot leave unchanged.
    """
    problems: list[str] = []
    if record.get("schema") != 1 or record.get("doc_type") != DOC_TYPE:
        return ["the lineage record is not one this search reads"]
    if record.get("model") != EMBED_MODEL:
        problems.append(f"the index was recorded as built with {record.get('model')!r}, "
                        f"and the search encodes with {EMBED_MODEL!r}")
    if record.get("dimensions") != DIMENSIONS:
        problems.append(f"the record gives {record.get('dimensions')} dimensions, not {DIMENSIONS}")
    passages = record.get("passages")
    vec = record.get("vector_index") or {}
    index = vector_store / str(vec.get("path") or "")
    if not index.is_file():
        problems.append(f"the vector index {index.name} is missing")
    else:
        kind, dims, vectors = faiss_header(index)
        if kind != b"IxFI" or dims != DIMENSIONS:
            problems.append(f"{index.name} is not a {DIMENSIONS}-dimension inner-product index")
        if vectors != vec.get("vectors") or vectors != passages:
            problems.append(f"{index.name} holds {vectors:,} vectors; the record gives "
                            f"{vec.get('vectors')} and {passages} passages")
        if index.stat().st_size != vec.get("bytes"):
            problems.append(f"{index.name} changed after its lineage was recorded")
    bm = record.get("bm25") or {}
    params = vector_store / str(bm.get("path") or "") / "params.index.json"
    try:
        parameters = params.read_bytes()
        docs = json.loads(parameters).get("num_docs")
        params_hash = hashlib.sha256(parameters).hexdigest()
    except (OSError, ValueError):
        docs, params_hash = None, None
    if docs is None:
        problems.append("the BM25 index or its parameters are missing")
    elif docs != bm.get("num_docs") or docs != passages:
        problems.append(f"the BM25 index holds {docs:,} documents; the record gives "
                        f"{bm.get('num_docs')} and {passages} passages")
    if params_hash is not None and params_hash != bm.get("params_sha256"):
        problems.append("the BM25 parameters changed after their lineage was recorded")
    store = record.get("passage_store") or {}
    db = vector_store / str(store.get("path") or "")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            count, top = con.execute("select count(*), max(pos) from chunks where doc_type=?",
                                     (DOC_TYPE,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        count, top = None, None
    if count is None:
        problems.append("the passage store could not be read")
    elif count != passages or top != passages - 1:
        problems.append(f"the passage store holds {count:,} passages up to position {top}; "
                        f"the record gives {passages}")
    return problems


class _Parts:
    """The loaded members. One lock serialises the models: one advocate's turn at a
    time is the served load, and a GPU shared between two encodes gains nothing."""

    def __init__(self, index, bm25, db: Path, embedder, reranker, passages: int) -> None:
        self.index, self.bm25, self.embedder, self.reranker = index, bm25, embedder, reranker
        self.db, self.count = db, passages
        self.lock = threading.Lock()

    def vector_top(self, wordings: list[str], depth: int) -> list[list[int]]:
        import numpy as np

        with self.lock:
            vectors = self.embedder.encode([QUERY_INSTRUCTION + w for w in wordings],
                                           normalize_embeddings=True, convert_to_numpy=True)
            _, found = self.index.search(np.asarray(vectors, dtype="float32"), depth)
        # A position past the passage store is a vector with no passage: dropped, never
        # mapped onto a neighbour.
        return [[int(p) for p in row if 0 <= p < self.count] for row in found]

    def bm25_top(self, wording: str, depth: int) -> list[int]:
        import numpy as np

        vocab = self.bm25.vocab_dict
        tokens = [t for t in bm25_tokens(wording) if t in vocab]
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        n = min(depth, len(scores))
        top = np.argpartition(-scores, n - 1)[:n]
        return [int(p) for p in top[np.argsort(-scores[top])] if scores[p] > 0 and p < self.count]

    def passages(self, positions: list[int]) -> list[Passage]:
        if not positions:
            return []
        con = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            marks = ",".join("?" for _ in positions)
            rows = con.execute(
                f"select pos, act_id, section_number, blob from chunks "
                f"where doc_type=? and pos in ({marks})", (DOC_TYPE, *positions)).fetchall()
        finally:
            con.close()
        held = {}
        for pos, act_id, section, blob in rows:
            try:
                doc = json.loads(blob)
            except ValueError:
                continue
            held[int(pos)] = Passage(int(pos), act_id or "", str(doc.get("act_name") or act_id),
                                     str(section or ""), str(doc.get("full_text") or ""))
        return [held[p] for p in positions if p in held]

    def rerank(self, wordings: list[str], texts: list[str]) -> list[float]:
        """Each passage's best score against any wording of the dispute."""
        if not texts:
            return []
        pairs = [(w, t[:RERANK_CHARS]) for t in texts for w in wordings]
        with self.lock:
            scores = self.reranker.predict(pairs, batch_size=32, show_progress_bar=False)
        n = len(wordings)
        return [float(max(scores[i * n:(i + 1) * n])) for i in range(len(texts))]


class HybridSections:
    """`SectionSearchPort` over the existing bare-act artefacts."""

    def __init__(self, vector_store: Path, manifest: Manifest, *,
                 read_provision: Callable[[str, str, date], EvidenceResult],
                 models: Path, lineage: Path, device: str | None = None,
                 parts: _Parts | None = None) -> None:
        self._dir = Path(vector_store)
        self._manifest = manifest
        self._read = read_provision
        self._models = Path(models)
        self._lineage = Path(lineage)
        self._device = device
        self._parts = parts
        self._refused: str | None = None
        self._loading = threading.Lock()

    # ------------------------------------------------------------- state ---

    def readiness(self) -> str:
        if self._refused:
            return f"unavailable: {self._refused}"
        return "ready" if self._parts is not None else "not loaded"

    def warm(self) -> None:
        """Load the index and the models before the first search -- the server starts
        this in the background. A refusal is kept, and `readiness` says it."""
        try:
            self._load()
        except Unavailable:
            pass

    def _load(self) -> _Parts:
        if self._parts is not None:
            return self._parts
        if self._refused:
            raise Unavailable(self._refused)
        with self._loading:
            if self._parts is not None:
                return self._parts
            try:
                self._parts = self._open()
            except Unavailable as exc:
                self._refused = str(exc)
                raise
            except Exception as exc:  # noqa: BLE001 -- a failed load is said, and logged in full
                log.exception("the bare-act search could not be loaded")
                self._refused = f"the search could not be loaded ({type(exc).__name__}: {exc})"
                raise Unavailable(self._refused) from exc
        return self._parts

    def _open(self) -> _Parts:
        try:
            record = json.loads(self._lineage.read_text(encoding="utf8"))
        except (OSError, ValueError):
            raise Unavailable("the search index has no lineage record, so what built it "
                              "cannot be checked") from None
        problems = check_lineage(record, self._dir)
        if problems:
            raise Unavailable("the search index was refused: " + "; ".join(problems))
        folder = self._models / EMBED_MODEL.replace("/", "__")
        judge = self._models / RERANK_MODEL.replace("/", "__")
        if not folder.is_dir() or not judge.is_dir():
            raise Unavailable("the search models are not installed on this machine")
        try:
            import bm25s
            import faiss
            import torch
            from sentence_transformers import CrossEncoder, SentenceTransformer
        except ImportError as exc:
            raise Unavailable(f"the search libraries are not installed ({exc.name})") from None
        device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
        half = {"torch_dtype": torch.float16} if device == "cuda" else {}
        index = faiss.read_index(str(self._dir / record["vector_index"]["path"]))
        bm25 = bm25s.BM25.load(str(self._dir / record["bm25"]["path"]), mmap=True)
        embedder = SentenceTransformer(str(folder), device=device, model_kwargs=half,
                                       local_files_only=True)
        reranker = CrossEncoder(str(judge), device=device, max_length=512, model_kwargs=half,
                                local_files_only=True)
        return _Parts(index, bm25, self._dir / record["passage_store"]["path"], embedder,
                      reranker, int(record["passages"]))

    # ------------------------------------------------------------ search ---

    def _entry(self, act_id: str) -> ManifestEntry | None:
        """The curated Act this store belongs to, by the manifest's own patterns -- or
        None when no entry or more than one claims it. Never a guess."""
        owners = [e for e in self._manifest.entries
                  if any(like(pattern, act_id) for pattern in e.act_patterns)]
        return owners[0] if len(owners) == 1 else None

    def search(self, words: str, *, similar: tuple[str, ...] = (), as_of: date,
               limit: int = 5) -> SectionSearch:
        words = " ".join((words or "").split())
        if not words:
            return SectionSearch(False, note="there were no words to search with")
        try:
            parts = self._load()
        except Unavailable as exc:
            return SectionSearch(False, note=str(exc))
        wordings = list(dict.fromkeys(
            [words, *(" ".join(s.split()) for s in similar if s and s.strip())]))[:MAX_WORDINGS]
        lists = [parts.bm25_top(w, LEG_DEPTH) for w in wordings]
        lists += parts.vector_top(wordings, LEG_DEPTH)
        scores = fused(lists)
        head = sorted(scores, key=lambda p: (-scores[p], p))[:RERANK_POOL]
        passages = parts.passages(head)
        judged = parts.rerank(wordings, [p.text for p in passages])

        best: dict[tuple[str, str], tuple[float, Passage]] = {}
        for passage, score in zip(passages, judged, strict=True):
            key = (passage.act_id, passage.section)
            if key not in best or score > best[key][0]:
                best[key] = (score, passage)
        ranked = sorted(best.values(), key=lambda row: -row[0])

        candidates: list[Finding] = []
        outside: list[str] = []
        not_in_force: list[str] = []
        unread: list[str] = []
        for rank, (score, passage) in enumerate(ranked, start=1):
            if len(candidates) >= limit:
                break
            label = f"{passage.act_name} {_section_label(passage.section)}"
            entry = self._entry(passage.act_id)
            if entry is None:
                outside.append(label)
                continue
            if not entry.in_force_on(as_of):
                not_in_force.append(f"{entry.act_name} {_section_label(passage.section)}")
                continue
            read = self._read(entry.act_name, passage.section, as_of)
            if read.coverage is not Coverage.ANSWERED or not read.findings:
                unread.append(f"{entry.act_name} {_section_label(passage.section)}")
                continue
            if any(f.ref == read.findings[0].ref for f in candidates):
                continue
            candidates.append(as_candidate(read.findings[0], score, rank, len(ranked)))
        note = (f"The bare acts were searched by meaning and by words with {len(wordings)} "
                f"wording(s) of this dispute; {len(passages)} passages were reranked and "
                f"{len(candidates)} section(s) from the curated Acts are shown as candidates, "
                "ranked by relevance, not established as the law that governs.")
        if not_in_force:
            note += (f" Set aside as not in force on {as_of.isoformat()}: "
                     f"{'; '.join(dict.fromkeys(not_in_force))}.")
        if outside:
            note += (" Ranked but outside the curated Acts, so not read: "
                     f"{'; '.join(list(dict.fromkeys(outside))[:4])}.")
        if unread:
            note += f" Ranked but could not be read: {'; '.join(dict.fromkeys(unread))}."
        return SectionSearch(True, tuple(candidates), note)


def _section_label(section: str) -> str:
    text = (section or "").replace("_", " ")
    return text if text.lower().startswith(("article", "order", "schedule")) else f"s.{text}"


def as_candidate(finding: Finding, score: float, rank: int, ranked: int) -> Finding:
    """A section the search found, as a CANDIDATE: searched, with its rank's score as the
    confidence and no support verdict, its limit written into its basis."""
    return replace(
        finding, origin=Origin.SEARCHED, confidence=round(float(score), 4), supports=None,
        binding_reason=(f"{finding.binding_reason}; found by search for this dispute, ranked "
                        f"{rank} of {ranked} -- whether it governs has not been assessed"))
