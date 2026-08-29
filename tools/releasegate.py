"""The release gate. Measures the corpus, scores it against `spec/release.yaml`.

    python tools/releasegate.py             # measure and score
    python tools/releasegate.py --write     # also write spec/coverage.yaml

WHY THIS IS A GATE AND NOT A REPORT
-----------------------------------
The external review's first stop-ship finding was that the product claims
Telangana coverage against a corpus holding ZERO Telangana High Court
judgments. That fact was already written down, in `docs/BASELINE.md`, measured
and dated -- and it changed nothing, because a fact in a document is not a
gate.

The rule this project runs on is that a rule you cannot run is not a
requirement. So the coverage position is now measured by this tool, written to
`spec/coverage.yaml`, READ AT TURN TIME by `nm/knowledge/coverage.py`, and
disclosed to the advocate through gate G-COVERAGE. The same measurement gates
the release and warns the user.

THREE STATES, NEVER TWO
-----------------------
Every row scores PASS, FAIL or NOT MEASURED. A scorecard with two states
reports an uncomputed metric as though it were fine, which is defect shape S8
aimed at the release decision -- the most expensive possible place for it.

WHAT IT DOES NOT DO
-------------------
It does not build indices and it does not run evals. Both are long jobs the
user runs deliberately. Rows that depend on them score NOT MEASURED, loudly.
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.knowledge.citator import normalise_case_name  # noqa: E402
from nm.knowledge.jurisdiction import BIFURCATION, Court, normalise_court  # noqa: E402
from nm.knowledge.manifest import Manifest  # noqa: E402

CORPUS = ROOT / "legal_database" / "vector_store"
RELEASE = ROOT / "spec" / "release.yaml"
COVERAGE_OUT = ROOT / "spec" / "coverage.yaml"

PASS, FAIL, UNMEASURED = "PASS", "FAIL", "NOT MEASURED"


class Score:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, rid: str, state: str, measured: str, blocking: bool,
            note: str = "") -> None:
        self.rows.append({"id": rid, "state": state, "measured": measured,
                          "blocking": blocking, "note": note})

    def get(self, rid: str) -> dict | None:
        return next((r for r in self.rows if r["id"] == rid), None)


# ---------------------------------------------------------------- measuring ---

def measure_judgments() -> dict:
    """Courts, years and the bifurcation tripwire, from the parents store."""
    path = CORPUS / "caselaws_v2_parents.json"
    if not path.exists():
        return {"available": False, "store": str(path)}

    data = json.loads(path.read_text(encoding="utf8", errors="replace"))
    by_court: dict[str, int] = collections.Counter()
    years: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    raw_labels: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter)

    for rec in data.values():
        raw = (rec.get("court") or "").strip()
        court = normalise_court(raw).value
        by_court[court] += 1
        raw_labels[court][raw] += 1
        year = str(rec.get("year") or "")
        if year.isdigit():
            years[court][int(year)] += 1

    ap = years.get(Court.HC_ANDHRA_PRADESH.value, collections.Counter())
    ts = years.get(Court.HC_TELANGANA.value, collections.Counter())
    return {
        "available": True,
        "store": path.name,
        "total": len(data),
        "by_court": dict(by_court),
        # The normalisation defect, made visible: one judgment carries
        # `court = "Supreme Court"` where every other carries "Supreme Court of
        # India". Reporting the RAW labels per normalised court is what lets a
        # future ingest's new spelling be seen rather than silently folded.
        "raw_labels": {k: dict(v) for k, v in raw_labels.items()},
        "ap_years": {"min": min(ap) if ap else None, "max": max(ap) if ap else None,
                     "total": sum(ap.values())},
        "ap_post_bifurcation": sum(n for y, n in ap.items() if y >= BIFURCATION.year),
        "telangana_total": sum(ts.values()),
        "telangana_years": sorted(ts),
    }


def measure_paragraphs() -> dict:
    """Attribution and section-link coverage, over every case paragraph."""
    db = CORPUS / "chunks.db"
    if not db.exists():
        return {"available": False, "store": str(db)}

    attributable = {"ratio", "reasoning", "order"}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    total = attr = linked = attr_linked = 0
    try:
        for (blob,) in con.execute(
                "select blob from chunks where doc_type='case_law'"):
            b = json.loads(blob)
            total += 1
            is_attr = (b.get("paragraph_type") or "") in attributable
            has_link = bool(b.get("sections_cited"))
            attr += is_attr
            linked += has_link
            attr_linked += is_attr and has_link
    finally:
        con.close()
    return {
        "available": True, "store": "chunks.db",
        "paragraphs": total,
        "attributable": attr,
        "attributable_share": round(attr / total, 4) if total else 0.0,
        "with_section_link": linked,
        "attributable_with_section_link": attr_linked,
        "section_link_share_of_attributable": (
            round(attr_linked / attr, 4) if attr else 0.0),
    }


def measure_provisions(manifest: Manifest) -> dict:
    """Intended coverage against what the UNION lookup actually returns.

    Union across identifier conventions, per check `act-1`. Measuring one store
    is what produced B-164 and two later false gaps.
    """
    db = CORPUS / "chunks.db"
    if not db.exists():
        return {"available": False, "store": str(db)}

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    acts: dict[str, dict] = {}
    try:
        for entry in manifest.entries:
            held: set[str] = set()
            per_pattern: dict[str, int] = {}
            for pattern in entry.act_patterns:
                rows = con.execute(
                    """select distinct section_number from chunks
                       where doc_type='bare_act' and act_id like ?
                         and section_number is not null""",
                    (pattern,)).fetchall()
                found = {r[0] for r in rows}
                per_pattern[pattern] = len(found)
                held |= found
            intended = set(entry.intended_sections)
            acts[entry.act_name] = {
                "intended": len(intended),
                "held_union": len(held & intended),
                "held_any": len(held),
                "coverage": round(len(held & intended) / len(intended), 4)
                if intended else 0.0,
                "per_pattern": per_pattern,
            }
    finally:
        con.close()

    covered = sum(a["held_union"] for a in acts.values())
    intended = sum(a["intended"] for a in acts.values())
    return {
        "available": True, "store": "chunks.db",
        "acts": acts,
        "intended_total": intended,
        "held_total": covered,
        "coverage": round(covered / intended, 4) if intended else 0.0,
    }


def measure_citator(judgments: dict) -> dict:
    path = CORPUS / "citator.json"
    if not path.exists():
        return {"available": False, "store": str(path)}
    raw = json.loads(path.read_text(encoding="utf8", errors="replace"))
    negative = sum(1 for v in raw.values() if v.get("negative"))
    held = judgments.get("total") or 0
    return {
        "available": True, "store": path.name,
        "entries": len(raw),
        "negative": negative,
        "judgments_held": held,
        # An upper bound, and labelled as one. Entries are keyed by the case
        # NAME as written by the citing judgment, so this ratio assumes every
        # entry matches a held judgment -- which is generous. The real figure
        # is lower and the threshold must not be read as if it were tight.
        "entry_ratio_upper_bound": round(len(raw) / held, 4) if held else 0.0,
        "normalised_keys": len({normalise_case_name(k) for k in raw}),
    }


# ----------------------------------------------------------------- scoring ---

def score(rows: list[dict], m: dict) -> Score:
    s = Score()
    j, para, prov, cit = m["judgments"], m["paragraphs"], m["provisions"], m["citator"]
    by_id = {r["id"]: r for r in rows}

    def blocking(rid: str) -> bool:
        return bool(by_id.get(rid, {}).get("blocking"))

    # RG-01 -- binding-court output for the current period
    if not j.get("available"):
        s.add("RG-01", UNMEASURED, "the judgment store is not readable",
              blocking("RG-01"))
    else:
        ts = j["telangana_total"]
        s.add("RG-01", PASS if ts else FAIL,
              f"{ts} Telangana High Court judgments held; "
              f"{j['ap_years']['total']} Andhra Pradesh "
              f"({j['ap_years']['min']}-{j['ap_years']['max']})",
              blocking("RG-01"),
              "" if ts else
              "The binding court for every Telangana matter has NO output held. "
              "G-COVERAGE discloses this on every turn that would rest on High "
              "Court authority.")

    # RG-02 -- bind-1
    if not j.get("available"):
        s.add("RG-02", UNMEASURED, "the judgment store is not readable",
              blocking("RG-02"))
    else:
        n = j["ap_post_bifurcation"]
        s.add("RG-02", PASS if n == 0 else FAIL,
              f"{n} Andhra Pradesh judgments dated {BIFURCATION.year} or later",
              blocking("RG-02"),
              "" if n == 0 else
              "THE STANDING DECISION IS VOID. Andhra judgments may no longer be "
              "treated as binding on Telangana without computing the date "
              "against the bifurcation.")

    # RG-03 -- provision coverage
    if not prov.get("available"):
        s.add("RG-03", UNMEASURED, "chunks.db is not readable", blocking("RG-03"))
    else:
        worst = sorted(prov["acts"].items(), key=lambda kv: kv[1]["coverage"])[:3]
        s.add("RG-03", PASS if prov["coverage"] >= 0.95 else FAIL,
              f"{prov['coverage']:.1%} of {prov['intended_total']} intended "
              f"sections retrievable via the union",
              blocking("RG-03"),
              "weakest: " + "; ".join(
                  f"{k} {v['coverage']:.0%}" for k, v in worst))

    # RG-04 -- attributable share
    if not para.get("available"):
        s.add("RG-04", UNMEASURED, "chunks.db is not readable", blocking("RG-04"))
    else:
        s.add("RG-04", PASS if para["attributable_share"] >= 0.40 else FAIL,
              f"{para['attributable_share']:.1%} of {para['paragraphs']:,} case "
              f"paragraphs are ratio, reasoning or order", blocking("RG-04"))

    # RG-05 -- treatment coverage
    if not cit.get("available"):
        s.add("RG-05", UNMEASURED, "citator.json is not readable", blocking("RG-05"))
    else:
        ratio = cit["entry_ratio_upper_bound"]
        s.add("RG-05", PASS if ratio >= 0.50 else FAIL,
              f"{cit['entries']:,} citator entries against "
              f"{cit['judgments_held']:,} judgments "
              f"(<= {ratio:.1%}, an upper bound)", blocking("RG-05"),
              "The product may not claim to verify an authority is still good "
              "law. Treatment is `not_checked` on a miss and cannot carry a "
              "proposition alone.")

    # RG-06 -- provision-to-authority links
    if not para.get("available"):
        s.add("RG-06", UNMEASURED, "chunks.db is not readable", blocking("RG-06"))
    else:
        share = para["section_link_share_of_attributable"]
        s.add("RG-06", PASS if share >= 0.25 else FAIL,
              f"{share:.1%} of attributable paragraphs carry a section link "
              f"({para['attributable_with_section_link']:,} of "
              f"{para['attributable']:,})", blocking("RG-06"),
              "`legal.db.case_section_links` holds 0 rows, so this is the only "
              "route to 'which authorities interpret this provision'.")

    # RG-07 -- the authority index
    index = ROOT / ".nm" / "authority.db"
    s.add("RG-07", PASS if index.exists() else FAIL,
          "built" if index.exists() else
          "NOT BUILT -- run python tools/build_authority_index.py",
          blocking("RG-07"))

    # Rows this tool deliberately does not measure.
    for rid, why in (
            ("RG-10", "run tools/trace.py"),
            ("RG-11", "run tools/mutate.py"),
            ("RG-12", "run tools/trace.py"),
            ("RG-20", "the golden runner is not built (S0/T-005b)"),
            ("RG-21", "the golden runner is not built, and class-D runs need "
                      "explicit per-run approval"),
            ("RG-22", "needs served-turn metrics over a window"),
            ("RG-23", "needs served-turn metrics over a window"),
            ("RG-24", "needs served-turn metrics over a window"),
            ("RG-25", "needs served-turn metrics over a window")):
        s.add(rid, UNMEASURED, why, blocking(rid))
    return s


def coverage_document(m: dict, s: Score) -> dict:
    """What the RUNTIME reads. Measured facts only -- no thresholds.

    `nm/knowledge/coverage.py` loads this to answer, at turn time, what the
    corpus holds for a jurisdiction. The gate and the product therefore rest on
    ONE measurement, taken once, rather than on two that can disagree.
    """
    j = m["judgments"]
    return {
        "measured_at": time.strftime("%Y-%m-%d"),
        "corpus_version": (CORPUS / "VERSION").read_text(encoding="utf8").strip()
        if (CORPUS / "VERSION").exists() else "unrecorded",
        "judgments": {
            "total": j.get("total"),
            "by_court": j.get("by_court", {}),
            "andhra_pradesh": j.get("ap_years", {}),
            "andhra_post_bifurcation": j.get("ap_post_bifurcation"),
            "telangana_total": j.get("telangana_total"),
        },
        "jurisdictions": {
            "Telangana": {
                "binding_courts": ["supreme_court", "hc_telangana",
                                   "hc_andhra_pradesh"],
                "held": {
                    "supreme_court": j.get("by_court", {}).get("supreme_court", 0),
                    "hc_telangana": j.get("by_court", {}).get("hc_telangana", 0),
                    "hc_andhra_pradesh": j.get("by_court", {}).get(
                        "hc_andhra_pradesh", 0),
                },
                "gap": (
                    "No High Court output is held for this jurisdiction after "
                    f"{j.get('ap_years', {}).get('max')}. The Telangana High "
                    "Court was constituted on 1 January 2019 and none of its "
                    "judgments are in the corpus."
                    if not j.get("telangana_total") else ""),
            },
        },
        "paragraphs": m["paragraphs"],
        "provisions": {"coverage": m["provisions"].get("coverage"),
                       "intended_total": m["provisions"].get("intended_total")},
        "citator": {"entries": m["citator"].get("entries"),
                    "negative": m["citator"].get("negative")},
        "scorecard": [{"id": r["id"], "state": r["state"], "blocking": r["blocking"]}
                      for r in s.rows],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write spec/coverage.yaml for the runtime to read")
    args = ap.parse_args()

    rows = yaml.safe_load(RELEASE.read_text(encoding="utf8"))["scorecard"]
    by_id = {r["id"]: r for r in rows}

    t0 = time.time()
    manifest = Manifest.load(ROOT / "spec" / "manifest.yaml")
    m = {
        "judgments": measure_judgments(),
        "paragraphs": measure_paragraphs(),
        "provisions": measure_provisions(manifest),
    }
    m["citator"] = measure_citator(m["judgments"])
    s = score(rows, m)

    print("=" * 78)
    print("RELEASE GATE   spec/release.yaml against the measured corpus")
    print("=" * 78)
    for r in s.rows:
        meta = by_id.get(r["id"], {})
        mark = {PASS: "PASS", FAIL: "FAIL", UNMEASURED: "  ??"}[r["state"]]
        block = "!" if r["blocking"] else " "
        print(f"  [{mark}]{block} {r['id']}  {str(meta.get('what'))[:56]}")
        print(f"           {r['measured']}")
        if r["note"]:
            for line in _wrap(r["note"], 66):
                print(f"           -> {line}")

    failed = [r for r in s.rows if r["state"] == FAIL and r["blocking"]]
    unmeasured = [r for r in s.rows if r["state"] == UNMEASURED and r["blocking"]]
    print()
    print(f"  measured in {time.time() - t0:.0f}s")
    print(f"  {sum(1 for r in s.rows if r['state'] == PASS)} pass, "
          f"{sum(1 for r in s.rows if r['state'] == FAIL)} fail, "
          f"{sum(1 for r in s.rows if r['state'] == UNMEASURED)} not measured")

    if args.write:
        doc = coverage_document(m, s)
        COVERAGE_OUT.write_text(
            "# GENERATED by tools/releasegate.py -- do not edit.\n"
            "# MEASURED FACTS ONLY. Thresholds live in spec/release.yaml, and\n"
            "# nm/knowledge/coverage.py reads this at turn time so the release\n"
            "# gate and the advocate-facing disclosure rest on ONE measurement.\n\n"
            + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf8")
        print(f"  wrote {COVERAGE_OUT.relative_to(ROOT)}")

    print()
    if failed:
        print(f"RELEASE BLOCKED -- {len(failed)} blocking row(s) FAILED: "
              f"{', '.join(r['id'] for r in failed)}")
        return 1
    if unmeasured:
        # NOT MEASURED is not a pass. A release criterion nobody computed is
        # the one that gets assumed, so it exits non-zero exactly like a fail.
        print(f"RELEASE BLOCKED -- {len(unmeasured)} blocking row(s) NOT MEASURED: "
              f"{', '.join(r['id'] for r in unmeasured)}")
        print("A criterion nobody has computed is not a criterion that passed.")
        return 2
    print("RELEASE GATE OK")
    return 0


def _wrap(text: str, width: int) -> list[str]:
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
