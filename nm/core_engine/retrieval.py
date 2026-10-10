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
from copy import deepcopy
from contextlib import closing
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
RRF_K = 60
CONTRACT = "hybrid_retrieval_v4"
PREVIOUS_CONTRACT = "hybrid_retrieval_v3"
PARENT_TREE_CONTRACT = "hybrid_retrieval_v2"
LEGACY_CONTRACT = "hybrid_retrieval_v1"
MAX_RERANK_PAIRS = 4096
MAX_CONTEXT_SEGMENTS = 500
log = logging.getLogger(__name__)

# The index's own tokenisation has one owner, shared with the index builds: a
# query cut differently from the built index silently stops meeting its words.
from nm.shared.citation_contracts import bm25_tokens, bind_provision_key, ProvisionKeyState  # noqa: E402


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
                        max_length=512, local_files_only=True,
                        model_kwargs={"torch_dtype": torch.float16} if device == "cuda" else {}))
            except (ImportError, OSError, RuntimeError, ValueError) as exc:
                raise SearchUnavailable(f"Local {which} model cannot load") from exc
            return self._loaded[which]

    def load(self):
        return self._model("embedding"), self._model("reranking")

    @lru_cache(maxsize=8)
    def encode(self, queries: tuple[str, ...]):
        """Both corpus indices reuse one batch in their verified vector space."""
        encoder = self._model("embedding")
        capacity = encoder.max_seq_length - len(encoder.tokenizer.encode(
            QUERY_INSTRUCTION, add_special_tokens=False)) - 4
        slices, groups = [], []
        for query in queries:
            start = len(slices)
            slices.extend(QUERY_INSTRUCTION + window[2] for window in token_windows(
                query, encoder.tokenizer, capacity))
            groups.append((start, len(slices)))
        with self.lock:
            vectors = encoder.encode(slices, normalize_embeddings=True, convert_to_numpy=True)
        return vectors, groups


class LocalCollection:
    """One coherent vector, word, and exact-passage collection."""

    def __init__(self, *, corpus_dir: Path, lineage: Path, doc_type: str,
                 models: _Models) -> None:
        self.corpus_dir = corpus_dir
        self.lineage = lineage
        self.doc_type = doc_type
        self.models = models
        self._loaded: tuple[dict, Path, int] | None = None
        self._vectors = None
        self._words = None
        self._revision: str | None = None
        self._lock = threading.Lock()
        self._parent_stamp = None
        self._parent_hash = None
        self._parents = None

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
            raw = json.dumps([identity, self._parent_identity(record)], separators=(",", ":")).encode() + lineage
            return hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _check_snapshot(self) -> None:
        if self._revision is None or self.revision() != self._revision:
            raise SearchUnavailable("The loaded corpus changed; reload its search indices")

    def warm(self) -> None:
        self._open()

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
                    "select pos from chunks where doc_type=? and act_id=? and section_number=? order by pos limit ?",
                    (self.doc_type, act_id, binding.key, MAX_CONTEXT_SEGMENTS + 1))]
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
            for (query, passage), anchor in zip(pairs, anchors, strict=True):
                first = len(windows)
                if query not in query_windows:
                    query_windows[query] = [(text, 512 - len(model.tokenizer.encode(
                        text, add_special_tokens=False)) - model.tokenizer.num_special_tokens_to_add(pair=True))
                        for _, _, text in token_windows(query, model.tokenizer, 160)]
                for query_window, room in query_windows[query]:
                    key = passage, room, anchor
                    if key not in passage_windows:
                        passage_windows[key] = _anchored_windows(passage, model.tokenizer, room, anchor)
                    # Reuse preparation only inside this call. Repeated prediction
                    # pairs retain their original order, count and score ownership.
                    windows.extend((query_window, text) for text in passage_windows[key])
                groups.append((first, len(windows)))
            if len(windows) > MAX_RERANK_PAIRS:
                raise SearchUnavailable("The complete passage windows exceed the local rerank budget")
            with self.models.lock:
                scores = model.predict(windows, batch_size=16,
                                       show_progress_bar=False)
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
                    "select pos from chunks where doc_type=? and act_id=? and chunk_id=? limit 2",
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
                    "select pos from chunks where doc_type=? and act_id=? and chunk_id=? limit 2",
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
                    "select pos from chunks where doc_type=? and act_id=? and section_number=? order by pos limit ?",
                    (self.doc_type, row["act_id"], str(row["section_number"]), MAX_CONTEXT_SEGMENTS + 1)) ]
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


