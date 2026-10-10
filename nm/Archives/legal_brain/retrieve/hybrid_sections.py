"""HYBRID SEARCH over the existing artefacts: bare-act sections here, judgment paragraphs
in `hybrid_judgments` -- ONE MECHANISM FOR BOTH. LB-106 (owner, 29 September 2026; judgments
added 30 September 2026: "both acts and judgements should be retrieved same way").

WHAT IS REUSED, AS IT IS. Measured 29 September 2026:
  * `bareacts_v3.index` -- 414,710 vectors of 1,024, inner product on normalised
    vectors. 60 of 60 sampled passages, encoded with BAAI/bge-large-en-v1.5, find
    their own position first: that is the model it was built with, and vector n is
    passage n of the store.
  * `bareacts_v3_bm25s` -- the native BM25 index over the same 414,710 passages.
  * `chunks.db`, doc_type bare_act -- positions 0 to 414,709.
  * BAAI/bge-reranker-v2-m3 for reranking.
The earlier system's recorded defects are not carried (below); its mechanism is rebuilt
behind `SectionSearchPort`.

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

THE TWO MODELS LOAD ONCE (`SearchModels`) and both searches use them, behind one lock:
two copies on one GPU would buy nothing but the memory they take.

HEAVY LIBRARIES ARE IMPORTED ONLY WHEN A SEARCH FIRST RUNS, so the product and its tests
import this module on a machine without them; the search then says it did not run, and
why.
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

from nm.Archives.legal_brain.retrieve.evidence_port import (
    Coverage,
    EvidenceResult,
    Finding,
    Origin,
)
from nm.Archives.legal_brain.retrieve.manifest_sources import Manifest, ManifestEntry
from nm.Archives.legal_brain.retrieve.section_search_port import SectionSearch

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
MAX_WORDINGS = 9  # full dispute plus up to eight anchored phrase/variant queries
RERANK_CHARS = 2000
#: SQLite's own ceiling on bound values, kept well under: a read of the whole fused
#: list is made in batches of this size.
_BATCH = 900

#: The legal tokens the BM25 index was built with, beside the lowercase whitespace
#: split: "Section 138" is also `section_138`. A query must be cut the same way as the
#: passages were, or its words and the index's never meet -- so the index builds that
#: import this and the live search share one owner of the tokenisation.
from nm.shared.citation_contracts import bm25_tokens  # noqa: E402,F401


class Unavailable(RuntimeError):
    """The search cannot run: a library, a model or a consistent artefact set is missing."""


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


def check_lineage(record: dict, vector_store: Path, *, doc_type: str = DOC_TYPE) -> list[str]:
    """What stops this artefact set being searched, from its lineage record. Empty when
    the record, the three members and the model agree.

    The record's sha256 is taken by the lineage job; each load checks the index's size
    and header, the BM25 count and the passage count, which a rebuild, an append or a
    swap cannot leave unchanged.

    VECTORS PAST THE LAST PASSAGE are allowed only as the record counts them
    (`vectors_without_passage`): the lineage job measured them, they map to nothing,
    and the search drops every position past the passage store. Measured 30 September
    2026: the judgment index holds 63 such vectors after its 1,015,780 passages.
    """
    problems: list[str] = []
    if record.get("schema") != 1 or record.get("doc_type") != doc_type:
        return ["the lineage record is not one this search reads"]
    if record.get("model") != EMBED_MODEL:
        problems.append(f"the index was recorded as built with {record.get('model')!r}, "
                        f"and the search encodes with {EMBED_MODEL!r}")
    if record.get("dimensions") != DIMENSIONS:
        problems.append(f"the record gives {record.get('dimensions')} dimensions, not {DIMENSIONS}")
    passages = record.get("passages")
    tail = record.get("vectors_without_passage", 0)
    vec = record.get("vector_index") or {}
    index = vector_store / str(vec.get("path") or "")
    if not isinstance(tail, int) or tail < 0:
        problems.append("the record's count of vectors without a passage is not a count")
        tail = 0
    if not index.is_file():
        problems.append(f"the vector index {index.name} is missing")
    else:
        kind, dims, vectors = faiss_header(index)
        if kind != b"IxFI" or dims != DIMENSIONS:
            problems.append(f"{index.name} is not a {DIMENSIONS}-dimension inner-product index")
        if (vectors != vec.get("vectors") or not isinstance(passages, int)
                or vectors != passages + tail):
            problems.append(f"{index.name} holds {vectors:,} vectors; the record gives "
                            f"{vec.get('vectors')}, {passages} passages and {tail} "
                            "vector(s) without a passage")
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
                                     (doc_type,)).fetchone()
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


class SearchModels:
    """THE TWO MODELS, LOADED ONCE, with the one lock both searches use.

    One advocate's turn at a time is the served load, and a GPU shared between two
    encodes gains nothing -- so every encode and every rerank, of either search, takes
    the same lock. A refusal is kept, and each search says it."""

    def __init__(self, folder: Path, *, device: str | None = None) -> None:
        self._folder = Path(folder)
        self._device = device
        self._loaded: tuple | None = None
        self._refused: str | None = None
        self._loading = threading.Lock()

    def load(self) -> tuple:
        """(embedder, reranker, lock), or `Unavailable` saying why not."""
        if self._loaded is not None:
            return self._loaded
        if self._refused:
            raise Unavailable(self._refused)
        with self._loading:
            if self._loaded is not None:
                return self._loaded
            try:
                self._loaded = self._open()
            except Unavailable as exc:
                self._refused = str(exc)
                raise
        return self._loaded

    def _open(self) -> tuple:
        folder = self._folder / EMBED_MODEL.replace("/", "__")
        judge = self._folder / RERANK_MODEL.replace("/", "__")
        if not folder.is_dir() or not judge.is_dir():
            raise Unavailable("the search models are not installed on this machine")
        try:
            import torch
            from sentence_transformers import CrossEncoder, SentenceTransformer
        except ImportError as exc:
            raise Unavailable(f"the search libraries are not installed ({exc.name})") from None
        device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
        half = {"torch_dtype": torch.float16} if device == "cuda" else {}
        embedder = SentenceTransformer(str(folder), device=device, model_kwargs=half,
                                       local_files_only=True)
        reranker = CrossEncoder(str(judge), device=device, max_length=512, model_kwargs=half,
                                local_files_only=True)
        return embedder, reranker, threading.Lock()


class _Parts:
    """One collection's loaded members, and the shared models behind their lock."""

    def __init__(self, index, bm25, db: Path, embedder, reranker, passages: int, *,
                 doc_type: str = DOC_TYPE, lock: threading.Lock | None = None) -> None:
        self.index, self.bm25, self.embedder, self.reranker = index, bm25, embedder, reranker
        self.db, self.count, self.doc_type = db, passages, doc_type
        self.lock = lock or threading.Lock()

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
        held = {}
        for pos, (_chunk, doc, act_id, section) in self._read(positions).items():
            held[pos] = Passage(pos, act_id or "", str(doc.get("act_name") or act_id),
                                str(section or ""), str(doc.get("full_text") or ""))
        return [held[p] for p in positions if p in held]

    def rows(self, positions: list[int]) -> dict[int, tuple[str, dict]]:
        """Each stored passage at these positions: its chunk id and its stored record."""
        return {pos: (chunk, doc) for pos, (chunk, doc, _act, _section)
                in self._read(positions).items()}

    def _read(self, positions: list[int]) -> dict[int, tuple]:
        if not positions:
            return {}
        con = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        held: dict[int, tuple] = {}
        try:
            for start in range(0, len(positions), _BATCH):
                batch = positions[start:start + _BATCH]
                marks = ",".join("?" for _ in batch)
                for pos, chunk, act_id, section, blob in con.execute(
                        f"select pos, chunk_id, act_id, section_number, blob from chunks "
                        f"where doc_type=? and pos in ({marks})", (self.doc_type, *batch)):
                    try:
                        doc = json.loads(blob)
                    except ValueError:
                        continue
                    held[int(pos)] = (str(chunk or ""), doc, act_id, section)
        finally:
            con.close()
        return held

    def rerank(self, wordings: list[str], texts: list[str]) -> list[float]:
        """Each passage's best score against any wording of the dispute."""
        if not texts:
            return []
        pairs = [(w, t[:RERANK_CHARS]) for t in texts for w in wordings]
        with self.lock:
            scores = self.reranker.predict(pairs, batch_size=32, show_progress_bar=False)
        n = len(wordings)
        return [float(max(scores[i * n:(i + 1) * n])) for i in range(len(texts))]


