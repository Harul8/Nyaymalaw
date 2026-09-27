"""Read admitted document bytes locally in a hard-bounded disposable process.

No OCR, network, filesystem extraction, fact admission or quarantine release.
PDF parser limits follow pypdf's documented content-stream warning, with hard
process memory containment because a compressed input bound cannot bound RAM.
"""
from __future__ import annotations

import hashlib
import io
import logging
import multiprocessing
import re
import traceback
import zipfile
import zlib
from dataclasses import replace
from pathlib import PurePosixPath
from xml.etree import ElementTree

from nm.adapters.documents.isolation import SandboxUnavailable, memory_limit
from nm.adapters.optional import library
from nm.domain.media import MediaKind
from nm.domain.media_policy import Route, refuse_request
from nm.ports.document_text import (
    DOCUMENT_OPERATION,
    DOCUMENT_PROCESSOR,
    DOCUMENT_READER_VERSION,
    AdmittedDocument,
    DocumentFormat,
    ExtractionBounds,
    ExtractionResult,
    LocatedText,
    TextState,
)

PROCESSOR = DOCUMENT_PROCESSOR
OPERATION = DOCUMENT_OPERATION
_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_LOCAL_PARTS = re.compile(r"word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml")
_log = logging.getLogger(__name__)


class ExtractionRefused(ValueError):
    """The trusted input contract was not met; bytes were not parsed."""


class DocumentParserDefect(RuntimeError):
    """An unexpected programming failure, distinct from a malformed document."""


class _Unreadable(ValueError):
    def __init__(self, kind: str, reason: str, observed: int | None = None):
        super().__init__(reason)
        self.kind, self.reason, self.observed = kind, reason, observed


def _result(document: AdmittedDocument, *, failure: str, reason: str,
            observed: int | None = None) -> ExtractionResult:
    return ExtractionResult(document.source_sha256, document.admission.media_id,
        document.format, len(document.data), observed, failure=failure, reason=reason,
        parser=DOCUMENT_PROCESSOR, parser_version=DOCUMENT_READER_VERSION)


def _located(number: int, kind: str, part: str, text: str,
             bounds: ExtractionBounds, total: int) -> LocatedText:
    if len(text) > bounds.max_unit_characters or total + len(text) > bounds.max_text_characters:
        raise _Unreadable("text_bound", "the extracted text exceeds its declared bound")
    if text.strip():
        return LocatedText(number, kind, part, TextState.EXTRACTED, text)
    return LocatedText(number, kind, part, TextState.NO_TEXT_LAYER,
        reason="no readable text was obtained at this location; no OCR was performed")


def _plain(document: AdmittedDocument, bounds: ExtractionBounds) -> ExtractionResult:
    try:
        text = document.data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise _Unreadable("encoding_unavailable", "the text is not valid UTF-8") from exc
    if any(not c.isprintable() and c not in "\t\r\n\f" for c in text):
        raise _Unreadable("malformed", "the input contains non-text control bytes")
    parts = text.split("\f")
    if len(parts) > bounds.max_units:
        raise _Unreadable("unit_bound", "the text exceeds its declared part bound", len(parts))
    units, total = [], 0
    for number, part in enumerate(parts, 1):
        units.append(_located(number, "part", "utf8-text", part, bounds, total))
        total += len(part)
    return ExtractionResult(document.source_sha256, document.admission.media_id,
        document.format, len(document.data), len(units), tuple(units),
        parser="strict-utf8", parser_version="1")


def _xml(data: bytes, bounds: ExtractionBounds) -> ElementTree.Element:
    if len(data) > bounds.max_stream_bytes:
        raise _Unreadable("stream_bound", "a document XML part exceeds its declared bound")
    # Removing NUL bytes for this lexical check also detects UTF-16 declarations.
    # Entities are rejected before parsing, not expanded and then measured.
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", data.replace(b"\x00", b""), re.I):
        raise _Unreadable("unsafe_xml", "document XML contains an entity or DTD declaration")
    depth = elements = 0
    root = None
    for event, element in ElementTree.iterparse(io.BytesIO(data), events=("start", "end")):
        if event == "start":
            depth += 1
            elements += 1
            if root is None:
                root = element
            if depth > bounds.max_xml_depth or elements > bounds.max_xml_elements:
                raise _Unreadable("xml_bound", "document XML exceeds its structural bound")
        else:
            depth -= 1
    if root is None:
        raise _Unreadable("malformed", "the document XML has no root")
    return root


