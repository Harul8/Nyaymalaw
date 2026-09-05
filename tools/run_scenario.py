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
import http.cookiejar
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._console import utf8_console  # noqa: E402

utf8_console()

from nm.domain.identity import source_fingerprint  # noqa: E402

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
    "GS-09": [
        "our client runs a small fabrication unit and he has five things "
        "running at once. First, a cheque he drew for 4 lakhs bounced and the "
        "payee has filed a complaint against him.",
        "second, a fitter he dismissed has gone to the Labour Court and our "
        "client is the respondent employer there",
        "third, he is a tenant at the Kukatpally shop and the landlord has "
        "issued a quit notice; we are resisting the eviction",
        "fourth, he was assaulted by a supplier outside the unit in June and "
        "he is the complainant in that",
        "fifth, he has filed his own recovery suit against a customer who owes "
        "him 11 lakhs. Where does each of these stand?",
    ],
    "GS-12": [
        "a neighbour grabbed my client's land and beat him up badly yesterday, "
        "injuring his knee",
        "we want to file a title suit over the strip of land. What is the "
        "limitation for that, and is there anything under the Specific Relief "
        "Act we should be looking at first?",
        "actually he says the neighbour has been encroaching since 2019",
        "no, hold on. The wall is new, put up yesterday. The 2019 encroachment "
        "was a different strip on the other side.",
        "what do we need to prove",
    ],
    "GS-13": [
        "a cheque our client received bounced on 3 March and we sent the "
        "statutory notice",
        "the notice went on 15 April. We act for the payee.",
        "what is the position under section 138 of the Negotiable Instruments "
        "Act",
        "can we still do something about the money",
        "there is a second cheque from the same drawer that bounced on 2 "
        "August, notice not yet sent",
    ],
    # A CUSTODY CLOCK THAT IS ARITHMETIC, NOT NARRATION. The default-bail
    # entitlement is a computed date, and "no escort was available" is not a
    # ground the statute gives.
    "GS-07": [
        "our client was remanded on 12 June 2026 and the magistrate has kept "
        "extending it. We act for the accused.",
        "the charge is an offence punishable with imprisonment up to seven "
        "years and the investigation is still not complete",
        "the last two extensions were because no police escort was available "
        "to produce him",
        "where does that leave us on default bail under section 167(2)",
    ],
    # THE MEASURED DEFECT, and the reason D2's coverage record exists. The debt
    # looks dead on the invoices; a written acknowledgment sits in the
    # chronology, is repeated back, and must reach the arithmetic.
    "GS-14": [
        "we act for the plaintiff in a recovery matter. The goods were "
        "supplied against invoices dated 14 March 2023 and nothing was paid.",
        "the defendant wrote to us on 12 June 2024 admitting the amount was "
        "outstanding and asking for time",
        "is the claim still in time",
        "what does that letter have to say for it to count",
    ],
    # THE DATE CORRECTED MID-CONVERSATION. Everything computed off the first
    # date has to be re-derived and the earlier position marked superseded.
    "GS-15": [
        "we act for the plaintiff on an agreement of sale. What is the "
        "limitation for specific performance?",
        "the agreement is dated 15-4-1984",
        "sorry, that is wrong. It is dated 15-4-2024.",
        "the agreement was never registered",
        "so where do we stand now",
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


def server_fingerprint() -> tuple[str | None, str]:
    """What code the SERVED PROCESS loaded, asked of the process itself.

    Three states, and the middle one is why this returns a pair. `None` is
    "could not be established" -- the server is down, too old to carry the
    field, or answering something else -- and it is not the same as a
    fingerprint that differs. Returning a sentinel string for both would make
    an unreachable server compare unequal and read as a stale one, which sends
    the reader to restart a process that is not running.
    """
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=10) as r:
            doc = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001 -- any failure is "not established"
        return None, f"{type(exc).__name__}: {exc}"
    fp = doc.get("serving")
    if not isinstance(fp, str) or not fp or fp.startswith("unknown"):
        return None, (f"the server reports serving={fp!r}. A process that "
                      f"cannot say what it loaded cannot be trusted to be "
                      f"current.")
    return fp, "ok"


#: THE SESSION, CARRIED. A1 moved the advocate off the request and onto a
#: cookie the server issues, so a runner that posts JSON and forgets the jar
#: gets 401 on every turn -- after the fingerprint check has already passed,
#: which is the moment in the run where everything looks ready to go.
_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_JAR))


