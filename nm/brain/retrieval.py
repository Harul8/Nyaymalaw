"""Local candidate search over the held bare-act and judgment passages.

Search ranks possible sources; it does not decide what law governs or what a
judgment holds. Every returned quotation is read back from the passage store.
The two indexes and the local models load only when a search is requested.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import struct
import threading
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Protocol

EMBED_MODEL = "BAAI/bge-large-en-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DIMENSIONS = 1024
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
LEG_DEPTH = 80
PER_QUERY_POOL = 18
RESULTS_PER_KIND = 6
RRF_K = 60
ATTRIBUTABLE_PARAGRAPHS = frozenset({"ratio", "reasoning", "order"})
log = logging.getLogger(__name__)


class SearchUnavailable(RuntimeError):
    """The local collection cannot be searched reliably."""


class Collection(Protocol):
    """Injectable boundary for one indexed corpus."""

    def lexical(self, query: str, depth: int) -> list[int]: ...

    def semantic(self, query: str, depth: int) -> list[int]: ...

    def read(self, positions: list[int]) -> dict[int, dict]: ...

    def rerank(self, pairs: list[tuple[str, str]]) -> list[float]: ...


def _rrf(lists: list[list[int]]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked in lists:
        for rank, position in enumerate(dict.fromkeys(ranked), 1):
            scores[position] = scores.get(position, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def _ordered(scores: dict[int, float]) -> list[int]:
    return sorted(scores, key=lambda position: (-scores[position], position))


class _Models:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._loaded: tuple[object, object] | None = None
        self.lock = threading.RLock()

    def load(self) -> tuple[object, object]:
        with self.lock:
            if self._loaded is not None:
                return self._loaded
            embed = self.folder / EMBED_MODEL.replace("/", "__")
            judge = self.folder / RERANK_MODEL.replace("/", "__")
            if not embed.is_dir() or not judge.is_dir():
                raise SearchUnavailable("local embedding or reranking model is absent")
            try:
                import torch
                from sentence_transformers import CrossEncoder, SentenceTransformer
            except (ImportError, OSError) as exc:
                raise SearchUnavailable(f"local search models cannot load: {exc}") from exc
            device = "cuda" if torch.cuda.is_available() else "cpu"
            try:
                self._loaded = (
                    SentenceTransformer(str(embed), device=device, local_files_only=True),
                    CrossEncoder(str(judge), device=device, max_length=512,
                                 local_files_only=True),
                )
            except (OSError, RuntimeError, ValueError) as exc:
                raise SearchUnavailable(f"local search models cannot load: {exc}") from exc
            return self._loaded


class LocalCollection:
    """One coherent vector, word, and exact-passage collection."""

    def __init__(self, *, corpus_dir: Path, lineage: Path, doc_type: str,
                 models: _Models) -> None:
        self.corpus_dir = corpus_dir
        self.lineage = lineage
        self.doc_type = doc_type
        self.models = models
        self._loaded: tuple[object, object, Path, int] | None = None
        self._lock = threading.Lock()

    def _open(self) -> tuple[object, object, Path, int]:
        if self._loaded is not None:
            return self._loaded
        with self._lock:
            if self._loaded is not None:
                return self._loaded
            try:
                record = json.loads(self.lineage.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise SearchUnavailable(f"{self.doc_type} lineage is unavailable") from exc
            if (record.get("schema") != 1 or record.get("doc_type") != self.doc_type
                    or record.get("model") != EMBED_MODEL
                    or record.get("dimensions") != DIMENSIONS):
                raise SearchUnavailable(f"{self.doc_type} lineage does not match the search model")
            verified = record.get("verified") or {}
            if (not verified.get("sampled")
                    or verified.get("same_vector") != verified.get("sampled")
                    or verified.get("mean_similarity", 0) < 0.99):
                raise SearchUnavailable(f"{self.doc_type} vector-to-passage lineage is unverified")
            words = verified.get("words")
            if words and (words.get("no_indexed_words")
                          or words.get("own_position") != words.get("sampled")):
                raise SearchUnavailable(f"{self.doc_type} word-to-passage lineage is unverified")
            vector_ref = record.get("vector_index") or {}
            bm_ref = record.get("bm25") or {}
            store_ref = record.get("passage_store") or {}
            vector_path = self.corpus_dir / str(vector_ref.get("path") or "")
            bm_path = self.corpus_dir / str(bm_ref.get("path") or "")
            db_path = self.corpus_dir / str(store_ref.get("path") or "")
            count = record.get("passages")
            tail = record.get("vectors_without_passage", 0)
            if not isinstance(count, int) or count < 1 or not isinstance(tail, int) or tail < 0:
                raise SearchUnavailable(f"{self.doc_type} lineage has invalid passage counts")
            try:
                with vector_path.open("rb") as stream:
                    header = stream.read(16)
                kind = header[:4]
                dims = struct.unpack("<i", header[4:8])[0]
                vectors = struct.unpack("<q", header[8:16])[0]
                params = (bm_path / "params.index.json").read_bytes()
                bm_count = json.loads(params)["num_docs"]
                connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                try:
                    stored, last = connection.execute(
                        "select count(*), max(pos) from chunks where doc_type=?",
                        (self.doc_type,),
                    ).fetchone()
                finally:
                    connection.close()
            except (OSError, ValueError, KeyError, struct.error, sqlite3.Error) as exc:
                raise SearchUnavailable(
                    f"{self.doc_type} search artifacts cannot be checked") from exc
            if (kind != b"IxFI" or dims != DIMENSIONS or vectors != count + tail
                    or vectors != vector_ref.get("vectors")
                    or vector_path.stat().st_size != vector_ref.get("bytes")
                    or bm_count != count or bm_count != bm_ref.get("num_docs")
                    or hashlib.sha256(params).hexdigest() != bm_ref.get("params_sha256")
                    or stored != count or last != count - 1):
                raise SearchUnavailable(
                    f"{self.doc_type} index and passage counts or lineage differ")
            try:
                import bm25s
                import faiss

                flags = faiss.IO_FLAG_MMAP_IFC | faiss.IO_FLAG_READ_ONLY
                index = faiss.read_index(str(vector_path), flags)
                bm25 = bm25s.BM25.load(str(bm_path), mmap=True)
                self.models.load()
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                raise SearchUnavailable(f"{self.doc_type} local index cannot load: {exc}") from exc
            self._loaded = index, bm25, db_path, count
            return self._loaded

    def lexical(self, query: str, depth: int) -> list[int]:
        _, bm25, _, count = self._open()
        try:
            import numpy as np

            tokens = [token for token in query.lower().split() if token in bm25.vocab_dict]
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
        index, _, _, count = self._open()
        try:
            import numpy as np

            encoder, _ = self.models.load()
            with self.models.lock:
                vector = encoder.encode([QUERY_INSTRUCTION + query for query in queries],
                                        normalize_embeddings=True, convert_to_numpy=True)
                _, positions = index.search(np.asarray(vector, dtype="float32"), depth)
            return [[int(pos) for pos in row if 0 <= pos < count]
                    for row in positions]
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise SearchUnavailable(f"{self.doc_type} semantic search failed: {exc}") from exc

    def read(self, positions: list[int]) -> dict[int, dict]:
        _, _, db_path, count = self._open()
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
                    f"select pos, chunk_id, blob from chunks where doc_type=? and pos in ({marks})",
                    (self.doc_type, *batch),
                )
                for pos, chunk_id, blob in rows:
                    try:
                        item = json.loads(blob)
                    except ValueError:
                        continue
                    if (item.get("doc_type", self.doc_type) == self.doc_type
                            and item.get("chunk_id") == chunk_id
                            and isinstance(item.get("full_text"), str)
                            and item["full_text"].strip()):
                        found[int(pos)] = item
        except sqlite3.Error as exc:
            raise SearchUnavailable(f"{self.doc_type} passages cannot be read") from exc
        finally:
            connection.close()
        return found

    def rerank(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        _, model = self.models.load()
        shortened = [(query, passage[:2000]) for query, passage in pairs]
        try:
            with self.models.lock:
                scores = model.predict(shortened, batch_size=32,
                                       show_progress_bar=False)
            return [float(score) for score in scores]
        except (OSError, RuntimeError, ValueError) as exc:
            raise SearchUnavailable(f"{self.doc_type} reranking failed: {exc}") from exc


def _candidate(kind: str, row: dict, score: float, source_path: str) -> dict:
    chunk_id = str(row["chunk_id"])
    # The held corpus repeats chunk IDs, so the passage's words and locator
    # participate in identity. This survives a reordered index without joining
    # distinct passages under one citation.
    identity = json.dumps(row, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    passage_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    if kind == "provision":
        title = str(row.get("act_name") or row.get("act_id") or "")
        section = str(row.get("section_number") or "")
        locator = f"{title}, {section}" if section else title
        court, held_date = "", str(row.get("year") or "")
    else:
        title = str(row.get("case_name") or row.get("case_id") or "")
        cite = str(row.get("citation") or "")
        paragraph = str(row.get("paragraph_num") or "")
        locator = ", ".join(part for part in (
            title, cite, f"paragraph {paragraph}" if paragraph else "") if part)
        court, held_date = str(row.get("court") or ""), str(row.get("year") or "")
    return {
        "id": f"{kind}:{passage_id}", "kind": kind, "title": title,
        "locator": locator, "text": row["full_text"], "court": court,
        "date": held_date, "score": round(float(score), 5),
        "source_path": source_path, "source_chunk_id": chunk_id,
    }


class HybridSearcher:
    """Search every query in both collections; retain each query's best pool."""

    def __init__(self, collections: Mapping[str, Collection], *,
                 source_paths: Mapping[str, str] | None = None) -> None:
        self.collections = collections
        self.source_paths = source_paths or {}

    @classmethod
    def local(cls, *, root: Path | None = None,
              corpus_dir: Path | None = None) -> HybridSearcher:
        root = root or Path(__file__).resolve().parents[2]
        corpus = (Path(corpus_dir) if corpus_dir is not None else
                  Path(os.environ.get("NM_CORPUS_DIR") or
                       root / "legal_database" / "vector_store"))
        if not corpus.is_absolute():
            corpus = root / corpus
        lineage = root / ".nm" / "retrieval"
        models = _Models(root / ".nm" / "models")
        return cls({
            "provision": LocalCollection(corpus_dir=corpus,
                                         lineage=lineage / "bare_acts.lineage.json",
                                         doc_type="bare_act", models=models),
            "judgment": LocalCollection(corpus_dir=corpus,
                                        lineage=lineage / "judgments.lineage.json",
                                        doc_type="case_law", models=models),
        }, source_paths={"provision": str(corpus / "chunks.db"),
                         "judgment": str(corpus / "chunks.db")})

    def search_dispute(self, dispute: dict, queries: tuple[str, ...], *,
                       as_of: date | None = None, jurisdiction: str = "") -> dict:
        """Return ranked, exact source candidates, never a legal-support verdict.

        ``dispute`` names the owner of this search but does not itself add a
        query: the caller must supply independently formulated search routes.
        ``jurisdiction`` is retained for downstream applicability analysis;
        keyword-based geographic exclusion here would erase possible law.
        """
        del dispute, jurisdiction
        clean = tuple(dict.fromkeys(" ".join(query.split()) for query in queries
                                        if isinstance(query, str) and query.strip()))[:4]
        if not clean:
            return {"state": "unavailable", "candidates": [],
                    "diagnostics": ["No dispute-specific search formulations were supplied."]}
        all_candidates: list[dict] = []
        diagnostics: list[str] = []
        searched = 0
        for kind in ("provision", "judgment"):
            collection = self.collections.get(kind)
            if collection is None:
                diagnostics.append(f"{kind} search is not configured")
                continue
            try:
                per_query: list[list[int]] = []
                query_by_position: dict[int, list[str]] = {}
                semantic_many = getattr(collection, "semantic_many", None)
                if callable(semantic_many):
                    semantic_lists = semantic_many(clean, LEG_DEPTH)
                else:
                    semantic_lists = [collection.semantic(query, LEG_DEPTH)
                                      for query in clean]
                if len(semantic_lists) != len(clean):
                    raise SearchUnavailable(f"{kind} semantic search returned incomplete results")
                for query, semantic in zip(clean, semantic_lists, strict=True):
                    lexical = collection.lexical(query, LEG_DEPTH)
                    shortlist = _ordered(_rrf([lexical, semantic]))[:PER_QUERY_POOL]
                    per_query.append(shortlist)
                    for position in shortlist:
                        query_by_position.setdefault(position, []).append(query)
                pool = _ordered(_rrf(per_query))
                rows = collection.read(pool)
                allowed: list[tuple[int, dict]] = []
                filtered = 0
                for position in pool:
                    row = rows.get(position)
                    if row is None:
                        continue
                    if (not isinstance(row.get("chunk_id"), str)
                            or not isinstance(row.get("full_text"), str)
                            or not row["full_text"].strip()):
                        continue
                    if kind == "judgment":
                        if row.get("paragraph_type") not in ATTRIBUTABLE_PARAGRAPHS:
                            filtered += 1
                            continue
                        year = str(row.get("year") or "")
                        if as_of is not None and year.isdigit() and int(year) > as_of.year:
                            filtered += 1
                            continue
                    allowed.append((position, row))
                pairs = [(query, row["full_text"])
                         for position, row in allowed
                         for query in query_by_position[position]]
                scores = collection.rerank(pairs)
                if (len(scores) != len(pairs)
                        or any(not math.isfinite(float(score)) for score in scores)):
                    raise SearchUnavailable(f"{kind} reranker returned invalid scores")
                judged = []
                offset = 0
                for position, row in allowed:
                    width = len(query_by_position[position])
                    judged.append(((position, row), max(scores[offset:offset + width])))
                    offset += width
                ranked = sorted(judged, key=lambda item: -item[1])
                seen: set[tuple[str, str]] = set()
                for (position, row), score in ranked:
                    del position
                    key = ((str(row.get("act_id") or ""), str(row.get("section_number") or ""))
                           if kind == "provision" else (str(row.get("case_id") or ""), ""))
                    if key in seen:
                        continue
                    candidate = _candidate(
                        kind, row, score, self.source_paths.get(kind, ""))
                    if not candidate["title"].strip() or not candidate["locator"].strip():
                        continue
                    seen.add(key)
                    all_candidates.append(candidate)
                    if len(seen) >= RESULTS_PER_KIND:
                        break
                if filtered:
                    diagnostics.append(
                        f"{kind} search excluded {filtered} non-attributable or later passages")
                if not seen:
                    diagnostics.append(f"{kind} search found no readable candidate passages")
                searched += 1
            except SearchUnavailable as exc:
                log.warning("%s search unavailable: %s", kind, exc)
                diagnostics.append(
                    f"{kind} search unavailable: the local corpus could not be searched")
            except Exception:  # noqa: BLE001 - external index boundary must fail closed
                log.exception("%s search failed", kind)
                diagnostics.append(f"{kind} search unavailable: local index failure")
        state = "ok" if searched == 2 else "partial" if searched else "unavailable"
        return {"state": state,
                "candidates": all_candidates if searched else [],
                "diagnostics": diagnostics}


@lru_cache(maxsize=1)
def _default_searcher() -> HybridSearcher:
    return HybridSearcher.local()


def search_dispute(dispute: dict, queries: tuple[str, ...], *,
                   as_of: date | None = None, jurisdiction: str = "") -> dict:
    """Public default search; inject ``HybridSearcher`` for tests or other stores."""
    return _default_searcher().search_dispute(dispute, queries, as_of=as_of,
                                              jurisdiction=jurisdiction)
