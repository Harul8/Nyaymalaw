"""Prepare-only reranker presentation diagnostic on a frozen older-matter pool.

Loads local tokenizer files, but never a neural model, network client or corpus.
Calls the current rerank implementation with a fake predictor. Zero scores have
no relevance meaning. Exact source passages remain in the earlier evidence file.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from nm.core_engine import retrieval

OUT = Path(__file__).resolve().parent
INPUT = OUT / "retrieval-context-comparison.json"
RESULT = OUT / "rerank-presentation-prepare-only.json"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def digest(value):
    return sha(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def inquiry(queries):
    # Matches HybridSearcher.search's current common-inquiry assembly.
    return "\n".join(dict.fromkeys(
        [q["context"] for q in queries if q.get("context")]
        + [q["text"] for q in queries]))


def occurrences(text, fragment):
    found, offset = [], 0
    while (start := text.find(fragment, offset)) >= 0:
        found.append((start, start + len(fragment)))
        offset = start + 1
    return found


def windows_for(text, tokenizer):
    return [{"start": start, "end": end, "text": part,
             "tokens": len(tokenizer.encode(part, add_special_tokens=False))}
            for start, end, part in retrieval.token_windows(text, tokenizer, 160)]


class FakePredictor:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.calls = []

    def predict(self, pairs, **kwargs):
        self.calls.append({"pair_count": len(pairs), "ordered_pairs_sha256": digest(pairs),
                           "kwargs": kwargs})
        return [0.0] * len(pairs)


class FakeModels:
    def __init__(self, predictor):
        self.predictor = predictor
        self.lock = threading.RLock()

    def _model(self, which):
        assert which == "reranking"
        return self.predictor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true", required=True)
    parser.parse_args()
    assert not RESULT.exists(), "Preserve prior diagnostic evidence; use a new reviewed destination"
    input_bytes = INPUT.read_bytes()
    data = json.loads(input_bytes)
    source_path = ROOT / "nm/core_engine/retrieval.py"
    source_hash = sha(source_path.read_bytes())
    work = data["original_work"]
    queries = data["baseline_result"]["queries"]
    concepts = [e["text"] for e in work["enquiries"]]
    assert [q["text"] for q in queries] == concepts
    assert [q["text"] for q in data["candidate_queries"]] == concepts
    assert len(concepts) == len(set(concepts))
    catalogue = {r["source_id"]: r for r in [*data["original_context"]["conversation"],
                                              data["original_context"]["latest"]]}
    selected, whole = [], []
    for source in work["sources"]:
        original = catalogue[source["source_id"]]
        assert original["record_role"] == source["record_role"] == "original_account"
        assert all(original[k] == source[k] for k in ("speaker", "turn_id"))
        assert original["text"][source["start"]:source["end"]] == source["text"]
        selected.append(source)
        if original not in whole:
            whole.append(original)

    def account_text(rows):
        return "\n\n".join(f"{r['speaker']}:\n{r['text']}" for r in rows)

    arms = {
        "recorded_production_metadata": inquiry(queries),
        "whole_original_messages_plus_same_concepts_once": account_text(whole) + "\n\n" + "\n".join(concepts),
        "exact_selected_account_plus_same_concepts_once": account_text(selected) + "\n\n" + "\n".join(concepts),
    }
    # Fixture annotations identify exact original qualifications, not relevance labels.
    original = data["original_context"]["latest"]
    annotations = {
        "subject_relationship": "They leased a laser cutter",
        "damage_disputed": "our client disputes causing it",
        "document_supply_status": "no joint inspection report has been supplied",
    }
    for text in annotations.values():
        assert text in original["text"] and text in selected[0]["text"]

    from transformers import AutoTokenizer
    tokenizer_path = ROOT / ".nm/models" / retrieval.RERANK_MODEL.replace("/", "__")
    assert tokenizer_path.is_dir(), "Existing local tokenizer files required; do not download"
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True)
    result = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Offline preparation using the complete frozen candidate pool of the older Vale Makers deposit investigation; not the new lean pilot or a new retrieval run",
        "input_file": INPUT.name, "input_sha256": sha(input_bytes),
        "source_sha256_before": source_hash,
        "historical_source_sha256": data["retrieval_source_sha256_start"],
        "corpus_revisions": data["baseline_result"]["corpus_revisions"],
        "tokenizer": retrieval.RERANK_MODEL,
        "tokenizer_files_sha256": {p.name: sha(p.read_bytes()) for p in tokenizer_path.iterdir()
            if p.is_file() and ("tokenizer" in p.name or p.name in {"sentencepiece.bpe.model", "special_tokens_map.json", "config.json"})},
        "neural_inference_calls": 0, "provider_calls": 0, "corpus_reads": 0,
        "source_pool_manifest": {}, "arms": {},
        "exact_original_annotations": {k: {"source_id": original["source_id"], "text": v,
            "ranges": occurrences(original["text"], v)} for k, v in annotations.items()},
        "limitations": [
            "Recorded production inquiry is reconstructed from its exact saved query objects using the current unchanged assembly rule; its original token windows were not saved.",
            "The pool was captured by the older compact-context comparison. It is reused identically here; this run does not claim that production and every proposed recall route originally produced that same pool.",
            "Fake zero scores provide no relevance or accuracy evidence, and tokenizer-only timing would not predict neural latency.",
            "Concepts are preserved unchanged, including the existing change from 'not supplied' in the account to 'no report exists' in one concept. This diagnostic does not repair that semantic defect.",
            "Whole-message presentation includes the separate drive dispute and advocate instructions; selected-account presentation tests the narrower exact saved deposit passage.",
            "Removing duplicated metadata changes presentation; factual qualifiers from the original account and every existing concept remain exact. Omitted model outcome/constraints/unresolved prose is not silently replaced.",
        ],
    }
    for kind, pool in data["reranked_pool"].items():
        assert all(sha(row["passage"].encode("utf-8")) == row["passage_sha256"] for row in pool)
        result["source_pool_manifest"][kind] = {
            "count": len(pool), "ordered_manifest_sha256": digest([
                {"positions": r["positions"], "passage_sha256": r["passage_sha256"]} for r in pool]),
            "passage_characters": sum(len(r["passage"]) for r in pool),
        }
    for name, query in arms.items():
        windows = windows_for(query, tokenizer)
        for window in windows:
            window["complete_concepts"] = [i + 1 for i, c in enumerate(concepts) if c in window["text"]]
            window["complete_original_qualifications"] = [k for k, v in annotations.items() if v in window["text"]]
            window["complete_selected_account"] = all(s["text"] in window["text"] for s in selected)
        arm = {"inquiry": query, "inquiry_sha256": sha(query.encode("utf-8")),
               "characters": len(query), "tokens": len(tokenizer.encode(query, add_special_tokens=False)),
               "query_windows": windows, "corpora": {},
               "concept_qualification_joint_windows": {
                   str(i + 1): {key: [j for j, w in enumerate(windows)
                       if concept in w["text"] and text in w["text"]]
                       for key, text in annotations.items()}
                   for i, concept in enumerate(concepts)},
               "concept_occurrence_counts": [len(occurrences(query, c)) for c in concepts]}
        assert all(c in query for c in concepts)
        if name != "recorded_production_metadata":
            assert arm["concept_occurrence_counts"] == [1] * len(concepts)
        for kind, pool in data["reranked_pool"].items():
            pairs = [(query, row["passage"]) for row in pool]
            expected = []
            per_source = []
            for _, passage in pairs:
                start = len(expected)
                for window in windows:
                    room = 512 - window["tokens"] - tokenizer.num_special_tokens_to_add(pair=True)
                    expected.extend((window["text"], text) for _, _, text in
                                    retrieval.token_windows(passage, tokenizer, room))
                per_source.append(len(expected) - start)
            fake = FakePredictor(tokenizer)
            collection = retrieval.LocalCollection(corpus_dir=Path("unused"), lineage=Path("unused"),
                doc_type="bare_act" if kind == "provision" else "case_law", models=FakeModels(fake))
            observed = {"source_count": len(pool), "prepared_pair_count": len(expected),
                "per_source_pair_counts": per_source, "ordered_pairs_sha256": digest(expected),
                "maximum_pair_count": retrieval.MAX_RERANK_PAIRS}
            try:
                scores = collection.rerank(pairs)
                assert len(scores) == len(pool) and all(s == 0.0 for s in scores)
                assert len(fake.calls) == 1 and fake.calls[0]["ordered_pairs_sha256"] == digest(expected)
                observed.update(state="prepared_with_fake_predictor", fake_predictor=fake.calls[0])
            except retrieval.SearchUnavailable as exc:
                assert len(expected) > retrieval.MAX_RERANK_PAIRS and not fake.calls
                observed.update(state="production_capacity_guard_refused", reason=str(exc))
            arm["corpora"][kind] = observed
        result["arms"][name] = arm
    result.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                  source_sha256_after=sha(source_path.read_bytes()))
    assert result["source_sha256_after"] == source_hash
    assert INPUT.read_bytes() == input_bytes
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(RESULT), "provider_calls": 0, "neural_inference_calls": 0,
        "arms": {k: {"tokens": v["tokens"], "query_windows": len(v["query_windows"]),
                     "pairs": {c: x["prepared_pair_count"] for c, x in v["corpora"].items()}}
                 for k, v in result["arms"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