def open_collection(vector_store: Path, lineage: Path, doc_type: str, models: SearchModels,
                    *, mapped: bool = False) -> _Parts:
    """One collection, opened only once its lineage record agrees with what is on disk.

    `mapped` leaves the vectors on disk, paged in by the operating system as they are
    searched, instead of copying them into the process -- for an index the size of the
    judgment collection (4.2 GB)."""
    try:
        record = json.loads(Path(lineage).read_text(encoding="utf8"))
    except (OSError, ValueError):
        raise Unavailable("the search index has no lineage record, so what built it "
                          "cannot be checked") from None
    problems = check_lineage(record, vector_store, doc_type=doc_type)
    if problems:
        raise Unavailable("the search index was refused: " + "; ".join(problems))
    embedder, reranker, lock = models.load()
    try:
        import bm25s
        import faiss
    except ImportError as exc:
        raise Unavailable(f"the search libraries are not installed ({exc.name})") from None
    flags = (faiss.IO_FLAG_MMAP_IFC | faiss.IO_FLAG_READ_ONLY) if mapped else 0
    index = faiss.read_index(str(vector_store / record["vector_index"]["path"]), flags)
    bm25 = bm25s.BM25.load(str(vector_store / record["bm25"]["path"]), mmap=True)
    return _Parts(index, bm25, vector_store / record["passage_store"]["path"], embedder,
                  reranker, int(record["passages"]), doc_type=doc_type, lock=lock)


