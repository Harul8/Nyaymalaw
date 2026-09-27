"""Admitted original bytes are read locally, bounded and located, never made facts."""
from __future__ import annotations

import hashlib
import io
import logging
import multiprocessing
import zipfile
from dataclasses import replace

import pytest

from nm.open_matter import document_local as local
from nm.open_matter.document_text_port import (
    AdmittedDocument,
    DocumentFormat,
    ExtractionBounds,
    ExtractionResult,
    LocatedText,
    TextState,
)
from nm.open_matter.media_contracts import MediaKind, Quarantine, Retention, admitted
from nm.shared.optional_adapter import library

pytestmark = pytest.mark.class_a


def document(data: bytes, format_: DocumentFormat = DocumentFormat.TEXT):
    admission = admitted("original-one", MediaKind.DOCUMENT,
        purpose="read this document for the fictional matter", authority="test advocate",
        quarantine=Quarantine.RELEASED, retention=Retention.MATTER_LIFE)
    return AdmittedDocument(data, format_, hashlib.sha256(data).hexdigest(), admission)


@pytest.fixture
def reader(monkeypatch):
    # Tests of parser/admission controls need no policy amendment. The separate
    # policy test below uses the actual deny-by-default contract and proves the
    # local adapter invokes it before a worker can be launched.
    monkeypatch.setattr(local, "refuse_request", lambda _route: [])
    return local.LocalDocumentText()


def pdf(pages: list[str | None], *, compress=False) -> bytes:
    """Small valid PDF bytes, generated without a second extraction library."""
    import zlib

    children = " ".join(f"{4 + index * 2} 0 R" for index in range(len(pages)))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{children}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for index, text in enumerate(pages):
        stream_id = 5 + index * 2
        objects.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>").encode())
        data = b"q 1 0 0 1 0 0 cm Q" if text is None else (
            f"BT /F1 12 Tf 20 700 Td ({text}) Tj ET").encode("ascii")
        filters = b""
        if compress:
            data, filters = zlib.compress(data), b" /Filter /FlateDecode"
        objects.append(b"<< /Length " + str(len(data)).encode() + filters + b" >>\nstream\n"
                       + data + b"\nendstream")
    result = b"%PDF-1.4\n"
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(result))
        result += f"{number} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(result)
    result += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    result += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    result += (f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
               f"startxref\n{xref}\n%%EOF\n").encode()
    return result


def word(xml: bytes | None = None, extra: dict[str, bytes] | None = None):
    body = xml or (b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Date 4 March 2026</w:t>'
        b'</w:r></w:p><w:p><w:r><w:t>Amount 10000</w:t></w:r></w:p></w:body></w:document>')
    types = (b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
        b'officedocument.wordprocessingml.document.main+xml"/></Types>')
    content = {"[Content_Types].xml": types, "word/document.xml": body, **(extra or {})}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in content.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_plain_text_keeps_original_values_and_locators_and_establishes_no_facts(reader):
    original = document("Date 4 March 2026\n₹10000\fsecond part".encode())
    result = reader.extract(original)
    assert result.complete and result.observed_units == 2
    assert result.units[0].text == "Date 4 March 2026\n₹10000"
    assert result.units[1].number == 2 and result.units[1].part == "utf8-text"
    assert result.source_sha256 == original.source_sha256
    assert result.original_id == original.admission.media_id
    assert not result.facts_established and not result.off_premises
    assert original.admission.quarantine is Quarantine.RELEASED


@pytest.mark.parametrize("state", [Quarantine.HELD, Quarantine.NOT_ASSESSED])
def test_unadmitted_material_is_refused_before_parser_start(reader, monkeypatch, state):
    original = document(b"do not read")
    original = replace(original, admission=replace(original.admission, quarantine=state))
    monkeypatch.setattr(local.multiprocessing, "get_context",
        lambda *_args: pytest.fail("unadmitted bytes reached the parser"))
    with pytest.raises(local.ExtractionRefused):
        reader.extract(original)


def test_digest_format_and_observed_byte_bounds_are_not_filename_guesses(reader, monkeypatch):
    original = document(b"original")
    monkeypatch.setattr(local.multiprocessing, "get_context",
        lambda *_args: pytest.fail("bad identity reached the parser"))
    for bad in [replace(original, source_sha256="0" * 64),
                replace(original, format="pdf"),
                replace(original, format=DocumentFormat.UNKNOWN), replace(original, data=b"")]:
        with pytest.raises(local.ExtractionRefused):
            reader.extract(bad)
    with pytest.raises(local.ExtractionRefused):
        reader.extract(original, bounds=ExtractionBounds(max_bytes=2))


