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
import threading
import time
from copy import deepcopy

from nm.arrive.advocate_contracts import utcnow
from nm.core_engine import copy_figures, documents, page_reading, voice
from nm.core_engine.documents import DocumentRefused
from nm.open_matter.document_local import DocumentParserDefect, ExtractionRefused
from nm.open_matter.document_text_port import AdmittedDocument, DocumentFormat, TextState
from nm.open_matter.matter_documents_port import MAX_DERIVATIVE_BYTES
from nm.open_matter.media_contracts import MediaKind, Processor, Quarantine, admitted

CHUNK = 1024 * 1024
_REFERENCE = re.compile(r"(doc_[0-9a-f]{24})-([0-9a-f]{64})")
#: The type an original is handed back with; a photograph's is read from its own bytes.
ORIGINAL_TYPES = {"pdf": "application/pdf", "text": "text/plain; charset=utf-8",
                  "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                  **documents.AUDIO}
_log = logging.getLogger(__name__)


def space(advocate_id):
    """The advocate's own document space, under its own encryption key."""
    return "docs_" + hashlib.sha256(advocate_id.encode("utf-8")).hexdigest()[:40]


class ReadingJobs:
    """What waits for the AI read as a background job the page asks after, with page-by-page progress (plan AN.25, P4): one request
    no longer holds the browser for the 80 seconds or more a long scan takes, which a proxy that cuts requests at 60 would refuse.
    A job is the advocate's own - keyed by them and the document - and is kept for KEPT seconds after it ends, so the page that asks
    after it can read how it ended."""

    KEPT = 600.0

    def __init__(self, clock=time.monotonic):
        self._jobs, self._lock, self._clock = {}, threading.Lock(), clock

    def start(self, advocate_id, ref, total, work, explain):
        """Begin work(progress) -> the document's summary, unless this document is already being read, and say where it stands.
        explain(exc): a failure the reading is known to end in, as {'status', 'why', 'code'}; None for any other, which is logged
        with its traceback and told plainly, never hidden."""
        key = (advocate_id, ref)
        with self._lock:
            self._forget()
            job = self._jobs.get(key)
            if job is not None and job["state"] == "reading":
                return self._shown(job)
            job = {"state": "reading", "done": 0, "total": total, "document": None, "error": None, "ended": None}
            self._jobs[key] = job

        def progress(done, count):
            with self._lock:
                job["done"], job["total"] = done, count

        def run():
            document, error = None, None
            try:
                document = work(progress)
            except Exception as exc:  # noqa: BLE001 - a job must end, however it ended; what it was is kept below
                error = explain(exc)
                if error is None:
                    _log.exception("Reading a document ended on an error nobody expected")
                    error = {"status": 500, "why": "The pages could not be read just now. Try again.",
                             "code": "document_reading_failed"}
            with self._lock:
                job.update(state="failed" if error else "done", document=document, error=error, ended=self._clock())

        threading.Thread(target=run, daemon=True, name="nm-document-reading").start()
        with self._lock:
            return self._shown(job)

    def status(self, advocate_id, ref):
        """Where this advocate's reading of the document stands, or None where there is none (never begun, long over, or lost when
        the server restarted)."""
        with self._lock:
            self._forget()
            job = self._jobs.get((advocate_id, ref))
            return None if job is None else self._shown(job)

    def _forget(self):
        now = self._clock()
        for key in [key for key, job in self._jobs.items() if job["ended"] is not None and now - job["ended"] > self.KEPT]:
            del self._jobs[key]

    @staticmethod
    def _shown(job):
        shown = {"state": job["state"], "done": job["done"], "total": job["total"]}
        if job["state"] == "done":
            shown["document"] = deepcopy(job["document"])
        if job["state"] == "failed":
            shown["error"] = dict(job["error"])
        return shown


class DocumentDesk:
    def __init__(self, *, prepare_space, originals, texts, checker, reader, clock=utcnow):
        self.prepare_space, self.originals, self.texts = prepare_space, originals, texts
        self.checker, self.reader, self.clock = checker, reader, clock
        self.jobs = ReadingJobs()

    def receive(self, advocate_id, name, data):
        name = documents.document_name(name)
        fmt = documents.document_format(name, data)
        if fmt is None:
            raise DocumentRefused("Only PDF, Word (.docx), plain text (.txt), PNG or JPEG files, or recordings "
                                  "in MP3, M4A, WAV or WebM, can be read. Video is not read.")
        if not 0 < len(data) <= documents.max_bytes(fmt):
            raise DocumentRefused("A recording can be at most 25 MB." if fmt in documents.AUDIO
                                  else "A document can be at most 16 MB.")
        sha = hashlib.sha256(data).hexdigest()
        document_id = "doc_" + secrets.token_hex(12)
        state, reason = self.checker.check(data)
        pages, observed, failure = (self._read(advocate_id, document_id, fmt, data, sha)
                                    if state == "clear" else ([], None, None))
        record = documents.receipt(
            document_id=document_id, name=name, fmt=fmt, sha256=sha, size=len(data),
            received_at=self.clock().isoformat(), check={"state": state, "reason": reason, "checker": self.checker.name},
            pages=pages, observed_pages=observed, failure=failure)
        body = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_DERIVATIVE_BYTES:
            raise DocumentRefused("This document holds more text than can be kept for one document. "
                                  "Send the relevant pages instead.")
        # Nothing is stored until the whole record is known: a refusal leaves nothing behind.
        where = space(advocate_id)
        self.prepare_space(where)
        if state == "clear":
            for start in range(0, len(data), CHUNK):
                self.originals.put(where, f"{document_id}-{start // CHUNK}", data[start:start + CHUNK])
        self.texts.put(where, documents.reference(record), body)
        return record

    def _admitted(self, advocate_id, document_id, fmt, data, sha):
        admission = admitted(document_id, MediaKind.DOCUMENT, purpose="legal research for the advocate's question",
                             authority=f"the advocate {advocate_id}", quarantine=Quarantine.RELEASED,
                             processors=(Processor(self.checker.name, False, "malware check before reading"),))
        return AdmittedDocument(data, DocumentFormat(fmt), sha, admission)

    def _read(self, advocate_id, document_id, fmt, data, sha):
        if fmt in documents.AUDIO:
            # A voice note is heard by the speech model, not read here (15 Oct 2026).
            return [{"number": 1, "state": "unread", "code": "audio",
                     "reason": "a recording, waiting to be transcribed"}], 1, None
        if fmt == "image":
            return [{"number": 1, "state": "unread", "code": "scanned",
                     "reason": "an image, with no text layer to read here"}], 1, None
        try:
            result = self.reader.extract(self._admitted(advocate_id, document_id, fmt, data, sha))
        except (ExtractionRefused, DocumentParserDefect) as exc:
            # A document a parser cannot handle is an expected outcome for uploaded files.
            _log.warning("A document could not be read: %s", type(exc).__name__)
            return [], None, "this document could not be read on this installation"
        failure = result.reason if result.failure else None
        if fmt != "pdf":
            return self._flowing(result.units, fmt) + (failure,)
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
        return pages, result.observed_units, failure

    @staticmethod
    def _flowing(units, fmt):
        """A Word or text document's pages (16 Oct 2026): only a PDF page without a text
        layer is a scan for the AI to read. A Word document has no fixed pages, so its
        paragraphs are kept in order as one page; a text file's form-feed parts stay
        pages. Empty paragraphs and parts are skipped, never sent to the AI. A reader that
        returned nothing (it failed, or reached its deadline) leaves no pages: its own
        reason is the record's failure, never 'no words'."""
        if not units:
            return [], None
        unread = [{"number": unit.number, "state": "unread", "code": "unreadable",
                   "reason": unit.reason or "this part could not be read"}
                  for unit in units if unit.state not in (TextState.EXTRACTED, TextState.NO_TEXT_LAYER)]
        words = [unit for unit in units if unit.state is TextState.EXTRACTED]
        if fmt == "docx":
            pages = ([{"number": 1, "state": "read", "text": "\n\n".join(unit.text for unit in words),
                       "read_by": "local"}] if words and not unread else [])
            if unread:
                pages = [{"number": 1, "state": "unread", "code": "unreadable",
                          "reason": "parts of this Word document could not be read"}]
        else:
            pages = [{"number": unit.number, "state": "read", "text": unit.text, "read_by": "local"}
                     for unit in words] + unread
            pages.sort(key=lambda page: page["number"])
        if not pages:
            pages = [{"number": 1, "state": "unread", "code": "unreadable",
                      "reason": "this document has no words to read"}]
        return pages, (1 if fmt == "docx" else len(pages))

    def read_waiting(self, advocate_id, ref, model, progress=None):
        """The document again, with what waits for the AI done (owner decisions, 15 Oct
        2026): scanned pages read, or a recording transcribed; stored as a new immutable
        record; and the calls made."""
        record = self.load(advocate_id, ref)
        numbers = documents.needs_transcription(record)
        if not numbers:
            return record, []
        data = self._original(advocate_id, record)
        if record["format"] in documents.AUDIO:
            page, call = voice.transcribe_note(model, record["name"], data, record["format"])
            read, calls = {1: page}, [call] if call else []
        else:
            images, undrawn = self.reader.page_images(
                self._admitted(advocate_id, record["document_id"], record["format"], data, record["sha256"]),
                numbers)
            read, calls = page_reading.read_pages(model, record["name"], images, progress=progress)
            for number, reason in undrawn.items():
                read[number] = {"number": number, "state": "unread", "code": "unreadable", "reason": reason}
        renewed = documents.receipt(
            document_id=record["document_id"], name=record["name"], fmt=record["format"],
            sha256=record["sha256"], size=record["size"], received_at=record["received_at"],
            check=record["check"], pages=[read.get(page["number"], page) for page in record["pages"]],
            observed_pages=record["observed_pages"], failure=record["failure"])
        body = json.dumps(renewed, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_DERIVATIVE_BYTES:
            raise DocumentRefused("This document holds more text than can be kept for one document. "
                                  "Send the relevant pages instead.")
        self.texts.put(space(advocate_id), documents.reference(renewed), body)
        return renewed, calls

    def relook(self, advocate_id, refs, model_factory):
        """The documents a message carries, with figures two copies of one page read differently looked at again on both images
        (plan AN.28, piece 4c): a page the AI read whose figure its image shows otherwise is corrected there, its first reading kept
        beside it, and the document stored as a new record. A page read from a text layer is the document's own words and is never
        changed. Returns (the records, in the order given, renewed where corrected; the calls made). model_factory: the reading
        model, built only where there is something to look at again."""
        records = [self.load(advocate_id, ref) for ref in refs]
        by_id = {record["document_id"]: record for record in records}
        pages = [{"document": record["name"], "key": record["document_id"], "page": page["number"], "text": page["text"]}
                 for record in records for page in record["pages"] if page["state"] == "read"]

        def page_of(place):
            return next(page for page in by_id[place["key"]]["pages"] if page["number"] == place["page"])
        found = [difference for difference in copy_figures.differences(pages)
                 if any(page_of(difference[side]).get("read_by") == "ai" for side in ("first", "second"))
                 and all(by_id[difference[side]["key"]]["format"] in ("pdf", "image") for side in ("first", "second"))]
        if not found:
            return records, []
        model, texts, calls = model_factory(), {}, []
        for difference in found:
            sides = []
            for side in ("first", "second"):
                record, number = by_id[difference[side]["key"]], difference[side]["page"]
                images, _ = self.reader.page_images(self._admitted(advocate_id, record["document_id"], record["format"],
                                                                   self._original(advocate_id, record), record["sha256"]), [number])
                if number not in images:
                    break
                key = (record["document_id"], number)
                sides.append({"name": record["name"], "number": number, "image": images[number],
                              "text": texts.get(key, page_of(difference[side])["text"]), "key": key,
                              "ai": page_of(difference[side]).get("read_by") == "ai"})
            if len(sides) != 2:
                continue
            first, second, call = page_reading.relook(model, sides[0], sides[1], difference["figures"])
            calls.append(call)
            for side, text in zip(sides, (first, second)):
                if text is not None and side["ai"]:
                    texts[side["key"]] = text
        renewed = []
        for record in records:
            mine = {number: text for (document_id, number), text in texts.items() if document_id == record["document_id"]}
            if not mine:
                renewed.append(record)
                continue
            pages = [{**page, "text": mine[page["number"]], "first_reading": page.get("first_reading", page["text"])}
                     if page["number"] in mine else page for page in record["pages"]]
            again = documents.receipt(document_id=record["document_id"], name=record["name"], fmt=record["format"],
                                      sha256=record["sha256"], size=record["size"], received_at=record["received_at"],
                                      check=record["check"], pages=pages, observed_pages=record["observed_pages"],
                                      failure=record["failure"])
            body = json.dumps(again, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(body) > MAX_DERIVATIVE_BYTES:
                renewed.append(record)
                continue
            self.texts.put(space(advocate_id), documents.reference(again), body)
            renewed.append(again)
        return renewed, calls

    def _original(self, advocate_id, record):
        """The original bytes from their sealed chunks, only if they are exactly the ones received."""
        where = space(advocate_id)
        try:
            data = b"".join(self.originals.read(where, f"{record['document_id']}-{index}")
                            for index in range(-(-record["size"] // CHUNK)))
        except (OSError, ValueError) as exc:
            raise DocumentRefused("This document's original is not available.") from exc
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise DocumentRefused("This document's original could not be verified.")
        return data

    def original(self, advocate_id, ref):
        """A document exactly as the advocate sent it, for them to open (owner decision 4,
        17 Oct 2026): its bytes, its type, its name and whether a browser shows it. A PDF,
        a photograph, a recording or plain text shows in the browser; a Word file is
        downloaded, to open in Word. A document the malware check held is never handed back."""
        record = self.load(advocate_id, ref)
        if record["check"]["state"] != "clear":
            raise DocumentRefused("This document was not cleared by the malware check, so it is not opened.")
        data = self._original(advocate_id, record)
        if record["format"] == "image":
            media = ("image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else
                     "image/jpeg" if data.startswith(b"\xff\xd8\xff") else None)
            if media is None:
                raise DocumentRefused("This picture's type could not be confirmed, so it is not opened.")
        else:
            media = ORIGINAL_TYPES[record["format"]]
        return data, media, record["name"], record["format"] != "docx"

    def recording(self, advocate_id, ref):
        """A voice note's original, for the advocate to play back: its bytes and type."""
        record = self.load(advocate_id, ref)
        if record["format"] not in documents.AUDIO or record["check"]["state"] != "clear":
            raise DocumentRefused("This is not a recording that can be played.")
        return self._original(advocate_id, record), documents.AUDIO[record["format"]]

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
