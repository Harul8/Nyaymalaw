"""Compare frozen pre-ranking labels with the one completed local diagnostic."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha(name):
    return hashlib.sha256((OUT / name).read_bytes()).hexdigest()


manifest = read("rerank-local-manifest.json")
result = read("rerank-local-results.json")
labels = read("rerank-local-independent-labels.json")
assert result["state"] == "completed" and result["local_predict_calls"] == 6
assert result["labels_sha256"] == result["labels_sha256_after"] == sha("rerank-local-independent-labels.json")
assert result["retrieval_sha256_after"] == manifest["retrieval_sha256"]
ranking = {(run["arm"], run["kind"]): sorted(enumerate(run["scores"]),
    key=lambda row: (-row[1]["score"], min(row[1]["positions"]), row[0])) for run in result["runs"]}
measured = []
for label in labels["assessments"]:
    identity = manifest["label_mapping"][label["id"]]
    movements = {}
    for arm in manifest["arm_order"]:
        movements[arm] = [{"pool_rank": rank + 1, "score": row["score"]}
            for rank, (_, row) in enumerate(ranking[(arm, identity["kind"])])
            if row["passage_sha256"] == identity["passage_sha256"]
            and row["positions"] == identity["positions"]]
        assert movements[arm]
    measured.append({"id": label["id"], **identity, "category": label["category"],
        "reason": label["reason"], "source_role": label["source_role"],
        "limitations": label["limitations"], "supporting_quotes": label["supporting_quotes"],
        "movements": movements})
summary = {
    "scope": "One local shared-model diagnostic on the older frozen Vale deposit-investigation pool; no production promotion or browser acceptance",
    "results_sha256": sha("rerank-local-results.json"),
    "independent_labels_sha256": sha("rerank-local-independent-labels.json"),
    "completed_local_predict_calls": 6, "provider_calls": 0, "timed_out": False,
    "model_load_seconds": result["model_load_seconds"], "device": result["device"], "dtype": result["dtype"],
    "timings": {arm: {"total_rerank_seconds": sum(r["elapsed_seconds"] for r in result["runs"] if r["arm"] == arm),
        "corpora": {r["kind"]: r["elapsed_seconds"] for r in result["runs"] if r["arm"] == arm}}
        for arm in manifest["arm_order"]},
    "ranking_method": "Sort the identical scored pool by descending score, lowest associated position, then original pool entry index. Preserve duplicate prediction rows; these are pool ranks, not final per-document-diversity selections.",
    "labelled_source_movements": measured,
    "top_six_pool_rows_not_final_selection": {arm: {kind: [
        {"pool_rank": i + 1, **row} for i, (_, row) in enumerate(ranking[(arm, kind)][:6])]
        for kind in manifest["corpus_order"]} for arm in manifest["arm_order"]},
    "findings": [
        "Focused input improves the two equipment-lease passages from judgment pool ranks16/5 to1/2. Their useful legal discussion is in a shared saved neighbour; these are not two independent governing authorities.",
        "The mortgage-jurisdiction party submission rises from judgment pool rank17 to3 under focused input despite an independent wrong-relationship/scope label.",
        "The Espire evidentiary lead falls from judgment pool rank3 to97, and the Mahendra deposit/handover lead from19 to78. Compactness can improve a close factual match while losing differently worded useful contributions.",
        "The qualified contractual/writ discussion moves from judgment pool rank9 to12. Its limited forum significance and quoted-authority status remain unchanged.",
        "The special Court-of-Wards procedure rises from provision pool rank18 to3, while the toll-device provision remains rank4 under focused input. Presenting account and concepts together does not establish the required legal relationship.",
        "Whole-message input also has mixed movement; it separates the exact factual qualifications and complete concepts into different tokenizer windows.",
        "No source selection, passage admission, response generation, legal applicability decision or browser run was executed. New score and rank movement is not an accuracy or completion claim.",
    ],
    "recommendation": "Do not promote as a proven relevance repair. Lower duplication and measured local runtime are supported; relevance is mixed, and precise relationship, evidentiary usefulness and source role remain unresolved.",
    "limitations": [
        "Fourteen targeted sources, labelled independently before new scores with prior familiarity disclosed; not a random or unfamiliar test population. No precision/recall/accuracy percentage is inferred.",
        "Labels assess exact primary passages plus available saved neighbours; the reranker scores primary passage text only. Some usefulness is neighbour-only and must remain qualified.",
        "Single run per arm, fixed arm order, shared cached model. Loading is separate; no repeated or counterbalanced latency trial was performed.",
        "Frozen pool includes duplicate prediction rows and does not measure candidate discovery. Complete corpus recall and final diversity selection are unmeasured.",
        "All original concepts, including their existing unsupported not-supplied-to-nonexistence transformation, remained unchanged across arms.",
    ],
}
destination = OUT / "rerank-local-assessment.json"
assert not destination.exists(), "Preserve prior assessment"
destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"output": str(destination), "state": result["state"], "local_predict_calls": 6,
                  "timings": summary["timings"]}))
