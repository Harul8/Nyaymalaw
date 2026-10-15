"""Receiving an advocate's documents: the malware check, local reading and sealed
storage in the advocate's own document space (owner decisions, 15 Oct 2026).

Composition supplies the stores, the checker and the reader; the rules a document
follows are nm/core_engine/documents.py. The original is kept in sealed chunks and
the record of what was read in one immutable sealed object, named by its reference.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets

from nm.arrive.advocate_contracts import utcnow
from nm.core_engine import documents
from nm.core_engine.documents import DocumentRefused
from nm.open_matter.document_local import DocumentParserDefect, ExtractionRefused
from nm.open_matter.document_text_port import AdmittedDocument, DocumentFormat, TextState
from nm.open_matter.media_contracts import MediaKind, Processor, Quarantine, admitted

CHUNK = 1024 * 1024
_REFERENCE = re.compile(r"(doc_[0-9a-f]{24})-([0-9a-f]{64})")
_log = logging.getLogger(__name__)


def space(advocate_id):
    """The advocate's own document space, under its own encryption key."""
    return "docs_" + hashlib.sha256(advocate_id.encode("utf-8")).hexdigest()[:40]


class DocumentDesk:
    def __init__(self, *, prepare_space, originals, texts, checker, reader, clock=utcnow):
        self.prepare_space, self.originals, self.texts = prepare_space, originals, texts
        self.checker, self.reader, self.clock = checker, reader, clock

    def receive(self, advocate_id, name, data):
        fmt = documents.document_format(name, data)
        if fmt is None:
            raise DocumentRefused("Only PDF, Word (.docx), plain text (.txt), PNG or JPEG files can be read.")
        if not 0 < len(data) <= documents.MAX_BYTES:
            raise DocumentRefused("A document can be at most 16 MB.")
        sha = hashlib.sha256(data).hexdigest()
        document_id = "doc_" + secrets.token_hex(12)
        state, reason = self.checker.check(data)
        where = space(advocate_id)
        self.prepare_space(where)
        pages, observed, failure = [], None, None
        if state == "clear":
            for start in range(0, len(data), CHUNK):
                self.originals.put(where, f"{document_id}-{start // CHUNK}", data[start:start + CHUNK])
            pages, observed, failure = self._read(advocate_id, document_id, fmt, data, sha)
        record = documents.receipt(
            document_id=document_id, name=name, fmt=fmt, sha256=sha, size=len(data),
            received_at=self.clock().isoformat(), check={"state": state, "reason": reason, "checker": self.checker.name},
            pages=pages, observed_pages=observed, failure=failure)
        body = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.texts.put(where, documents.reference(record), body)
        return record

    def _read(self, advocate_id, document_id, fmt, data, sha):
        if fmt == "image":
            return [{"number": 1, "state": "unread", "code": "scanned",
                     "reason": "an image, with no text layer to read here"}], 1, None
        admission = admitted(document_id, MediaKind.DOCUMENT, purpose="legal research for the advocate's question",
                             authority=f"the advocate {advocate_id}", quarantine=Quarantine.RELEASED,
                             processors=(Processor(self.checker.name, False, "malware check before reading"),))
        try:
            result = self.reader.extract(AdmittedDocument(data, DocumentFormat(fmt), sha, admission))
        except (ExtractionRefused, DocumentParserDefect) as exc:
            # A document a parser cannot handle is an expected outcome for uploaded files.
            _log.warning("A document could not be read: %s", type(exc).__name__)
            return [], None, "this document could not be read on this installation"
        pages = []
        for unit in result.units:
            if unit.state is TextState.EXTRACTED:
                pages.append({"number": unit.number, "state": "read", "text": unit.text, "read_by": "local"})
            elif unit.state is TextState.NO_TEXT_LAYER:
                pages.append({"number": unit.number, "state": "unread", "code": "scanned",
                              "reason": "a scanned page with no text layer"})
            else:
                pages.append({"number": unit.number, "state": "unread", "code": "unreadable",
                              "reason": unit.reason or "this page could not be read"})
        return pages, result.observed_units, (result.reason if result.failure else None)

    def load(self, advocate_id, ref):
        """The exact record a reference names, from the advocate's own space only."""
        match = _REFERENCE.fullmatch(ref or "")
        if not match:
            raise DocumentRefused("This is not a document reference.")
        try:
            body = self.texts.read(space(advocate_id), ref, match.group(2))
        except (OSError, ValueError) as exc:
            raise DocumentRefused("This document is not available.") from exc
        return documents.checked(json.loads(body.decode("utf-8")), ref)
