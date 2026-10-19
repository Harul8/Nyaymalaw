"""Fetch the Acts of the Centre and Telangana from India Code. AN OFFLINE JOB, READ-ONLY ON
INDIA CODE; IT WRITES ONLY A NEW, DATED FOLDER.

    .venv-arrive\\Scripts\\python.exe pipeline\\fetch_india_code.py --out "legal_database/raw_data/IndiaCode/2026-10-19"
        --cache outputs/corpus-indiacode-20261019/cache --files-for outputs/corpus-indiacode-20261019/missing_acts.json

Owner decisions P20-P23 (19 Oct 2026, the Advocate build plan): the Acts are re-sourced from
India Code where it publishes them section by section, the current Acts the corpus lacks are
added from it, and Telangana keeps what India Code lists under Telangana. India Code moved in
August 2026 to indiacode.gov.in, whose public data service publishes each section of an Act as
its own record - its number, heading, order, text and amendment footnotes - and keeps Act texts,
schedules, rules and regulations as PDFs.

For every Act India Code lists for the Centre and for Telangana the job writes one JSON file:
the Act's own record (titles, numbers, dates, preamble, history) and every section record, in
India Code's order, checked against India Code's own count; and, for the Acts named in
--files-for (the Acts the corpus does not hold), the Act's and its schedules' PDFs with India
Code's text of them. A manifest records what was fetched, when, and each file's SHA-256.

It asks one thing at a time with a pause, keeps every answer of the data service in --cache so a
re-run asks nothing again, and resumes where it stopped. It reads nothing from, and writes
nothing to, the existing corpus, its store or its indexes: what becomes of the fetched text is
the rebuild's business, compared with our text and shown to the owner first (P20).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import truststore

API = "https://indiacode.gov.in/server/api"
STATES = ("CENTRAL", "Telangana")
HEADERS = {"User-Agent": "Nyaymalaw corpus fetch (read-only; one request at a time)", "Accept": "application/json"}
PAUSE = 0.45


class Source:
    """India Code's data service, politely: one request at a time, a pause between them, a few
    retries on a server fault, every JSON answer kept on disk."""

    def __init__(self, cache: Path):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(headers=HEADERS, timeout=httpx.Timeout(180, connect=20), follow_redirects=True,
                                   verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        self.asked = self.reused = 0

    def _get(self, url: str, **params) -> httpx.Response:
        for attempt in range(5):
            time.sleep(PAUSE * (1 + 3 * attempt))
            try:
                response = self.client.get(url, params=params or None)
                if response.status_code < 500:
                    response.raise_for_status()
                    return response
                problem = f"server {response.status_code}"
            except httpx.TransportError as error:
                problem = type(error).__name__
            print(f"   retry {attempt + 1}: {problem}", flush=True)
        raise RuntimeError(f"India Code did not answer: {url}")

    def json(self, path: str, **params) -> dict:
        key = hashlib.sha1(json.dumps([path, sorted(params.items())]).encode()).hexdigest()
        kept = self.cache / f"{key}.json"
        if kept.exists():
            self.reused += 1
            return json.loads(kept.read_text(encoding="utf-8"))
        data = self._get(API + path, **params).json()
        self.asked += 1
        kept.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def file(self, url: str, target: Path) -> None:
        if target.exists() and target.stat().st_size:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(self._get(url).content)
        partial.replace(target)
        self.asked += 1


def values(record: dict, key: str) -> list[str]:
    return [entry["value"] for entry in record["metadata"].get(key, [])]


def first(record: dict, key: str) -> str | None:
    found = values(record, key)
    return found[0] if found else None


def search(source: Source, **filters) -> list[dict]:
    """Every record matching the filters, a hundred at a time, in India Code's order."""
    found, page = [], 0
    while True:
        result = source.json("/discover/search/objects", **filters, size=100, page=page)["_embedded"]["searchResult"]
        found.extend(entry["_embedded"]["indexableObject"] for entry in result["_embedded"]["objects"])
        page += 1
        if page >= result["page"]["totalPages"]:
            return found


def count(source: Source, **filters) -> int:
    return source.json("/discover/search/objects", **filters, size=1)["_embedded"]["searchResult"]["page"]["totalElements"]


def section(record: dict) -> dict:
    order = first(record, "dc.identifier.order_number")
    return {"number": first(record, "dc.identifier.section_number"), "heading": first(record, "dc.title"),
            "order": int(order) if order and order.isdigit() else None,
            "text_html": first(record, "dc.identifier.section_page_note") or "",
            "footnotes_html": first(record, "dc.identifier.section_footnote") or "",
            "section_id": first(record, "dc.identifier.section_id"), "uuid": record["uuid"],
            "handle": record["handle"]}


