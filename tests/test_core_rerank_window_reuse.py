"""Exact rerank preparation parity and work counts; no neural inference or corpus."""
from copy import deepcopy
import re
import threading
from types import SimpleNamespace

import pytest

from nm.core_engine import retrieval
from tests.test_current_brain_retrieval import Collection, QUERIES


pytestmark = pytest.mark.class_a


class CountingTokenizer:
    def __init__(self):
        self.calls = 0
        self.encodes = 0

    def __call__(self, text, **kwargs):
        assert kwargs == {"add_special_tokens": False, "return_offsets_mapping": True,
                          "truncation": False}
        self.calls += 1
        return {"offset_mapping": [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]}

    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        self.encodes += 1
        return list(range(len(re.findall(r"\S+", text))))

    def num_special_tokens_to_add(self, *, pair):
        assert pair is True
        return 3


class Predictor:
    def __init__(self):
        self.tokenizer = CountingTokenizer()
        self.calls = []

    def predict(self, windows, **kwargs):
        self.calls.append((deepcopy(windows), kwargs))
        # Index-dependent scores expose accidental deduplication or reordering.
        return [float(index) for index in range(len(windows))]


def reference_rerank(pairs, model):
    """Frozen pre-optimization preparation, to compare actual ordered inputs."""
    windows, groups = [], []
    for query, passage in pairs:
        start = len(windows)
        for _, _, query_window in retrieval.token_windows(query, model.tokenizer, 160):
            room = (512 - len(model.tokenizer.encode(query_window, add_special_tokens=False))
                    - model.tokenizer.num_special_tokens_to_add(pair=True))
            windows.extend((query_window, text) for _, _, text in
                           retrieval.token_windows(passage, model.tokenizer, room))
        groups.append((start, len(windows)))
    if len(windows) > retrieval.MAX_RERANK_PAIRS:
        raise retrieval.SearchUnavailable("The complete passage windows exceed the local rerank budget")
    scores = model.predict(windows, batch_size=16, show_progress_bar=False)
    return [max(float(score) for score in scores[start:end]) for start, end in groups]


def reference_anchored_rerank(pairs, anchors, model):
    """Independent ordered preparation for the explicit owned-header contract."""
    windows, groups = [], []
    for (query, body), anchor in zip(pairs, anchors, strict=True):
        start = len(windows)
        for _, _, question in retrieval.token_windows(query, model.tokenizer, 160):
            room = (512 - len(model.tokenizer.encode(question, add_special_tokens=False))
                    - model.tokenizer.num_special_tokens_to_add(pair=True)
                    - len(model.tokenizer.encode(anchor, add_special_tokens=False)) - 8)
            for _, _, part in retrieval.token_windows(body, model.tokenizer, room):
                assert len(model.tokenizer.encode(question, add_special_tokens=False)) + len(
                    model.tokenizer.encode(anchor + part, add_special_tokens=False)) + 3 <= 512
                windows.append((question, anchor + part))
        groups.append((start, len(windows)))
    scores = model.predict(windows, batch_size=16, show_progress_bar=False)
    return [max(float(score) for score in scores[start:end]) for start, end in groups]


def local(tmp_path, predictor):
    models = SimpleNamespace(_model=lambda _: predictor, lock=threading.RLock())
    return retrieval.LocalCollection(corpus_dir=tmp_path, lineage=tmp_path / "unused.json",
                                    doc_type="bare_act", models=models)


def long_pairs():
    query = "  " + "  ".join(f"query{i}" for i in range(181)) + "\nQUERY TAIL\n"
    passage = "\n" + " ".join(f"source{i}" for i in range(701)) + "\nFINAL QUALIFICATION  "
    return [(query, passage)] * 6 + [("Short question", passage),
                                    (query, passage + "Different exact ending.")]


def test_repeated_preparation_reuses_work_but_keeps_every_ordered_window_and_score(tmp_path):
    baseline, current = Predictor(), Predictor()
    pairs = long_pairs()
    original = deepcopy(pairs)
    expected = reference_rerank(pairs, baseline)
    actual = local(tmp_path, current).rerank(pairs)
    assert actual == expected and current.calls == baseline.calls
    assert pairs == original
    assert current.tokenizer.calls < baseline.tokenizer.calls / 2
    assert current.tokenizer.encodes < baseline.tokenizer.encodes / 2
    windows = current.calls[0][0]
    assert any("QUERY TAIL" in query for query, _ in windows)
    assert any("FINAL QUALIFICATION  " in text for _, text in windows)
    assert any(text.endswith("Different exact ending.") for _, text in windows)
    assert len({len(query.split()) for query, _ in windows}) > 1  # Different passage capacities.


def test_window_preparation_is_not_reused_across_invocations(tmp_path):
    model = Predictor()
    collection = local(tmp_path, model)
    pairs = long_pairs()
    first = collection.rerank(pairs)
    counts = model.tokenizer.calls, model.tokenizer.encodes
    assert collection.rerank(pairs) == first
    assert (model.tokenizer.calls, model.tokenizer.encodes) == tuple(2 * n for n in counts)
    assert model.calls[0] == model.calls[1]


@pytest.mark.parametrize("query,passage", [
    (" प्रश्न  కర్తవ్యం\n", "  पूरा कथन\nఅయితే పరిమితి.  "),
    ("", "  Source with whitespace and a final exception.\n"),
    ("Specific question", " "),
])
def test_exact_unicode_and_empty_token_windows_keep_original_parity(tmp_path, query, passage):
    baseline, current = Predictor(), Predictor()
    pairs = [(query, passage), (query, passage)]
    assert local(tmp_path, current).rerank(pairs) == reference_rerank(pairs, baseline)
    assert current.calls == baseline.calls


def test_resource_bound_counts_repeated_prediction_pairs_not_unique_cached_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "MAX_RERANK_PAIRS", 2)
    model = Predictor()
    with pytest.raises(retrieval.SearchUnavailable, match="rerank budget"):
        local(tmp_path, model).rerank([("Question", "Source text")] * 3)
    assert model.calls == []


def test_empty_pairs_do_not_load_the_model(tmp_path):
    def forbidden(_):
        raise AssertionError("An empty rerank must not load a model")
    collection = retrieval.LocalCollection(corpus_dir=tmp_path, lineage=tmp_path / "unused.json",
        doc_type="bare_act", models=SimpleNamespace(_model=forbidden))
    assert collection.rerank([]) == []


@pytest.mark.parametrize("failed_context", [None, "context"])
def test_equal_text_different_source_identities_preserve_selection_and_gaps(tmp_path, failed_context):
    baseline, current = Predictor(), Predictor()
    old = Collection("judgment", fail=failed_context)
    new = Collection("judgment", fail=failed_context)
    for collection in (old, new):
        for position in collection.rows:
            collection.rows[position]["full_text"] = "Identical source words with final condition."
        collection.rows[1]["chunk_id"] = "different-owned-chunk"
    old.rerank = lambda pairs, *, anchors: reference_anchored_rerank(pairs, anchors, baseline)
    new.rerank = local(tmp_path, current).rerank
    expected = retrieval.HybridSearcher({"judgment": old}).search(QUERIES)
    actual = retrieval.HybridSearcher({"judgment": new}).search(QUERIES)
    assert actual == expected and current.calls == baseline.calls
    assert len(actual["candidates"]) == 2
    assert len({row["id"] for row in actual["candidates"]}) == 2
    assert retrieval.validate_search(actual, QUERIES) == actual
