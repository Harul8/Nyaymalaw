"""Frozen older-matter reranking diagnostic. Preparation performs no inference.

The separately authorised run makes six local predict calls (three presentations
times two corpora) using one cached local model. A parent process enforces a
600-second ceiling, including loading, with no retries or downloads.
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
PREPARATION = OUT / "rerank-presentation-prepare-only.json"
MANIFEST = OUT / "rerank-local-manifest.json"
PACKET = OUT / "rerank-local-blinded-packet.json"
LABELS = OUT / "rerank-local-independent-labels.json"
RESULT = OUT / "rerank-local-results.json"
MAX_SECONDS = 600


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare():
    assert not MANIFEST.exists() and not PACKET.exists(), "Preserve existing preparation"
    from nm.core_engine import retrieval
    data, prepared = read(INPUT), read(PREPARATION)
    assert sha(INPUT) == prepared["input_sha256"]
    assert sha(ROOT / "nm/core_engine/retrieval.py") == prepared["source_sha256_after"]
    model_dir = ROOT / ".nm/models" / retrieval.RERANK_MODEL.replace("/", "__")
    expected = {"config.json", "model.safetensors", "sentencepiece.bpe.model",
                "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json"}
    assert model_dir.is_dir() and {p.name for p in model_dir.iterdir() if p.is_file()} == expected
    model_files = {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)}
                   for p in sorted(model_dir.iterdir()) if p.is_file()}
    for name, digest in prepared["tokenizer_files_sha256"].items():
        assert model_files[name]["sha256"] == digest

    # Diagnostic fixture selection only: prior source-scope concerns and useful
    # neighbouring leads, not a random sample or an unfamiliar holdout. Do not
    # send the former ranks, arms, selection rationale or verdicts to the labeler.
    chosen = {"provision": {77351, 268045, 330012, 177128, 88227, 160356},
              "judgment": {1011003, 951349, 928389, 951348, 332879, 504013, 799246, 594188}}
    selected, labelled = [], set()
    for kind, pool in data["reranked_pool"].items():
        for row in pool:
            if not chosen[kind].intersection(row["positions"]):
                continue
            identity = kind, tuple(row["positions"]), row["passage_sha256"]
            if identity in labelled:
                continue
            labelled.add(identity)
            neighbours = {}
            for snapshot in (data["baseline_result"], data["candidate_result"]):
                for candidate in snapshot["candidates"]:
                    if candidate["kind"] != kind:
                        continue
                    segments = candidate["context"]["segments"]
                    positions = {candidate["position"], *(s["position"] for s in segments)}
                    if not positions.intersection(row["positions"]):
                        continue
                    for segment in segments:
                        raw = segment["row"]
                        if segment["position"] in row["positions"]:
                            continue
                        key = (segment["position"], raw["full_text"])
                        neighbours[key] = {"position": segment["position"], "text": raw["full_text"],
                            "title": raw.get("act_name") or raw.get("case_name"),
                            "document_id": raw.get("act_id") or raw.get("case_id"),
                            "saved_scope": candidate["context"]["scope"]}
            selected.append({"kind": kind, "positions": row["positions"],
                "passage_sha256": row["passage_sha256"], "passage": row["passage"],
                "available_saved_neighbours": sorted(neighbours.values(), key=lambda r: r["position"])})
    assert len(selected) == 14
    selected.sort(key=lambda r: hashlib.sha256(("scope-label-order:" + r["passage_sha256"]).encode()).hexdigest())
    packet_rows, mapping = [], {}
    for number, row in enumerate(selected, 1):
        identity = f"source-{number:02d}"
        mapping[identity] = {k: row[k] for k in ("kind", "positions", "passage_sha256")}
        packet_rows.append({"id": identity, "kind": row["kind"], "passage": row["passage"],
            "available_saved_neighbours": row["available_saved_neighbours"]})
    write(PACKET, {"task": "Independently assess source usefulness for the deposit investigation below before any new ranking results. No arm, score or expected verdict is supplied. State prior familiarity.",
        "original_context": data["original_context"],
        "scope": "The reported equipment-deposit dispute, including conditional recovery routes and evidentiary or contrary-position distinctions. The separate drive dispute is background, not this labelled investigation.",
        "categories": ["directly_useful", "conditional_or_evidentiary_lead", "wrong_relationship_or_scope", "insufficient_held_context"],
        "instructions": "Read exact passages and supplied neighbours. Preserve party submissions, reproduced contract terms, quoted authority and deciding-court treatment separately. A useful lead is not a governing legal conclusion. For each ID provide category, source-linked reason, exact supporting quote(s), source role and limitations. You may mark genuine uncertainty; do not infer missing judgment context. Do not read experiment artifacts containing ranks, arms or prior assessments.",
        "sources": packet_rows})
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "state": "prepared_no_neural_calls",
        "input_sha256": sha(INPUT), "preparation_sha256": sha(PREPARATION),
        "script_sha256": sha(Path(__file__)), "retrieval_sha256": sha(ROOT / "nm/core_engine/retrieval.py"),
        "model": retrieval.RERANK_MODEL, "model_directory": str(model_dir), "model_files": model_files,
        "packet_sha256": sha(PACKET), "label_mapping": mapping,
        "arm_order": list(prepared["arms"]), "corpus_order": ["provision", "judgment"],
        "maximum_seconds": MAX_SECONDS, "maximum_local_predict_calls": 6, "provider_calls": 0,
        "source_pool_manifest": prepared["source_pool_manifest"],
        "evaluation_limits": ["Older seen matter; targeted14-source diagnostic set, not a random sample or held-out accuracy estimate.",
            "An identical provision passage occurs twice in the frozen pool. Both prediction entries remain unchanged; its source receives one independent label.",
            "Source labeler receives no arms/ranks/verdicts, but must disclose any prior familiarity.",
            "No fresh retrieval, complete-pool relevance labels or corpus-wide recall measurement.",
            "Recorded old scores lack model/tokenizer weight identity and full baseline-pool ranks; rerun all three arms once under this single frozen model.",
            "Fixed arm order with one cached model is not a counterbalanced repeated latency trial."]}
    write(MANIFEST, manifest)
    print(json.dumps({"state": manifest["state"], "manifest": str(MANIFEST), "packet": str(PACKET),
        "model_sha256": model_files["model.safetensors"]["sha256"], "label_sources": len(packet_rows),
        "inference_calls": 0, "provider_calls": 0}))


def check_inputs(manifest):
    assert sha(INPUT) == manifest["input_sha256"]
    assert sha(PREPARATION) == manifest["preparation_sha256"]
    assert sha(ROOT / "nm/core_engine/retrieval.py") == manifest["retrieval_sha256"]
    assert sha(Path(__file__)) == manifest["script_sha256"]
    assert sha(PACKET) == manifest["packet_sha256"]
    for name, entry in manifest["model_files"].items():
        path = Path(manifest["model_directory"]) / name
        assert path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"]


def worker():
    # Called only by the separately authorised controller below.
    from nm.core_engine import retrieval
    manifest, result = read(MANIFEST), read(RESULT)
    assert result["state"] == "running" and sha(LABELS) == result["labels_sha256"]
    check_inputs(manifest)
    prepared, original = read(PREPARATION), read(INPUT)
    models = retrieval._Models(ROOT / ".nm/models")
    load_start = time.perf_counter()
    model = models._model("reranking")
    result["model_load_seconds"] = time.perf_counter() - load_start
    result["device"] = str(model.device)
    result["dtype"] = str(next(model.model.parameters()).dtype)
    result["state"] = "running_local_inference"
    write(RESULT, result)
    original_predict = model.predict
    dispatches = 0

    def counted_predict(pairs, **kwargs):
        nonlocal dispatches
        assert dispatches < 6
        dispatches += 1
        return original_predict(pairs, **kwargs)

    model.predict = counted_predict
    try:
        for arm in manifest["arm_order"]:
            for kind in manifest["corpus_order"]:
                rows = original["reranked_pool"][kind]
                query = prepared["arms"][arm]["inquiry"]
                collection = retrieval.LocalCollection(corpus_dir=Path("unused"), lineage=Path("unused"),
                    doc_type="bare_act" if kind == "provision" else "case_law", models=models)
                start = time.perf_counter()
                scores = collection.rerank([(query, row["passage"]) for row in rows])
                elapsed = time.perf_counter() - start
                result["runs"].append({"arm": arm, "kind": kind, "elapsed_seconds": elapsed,
                    "query_sha256": prepared["arms"][arm]["inquiry_sha256"],
                    "prepared_pair_count": prepared["arms"][arm]["corpora"][kind]["prepared_pair_count"],
                    "scores": [{"positions": row["positions"], "passage_sha256": row["passage_sha256"], "score": float(score)}
                               for row, score in zip(rows, scores)]})
                result["local_predict_calls"] = dispatches
                write(RESULT, result)
        assert dispatches == 6
        result["state"] = "completed"
    finally:
        model.predict = original_predict
        result.update(finished_utc=datetime.now(timezone.utc).isoformat(),
            retrieval_sha256_after=sha(ROOT / "nm/core_engine/retrieval.py"), labels_sha256_after=sha(LABELS))
        assert result["retrieval_sha256_after"] == manifest["retrieval_sha256"]
        assert result["labels_sha256_after"] == result["labels_sha256"]
        write(RESULT, result)


def run():
    assert not RESULT.exists(), "Do not repeat the bounded diagnostic"
    manifest = read(MANIFEST)
    assert LABELS.is_file(), "Independent frozen source labels required before inference"
    labels = read(LABELS)
    assert labels.get("packet_sha256") == sha(PACKET)
    ids = {r["id"] for r in labels["assessments"]}
    assert ids == set(manifest["label_mapping"]) and len(labels["assessments"]) == len(ids)
    assert all(r.get("category") and r.get("reason") for r in labels["assessments"])
    write(RESULT, {"state": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": sha(MANIFEST), "labels_sha256": sha(LABELS), "runs": [],
        "provider_calls": 0, "maximum_seconds": MAX_SECONDS, "local_predict_calls": 0})
    try:
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker"],
            cwd=ROOT, timeout=MAX_SECONDS, check=False)
        if completed.returncode:
            result = read(RESULT)
            result.update(state="stopped_worker_failure", returncode=completed.returncode)
            write(RESULT, result)
    except subprocess.TimeoutExpired:
        result = read(RESULT)
        result.update(state="stopped_at_600_seconds", partial_measurement=True)
        write(RESULT, result)
    print(json.dumps({"output": str(RESULT), "state": read(RESULT)["state"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--run-authorized-local-once", action="store_true")
    mode.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.prepare_only:
        prepare()
    elif arguments.run_authorized_local_once:
        run()
    else:
        worker()
