"""Fetch judgments from Indian Kanoon into a STAGING quarantine. Offline job.

    python tools/fetch_judgments.py --plan              # what it would request
    python tools/fetch_judgments.py --year 2019 --run   # needs a token

WHAT THIS IS FOR
----------------
RG-01 fails: the corpus holds ZERO judgments of the Telangana High Court, which
was constituted on 1 January 2019 and is the binding court for every matter
this product advises on. Seven years of the binding court's own output is
missing, and no amount of code closes that — it needs judgments.

WHAT SURVIVED OF THE PREVIOUS BUILD'S INGESTION, AND WHAT DID NOT
-------------------------------------------------------------------
The module itself is gone. `ingestion/acts_indiankanoon.py` is referenced in
that build's BACKLOG and the directory is not in the tree. What survives is its
CONFIGURATION SURFACE, in `.env.example`, and it is worth reading because the
constraints it encodes were evidently learned:

    AGENTIFIED_NM_IK_MODE=api    # 'api' (official, needs token) or 'web' (ToS-bound scrape)
    INDIANKANOON_API_TOKEN=      # required for api mode (paid token)
    AGENTIFIED_NM_IK_MAX=50      # safety cap: max judgments fetched per staged run
    AGENTIFIED_NM_IK_DELAY=      # seconds between requests (default 1.0 api / 3.0 web)

A capped, delayed, staged fetch behind a paid API — with `web` mode labelled by
its own author as ToS-bound. Those constraints are kept here.

**ONLY API MODE IS IMPLEMENTED.** The scrape path is deliberately absent: the
sanctioned route exists, the previous build flagged the other as ToS-bound, and
a product that advises advocates should not acquire its corpus in a way it
would have to explain. Adding it is a decision to take deliberately, not a
default to inherit.

WHAT THE API CAN AND CANNOT DO — CHECKED AGAINST THE OFFICIAL DOCUMENTATION
----------------------------------------------------------------------------
    POST https://api.indiankanoon.org/search/?formInput=<q>&pagenum=<n>
    POST https://api.indiankanoon.org/doc/<docid>/
    POST https://api.indiankanoon.org/docmeta/<docid>/
    Authorization: Token <token>

    filters: doctypes, fromdate, todate, title, cite, author, bench,
             maxcites (<=50), pagenum, maxpages (<=1000)

**THERE IS NO SORT OR FILTER BY CITATION COUNT.** No `most cited` parameter
exists. `citedbyList` is returned PER DOCUMENT, so "the hundred most cited
judgments of 2019" is not a query — it is the result of enumerating that year
and ranking locally, which is thousands of metered calls per year rather than a
hundred.

The API is metered: "you will be charged for only the number of pages that are
returned". So the shape of the query is a cost decision, and `--plan` exists to
make that visible BEFORE anything is spent.

NOTHING FETCHED ENTERS THE CORPUS
----------------------------------
Everything lands in a staging directory with a manifest recording the query,
the date, the token identity and a hash per document. Promotion into
`legal_database/` is a separate, deliberate step — the previous build's
stage-review-approve, kept, because material acquired automatically is exactly
the material that should not appear in an advocate's answer unreviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".nm" / "staging" / "judgments"

API = "https://api.indiankanoon.org"
#: Indian Kanoon's doctype for the High Court whose output RG-01 is missing.
TELANGANA = "telangana"

DEFAULT_MAX = 50          # the previous build's per-run cap, kept
DEFAULT_DELAY = 1.0       # its api-mode delay, kept


class NoToken(RuntimeError):
    pass


def token() -> str:
    t = (os.environ.get("INDIANKANOON_API_TOKEN") or "").strip()
    if not t:
        raise NoToken(
            "INDIANKANOON_API_TOKEN is not set. The Indian Kanoon API is a paid "
            "service and the token is per-account; there is none in this "
            "repository's .env or the previous build's. Set it and re-run, or "
            "decide deliberately to do something else — this tool does not "
            "implement the unauthenticated scrape.")
    return t


def _post(path: str, params: dict) -> dict:
    body = urllib.parse.urlencode(params).encode("utf8")
    req = urllib.request.Request(
        f"{API}{path}", data=body, method="POST",
        headers={"Authorization": f"Token {token()}",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


# --------------------------------------------------------------------- plan ---

def plan(years: list[int], doctype: str, per_year: int) -> list[dict]:
    """What would be requested, and roughly what it would cost.

    A PLAN IS NOT A DRY RUN OF THE REAL THING -- it makes no call at all. The
    API is metered per page returned, so the first honest thing this tool can
    do is show the shape of the spend before any of it happens.
    """
    rows = []
    for year in years:
        to_month = "08" if year == 2026 else "12"
        to_day = "31" if to_month == "12" else "31"
        rows.append({
            "year": year,
            "doctypes": doctype,
            "fromdate": f"01-01-{year}",
            "todate": f"{to_day}-{to_month}-{year}",
            "wanted": per_year,
            "search_pages": "1 per 10 results, so >= "
                            f"{max(1, per_year // 10)} for a relevance pass",
            "docmeta_calls_for_ranking": "one per candidate — this is the cost "
                                         "driver, and it is why 'most cited' is "
                                         "not a hundred calls",
        })
    return rows


# ------------------------------------------------------------------- fetching ---

def search(query: str, doctype: str, fromdate: str, todate: str,
           pagenum: int) -> dict:
    return _post("/search/", {
        "formInput": query, "doctypes": doctype,
        "fromdate": fromdate, "todate": todate, "pagenum": pagenum})


def docmeta(docid: int) -> dict:
    return _post(f"/docmeta/{docid}/", {})


def document(docid: int) -> dict:
    return _post(f"/doc/{docid}/", {"maxcites": 50})


def stage(year: int, docs: list[dict], query: str, doctype: str) -> Path:
    """Write to quarantine with a manifest. NOTHING enters the corpus here."""
    out = STAGING / str(year)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for d in docs:
        raw = json.dumps(d, ensure_ascii=False, indent=1)
        digest = hashlib.sha256(raw.encode("utf8")).hexdigest()[:16]
        name = f"IK_{year}_{d.get('tid') or d.get('docid')}_{digest}.json"
        (out / name).write_text(raw, encoding="utf8")
        manifest.append({
            "file": name, "docid": d.get("tid") or d.get("docid"),
            "title": d.get("title"), "sha256_16": digest,
            "citedby": len(d.get("citedbyList") or []),
        })
    (out / "_manifest.json").write_text(json.dumps({
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "api.indiankanoon.org",
        "query": query, "doctypes": doctype, "year": year,
        "documents": len(manifest),
        "promoted": False,
        "note": "STAGED, NOT INGESTED. Promotion into legal_database is a "
                "separate deliberate step.",
        "items": manifest,
    }, indent=2), encoding="utf8")
    return out


def run(year: int, doctype: str, want: int, cap: int, delay: float,
        query: str) -> int:
    """Fetch one year, ranked by cited-by, within the cap.

    Ranking is LOCAL because the API offers no citation sort. Every candidate
    costs a metered call, so the cap is a real limit and not a formality.
    """
    to_month_day = "31-08" if year == 2026 else "31-12"
    fromdate, todate = f"01-01-{year}", f"{to_month_day}-{year}"

    candidates: list[dict] = []
    page = 0
    while len(candidates) < cap:
        res = search(query, doctype, fromdate, todate, page)
        docs = res.get("docs") or []
        if not docs:
            break
        candidates.extend(docs)
        page += 1
        time.sleep(delay)

    candidates = candidates[:cap]
    enriched = []
    for d in candidates:
        docid = d.get("tid") or d.get("docid")
        if docid is None:
            continue
        try:
            enriched.append(document(int(docid)))
        except urllib.error.HTTPError as exc:
            print(f"    ! {docid}: HTTP {exc.code}", file=sys.stderr)
        time.sleep(delay)

    enriched.sort(key=lambda d: len(d.get("citedbyList") or []), reverse=True)
    kept = enriched[:want]
    out = stage(year, kept, query, doctype)
    print(f"  {year}: {len(kept)} staged (from {len(candidates)} candidates) -> {out}")
    return len(kept)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true",
                    help="show what would be requested; makes NO call")
    ap.add_argument("--run", action="store_true", help="actually fetch")
    ap.add_argument("--year", type=int, action="append")
    ap.add_argument("--doctype", default=TELANGANA)
    ap.add_argument("--query", default="",
                    help="base search text; empty means the whole period")
    ap.add_argument("--per-year", type=int, default=100)
    ap.add_argument("--cap", type=int, default=DEFAULT_MAX,
                    help="candidates examined per year; each costs a metered call")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    args = ap.parse_args()

    years = args.year or list(range(2019, 2027))

    if args.plan or not args.run:
        rows = plan(years, args.doctype, args.per_year)
        print("=" * 76)
        print("PLAN — no call is made by this command")
        print("=" * 76)
        for r in rows:
            print(f"  {r['year']}  doctypes={r['doctypes']}  "
                  f"{r['fromdate']} .. {r['todate']}  want={r['wanted']}")
        print()
        print("  THE API HAS NO CITATION SORT. `citedbyList` comes back per")
        print("  document, so ranking by 'most cited' means examining every")
        print("  candidate in the year — each a metered call — and ranking")
        print("  locally. `--cap` bounds that, and the top `--per-year` of what")
        print("  was examined is what gets staged.")
        print()
        print(f"  cap per year   {args.cap}")
        print(f"  years          {len(years)}")
        print(f"  metered calls  ~{len(years) * (args.cap + max(1, args.cap // 10))}"
              f"  (search pages + one document call per candidate)")
        print()
        try:
            token()
            print("  token         SET")
        except NoToken as exc:
            print(f"  token         NOT SET\n\n  {exc}")
            return 2
        print("\n  Re-run with --run to fetch.")
        return 0

    token()
    total = 0
    for year in years:
        total += run(year, args.doctype, args.per_year, args.cap, args.delay,
                     args.query)
    print(f"\n  {total} judgments staged in {STAGING}")
    print("  NOTHING HAS ENTERED THE CORPUS. Review the staged manifests, then "
          "promote deliberately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
