"""Human original inspection through existing local document permission owners.

No new upload store, admission, parser, model tool or fact authority lives here.
Bare original-content requests remain held at the HTTP edge. A supplied exact
receipt only identifies the request; the existing DocumentService._read owner
must establish the current successful derivative and all reading restrictions.
"""

from __future__ import annotations


from nm.open_matter.matter_documents_port import DocumentRefused
from nm.work_the_file.original_source_locators import MAX_ORIGINAL_VIEW_BYTES

INSPECTION_PURPOSE = "human_original_inspection"


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
