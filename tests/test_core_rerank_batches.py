"""The reranker reads each passage whole and scores pairs shortest first (owner decision P30,
20 Oct 2026). A question and its passage are read together up to RERANK_TOKENS tokens, so a
passage is cut only when it alone is longer; pairs are batched by length, so a short pair is
never padded to a long one, and each score comes back to its own pair. No model calls."""
import zlib

import pytest

from nm.core_engine import retrieval
from tests.test_core_rerank_window_reuse import CountingTokenizer, local

pytestmark = pytest.mark.class_a


class ByContent:
    """Scores a pair by its words alone, so a score returned to the wrong pair shows."""

    def __init__(self):
        self.tokenizer = CountingTokenizer()
        self.calls = []

    def predict(self, windows, **kwargs):
        self.calls.append((list(windows), kwargs))
        return [score(window) for window in windows]


def score(window):
    return float(zlib.crc32("\x00".join(window).encode()) % 10_000)


def windows(lengths):
    return [(f"question {n}", " ".join(["word"] * n)) for n in lengths]


def test_each_score_returns_to_its_own_pair():
    pairs = windows([900, 3, 40, 3, 7000, 250, 12, 0, 60])
    model = ByContent()
    assert retrieval._batched_scores(model, pairs) == [score(pair) for pair in pairs]
    assert sorted(pair for batch, _ in model.calls for pair in batch) == sorted(pairs)


def test_pairs_are_scored_shortest_first_within_both_bounds(monkeypatch):
    monkeypatch.setattr(retrieval, "RERANK_BATCH_PAIRS", 3)
    monkeypatch.setattr(retrieval, "RERANK_BATCH_CHARACTERS", 2000)
    model = ByContent()
    pairs = windows([5, 900, 1, 300, 2, 4, 3, 700, 6])
    retrieval._batched_scores(model, pairs)
    lengths = [[len(q) + len(p) for q, p in batch] for batch, _ in model.calls]
    flat = [length for batch in lengths for length in batch]
    assert flat == sorted(flat)
    for batch, (_, kwargs) in zip(lengths, model.calls, strict=True):
        assert len(batch) <= 3 and (sum(batch) <= 2000 or len(batch) == 1)
        assert kwargs == {"batch_size": len(batch), "show_progress_bar": False}


def test_a_pair_longer_than_a_batch_is_scored_alone(monkeypatch):
    monkeypatch.setattr(retrieval, "RERANK_BATCH_CHARACTERS", 100)
    model = ByContent()
    pairs = windows([2, 500, 3])
    assert retrieval._batched_scores(model, pairs) == [score(pair) for pair in pairs]
    assert [len(batch) for batch, _ in model.calls] == [2, 1]


def test_a_question_and_a_long_passage_are_read_in_one_window(tmp_path):
    """Before P30 a passage of 3,000 words was read in seven pieces of 512 tokens."""
    model = ByContent()
    question = " ".join(f"phrase{n}" for n in range(300))
    passage = " ".join(f"word{n}" for n in range(3000)) + " FINAL PROVISO"
    assert retrieval.RERANK_TOKENS == 8192 and retrieval.QUESTION_TOKENS == 380
    scores = local(tmp_path, model).rerank([(question, passage)], anchors=["Act\n4\nHeading\n"])
    (only, *_), = [batch for batch, _ in model.calls]
    assert len(model.calls) == 1 and len(model.calls[0][0]) == 1
    assert only == (question, "Act\n4\nHeading\n" + passage) and scores == [score(only)]
