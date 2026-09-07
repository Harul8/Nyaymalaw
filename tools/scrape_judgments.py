"""Fetch judgments from indiankanoon.org's WEB pages. Offline job, ToS-bound.

    python tools/scrape_judgments.py --plan
    python tools/scrape_judgments.py --run --from-year 2018 --to-year 2026 \
        --pages-per-year 15 --min-cited-by 2

THIS REVERSES A DECISION THIS REPOSITORY HAD ALREADY TAKEN
------------------------------------------------------------
`tools/fetch_judgments.py` says, in terms:

    ONLY API MODE IS IMPLEMENTED. The scrape path is deliberately absent: the
    sanctioned route exists, the previous build flagged the other as ToS-bound,
    and a product that advises advocates should not acquire its corpus in a way
    it would have to explain.

The advocate was shown that and asked for the scraper anyway on 7 September
2026, **as a one-time exception** -- their words. That is their call to make
about their own product.

SO THE POLICY IN `fetch_judgments.py` STILL STANDS. This is not the new
default and it is not permission for the next acquisition to take the same
route. A one-time exception that quietly becomes the normal way is how a
product ends up acquiring its corpus in a way it would have to explain --
which is the sentence the original decision was written to avoid.

The reasoning above is therefore not deleted, and BK-23 records the exception
with its date and its scope: 2018-2026, Telangana, cited by two or more, one
run.

WHAT IS NOT NEGOTIABLE, HAVING TAKEN THAT DECISION
----------------------------------------------------
If this runs at all it runs like a good citizen, and every one of these is a
refusal rather than a setting nobody looks at:

  * `robots.txt` IS READ AND OBEYED, every run, before anything else. If it
    disallows the search path this exits and fetches nothing. It is not a flag
    and there is no override.
  * THREE SECONDS between requests, which is the delay the previous build's own
    `AGENTIFIED_NM_IK_DELAY` specified for web mode.
  * A REAL User-Agent naming the project and a contact. A scraper that hides
    what it is cannot be asked to stop, which is the only thing that makes it
    answerable.
  * ONE REQUEST AT A TIME. No concurrency, ever.
  * A HARD CAP on total requests, so a bug cannot turn a bounded job into an
    unbounded one.

WHAT IT COSTS, WHICH IS THE PART TO READ BEFORE `--run`
---------------------------------------------------------
"Cited by 2 or more" IS NOT A SEARCH FILTER on Indian Kanoon, on the web or in
the API -- `tools/fetch_judgments.py` records that, checked against the
official documentation. The citation count lives on the DOCUMENT, so it can
only be learned by opening each result.

    9 years x 15 pages       =    135 search pages
    ~10 results per page     = ~1,350 documents to open
    at 3s apart              = ~75 minutes of sustained requests

`--plan` prints that arithmetic and makes no request at all. Read it first.

NOTHING FETCHED ENTERS THE CORPUS
-----------------------------------
Everything lands in the same staging quarantine `fetch_judgments.py` uses, with
a manifest recording the query, the date and a hash per document. Promotion
into `legal_database/` is a separate, deliberate step -- material acquired
automatically is exactly the material that must not reach an advocate's answer
unreviewed.

AND IT IS NOT RUN FOR YOU
---------------------------
Long jobs are started by the advocate, never by the product or by an assistant
on its behalf. This prints what it would do and stops unless `--run` is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
from tools._console import utf8_console  # noqa: E402

utf8_console()

SITE = "https://indiankanoon.org"
SEARCH = "/search/"
STAGING = ROOT / ".nm" / "staging" / "judgments"

#: The previous build's own web-mode delay, kept. Not a tuning knob.
DELAY = 3.0

#: A scraper that will not say what it is cannot be asked to stop.
UA = ("Nyaymalaw/0.1 (legal research corpus for Telangana practice; "
      "+https://github.com/Harul8/Nyaymalaw)")

#: A bug must not turn a bounded job into an unbounded one.
HARD_CAP = 3000

DOCTYPE = "telangana"


class Refused(RuntimeError):
    """Raised where continuing would be the wrong thing, not merely a failure."""


# ----------------------------------------------------------------- courtesy ---

def robots_allows(path: str) -> tuple[bool, str]:
    """Whether `robots.txt` permits this path for this User-Agent.

    READ EVERY RUN, not cached and not assumed. A site's answer to *may I* can
    change between Tuesday and Wednesday, and a scraper that asked once is a
    scraper that stopped asking.

    A ROBOTS FILE THAT CANNOT BE READ IS A REFUSAL, not a permission. The
    whole point of the file is that silence is not consent -- treating an
    unreachable one as "go ahead" inverts it, and is the S1 shape applied to
    somebody else's server.
    """
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{SITE}/robots.txt")
    try:
        rp.read()
    except Exception as exc:                                  # noqa: BLE001
        return False, (f"robots.txt could not be read ({type(exc).__name__}: "
                       f"{exc}). That is a refusal, not a permission: the "
                       f"file exists so silence is not consent.")
    if rp.can_fetch(UA, f"{SITE}{path}"):
        return True, "robots.txt permits this path"
    return False, (f"robots.txt DISALLOWS {path} for this User-Agent. "
                   f"There is no override and there should not be one.")


def _get(url: str, budget: dict) -> str:
    """One request, counted, delayed, and identified."""
    if budget["spent"] >= budget["cap"]:
        raise Refused(
            f"the request cap of {budget['cap']} was reached. Raise it "
            f"deliberately or narrow the job; a cap that is edited away the "
            f"first time it fires is not a cap.")
    budget["spent"] += 1
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf8", errors="replace")
    time.sleep(DELAY)
    return body


# ------------------------------------------------------------------ parsing ---

#: A result link on the search page: /doc/<id>/
_DOC = re.compile(r'href="/doc/(\d+)/"')

#: "Cited by 7 documents" on a document page. The count is the WHOLE POINT of
#: this job and it is the one thing the search page does not carry, which is
#: why every candidate has to be opened.
_CITEDBY = re.compile(r"Cited by\s+(\d+)\s+doc", re.I)

_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def result_ids(html: str) -> list[str]:
    """Document ids on one search page, in order, without duplicates."""
    return list(dict.fromkeys(_DOC.findall(html)))


def cited_by(html: str) -> int | None:
    """How many documents cite this one, or None if the page does not say.

    NONE IS NOT ZERO. A page whose citation line is missing or has moved is a
    page this could not read -- and filtering it out as "cited by 0" would
    silently drop exactly the judgments a parser change had blinded us to.
    """
    m = _CITEDBY.search(html)
    return int(m.group(1)) if m else None


def title_of(html: str) -> str:
    m = _TITLE.search(html)
    return " ".join(m.group(1).split()) if m else ""


# --------------------------------------------------------------------- plan ---

def plan(years: list[int], pages: int, min_cited: int) -> None:
    searches = len(years) * pages
    docs = searches * 10
    seconds = (searches + docs) * DELAY
    print()
    print("  PLAN — no request is made by this command.")
    print()
    print(f"    years                 {years[0]}–{years[-1]} ({len(years)})")
    print(f"    pages per year        {pages}")
    print(f"    search requests       {searches}")
    print(f"    documents to open     ~{docs}  (~10 results per page)")
    print(f"    keep where cited by   >= {min_cited}")
    print(f"    delay between calls   {DELAY}s")
    print(f"    total requests        ~{searches + docs}"
          f"  (cap {HARD_CAP})")
    print(f"    wall time             ~{seconds / 60:.0f} minutes of sustained")
    print("                          requests to someone else's server")
    print()
    print("  EVERY DOCUMENT MUST BE OPENED. 'Cited by N' is not a search")
    print("  filter on Indian Kanoon — the count lives on the document, so the")
    print("  filter cannot be pushed to the server. That is the cost driver,")
    print("  and it is the same on the paid API.")
    print()
    if searches + docs > HARD_CAP:
        print(f"  THIS EXCEEDS THE CAP OF {HARD_CAP} AND WOULD STOP PART WAY.")
        print("  Narrow the years or the pages, or raise the cap knowingly.")
        print()


# ------------------------------------------------------------------ running ---

def run(years: list[int], pages: int, min_cited: int, cap: int) -> int:
    allowed, why = robots_allows(SEARCH)
    print(f"  robots.txt: {why}")
    if not allowed:
        print()
        print("  NOTHING WAS FETCHED.")
        return 2

    budget = {"spent": 0, "cap": cap}
    kept_total = 0

    for year in years:
        seen: list[str] = []
        for page in range(pages):
            q = urllib.parse.urlencode({
                "formInput": f"doctypes: {DOCTYPE} year: {year}",
                "pagenum": page})
            try:
                html = _get(f"{SITE}{SEARCH}?{q}", budget)
            except Refused as exc:
                print(f"  stopped: {exc}")
                return 1
            except urllib.error.HTTPError as exc:
                print(f"  {year} page {page}: HTTP {exc.code} — stopping this "
                      f"year rather than retrying into a rate limit")
                break
            ids = result_ids(html)
            if not ids:
                print(f"  {year} page {page}: no results — end of this year")
                break
            seen.extend(i for i in ids if i not in seen)

        print(f"  {year}: {len(seen)} candidate(s) from "
              f"{min(pages, len(seen) // 10 + 1)} page(s)")

        kept: list[dict] = []
        unreadable = 0
        for docid in seen:
            try:
                page_html = _get(f"{SITE}/doc/{docid}/", budget)
            except Refused as exc:
                print(f"  stopped: {exc}")
                break
            except urllib.error.HTTPError as exc:
                print(f"    doc {docid}: HTTP {exc.code}, skipped")
                continue
            n = cited_by(page_html)
            if n is None:
                # SAID, NOT SWALLOWED. A page this could not read is not a
                # page with no citations, and reporting it as one would hide a
                # parser that had stopped working.
                unreadable += 1
                continue
            if n < min_cited:
                continue
            kept.append({
                "docid": docid, "year": year, "citedby": n,
                "title": title_of(page_html), "html": page_html,
                "source": f"{SITE}/doc/{docid}/",
            })

        if unreadable:
            print(f"    {unreadable} document(s) did not state a citation "
                  f"count — NOT counted as zero, and NOT kept. If this is "
                  f"large the page format has changed and `_CITEDBY` needs "
                  f"looking at.")
        if kept:
            where = stage(year, kept, min_cited)
            kept_total += len(kept)
            print(f"    kept {len(kept)} cited by >= {min_cited} -> {where}")
        else:
            print(f"    kept 0 cited by >= {min_cited}")

    print()
    print(f"  {kept_total} judgment(s) staged, {budget['spent']} request(s) "
          f"made.")
    print("  NOTHING HAS ENTERED THE CORPUS. Promotion out of "
          f"{STAGING.relative_to(ROOT)} is a separate, deliberate step.")
    return 0


def stage(year: int, docs: list[dict], min_cited: int) -> Path:
    """Quarantine with a manifest. The same shape `fetch_judgments.py` uses."""
    out = STAGING / str(year)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for d in docs:
        raw = json.dumps(d, ensure_ascii=False, indent=1)
        digest = hashlib.sha256(raw.encode("utf8")).hexdigest()[:16]
        name = f"IKWEB_{year}_{d['docid']}_{digest}.json"
        (out / name).write_text(raw, encoding="utf8")
        manifest.append({
            "file": name, "docid": d["docid"], "title": d["title"],
            "citedby": d["citedby"], "sha256_16": digest,
            "source": d["source"],
        })
    (out / "manifest.json").write_text(json.dumps({
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "route": "web scrape of indiankanoon.org",
        "user_agent": UA,
        "delay_seconds": DELAY,
        "doctype": DOCTYPE,
        "year": year,
        "min_cited_by": min_cited,
        "documents": manifest,
        # WHY THIS IS RECORDED IN THE ARTEFACT ITSELF: six months from now the
        # question about any of these files will be "where did this come
        # from", and an answer that lives only in a commit message is an
        # answer nobody finds. S11's rule for derived artefacts.
        "note": ("Acquired by web scrape, not the sanctioned API. This route "
                 "was deliberately excluded by tools/fetch_judgments.py and "
                 "reinstated on the advocate's instruction on 2026-09-07 — "
                 "see BK-23."),
    }, ensure_ascii=False, indent=2), encoding="utf8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true",
                    help="print the request count and cost; fetch nothing")
    ap.add_argument("--run", action="store_true", help="actually fetch")
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2026)
    ap.add_argument("--pages-per-year", type=int, default=15)
    ap.add_argument("--min-cited-by", type=int, default=2)
    ap.add_argument("--cap", type=int, default=HARD_CAP,
                    help="hard ceiling on total requests")
    args = ap.parse_args()

    years = list(range(args.from_year, args.to_year + 1))
    plan(years, args.pages_per_year, args.min_cited_by)

    if not args.run:
        print("  Re-run with --run to fetch. This is a long job and it is "
              "started by you, not by the product.")
        return 0

    return run(years, args.pages_per_year, args.min_cited_by, args.cap)


if __name__ == "__main__":
    raise SystemExit(main())
