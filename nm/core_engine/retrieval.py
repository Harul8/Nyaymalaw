"""Local candidate search over the held bare-act and judgment passages.

Search ranks possible sources; it does not decide what law governs or what a
judgment holds. Every returned quotation is read back from the passage store.
The two indexes and the local models load only when a search is requested.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import struct
import threading
import traceback
from collections import OrderedDict
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, contextmanager, nullcontext
from functools import lru_cache
from pathlib import Path
from typing import Protocol

EMBED_MODEL = "BAAI/bge-large-en-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DIMENSIONS = 1024
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
LEG_DEPTH = 80
PER_QUERY_POOL = 60
RESULTS_PER_KIND = 6
#: Measured 14 Oct 2026 on the test matters, live search: ranking the first 40 provision
#: positions kept 53 of 63 answer-key provisions in the six (50 when all ~170 were ranked)
#: at a third of the search time; ranking the first 100 judgment positions kept 15 of 25
#: key judgments (16 when all were ranked) in under half the time. A pre-ordered first 20
#: judgments kept 14 and missed the owner's fixed criterion of 15.
RANK_DEPTH = {"provision": 40, "judgment": 100}
RRF_K = 60
#: v10 (owner decision P30, 20 Oct 2026): the reranker reads a question and each passage in
#: one reading of up to RERANK_TOKENS tokens. v9 records, of the same shape, replay unchanged.
CONTRACT = "hybrid_retrieval_v10"
#: v9 (owner decision P32, 20 Oct 2026): each returned provision is read whole, and with it
#: the provisions its Act links to it in its own words and the provisions beside it, as
#: connected candidates for the pick. v8 records replay unchanged.
CONNECTED_CONTRACT = "hybrid_retrieval_v9"
#: v8 (owner decision, 14 Oct 2026): the reranker reads only the strongest candidates,
#: the first RANK_DEPTH positions of each corpus's fused shortlist. v7 records replay.
RANK_DEPTH_CONTRACT = "hybrid_retrieval_v8"
#: A section longer than this is read in part, the parts search found with its opening
#: (P32, at the line P30 and P31 draw, about 8,000 tokens): 276 of 66,684 held sections.
WHOLE_SECTION_CHARACTERS = 32000
#: Links shown each way for one returned provision (99% of held sections name at most 9 and
#: are named by at most 6); the rest are counted in the record, never dropped silently.
LINKS_EACH_WAY = 10
#: Acts whose links are kept in memory once worked out.
LINKED_ACTS = 32
#: How a connected provision is connected: it is named, or it is beside.
CONNECTIONS = ("names", "beside")
#: v7 (owner decision, 14 Oct 2026): judgment paragraphs are ordered by what makes them
#: usable as authority (_judgment_order). v6 records replay unchanged.
JUDGMENT_ORDER_CONTRACT = "hybrid_retrieval_v7"
#: v6 (owner decision, 12 Oct 2026): word and vector search inside the held Acts a
#: research plan names join each formulation's legs, and the provision order blends the
#: reranker's order with the shortlist's order. v5 records replay unchanged.
NAMED_CONTRACT = "hybrid_retrieval_v6"
RERANK_ORDER_CONTRACT = "hybrid_retrieval_v5"
PARENT_STORE_CONTRACT = "hybrid_retrieval_v4"
PREVIOUS_CONTRACT = "hybrid_retrieval_v3"
PARENT_TREE_CONTRACT = "hybrid_retrieval_v2"
LEGACY_CONTRACT = "hybrid_retrieval_v1"
MAX_RERANK_PAIRS = 4096
#: P30 (owner, 20 Oct 2026): a question and its passage are read together in one reading of
#: up to RERANK_TOKENS tokens instead of 512, so a passage is cut into pieces only when it alone
#: is longer (a handful of held passages); the question side, the legal question with its
#: search phrases, is read in windows of QUESTION_TOKENS. Against the 14 Oct answer keys
#: (round 2, offline): provisions about level, two more key judgments among the six, about the
#: same search time.
RERANK_TOKENS = 8192
QUESTION_TOKENS = 380
#: Pairs are scored shortest first, at most RERANK_BATCH_PAIRS pairs and RERANK_BATCH_CHARACTERS
#: characters a batch: a short pair is not padded to a long one's length, and a batch of long ones
#: stays below the graphics card's memory (P30: the batch where speed stops improving).
RERANK_BATCH_PAIRS = 16
RERANK_BATCH_CHARACTERS = 32000
WINDOW_OVERLAP = 32
COPY_REGISTER_SCHEMA = 1
MAX_CONTEXT_SEGMENTS = 500
#: A provision's stored parts, by its Act and section number, in stored order. The "+" keeps
#: the order from choosing the index: the Acts store holds no planner statistics, and
#: ordering by the stored position walked every stored Act passage for each lookup (1.75 s
#: on average across 353,689 passages, 20 Oct 2026) where the Act-and-section index finds
#: the few parts at once. The rows and their order are the same.
SECTION_PARTS = ("select pos from chunks where doc_type=? and act_id=? and section_number=? "
                 "order by +pos limit ?")
#: One stored part by its identity within its Act. Without planner statistics the store walked
#: every passage of the Act through its Act-and-section index to find one part; the "+" leaves
#: the part-identity index to find it (20 Oct 2026: 3.5 ms to 0.13 ms a lookup in the CPC, most
#: of the time reading a section whole took). The rows are the same.
PART_BY_ID = "select pos from chunks where +doc_type=? and +act_id=? and chunk_id=? limit 2"
#: A matter's questions searched at once (owner, 20 Oct 2026: step 1). The reranker on the
#: graphics card bounds a matter's search (62 s of the 13 questions of the first live run of
#: answering dispute by dispute); four at a time searched them in 89 s instead of about 150 s,
#: every result the same (in trials two at a time were slower than four, and six no faster).
SIDE_BY_SIDE = 4
#: Copies of each model's tokenizer that searches running side by side borrow to prepare text.
TOKENIZER_COPIES = SIDE_BY_SIDE
log = logging.getLogger(__name__)


def _log_stage_failure(kind, stage, exc, query_id=None):
    """Make a degraded search stage diagnosable without changing what is saved.

    The saved issue keeps its existing reason, so search records, replay and the
    writer's and reviewer's inputs are unchanged. A failure that leaves only an
    exception type in the record cannot be diagnosed afterwards: on 10 October 2026
    a reranking attempt failed and its exact replay succeeded, with nothing left to
    say why. An expected SearchUnavailable is logged with its code-authored message,
    which names the underlying cause. Anything else may be a programming error and
    is logged at ERROR with its traceback frames but without its message, so an
    advocate's words in a query or passage cannot reach the log.
    """
    where = f"{kind} {stage}" + (f" for {query_id}" if query_id else "")
    if isinstance(exc, SearchUnavailable):
        log.warning("Search stage degraded: %s: %s", where, exc)
    else:
        log.error("Search stage failed unexpectedly: %s: %s\n%s", where, type(exc).__name__,
                  "".join(traceback.format_tb(exc.__traceback__)))

# The index's own tokenisation has one owner, shared with the index builds: a
# query cut differently from the built index silently stops meeting its words.
from nm.shared.citation_contracts import (  # noqa: E402
    bm25_tokens, bind_provision_key, instrument_candidates, ProvisionKeyState, provision_key_binder,
    provisions_named, statute_own_title,
)


class SearchUnavailable(RuntimeError):
    """The local collection cannot be searched reliably."""


class _ContextGap(SearchUnavailable):
    """A readable, connected source survives incomplete or ambiguous neighbours."""

    def __init__(self, reason, context):
        super().__init__(reason)
        self.context = context


class _ParentObject(dict):
    """Preserve ambiguous JSON fields without disabling independent records."""

    def __init__(self, pairs=()):
        super().__init__()
        self.duplicates = set()
        for key, value in pairs:
            if key in self:
                self.duplicates.add(key)
            else:
                self[key] = value


class Collection(Protocol):
    """Injectable boundary for one indexed corpus."""

    def lexical(self, query: str, depth: int) -> list[int]: ...

    def semantic(self, query: str, depth: int) -> list[int]: ...

    def read(self, positions: list[int]) -> dict[int, dict]: ...

    def rerank(self, pairs: list[tuple[str, str]], *, anchors: list[str] | None = None) -> list[float]: ...


def _rrf(lists: list[list[int]]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked in lists:
        for rank, position in enumerate(dict.fromkeys(ranked), 1):
            scores[position] = scores.get(position, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def _ordered(scores: dict[int, float]) -> list[int]:
    return sorted(scores, key=lambda position: (-scores[position], position))


def _ranked_positions(ranked: object) -> tuple[list[int], int]:
    """Keep usable store positions without treating unread ranks as no hits."""
    if not isinstance(ranked, (list, tuple)):
        return [], 1
    positions = [position for position in ranked
                 if type(position) is int and position >= 0]
    return positions, len(ranked) - len(positions)


class _Models:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._loaded: dict | None = None
        self.lock = threading.RLock()
        # Copies of each model's tokenizer that text preparation borrows (borrowed()).
        self._spare: dict[str, list] = {}
        self._made: dict[str, int] = {}
        self._returned = threading.Condition()

    def _model(self, which):
        with self.lock:
            if self._loaded is None:
                self._loaded = {}
            if which in self._loaded:
                return self._loaded[which]
            name = EMBED_MODEL if which == "embedding" else RERANK_MODEL
            folder = self.folder / name.replace("/", "__")
            if not folder.is_dir():
                raise SearchUnavailable(f"Local {which} weights are absent")
            try:
                import torch
                from sentence_transformers import CrossEncoder, SentenceTransformer
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._loaded[which] = (SentenceTransformer(str(folder), device=device, local_files_only=True)
                    if which == "embedding" else CrossEncoder(str(folder), device=device,
                        max_length=RERANK_TOKENS, local_files_only=True,
                        model_kwargs={"torch_dtype": torch.float16} if device == "cuda" else {}))
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                raise SearchUnavailable(f"Local {which} model cannot load") from exc
            return self._loaded[which]

    def load(self):
        models = self._model("embedding"), self._model("reranking")
        # The copies text preparation borrows are made here, on the startup thread: copying
        # the reranker's tokenizer takes seconds, and a search should not wait for it.
        for which in ("embedding", "reranking"):
            spare = []
            while self._made.get(which, 0) < TOKENIZER_COPIES:
                spare.append(self._borrow(which))
            for tokenizer in spare:
                self._give_back(which, tokenizer)
        return models

    @contextmanager
    def borrowed(self, which):
        """A copy of a model's tokenizer for one search's text preparation, given back after.

        Calling a tokenizer sets its truncation and padding, so threads sharing one spoil each
        other's settings (20 Oct 2026: four searches at once lost a judgment ranking, "Unable
        to create tensor"). The models keep their own tokenizers and use them only under the
        lock; preparation borrows a copy, so searches running side by side never share one.
        """
        tokenizer = self._borrow(which)
        try:
            yield tokenizer
        finally:
            self._give_back(which, tokenizer)

    def _borrow(self, which):
        with self._returned:
            while not self._spare.get(which) and self._made.get(which, 0) >= TOKENIZER_COPIES:
                self._returned.wait()
            if self._spare.get(which):
                return self._spare[which].pop()
            self._made[which] = self._made.get(which, 0) + 1
        try:
            model = self._model(which)
            with self.lock:  # copied while no model call is using the original
                return deepcopy(model.tokenizer)
        except BaseException:
            with self._returned:
                self._made[which] -= 1
                self._returned.notify()
            raise

    def _give_back(self, which, tokenizer):
        with self._returned:
            self._spare.setdefault(which, []).append(tokenizer)
            self._returned.notify()

    @lru_cache(maxsize=8)
    def encode(self, queries: tuple[str, ...]):
        """Both corpus indices reuse one batch in their verified vector space."""
        encoder = self._model("embedding")
        slices, groups = [], []
        with self.borrowed("embedding") as tokenizer:
            capacity = encoder.max_seq_length - len(tokenizer.encode(
                QUERY_INSTRUCTION, add_special_tokens=False)) - 4
            for query in queries:
                start = len(slices)
                slices.extend(QUERY_INSTRUCTION + window[2] for window in token_windows(
                    query, tokenizer, capacity))
                groups.append((start, len(slices)))
        with self.lock:
            vectors = encoder.encode(slices, normalize_embeddings=True, convert_to_numpy=True)
        return vectors, groups


class _SnapshotScope:
    """A search reads one checked snapshot. A change during it fails the whole
    search on exit, so no result mixes two corpus versions."""

    def __init__(self, collection) -> None:
        self.collection = collection

    def __enter__(self):
        scope = self.collection._scope
        scope.active, scope.verified = True, None
        return self

    def __exit__(self, kind, value, trace):
        scope = self.collection._scope
        verified, scope.active, scope.verified = scope.verified, False, None
        if kind is None and verified is not None and self.collection.revision() != verified:
            raise SearchUnavailable("The loaded corpus changed; reload its search indices")
        return False


class LocalCollection:
    """One coherent vector, word, and exact-passage collection."""

    def __init__(self, *, corpus_dir: Path, lineage: Path, doc_type: str,
                 models: _Models, copies: Path | None = None) -> None:
        self.corpus_dir = corpus_dir
        self.lineage = lineage
        self.doc_type = doc_type
        self.models = models
        self.copies = copies
        self._loaded: tuple[dict, Path, int] | None = None
        self._vectors = None
        self._words = None
        self._revision: str | None = None
        self._lock = threading.Lock()
        # The startup warm-up and a first search load each index once.
        self._words_lock = threading.Lock()
        self._vectors_lock = threading.Lock()
        self._scope = threading.local()
        self._parent_stamp = None
        self._parent_hash = None
        self._parents = None
        self._copies_stamp = None
        self._copies_hash = None
        self._hidden = None
        self._hidden_key = None
        self._documents = None
        self._documents_key = None
        self._instrument_positions = {}
        self._standing = None
        self._standing_lock = threading.Lock()
        self._links = OrderedDict()
        self._links_lock = threading.Lock()

    def _parent_path(self, record):
        # Contextual records have declared source keys, not vector positions.
        store = record.get("context_store")
        if self.doc_type != "bare_act" or store is None:
            return None
        if (not isinstance(store, dict) or store.get("format") != "parent_map_v1"
                or not isinstance(store.get("path"), str) or not store["path"]
                or not isinstance(store.get("sha256"), str) or len(store["sha256"]) != 64):
            raise ValueError("Parent source store has no declared artifact identity")
        name = store["path"]
        path = (self.corpus_dir / name).resolve()
        if not path.is_relative_to(self.corpus_dir.resolve()):
            raise ValueError("Parent source path leaves its corpus")
        return path

    def _parent_identity(self, record):
        path = self._parent_path(record)
        if path is None:
            return None
        if not path.is_file():
            return (str(path), None)
        stat = path.stat()
        stamp = (str(path), stat.st_size, stat.st_mtime_ns)
        if stamp != self._parent_stamp:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != stamp[1:]:
                raise ValueError("Parent source store changed while reading")
            self._parent_stamp, self._parent_hash = stamp, digest.hexdigest()
            self._parents = None
        return (*stamp, self._parent_hash)

    def _read_parent(self, identity, act_id):
        record, _, _ = self._open()
        path = self._parent_path(record)
        if path is None or not path.is_file():
            raise SearchUnavailable("Contextual parent source store is unavailable")
        if self._parents is None:
            try:
                raw = path.read_bytes()
                if (hashlib.sha256(raw).hexdigest() != self._parent_hash
                        or self._parent_hash != record["context_store"]["sha256"]):
                    raise ValueError("Parent source store differs from its corpus revision")
                self._parents = json.loads(raw, object_pairs_hook=_ParentObject)
                if not isinstance(self._parents, dict):
                    raise ValueError("Parent source store is not an identity map")
            except (OSError, ValueError) as exc:
                self._parents = None
                raise SearchUnavailable("Contextual parent source store cannot be checked") from exc
        row = self._parents.get(identity)
        if (identity in self._parents.duplicates or not isinstance(row, _ParentObject)
                or row.duplicates or row.get("chunk_id") != identity
                or row.get("act_id") != act_id or row.get("doc_type") != "bare_act"
                or not isinstance(row.get("full_text"), str) or not row["full_text"].strip()):
            raise SearchUnavailable("Parent source is missing or has conflicting ownership")
        self._check_snapshot()
        return deepcopy(row)

    def revision(self) -> str | None:
        """Identify the actual corpus artifacts, without hashing large indices."""
        try:
            lineage = self.lineage.read_bytes()
            record = json.loads(lineage)
            paths = [self.lineage,
                     self.corpus_dir / record["vector_index"]["path"],
                     self.corpus_dir / record["passage_store"]["path"]]
            bm_path = self.corpus_dir / record["bm25"]["path"]
            paths.extend(sorted(path for path in bm_path.rglob("*") if path.is_file()))
            paths.extend((bm_path / "params.index.json", Path(str(paths[2]) + "-wal")))
            identity = [(str(path.resolve()), path.stat().st_size if path.exists() else None,
                         path.stat().st_mtime_ns if path.exists() else None) for path in paths]
            parts = [identity, self._parent_identity(record)]
            if self.copies is not None:
                # Which copies search keeps is part of what this collection serves.
                parts.append(self._copies_identity())
            raw = json.dumps(parts, separators=(",", ":")).encode() + lineage
            return hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _copies_identity(self):
        path = Path(self.copies)
        if not path.is_file():
            return (str(path), None)
        stat = path.stat()
        stamp = (str(path), stat.st_size, stat.st_mtime_ns)
        if stamp != self._copies_stamp:
            self._copies_stamp, self._copies_hash = stamp, hashlib.sha256(path.read_bytes()).hexdigest()
        return (*stamp, self._copies_hash)

    def suppressed_positions(self) -> frozenset:
        """Stored positions of copies the owner's register does not keep.

        Owner decision, 10-11 October 2026: keep one copy of each instrument
        (pipeline/instrument_copies.json). A section that only a copy holds stays
        searchable there. A missing or unusable register suppresses nothing: every
        stored copy stays searchable and the cause is logged.
        """
        if self.copies is None or self.doc_type != "bare_act":
            return frozenset()
        _, db_path, _ = self._open()
        key = (self._revision, self._copies_identity())
        if self._hidden is not None and self._hidden_key == key:
            return self._hidden
        hidden = frozenset()
        try:
            documents = self._register_documents()
            # A copy keeps only the sections the register lists for it; every copy of an
            # instrument the owner excluded from search (11 Oct 2026) keeps none.
            kept = {act_id: {str(section) for section in entry.get("kept_sections", ())}
                    for act_id, entry in documents.items()
                    if isinstance(entry, dict) and entry.get("role") in ("copy", "excluded")}
            found = set()
            names = sorted(kept)
            with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
                for start in range(0, len(names), 500):
                    batch = names[start:start + 500]
                    marks = ",".join("?" for _ in batch)
                    for position, act_id, section in db.execute(
                            f"select pos, act_id, section_number from chunks where doc_type=? and act_id in ({marks})",
                            (self.doc_type, *batch)):
                        if str(section or "") not in kept[act_id]:
                            found.add(int(position))
            hidden = frozenset(found)
        except FileNotFoundError:
            log.warning("The one-copy register is absent; every stored copy stays searchable")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error) as exc:
            log.error("The one-copy register cannot be applied (%s); every stored copy stays searchable",
                      type(exc).__name__)
        self._hidden, self._hidden_key = hidden, key
        return hidden

    def _register_documents(self) -> dict:
        """The one-copy register's document map, read once per served register."""
        key = (self._revision, self._copies_identity())
        if self._documents is None or self._documents_key != key:
            register = json.loads(Path(self.copies).read_text(encoding="utf-8"))
            documents = register.get("documents") if register.get("schema") == COPY_REGISTER_SCHEMA else None
            if not isinstance(documents, dict):
                raise ValueError("The copy register has no supported document map")
            self._documents, self._documents_key, self._instrument_positions = documents, key, {}
        return self._documents

    def instrument_keys(self) -> frozenset:
        """Instruments search keeps, by the shared instrument key of their register group.
        An instrument the owner excluded from search has no kept copy, so it is not offered."""
        if self.copies is None or self.doc_type != "bare_act":
            return frozenset()
        self._open()
        try:
            return frozenset(entry["group"] for entry in self._register_documents().values()
                             if isinstance(entry, dict) and entry.get("role") == "kept"
                             and isinstance(entry.get("group"), str) and entry["group"])
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise SearchUnavailable("The instrument register cannot be read") from exc

    def instrument_positions(self, keys) -> frozenset:
        """Searchable passages of the given instruments: each kept copy, and a copy only
        in the sections the register keeps for it."""
        _, db_path, _ = self._open()
        keys = frozenset(keys)
        try:
            documents = self._register_documents()
            if keys not in self._instrument_positions:
                names = sorted(act_id for act_id, entry in documents.items()
                               if isinstance(entry, dict) and entry.get("group") in keys
                               and entry.get("role") in ("kept", "copy"))
                found = set()
                with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
                    for start in range(0, len(names), 500):
                        batch = names[start:start + 500]
                        marks = ",".join("?" for _ in batch)
                        found.update(int(row[0]) for row in db.execute(
                            f"select pos from chunks where doc_type=? and act_id in ({marks})", (self.doc_type, *batch)))
                self._instrument_positions[keys] = frozenset(found) - self.suppressed_positions()
        except (OSError, ValueError, TypeError, AttributeError, sqlite3.Error) as exc:
            raise SearchUnavailable("The named instruments' passages cannot be read") from exc
        self._check_snapshot()
        return self._instrument_positions[keys]

    def lexical_within(self, query: str, depth: int, allowed) -> list[int]:
        """Word search over the given passages only, with the full index's statistics."""
        _, _, count = self._open()
        bm25 = self._word_index()
        try:
            import numpy as np

            tokens = [token for token in bm25_tokens(query) if token in bm25.vocab_dict]
            within = np.asarray(sorted(p for p in allowed if 0 <= p < count), dtype="int64")
            if not tokens or not len(within):
                return []
            scores = bm25.get_scores(tokens)[within]
            order = np.argsort(-scores, kind="stable")[:depth]
            return [int(within[i]) for i in order if scores[i] > 0]
        except (ImportError, OSError, RuntimeError, ValueError, IndexError) as exc:
            raise SearchUnavailable(f"{self.doc_type} word search within named instruments failed: {exc}") from exc

    def semantic_many_within(self, queries: tuple[str, ...], depth: int, allowed) -> list[list[int]]:
        """Vector search over the given passages only (an exact selection, not a filter
        applied after a global cut-off), all formulations in one index operation."""
        _, _, count = self._open()
        index = self._vector_index()
        try:
            import faiss
            import numpy as np

            within = np.asarray(sorted(p for p in allowed if 0 <= p < count), dtype="int64")
            if not len(within):
                return [[] for _ in queries]
            vectors, groups = self.models.encode(queries)
            params = faiss.SearchParameters(sel=faiss.IDSelectorBatch(within))
            _, positions = index.search(np.asarray(vectors, dtype="float32"), min(depth, len(within)), params=params)
            ranked = [[int(pos) for pos in row if 0 <= pos < count] for row in positions]
            return [_ordered(_rrf(ranked[start:end])) for start, end in groups]
        except (ImportError, OSError, RuntimeError, ValueError, AttributeError) as exc:
            raise SearchUnavailable(f"{self.doc_type} semantic search within named instruments failed: {exc}") from exc

    def judgment_paragraphs(self, case_id: str) -> list[tuple[int, dict]]:
        """Every held paragraph of one judgment, in stored order, each read and checked as a
        search result is (owner decision P31, 21 Oct 2026: a judgment the research chooses is
        read whole, or as an extract of a long one)."""
        if self.doc_type != "case_law" or not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("A judgment is read by its own case identity")
        _, db_path, count = self._open()
        try:
            with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
                positions = [row[0] for row in db.execute(
                    "select pos from chunks where doc_type=? and case_id=? order by pos", (self.doc_type, case_id))]
        except sqlite3.Error as exc:
            raise SearchUnavailable("The judgment's paragraphs cannot be read") from exc
        rows = self.read(positions)
        if not positions or set(rows) != set(positions):
            raise SearchUnavailable("Some paragraphs of the judgment cannot be read")
        return [(position, rows[position]) for position in positions]

    def case_standing(self) -> dict:
        """Each held judgment's citation standing: the mid-rank share of held judgments
        of the same court and year that later judgments cite less, read once per corpus
        revision from each judgment's first stored passage. None marks a court-year where
        most held judgments have no recorded citations yet, so the count says little.
        Standing orders search candidates; it is not court treatment, currency or
        binding force."""
        _, db_path, _ = self._open()
        with self._standing_lock:
            if self._standing is not None and self._standing[0] == self._revision:
                return self._standing[1]
            try:
                with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
                    firsts = [pos for _, pos in db.execute(
                        "select case_id, min(pos) from chunks where doc_type=? group by case_id", (self.doc_type,))]
                    cases = {}
                    for start in range(0, len(firsts), 500):
                        batch = firsts[start:start + 500]
                        marks = ",".join("?" for _ in batch)
                        for case_id, blob in db.execute(
                                f"select case_id, blob from chunks where doc_type=? and pos in ({marks})",
                                (self.doc_type, *batch)):
                            item = json.loads(blob)
                            cited = item.get("cited_by_count") or 0
                            cases[case_id] = (item.get("court"), item.get("year"), cited if type(cited) is int else 0)
            except (sqlite3.Error, ValueError, TypeError, AttributeError) as exc:
                raise SearchUnavailable("Judgment citation standing cannot be read") from exc
            peers = {}
            for court, year, cited in cases.values():
                peers.setdefault((court, year), []).append(cited)
            for values in peers.values():
                values.sort()
            table = {}
            for case_id, (court, year, cited) in cases.items():
                values = peers[(court, year)]
                unsettled = sum(value == 0 for value in values) * 2 > len(values)
                table[case_id] = None if unsettled else (
                    bisect.bisect_left(values, cited) + bisect.bisect_right(values, cited)) / (2 * len(values))
            self._standing = (self._revision, table)
        self._check_snapshot()
        return table

    def _check_snapshot(self) -> None:
        scope = self._scope
        active = getattr(scope, "active", False)
        if active and scope.verified is not None and scope.verified == self._revision:
            return
        if self._revision is None or self.revision() != self._revision:
            raise SearchUnavailable("The loaded corpus changed; reload its search indices")
        if active:
            scope.verified = self._revision

    def snapshot_scope(self):
        """One search checks its loaded snapshot on first use and again on exit,
        not before each of its hundreds of reads (this thread only)."""
        return _SnapshotScope(self)

    def _readback_scope(self):
        """One exact provision readback checks the loaded snapshot once and again at its end,
        as one search does, unless a search on this thread already holds that check (20 Oct
        2026: a check at every read made each readback about three times slower)."""
        return nullcontext() if getattr(self._scope, "active", False) else self.snapshot_scope()

    def warm(self) -> None:
        """Load what a first search would otherwise wait for (the startup thread):
        indices, the copy register's hidden positions and the shared models."""
        self._open()
        self._word_index()
        self._vector_index()
        if self.copies is not None:
            self.suppressed_positions()
        if self.doc_type == "case_law":
            try:
                self.case_standing()
            except SearchUnavailable:
                # Only the citation part of judgment ordering depends on it; a search
                # records the gap itself.
                log.warning("Judgment citation standing could not be warmed", exc_info=True)
        self.models.load()
        # One probe pages in the vector index and starts the device kernels;
        # its results are discarded and nothing is cached as evidence.
        self.semantic_many(("warm-up",), 1)
        self.rerank([("warm-up", "warm-up")])

    def _open(self):
        if self._loaded is not None:
            self._check_snapshot()
            return self._loaded
        with self._lock:
            if self._loaded is not None:
                self._check_snapshot()
                return self._loaded
            try:
                record = json.loads(self.lineage.read_text(encoding="utf-8"))
                count = record["passages"]
                db_path = self.corpus_dir / record["passage_store"]["path"]
                revision = self.revision()
                if (record["schema"] != 1 or record["doc_type"] != self.doc_type
                        or record["model"] != EMBED_MODEL or record["dimensions"] != DIMENSIONS
                        or type(count) is not int or count < 1 or not revision):
                    raise SearchUnavailable("Corpus manifest has no coherent passage identity")
                with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
                    stored, last = db.execute("select count(*), max(pos) from chunks where doc_type=?",
                        (self.doc_type,)).fetchone()
                if stored != count or last != count - 1:
                    raise SearchUnavailable("Stored passages differ from their recorded positions")
                self._revision = revision
                self._loaded = record, db_path, count
                self._check_snapshot()
                return self._loaded
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                raise SearchUnavailable("Corpus passage identity cannot be checked") from exc

    def _word_index(self):
        record, _, count = self._open()
        with self._words_lock:
            if self._words is None:
                path = self.corpus_dir / record["bm25"]["path"]
                try:
                    params = (path / "params.index.json").read_bytes()
                    if (json.loads(params)["num_docs"] != count
                            or record["bm25"]["num_docs"] != count
                            or hashlib.sha256(params).hexdigest() != record["bm25"]["params_sha256"]):
                        raise SearchUnavailable("Word index differs from its recorded source positions")
                    import bm25s
                    self._words = bm25s.BM25.load(str(path), mmap=True)
                except (ImportError, OSError, ValueError, KeyError) as exc:
                    raise SearchUnavailable("Word index is unavailable") from exc
        return self._words

    def _vector_index(self):
        record, _, count = self._open()
        with self._vectors_lock:
            if self._vectors is None:
                path = self.corpus_dir / record["vector_index"]["path"]
                try:
                    verified = record["verified"]
                    with path.open("rb") as stream:
                        header = stream.read(16)
                    vectors = struct.unpack("<q", header[8:16])[0]
                    if (header[:4] != b"IxFI" or struct.unpack("<i", header[4:8])[0] != DIMENSIONS
                            or vectors != count + record.get("vectors_without_passage", 0)
                            or vectors != record["vector_index"]["vectors"]
                            or path.stat().st_size != record["vector_index"]["bytes"]
                            or not verified.get("sampled") or verified["same_vector"] != verified["sampled"]
                            or verified["mean_similarity"] < 0.99):
                        raise SearchUnavailable("Vector index differs from its verified source space")
                    import faiss
                    self._vectors = faiss.read_index(str(path), faiss.IO_FLAG_MMAP_IFC | faiss.IO_FLAG_READ_ONLY)
                except (ImportError, OSError, ValueError, KeyError, struct.error) as exc:
                    raise SearchUnavailable("Vector index is unavailable") from exc
        return self._vectors

    def lexical(self, query: str, depth: int) -> list[int]:
        _, _, count = self._open()
        bm25 = self._word_index()
        try:
            import numpy as np

            tokens = [token for token in bm25_tokens(query) if token in bm25.vocab_dict]
            if not tokens:
                return []
            scores = bm25.get_scores(tokens)
            limit = min(depth, len(scores))
            if not limit:
                return []
            top = np.argpartition(-scores, limit - 1)[:limit]
            return [int(pos) for pos in top[np.argsort(-scores[top])]
                    if 0 <= pos < count and scores[pos] > 0]
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise SearchUnavailable(f"{self.doc_type} word search failed: {exc}") from exc

    def semantic(self, query: str, depth: int) -> list[int]:
        return self.semantic_many((query,), depth)[0]

    def semantic_many(self, queries: tuple[str, ...], depth: int) -> list[list[int]]:
        """Encode and search all formulations in one index operation."""
        _, _, count = self._open()
        index = self._vector_index()
        try:
            import numpy as np

            vectors, groups = self.models.encode(queries)
            _, positions = index.search(np.asarray(vectors, dtype="float32"), depth)
            ranked = [[int(pos) for pos in row if 0 <= pos < count] for row in positions]
            return [_ordered(_rrf(ranked[start:end])) for start, end in groups]
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise SearchUnavailable(f"{self.doc_type} semantic search failed: {exc}") from exc

    def read(self, positions: list[int]) -> dict[int, dict]:
        _, db_path, count = self._open()
        selected = [pos for pos in dict.fromkeys(positions) if 0 <= pos < count]
        if not selected:
            return {}
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        found: dict[int, dict] = {}
        try:
            for start in range(0, len(selected), 500):
                batch = selected[start:start + 500]
                marks = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"select pos, chunk_id, blob, act_id, case_id, section_number, parent_chunk_id "
                    f"from chunks where doc_type=? and pos in ({marks})",
                    (self.doc_type, *batch),
                )
                for pos, chunk_id, blob, act_id, case_id, section, parent in rows:
                    try:
                        item = json.loads(blob)
                    except ValueError:
                        continue
                    indexed = {"act_id": act_id, "section_number": section, "parent_chunk_id": parent}
                    if self.doc_type == "case_law":
                        indexed = {"case_id": case_id}
                    owner = act_id if self.doc_type == "bare_act" else case_id
                    if (isinstance(item, dict) and isinstance(owner, str) and owner.strip()
                            and all(str(item.get(key) or "") == str(value or "")
                                    for key, value in indexed.items())
                            and item.get("doc_type", self.doc_type) == self.doc_type
                            and item.get("chunk_id") == chunk_id
                            and isinstance(item.get("full_text"), str)
                            and item["full_text"].strip()):
                        found[int(pos)] = item
        except sqlite3.Error as exc:
            raise SearchUnavailable(f"{self.doc_type} passages cannot be read") from exc
        finally:
            connection.close()
        self._check_snapshot()
        return found

    def read_provision(self, act_id: str, reference: str) -> dict:
        """Read an explicit provision inside one already selected held Act.

        Corpus revision identifies stored artifacts, never legal currency.
        Missing/unread source words cannot become a successful complete read.
        """
        if (self.doc_type != "bare_act" or not isinstance(act_id, str) or not act_id.strip()
                or not isinstance(reference, str) or not reference.strip()):
            raise ValueError("Exact provision readback needs one owned Act and explicit reference")
        result = {"state": "unavailable", "act_id": act_id, "reference": reference,
                  "provision_key": None, "candidates": [], "sources": [],
                  "legal_version": "not_assessed", "reason": None}
        try:
            with self._readback_scope():
                _, db_path, _ = self._open()
                with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
                    keys = tuple(row[0] for row in db.execute(
                        "select distinct section_number from chunks where doc_type=? and act_id=?",
                        (self.doc_type, act_id)))
                    binding = bind_provision_key(reference, keys)
                    result.update(candidates=list(binding.candidate_keys), reason=binding.reason)
                    if binding.state != ProvisionKeyState.BOUND:
                        self._check_snapshot()
                        result["state"] = "ambiguous" if binding.state == ProvisionKeyState.AMBIGUOUS else "not_held"
                        return result
                    positions = [row[0] for row in db.execute(
                        SECTION_PARTS, (self.doc_type, act_id, binding.key, MAX_CONTEXT_SEGMENTS + 1))]
                if len(positions) > MAX_CONTEXT_SEGMENTS:
                    raise SearchUnavailable("Complete provision readback exceeds the indexed-segment resource bound")
                rows = self.read(positions)
                if not positions or set(rows) != set(positions):
                    raise SearchUnavailable("Some indexed words of this provision cannot be read")
                identities = [row["chunk_id"] for row in rows.values()]
                roots = [position for position, row in rows.items() if not row.get("parent_chunk_id")]
                if len(set(identities)) != len(identities) or len(roots) > 1:
                    self._check_snapshot()
                    result.update(state="ambiguous", reason="The provision locator identifies distinct or repeated source roots")
                    return result
                paths = [self.rank_context(position, row) for position, row in rows.items()]
                checked_roots = {path["segments"][0]["position"] for path in paths}
                if len(checked_roots) != 1:
                    result.update(state="ambiguous", reason="The provision has distinct connected source occurrences")
                    return result
                connected = {}
                for path in paths:
                    for segment in path["segments"]:
                        address = segment["position"]
                        if address in connected and connected[address] != segment:
                            raise SearchUnavailable("Provision readback has conflicting source records")
                        connected[address] = segment
                context = {"scope": "indexed_section_segments", "bounded": False, "unread_positions": [],
                           "segments": [connected[p] for p in sorted(connected, key=_location_order)]}
                sources = []
                for segment in context["segments"]:
                    sources.append(_candidate("provision", segment["position"], segment["row"],
                                              self._revision, None, [], context))
                self._check_snapshot()
                result.update(state="found", provision_key=binding.key, sources=sources)
        except (SearchUnavailable, sqlite3.Error, ValueError) as exc:
            result.update(state="unavailable", reason=str(exc), sources=[], provision_key=None)
        return result

    def act_links(self, act_id: str) -> dict:
        """One held Act's own links (owner decision P32, 20 Oct 2026): its provisions in the
        Act's order, each with its heading and its one root part's position (None when it has
        none or several), the provisions each names in its own words with those words, the
        provisions naming each, and how many of each one's references bind to no single held
        provision. Worked out from the held Act when it is first read, once per corpus
        revision; nothing about another Act is read or bound."""
        if self.doc_type != "bare_act" or not isinstance(act_id, str) or not act_id.strip():
            raise ValueError("An Act's links need one owned Act")
        _, db_path, _ = self._open()
        key = (self._revision, act_id)
        with self._links_lock:
            if key in self._links:
                self._links.move_to_end(key)
                return self._links[key]
        try:
            with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
                rows = db.execute("select pos, section_number, parent_chunk_id, blob from chunks "
                                  "where doc_type=? and act_id=? order by +pos", (self.doc_type, act_id)).fetchall()
            order, titles, roots, texts = [], {}, {}, []
            for position, section, parent, blob in rows:
                item, section = json.loads(blob), str(section or "")
                if not section or not isinstance(item, dict) or not isinstance(item.get("full_text"), str):
                    continue
                if section not in titles:
                    order.append(section)
                    titles[section] = item.get("section_title") if isinstance(item.get("section_title"), str) else ""
                if not parent:
                    roots.setdefault(section, []).append(int(position))
                texts.append((section, item["full_text"], item.get("act_name") or ""))
        except (sqlite3.Error, ValueError, TypeError) as exc:
            raise SearchUnavailable("The Act's provisions cannot be read for its links") from exc
        place, bind = {section: index for index, section in enumerate(order)}, provision_key_binder(tuple(order))
        names, unbound = {}, {}
        for section, text, title in texts:
            for named in provisions_named(text, within=section, instrument=statute_own_title(title, act_id)):
                if named.elsewhere:
                    continue
                first = bind(named.reference)
                targets = [first.key] if first.state == ProvisionKeyState.BOUND else []
                if targets and named.through:
                    last = bind(named.through)
                    targets = (list(order[place[first.key]:place[last.key] + 1])
                               if last.state == ProvisionKeyState.BOUND and place[last.key] > place[first.key] else [])
                if not targets:
                    unbound[section] = unbound.get(section, 0) + 1
                for target in targets:
                    if target != section:
                        names.setdefault(section, {}).setdefault(target, _link_words(text, named))
        named_by = {}
        for section in order:
            for target, words in names.get(section, {}).items():
                named_by.setdefault(target, {})[section] = words
        links = {"order": tuple(order), "place": place, "titles": titles,
                 "roots": {section: found[0] if len(found) == 1 else None for section, found in roots.items()},
                 "names": names, "named_by": named_by, "unbound": unbound}
        self._check_snapshot()
        with self._links_lock:
            self._links[key] = links
            while len(self._links) > LINKED_ACTS:
                self._links.popitem(last=False)
        return links

    def rerank(self, pairs: list[tuple[str, str]], *, anchors: list[str] | None = None) -> list[float]:
        anchors = [""] * len(pairs) if anchors is None else anchors
        if len(anchors) != len(pairs) or any(not isinstance(anchor, str) for anchor in anchors):
            raise SearchUnavailable("Rerank document anchors do not match their source pairs")
        if not pairs:
            return []
        model = self.models._model("reranking")
        try:
            windows, groups = [], []
            query_windows, passage_windows = {}, {}
            # Text is prepared with a borrowed copy of the tokenizer, never the model's own,
            # which only the prediction below uses, under the lock.
            with self.models.borrowed("reranking") as tokenizer:
                for (query, passage), anchor in zip(pairs, anchors, strict=True):
                    first = len(windows)
                    if query not in query_windows:
                        query_windows[query] = [(text, RERANK_TOKENS - len(tokenizer.encode(
                            text, add_special_tokens=False)) - tokenizer.num_special_tokens_to_add(pair=True))
                            for _, _, text in token_windows(query, tokenizer, QUESTION_TOKENS)]
                    for query_window, room in query_windows[query]:
                        key = passage, room, anchor
                        if key not in passage_windows:
                            passage_windows[key] = _anchored_windows(passage, tokenizer, room, anchor)
                        # Reuse preparation only inside this call. Repeated prediction
                        # pairs retain their original order, count and score ownership.
                        windows.extend((query_window, text) for text in passage_windows[key])
                    groups.append((first, len(windows)))
            if len(windows) > MAX_RERANK_PAIRS:
                raise SearchUnavailable("The complete passage windows exceed the local rerank budget")
            with self.models.lock:
                scores = _batched_scores(model, windows)
            return [max(float(s) for s in scores[start:end]) for start, end in groups]
        except (OSError, RuntimeError, ValueError) as exc:
            raise SearchUnavailable(f"{self.doc_type} reranking failed: {exc}") from exc

    def rank_context(self, position: int | str, row: dict) -> dict:
        """Resolve exact parents; section numbers alone do not identify a parent."""
        _, db_path, _ = self._open()
        segments = [{"position": position, "row": row, "content_digest": _digest(row)}]
        seen, child, child_position = {position}, row, position
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as connection:
            while True:
                if self.doc_type != "bare_act" or not row.get("act_id") or not child.get("chunk_id"):
                    raise SearchUnavailable("Source ancestry has no owned provision identity")
                own_matches = connection.execute(
                    PART_BY_ID,
                    (self.doc_type, row["act_id"], child["chunk_id"])).fetchall()
                if isinstance(child_position, str):
                    if (child_position != _parent_address(child) or own_matches
                            or self._read_parent(child["chunk_id"], row["act_id"]) != child):
                        raise SearchUnavailable("Contextual source identity is ambiguous or changed")
                elif own_matches != [(child_position,)]:
                    raise SearchUnavailable("Source chunk identity is missing or ambiguous within its Act")
                if not child.get("parent_chunk_id"):
                    break
                identity = child["parent_chunk_id"]
                if self.doc_type != "bare_act" or not isinstance(identity, str) or not row.get("act_id"):
                    raise SearchUnavailable("Parent source identity is invalid")
                matches = connection.execute(
                    PART_BY_ID,
                    (self.doc_type, row["act_id"], identity)).fetchall()
                if len(matches) > 1:
                    raise SearchUnavailable("Parent source identity is ambiguous")
                if matches:
                    parent_position = matches[0][0]
                    parent = self.read([parent_position]).get(parent_position)
                else:
                    parent = self._read_parent(identity, row["act_id"])
                    parent_position = _parent_address(parent)
                if parent_position in seen:
                    raise SearchUnavailable("Parent source links contain a cycle")
                if (parent is None or parent.get("chunk_id") != identity
                        or parent.get("act_id") != row["act_id"]
                        or parent.get("section_number") != row.get("section_number")):
                    raise SearchUnavailable("Parent source words or ownership cannot be checked")
                segments.append({"position": parent_position, "row": parent,
                                 "content_digest": _digest(parent)})
                seen.add(parent_position)
                child, child_position = parent, parent_position
        return {"scope": "exact_parent_tree", "bounded": False, "unread_positions": [],
                "segments": list(reversed(segments))}

    def context(self, position: int, row: dict) -> dict:
        """Exact indexed segments; no claim that these form a complete judgment."""
        _, db_path, _ = self._open()
        if self.doc_type == "bare_act" and row.get("act_id") and row.get("section_number"):
            # A printed provision number is a discovery key, not a relationship.
            # Repeated numbering in annexures/forms must not create neighbours.
            ancestry = self.rank_context(position, row)
            root = ancestry["segments"][0]["position"]
            with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as connection:
                positions = [p[0] for p in connection.execute(
                    SECTION_PARTS, (self.doc_type, row["act_id"], str(row["section_number"]), MAX_CONTEXT_SEGMENTS + 1))]
            limited = len(positions) > MAX_CONTEXT_SEGMENTS
            positions = positions[:MAX_CONTEXT_SEGMENTS]
            rows = self.read(positions)
            unread = [p for p in positions if p not in rows]
            connected = {s["position"]: s for s in ancestry["segments"]}
            ambiguous, other_roots = [], set()
            for other_position, other in rows.items():
                try:
                    path = self.rank_context(other_position, other)
                except SearchUnavailable:
                    ambiguous.append(other_position)
                    continue
                other_root = path["segments"][0]["position"]
                if other_root == root:
                    connected.update((s["position"], s) for s in path["segments"])
                else:
                    other_roots.add(other_root)
            context = {"scope": "indexed_section_segments", "bounded": bool(limited or unread or ambiguous or other_roots),
                "unread_positions": unread, "segments": [connected[p] for p in sorted(connected, key=_location_order)]}
            if context["bounded"]:
                raise _ContextGap(
                    f"Provision context retains its connected source; {len(unread)} unread positions, "
                    f"{len(ambiguous)} ambiguous source links and {len(other_roots)} unrelated roots share its locator; "
                    f"indexed-segment resource bound reached: {limited}",
                    context)
            return context
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            if self.doc_type == "case_law" and row.get("case_id"):
                earlier = [p[0] for p in connection.execute(
                    "select pos from chunks where doc_type=? and case_id=? and pos<? order by pos desc limit 2",
                    (self.doc_type, row["case_id"], position))]
                later = [p[0] for p in connection.execute(
                    "select pos from chunks where doc_type=? and case_id=? and pos>? order by pos limit 2",
                    (self.doc_type, row["case_id"], position))]
                positions, scope, bounded = sorted([*earlier, position, *later]), "adjacent_indexed_segments", False
            else:
                positions, scope, bounded = [position], "selected_indexed_segment", False
        finally:
            connection.close()
        positions = sorted(set([*positions, position]))
        rows = self.read(positions)
        return {"scope": scope, "bounded": bounded, "unread_positions": [p for p in positions if p not in rows],
                "segments": [{"position": p, "row": rows[p], "content_digest": _digest(rows[p])}
                             for p in positions if p in rows]}


