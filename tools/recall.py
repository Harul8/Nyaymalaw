"""Recall@k on (matter, governing provision) pairs. E-053, task T-055.

    python tools/recall.py                 # score the sample, if there is one
    python tools/recall.py --template      # write an empty sample to fill in

WHY THIS TOOL EXISTS BUT REPORTS NOT MEASURED
-----------------------------------------------
T-055 is explicit about the one thing that makes this number worth having:

    "Drawn from real matters and hand-vetted, NEVER authored. An authored set
     measures only what its author expected the system to find."

That is not a stylistic preference. A sample I write is a sample of the
questions I already know the router handles — every edge in
`nm/knowledge/resolution.py` would score, the number would be high, and it
would measure nothing except my own memory of what I built this morning.

So the runner is built, the format is fixed, and the sample is EMPTY until an
advocate supplies real matters with the provision that actually governed each
one. `spec/release.yaml` RG-19 reads the result, and an absent sample scores
NOT MEASURED — which exits non-zero exactly like FAIL, because a criterion
nobody computed is the one that gets assumed.

WHAT "RECALL@K" MEANS HERE, PRECISELY
--------------------------------------
For each pair, retrieval is run on the matter's own question and the rank of
the governing provision in the returned Findings is recorded. `k` is a list,
not a single number, because the useful question is not "did it find it" but
"how far down" — a provision at rank 1 is an answer and the same provision at
rank 30 is a list the advocate has to read.

A pair whose provision is NOT retrieved at all is recorded as a MISS with the
coverage state that came back, so a routing failure can be told apart from a
corpus gap. Collapsing those two would make this number unactionable: the fix
for one is an edge and the fix for the other is ingestion.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._console import utf8_console  # noqa: E402

utf8_console()

SAMPLE = ROOT / "spec" / "recall_sample.json"
OUT = ROOT / ".nm" / "recall.json"
KS = (1, 3, 5, 10)

TEMPLATE = {
    "_what_this_is": (
        "Hand-vetted (matter, governing provision) pairs drawn from REAL "
        "matters. Never authored: an authored set measures only what its "
        "author expected the system to find (T-055)."),
    "_how_to_fill": (
        "One object per pair. `question` is what the advocate actually wrote. "
        "`cause_of_action` is what an advocate says the cause is, or null if "
        "they would not classify it. `governing` is the provision that "
        "ACTUALLY governed, in the corpus's own key form -- `Article_14`, "
        "`138` -- with `act` its full title."),
    "_vetted_by": "",
    "_vetted_on": "",
    "pairs": [],
}


def load() -> dict | None:
    if not SAMPLE.exists():
        return None
    doc = json.loads(SAMPLE.read_text(encoding="utf8"))
    return doc if doc.get("pairs") else None


def score(doc: dict) -> dict:
    """Run retrieval for each pair and record where the governing provision
    landed. NEVER an average that hides a miss: misses are listed."""
    from datetime import date

    from nm.adapters.evidence.corpus import CorpusEvidenceAdapter
    from nm.knowledge.manifest import Manifest
    from nm.ports.evidence import EvidenceNeed

    adapter = CorpusEvidenceAdapter(
        ROOT / "legal_database" / "vector_store",
        Manifest.load(ROOT / "spec" / "manifest.yaml"))
    if not adapter.available:
        return {"state": "NOT MEASURED",
                "why": "the corpus is not attached, so nothing was retrieved"}

    ranks: list[int | None] = []
    misses: list[dict] = []
    for pair in doc["pairs"]:
        need = EvidenceNeed(
            question=pair["question"],
            governing_date=date.fromisoformat(
                pair.get("governing_date") or date.today().isoformat()),
            cause_of_action=pair.get("cause_of_action"))
        result = adapter.fetch(need)
        want = (pair["governing"] or "").strip()
        found = None
        for i, f in enumerate(result.findings, 1):
            if want and want.replace("_", " ").lower() in f.ref.lower():
                found = i
                break
        ranks.append(found)
        if found is None:
            # THE COVERAGE STATE IS KEPT. A routing failure and a corpus gap
            # need different fixes, and a bare miss cannot tell them apart.
            misses.append({"question": pair["question"][:80],
                           "wanted": want,
                           "coverage": result.coverage.value,
                           "missing": (result.missing or "")[:140]})

    total = len(ranks)
    return {
        "state": "MEASURED",
        "pairs": total,
        "recall_at": {str(k): round(
            sum(1 for r in ranks if r is not None and r <= k) / total, 3)
            for k in KS} if total else {},
        "misses": misses,
        "vetted_by": doc.get("_vetted_by") or "UNRECORDED",
        "vetted_on": doc.get("_vetted_on") or "UNRECORDED",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", action="store_true",
                    help="write an empty sample file to fill in")
    args = ap.parse_args()

    if args.template:
        if SAMPLE.exists():
            print(f"REFUSED. {SAMPLE.relative_to(ROOT)} already exists and "
                  f"overwriting it would discard vetted work.")
            return 2
        SAMPLE.write_text(json.dumps(TEMPLATE, indent=2), encoding="utf8")
        print(f"wrote {SAMPLE.relative_to(ROOT)} -- fill in `pairs` from REAL "
              f"matters and record who vetted them.")
        return 0

    doc = load()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if doc is None:
        result = {
            "state": "NOT MEASURED",
            "why": ("no hand-vetted sample exists at "
                    f"{SAMPLE.relative_to(ROOT)}. T-055 requires pairs drawn "
                    "from real matters; an authored set measures only what "
                    "its author expected the system to find."),
        }
        OUT.write_text(json.dumps(result, indent=2), encoding="utf8")
        print("RECALL: NOT MEASURED")
        print(f"  {result['why']}")
        print("  Run `python tools/recall.py --template` to start one.")
        # NOT MEASURED EXITS NON-ZERO, exactly like FAIL.
        return 1

    result = score(doc)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf8")
    print(f"RECALL: {result['state']}")
    for k, v in (result.get("recall_at") or {}).items():
        print(f"  recall@{k:<3} {v:.1%}")
    for m in result.get("misses", []):
        print(f"  MISS  {m['wanted']:<14} [{m['coverage']}]  {m['question']}")
    return 0 if result["state"] == "MEASURED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
