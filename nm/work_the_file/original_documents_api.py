"""Human original inspection through existing local document permission owners.

No new upload store, admission, parser, model tool or fact authority lives here.
Bare original-content requests remain held at the HTTP edge. A supplied exact
receipt only identifies the request; the existing DocumentService._read owner
must establish the current successful derivative and all reading restrictions.
"""

from __future__ import annotations

import base64
import re

from nm.open_matter.document_text_port import DocumentFormat, TextState
from nm.open_matter.documents_api import DocumentService
from nm.open_matter.matter_documents_port import DocumentRefused
from nm.open_matter.uploads_api import _receipt
from nm.work_the_file.original_source_locators import MAX_ORIGINAL_VIEW_BYTES

INSPECTION_PURPOSE = "human_original_inspection"


def original_view(
    service: DocumentService,
    matter_id: str,
    actor_id: str,
    *,
    expected_version: int,
    original_id: str,
    asset_version: int,
    source_sha256: str,
    purpose: str,
) -> dict:
    """One explicit, bounded original read; authority is rechecked at every sink."""
    if (
        purpose != INSPECTION_PURPOSE
        or type(purpose) is not str
        or type(asset_version) is not int
        or asset_version < 1
        or type(source_sha256) is not str
        or not re.fullmatch(r"[a-f0-9]{64}", source_sha256)
    ):
        raise DocumentRefused("identify the exact original for human inspection")
    matter = service._owned(matter_id, actor_id, expected_version)
    row = service.uploads._row(matter, original_id)
    receipt = _receipt(row)
    if (
        type(row["asset_version"]) is not int
        or row["asset_version"] != asset_version
        or receipt.observed_hash != source_sha256
    ):
        raise DocumentRefused("the original inspection identifies a stale or different receipt")
    _bounded(row, receipt.observed_size)
    # This is the actual current local-read owner, including withdrawal,
    # admission/clearance identity, retention and original/derivative integrity.
    _reading, result = service._read(matter, row)
    if (
        result.failure is not None
        or not result.units
        or not any(unit.state is TextState.EXTRACTED for unit in result.units)
        or result.format not in {DocumentFormat.TEXT, DocumentFormat.PDF, DocumentFormat.DOCX}
    ):
        raise DocumentRefused("a successful current local derivative is required for inspection")
    service._owned(matter_id, actor_id, expected_version)
    _matter, _row, data = service.uploads.verified_original(
        matter_id,
        actor_id,
        original_id,
        expected_version=expected_version,
        max_bytes=MAX_ORIGINAL_VIEW_BYTES,
        before_read=lambda: service._owned(matter_id, actor_id, expected_version),
    )
    service._owned(matter_id, actor_id, expected_version)
    if len(data) != receipt.observed_size or not 0 < len(data) <= MAX_ORIGINAL_VIEW_BYTES:
        raise DocumentRefused("the opened original exceeds its identified viewing bound")
    result = {
        "state": "original_opened",
        "matter_id": matter_id,
        "matter_version": expected_version,
        "original_id": original_id,
        "asset_version": asset_version,
        "source_sha256": source_sha256,
        "byte_length": len(data),
        "filename": row["offer"]["filename"],
        "format": result.format.value,
        "content_base64": base64.b64encode(data).decode("ascii"),
        "facts_established": False,
        "representation": "original_bytes",
        "purpose": INSPECTION_PURPOSE,
    }
    service._owned(matter_id, actor_id, expected_version)
    return result


def _bounded(row, size):
    # Apply the narrower transport bound before the owner's first byte read,
    # not after reconstructing/base64-encoding a server-upload-sized object.
    if type(size) is not int or not 0 < size <= MAX_ORIGINAL_VIEW_BYTES:
        raise DocumentRefused("the original exceeds the human inspection byte bound")
    total = 0
    for chunk in row.get("chunks", ()):
        count = chunk.get("size") if type(chunk) is dict else None
        if type(count) is not int or count < 1:
            raise DocumentRefused("the original chunk sizes cannot establish a viewing bound")
        total += count
        if total > MAX_ORIGINAL_VIEW_BYTES:
            raise DocumentRefused("the original chunks exceed the human inspection byte bound")
    if total != size:
        raise DocumentRefused("the original chunk sizes differ from their identified receipt")
