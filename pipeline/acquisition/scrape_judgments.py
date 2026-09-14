"""Fetch judgments from indiankanoon.org's WEB pages. Offline job, ToS-bound.

    python pipeline/acquisition/scrape_judgments.py --plan
    python pipeline/acquisition/scrape_judgments.py --run --from-year 2018 --to-year 2026 \
        --pages-per-year 15 --min-cited-by 2

THIS REVERSES A DECISION THIS REPOSITORY HAD ALREADY TAKEN
------------------------------------------------------------
`pipeline/acquisition/fetch_judgments.py` says, in terms:

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
the API -- `pipeline/acquisition/fetch_judgments.py` records that, checked against the
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
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "backend"))
from nm.knowledge.acquisition import (  # noqa: E402
    AcquiredArtifact,
    AcquisitionRoute,
    AcquisitionScope,
    JudgmentCandidate,
    SelectionState,
    acquisition_dates,
    select_candidates,
    stage_acquisition,
)
from nm.knowledge.source_registry import RightsState  # noqa: E402

from assurance.common._console import utf8_console  # noqa: E402

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

#: THE BENCH THIS SCRAPE WAS APPROVED FOR. `DOCTYPE` above is the
#: jurisdiction, and the two are not the same permission.
ISSUING_BODY = "High Court for the State of Telangana"


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
    # FETCHED WITH OUR OWN User-Agent, and this is not a detail.
    #
    # `RobotFileParser.read()` fetches with urllib's default UA, Indian
    # Kanoon answers that with 403, and the parser turns a 403 into
    # `disallow_all = True`. The first run of this tool reported
    # *robots.txt DISALLOWS /search/* and fetched nothing -- on a file it
    # had never read. The site permits /search/ for `*`.
    #
    # A crawler that will not identify itself when ASKING PERMISSION is not
    # entitled to the answer. So the file is fetched the same way every
    # other request is made, and parsed from the bytes.
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{SITE}/robots.txt")
    try:
        req = urllib.request.Request(f"{SITE}/robots.txt",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status in (401, 403):
                # THE ONE CASE THAT REALLY IS A REFUSAL. Per the standard, a
                # robots.txt behind an authorisation failure means the whole
                # site is disallowed -- and here it is read from the STATUS
                # rather than inferred from an exception.
                return False, (f"robots.txt returned HTTP {r.status}, which the "
                               f"standard makes a refusal for the whole site.")
            rp.parse(r.read().decode("utf8", errors="replace").splitlines())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, (f"robots.txt returned HTTP {exc.code}, which the "
                           f"standard makes a refusal for the whole site.")
        return False, (f"robots.txt could not be read (HTTP {exc.code}). "
                       f"That is a refusal, not a permission: the file "
                       f"exists so silence is not consent.")
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

#: HOW MANY DOCUMENTS CITE THIS ONE. The count is the whole point of this
#: job, and the search page does not carry it -- which is why every
#: candidate has to be opened.
#:
#: IT IS NOT PROSE. The first version looked for "Cited by 7 documents" and
#: matched nothing on any of ten real pages -- correctly reported as ten
#: documents that DID NOT STATE a count rather than ten with zero, which is
#: the distinction that made the failure visible in one line instead of
#: producing a confident empty result.
#:
#: The real shape is a link: `citedby:86420904">276`. Note the neighbouring
#: `cites:<id>">N`, which is the OPPOSITE relation -- how many this one
#: cites -- and would silently give the wrong number to anything matching on
#: `cite` loosely.
_CITEDBY = re.compile(r'citedby:\d+"[^>]*>\s*(\d+)')

_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
_ISO_DATE = re.compile(
    r'(?:date|published)[^>]{0,120}(\d{4}-\d{2}-\d{2})', re.I,
)
_PROSE_DATE = re.compile(
    r"\bon\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", re.I,
)


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


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def source_date(html: str) -> date | None:
    """Read a stated page date; the search cohort is not an invented day."""
    for expression, pattern in (
        (_ISO_DATE, "%Y-%m-%d"),
        (_PROSE_DATE, "%d %B %Y"),
    ):
        found = expression.search(html)
        if found:
            try:
                return datetime.strptime(found.group(1), pattern).date()
            except ValueError:
                continue
    return None


def candidate(docid: str, html: str, citation_count: int | None,
              *, readable: bool = True) -> JudgmentCandidate:
    return JudgmentCandidate(
        candidate_id=docid,
        source="indiankanoon.org",
        jurisdiction=DOCTYPE,
        issuing_body=ISSUING_BODY,
        document_type=DOCTYPE,
        source_url=f"{SITE}/doc/{docid}/",
        source_date=source_date(html),
        citation_count=citation_count,
        readable=readable,
    )


# --------------------------------------------------------------------- plan ---

def plan(years: list[int], pages: int, legacy_min_cited: int, *,
         from_date: date | None = None, to_date: date | None = None) -> None:
    if not years:
        raise ValueError("acquisition needs a non-empty year population")
    intervals = [acquisition_dates(year, from_date=from_date, to_date=to_date)
                 for year in years]
    searches = len(years) * pages
    docs = searches * 10
    seconds = (searches + docs) * DELAY
    print()
    print("  PLAN — no request is made by this command.")
    print()
    print(f"    years                 {years[0]}–{years[-1]} ({len(years)})")
    print(f"    source dates          {intervals[0][0]} through {intervals[-1][1]}")
    print(f"    pages per year        {pages}")
    print(f"    search requests       {searches}")
    print(f"    documents to open     ~{docs}  (~10 results per page)")
    print(f"    legacy cited-by input {legacy_min_cited} (recorded, not an eligibility gate)")
    print(f"    delay between calls   {DELAY}s")
    print(f"    total requests        ~{searches + docs}"
          f"  (cap {HARD_CAP})")
    print(f"    wall time             ~{seconds / 60:.0f} minutes of sustained")
    print("                          requests to someone else's server")
    print()
    print("  EVERY DOCUMENT MUST BE OPENED. 'Cited by N' is not a search")
    print("  filter on Indian Kanoon. Citation count may prioritise only inside")
    print("  one eligible source-year cohort; it does not decide eligibility.")
    print()
    if searches + docs > HARD_CAP:
        print(f"  THIS EXCEEDS THE CAP OF {HARD_CAP} AND WOULD STOP PART WAY.")
        print("  Narrow the years or the pages, or raise the cap knowingly.")
        print()


# ------------------------------------------------------------------ running ---

def run(years: list[int], pages: int, legacy_min_cited: int, cap: int,
        selection_budget: int, authorization_id: str, *,
        source_rights: RightsState = RightsState.UNKNOWN,
        from_date: date | None = None, to_date: date | None = None) -> int:
    if not years:
        raise ValueError("acquisition needs a non-empty year population")
    intervals = {year: acquisition_dates(year, from_date=from_date, to_date=to_date)
                 for year in years}
    allowed, why = robots_allows(SEARCH)
    print(f"  robots.txt: {why}")
    if not allowed:
        print()
        print("  NOTHING WAS FETCHED.")
        return 2

    budget = {"spent": 0, "cap": cap}
    kept_total = 0

    for year in years:
        start, end = intervals[year]
        seen: list[str] = []
        for page in range(pages):
            q = urllib.parse.urlencode({
                "formInput": (f"doctypes: {DOCTYPE} year: {year} "
                              f"fromdate: {start:%d-%m-%Y} todate: {end:%d-%m-%Y}"),
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

        observed: list[JudgmentCandidate] = []
        documents: dict[str, str] = {}
        for docid in seen:
            try:
                page_html = _get(f"{SITE}/doc/{docid}/", budget)
            except Refused as exc:
                print(f"  stopped: {exc}")
                return 1
            except urllib.error.HTTPError as exc:
                print(f"    doc {docid}: HTTP {exc.code}, skipped")
                observed.append(candidate(docid, "", None, readable=False))
                continue
            n = cited_by(page_html)
            observed.append(candidate(docid, page_html, n))
            documents[docid] = page_html

        scope = AcquisitionScope(
            route=AcquisitionRoute.WEB,
            source="indiankanoon.org",
            jurisdiction=DOCTYPE,
            document_types=(DOCTYPE,),
            from_date=start,
            to_date=end,
            discovery_budget=cap,
            selection_budget=min(selection_budget, cap),
            authorization_id=authorization_id,
            issuing_bodies=(ISSUING_BODY,),
            source_rights=source_rights,
        )
        selection = select_candidates(scope, observed)
        by_id: dict[str, JudgmentCandidate] = {}
        for row in observed:
            by_id.setdefault(row.candidate_id, row)
        artifacts = [
            AcquiredArtifact(
                candidate_id,
                by_id[candidate_id].canonical_source_id,
                by_id[candidate_id].source_url,
                documents[candidate_id].encode("utf8"),
            )
            for candidate_id in selection.selected_ids
        ]
        run_id = (
            f"web-{year}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        )
        where = stage_acquisition(
            STAGING, run_id=run_id, scope=scope, selection=selection,
            artifacts=artifacts, observed_at=datetime.now(timezone.utc),
        )
        selected = selection.count(SelectionState.SELECTED)
        unresolved = selection.count(SelectionState.UNRESOLVED)
        rejected = selection.count(SelectionState.REJECTED)
        kept_total += selected
        print(f"    {selected} staged, {unresolved} unresolved, {rejected} "
              f"rejected; legacy min-cited {legacy_min_cited} did not filter -> "
              f"{where}")

    print()
    print(f"  {kept_total} judgment(s) staged, {budget['spent']} request(s) "
          f"made.")
    print("  NOTHING HAS ENTERED THE CORPUS. Promotion out of "
          f"{display_path(STAGING)} is a separate, deliberate step.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true",
                    help="print the request count and cost; fetch nothing")
    ap.add_argument("--run", action="store_true", help="actually fetch")
    ap.add_argument("--authorization-id",
                    help="approval record for this exact web scope and run")
    ap.add_argument("--source-rights", default="unknown",
                    choices=[s.value for s in RightsState],
                    help="the REVIEWED right to take from this source. "
                         "`unknown` is refused: an authorisation id is a "
                         "reference to a decision, not the decision.")
    ap.add_argument("--from-year", type=int)
    ap.add_argument("--to-year", type=int)
    ap.add_argument("--from-date", type=date.fromisoformat,
                    help="inclusive approved source-date lower bound, YYYY-MM-DD")
    ap.add_argument("--to-date", type=date.fromisoformat,
                    help="inclusive approved source-date upper bound, YYYY-MM-DD")
    ap.add_argument("--pages-per-year", type=int, default=15)
    ap.add_argument("--min-cited-by", type=int, default=2)
    ap.add_argument("--selection-budget", type=int, default=100,
                    help="maximum eligible candidates staged per source year")
    ap.add_argument("--cap", type=int, default=HARD_CAP,
                    help="hard ceiling on total requests")
    args = ap.parse_args()

    first = args.from_year or (args.from_date.year if args.from_date else 2018)
    last = args.to_year or (args.to_date.year if args.to_date else 2026)
    years = list(range(first, last + 1))
    try:
        plan(years, args.pages_per_year, args.min_cited_by,
             from_date=args.from_date, to_date=args.to_date)
    except ValueError as exc:
        ap.error(str(exc))

    if not args.run:
        print("  Re-run with --run to fetch. This is a long job and it is "
              "started by you, not by the product.")
        return 0

    if not (args.authorization_id or "").strip():
        ap.error("--run requires --authorization-id for this exact web scope")
    if args.from_date is None or args.to_date is None:
        ap.error("--run requires explicit --from-date and --to-date for the approved scope")

    return run(
        years, args.pages_per_year, args.min_cited_by, args.cap,
        args.selection_budget, args.authorization_id,
        source_rights=RightsState(args.source_rights),
        from_date=args.from_date, to_date=args.to_date,
    )


if __name__ == "__main__":
    raise SystemExit(main())
