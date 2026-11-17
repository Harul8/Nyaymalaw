"""A search stage that fails leaves its cause in the server log, never only in a type name.

On 10 October 2026 a reranking attempt failed and its exact replay succeeded; the saved
record held only the exception type, so the cause could not be recovered. The rule: every
search stage that fails logs why, and no advocate words reach the log. From plan AN.52 (52b,
D208; 17 Nov 2026) a stage that finds or orders the held law and fails ends the search - it
no longer goes on without it - so those failures are read here from what the search raised; a
passage that cannot be read, or its neighbours, is still that passage's gap in a search that stays.
"""
from __future__ import annotations

import logging

import pytest

from nm.core_engine.retrieval import HybridSearcher, SearchUnavailable, StageUnavailable, validate_search
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


#: The stages that find or order the held law: a failure of one ends the search (52b).
ENDS_THE_SEARCH = ("lexical", "rerank")


def _search(stage, error):
    """The record, or for a stage that ends the search what it raised."""
    collections = {"provision": Failing(stage, error), "judgment": Collection("judgment")}
    try:
        return HybridSearcher(collections).search(QUERIES)
    except StageUnavailable as stopped:
        assert stage in ENDS_THE_SEARCH and (stopped.kind, stopped.stage) == ("provision", stage)
        return stopped


def _stands(stage, outcome):
    if stage in ENDS_THE_SEARCH:
        assert isinstance(outcome, StageUnavailable)
    else:
        assert validate_search(outcome, QUERIES) == outcome


@pytest.mark.parametrize("stage", ["lexical", "read", "rerank", "context"])
def test_an_expected_stage_failure_is_logged_with_its_cause(stage, caplog):
    cause = f"provision {stage} failed: CUDA out of memory"
    with caplog.at_level(logging.WARNING, logger="nm.core_engine.retrieval"):
        record = _search(stage, SearchUnavailable(cause))
    logged = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(stage in message and "CUDA out of memory" in message for message in logged), logged
    _stands(stage, record)


@pytest.mark.parametrize("stage", ["lexical", "read", "rerank", "context"])
def test_an_unexpected_failure_is_an_error_with_its_traceback_and_without_advocate_words(stage, caplog):
    with caplog.at_level(logging.WARNING, logger="nm.core_engine.retrieval"):
        record = _search(stage, TypeError(ADVOCATE_WORDS))
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and all("TypeError" in m for m in errors)
    assert any("_maybe" in m for m in errors), "the traceback frames locate the failure"
    assert not any(ADVOCATE_WORDS in r.getMessage() for r in caplog.records)
    assert ADVOCATE_WORDS not in str(record) if isinstance(record, StageUnavailable) else True
    _stands(stage, record)


def test_a_failed_ranking_returns_nothing_and_what_is_kept_of_it_is_the_failures_name(caplog):
    """What the research step keeps for the question is code's sentence and the failure's own name - never the provider's or the
    device's words, which stay in the log. Until 52b a failed ranking still returned its candidates, unranked."""
    stopped = _search("rerank", SearchUnavailable("provision reranking failed: CUDA out of memory"))
    assert isinstance(stopped, StageUnavailable) and stopped.cause == "SearchUnavailable"
    assert "CUDA" not in str(stopped) and "the ranking of what was found could not be used" in str(stopped)


def test_a_failed_batch_embedding_is_logged_and_falls_back_per_query(caplog):
    class BatchFails(Collection):
        def semantic_many(self, queries, depth):
            raise SearchUnavailable("provision semantic batch failed: device lost")

    with caplog.at_level(logging.WARNING, logger="nm.core_engine.retrieval"):
        record = HybridSearcher({"provision": BatchFails(), "judgment": Collection("judgment")}).search(QUERIES)
    assert any("semantic batch" in r.getMessage() and "device lost" in r.getMessage() for r in caplog.records)
    assert record["state"] == "ready", "the per-query fallback recovered every semantic leg"
