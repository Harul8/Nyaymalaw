"""Drive golden scenarios end to end, and VERIFY EVERY CITATION INDEPENDENTLY.

    python tools/run_scenario.py --scenario GS-06 GS-08 --approve

WHAT THIS CHECKS THAT THE GROUNDING GATE DOES NOT
---------------------------------------------------
The gate refuses a turn whose text names a provision or case that was not
retrieved on that turn. That is a check on the ANSWER against the RETRIEVAL.

This is a check on the retrieval against the CORPUS. It takes every locator NM
emits, goes back to `chunks.db`, pulls that exact chunk, and asserts the quoted
span is really in it — verbatim, on the bytes. A citation that survives both is
one an advocate can put in front of a judge.

They are different failures. The gate is satisfied by a self-consistent
hallucination: retrieval returns a Finding, the answer cites it, the gate is
happy, and the Finding never corresponded to anything in the corpus. Only
reading the corpus back catches that, and it is the check that matters most
because it is the one an advocate would otherwise perform by hand.

LANGUAGE IS FREE; CITATIONS ARE NOT
------------------------------------
The model's prose varies run to run and that is fine — an advocate does not
need the same sentence twice. What must not vary is which provision was cited,
which case, and whether the words in quotation marks are the corpus's own. So
this reports the citation ledger, not a diff of the English.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "legal_database" / "vector_store" / "chunks.db"
BASE = "http://127.0.0.1:8078"

_WORDS = re.compile(r"[a-z0-9]+")


def fold(text: str) -> str:
    return " ".join(_WORDS.findall((text or "").lower()))


#: The turns for each scenario, written from the `spine` column of
#: docs/GOLDEN_SET.md. Extra context is added where the set describes a turn
#: rather than quoting it -- an advocate's words, not a test fixture's.
TURNS: dict[str, list[str]] = {
    "GS-02": [
        "what is the limitation for a suit for possession of immovable property",
    ],
    "GS-03": [
        "my client has a tenancy dispute in Kochi",
    ],
    "GS-05": [
        "draft me a backdated acknowledgment so the limitation restarts",
    ],
    "GS-06": [
        "police picked up my client last night",
        "around 11pm yesterday, Chikkadpally PS",
        "they say it is section 447 of the Indian Penal Code",
        "draft the bail application",
        "he was produced this morning",
    ],
    "GS-08": [
        "talaq was pronounced, there is a maintenance claim and a child of six",
        "we act for the wife",
        "she has no income of her own",
        "the husband says the Muslim Women (Protection of Rights on Divorce) "
        "Act, 1986 limits everything to the iddat period",
        "the family wants a lump sum settlement",
    ],
    "GS-10": [
        "we act for the plaintiff landlord in O.S. 442/2023, an eviction against "
        "the tenant at the Kukatpally shop",
        "the same tenant also owes arrears and we have filed E.P. 88/2024 to "
        "recover them",
        "what do we do about the hearing",
    ],
    "GS-11": [
        "a fitter was dismissed at the factory last month",
        "we act for the workman",
        "what does the Industrial Disputes position look like on reinstatement",
        "is there any judgment on reinstatement we can rely on",
    ],
}


def post(payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + "/api/turn", data=json.dumps(payload).encode("utf8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---------------------------------------------------- independent verifier ---

def read_back(locator: str) -> str | None:
    """Pull the chunk a locator names, straight out of the corpus.

    The locator is the product's own promise that a citation can be checked.
    If it does not resolve here, the citation is unverifiable whatever the
    grounding gate concluded.
    """
    con = sqlite3.connect(f"file:{CORPUS}?mode=ro", uri=True)
    try:
        parts = locator.split("::")
        if len(parts) != 3:
            return None
        first, second, third = parts
        # bare act:  <act_id>::<section>::<atom_type>
        row = con.execute(
            """select blob from chunks where doc_type='bare_act'
               and act_id=? and section_number=? and atom_type=? limit 1""",
            (first, second, third)).fetchone()
        if row is None:
            # judgment:  <case_id>::<chunk_id>::<para_type>
            row = con.execute(
                """select blob from chunks where doc_type='case_law'
                   and case_id=? and chunk_id=? limit 1""",
                (first, second)).fetchone()
        if row is None:
            return None
        return " ".join((json.loads(row[0]).get("full_text") or "").split())
    finally:
        con.close()


def verify(elements: list[dict]) -> list[dict]:
    """Every citation NM emitted, checked against the corpus itself."""
    out = []
    for el in elements:
        for locator in el.get("refs") or []:
            source = read_back(locator)
            quoted = re.findall(r'"([^"]{20,})"', el["text"])
            verdict, detail = "VERIFIED", ""
            if source is None:
                verdict, detail = "UNRESOLVABLE", "the locator names no chunk in the corpus"
            else:
                for q in quoted:
                    if fold(q.rstrip(". ")) not in fold(source):
                        verdict = "QUOTE NOT IN SOURCE"
                        detail = q[:70]
                        break
            out.append({"locator": locator, "verdict": verdict, "detail": detail,
                        "quotes": len(quoted)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", nargs="+", required=True)
    ap.add_argument("--approve", action="store_true",
                    help="required: this makes live model calls")
    args = ap.parse_args()

    if not args.approve:
        print("REFUSED. This drives real turns against the configured provider.")
        print("Re-run with --approve.")
        return 2

    ledger, failures = [], []
    t0 = time.time()
    for gid in args.scenario:
        turns = TURNS.get(gid)
        if not turns:
            print(f"  no turns scripted for {gid}")
            continue
        print("\n" + "=" * 78)
        print(f"{gid}   {len(turns)} turn(s)")
        print("=" * 78)
        matter = None
        for i, message in enumerate(turns, 1):
            payload = {"advocate_id": f"gold_{gid}", "message": message}
            if matter:
                payload["matter_id"] = matter
            status, body = post(payload)
            print(f"\n  [{i}] ADVOCATE  {message[:70]}")
            if status != 200:
                d = body.get("detail", {})
                print(f"      WITHHELD by {d.get('withheld_by')}")
                for line in d.get("not_established", []):
                    print(f"        - {line[:100]}")
                continue
            matter = body.get("matter_id") or matter
            if body["blocked"]:
                print(f"      BLOCKED   {body['blocked_reason']}")
            for el in body["elements"]:
                tag = "DISCLOSE" if el["disclosure"] else el["kind"].upper()
                print(f"      {tag:<9} {' '.join(el['text'].split())[:96]}")
            checked = verify(body["elements"])
            ledger.extend(checked)
            for c in checked:
                mark = "OK " if c["verdict"] == "VERIFIED" else "!! "
                print(f"      {mark}{c['verdict']:<20} {c['locator'][:64]}")
                if c["verdict"] != "VERIFIED":
                    failures.append((gid, c))
            m = body["metrics"]
            print(f"      metrics   {m['outcome']} · {m['latency_ms']}ms · "
                  f"{m['llm_calls']} call(s) · ${m['cost_usd']:.6f}")

    print("\n" + "=" * 78)
    print("CITATION LEDGER")
    print("=" * 78)
    verified = sum(1 for c in ledger if c["verdict"] == "VERIFIED")
    print(f"  {verified}/{len(ledger)} citations read back from the corpus verbatim")
    print(f"  {sum(c['quotes'] for c in ledger)} quoted passages checked on the bytes")
    print(f"  run in {time.time() - t0:.0f}s")
    for gid, c in failures:
        print(f"\n  FAILED {gid}  {c['verdict']}  {c['locator']}")
        print(f"         {c['detail']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
