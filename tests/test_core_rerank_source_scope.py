"""Owned rerank scope, complete source windows and bounded failures; no model calls."""
from copy import deepcopy

import pytest

from nm.core_engine import retrieval
from tests.test_core_rerank_window_reuse import Predictor, local
from tests.test_current_brain_retrieval import Collection, QUERIES

pytestmark = pytest.mark.class_a


def checked(kind, row):
    return retrieval._candidate(kind, 0, row, "corpus", None, ["q1"], {})


def test_anchors_reuse_canonical_id_and_locator_fallbacks():
    statute = {"chunk_id": "section", "full_text": "Exact full statute.",
               "act_id": "owned-act", "section_number": "4"}
    judgment = {"chunk_id": "paragraph", "full_text": "Exact court words.",
                "case_id": "owned-case", "para_no": "11_2"}
    for kind, row, wanted in (("provision", statute, "owned-act\n4\n"),
                              ("judgment", judgment, "owned-case\n11_2\n")):
        admitted = checked(kind, row)
        before = deepcopy(admitted)
        assert retrieval._rerank_anchor(admitted) == wanted
        assert admitted == before


@pytest.mark.parametrize("heading", [None, "", {"unusable": "metadata"}, ["unusable"], 7])
def test_optional_bad_heading_cannot_fail_an_otherwise_owned_source(heading):
    collection = Collection()
    collection.rows[0]["section_title"] = heading
    received = []

    def rerank(pairs, *, anchors):
        received.extend(zip(deepcopy(pairs), deepcopy(anchors), strict=True))
        return [0.5] * len(pairs)

    collection.rerank = rerank
    result = retrieval.HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES)
    assert result["state"] == "ready"
    assert len(received) == 2 and received[0][1] == "Act\n4\n"
    original = next(c for c in result["candidates"] if c["kind"] == "provision" and c["position"] == 0)
    assert original["source"]["section_title"] == heading
    assert original["text"] == collection.rows[0]["full_text"]
    assert retrieval.validate_search(result, QUERIES) == result


@pytest.mark.parametrize("damage", ["required_identity", "blank_body"])
def test_one_unowned_or_empty_source_does_not_discard_readable_peers(damage):
    collection = Collection()
    if damage == "required_identity":
        collection.rows[0].update(act_name=None, act_id=None)
    else:
        collection.rows[0]["full_text"] = " \n "
    result = retrieval.HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES)
    assert result["state"] == "partial"
    assert {c["position"] for c in result["candidates"] if c["kind"] == "provision"} == {1}
    assert any(c["kind"] == "judgment" for c in result["candidates"])
    assert any(i["kind"] == "provision" and i["stage"] == "read" and i["position"] == 0
               for i in result["issues"])
    assert retrieval.validate_search(result, QUERIES) == result


def test_every_window_keeps_its_identity_and_all_original_words(tmp_path):
    model = Predictor()
    body = "\n  " + " ".join(f"source_{i}" for i in range(803)) + "\nదాచని చివరి షరతు  "
    anchor = "Exact Document Name\n4\nExact Section Heading\n"
    query = " ".join(f"question_{i}" for i in range(181)) + " FINAL QUESTION"
    original = [(query, body)]
    unchanged = deepcopy(original)
    scores = local(tmp_path, model).rerank(original, anchors=[anchor])
    windows = model.calls[0][0]
    assert original == unchanged
    assert scores == [float(len(windows) - 1)]
    assert any("FINAL QUESTION" in q for q, _ in windows)
    for q, passage in windows:
        assert passage.startswith(anchor)
        assert passage[len(anchor):] in body
        assert len(model.tokenizer.encode(q, add_special_tokens=False)) + len(
            model.tokenizer.encode(passage, add_special_tokens=False)) + 3 <= 512
    first_query = windows[0][0]
    parts = [p[len(anchor):] for q, p in windows if q == first_query]
    assert parts[0].startswith("\n  ") and parts[-1].endswith("చివరి షరతు  ")
    covered = set()
    for part in parts:
        start = body.index(part)
        covered.update(range(start, start + len(part)))
    assert covered == set(range(len(body)))


def test_equal_bodies_with_distinct_owners_do_not_share_the_wrong_header(tmp_path):
    model = Predictor()
    body = "same exact words " * 250
    anchors = ["Owner A\n1\n", "Owner B\n2\n", "Owner A\n1\n"]
    results = local(tmp_path, model).rerank([("query", body)] * 3, anchors=anchors)
    windows = model.calls[0][0]
    counts = [len(retrieval._anchored_windows(body, model.tokenizer, 508, anchor)) for anchor in anchors]
    start = 0
    for anchor, count, result in zip(anchors, counts, results, strict=True):
        assert all(p.startswith(anchor) for _, p in windows[start:start + count])
        assert result == float(start + count - 1)
        start += count
    assert start == len(windows)