class Searching:
    """What both searches share: load once, keep a refusal, say the state."""

    _what = "the search"

    def __init__(self, parts: _Parts | None) -> None:
        self._parts = parts
        self._refused: str | None = None
        self._loading = threading.Lock()

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
                log.exception("%s could not be loaded", self._what)
                self._refused = f"the search could not be loaded ({type(exc).__name__}: {exc})"
                raise Unavailable(self._refused) from exc
        return self._parts

    def _open(self) -> _Parts:
        raise NotImplementedError

    @staticmethod
    def wordings(words: str, similar: tuple[str, ...]) -> list[str]:
        return list(dict.fromkeys(
            [words, *(" ".join(s.split()) for s in similar if s and s.strip())]))[:MAX_WORDINGS]

    @staticmethod
    def ranked(parts: _Parts, wordings: list[str]) -> list[int]:
        """Every position either leg ranked for any wording, merged by reciprocal rank."""
        lists = [parts.bm25_top(w, LEG_DEPTH) for w in wordings]
        lists += parts.vector_top(wordings, LEG_DEPTH)
        scores = fused(lists)
        return sorted(scores, key=lambda p: (-scores[p], p))


class HybridSections(Searching):
    """`SectionSearchPort` over the existing bare-act artefacts."""

    _what = "the bare-act search"

    def __init__(self, vector_store: Path, manifest: Manifest, *,
                 read_provision: Callable[[str, str, date], EvidenceResult],
                 models: "Path | SearchModels", lineage: Path, device: str | None = None,
                 parts: _Parts | None = None) -> None:
        super().__init__(parts)
        self._dir = Path(vector_store)
        self._manifest = manifest
        self._read = read_provision
        self._models = (models if isinstance(models, SearchModels)
                        else SearchModels(Path(models), device=device))
        self._lineage = Path(lineage)

    def _open(self) -> _Parts:
        return open_collection(self._dir, self._lineage, DOC_TYPE, self._models)

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
        wordings = self.wordings(words, similar)
        head = self.ranked(parts, wordings)[:RERANK_POOL]
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


def as_candidate(finding: Finding, score: float, rank: int, ranked: int, *,
                 undecided: str = "whether it governs has not been assessed") -> Finding:
    """A passage the search found, as a CANDIDATE: searched, with its rank's score as the
    confidence and no support verdict, its limit written into its basis."""
    return replace(
        finding, origin=Origin.SEARCHED, confidence=round(float(score), 4), supports=None,
        binding_reason=(f"{finding.binding_reason}; found by search for this dispute, ranked "
                        f"{rank} of {ranked} -- {undecided}"))
