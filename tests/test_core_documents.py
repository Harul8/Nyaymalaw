"""Receiving an advocate's documents (owner decisions, 15 Oct 2026): the malware check,
local reading, sealed storage in the advocate's own space and exact reloading.

The checker is a recorded outcome here; the local reader and the sealed store are real.
"""
import re

import pytest

from nm.app.composition import ROOT, _document_desk
from nm.core_engine import documents
from nm.core_engine.documents import DocumentRefused
from nm.shared.egress_contracts import Gatekeeper
from nm.shared.egress_policy import egress_policy
from nm.shared.store_file_store import FileMatterStore

pytestmark = pytest.mark.class_a
ADVOCATE, OTHER = "owner@example.test", "other@example.test"


class Checker:
    name = "recorded-check"

    def __init__(self, state="clear", reason="no threat found"):
        self.state, self.reason, self.seen = state, reason, []

    def check(self, data):
        self.seen.append(data)
        return self.state, self.reason


def pdf(pages):
    """A minimal PDF: each page carries a line of text or is blank, like a scan."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET" if text else ""
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objects)} 0 R "
                       f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


@pytest.fixture
def desk(tmp_path):
    store = FileMatterStore(tmp_path, key="test-documents-key-for-these-tests-only-1")
    made = _document_desk(store, tmp_path, Gatekeeper(policy=egress_policy(ROOT)), {})
    made.checker = Checker()
    return made


def originals(tmp_path, record):
    chunk = re.compile(re.escape(record["document_id"]) + r"-\d{1,4}\.nm")
    return sorted(path.name for path in tmp_path.rglob("*") if chunk.fullmatch(path.name))


def test_a_cleared_text_document_is_read_sealed_and_reloaded_exactly_by_its_owner_only(desk, tmp_path):
    words = b"The cheque was returned on 3 October 2026 for insufficient funds."
    record = desk.receive(ADVOCATE, "note.txt", words)
    assert desk.checker.seen == [words]
    assert documents.summary(record)["state"] == "read"
    assert record["pages"] == [{"number": 1, "state": "read", "text": words.decode(), "read_by": "local"}]
    assert originals(tmp_path, record) and all(words not in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())
    ref = documents.reference(record)
    assert desk.load(ADVOCATE, ref) == record
    with pytest.raises(DocumentRefused):
        desk.load(OTHER, ref)


def test_a_scanned_pdf_page_is_listed_unread_for_the_ai_and_text_pages_are_read_here(desk):
    record = desk.receive(ADVOCATE, "memo.pdf", pdf(["Return memo: funds insufficient.", ""]))
    first, second = record["pages"]
    assert first == {"number": 1, "state": "read", "text": "Return memo: funds insufficient.", "read_by": "local"}
    assert second["state"] == "unread" and second["code"] == "scanned"
    assert documents.needs_transcription(record) == [2]
    shown = documents.summary(record)
    assert shown["state"] == "partly_read" and shown["pages_total"] == 2 and "Return memo" not in str(shown)


def word(paragraphs):
    """A minimal Word document, one paragraph per entry; an empty entry is an empty paragraph."""
    import io
    import zipfile
    from xml.sax.saxutils import escape
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>' if text else "<w:p/>"
                   for text in paragraphs)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/'
                   'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
                   f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    return data.getvalue()


def test_a_word_document_is_one_page_of_its_paragraphs_and_no_empty_paragraph_waits_for_the_ai(desk):
    # Found in the owner's end-to-end run (16 Oct 2026): empty paragraphs were listed as
    # scanned pages waiting for the AI, and each paragraph was counted as a page.
    record = desk.receive(ADVOCATE, "complaint.docx", word(["To,", "", "The Station House Officer.", "", "",
                                                           "Sub: complaint of cheating."]))
    assert record["pages"] == [{"number": 1, "state": "read", "read_by": "local",
                                "text": "To,\n\nThe Station House Officer.\n\nSub: complaint of cheating."}]
    assert documents.needs_transcription(record) == []
    shown = documents.summary(record)
    assert shown["state"] == "read" and shown["pages_total"] == 1 and shown["waiting_for_ai"] == 0


def test_a_word_or_text_file_without_words_is_unread_and_never_sent_to_the_ai(desk):
    for name, data in (("blank.docx", word(["", ""])), ("blank.txt", b"\f\f")):
        record = desk.receive(ADVOCATE, name, data)
        page, = record["pages"]
        assert page["state"] == "unread" and page["code"] == "unreadable" and "no words" in page["reason"]
        assert documents.needs_transcription(record) == []


def test_a_word_reader_that_returns_nothing_keeps_its_own_reason(desk, monkeypatch):
    # Seen in the owner's run (16 Oct 2026): a reader that reached its deadline was
    # reported as a document with no words.
    from nm.open_matter.document_text_port import ExtractionResult
    def deadline(document, bounds=None):
        return ExtractionResult(document.source_sha256, document.admission.media_id, document.format,
                                len(document.data), None, failure="deadline",
                                reason="the local reader reached its deadline; no complete reading is claimed",
                                parser="bounded", parser_version="1")
    monkeypatch.setattr(desk.reader, "extract", deadline)
    record = desk.receive(ADVOCATE, "complaint.docx", word(["To,", "The Station House Officer."]))
    assert record["pages"] == [] and "deadline" in record["failure"]
    assert documents.summary(record)["state"] == "not_read" and documents.needs_transcription(record) == []


def test_a_text_file_keeps_its_form_feed_pages_and_skips_empty_ones(desk):
    record = desk.receive(ADVOCATE, "notes.txt", b"First page.\f\fThird page.")
    assert [(page["number"], page["text"]) for page in record["pages"]] == [(1, "First page."), (3, "Third page.")]
    assert documents.needs_transcription(record) == []


@pytest.mark.parametrize("state", ["held", "unavailable"])
def test_a_file_the_check_does_not_clear_is_neither_read_nor_kept(desk, tmp_path, state):
    desk.checker = Checker(state, "the check did not clear it")
    record = desk.receive(ADVOCATE, "note.txt", b"words")
    assert record["pages"] == [] and originals(tmp_path, record) == []
    assert documents.summary(record)["state"] == "held"
    assert desk.load(ADVOCATE, documents.reference(record))["check"]["state"] == state


def test_unsupported_and_oversized_files_are_refused_before_any_check(desk, monkeypatch):
    for name, data in [("tool.exe", b"MZ\x90\x00"), ("note.txt", b"\xff\xfe\x00bad"), ("x.docx", b"%not")]:
        with pytest.raises(DocumentRefused):
            desk.receive(ADVOCATE, name, data)
    monkeypatch.setattr(documents, "MAX_BYTES", 4)
    with pytest.raises(DocumentRefused):
        desk.receive(ADVOCATE, "note.txt", b"too long")
    assert desk.checker.seen == []


def test_a_reference_names_one_exact_record(desk):
    record = desk.receive(ADVOCATE, "note.txt", b"words")
    ref = documents.reference(record)
    for wrong in (ref[:-1] + ("0" if ref[-1] != "0" else "1"), "doc_x", "../" + ref, ""):
        with pytest.raises(DocumentRefused):
            desk.load(ADVOCATE, wrong)
    altered = dict(record, name="other.txt")
    with pytest.raises(DocumentRefused):
        documents.checked(altered, ref)


def test_nothing_read_can_be_recorded_for_a_document_the_check_did_not_clear():
    with pytest.raises(ValueError):
        documents.receipt(document_id="doc_" + "0" * 24, name="a.txt", fmt="text", sha256="0" * 64, size=1,
                          received_at="2026-10-15T00:00:00+00:00",
                          check={"state": "held", "reason": "flagged", "checker": "recorded-check"},
                          pages=[{"number": 1, "state": "read", "text": "x", "read_by": "local"}],
                          observed_pages=1)


def test_documents_too_long_for_one_question_are_refused_never_cut(desk, monkeypatch):
    first = desk.receive(ADVOCATE, "note.txt", b"0123456789")
    second = desk.receive(ADVOCATE, "other.txt", b"abcdefghij")
    material = documents.turn_material([first, second])
    assert [d["pages"][0]["text"] for d in material] == ["0123456789", "abcdefghij"]
    assert documents.checked_material(material) == material
    monkeypatch.setattr(documents, "MAX_TURN_CHARACTERS", 15)
    with pytest.raises(DocumentRefused, match="too long"):
        documents.turn_material([first, second])


def test_a_question_refuses_held_repeated_or_too_many_documents(desk, monkeypatch):
    note = desk.receive(ADVOCATE, "note.txt", b"words")
    desk.checker = Checker("held", "flagged")
    held = desk.receive(ADVOCATE, "bad.txt", b"words")
    for records, why in [([held], "malware"), ([note, note], "twice")]:
        with pytest.raises(DocumentRefused, match=why):
            documents.turn_material(records)
    monkeypatch.setattr(documents, "MAX_TURN_DOCUMENTS", 0)
    with pytest.raises(DocumentRefused, match="At most"):
        documents.turn_material([note])


@pytest.mark.parametrize("change", [
    lambda m: m[0].update(name=""), lambda m: m[0]["pages"][0].update(read_by="someone"),
    lambda m: m[0]["pages"].append(dict(m[0]["pages"][0])), lambda m: m[0].update(extra=1),
    lambda m: m[0]["unread"].append({"number": 9}),
])
def test_saved_question_material_must_keep_its_exact_shape(desk, change):
    material = documents.turn_material([desk.receive(ADVOCATE, "note.txt", b"words")])
    change(material)
    with pytest.raises(ValueError):
        documents.checked_material(material)