def test_unknown_format_does_not_try_a_likely_parser(reader, monkeypatch):
    monkeypatch.setattr(local.multiprocessing, "get_context",
        lambda *_args: pytest.fail("an unknown format reached a guessed parser"))
    with pytest.raises(local.ExtractionRefused):
        reader.extract(replace(document(b"%PDF-1.4\nlooks like a PDF"),
                               format=DocumentFormat.UNKNOWN))


def test_the_actual_processing_policy_refuses_before_the_worker_runs(monkeypatch):
    from nm.open_matter.media_policy_contracts import ProcessingContract, refuse_request

    deny = ProcessingContract(frozenset({"biometrics"}), frozenset({"transcription"}),
                              frozenset({"logs"}))
    monkeypatch.setattr(local, "refuse_request", lambda route: refuse_request(route, deny))
    monkeypatch.setattr(local.multiprocessing, "get_context",
        lambda *_args: pytest.fail("denied processing reached the parser"))
    with pytest.raises(local.ExtractionRefused, match="approved set"):
        local.LocalDocumentText().extract(document(b"sensitive original"))


@pytest.mark.parametrize("data,failure", [(b"\xff\xfe\x00", "encoding_unavailable"),
    (b"binary\x00", "malformed"), (b"123456", "text_bound")])
def test_unread_text_is_a_failure_not_a_successful_empty_search(reader, data, failure):
    result = reader.extract(document(data), bounds=ExtractionBounds(max_unit_characters=5))
    assert result.failure == failure and not result.complete and result.reason
    assert not result.units


def test_a_blank_part_remains_named_and_prevents_a_complete_read(reader):
    result = reader.extract(document(b"read\f   \flast"))
    assert [unit.state for unit in result.units] == [TextState.EXTRACTED,
        TextState.NO_TEXT_LAYER, TextState.EXTRACTED]
    assert result.units[1].number == 2 and result.units[1].reason
    assert not result.complete


def test_word_parts_are_located_without_following_external_relationships(reader):
    header = (b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              b'<w:p><w:r><w:t>Header text</w:t></w:r></w:p></w:hdr>')
    result = reader.extract(document(word(extra={"word/header1.xml": header,
        "word/_rels/document.xml.rels": b"external content intentionally not followed"}),
        DocumentFormat.DOCX))
    assert result.complete and result.observed_units == 3
    assert result.units[0].part == "word/document.xml"
    assert result.units[2].part == "word/header1.xml"
    assert result.units[2].number == 1
    assert "Date 4 March 2026" == result.units[0].text
    assert any("external" in reason for reason in result.excluded)


@pytest.mark.parametrize("shape", ["dtd", "utf16_entity", "deep", "path", "macro", "oversized"])
def test_malformed_or_pathological_word_parts_are_not_reported_as_read(reader, shape):
    bounds = ExtractionBounds(max_xml_depth=8, max_stream_bytes=2048)
    extra = {}
    xml = None
    if shape == "dtd":
        xml = b'<!DOCTYPE doc [<!ENTITY secret SYSTEM "file:///do-not-open">]><doc>&secret;</doc>'
    elif shape == "utf16_entity":
        xml = '<!DOCTYPE doc [<!ENTITY a "text">]><doc>&a;</doc>'.encode("utf-16")
    elif shape == "deep":
        xml = b"<root>" + b"<x>" * 20 + b"</x>" * 20 + b"</root>"
    elif shape == "path":
        extra["../outside"] = b"do not write"
    elif shape == "macro":
        extra["word/vbaProject.bin"] = b"do not execute"
    else:
        extra["large.bin"] = b"x" * 10000
    result = reader.extract(document(word(xml, extra), DocumentFormat.DOCX), bounds=bounds)
    assert result.failure and not result.complete and not result.units


def test_pdf_text_and_missing_text_pages_are_distinct_or_reader_is_explicitly_unavailable(reader):
    result = reader.extract(document(pdf(["Known text 2026", None, "Final page"]),
        DocumentFormat.PDF))
    if not library("pypdf").usable:
        assert result.failure == "capability_unavailable" and not result.complete
        return
    assert result.failure is None and result.observed_units == 3
    assert [unit.state for unit in result.units] == [TextState.EXTRACTED,
        TextState.NO_TEXT_LAYER, TextState.EXTRACTED]
    assert [unit.number for unit in result.units] == [1, 2, 3]
    assert "Known text 2026" in result.units[0].text
    assert not result.complete


