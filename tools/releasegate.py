"""The release gate. Measures the corpus, scores it against `spec/release.yaml`.

    python tools/releasegate.py             # measure and score
    python tools/releasegate.py --write     # also write spec/coverage.yaml

WHY THIS IS A GATE AND NOT A REPORT
-----------------------------------
The external review's first stop-ship finding was that the product claims
Telangana coverage it had not measured. That fact was already written down, in
`docs/BASELINE.md`, measured and dated -- and it changed nothing, because a
fact in a document is not a gate.

AND THE FIRST VERSION OF THAT GATE MEASURED THE WRONG THING. RG-01 counted the
`hc_telangana` court LABEL, which no record in the corpus carries, got 0, and
reported that the binding court for every Telangana matter has no output held.
There are 4,280 High Court judgments binding on Telangana -- every held Andhra
Pradesh judgment is binding under the standing decision in BASELINE.md 1.1 --
so a blocking release criterion, and the disclosure the advocate reads on every
authority turn, both stated the opposite of the truth. A zero from the wrong
index reads exactly like absence; that is the trap CLAUDE.md records against
the provision stores, and it reached the case store too.

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
import os
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

from tools._console import utf8_console  # noqa: E402

utf8_console()

from nm.knowledge.citator import normalise_case_name  # noqa: E402
from nm.knowledge.jurisdiction import BIFURCATION, Court, normalise_court  # noqa: E402
from nm.knowledge.manifest import Manifest  # noqa: E402
from tools._fingerprint import source_fingerprint  # noqa: E402

#: The first year of "the current period" for coverage purposes. Authority
#: older than this is held and quotable; what it is not is CURRENT, and the
#: two are different things an advocate needs told apart.
CURRENT_PERIOD_FROM = 2021

#: How many served turns the rolling rows look back over. Named once so
#: RG-22..RG-25 cannot silently measure different windows and be compared.
SERVED_WINDOW = 200

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
        # WHAT BINDS A TELANGANA MATTER, which is a relationship and not a
        # court label. Counting the `hc_telangana` label alone returned 0 --
        # no record carries it, the files describe themselves as "Andhra HC
        # (Pre-Telangana)" -- and 0 from the wrong index reads exactly like
        # "not in the corpus". Every one of these 4,280 AP judgments is
        # BINDING on Telangana; that decision is recorded in BASELINE.md 1.1
        # and implemented in nm/knowledge/jurisdiction.py.
        "hc_binding_total": sum(ap.values()) + sum(ts.values()),
        "hc_binding_years": sorted(set(ap) | set(ts)),
        "hc_binding_latest": max([*ap, *ts], default=None),
        "sc_years": sorted(years.get(Court.SUPREME_COURT.value, {})),
        "sc_latest": max(years.get(Court.SUPREME_COURT.value, {}),
                         default=None),
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
    """THE INTERSECTION, not the ratio.

    The first version of this divided 4,894 citator entries by 33,791
    judgments, called the result an upper bound, and reported 14.5%. The
    measured intersection is 0.84% -- wrong by a factor of seventeen, because
    94.3% of citator keys name cases this corpus does not hold.

    A ratio of two set sizes is not a coverage measurement. Naming it an upper
    bound made it sound careful without making it true.
    """
    path = CORPUS / "citator.json"
    parents = CORPUS / "caselaws_v2_parents.json"
    if not path.exists() or not parents.exists():
        return {"available": False, "store": str(path)}

    raw = json.loads(path.read_text(encoding="utf8", errors="replace"))
    held_doc = json.loads(parents.read_text(encoding="utf8", errors="replace"))
    held_names = {normalise_case_name(r.get("case_name") or "")
                  for r in held_doc.values()}
    held_names.discard("")

    # Resolved through the citation graph's name variants where available --
    # exact-match-only would understate it, and understating is not honesty.
    variants: dict[str, list] = {}
    graph = CORPUS / "citation_graph.json"
    if graph.exists():
        g = json.loads(graph.read_text(encoding="utf8", errors="replace"))
        info = g.get("case_info", {})
        for name, ids in (g.get("name_to_ids") or {}).items():
            variants.setdefault(normalise_case_name(name), []).extend(
                normalise_case_name(info.get(i, {}).get("case_name") or "")
                for i in ids)

    matched, negative_matched = set(), set()
    for key, entry in raw.items():
        norm = normalise_case_name(key)
        candidates = {norm} | set(variants.get(norm, ()))
        hit = candidates & held_names
        if hit:
            matched |= hit
            if entry.get("negative"):
                negative_matched |= hit

    return {
        "available": True, "store": path.name,
        "entries": len(raw),
        "negative_entries": sum(1 for v in raw.values() if v.get("negative")),
        "judgments_held": len(held_names),
        "judgments_with_treatment": len(matched),
        "judgments_with_negative_treatment": len(negative_matched),
        "coverage": round(len(matched) / len(held_names), 4) if held_names else 0.0,
        "keys_naming_nothing_held": len(raw) - len(matched),
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
        # BINDING-COURT OUTPUT, not one court's label. The courts that bind
        # a Telangana matter are the Supreme Court and the High Court for
        # its territory -- which means the Andhra Pradesh High Court, whose
        # every held judgment is binding under the standing decision.
        hc = j["hc_binding_total"]
        sc = j["by_court"].get(Court.SUPREME_COURT.value, 0)
        recent = [y for y in j["sc_years"] if y >= CURRENT_PERIOD_FROM]
        s.add("RG-01", PASS if (hc and sc and len(recent) >= 5) else FAIL,
              f"{hc + sc:,} binding-court judgments held: {sc:,} Supreme "
              f"Court (through {j['sc_latest']}), {hc:,} High Court binding "
              f"on Telangana (through {j['hc_binding_latest']})",
              blocking("RG-01"),
              "" if (hc and sc and len(recent) >= 5) else
              "A court that binds every Telangana matter has no output held "
              "for the current period.")

        # RG-01b -- the gap that IS real, stated as itself. High Court
        # output stops at the bifurcation, so the most recent binding High
        # Court authority is years old. That is a RECENCY gap, and folding
        # it into RG-01 made the product say the opposite of the truth:
        # "no High Court output is held" where 4,280 judgments are held.
        latest = j["hc_binding_latest"]
        fresh = latest is not None and latest >= CURRENT_PERIOD_FROM
        s.add("RG-01b", PASS if fresh else FAIL,
              f"the most recent binding High Court judgment is {latest}; "
              f"the current period begins {CURRENT_PERIOD_FROM}",
              blocking("RG-01b"),
              "" if fresh else
              f"No High Court judgment later than {latest} is held. The "
              f"authority is not absent — it is not current, and an advocate "
              f"relying on it should know which.")

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
        cov = cit["coverage"]
        s.add("RG-05", PASS if cov >= 0.50 else FAIL,
              f"{cit['judgments_with_treatment']:,} of {cit['judgments_held']:,} "
              f"held judgments have any citator entry ({cov:.2%}); "
              f"{cit['judgments_with_negative_treatment']:,} carry negative "
              f"treatment", blocking("RG-05"),
              "THE PRODUCT DOES NOT VERIFY WHETHER AN AUTHORITY IS STILL GOOD "
              "LAW. Treatment is `not_checked` on a miss, so no recommendation "
              "rests on case law: judgments are shown as reading material with "
              "the limit stated, and statute carries the advice.")

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

    # RG-08 / RG-09 -- the identity index and the shape of what it parsed
    identity = ROOT / ".nm" / "identity.db"
    if not identity.exists():
        for rid in ("RG-08", "RG-09"):
            s.add(rid, FAIL, "NOT BUILT -- run python tools/build_identity_index.py",
                  blocking(rid))
    else:
        con = sqlite3.connect(f"file:{identity}?mode=ro", uri=True)
        try:
            ident = dict(con.execute("select key, value from identity").fetchall())
            sizes = dict(con.execute(
                "select bench_size, count(*) from cases where bench_size is not null"
                " group by 1").fetchall())
        finally:
            con.close()
        cases, with_bench = int(ident["cases"]), int(ident["with_bench"])
        keys = int(ident["citation_keys"])
        ok = with_bench / cases >= 0.85 and keys >= 250_000
        s.add("RG-08", PASS if ok else FAIL,
              f"{with_bench:,} of {cases:,} judgments carry a parsed bench "
              f"({with_bench / cases:.1%}); {keys:,} citation keys; "
              f"{ident['targets_adverse']} judgments with adverse treatment; "
              f"{ident.get('rejects', '?')} rejects recorded",
              blocking("RG-08"),
              "The corpus spans 1955-2026 and the header format drifts. Every "
              "field that could not be established is recorded in `rejects` "
              "with a reason and an era, so the gap is enumerable rather than "
              "an undifferentiated NULL.")

        total = sum(sizes.values()) or 1
        small = sum(v for k, v in sizes.items() if k <= 3) / total
        huge = sum(v for k, v in sizes.items() if k >= 8) / total
        s.add("RG-09", PASS if (small >= 0.85 and huge < 0.005) else FAIL,
              f"{small:.1%} of benches are 1-3 judges, {huge:.2%} are 8 or more",
              blocking("RG-09"),
              "" if small >= 0.85 else
              "the bench parse is swallowing non-judge lines again")

    # Rows this tool deliberately does not measure.
    for rid, why in (
            ("RG-21", "a class-D judged run needs explicit per-run approval "
                      "and none is recorded against this source"),):
        s.add(rid, UNMEASURED, why, blocking(rid))

    # ---- RG-10, RG-12: the matrix and the status claims, RECOMPUTED --------
    tr = measure_trace()
    if not tr["available"]:
        s.add("RG-10", UNMEASURED, tr["why"], blocking("RG-10"))
        s.add("RG-12", UNMEASURED, tr["why"], blocking("RG-12"))
    else:
        broken = tr["unwired"] + tr["undeclared"] + tr["orphan_gates"]
        s.add("RG-10", PASS if not broken else FAIL,
              f"{tr['gates']} gates; {len(tr['unwired'])} declared built and "
              f"unwired, {len(tr['undeclared'])} declared unbuilt and consulted, "
              f"{len(tr['orphan_gates'])} consulted and not in the matrix",
              blocking("RG-10"),
              "" if not broken else
              f"The matrix and the code disagree on {', '.join(broken)}. The "
              f"matrix is what the advocate is told evaluates their matter.")
        s.add("RG-12", PASS if not tr["inflated"] else FAIL,
              f"{tr['evals_run']} evals have run; "
              f"{len(tr['inflated'])} feature(s) claim `tested` on evals that "
              f"never ran",
              blocking("RG-12"),
              "" if not tr["inflated"] else
              f"{', '.join(tr['inflated'])} claim evidence that does not exist.")

    # ---- RG-11: the suite bites, against THIS source -----------------------
    mu = measure_mutations()
    if not mu["available"]:
        s.add("RG-11", UNMEASURED, mu["why"], blocking("RG-11"))
    else:
        ok = mu["total"] > 0 and not mu["survived"]
        s.add("RG-11", PASS if ok else FAIL,
              f"{mu['caught']} of {mu['total']} mutations caught",
              blocking("RG-11"),
              "" if ok else
              f"These tests are decoration: {', '.join(mu['survived'])}")

    # ---- RG-20: the golden smoke suite, class A and C ----------------------
    g = measure_goldens()
    if not g["available"]:
        s.add("RG-20", UNMEASURED, g["why"], blocking("RG-20"))
    else:
        bad = g["structure_failures"] + g["authority_failures"]
        s.add("RG-20", PASS if not bad else FAIL,
              f"{g['scenarios']} scenarios, {g['smoke']} in `smoke`; "
              f"{g['resolved']}/{g['authority_total']} anchors read back",
              blocking("RG-20"),
              "" if not bad else "; ".join(bad[:3]))

    # ---- RG-22..RG-25: over the turns actually served ----------------------
    sv = measure_served()
    for rid in ("RG-22", "RG-23", "RG-24", "RG-25"):
        if not sv["available"]:
            s.add(rid, UNMEASURED, sv["why"], blocking(rid))
    if sv["available"]:
        n = sv["turns"]
        s.add("RG-22", PASS if sv["ungated_grounding"] == 0 else FAIL,
              f"{sv['ungated_grounding']} ungated grounding violation(s) in the "
              f"last {n} served turns", blocking("RG-22"),
              "" if sv["ungated_grounding"] == 0 else
              "A grounding violation that did not gate means the answer went out.")
        s.add("RG-23", PASS if sv["withheld_rate"] <= 0.05 else FAIL,
              f"{sv['withheld']} of {n} served turns withheld "
              f"({sv['withheld_rate']:.1%})", blocking("RG-23"))
        s.add("RG-24", PASS if sv["median_cost"] <= 0.02 else FAIL,
              f"median cost ${sv['median_cost']:.4f} over {n} served turns",
              blocking("RG-24"))
        s.add("RG-25", PASS if sv["p95_latency_ms"] <= 8000 else FAIL,
              f"p95 latency {sv['p95_latency_ms']}ms over {n} served turns",
              blocking("RG-25"))
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
                    "hc_binding_on_telangana": j.get("hc_binding_total", 0),
                },
                "hc_binding_latest": j.get("hc_binding_latest"),
                "supreme_court_latest": j.get("sc_latest"),
                # WHAT IS TRUE, and it is not what this used to say. There
                # ARE High Court judgments binding on Telangana -- 4,280 of
                # them -- and telling an advocate otherwise on every
                # authority turn was a false gap, from counting a court
                # label instead of a binding relationship.
                "gap": (
                    f"the most recent High Court judgment binding on this "
                    f"jurisdiction is from {j.get('hc_binding_latest')}, so "
                    f"there is no High Court authority here for the years "
                    f"since. Supreme Court output runs to "
                    f"{j.get('sc_latest')} and binds throughout."
                    if (j.get("hc_binding_latest") or 0) < CURRENT_PERIOD_FROM
                    else ""),
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


def measure_trace() -> dict:
    """RG-10 and RG-12, RECOMPUTED rather than read from a log.

    Parsing trace's stdout would score a criterion off a run that may predate
    the code. These call the same helpers trace does, here, now.
    """
    try:
        from tools import trace as tracer
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        return {"available": False, "why": f"trace is not importable: {exc}"}

    try:
        features, evals = tracer.load_spec()
        gates = tracer.load_gates()
        consulted = tracer.gate_consultations()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "why": f"the spec could not be read: {exc}"}

    # T8 / T9 -- the matrix against the code, in BOTH directions. A gate
    # declared built that nothing consults is a promise the product does not
    # keep; one declared unbuilt that something consults is worse, because the
    # matrix is then telling the advocate nothing evaluates a condition while
    # something quietly does.
    unwired = [g["id"] for g in gates if g["built"] and not consulted.get(g["id"])]
    undeclared = [g["id"] for g in gates
                  if not g["built"] and consulted.get(g["id"])]
    known = {g["id"] for g in gates}
    orphan = sorted(set(consulted) - known)

    # T3 / T4 -- status inflation. A feature at `tested` whose evals have
    # never run is claiming evidence that does not exist.
    ran = set(tracer.recorded_runs()) if hasattr(tracer, "recorded_runs") else set()
    if not ran:
        results = ROOT / ".nm" / "eval_results.json"
        if results.exists():
            ran = set(json.loads(results.read_text(encoding="utf8"))
                      .get("evals_run", []))
    inflated = []
    for f in features:
        if (f.get("status") or "decided") != "tested":
            continue
        declared = set(f.get("eval_ids") or [])
        if declared and not (declared & ran):
            inflated.append(f["id"])

    return {"available": True, "unwired": unwired, "undeclared": undeclared,
            "orphan_gates": orphan, "inflated": sorted(inflated),
            "gates": len(gates), "evals_run": len(ran)}


def measure_mutations() -> dict:
    """RG-11. A RECORDED run, so it must say what it ran against."""
    results = ROOT / ".nm" / "eval_results.json"
    if not results.exists():
        return {"available": False, "why": "no mutation run has been recorded"}
    try:
        doc = json.loads(results.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {"available": False, "why": f"the eval record is unreadable: {exc}"}

    rec = doc.get("mutations")
    if not rec:
        return {"available": False,
                "why": "no mutation run has been recorded since runs began "
                       "carrying a source fingerprint. Run tools/mutate.py"}

    now = source_fingerprint()
    if rec.get("source_fingerprint") != now:
        # STALE IS NOT MEASURED. It is never PASS, and it is not FAIL either --
        # the suite may well still bite; nobody has checked against this code.
        return {"available": False,
                "why": (f"the recorded mutation run was made against source "
                        f"{rec.get('source_fingerprint')!r} and the tree is now "
                        f"{now!r}. A run cannot vouch for code it never saw. "
                        f"Run tools/mutate.py")}
    return {"available": True, "caught": rec.get("caught", 0),
            "total": rec.get("total", 0), "survived": rec.get("survived", [])}


def measure_goldens() -> dict:
    """RG-20. The smoke suite's structure and authority checks, run here.

    These are class A and C -- no model, no approval -- so there is no reason
    to report them unmeasured. The class-D judged run is RG-21 and stays
    separate, because it costs money and needs your word.
    """
    try:
        from tools import run_goldens as goldens
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "why": f"the golden runner is not importable: {exc}"}
    try:
        scenarios = goldens.load_scenarios()
        structure = goldens.check_structure(scenarios)
        authority, resolved, total = goldens.check_authority()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "why": f"the golden set could not be read: {exc}"}
    smoke = goldens.expand("smoke", scenarios)
    return {"available": True, "scenarios": len(scenarios), "smoke": len(smoke),
            "structure_failures": structure, "authority_failures": authority,
            "resolved": resolved, "authority_total": total}


def measure_served() -> dict:
    """RG-22..RG-25, over the last SERVED_WINDOW turns actually served.

    Real turns, not a synthetic sample. `metrics` is written on every turn
    including the ones that failed, which is what makes a withheld-turn rate
    meaningful rather than a survivorship figure.
    """
    store = os.environ.get("NM_MATTER_STORE", ".nm/matters")
    d = ROOT / store / "metrics"
    if not d.is_dir():
        return {"available": False, "why": f"no served-turn metrics at {d}"}
    files = sorted(d.glob("turn_*.json"), key=lambda p: p.stat().st_mtime)
    files = files[-SERVED_WINDOW:]
    if not files:
        return {"available": False, "why": "no served turns have been recorded"}

    turns, ungated, withheld, costs, latencies = [], 0, 0, [], []
    for f in files:
        try:
            m = json.loads(f.read_text(encoding="utf8"))
        except json.JSONDecodeError:
            continue
        turns.append(m)
        # A GROUNDING VIOLATION THAT DID NOT GATE is the dangerous one: the
        # answer went out. One that gated is the system working.
        for v in m.get("violations", []):
            if v.get("rule", "").startswith("G-") and not v.get("gating"):
                ungated += 1
        if m.get("outcome") in ("gated", "failed"):
            withheld += 1
        costs.append(float(m.get("cost_usd") or 0.0))
        latencies.append(int(m.get("latency_ms") or 0))

    if not turns:
        return {"available": False, "why": "every recorded turn was unreadable"}
    costs.sort()
    latencies.sort()
    mid = costs[len(costs) // 2] if costs else 0.0
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    return {"available": True, "turns": len(turns), "ungated_grounding": ungated,
            "withheld": withheld, "withheld_rate": withheld / len(turns),
            "median_cost": mid, "p95_latency_ms": p95}


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