def _word(document: AdmittedDocument, bounds: ExtractionBounds) -> ExtractionResult:
    if not document.data.startswith(b"PK\x03\x04"):
        raise _Unreadable("malformed", "the document is not a Word ZIP container")
    units, total = [], 0
    with zipfile.ZipFile(io.BytesIO(document.data)) as archive:
        entries = archive.infolist()
        if len(entries) > bounds.max_zip_entries:
            raise _Unreadable("zip_bound", "the document exceeds its ZIP entry bound")
        names = [entry.filename for entry in entries]
        if len(set(names)) != len(names):
            raise _Unreadable("malformed", "duplicate ZIP part names are ambiguous")
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            raise _Unreadable("malformed", "the container lacks the required Word parts")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                raise _Unreadable("unsafe_container", "a ZIP part has an unsafe path")
            if entry.flag_bits & 1:
                raise _Unreadable("encrypted", "encrypted document parts were not read")
            if entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise _Unreadable("unsupported", "a ZIP compression method is unavailable")
            if entry.file_size > bounds.max_stream_bytes:
                raise _Unreadable("stream_bound", "a ZIP part exceeds its declared size bound")
        if sum(entry.file_size for entry in entries) > bounds.max_bytes:
            raise _Unreadable("zip_bound", "expanded ZIP parts exceed the document byte bound")
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise _Unreadable("unsupported", "macro-enabled containers are not supported")
        with archive.open("[Content_Types].xml") as stream:
            content_types = _xml(stream.read(bounds.max_stream_bytes + 1), bounds)
        type_namespace = "{http://schemas.openxmlformats.org/package/2006/content-types}"
        main_type = ("application/vnd.openxmlformats-officedocument."
                     "wordprocessingml.document.main+xml")
        if (content_types.tag != type_namespace + "Types"
                or not any(element.tag == type_namespace + "Override"
                    and element.get("PartName") == "/word/document.xml"
                    and element.get("ContentType") == main_type for element in content_types)):
            raise _Unreadable("malformed", "the ZIP content types do not identify a Word document")
        parts = sorted(name for name in names if _LOCAL_PARTS.fullmatch(name))
        parts.remove("word/document.xml")
        parts.insert(0, "word/document.xml")
        for part in parts:
            with archive.open(part) as stream:
                data = stream.read(bounds.max_stream_bytes + 1)
            tree = _xml(data, bounds)
            if part == "word/document.xml" and (tree.tag != _WORD + "document"
                                               or tree.find(_WORD + "body") is None):
                raise _Unreadable("malformed", "the Word main part has no document body")
            for number, paragraph in enumerate(tree.iter(_WORD + "p"), 1):
                if len(units) >= bounds.max_units:
                    raise _Unreadable("unit_bound", "the document exceeds its part bound")
                chunks = []
                for element in paragraph.iter():
                    if element.tag == _WORD + "t":
                        chunks.append(element.text or "")
                    elif element.tag == _WORD + "tab":
                        chunks.append("\t")
                    elif element.tag in {_WORD + "br", _WORD + "cr"}:
                        chunks.append("\n")
                text = "".join(chunks)
                units.append(_located(number, "part", part, text, bounds, total))
                total += len(text)
        excluded = ("embedded objects and image-only content were not read",
                    "external relationships were not followed",
                    "tracked deletions and revision meaning were not assessed")
        if not units:
            units.append(_located(1, "part", "word/document.xml", "", bounds, total))
    return ExtractionResult(document.source_sha256, document.admission.media_id,
        document.format, len(document.data), len(units), tuple(units), excluded=excluded,
        parser="bounded-ooxml", parser_version="1")


def _pdf(document: AdmittedDocument, bounds: ExtractionBounds) -> ExtractionResult:
    if not document.data.startswith(b"%PDF-"):
        raise _Unreadable("malformed", "the input has no PDF container signature")
    if not library("pypdf").usable:
        raise _Unreadable("capability_unavailable", "the local PDF text reader is unavailable")
    import pypdf
    from pypdf.errors import PdfReadError

    units, total = [], 0
    try:
        reader = pypdf.PdfReader(io.BytesIO(document.data), strict=True)
    except PdfReadError as exc:
        raise _Unreadable("malformed", "the PDF container could not be parsed") from exc
    try:
        if reader.is_encrypted:
            raise _Unreadable("encrypted", "the encrypted PDF was not read")
        count = len(reader.pages)
        if count < 1:
            raise _Unreadable("malformed", "the PDF contains no readable pages", 0)
        if count > bounds.max_units:
            raise _Unreadable("unit_bound", "the PDF exceeds its declared page bound", count)
        for number, page in enumerate(reader.pages, 1):
            try:
                content = page.get_contents()
                if content is not None and len(content.get_data()) > bounds.max_stream_bytes:
                    units.append(LocatedText(number, "page", "pdf", TextState.UNAVAILABLE,
                        reason="the page content stream exceeds its declared byte bound"))
                    continue
                text = page.extract_text()
                if not isinstance(text, str):
                    units.append(LocatedText(number, "page", "pdf", TextState.UNAVAILABLE,
                        reason="the PDF reader did not return a text result"))
                    continue
                units.append(_located(number, "page", "pdf", text, bounds, total))
                total += len(text)
            except PdfReadError:
                units.append(LocatedText(number, "page", "pdf", TextState.UNAVAILABLE,
                    reason="this PDF page could not be parsed"))
    finally:
        reader.close()
    return ExtractionResult(document.source_sha256, document.admission.media_id,
        document.format, len(document.data), count, tuple(units),
        excluded=("image-only content was not read; no OCR was performed",
                  "embedded objects and external references were not followed"),
        parser="pypdf", parser_version=pypdf.__version__)