def test_pdf_compressed_stream_and_page_bounds_do_not_look_like_absence(reader):
    if not library("pypdf").usable:
        result = reader.extract(document(pdf(["text"]), DocumentFormat.PDF))
        assert result.failure == "capability_unavailable"
        return
    result = reader.extract(document(pdf(["a" * 1000], compress=True), DocumentFormat.PDF),
                            bounds=ExtractionBounds(max_stream_bytes=100))
    assert result.units[0].state is TextState.UNAVAILABLE and not result.complete
    result = reader.extract(document(pdf(["one", "two"]), DocumentFormat.PDF),
                            bounds=ExtractionBounds(max_units=1))
    assert result.failure == "unit_bound" and result.observed_units == 2


def test_malformed_pdf_signature_is_typed_and_never_reads_as_empty(reader):
    result = reader.extract(document(b"not a pdf", DocumentFormat.PDF))
    assert result.failure == "malformed" and result.observed_units is None and not result.complete


def test_a_broken_pdf_container_and_an_encrypted_pdf_never_look_read(reader):
    if not library("pypdf").usable:
        result = reader.extract(document(pdf(["text"]), DocumentFormat.PDF))
        assert result.failure == "capability_unavailable"
        return
    import pypdf

    result = reader.extract(document(b"%PDF-1.4\nbroken document", DocumentFormat.PDF))
    assert result.failure == "malformed" and not result.complete
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=600, height=800)
    writer.encrypt("not-supplied-to-the-parser")
    output = io.BytesIO()
    writer.write(output)
    result = reader.extract(document(output.getvalue(), DocumentFormat.PDF))
    assert result.failure == "encrypted" and not result.complete and not result.units


def test_a_programming_defect_is_not_swallowed_as_absence_or_logged_with_its_value(monkeypatch):
    def defective(_document, _bounds):
        raise NameError("SENSITIVE_SOURCE_VALUE")

    class Connection:
        def __init__(self):
            self.messages = []

        def send(self, value):
            self.messages.append(value)

        def close(self):
            pass

    connection = Connection()
    monkeypatch.setattr(local, "memory_limit", lambda _maximum: None)
    monkeypatch.setattr(local, "_plain", defective)
    prior = logging.root.manager.disable
    try:
        local._worker(document(b"original"), ExtractionBounds(), connection)
    finally:
        logging.disable(prior)
    assert connection.messages[0][0] == "defect"
    assert connection.messages[0][1][0] == "NameError"
    assert "SENSITIVE_SOURCE_VALUE" not in repr(connection.messages)


def test_the_configured_local_policy_runs_the_actual_reader_without_exporting():
    result = local.LocalDocumentText().extract(document(b"safe local document"))
    assert result.complete and result.units[0].text == "safe local document"
    assert result.off_premises is False and result.facts_established is False


def test_deadline_stops_the_disposable_worker_and_leaves_no_fact_or_clean_read(reader):
    before = {process.pid for process in multiprocessing.active_children()}
    result = reader.extract(document(b"bounded read"),
        bounds=ExtractionBounds(deadline_seconds=0.000001))
    assert result.failure == "deadline_bound" and not result.complete
    assert {process.pid for process in multiprocessing.active_children()} == before


def test_invalid_locator_or_missing_reason_cannot_manufacture_an_extraction():
    with pytest.raises(ValueError):
        LocatedText(0, "page", "pdf", TextState.EXTRACTED, "text")
    with pytest.raises(ValueError):
        LocatedText(1, "page", "pdf", TextState.EXTRACTED, "")
    with pytest.raises(ValueError):
        LocatedText(1, "page", "pdf", TextState.NO_TEXT_LAYER)
    with pytest.raises(ValueError):
        ExtractionBounds(max_units=1.2)
    for deadline in (float("nan"), float("inf")):
        with pytest.raises(ValueError):
            ExtractionBounds(deadline_seconds=deadline)
    with pytest.raises(ValueError, match="representable"):
        ExtractionBounds(deadline_seconds=10 ** 10000)
    with pytest.raises(ValueError):
        LocatedText(1, "part", "text", "unknown", reason="does not become a state")
    original = document(b"original")
    with pytest.raises(ValueError):
        ExtractionResult(original.source_sha256, "id", DocumentFormat.TEXT, 8, None,
                         facts_established=True)


@pytest.mark.parametrize("field,value", [
    ("source_sha256", "f" * 64), ("original_id", "other-original"),
    ("format", DocumentFormat.PDF), ("byte_length", 9),
    ("off_premises", True), ("facts_established", True),
])
def test_worker_metadata_is_validated_never_overwritten_to_look_safe(field, value):
    original = document(b"original")
    result = ExtractionResult(original.source_sha256, original.admission.media_id,
        DocumentFormat.TEXT, 8, 1, (LocatedText(1, "part", "text", TextState.EXTRACTED,
                                              "original"),))
    object.__setattr__(result, field, value)
    with pytest.raises(local.DocumentParserDefect):
        local._checked_worker_result(original, result)
