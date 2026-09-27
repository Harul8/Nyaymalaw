"""Exact original receipt locators on the existing attributed-file projection.

A document name is not an upload identity. This projection never matches a
filename, supplies a new fact, or decides whether original reading is allowed.
The original-view edge rechecks the current owned permission before byte access.
"""
from __future__ import annotations

import re

from nm.work_the_file.matter_contracts import Matter

MAX_ORIGINAL_VIEW_BYTES = 8 * 1024 * 1024


def add_original_locators(casefile: dict, matter: Matter) -> dict:
    """Return a fresh projection; only an exact existing upload ID can resolve."""
    if type(casefile) is not dict or casefile.get("matter_id") != matter.id:
        raise ValueError("an original locator requires its owning case-file projection")
    entries = []
    for entry in casefile["entries"]:
        attribution = dict(entry.get("attribution") or {})
        document = attribution.get("document")
        if document:
            locator = _locator(matter, document, attribution.get("page"), attribution.get("span"))
            attribution["original"] = locator
            attribution["original_unavailable"] = "" if locator else (
                "Opening the original is not available: this source lacks an exact "
                "current sealed-original receipt. No filename or URL was substituted.")
        entries.append({**entry, "attribution": attribution})
    by_id = {entry["fact_id"]: entry for entry in entries}
    return {**casefile, "entries": entries,
            "live": [by_id[entry["fact_id"]] for entry in casefile.get("live", ())]}


def _locator(matter, document, page, span):
    if (type(document) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", document)
            or type(page) is not int or page < 1
            or span is not None and (type(span) is not str or len(span) > 4000)):
        return None
    row = matter.uploads.get(document)
    if type(row) is not dict or type(row.get("receipt")) is not dict:
        return None
    receipt = row["receipt"]
    if (receipt.get("upload_id") != document or receipt.get("matter_id") != matter.id
            or receipt.get("actor_id") != matter.advocate_id or receipt.get("state") != "received"
            or type(row.get("asset_version")) is not int or row["asset_version"] < 1
            or type(receipt.get("observed_size")) is not int
            or not 0 < receipt["observed_size"] <= MAX_ORIGINAL_VIEW_BYTES
            or type(receipt.get("observed_hash")) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", receipt["observed_hash"])):
        return None
    return {"original_id": document, "matter_version": matter.version,
            "asset_version": row["asset_version"], "source_sha256": receipt["observed_hash"],
            "byte_length": receipt["observed_size"], "page": page, "span": span}