@pytest.mark.parametrize("pairs,anchors", [([("q", "p")], []), ([('q', 'p')], [None]), ([], ["orphan"])])
def test_anchor_association_mismatch_never_reaches_prediction(tmp_path, pairs, anchors):
    model = Predictor()
    with pytest.raises(retrieval.SearchUnavailable, match="anchors"):
        local(tmp_path, model).rerank(pairs, anchors=anchors)
    assert model.calls == []


def test_oversized_identity_never_silently_truncates_body_or_escapes_search(tmp_path):
    model = Predictor()
    collection = Collection()
    collection.rows[0]["act_name"] = "Document " * 490
    collection.rerank = local(tmp_path, model).rerank
    result = retrieval.HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES)
    assert result["state"] == "partial" and model.calls == []
    assert len([c for c in result["candidates"] if c["kind"] == "provision"]) == 2
    assert all(c["score"] is None for c in result["candidates"] if c["kind"] == "provision")
    assert any(c["kind"] == "judgment" and c["score"] is not None for c in result["candidates"])
    assert any(i["kind"] == "provision" and i["stage"] == "rerank" for i in result["issues"])
    assert retrieval.validate_search(result, QUERIES) == result


def previous_anchored_windows(text, tokenizer, capacity, anchor):
    """Frozen pre-repair preparation, for parity wherever the complete anchor fitted."""
    room = capacity - len(tokenizer.encode(anchor, add_special_tokens=False)) - 8
    while True:
        pieces = [anchor + part for _, _, part in retrieval.token_windows(text, tokenizer, room)]
        overflow = max(0, max(len(tokenizer.encode(p, add_special_tokens=False)) - capacity
                              for p in pieces))
        if not overflow:
            return pieces
        room -= overflow


@pytest.mark.parametrize("anchor", ["Owner\n", "Exact Document Name\n4\nExact Section Heading\n",
                                    "Act\n4\nHeading with\n\nblank line\n", "Act\n4\nHeading\n\n"])
@pytest.mark.parametrize("capacity", [348, 383, 508])
def test_anchors_that_fit_keep_exactly_their_previous_windows(anchor, capacity):
    tokenizer = Predictor().tokenizer
    body = "\n  " + " ".join(f"word_{i}" for i in range(900)) + " last words  "
    assert (retrieval._anchored_windows(body, tokenizer, capacity, anchor)
            == previous_anchored_windows(body, tokenizer, capacity, anchor))


def test_a_whole_provision_in_the_heading_keeps_identity_and_every_body_word():
    """Measured 10 Oct 2026: a 1,570-character heading left no room and unranked every peer."""
    tokenizer = Predictor().tokenizer
    heading = "Short first heading line\n" + " ".join(f"heading_{i}" for i in range(400))
    anchor = f"Exact Document Name\n18\n{heading}\n"
    kept = "Exact Document Name\n18\nShort first heading line\n"
    body = "\n  " + " ".join(f"source_{i}" for i in range(803)) + "\nచివరి షరతు  "
    with pytest.raises(retrieval.SearchUnavailable, match="no room"):
        previous_anchored_windows(body, tokenizer, 383, anchor)
    windows = retrieval._anchored_windows(body, tokenizer, 383, anchor)
    covered = set()
    for window in windows:
        assert window.startswith(kept) and "heading_0" not in window
        assert len(tokenizer.encode(window, add_special_tokens=False)) <= 383
        start = body.index(window[len(kept):])
        covered.update(range(start, start + len(window) - len(kept)))
    assert covered == set(range(len(body)))


def test_one_overlong_heading_no_longer_unranks_its_peers(tmp_path):
    model = Predictor()
    collection = Collection()
    collection.rows[0]["section_title"] = " ".join(f"heading_{i}" for i in range(600))
    collection.rerank = local(tmp_path, model).rerank
    result = retrieval.HybridSearcher({"provision": collection, "judgment": Collection("judgment")}).search(QUERIES)
    assert result["state"] == "ready" and len(model.calls) == 1
    provisions = [c for c in result["candidates"] if c["kind"] == "provision"]
    assert len(provisions) == 2 and all(c["score"] is not None for c in provisions)
    long_windows = [p for _, p in model.calls[0][0] if p.startswith("Act\n4\n")]
    assert long_windows and not any("heading_0" in p for p in long_windows)
    original = next(c for c in provisions if c["position"] == 0)
    assert original["source"]["section_title"] == collection.rows[0]["section_title"]
    assert retrieval.validate_search(result, QUERIES) == result


def test_anchored_prediction_bound_still_counts_every_repeated_source(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "MAX_RERANK_PAIRS", 2)
    model = Predictor()
    with pytest.raises(retrieval.SearchUnavailable, match="rerank budget"):
        local(tmp_path, model).rerank([("query", "body")] * 3, anchors=["Owner\n"] * 3)
    assert model.calls == []