def _call(path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf8") if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET")
    try:
        with _OPENER.open(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:  # noqa: BLE001 -- a non-JSON error page
            return e.code, {}


def sign_in(advocate_id: str, password: str) -> tuple[bool, str]:
    """Enrol if needed, then authenticate. Returns whether the session is live.

    ENROLMENT IS DONE HERE AND NOT BY HAND because a scenario advocate is a
    test fixture, not a person: it exists for the length of a run and its
    password comes from the environment so nothing is chosen in this file.
    """
    status, body = _call("/api/login",
                         {"advocate_id": advocate_id, "password": password})
    if status == 200:
        return True, "signed in"
    return False, str(body.get("detail") or f"HTTP {status}")


def post(payload: dict) -> tuple[int, dict]:
    """One turn. The advocate is NOT in the payload any more -- it comes from
    the session, and there is no field left to override it with."""
    return _call("/api/turn", payload)


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

    # ---- WHAT CODE IS THE SERVER RUNNING? ------------------------------
    #
    # Measured on 31 August 2026: this ran five scenarios against a server
    # started the previous evening, made live model calls, found none of the
    # slice it existed to prove, and EXITED 0. Every element it printed was
    # about code that had been superseded that morning.
    #
    # A run that measured the wrong code must not be distinguishable only by
    # someone noticing the output looks thin. It is refused here, before a
    # single paid call.
    serving, why = server_fingerprint()
    mine = source_fingerprint()
    if serving is None:
        print(f"REFUSED. The server at {BASE} could not be asked what code it "
              f"is running: {why}")
        print("This run would cost money and prove nothing. Start the server, "
              "or fix the health endpoint.")
        return 2
    if serving != mine:
        print(f"REFUSED. The server at {BASE} is running DIFFERENT CODE.")
        print(f"    serving:      {serving}")
        print(f"    working tree: {mine}")
        print()
        print("  Restart it and run again. On Windows `pkill` does not exist "
              "and a failed kill is silent, so use:")
        print("    Get-CimInstance Win32_Process -Filter \"Name like "
              "'%python%'\" | Where-Object { $_.CommandLine -match '8078' } "
              "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        return 2

    # ---- AND WHO IS RUNNING IT ----------------------------------------
    #
    # Refused BEFORE any paid call, for the same reason the fingerprint is:
    # a run that cannot authenticate produces five 401s and an empty report,
    # which reads exactly like a product that answered nothing.
    advocate = os.environ.get("NM_SCENARIO_ADVOCATE", "adv_scenarios")
    password = os.environ.get("NM_SCENARIO_PASSWORD", "")
    if not password:
        print("REFUSED. Set NM_SCENARIO_PASSWORD to the password of the "
              "scenario advocate.")
        print(f"  Enrol one first:  python tools/enrol.py --id {advocate} "
              f"--name 'Scenario runner' --enrolment 'AP/0000/2000' "
              f"--practice Hyderabad --firm firm_scenarios")
        return 2
    ok, why = sign_in(advocate, password)
    if not ok:
        print(f"REFUSED. Could not sign in as {advocate}: {why}")
        print("  This run would cost money and prove nothing.")
        return 2

    # ---- EVERY NAMED SCENARIO MUST BE RUNNABLE -------------------------
    #
    # `continue` on a scenario with no scripted turns is the same defect: the
    # caller named five, three had no turns, and the run reported success. A
    # scenario that could not run must never read as one that passed.
    incomplete: list[tuple[str, int, int]] = []
    unscripted = [g for g in args.scenario if not TURNS.get(g)]
    if unscripted:
        print(f"REFUSED. {len(unscripted)} named scenario(s) have no scripted "
              f"turns: {', '.join(unscripted)}")
        print("They exist in docs/GOLDEN_SET.md and cannot be driven from "
              "here, so naming them proves nothing. Script them in TURNS, or "
              "do not name them.")
        return 2

    ledger, failures = [], []
    t0 = time.time()
    for gid in args.scenario:
        turns = TURNS[gid]
        print("\n" + "=" * 78)
        print(f"{gid}   {len(turns)} turn(s)")
        print("=" * 78)
        matter = None
        withheld_at = None
        for i, message in enumerate(turns, 1):
            payload = {"message": message}
            if matter:
                payload["matter_id"] = matter
            status, body = post(payload)
            print(f"\n  [{i}] ADVOCATE  {message[:70]}")
            if status != 200:
                d = body.get("detail", {})
                print(f"      WITHHELD by {d.get('withheld_by')}")
                for line in d.get("not_established", []):
                    print(f"        - {line[:100]}")

                # THE SCENARIO STOPS HERE, and this used to `continue`.
                #
                # A withheld turn commits nothing, so it returns no matter id
                # — and the loop carried on with `matter` still None, opening
                # a FRESH MATTER on every remaining turn. Five turns ran, four
                # of them on files that had never been briefed, each blocking
                # on a posture nobody had stated, and the run printed a
                # transcript that looked like a product refusing to answer.
                #
                # Measured on GS-15, 4 September 2026: turn 1 was withheld and
                # the whole cascade the scenario exists to prove never ran, at
                # full price. A run that measured nothing must not be
                # distinguishable only by someone noticing the output looks
                # thin — that is B-061 with a different cause.
                if matter is None:
                    print()
                    print("      STOPPING THIS SCENARIO. The turn that opens "
                          "the matter was withheld, so there is no file for "
                          "the remaining turns to be about. Continuing would "
                          "open a fresh matter on each and measure nothing.")
                    withheld_at = i
                    break
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

        if withheld_at is not None:
            # AN INCOMPLETE RUN IS A FAILED RUN, and it exits non-zero.
            # A scenario that stopped at turn 1 and then printed a clean
            # citation ledger is the shape this whole tool exists to
            # refuse: a run that measured nothing, reporting success.
            incomplete.append((gid, withheld_at, len(turns)))

    if incomplete:
        print("\n" + "=" * 78)
        print("SCENARIOS THAT DID NOT FINISH")
        print("=" * 78)
        for gid, at, total in incomplete:
            print(f"  {gid}: stopped at turn {at} of {total} — the turn that "
                  f"opens the matter was withheld, so nothing after it was "
                  f"measured.")

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
    return 1 if (failures or incomplete) else 0


if __name__ == "__main__":
    raise SystemExit(main())