def _worker(document: AdmittedDocument, bounds: ExtractionBounds, connection) -> None:
    # Third-party parse diagnostics can quote untrusted original material.
    # This is a disposable process: suppress all of its logging, and send only
    # fixed input failures or value-free programmer stack locations to the parent.
    logging.disable(logging.CRITICAL)
    try:
        job = memory_limit(bounds.memory_bytes)
        del job  # The native handle remains open until this disposable process exits.
        readers = {DocumentFormat.TEXT: _plain, DocumentFormat.DOCX: _word,
                   DocumentFormat.PDF: _pdf}
        result = readers[document.format](document, bounds)
        connection.send(("result", result))
    except _Unreadable as exc:
        connection.send(("result", _result(document, failure=exc.kind,
            reason=exc.reason, observed=exc.observed)))
    except SandboxUnavailable:
        connection.send(("result", _result(document, failure="sandbox_unavailable",
            reason="hard parser memory containment is unavailable; nothing was read")))
    except (UnicodeError, zipfile.BadZipFile, ElementTree.ParseError, zlib.error):
        connection.send(("result", _result(document, failure="malformed",
            reason="the document container or encoded text could not be parsed")))
    except MemoryError:
        connection.send(("result", _result(document, failure="memory_bound",
            reason="the parser reached its hard memory bound; no complete reading is claimed")))
    except Exception as exc:  # noqa: BLE001 -- programming failures are surfaced, not hidden.
        # No exception value or input bytes enter shared diagnostics. Safe stack
        # locations distinguish a programmer failure from missing capability.
        frames = tuple((frame.filename, frame.lineno, frame.name)
                       for frame in traceback.extract_tb(exc.__traceback__))
        connection.send(("defect", (type(exc).__name__, frames)))
    finally:
        connection.close()


class LocalDocumentText:
    """The upload-owner-facing reader. It accepts immutable admitted bytes only."""

    def extract(self, document: AdmittedDocument, *,
                bounds: ExtractionBounds | None = None) -> ExtractionResult:
        bounds = bounds or ExtractionBounds()
        allowed, reason = document.admission.may_reach_reasoning()
        if not allowed or document.admission.kind is not MediaKind.DOCUMENT:
            raise ExtractionRefused(reason if not allowed else "the admission is not a document")
        if not document.admission.media_id.strip():
            raise ExtractionRefused("the admitted original has no identity")
        if not isinstance(document.data, bytes) or not 0 < len(document.data) <= bounds.max_bytes:
            raise ExtractionRefused("original bytes are absent or exceed their declared bound")
        if (not isinstance(document.format, DocumentFormat)
                or document.format is DocumentFormat.UNKNOWN):
            raise ExtractionRefused("the document format is not supported")
        if not re.fullmatch(r"[a-f0-9]{64}", document.source_sha256 or ""):
            raise ExtractionRefused("the original has no valid SHA-256 identity")
        if hashlib.sha256(document.data).hexdigest() != document.source_sha256:
            raise ExtractionRefused("the supplied bytes do not match the admitted original digest")
        refused = refuse_request(Route(
            PROCESSOR, (OPERATION,), configuration_known=True, off_premises=False))
        if refused:
            raise ExtractionRefused(refused[0])
        context = multiprocessing.get_context("spawn")
        incoming, outgoing = context.Pipe(duplex=False)
        process = context.Process(target=_worker, args=(document, bounds, outgoing), daemon=True)
        try:
            process.start()
            outgoing.close()
            if not incoming.poll(bounds.deadline_seconds):
                return _result(document, failure="deadline_bound",
                    reason="the local reader reached its deadline; no complete reading is claimed")
            try:
                kind, payload = incoming.recv()
            except EOFError:
                return _result(document, failure="worker_unavailable",
                    reason="the bounded reader stopped before returning its result")
            if kind == "defect":
                error_kind, frames = payload
                _log.error("local document reader defect: %s; safe stack %s", error_kind, frames)
                raise DocumentParserDefect(f"the document reader raised {error_kind}")
            if kind != "result" or not isinstance(payload, ExtractionResult):
                raise DocumentParserDefect(
                    "the document reader returned a malformed internal result")
            return _checked_worker_result(document, payload)
        finally:
            incoming.close()
            outgoing.close()
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(timeout=1.0)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1.0)


def _checked_worker_result(document, payload):
    """Revalidate child metadata; never repair an invalid result into success."""
    try:
        result = replace(payload, units=tuple(replace(unit) for unit in payload.units))
    except (TypeError, ValueError) as exc:
        raise DocumentParserDefect(
            "the bounded reader returned invalid extraction metadata") from exc
    expected = (document.source_sha256, document.admission.media_id,
                document.format, len(document.data))
    observed = (result.source_sha256, result.original_id, result.format, result.byte_length)
    if observed != expected:
        raise DocumentParserDefect("the extraction belongs to different original bytes")
    return result
