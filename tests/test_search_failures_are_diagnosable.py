"""A degraded search stage leaves its cause in the server log, never only in a type name.

On 10 October 2026 a reranking attempt failed and its exact replay succeeded; the saved
record held only the exception type, so the cause could not be recovered. The rule: every
search stage that degrades logs why, while the saved record (and so replay and the model
inputs built from it) stays exactly as before, and no advocate words reach the log.
"""
from __future__ import annotations

import logging

import pytest

from nm.core_engine.retrieval import HybridSearcher, SearchUnavailable, validate_search
from tests.test_current_brain_retrieval import QUERIES, Collection

ADVOCATE_WORDS = "my client's landlord changed the locks on 3 March"


class Failing(Collection):
    """A collection whose one stage raises a chosen exception."""

    def __init__(self, stage, error, **kwargs):
        super().__init__(**kwargs)
        self.stage, self.error = stage, error

    def _maybe(self, stage):
        if self.stage == stage:
            raise self.error

    def lexical(self, query, depth):
        self._maybe("lexical")
        return super().lexical(query, depth)

    def read(self, positions):
        self._maybe("read")
        return super().read(positions)

    def rerank(self, pairs, *, anchors=None):
        self._maybe("rerank")
        return super().rerank(pairs, anchors=anchors)

    def context(self, position, source):
        self._maybe("context")
        return super().context(position, source)


def _search(stage, error):
    collections = {"provision": Failing(stage, error), "judgment": Collection("judgment")}
    return HybridSearcher(collections).search(QUERIES)


@pytest.mark.parametrize("stage", ["lexical", "read", "rerank", "context"])
def test_an_expected_stage_failure_is_logged_with_its_cause(stage, caplog):
    cause = f"provision {stage} failed: CUDA out of memory"
    with caplog.at_level(logging.WARNING, logger="nm.core_engine.retrieval"):
        record = _search(stage, SearchUnavailable(cause))
    logged = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(stage in message and "CUDA out of memory" in message for message in logged), logged
    assert validate_search(record, QUERIES) == record


@pytest.mark.parametrize("stage", ["lexical", "read", "rerank", "context"])
def test_an_unexpected_failure_is_an_error_with_its_traceback_and_without_advocate_words(stage, caplog):
    with caplog.at_level(logging.WARNING, logger="nm.core_engine.retrieval"):
        record = _search(stage, TypeError(ADVOCATE_WORDS))
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and all("TypeError" in m for m in errors)
    assert any("_maybe" in m for m in errors), "the traceback frames locate the failure"
    assert not any(ADVOCATE_WORDS in r.getMessage() for r in caplog.records)
    assert validate_search(record, QUERIES) == record


def test_the_saved_record_is_unchanged_by_logging(caplog):
    """The issue reason stays the exception type, so replay and model inputs do not move."""
    record = _search("rerank", SearchUnavailable("provision reranking failed: CUDA out of memory"))
    rerank = [i for i in record["issues"] if i["stage"] == "rerank"]
    assert rerank == [{"kind": "provision", "query_id": None, "stage": "rerank", "reason": "SearchUnavailable"}]
    assert any(c["kind"] == "provision" for c in record["candidates"]), "a failed rerank still returns candidates"


def test_a_failed_batch_embedding_is_logged_and_falls_back_per_query(caplog):
    class BatchFails(Collection):
        def semantic_many(self, queries, depth):
            raise SearchUnavailable("provision semantic batch failed: device lost")

    with caplog.at_level(logging.WARNING, logger="nm.core_engine.retrieval"):
        record = HybridSearcher({"provision": BatchFails(), "judgment": Collection("judgment")}).search(QUERIES)
    assert any("semantic batch" in r.getMessage() and "device lost" in r.getMessage() for r in caplog.records)
    assert record["state"] == "ready", "the per-query fallback recovered every semantic leg"