def _batched_scores(model, windows):
    """Each pair's score, the pairs scored shortest first in batches of at most
    RERANK_BATCH_PAIRS pairs and RERANK_BATCH_CHARACTERS characters (a pair longer than that
    alone is a batch of its own), returned in the pairs' own order (P30)."""
    order = sorted(range(len(windows)), key=lambda index: (len(windows[index][0]) + len(windows[index][1]), index))
    scores, group, size = [None] * len(windows), [], 0
    for index in [*order, None]:
        length = 0 if index is None else len(windows[index][0]) + len(windows[index][1])
        if group and (index is None or size + length > RERANK_BATCH_CHARACTERS or len(group) == RERANK_BATCH_PAIRS):
            for position, score in zip(group, model.predict([windows[i] for i in group], batch_size=len(group),
                                                           show_progress_bar=False), strict=True):
                scores[position] = float(score)
            group, size = [], 0
        if index is not None:
            group.append(index)
            size += length
    return scores


def token_windows(text, tokenizer, capacity, overlap=WINDOW_OVERLAP):
    """Cover the entire original text, including tails, with exact character offsets."""
    if capacity <= overlap:
        raise SearchUnavailable("The local model has no room for attributable windows")
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, truncation=False)
    offsets = encoded["offset_mapping"]
    if not offsets:
        return [(0, len(text), text)]
    windows = []
    start = 0
    while start < len(offsets):
        end = min(len(offsets), start + capacity)
        left = 0 if start == 0 else offsets[start][0]
        right = len(text) if end == len(offsets) else offsets[end][0]
        # Tokenising a substring can change its first token, especially for
        # multilingual tokenizers. Check the actual slice rather than its old offsets.
        while len(tokenizer(text[left:right], add_special_tokens=False,
                return_offsets_mapping=True, truncation=False)["offset_mapping"]) > capacity:
            end -= 1
            if end <= start:
                raise SearchUnavailable("An exact source token cannot fit its window")
            right = offsets[end][0]
        windows.append((left, right, text[left:right]))
        if end == len(offsets):
            break
        start = max(start + 1, end - overlap)
    return windows