def files_of(source: Source, record: dict, folder: Path) -> list[dict]:
    """A record's PDFs and India Code's text of them, saved under folder; the Hindi text of a
    central Act (named H<year>-<number>) is left, the corpus being English."""
    saved = []
    for bundle in source.json(f"/core/items/{record['uuid']}/bundles").get("_embedded", {}).get("bundles", []):
        if bundle["name"] not in ("ORIGINAL", "TEXT"):
            continue
        for stream in source.json(f"/core/bundles/{bundle['uuid']}/bitstreams").get("_embedded", {}) \
                .get("bitstreams", []):
            if stream["name"][:1] == "H" and stream["name"][1:2].isdigit():
                continue
            target = folder / stream["name"]
            source.file(stream["_links"]["content"]["href"], target)
            saved.append({"name": stream["name"], "bundle": bundle["name"], "bytes": target.stat().st_size,
                          "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--files-for", type=Path, help="JSON with act_ids whose PDFs and schedules to fetch")
    parser.add_argument("--only", help="comma-separated India Code act_ids: fetch these Acts alone (a pilot)")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    sys.stdout.reconfigure(encoding="utf-8")
    if args.out.exists() and any(args.out.glob("manifest.json")):
        print(f"{args.out} already holds a finished fetch; give a new folder.")
        return 1
    files_for = set(json.loads(args.files_for.read_text(encoding="utf-8"))["act_ids"]) if args.files_for else set()
    source = Source(args.cache)
    manifest = {"source": "India Code, indiacode.gov.in public data service", "api": API,
                "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "decisions": "Owner decisions P20-P23, 19 Oct 2026 (Advocate build plan)", "acts": []}
    for state in STATES:
        acts = search(source, **{"f.identifier_collection": "ACT,equals", "f.identifier_state": f"{state},equals",
                                 "sort": "dc.title,ASC"})
        schedules: dict[str, list[dict]] = {}
        for record in search(source, **{"f.identifier_collection": "SCHEDULE,equals",
                                        "f.identifier_state": f"{state},equals", "sort": "dc.title,ASC"}):
            schedules.setdefault(first(record, "dc.identifier.act_id"), []).append(record)
        print(f"{state}: {len(acts)} Acts, {sum(map(len, schedules.values()))} schedule records", flush=True)
        for number, act in enumerate(acts, 1):
            act_id = first(act, "dc.identifier.act_id")
            if only is not None and act_id not in only:
                continue
            target = args.out / state / f"{act_id}.json"
            filters = {"f.act_id": f"{act_id},equals", "f.identifier_collection": "SECTION,equals"}
            expected = count(source, **filters, sort="dc.title,ASC")
            if target.exists():
                held = json.loads(target.read_text(encoding="utf-8"))
            else:
                records = search(source, **filters, sort="dc.identifier.order_number,ASC")
                unique = {record["uuid"]: record for record in records}
                if len(unique) != expected:
                    # A page boundary between equal order numbers can repeat or skip a record:
                    # read the Act's sections a second way, and keep every record found.
                    for record in search(source, **filters, sort="dc.identifier.section_number,ASC"):
                        unique.setdefault(record["uuid"], record)
                sections = sorted((section(record) for record in unique.values()),
                                  key=lambda entry: (entry["order"] is None, entry["order"] or 0, entry["number"] or ""))
                # India Code's machine-written summary of an Act is not law, and is not kept.
                held = {"state": state, "act_id": act_id, "uuid": act["uuid"], "handle": act["handle"],
                        "act": {key: values(act, key) for key in act["metadata"] if key != "dc.description.abstract"},
                        "sections": sections, "india_code_section_count": expected,
                        "schedules": [{"title": first(record, "dc.title"), "uuid": record["uuid"],
                                       "handle": record["handle"],
                                       "order": first(record, "dc.identifier.order_number")}
                                      for record in schedules.get(act_id, [])],
                        "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                if act_id in files_for:
                    # An Act the corpus lacks: its own text where India Code has no section
                    # records, and its schedules (which India Code keeps only as PDFs).
                    folder = args.out / state / "files" / act_id
                    if not sections:
                        held["files"] = files_of(source, act, folder)
                    for entry, record in zip(held["schedules"], schedules.get(act_id, [])):
                        entry["files"] = files_of(source, record, folder / "schedules" / record["uuid"])
                target.parent.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(target.name + ".part")
                partial.write_text(json.dumps(held, ensure_ascii=False, indent=1), encoding="utf-8")
                partial.replace(target)
            complete = len(held["sections"]) == expected
            manifest["acts"].append({"state": state, "act_id": act_id, "title": first(act, "dc.title"),
                                     "number": first(act, "dc.identifier.act_number"),
                                     "year": first(act, "dc.date.act_year"), "sections": len(held["sections"]),
                                     "india_code_sections": expected, "complete": complete,
                                     "schedules": len(held["schedules"]), "files": len(held.get("files", [])),
                                     "path": target.relative_to(args.out).as_posix(),
                                     "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
            if not complete:
                print(f"   {act_id}: {len(held['sections'])} of {expected} sections", flush=True)
            if number % 50 == 0:
                print(f"   {state} {number}/{len(acts)} ({source.asked} asked, {source.reused} from disk)", flush=True)
    manifest["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["totals"] = {state: {"acts": sum(1 for act in manifest["acts"] if act["state"] == state),
                                  "sections": sum(act["sections"] for act in manifest["acts"] if act["state"] == state),
                                  "incomplete": sum(1 for act in manifest["acts"]
                                                    if act["state"] == state and not act["complete"])}
                          for state in STATES}
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("done:", manifest["totals"], f"| {source.asked} asked, {source.reused} from disk", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
