"""Build the sampling frame for the golden evaluation set, and draw from it.

    python pipeline/acquisition/build_eval_frame.py frame --out golden
    python pipeline/acquisition/build_eval_frame.py fetch --out golden

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
This decides WHICH documents the evaluation set is drawn from. It does not
stage, quarantine or reconcile them -- `backend/nm/knowledge/acquisition.py`
owns that, and a second staging path beside it is the duplicate this project
already pays for elsewhere. The output here is a manifest of S3 keys plus the
identity of the frame they were drawn from; everything downstream reads that.

THE SOURCE
----------
`s3://indian-high-court-judgments`, the eCourts scrape published on the AWS
Open Data Registry under CC-BY-4.0, read anonymously over HTTPS with no
credentials. Telangana is `court=36_29` (bench `taphc`) and Andhra Pradesh is
`court=28_2` (bench `aphc`); under `docs/BASELINE.md` 1.1 both bind a
Telangana matter.

WHY THESE ARE CASE FILES AND NOT JUDGEMENTS
-------------------------------------------
The PDFs are the REGISTRY's order documents, so each carries the cause title
before the order: the parties with their particulars, the provision the matter
was filed under, the order appealed from, the interlocutory applications and
who appeared. That is the procedural spine of a real matter. The e-SCR bucket
for the Supreme Court serves the LAW REPORT instead -- headnotes and held --
and is therefore not a substitute for this one.

THREE MEASURED TRAPS THIS FILE REFUSES
--------------------------------------
1. `pdf_exists` IS FALSE ON EVERY ROW AND IT IS WRONG. Measured 20 September
   2026: all 38,931 rows of Telangana 2024 carry `pdf_exists: false` while
   12.24 GB of those PDFs sit in the same bucket. It is a flag nothing ever
   set, rendering as measured absence. This module never reads that column.
   Presence is derived from the fetch and carries THREE states -- held, not
   held, and not assessed -- because a document nobody asked for is not a
   document that is missing.

2. `court` IS THE CUSTODIAN, NOT THE COURT THAT DECIDED. All 53,885 rows of
   `year=2010/court=36_29` say "High Court for State of Telangana" while the
   documents say "HIGH COURT OF JUDICATURE OF ANDHRA PRADESH AT HYDERABAD".
   The Telangana High Court was constituted on 1 January 2019; eCourts filed
   the common court's older records under the surviving bench. The deciding
   court is read from the document header, never from the column.

3. A THIN YEAR IS A THIN SCRAPE, NOT A QUIET COURT. Telangana 2022 holds
   25.76 GB and 2024 holds 13.14 GB; 2010 has 53,885 rows against 2024's
   38,931. No docket moves like that. Year coverage is reported, never
   inferred.

ALLOCATION
----------
Proportional to the measured population, with a floor, so the tail is present
without the head losing precision. Every stratum carries its weight back to
the population. Strata under `--diversity-below` of the population are marked
`diversity_only`: they are tripwires that detect a wholly broken case type,
they are not measurements, and they are excluded from any weighted estimate.

RIGHTS
------
CC-BY-4.0 is recorded as the licence the source publishes, with where that was
read. That is a statement about the source, NOT an authorisation to acquire:
`AcquisitionScope` refuses `RightsState.UNKNOWN` and requires an authorisation
id precisely so that nobody's reading of a licence page becomes a review
nobody did. The manifest says `authorisation: null` until a real one exists.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as futures
import hashlib
import json
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()

BUCKET = "https://indian-high-court-judgments.s3.amazonaws.com/"
LICENCE = "CC-BY-4.0"
LICENCE_READ_AT = "https://github.com/vanga/indian-high-court-judgments"

#: court code -> (bench, the name to attribute, the years worth pulling).
COURTS = {
    "36_29": ("taphc", "High Court for the State of Telangana"),
    "28_2": ("aphc", "High Court of Andhra Pradesh"),
}

#: The cause title names the provision the matter was FILED under. It survives
#: dirty OCR better than anything else in the row, and it is the only free
#: subject signal in the metadata, so it is the second stratification axis.
#: A TRAILING LETTER IS A SUB-SECTION ONLY WHEN IT IS ATTACHED. An earlier
#: form allowed whitespace before it and captured the first letter of the
#: NEXT word: "under Section 482 of Cr.P.C" became `482O`, "under Section 151
#: CPC" became `151C`, and 282 of 1,000 gold labels were wrong in a way that
#: reads exactly like the real sub-section suffixes (138A, 437A) it must be
#: able to tell them from. The letter must touch the digits and must not be
#: the start of a word.
FILED_UNDER = re.compile(
    r"\bunder\s+(?:sec(?:tion)?s?\.?|s\.|u/s\.?)\s*([0-9]+[A-Za-z]?)(?![A-Za-z])",
    re.I)

#: The court that actually decided, read off the document header.
DECIDING_COURT = re.compile(
    r"HIGH\s+COURT\s+(?:OF\s+JUDICATURE\s+)?(?:OF|FOR)\s+(?:THE\s+)?"
    r"(?:STATE\s+OF\s+)?([A-Z][A-Z\s]+?)(?:\s+AT\s|\s*$)", re.I)


def _get(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def list_keys(prefix: str) -> list[tuple[str, int]]:
    """Every key under a prefix, following continuation tokens."""
    found, token = [], None
    while True:
        query = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            query["continuation-token"] = token
        body = _get(BUCKET + "?" + urllib.parse.urlencode(query)).decode("utf8", "replace")
        found += list(zip(re.findall(r"<Key>(.*?)</Key>", body),
                          (int(size) for size in re.findall(r"<Size>(\d+)</Size>", body))))
        if not re.search(r"<IsTruncated>true</IsTruncated>", body):
            return found
        match = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", body)
        token = urllib.parse.unquote(match.group(1))


def case_type(title: str) -> str:
    match = re.match(r"\s*([A-Za-z\.\&\(\)]+)\s*/", title or "")
    return match.group(1).upper() if match else "UNPARSED"


def filed_under(description: str) -> tuple[str | None, str | None]:
    """The provision filed under, and the text it was read from.

    The context travels with the label so a human verifying the gold set can
    see what the OCR actually said rather than trusting the extraction.
    """
    match = FILED_UNDER.search(description or "")
    if not match:
        return None, None
    text = description or ""
    start, end = max(0, match.start() - 40), min(len(text), match.end() + 60)
    return match.group(1).upper(), re.sub(r"\s+", " ", text[start:end]).strip()


def deciding_court(description: str) -> str | None:
    match = DECIDING_COURT.search(description or "")
    return re.sub(r"\s+", " ", match.group(1)).strip().title() if match else None


def pendency_days(registered: str, decided) -> int | None:
    if not registered or decided is None:
        return None
    try:
        start = datetime.strptime(registered.strip(), "%d-%m-%Y").date()
    except ValueError:
        return None
    end = decided.date() if hasattr(decided, "date") else decided
    days = (end - start).days
    return days if days >= 0 else None


def read_frame(courts: list[str], years: list[int], cache: Path) -> list[dict]:
    """Pull the metadata partitions and flatten them into frame rows."""
    import pyarrow.parquet as pq

    cache.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for code in courts:
        bench, attribution = COURTS[code]
        for year in years:
            key = f"metadata/parquet/year={year}/court={code}/bench={bench}/metadata.parquet"
            local = cache / f"{code}_{year}.parquet"
            if not local.exists():
                try:
                    local.write_bytes(_get(BUCKET + key, timeout=600))
                except Exception as error:   # noqa: BLE001 - reported, not hidden
                    print(f"  ! {code} {year}: {type(error).__name__} {error}", file=sys.stderr)
                    continue
            table = pq.read_table(local, columns=[
                "title", "description", "judge", "cnr", "pdf_link",
                "date_of_registration", "decision_date", "disposal_nature"])
            data = table.to_pydict()
            for i in range(len(data["cnr"])):
                pdf_link = data["pdf_link"][i] or ""
                name = pdf_link.rsplit("/", 1)[-1]
                if not name.endswith(".pdf"):
                    continue
                provision, provision_context = filed_under(data["description"][i])
                court_from_header = deciding_court(data["description"][i])
                rows.append({
                    # THE DOCUMENT KEY IS THE FILE, NOT THE CASE. A CNR names
                    # a matter and a matter has many orders; keyed by CNR,
                    # 75 of 1,493 drawn documents vanished into each other on
                    # the first run and the count still read as a success.
                    "doc_id": name[:-4],
                    "cnr": data["cnr"][i],
                    "court_code": code,
                    "bench": bench,
                    "attribution": attribution,
                    "decision_year": year,
                    "title": data["title"][i],
                    "case_type": case_type(data["title"][i]),
                    "filed_under": provision,
                    "filed_under_context": provision_context,
                    # THE THIRD STATE, NAMED. `description` is a ~300-character
                    # OCR of the first page and often starts mid-header, so a
                    # miss here is "this field could not tell us", not "the
                    # document does not say". The PDF is where it is read
                    # properly, and until that runs the source says so.
                    "deciding_court": court_from_header,
                    "deciding_court_source": (
                        "description_header" if court_from_header else "not_assessed"),
                    "judge": data["judge"][i],
                    "registered": data["date_of_registration"][i],
                    "decided": str(data["decision_date"][i])[:10],
                    "pendency_days": pendency_days(
                        data["date_of_registration"][i], data["decision_date"][i]),
                    "disposal": data["disposal_nature"][i],
                    "s3_key": f"data/pdf/year={year}/court={code}/bench={bench}/{name}",
                })
            print(f"  {code} {year}: {len(data['cnr'])} rows")

    # THE SOURCE LISTS DOCUMENTS TWICE. Measured 20 September 2026 over
    # 2023-2026 for both courts: 48,917 of 364,739 distinct documents appear
    # more than once, and 48,872 of those duplicates sit INSIDE one partition.
    # Rows are therefore not documents, and a population counted in rows
    # over-states every stratum that happens to duplicate more than its
    # neighbours -- which is a bias in the weights, not merely a tidiness
    # problem. Deduplicate on the document key and report what was removed.
    unique: dict[str, dict] = {}
    for row in rows:
        unique.setdefault(row["doc_id"], row)
    removed = len(rows) - len(unique)
    print(f"  deduplicated: {len(rows)} rows -> {len(unique)} documents "
          f"({removed} duplicate listings removed)")
    return list(unique.values())


def allocate(population: collections.Counter, size: int, floor: int,
             min_population: int) -> dict[str, int]:
    """Proportional to the population, with a floor under every eligible cell."""
    eligible = {k: v for k, v in population.items() if v >= min_population}
    if floor * len(eligible) > size:
        raise SystemExit(
            f"floor {floor} across {len(eligible)} strata needs "
            f"{floor * len(eligible)} draws but the sample is {size}. "
            f"Raise --size, lower --floor, or raise --min-population.")
    total = sum(eligible.values())
    share = {k: floor for k in eligible}
    remainder = size - floor * len(eligible)
    for k, v in eligible.items():
        share[k] += int(remainder * v / total)
    share[max(share, key=lambda k: eligible[k])] += size - sum(share.values())
    return share


def draw(rows: list[dict], share: dict[str, int], seed: int,
         headroom: float) -> dict[str, list[dict]]:
    """Draw each stratum with headroom, so a missing PDF has a replacement."""
    rng = random.Random(seed)
    by_type: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        by_type[row["case_type"]].append(row)
    drawn = {}
    for stratum, want in share.items():
        pool = by_type[stratum]
        # Prefer rows whose cause title named the filing provision: they carry
        # a free exact label as well as the document.
        labelled = [r for r in pool if r["filed_under"]]
        rest = [r for r in pool if not r["filed_under"]]
        rng.shuffle(labelled)
        rng.shuffle(rest)
        drawn[stratum] = (labelled + rest)[:int(want * headroom) + want]
    return drawn


def cmd_frame(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    years = list(range(args.from_year, args.to_year + 1))
    print(f"Reading metadata: courts={args.courts} years={years[0]}-{years[-1]}")
    rows = read_frame(args.courts, years, out / "_metadata_cache")
    if not rows:
        raise SystemExit("no frame rows were read; nothing was drawn")

    population = collections.Counter(r["case_type"] for r in rows)
    total = sum(population.values())
    share = allocate(population, args.size, args.floor, args.min_population)
    drawn = draw(rows, share, args.seed, args.headroom)

    strata = {}
    for stratum, want in sorted(share.items(), key=lambda kv: -kv[1]):
        pop_share = population[stratum] / total
        strata[stratum] = {
            "population": population[stratum],
            "population_share": round(pop_share, 6),
            "target": want,
            "weight": round(pop_share * args.size / want, 4),
            "diversity_only": pop_share < args.diversity_below,
            "candidates": [r["doc_id"] for r in drawn[stratum]],
        }

    # AN EXCLUDED STRATUM IS DECLARED, NEVER DROPPED QUIETLY. A case type too
    # rare to carry the floor would enter a weighted estimate at a weight near
    # zero, which is noise wearing the costume of coverage. Naming it here is
    # what keeps "24 case types" from being read as "every case type".
    excluded = {
        stratum: {
            "population": count,
            "population_share": round(count / total, 6),
            "reason": "below --min-population; too rare to carry the floor",
        }
        for stratum, count in sorted(population.items(), key=lambda kv: -kv[1])
        if stratum not in share
    }

    manifest = {
        "drawn_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "size": args.size,
        "floor": args.floor,
        "diversity_below": args.diversity_below,
        "frame": {
            "courts": args.courts,
            "years": [years[0], years[-1]],
            "rows": total,
            "distinct_case_types": len(population),
            "strata_eligible": len(share),
            "strata_excluded": len(excluded),
            "rows_naming_a_provision": sum(1 for r in rows if r["filed_under"]),
            "distinct_cases": len({r["cnr"] for r in rows}),
        },
        "source": {
            "bucket": BUCKET,
            "licence": LICENCE,
            "licence_read_at": LICENCE_READ_AT,
            "attribution": sorted({COURTS[c][1] for c in args.courts}),
            "read_anonymously": True,
        },
        # NOT AN AUTHORISATION. The licence is what the source publishes; an
        # authorisation is a decision somebody made and signed. Downstream
        # staging refuses this manifest until the second exists.
        "authorisation": None,
        "rights_state": "LICENCE_STATED_NOT_REVIEWED",
        "strata": strata,
        "excluded_strata": excluded,
        "rows": {r["doc_id"]: r for stratum in drawn for r in drawn[stratum]},
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")

    print(f"\nframe rows {total}  case types {len(population)}  "
          f"strata {len(share)}  provision named on "
          f"{manifest['frame']['rows_naming_a_provision']}")
    print(f"\n  {'stratum':12} {'pop %':>7} {'target':>7} {'weight':>7}  note")
    for stratum, meta in strata.items():
        note = "diversity only" if meta["diversity_only"] else ""
        print(f"  {stratum:12} {100*meta['population_share']:6.2f}% "
              f"{meta['target']:7} {meta['weight']:7.2f}  {note}")
    print(f"\nwrote {out / 'manifest.json'}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download every drawn candidate, then say which ones the sample is.

    THE HEADROOM IS NOT WASTE AND IT IS NOT THE SAMPLE. Each stratum is drawn
    with spare candidates so a document the bucket does not hold has a
    replacement. What comes back is split in draw order: the first `target`
    documents held are SELECTED and are the evaluation set; the rest are
    RESERVE, which is what a later quarter re-draws from without going back to
    the bucket. A reserve document is not a selected one that failed.
    """
    out = Path(args.out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf8"))
    docs = out / "docs"
    rows = manifest["rows"]

    def fetch_one(doc_id: str) -> tuple[str, str, int]:
        row = rows[doc_id]
        target = docs / row["case_type"] / f"{doc_id}.pdf"
        if target.exists() and target.stat().st_size > 0:
            return doc_id, "held", target.stat().st_size
        try:
            payload = _get(BUCKET + row["s3_key"], timeout=180)
        except urllib.error.HTTPError as error:
            return doc_id, ("not_held" if error.code == 404 else f"error:{error.code}"), 0
        except Exception as error:   # noqa: BLE001 - reported, never hidden
            return doc_id, f"error:{type(error).__name__}", 0
        if not payload.startswith(b"%PDF"):
            return doc_id, "not_held", 0
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return doc_id, "held", len(payload)

    state: dict[str, str] = {}
    size: dict[str, int] = {}
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        every = [c for meta in manifest["strata"].values() for c in meta["candidates"]]
        for doc_id, result, length in pool.map(fetch_one, every):
            state[doc_id] = result
            size[doc_id] = length

    print(f"  {'stratum':12} {'target':>7} {'selected':>9} {'reserve':>8}  note")
    for stratum, meta in manifest["strata"].items():
        selected = 0
        for doc_id in meta["candidates"]:
            role = "not_held"
            if state.get(doc_id) == "held":
                role = "selected" if selected < meta["target"] else "reserve"
                selected += 1 if role == "selected" else 0
            elif doc_id not in state:
                role = "not_assessed"
            rows[doc_id]["role"] = role
            rows[doc_id]["pdf_state"] = state.get(doc_id, "not_assessed")
            rows[doc_id]["pdf_bytes"] = size.get(doc_id, 0)
        meta["selected"] = selected
        meta["reserve"] = sum(1 for c in meta["candidates"]
                              if rows[c]["role"] == "reserve")
        meta["shortfall"] = max(0, meta["target"] - selected)
        note = "SHORTFALL" if meta["shortfall"] else ""
        print(f"  {stratum:12} {meta['target']:7} {selected:9} "
              f"{meta['reserve']:8}  {note}")

    tally = collections.Counter(r["pdf_state"] for r in rows.values())
    roles = collections.Counter(r["role"] for r in rows.values())
    manifest["fetched_at"] = datetime.now(timezone.utc).isoformat()
    manifest["document_states"] = dict(tally)
    manifest["roles"] = dict(roles)
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")

    identity = {
        "artefact": "golden evaluation document set",
        "built_at": manifest["fetched_at"],
        "source_bucket": BUCKET,
        "licence": LICENCE,
        "licence_read_at": LICENCE_READ_AT,
        "attribution": manifest["source"]["attribution"],
        # NOT AN AUTHORISATION. See the module docstring.
        "authorisation": None,
        "rights_state": manifest["rights_state"],
        "frame": manifest["frame"],
        "seed": manifest["seed"],
        "documents": dict(roles),
        "document_states": dict(tally),
        "shortfall_strata": {k: v["shortfall"] for k, v in manifest["strata"].items()
                             if v["shortfall"]},
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (out / "identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf8")

    # A KEY IS NOT A NAME. The full manifest carries party names, advocate
    # names and the OCR context they were read from -- real personal data
    # about real litigants, and committing it would turn the repository into
    # a searchable index of them. The published manifest keeps only what
    # reconstitutes the set: the document key, the S3 key, the seed and the
    # structural labels. Every name stays recoverable from the public court
    # record the key points at, which is where it already lives.
    private = {"title", "judge", "filed_under_context", "attribution"}
    published = dict(manifest)
    published["rows"] = {
        doc_id: {k: v for k, v in row.items() if k not in private}
        for doc_id, row in rows.items()
    }
    published["redacted_fields"] = sorted(private)
    (out / "manifest.public.json").write_text(
        json.dumps(published, ensure_ascii=False, indent=2), encoding="utf8")
    print(f"  wrote {out / 'manifest.public.json'} (party names removed)")
    print(f"\n  roles  {dict(roles)}")
    print(f"  states {dict(tally)}")
    print(f"  wrote {out / 'identity.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    frame = sub.add_parser("frame", help="build the frame and draw the sample")
    frame.add_argument("--out", default="golden")
    frame.add_argument("--courts", nargs="+", default=["36_29", "28_2"])
    frame.add_argument("--from-year", type=int, default=2023)
    frame.add_argument("--to-year", type=int, default=2026)
    frame.add_argument("--size", type=int, default=1000)
    frame.add_argument("--floor", type=int, default=20)
    frame.add_argument("--min-population", type=int, default=400)
    frame.add_argument("--diversity-below", type=float, default=0.01)
    frame.add_argument("--headroom", type=float, default=0.5)
    frame.add_argument("--seed", type=int, default=20260920)
    frame.set_defaults(func=cmd_frame)

    fetch = sub.add_parser("fetch", help="download the drawn documents")
    fetch.add_argument("--out", default="golden")
    fetch.add_argument("--workers", type=int, default=8)
    fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