def _anchored_windows(text, tokenizer, capacity, anchor):
    """Keep owned document identity on every exact body window without truncation.

    Some held rows carry a whole provision in their heading field. An anchor that
    leaves no attributable room gives up trailing lines, the optional heading first,
    and keeps its leading identity lines; body words are never cut. Anchors that
    already fitted produce exactly the same windows as before.
    """
    if not anchor:
        return [part for _, _, part in token_windows(text, tokenizer, capacity)]
    lines = anchor.removesuffix("\n").split("\n")
    while lines:
        shortened = "\n".join(lines) + "\n" if anchor.endswith("\n") else "\n".join(lines)
        room = capacity - len(tokenizer.encode(shortened, add_special_tokens=False)) - 8
        while room > WINDOW_OVERLAP:
            pieces = [shortened + part for _, _, part in token_windows(text, tokenizer, room)]
            overflow = max(0, max(len(tokenizer.encode(part, add_special_tokens=False)) - capacity
                                  for part in pieces))
            if not overflow:
                return pieces
            room -= overflow
        lines.pop()
    raise SearchUnavailable("The local model has no room for attributable windows")


#: Stored judgment paragraph kinds that report rather than decide: the facts, counsel's
#: arguments and the operative order. An automatic labeller assigned them, so they only
#: order candidates and never remove one.
REPORTED_PARAGRAPHS = frozenset({"facts", "arguments", "argument", "order"})
#: A paragraph mostly inside quotation marks repeats a statute or an earlier judgment.
QUOTED_SHARE = 0.5
_QUOTED = re.compile(r"[\"“”]([^\"“”]{20,})[\"“”]")