def token_windows(text, tokenizer, capacity, overlap=32):
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
    """Keep owned document identity on every exact body window without truncation."""
    if not anchor:
        return [part for _, _, part in token_windows(text, tokenizer, capacity)]
    room = capacity - len(tokenizer.encode(anchor, add_special_tokens=False)) - 8
    while True:
        pieces = [anchor + part for _, _, part in token_windows(text, tokenizer, room)]
        overflow = max(0, max(len(tokenizer.encode(part, add_special_tokens=False)) - capacity
                              for part in pieces))
        if not overflow:
            return pieces
        room -= overflow


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
        return cls({kind: LocalCollection(corpus_dir=corpus, lineage=root / ".nm/retrieval" / file,
            doc_type=doc_type, models=models) for kind, file, doc_type in (
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

    def search(self, queries):
        """Search one dispute; query IDs are owned by its checked query plan."""
        if (not isinstance(queries, list) or not queries or any(
                not isinstance(q, dict) or not isinstance(q.get("query_id"), str)
                or not q["query_id"] or not isinstance(q.get("text"), str) or not q["text"].strip()
                for q in queries) or len({q["query_id"] for q in queries}) != len(queries)):
            raise ValueError("Search needs unique owned query IDs and nonblank text")
        candidates, issues, stages, revisions = [], [], [], {}
        for kind in ("provision", "judgment"):
            collection = self.collections.get(kind)
            revision = collection.revision() if collection is not None else None
            revisions[kind] = revision
            if collection is None or not revision:
                issues.append({"kind": kind, "query_id": None, "stage": "identity", "reason": "Corpus identity unavailable"})
                continue
            pool, associations = {}, {}
            # A batch embeds every formulation once and searches each corpus in one operation.
            semantic = None
            semantic_many = getattr(collection, "semantic_many", None)
            if callable(semantic_many):
                try:
                    semantic = semantic_many(tuple(q["text"] for q in queries), LEG_DEPTH)
                    if len(semantic) != len(queries):
                        raise SearchUnavailable("Incomplete semantic query batch")
                except Exception:
                    semantic = None  # Independent calls retain any surviving query routes.
            for index, query in enumerate(queries):
                legs = []
                for leg in ("lexical", "semantic"):
                    try:
                        values = semantic[index] if leg == "semantic" and semantic is not None else getattr(collection, leg)(query["text"], LEG_DEPTH)
                        ranked, invalid = _ranked_positions(values)
                        if invalid:
                            raise SearchUnavailable("Ranked positions are malformed")
                        legs.append(ranked)
                        stages.append({"kind": kind, "query_id": query["query_id"], "stage": leg,
                                       "state": "evaluated", "hits": len(ranked)})
                    except Exception as exc:
                        issues.append({"kind": kind, "query_id": query["query_id"], "stage": leg,
                                       "reason": type(exc).__name__})
                for position, score in sorted(_rrf(legs).items(), key=lambda x: (-x[1], x[0]))[:PER_QUERY_POOL]:
                    pool[position] = pool.get(position, 0) + score
                    associations.setdefault(position, []).append(query["query_id"])
            positions = _ordered(pool)
            try:
                rows = collection.read(positions)
            except Exception as exc:
                issues.append({"kind": kind, "query_id": None, "stage": "read", "reason": type(exc).__name__})
                continue
            usable, pairs, rank_contexts = [], [], {}
            rank_rows, rank_associations, rank_anchors = {}, {}, {}
            # Variants broaden recall; ranking examines their common dispute once.
            # Retain every formulation and the original account, including long tails.
            inquiry = "\n".join(dict.fromkeys(
                [q["context"] for q in queries if q.get("context")]
                + [q["text"] for q in queries]))
            for position in positions:
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
                        # Keep unread ancestry explicit without discarding readable peers.
                        rank_contexts[position] = {"scope": "selected_indexed_segment", "bounded": True,
                            "unread_positions": [], "segments": [{"position": position, "row": rows[position]}]}
                        issues.append({"kind": kind, "query_id": None, "stage": "context",
                            "reason": str(exc) if isinstance(exc, SearchUnavailable) else type(exc).__name__,
                            "position": position})
                        # Score readable words even when their context is missing.
                        # The exact selected source keeps its explicit coverage gap.
                        target, row, context = position, rows[position], rank_contexts[position]
                rank_rows[target] = row
                rank_anchors[target] = _rerank_anchor(checked_source)
                rank_associations.setdefault(target, []).extend(associations[position])
                if context is not None:
                    prior = rank_contexts.get(target, {}).get("segments", [])
                    segments = {s["position"]: s for s in [*prior, *context["segments"]]}
                    rank_contexts[target] = {**context, "segments": list(segments.values())}
            # Score and return the same source unit. A sibling's relevance must not
            # be transferred from a parent window to an unrelated selected child.
            anchors = []
            for position, row in rank_rows.items():
                usable.append(position)
                pairs.append((inquiry, row["full_text"]))
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
                stages.append({"kind": kind, "query_id": None, "stage": "rerank", "state": "evaluated", "hits": len(usable)})
            except Exception as exc:
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
                if len(selected) == RESULTS_PER_KIND:
                    break
            for position, score in selected:
                try:
                    context = rank_contexts.get(position)
                    if context is None:
                        context = collection.context(position, rows[position])
                except _ContextGap as exc:
                    context = exc.context
                    issues.append({"kind": kind, "query_id": None, "stage": "context",
                                   "reason": str(exc), "position": position})
                except Exception as exc:
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
            if collection.revision() != revision:
                candidates = [c for c in candidates if c["kind"] != kind]
                issues.append({"kind": kind, "query_id": None, "stage": "identity", "reason": "Corpus changed during search"})
        state = "partial" if issues else "ready"
        return {"contract": CONTRACT, "state": state, "queries": deepcopy(queries),
                "corpus_revisions": revisions, "stages": stages, "candidates": candidates, "issues": issues}


def validate_search(record, queries):
    """Replay validates the saved exact snapshot, never reads a changed corpus."""
    if (not isinstance(record, dict) or set(record) != {"contract", "state", "queries", "corpus_revisions", "stages", "candidates", "issues"}
            or record["contract"] not in (LEGACY_CONTRACT, PARENT_TREE_CONTRACT, PREVIOUS_CONTRACT, CONTRACT) or record["queries"] != queries
            or record["state"] != ("partial" if record["issues"] else "ready")
            or set(record["corpus_revisions"]) != {"provision", "judgment"}):
        raise ValueError("Search snapshot differs from its owned query contract")
    if any(not isinstance(record[key], list) for key in ("stages", "candidates", "issues")):
        raise ValueError("Search receipts and gaps must be explicit arrays")
    query_ids = {q["query_id"] for q in queries}
    evaluated = set()
    for stage in record["stages"]:
        if (not isinstance(stage, dict) or set(stage) != {"kind", "query_id", "stage", "state", "hits"}
                or stage["kind"] not in record["corpus_revisions"] or stage["state"] != "evaluated"
                or type(stage["hits"]) is not int or stage["hits"] < 0
                or stage["stage"] not in ("lexical", "semantic", "rerank")
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
                or issue["stage"] not in ("identity", "lexical", "semantic", "read", "rerank", "context")
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
        if not any((kind, None, stage) in failed for stage in ("read", "rerank")) and (kind, None, "rerank") not in evaluated:
            raise ValueError("Reranking has no execution disposition")
    identities = set()
    for candidate in record["candidates"]:
        if record["contract"] != CONTRACT and any(type(p) is not int for p in (
                candidate["position"], *(s["position"] for s in candidate["context"]["segments"]))):
            raise ValueError("Historical search cannot contain contextual parent addresses")
        if (candidate["kind"] not in record["corpus_revisions"]
                or candidate["corpus_revision"] != record["corpus_revisions"][candidate["kind"]]
                or not set(candidate["query_ids"]) <= {q["query_id"] for q in queries}
                or not candidate["query_ids"] or candidate["id"] in identities):
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
            if (record["contract"] not in (PARENT_TREE_CONTRACT, PREVIOUS_CONTRACT, CONTRACT) or candidate["kind"] != "provision" or len(segments) < 2
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
        if record["contract"] in (PREVIOUS_CONTRACT, CONTRACT) and candidate["kind"] == "provision":
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
    return deepcopy(record)


