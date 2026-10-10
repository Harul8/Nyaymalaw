"""One authorised local per-enquiry diagnostic, preserving earlier evidence.

No new retrieval, provider calls, downloads, prompt edits or production changes.
The three original enquiries remain verbatim, including their known premise defect.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
OUT = Path(__file__).resolve().parent
INPUT = OUT / "retrieval-context-comparison.json"
OLD_MANIFEST = OUT / "rerank-local-manifest.json"
OLD_RESULT = OUT / "rerank-local-results.json"
LABELS = OUT / "rerank-local-independent-labels.json"
MANIFEST = OUT / "rerank-per-enquiry-manifest.json"
RESULT = OUT / "rerank-per-enquiry-results.json"
ASSESSMENT = OUT / "rerank-per-enquiry-assessment.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def prepare():
    from nm.core_engine import retrieval
    from transformers import AutoTokenizer
    assert not any(p.exists() for p in (MANIFEST, RESULT, ASSESSMENT)), "Preserve prior experiment"
    old, baseline, original = read(OLD_MANIFEST), read(OLD_RESULT), read(INPUT)
    assert baseline["state"] == "completed"
    assert baseline["labels_sha256"] == baseline["labels_sha256_after"] == sha(LABELS)
    assert old["input_sha256"] == sha(INPUT)
    assert old["retrieval_sha256"] == sha(ROOT / "nm/core_engine/retrieval.py")
    for name, entry in old["model_files"].items():
        path = Path(old["model_directory"]) / name
        assert path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"]
    latest = original["original_context"]["latest"]
    catalogue = {r["source_id"]: r for r in [*original["original_context"]["conversation"], latest]}
    work = original["original_work"]
    for source in work["sources"]:
        assert source["record_role"] == "original_account"
        assert catalogue[source["source_id"]]["text"][source["start"]:source["end"]] == source["text"]
    account = "\n\n".join(f"{row['speaker']}:\n{row['text']}" for row in work["sources"])
    tokenizer = AutoTokenizer.from_pretrained(old["model_directory"], local_files_only=True)
    queries = []
    for enquiry in work["enquiries"]:
        query = account + "\n\n" + enquiry["text"]
        windows = [{"start": a, "end": b, "text": text,
                    "tokens": len(tokenizer.encode(text, add_special_tokens=False))}
                   for a, b, text in retrieval.token_windows(query, tokenizer, 160)]
        counts = {}
        for kind, pool in original["reranked_pool"].items():
            count = 0
            for row in pool:
                for window in windows:
                    room = 512 - window["tokens"] - tokenizer.num_special_tokens_to_add(pair=True)
                    count += len(retrieval.token_windows(row["passage"], tokenizer, room))
            assert count <= retrieval.MAX_RERANK_PAIRS
            counts[kind] = count
        queries.append({"query_id": enquiry["query_id"], "original_enquiry": enquiry["text"],
                        "ranking_input": query, "query_windows": windows, "prepared_pairs": counts})
    assert len(queries) == 3 and all(len(q["query_windows"]) == 1 for q in queries)
    write(MANIFEST, {"state": "prepared_without_neural_inference", "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": sha(INPUT), "baseline_manifest_sha256": sha(OLD_MANIFEST),
        "baseline_result_sha256": sha(OLD_RESULT), "labels_sha256": sha(LABELS),
        "script_sha256": sha(Path(__file__)), "retrieval_sha256": old["retrieval_sha256"],
        "model": old["model"], "model_directory": old["model_directory"], "model_files": old["model_files"],
        "source_pool_manifest": old["source_pool_manifest"], "queries": queries,
        "maximum_seconds": 600, "maximum_local_predict_calls": 6, "provider_calls": 0,
        "deduplication": "Owned source identity is corpus revision + kind + position. Identical wording at different positions remains distinct. Repeated identical input rows for one position must have agreeing scores before ranking.",
        "round_robin": "Within each corpus, take the next unseen source from enquiry1,2,3 in supplied order, repeating until six unique source identities. Skip already selected identities within the active enquiry. No score threshold, relevance label, manual promotion or document-diversity rule participates.",
        "limitations": ["Older seen matter and14 prelabelled targeted sources, not a corpus-wide or unfamiliar accuracy estimate.",
            "Queries remain unchanged, including the unsupported not-supplied to nonexistence premise; discovery output is not authority.",
            "Same frozen pool for every query. Neither recall route nor actual product final selection is measured.",
            "Combined-input baseline was measured in an earlier process against identical hashed weights; latency comparison is not a counterbalanced performance trial."]})
    print(json.dumps({"manifest": str(MANIFEST), "provider_calls": 0, "neural_calls": 0,
        "queries": [{"id": q["query_id"], "tokens": q["query_windows"][0]["tokens"], "pairs": q["prepared_pairs"]} for q in queries],
        "total_prepared_pairs": sum(sum(q["prepared_pairs"].values()) for q in queries)}))


def check(manifest):
    for path, field in ((INPUT, "input_sha256"), (OLD_MANIFEST, "baseline_manifest_sha256"),
                        (OLD_RESULT, "baseline_result_sha256"), (LABELS, "labels_sha256"),
                        (Path(__file__), "script_sha256")):
        assert sha(path) == manifest[field]
    assert sha(ROOT / "nm/core_engine/retrieval.py") == manifest["retrieval_sha256"]
    for name, entry in manifest["model_files"].items():
        path = Path(manifest["model_directory"]) / name
        assert path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"]


def worker():
    from nm.core_engine import retrieval
    manifest, result, original = read(MANIFEST), read(RESULT), read(INPUT)
    assert result["state"] == "running"
    check(manifest)
    models = retrieval._Models(ROOT / ".nm/models")
    start = time.perf_counter()
    model = models._model("reranking")
    result.update(model_load_seconds=time.perf_counter() - start, device=str(model.device),
                  dtype=str(next(model.model.parameters()).dtype), state="running_local_inference")
    write(RESULT, result)
    original_predict, dispatches = model.predict, 0

    def predict(pairs, **kwargs):
        nonlocal dispatches
        assert dispatches < 6
        dispatches += 1
        return original_predict(pairs, **kwargs)

    model.predict = predict
    try:
        for query in manifest["queries"]:
            for kind in ("provision", "judgment"):
                collection = retrieval.LocalCollection(corpus_dir=Path("unused"), lineage=Path("unused"),
                    doc_type="bare_act" if kind == "provision" else "case_law", models=models)
                rows = original["reranked_pool"][kind]
                start = time.perf_counter()
                scores = collection.rerank([(query["ranking_input"], r["passage"]) for r in rows])
                result["runs"].append({"query_id": query["query_id"], "kind": kind,
                    "elapsed_seconds": time.perf_counter() - start,
                    "prepared_pair_count": query["prepared_pairs"][kind],
                    "scores": [{"positions": r["positions"], "passage_sha256": r["passage_sha256"], "score": float(s)}
                               for r, s in zip(rows, scores)]})
                result["local_predict_calls"] = dispatches
                write(RESULT, result)
        assert dispatches == 6
        result["state"] = "completed"
    finally:
        model.predict = original_predict
        result.update(finished_utc=datetime.now(timezone.utc).isoformat(),
            labels_sha256_after=sha(LABELS), retrieval_sha256_after=sha(ROOT / "nm/core_engine/retrieval.py"))
        assert result["labels_sha256_after"] == manifest["labels_sha256"]
        assert result["retrieval_sha256_after"] == manifest["retrieval_sha256"]
        write(RESULT, result)


def run():
    assert not RESULT.exists(), "Never repeat or overwrite the bounded run"
    manifest = read(MANIFEST)
    check(manifest)
    write(RESULT, {"state": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha(MANIFEST), "labels_sha256": sha(LABELS), "runs": [],
        "provider_calls": 0, "maximum_seconds": 600, "local_predict_calls": 0})
    try:
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker"], cwd=ROOT,
                               timeout=600, check=False)
        if child.returncode:
            result = read(RESULT)
            result.update(state="stopped_worker_failure", returncode=child.returncode)
            write(RESULT, result)
    except subprocess.TimeoutExpired:
        result = read(RESULT)
        result.update(state="stopped_at_600_seconds", partial_measurement=True)
        write(RESULT, result)
    print(json.dumps({"state": read(RESULT)["state"], "output": str(RESULT)}))


def assess():
    assert not ASSESSMENT.exists(), "Preserve previous assessment"
    manifest, result, old, labels = read(MANIFEST), read(RESULT), read(OLD_MANIFEST), read(LABELS)
    check(manifest)
    assert result["state"] == "completed" and result["local_predict_calls"] == 6
    assert result["labels_sha256_after"] == manifest["labels_sha256"]
    original, baseline = read(INPUT), read(OLD_RESULT)

    def ranked(run):
        # A saved pool entry may represent multiple identical-text positions.
        # Expand real positions while refusing conflicting content or scores.
        rows = {}
        for row in run["scores"]:
            for position in row["positions"]:
                value = {"position": position, "passage_sha256": row["passage_sha256"], "score": row["score"]}
                if position in rows:
                    assert rows[position] == value, "Repeated identity has conflicting input or score"
                rows[position] = value
        ordered = sorted(rows.values(), key=lambda row: (-row["score"], row["position"]))
        return [{**row, "rank": i + 1} for i, row in enumerate(ordered)]

    ranks = {(r["query_id"], r["kind"]): ranked(r) for r in result["runs"]}
    combined = {r["kind"]: ranked(r) for r in baseline["runs"] if r["arm"] == "exact_selected_account_plus_same_concepts_once"}
    ids = [q["query_id"] for q in manifest["queries"]]
    outputs = {}
    for kind in ("provision", "judgment"):
        cursors, seen, chosen = {identity: 0 for identity in ids}, set(), []
        while len(chosen) < 6:
            progressed = False
            for identity in ids:
                ordered = ranks[(identity, kind)]
                while cursors[identity] < len(ordered) and ordered[cursors[identity]]["position"] in seen:
                    cursors[identity] += 1
                if cursors[identity] < len(ordered):
                    row = ordered[cursors[identity]]
                    cursors[identity] += 1
                    seen.add(row["position"])
                    chosen.append({**row, "selected_by_query": identity})
                    progressed = True
                if len(chosen) == 6:
                    break
            if not progressed:
                break
        outputs[kind] = {"round_robin_top6": chosen, "combined_focused_top6": combined[kind][:6],
                         "each_query_top6": {identity: ranks[(identity, kind)][:6] for identity in ids}}
    movements = []
    for label in labels["assessments"]:
        identity = old["label_mapping"][label["id"]]
        positions, kind = set(identity["positions"]), identity["kind"]
        movements.append({**label, **identity,
            "combined_focused": [r for r in combined[kind] if r["position"] in positions],
            "each_query": {q: [r for r in ranks[(q, kind)] if r["position"] in positions] for q in ids},
            "round_robin_selected": [r for r in outputs[kind]["round_robin_top6"] if r["position"] in positions]})
    write(ASSESSMENT, {"scope": "Per-enquiry local candidate-ranking diagnostic only; not product final selection",
        "manifest_sha256": sha(MANIFEST), "results_sha256": sha(RESULT), "labels_sha256": sha(LABELS),
        "model_load_seconds": result["model_load_seconds"], "device": result["device"], "dtype": result["dtype"],
        "timings": [{k: r[k] for k in ("query_id", "kind", "elapsed_seconds", "prepared_pair_count")} for r in result["runs"]],
        "ranked_source_identity": "Frozen corpus revision + corpus kind + store position; equal text at different positions stays distinct",
        "round_robin_method": manifest["round_robin"], "top6_comparisons": outputs,
        "fourteen_prelabelled_source_movements": movements, "limitations": manifest["limitations"] + [
            "Only14 targeted labels; new unlabelled candidates remain unassessed, so no precision, recall or accuracy fraction is inferred.",
            "The two equipment-source leads share the same decisive saved neighbour; their higher ranks do not establish two independent authorities.",
            "Labels include source purpose and neighbour-only relevance; ranks score the primary passage and do not verify court treatment or applicability."]})
    print(json.dumps({"assessment": str(ASSESSMENT), "provider_calls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--run-authorized-local-once", action="store_true")
    mode.add_argument("--assess-only", action="store_true")
    mode.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.prepare_only:
        prepare()
    elif args.run_authorized_local_once:
        run()
    elif args.assess_only:
        assess()
    else:
        worker()