def _quoted_share(text):
    return sum(len(quoted) for quoted in _QUOTED.findall(text)) / max(1, len(text))


def _reported(row):
    """A judgment paragraph that reports facts, arguments or the order, or mostly quotes."""
    return (row.get("paragraph_type") in REPORTED_PARAGRAPHS
            or _quoted_share(row.get("full_text") or "") >= QUOTED_SHARE)


def _standing_values(positions, rows, standing):
    """Each paragraph's judgment standing. A court-year whose citations are mostly
    unrecorded takes the middle of the others ordered with it; a judgment absent from
    the table takes 0.5."""
    values = {position: standing.get(rows[position].get("case_id"), 0.5) for position in positions}
    known = sorted(value for value in values.values() if value is not None)
    middle = known[len(known) // 2] if known else 0.5
    return {position: middle if value is None else value for position, value in values.items()}


def _judgment_order(scored, rows, standing):
    """v7 judgment order (owner decision, 14 Oct 2026). The reranker scores almost every
    on-topic paragraph near its maximum, and paragraphs quoting a statute word for word
    score highest, so its order among them carries little information. Paragraphs in the
    court's own words come before those that report facts, arguments or the order or
    mostly quote; within each, the reranker's order is blended by reciprocal ranks with
    the judgment's citation standing among held judgments of its court and year. A
    judgment from a court-year whose citations are mostly unrecorded takes the middle
    standing of the others ordered; one absent from the table takes 0.5. Each candidate
    keeps the reranker's own score."""
    reranked = {position: rank for rank, (position, _) in enumerate(scored, 1)}
    values = _standing_values([position for position, _ in scored], rows, standing)
    standing_rank = {position: rank for rank, position in enumerate(
        sorted(values, key=lambda p: (-values[p], reranked[p])), 1)}
    return sorted(scored, key=lambda x: (
        _reported(rows[x[0]]), -(1.0 / (RRF_K + reranked[x[0]]) + 1.0 / (RRF_K + standing_rank[x[0]])),
        _location_order(x[0])))


def _rerank_anchor(checked_source):
    """Reuse the exact identity and locator already admitted by _candidate."""
    heading = (checked_source["source"].get("section_title")
               if checked_source["kind"] == "provision" else None)
    parts = (checked_source["title"], checked_source["locator"],
             heading if isinstance(heading, str) else "")
    return "\n".join(part for part in parts if part) + "\n"


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _parent_address(row):
    return "parent:" + row["chunk_id"]


def _valid_location(kind, position, row):
    return ((type(position) is int and position >= 0)
            or (kind == "provision" and isinstance(position, str)
                and isinstance(row, dict) and isinstance(row.get("chunk_id"), str)
                and bool(row["chunk_id"]) and position == _parent_address(row)))


def _location_order(position):
    return (0, position) if type(position) is int else (1, position)


def in_force(row):
    """The store's mark on a held provision whose Act India Code does not list as in force
    (owner decision P21; the Act store of 19 Oct 2026), or None. No mark is no finding that
    an Act is in force: earlier stores carry none, nor do instruments India Code does not hold."""
    mark = row.get("standing") if isinstance(row, dict) else None
    return mark if isinstance(mark, str) and mark.strip() else None


def _candidate(kind, position, row, revision, score, query_ids, context):
    if (not isinstance(row, dict) or not isinstance(row.get("full_text"), str)
            or not row["full_text"].strip() or not isinstance(row.get("chunk_id"), str)
            or not row["chunk_id"].strip()):
        raise SearchUnavailable("Candidate has no exact stored words or chunk identity")
    if (not _valid_location(kind, position, row) or not isinstance(revision, str) or not revision
            or row.get("doc_type", "bare_act" if kind == "provision" else "case_law") != (
                "bare_act" if kind == "provision" else "case_law")
            or score is not None and (type(score) not in (int, float) or not math.isfinite(score))):
        raise SearchUnavailable("Candidate source position, kind or score is inconsistent")
    title = row.get("act_name") or row.get("act_id") if kind == "provision" else row.get("case_name") or row.get("case_id")
    locator = str(row.get("section_number") or "") if kind == "provision" else str(row.get("paragraph_num") or row.get("para_no") or "")
    if not isinstance(title, str) or not title.strip():
        raise SearchUnavailable("Candidate has no attributable document identity")
    identity = {"kind": kind, "position": position, "revision": revision, "row": row}
    context = deepcopy(context)
    for segment in context.get("segments", []):
        segment.setdefault("content_digest", _digest(segment["row"]))
    return {"id": f"{kind}:{_digest(identity)}", "kind": kind, "position": position,
        "corpus_revision": revision, "title": title, "locator": locator,
        "text": row["full_text"], "source": deepcopy(row), "content_digest": _digest(row),
        "score": score, "query_ids": list(dict.fromkeys(query_ids)), "context": context,
        "context_digest": _digest(context),
        "legal_status": "candidate_unassessed"}


#: Where the words that name a provision begin: their own sentence, clause or heading.
_LINK_START = re.compile(r"(?:[.;:\n—]\s*|^)(?=[^.;:\n—]*$)")


def _link_words(text, named):
    """The words in which a provision names another, from the start of their sentence or
    clause (at most 160 characters before them), exactly as held but for spacing."""
    start = max(0, named.start - 160)
    lead = text[start:named.start]
    begin = _LINK_START.search(lead)
    lead = lead[begin.end():] if begin else lead
    return ("" if begin or start == 0 else "…") + " ".join((lead + text[named.start:named.end]).split())


def _whole_section(collection, position, row, touched, issues):
    """A returned provision with all its parts (P32): the whole section when it is no longer
    than WHOLE_SECTION_CHARACTERS, otherwise the parts search found with the section's
    opening. Either way a gap is recorded, never hidden."""
    alone = {"scope": "selected_indexed_segment", "bounded": True, "unread_positions": [],
             "segments": [{"position": position, "row": row, "content_digest": _digest(row)}]}
    try:
        context = collection.context(position, row)
    except _ContextGap as exc:
        issues.append({"kind": "provision", "query_id": None, "stage": "context", "reason": str(exc), "position": position})
        return exc.context
    except Exception as exc:
        _log_stage_failure("provision", "context", exc)
        issues.append({"kind": "provision", "query_id": None, "stage": "context",
                       "reason": str(exc) if isinstance(exc, SearchUnavailable) else type(exc).__name__,
                       "position": position})
        return {**(touched or alone), "bounded": True}
    size = sum(len(segment["row"]["full_text"]) for segment in context["segments"])
    if size <= WHOLE_SECTION_CHARACTERS:
        return context
    issues.append({"kind": "provision", "query_id": None, "stage": "context", "position": position,
                   "reason": f"The whole section is {size:,} characters in {len(context['segments'])} parts, more than "
                             f"the {WHOLE_SECTION_CHARACTERS:,} read whole; the parts search found are read with its opening"})
    return {**(touched or alone), "bounded": True}


def _connect(collection, revision, returned, issues):
    """The provisions the returned ones are read with (P32): those each names in its own
    words and those naming it, up to LINKS_EACH_WAY each way, and the provision before and
    after it in its Act. Each is read whole as a connected candidate. Returns the connected
    candidates, the connections (from the provision whose words name the other, or from the
    earlier of two beside each other) and each returned provision's link counts."""
    if not returned or not callable(getattr(collection, "act_links", None)):
        return [], [], {}
    try:
        hidden = collection.suppressed_positions() if callable(getattr(collection, "suppressed_positions", None)) else frozenset()
    except SearchUnavailable as exc:
        _log_stage_failure("provision", "copy register", exc)
        hidden = frozenset()
    found = {candidate["position"]: candidate["id"] for candidate in returned}
    wanted, edges, counts, tables = {}, [], {}, {}
    for candidate in returned:
        act_id, section = candidate["source"]["act_id"], str(candidate["source"].get("section_number") or "")
        try:
            if act_id not in tables:
                tables[act_id] = collection.act_links(act_id)
            table = tables[act_id]
        except (SearchUnavailable, ValueError) as exc:
            _log_stage_failure("provision", "links", exc)
            issues.append({"kind": "provision", "query_id": None, "stage": "links", "reason": str(exc),
                           "position": candidate["position"]})
            continue
        if section not in table["place"]:
            issues.append({"kind": "provision", "query_id": None, "stage": "links", "position": candidate["position"],
                           "reason": "The provision's own key is not among its Act's held provisions"})
            continue
        names, named_by = list(table["names"].get(section, {}).items()), list(table["named_by"].get(section, {}).items())
        counts[candidate["id"]] = {"names": len(names), "named_by": len(named_by),
                                   "unbound": table["unbound"].get(section, 0)}
        index, order = table["place"][section], table["order"]
        reach = ([(other, words, "names", True) for other, words in names[:LINKS_EACH_WAY]]
                 + [(other, words, "names", False) for other, words in named_by[:LINKS_EACH_WAY]]
                 + [(order[at], None, "beside", at > index) for at in (index - 1, index + 1) if 0 <= at < len(order)])
        for other, words, how, outward in reach:
            root = table["roots"].get(other)
            if root is None:
                issues.append({"kind": "provision", "query_id": None, "stage": "links", "position": candidate["position"],
                               "reason": f"A connected provision ({other}) has no one root part in its Act"})
                continue
            if root in hidden:
                continue
            wanted.setdefault(root, None)
            edges.append((candidate["position"], root, how, words) if outward else (root, candidate["position"], how, words))
    reading = [root for root in wanted if root not in found]
    try:
        rows = collection.read(reading) if reading else {}
    except Exception as exc:
        _log_stage_failure("provision", "links", exc)
        issues.append({"kind": "provision", "query_id": None, "stage": "links", "reason": type(exc).__name__})
        rows = {}
    connected = []
    for root in reading:
        row = rows.get(root)
        if row is None or row.get("act_id") not in tables:
            issues.append({"kind": "provision", "query_id": None, "stage": "links", "position": root,
                           "reason": "A connected provision's words cannot be read"})
            continue
        try:
            context = _whole_section(collection, root, row, None, issues)
            candidate = _candidate("provision", root, row, revision, None, [], context)
        except SearchUnavailable as exc:
            issues.append({"kind": "provision", "query_id": None, "stage": "links", "reason": str(exc), "position": root})
            continue
        found[root] = candidate["id"]
        connected.append(candidate)
    connections, seen = [], set()
    for start, end, how, words in edges:
        if start not in found or end not in found:
            continue
        edge = {"from": found[start], "to": found[end], "how": how, "words": words}
        if (edge["from"], edge["to"], how) not in seen:
            seen.add((edge["from"], edge["to"], how))
            connections.append(edge)
    return connected, connections, counts


def offered(record):
    """Every candidate a search record offers: what search returned and, from v9, the
    provisions connected to them (P32)."""
    return [*record["candidates"], *record.get("connected", ())]


class SearchPort(Protocol):
    """The held-law search as a destination: the queries carry the advocate's words, so
    the composition root polices every search like any other destination."""

    def search(self, queries, instruments=None, *, results=None) -> dict:
        ...

    def search_many(self, searches, *, results=None, done=None) -> list:
        ...

    def read_judgment(self, case_id) -> dict:
        ...


class HybridSearcher:
    """Independent lexical/vector legs and exact source reads for both corpora."""
    def __init__(self, collections):
        self.collections = collections

    @classmethod
    def local(cls, root=None, corpus_dir=None):
        root = Path(root or Path(__file__).resolve().parents[2])
        corpus = Path(corpus_dir or os.environ.get("NM_CORPUS_DIR") or root / "legal_database/vector_store")
        if not corpus.is_absolute():
            corpus = root / corpus
        models = _Models(root / ".nm/models")
        copies = {"provision": root / "pipeline" / "instrument_copies.json"}
        return cls({kind: LocalCollection(corpus_dir=corpus, lineage=root / ".nm/retrieval" / file,
            doc_type=doc_type, models=models, copies=copies.get(kind)) for kind, file, doc_type in (
                ("provision", "bare_acts.lineage.json", "bare_act"),
                ("judgment", "judgments.lineage.json", "case_law"))})

    def revision(self):
        values = {kind: collection.revision() for kind, collection in self.collections.items()}
        return _digest({"contract": CONTRACT, "collections": values}) if (
            set(values) == {"provision", "judgment"} and all(values.values())) else None

    def warm(self):
        for collection in self.collections.values():
            try:
                collection.warm()
            except SearchUnavailable:
                log.warning("A corpus could not be warmed", exc_info=True)

    def search(self, queries, instruments=None, *, results=None):
        """Search one dispute; query IDs are owned by its checked query plan. instruments
        are the Acts that plan names, matched to held instruments as search candidates.
        results sets how many candidates of each kind are returned (RESULTS_PER_KIND
        unless a caller that chooses among more asks for more; owner decision, 14 Oct)."""
        with ExitStack() as scopes:
            for collection in self.collections.values():
                scope = getattr(collection, "snapshot_scope", None)
                if callable(scope):
                    scopes.enter_context(scope())
            return self._search(queries, instruments, results)

    def search_many(self, searches, *, results=None, done=None):
        """Search a matter's questions side by side (owner, 20 Oct 2026: step 1), each exactly
        as search() searches it alone: searches are (queries, instruments) pairs, taken in their
        order. Returns one future per search at once, in order, each holding its result or its
        own failure once it finishes, so that a failed question never takes its peers' work
        with it and a dispute's questions can be read as soon as they are found (step 4, 21 Oct
        2026). done() is told as each finishes. The reranker on the graphics card still reads
        one question at a time."""
        searches = list(searches)
        if not searches:
            return []
        pool = ThreadPoolExecutor(max_workers=min(SIDE_BY_SIDE, len(searches)), thread_name_prefix="search")
        futures = [pool.submit(self.search, queries, instruments, results=results)
                   for queries, instruments in searches]
        for future in futures if done is not None else ():
            # Told apart from the result: a failure to report progress changes no search.
            future.add_done_callback(lambda _: done())
        pool.shutdown(wait=False)
        return futures

    def read_judgment(self, case_id):
        """One judgment's held paragraphs in stored order (owner decision P31, 21 Oct 2026),
        read inside one checked snapshot of the judgment store: its corpus revision and the
        (position, row) of each paragraph."""
        collection = self.collections.get("judgment")
        if collection is None or not callable(getattr(collection, "judgment_paragraphs", None)):
            raise SearchUnavailable("Held judgments cannot be read")
        revision = collection.revision()
        if not revision:
            raise SearchUnavailable("The judgment store's identity cannot be checked")
        scope = getattr(collection, "snapshot_scope", None)
        with scope() if callable(scope) else nullcontext():
            paragraphs = collection.judgment_paragraphs(case_id)
        if collection.revision() != revision:
            raise SearchUnavailable("The judgment store changed while the judgment was read")
        return {"corpus_revision": revision, "paragraphs": paragraphs}

    def _search(self, queries, instruments=None, results=None):
        if (not isinstance(queries, list) or not queries or any(
                not isinstance(q, dict) or not isinstance(q.get("query_id"), str)
                or not q["query_id"] or not isinstance(q.get("text"), str) or not q["text"].strip()
                for q in queries) or len({q["query_id"] for q in queries}) != len(queries)):
            raise ValueError("Search needs unique owned query IDs and nonblank text")
        names = [] if instruments is None else instruments
        if (not isinstance(names, list) or any(not isinstance(n, str) or not n.strip() for n in names)
                or len(set(names)) != len(names)):
            raise ValueError("Named instruments must be distinct nonblank names")
        returned = {"provision": RESULTS_PER_KIND, "judgment": RESULTS_PER_KIND, **(results or {})}
        if set(returned) != {"provision", "judgment"} or any(
                type(count) is not int or not 1 <= count <= 50 for count in returned.values()):
            raise ValueError("Each kind returns between 1 and 50 candidates")
        named = [{"name": name, "candidates": []} for name in names]
        candidates, issues, stages, revisions = [], [], [], {}
        connected, connections, links = [], [], {}
        for kind in ("provision", "judgment"):
            collection = self.collections.get(kind)
            revision = collection.revision() if collection is not None else None
            revisions[kind] = revision
            if collection is None or not revision:
                issues.append({"kind": kind, "query_id": None, "stage": "identity", "reason": "Corpus identity unavailable"})
                continue
            # Word and vector search inside the held Acts the plan names joins each
            # formulation's legs. A name proposes candidates and never resolves identity.
            within = frozenset()
            if kind == "provision" and names and callable(getattr(collection, "instrument_keys", None)):
                try:
                    held = collection.instrument_keys()
                    named = [{"name": name, "candidates": list(instrument_candidates(name, held))} for name in names]
                    keys = {key for entry in named for key in entry["candidates"]}
                    within = collection.instrument_positions(keys) if keys else frozenset()
                except SearchUnavailable as exc:
                    _log_stage_failure(kind, "instruments", exc)
                    issues.append({"kind": kind, "query_id": None, "stage": "instruments", "reason": type(exc).__name__})
                    within = frozenset()
            pool, associations = {}, {}
            # A copy the owner's register does not keep never takes a slot: each leg looks
            # twice as deep and keeps its first LEG_DEPTH positions that are not such copies.
            hidden = frozenset()
            suppressed = getattr(collection, "suppressed_positions", None)
            if callable(suppressed):
                try:
                    hidden = suppressed()
                except SearchUnavailable as exc:
                    _log_stage_failure(kind, "copy register", exc)
            depth = LEG_DEPTH * 2 if hidden else LEG_DEPTH
            # A batch embeds every formulation once and searches each corpus in one operation.
            semantic = None
            semantic_many = getattr(collection, "semantic_many", None)
            if callable(semantic_many):
                try:
                    semantic = semantic_many(tuple(q["text"] for q in queries), depth)
                    if len(semantic) != len(queries):
                        raise SearchUnavailable("Incomplete semantic query batch")
                except Exception as exc:
                    _log_stage_failure(kind, "semantic batch", exc)
                    semantic = None  # Independent calls retain any surviving query routes.
            named_semantic = None
            if within:
                try:
                    named_semantic = collection.semantic_many_within(tuple(q["text"] for q in queries), LEG_DEPTH, within)
                    if len(named_semantic) != len(queries):
                        raise SearchUnavailable("Incomplete named-instrument query batch")
                except Exception as exc:
                    _log_stage_failure(kind, "named semantic batch", exc)
                    named_semantic = None
            for index, query in enumerate(queries):
                legs = []
                for leg in ("lexical", "semantic", *(("named_lexical", "named_semantic") if within else ())):
                    try:
                        if leg == "named_lexical":
                            values = collection.lexical_within(query["text"], LEG_DEPTH, within)
                        elif leg == "named_semantic":
                            values = (named_semantic[index] if named_semantic is not None
                                      else collection.semantic_many_within((query["text"],), LEG_DEPTH, within)[0])
                        else:
                            values = semantic[index] if leg == "semantic" and semantic is not None else getattr(collection, leg)(query["text"], depth)
                        ranked, invalid = _ranked_positions(values)
                        if invalid:
                            raise SearchUnavailable("Ranked positions are malformed")
                        if leg.startswith("named_"):
                            ranked = [position for position in ranked if position in within][:LEG_DEPTH]
                        elif hidden:
                            ranked = [position for position in ranked if position not in hidden][:LEG_DEPTH]
                        legs.append(ranked)
                        stages.append({"kind": kind, "query_id": query["query_id"], "stage": leg,
                                       "state": "evaluated", "hits": len(ranked)})
                    except Exception as exc:
                        _log_stage_failure(kind, leg, exc, query["query_id"])
                        issues.append({"kind": kind, "query_id": query["query_id"], "stage": leg,
                                       "reason": type(exc).__name__})
                for position, score in sorted(_rrf(legs).items(), key=lambda x: (-x[1], x[0]))[:PER_QUERY_POOL]:
                    pool[position] = pool.get(position, 0) + score
                    associations.setdefault(position, []).append(query["query_id"])
            # v8: the reranker reads the strongest part of the fused shortlist.
            positions = _ordered(pool)[:RANK_DEPTH[kind]]
            try:
                rows = collection.read(positions)
            except Exception as exc:
                _log_stage_failure(kind, "read", exc)
                issues.append({"kind": kind, "query_id": None, "stage": "read", "reason": type(exc).__name__})
                continue
            usable, pairs, rank_contexts = [], [], {}
            rank_rows, rank_associations, rank_anchors = {}, {}, {}
            # Variants broaden recall; ranking examines their common dispute once.
            # Retain every formulation and the original account, including long tails.
            inquiry = "\n".join(dict.fromkeys(
                [q["context"] for q in queries if q.get("context")]
                + [q["text"] for q in queries]))
            shortlisted = {}  # each ranked source unit's best place in the fused shortlist
            for pool_rank, position in enumerate(positions, 1):
                row = rows.get(position)
                try:
                    checked_source = _candidate(kind, position, row, revision, None, associations[position], {})
                except SearchUnavailable as exc:
                    issues.append({"kind": kind, "query_id": None, "stage": "read", "reason": str(exc), "position": position})
                    continue
                target, context = position, None
                if kind == "provision" and row.get("parent_chunk_id"):
                    try:
                        context = collection.rank_context(position, row)
                        root = context["segments"][0]
                        target, row = root["position"], root["row"]
                        checked_source = _candidate(kind, target, row, revision, None, associations[position], context)
                    except Exception as exc:
                        _log_stage_failure(kind, "context", exc)
                        # Keep unread ancestry explicit without discarding readable peers.
                        rank_contexts[position] = {"scope": "selected_indexed_segment", "bounded": True,
                            "unread_positions": [], "segments": [{"position": position, "row": rows[position]}]}
                        issues.append({"kind": kind, "query_id": None, "stage": "context",
                            "reason": str(exc) if isinstance(exc, SearchUnavailable) else type(exc).__name__,
                            "position": position})
                        # Score readable words even when their context is missing.
                        # The exact selected source keeps its explicit coverage gap.
                        target, row, context = position, rows[position], rank_contexts[position]
                shortlisted.setdefault(target, pool_rank)
                rank_rows[target] = row
                rank_anchors[target] = _rerank_anchor(checked_source)
                rank_associations.setdefault(target, []).extend(associations[position])
                if context is not None:
                    prior = rank_contexts.get(target, {}).get("segments", [])
                    segments = {s["position"]: s for s in [*prior, *context["segments"]]}
                    rank_contexts[target] = {**context, "segments": list(segments.values())}
            units, standing = list(rank_rows), {}
            if kind == "judgment":
                # v7: an unreadable standing table costs only the citation part of the
                # order, recorded as a gap; the paragraph-kind order still applies.
                if callable(getattr(collection, "case_standing", None)):
                    try:
                        standing = collection.case_standing()
                    except SearchUnavailable as exc:
                        _log_stage_failure(kind, "standing", exc)
                        issues.append({"kind": kind, "query_id": None, "stage": "standing", "reason": str(exc)})
            # Score and return the same source unit. A sibling's relevance must not
            # be transferred from a parent window to an unrelated selected child.
            anchors = []
            for position in units:
                usable.append(position)
                pairs.append((inquiry, rank_rows[position]["full_text"]))
                anchors.append(rank_anchors[position])
            rows.update(rank_rows)
            associations.update({p: list(dict.fromkeys(ids)) for p, ids in rank_associations.items()})
            try:
                scores = collection.rerank(pairs, anchors=anchors)
                if len(scores) != len(pairs) or any(not math.isfinite(float(score)) for score in scores):
                    raise SearchUnavailable("Invalid rerank scores")
                scored, offset = [], 0
                for position in usable:
                    width = 1
                    scored.append((position, max(float(s) for s in scores[offset:offset+width])))
                    offset += width
                scored.sort(key=lambda x: (-x[1], _location_order(x[0])))
                if kind == "provision":
                    # v6: the reranker reads all formulations as one inquiry; the shortlist
                    # records how strongly the formulations agree. Their orders are blended
                    # by reciprocal ranks; the candidate keeps the reranker's own score.
                    reranked = {position: rank for rank, (position, _) in enumerate(scored, 1)}
                    scored.sort(key=lambda x: (-(1.0 / (RRF_K + reranked[x[0]]) + 1.0 / (RRF_K + shortlisted[x[0]])),
                                               _location_order(x[0])))
                elif kind == "judgment":
                    scored = _judgment_order(scored, rows, standing)
                stages.append({"kind": kind, "query_id": None, "stage": "rerank", "state": "evaluated", "hits": len(usable)})
            except Exception as exc:
                _log_stage_failure(kind, "rerank", exc)
                issues.append({"kind": kind, "query_id": None, "stage": "rerank", "reason": type(exc).__name__})
                scored = [(position, None) for position in usable]
            selected, groups = [], {}
            for position, score in scored:
                row = rows[position]
                # Unique ancestry already maps connected hits to their root
                # position. Equal printed section numbers cannot suppress peers.
                group = (position,) if kind == "provision" else (row.get("case_id"),)
                if not all(group):
                    group = (position,)
                if groups.get(group, 0) >= (1 if kind == "provision" else 2):
                    continue
                groups[group] = groups.get(group, 0) + 1
                selected.append((position, score))
                if len(selected) == returned[kind]:
                    break
            for position, score in selected:
                try:
                    context = rank_contexts.get(position)
                    if kind == "provision":
                        # v9 (P32): every returned provision is read whole.
                        context = _whole_section(collection, position, rows[position], context, issues)
                    elif context is None:
                        context = collection.context(position, rows[position])
                except _ContextGap as exc:
                    context = exc.context
                    issues.append({"kind": kind, "query_id": None, "stage": "context",
                                   "reason": str(exc), "position": position})
                except Exception as exc:
                    _log_stage_failure(kind, "context", exc)
                    context = {"scope": "selected_indexed_segment", "bounded": True, "unread_positions": [],
                               "segments": [{"position": position, "row": rows[position]}]}
                    issues.append({"kind": kind, "query_id": None, "stage": "context",
                        "reason": str(exc) if isinstance(exc, SearchUnavailable) else type(exc).__name__,
                        "position": position})
                if (context["bounded"] or context["unread_positions"]) and not any(
                        issue["kind"] == kind and issue["stage"] == "context"
                        and issue.get("position") == position for issue in issues):
                    issues.append({"kind": kind, "query_id": None, "stage": "context", "reason": "Context has an explicit gap", "position": position})
                candidates.append(_candidate(kind, position, rows[position], revision, score, associations[position], context))
            if kind == "provision":
                connected, connections, links = _connect(
                    collection, revision, [c for c in candidates if c["kind"] == kind], issues)
            if collection.revision() != revision:
                candidates = [c for c in candidates if c["kind"] != kind]
                if kind == "provision":
                    connected, connections, links = [], [], {}
                issues.append({"kind": kind, "query_id": None, "stage": "identity", "reason": "Corpus changed during search"})
        state = "partial" if issues else "ready"
        return {"contract": CONTRACT, "state": state, "queries": deepcopy(queries), "instruments": named,
                "corpus_revisions": revisions, "stages": stages, "candidates": candidates, "issues": issues,
                "connected": connected, "connections": connections, "links": links}


def validate_search(record, queries, instruments=None):
    """Replay validates the saved exact snapshot, never reads a changed corpus.
    instruments are the Acts the plan named; a v6 or v7 record keeps them with the held
    candidates each proposed when it was searched."""
    current = isinstance(record, dict) and record.get("contract") in (
        NAMED_CONTRACT, JUDGMENT_ORDER_CONTRACT, RANK_DEPTH_CONTRACT, CONNECTED_CONTRACT, CONTRACT)
    connecting = isinstance(record, dict) and record.get("contract") in (CONNECTED_CONTRACT, CONTRACT)
    fields = {"contract", "state", "queries", "corpus_revisions", "stages", "candidates", "issues"}
    if (not isinstance(record, dict) or set(record) != (
            fields | {"instruments"} | ({"connected", "connections", "links"} if connecting else set()) if current else fields)
            or record["contract"] not in (LEGACY_CONTRACT, PARENT_TREE_CONTRACT, PREVIOUS_CONTRACT, PARENT_STORE_CONTRACT,
                                          RERANK_ORDER_CONTRACT, NAMED_CONTRACT, JUDGMENT_ORDER_CONTRACT,
                                          RANK_DEPTH_CONTRACT, CONNECTED_CONTRACT, CONTRACT)
            or record["queries"] != queries
            or record["state"] != ("partial" if record["issues"] else "ready")
            or set(record["corpus_revisions"]) != {"provision", "judgment"}):
        raise ValueError("Search snapshot differs from its owned query contract")
    if any(not isinstance(record[key], list) for key in ("stages", "candidates", "issues")):
        raise ValueError("Search receipts and gaps must be explicit arrays")
    proposed = False
    if current:
        named = record["instruments"]
        if (not isinstance(named, list) or [entry.get("name") if isinstance(entry, dict) else None for entry in named]
                != ([] if instruments is None else instruments)
                or any(set(entry) != {"name", "candidates"} or not isinstance(entry["candidates"], list)
                       or any(not isinstance(key, str) or not key for key in entry["candidates"]) for entry in named)):
            raise ValueError("Search instruments differ from the Acts its plan named")
        proposed = any(entry["candidates"] for entry in named)
    elif instruments:
        raise ValueError("A historical search did not search named instruments")
    legs = ("lexical", "semantic", "named_lexical", "named_semantic") if current else ("lexical", "semantic")
    query_ids = {q["query_id"] for q in queries}
    evaluated = set()
    for stage in record["stages"]:
        if (not isinstance(stage, dict) or set(stage) != {"kind", "query_id", "stage", "state", "hits"}
                or stage["kind"] not in record["corpus_revisions"] or stage["state"] != "evaluated"
                or type(stage["hits"]) is not int or stage["hits"] < 0
                or stage["stage"] not in (*legs, "rerank")
                or stage["stage"].startswith("named_") and (stage["kind"] != "provision" or not proposed)
                or (stage["query_id"] not in query_ids if stage["stage"] != "rerank" else stage["query_id"] is not None)):
            raise ValueError("Search stage has no owned query/kind disposition")
        key = stage["kind"], stage["query_id"], stage["stage"]
        if key in evaluated:
            raise ValueError("Search stage receipt is duplicated")
        evaluated.add(key)
    failed = set()
    for issue in record["issues"]:
        if (not isinstance(issue, dict) or not {"kind", "query_id", "stage", "reason"} <= issue.keys()
                or issue["kind"] not in record["corpus_revisions"]
                or issue["query_id"] is not None and issue["query_id"] not in query_ids
                or issue["stage"] not in ("identity", *legs, "read", "rerank", "context", *(("instruments",) if current else ()),
                                          *(("standing",) if record["contract"] in (
                                              JUDGMENT_ORDER_CONTRACT, RANK_DEPTH_CONTRACT, CONNECTED_CONTRACT, CONTRACT) else ()),
                                          *(("links",) if connecting else ()))
                or issue["stage"] == "links" and (issue["kind"] != "provision" or issue["query_id"] is not None)
                or issue["stage"].startswith("named_") and (issue["kind"] != "provision" or not proposed)
                or issue["stage"] == "standing" and (issue["kind"] != "judgment" or issue["query_id"] is not None)
                or not isinstance(issue["reason"], str) or not issue["reason"]):
            raise ValueError("Search gap has no owned query/source scope")
        failed.add((issue["kind"], issue["query_id"], issue["stage"]))
    for kind, revision in record["corpus_revisions"].items():
        if (kind, None, "identity") in failed:
            if any(c["kind"] == kind for c in record["candidates"]):
                raise ValueError("Changed or unavailable corpus cannot admit candidates")
            continue
        if not isinstance(revision, str) or not revision:
            raise ValueError("Search has no checked corpus identity")
        for query_id in query_ids:
            for leg in ("lexical", "semantic"):
                key = kind, query_id, leg
                if (key in evaluated) == (key in failed):
                    raise ValueError("Every query/search leg needs exactly one execution disposition")
        # Named legs run for every formulation when the named Acts' passages were read,
        # and for none when they proposed nothing held or could not be read.
        ran = {(query_id, leg) for (k, query_id, leg) in evaluated | failed if k == kind and leg.startswith("named_")}
        if ran and ran != {(query_id, leg) for query_id in query_ids for leg in ("named_lexical", "named_semantic")}:
            raise ValueError("Every query/search leg needs exactly one execution disposition")
        if ran and any((kind, q, leg) in evaluated and (kind, q, leg) in failed for q, leg in ran):
            raise ValueError("Every query/search leg needs exactly one execution disposition")
        if not any((kind, None, stage) in failed for stage in ("read", "rerank")) and (kind, None, "rerank") not in evaluated:
            raise ValueError("Reranking has no execution disposition")
    identities = set()
    returned = len(record["candidates"])
    if connecting and (not isinstance(record["connected"], list) or not isinstance(record["connections"], list)
                       or not isinstance(record["links"], dict)):
        raise ValueError("Connected provisions must be explicit arrays")
    for number, candidate in enumerate([*record["candidates"], *(record["connected"] if connecting else ())]):
        # v9 (P32): a connected provision was found through a returned one, not by a query.
        joined = number >= returned
        if record["contract"] not in (PARENT_STORE_CONTRACT, RERANK_ORDER_CONTRACT, NAMED_CONTRACT, JUDGMENT_ORDER_CONTRACT,
                                      RANK_DEPTH_CONTRACT, CONNECTED_CONTRACT, CONTRACT) and any(type(p) is not int for p in (
                candidate["position"], *(s["position"] for s in candidate["context"]["segments"]))):
            raise ValueError("Historical search cannot contain contextual parent addresses")
        if (candidate["kind"] not in record["corpus_revisions"]
                or candidate["corpus_revision"] != record["corpus_revisions"][candidate["kind"]]
                or not set(candidate["query_ids"]) <= {q["query_id"] for q in queries}
                or bool(candidate["query_ids"]) == joined or candidate["id"] in identities
                or joined and (candidate["kind"] != "provision" or candidate["score"] is not None)):
            raise ValueError("Candidate has no owned source/query binding")
        expected = _candidate(candidate["kind"], candidate["position"], candidate["source"],
            candidate["corpus_revision"], candidate["score"], candidate["query_ids"], candidate["context"])
        if expected != candidate:
            raise ValueError("Candidate changed its exact stored projection")
        for segment in candidate["context"]["segments"]:
            row = segment["row"]
            document_field = "act_id" if candidate["kind"] == "provision" else "case_id"
            if (row.get(document_field) != candidate["source"].get(document_field)
                    or not row.get("full_text") or segment.get("content_digest") != _digest(row)
                    or not _valid_location(candidate["kind"], segment.get("position"), row)):
                raise ValueError("Context crossed source-document ownership")
            if candidate["context"]["scope"] in ("indexed_section_segments", "exact_parent_tree") and row.get("section_number") != candidate["source"].get("section_number"):
                raise ValueError("Context crossed the selected section")
        context = candidate["context"]
        if (set(context) != {"scope", "bounded", "unread_positions", "segments"}
                or context["scope"] not in ("indexed_section_segments", "adjacent_indexed_segments", "selected_indexed_segment", "exact_parent_tree")
                or type(context["bounded"]) is not bool or not isinstance(context["unread_positions"], list)
                or not any(s["position"] == candidate["position"] and s["row"] == candidate["source"] for s in context["segments"])
                or (context["bounded"] or context["unread_positions"]) and (candidate["kind"], None, "context") not in failed):
            raise ValueError("Exact selected context or its coverage is missing")
        if context["scope"] == "exact_parent_tree":
            segments = context["segments"]
            by_id = {}
            for segment in segments:
                by_id.setdefault(segment["row"]["chunk_id"], []).append(segment["row"])
            root = candidate["source"]
            if (record["contract"] not in (PARENT_TREE_CONTRACT, PREVIOUS_CONTRACT, PARENT_STORE_CONTRACT, RERANK_ORDER_CONTRACT,
                                           NAMED_CONTRACT, JUDGMENT_ORDER_CONTRACT, RANK_DEPTH_CONTRACT, CONNECTED_CONTRACT, CONTRACT)
                    or candidate["kind"] != "provision" or len(segments) < 2
                    or root.get("parent_chunk_id") or len(by_id[root["chunk_id"]]) != 1
                    or len({s["position"] for s in segments}) != len(segments)):
                raise ValueError("Ranking context has no unique owned root")
            for segment in segments:
                child, seen = segment["row"], set()
                while child["chunk_id"] != root["chunk_id"]:
                    identity = child["chunk_id"]
                    parents = by_id.get(child.get("parent_chunk_id"), [])
                    if identity in seen or len(parents) != 1:
                        raise ValueError("Ranking context has a detached or cyclic source")
                    seen.add(identity)
                    child = parents[0]
        if record["contract"] in (PREVIOUS_CONTRACT, PARENT_STORE_CONTRACT, RERANK_ORDER_CONTRACT, NAMED_CONTRACT,
                                  JUDGMENT_ORDER_CONTRACT, RANK_DEPTH_CONTRACT, CONNECTED_CONTRACT, CONTRACT) and candidate["kind"] == "provision":
            segments = context["segments"]
            if context["scope"] == "selected_indexed_segment":
                if len(segments) != 1:
                    raise ValueError("A selected source cannot certify disconnected neighbours")
            elif context["scope"] in ("indexed_section_segments", "exact_parent_tree"):
                by_id = {s["row"]["chunk_id"]: s["row"] for s in segments}
                roots = [s["row"] for s in segments if not s["row"].get("parent_chunk_id")]
                if (len(by_id) != len(segments) or len(roots) != 1
                        or len({s["position"] for s in segments}) != len(segments)):
                    raise ValueError("Provision context has no unique connected root")
                for segment in segments:
                    child, seen = segment["row"], set()
                    while child["chunk_id"] != roots[0]["chunk_id"]:
                        identity, parent = child["chunk_id"], child.get("parent_chunk_id")
                        if identity in seen or parent not in by_id:
                            raise ValueError("Provision context is detached or cyclic")
                        seen.add(identity)
                        child = by_id[parent]
            else:
                raise ValueError("A provision cannot use unrelated adjacent source positions")
        identities.add(candidate["id"])
    if connecting:
        _validate_connections(record)
    return deepcopy(record)


def _validate_connections(record):
    """v9 (P32): each connection joins two offered provisions of one Act, at least one
    returned by search, as the words of one name the other or as neighbours in their Act;
    every connected provision is joined to a returned one; each returned provision's link
    counts cover what is shown of them."""
    returned = {c["id"]: c for c in record["candidates"] if c["kind"] == "provision"}
    offered_by_id = {**returned, **{c["id"]: c for c in record["connected"]}}
    seen, reached = set(), set()
    shown = {identity: {"names": 0, "named_by": 0} for identity in returned}
    for edge in record["connections"]:
        if (not isinstance(edge, dict) or set(edge) != {"from", "to", "how", "words"}
                or edge["how"] not in CONNECTIONS or edge["from"] not in offered_by_id or edge["to"] not in offered_by_id
                or edge["from"] == edge["to"] or not ({edge["from"], edge["to"]} & returned.keys())
                or (edge["from"], edge["to"], edge["how"]) in seen
                or (edge["how"] == "names") != (isinstance(edge["words"], str) and bool(edge["words"].strip()))
                or edge["how"] == "beside" and edge["words"] is not None):
            raise ValueError("A connection has no owned pair of offered provisions")
        if offered_by_id[edge["from"]]["source"].get("act_id") != offered_by_id[edge["to"]]["source"].get("act_id"):
            raise ValueError("A connection crosses from one Act into another")
        seen.add((edge["from"], edge["to"], edge["how"]))
        for end, other in (("from", "to"), ("to", "from")):
            if edge[end] in returned:
                reached.add(edge[other])
                if edge["how"] == "names":
                    shown[edge[end]]["names" if end == "from" else "named_by"] += 1
    if not (offered_by_id.keys() - returned.keys()) <= reached:
        raise ValueError("A connected provision is joined to no returned provision")
    for identity, counts in record["links"].items():
        if (identity not in returned or not isinstance(counts, dict) or set(counts) != {"names", "named_by", "unbound"}
                or any(type(value) is not int or value < 0 for value in counts.values())
                or shown[identity]["names"] > counts["names"] or shown[identity]["named_by"] > counts["named_by"]):
            raise ValueError("A returned provision's link counts do not cover its connections")


