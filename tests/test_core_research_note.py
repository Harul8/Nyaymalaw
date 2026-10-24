"""A research note: one saved answer as a document (owner decisions, 15 Oct 2026: Word by
default, PDF as an option). Built by code from the saved turn; nothing is reworded.

Scripted turns prove the note's projection and the Word file's shape, not the answer.
"""
import io
import zipfile
from xml.etree import ElementTree

import pytest

from nm.core_engine import research_note
from nm.core_engine.conversation import chat_matter_id
from nm.core_engine.turn import saved_rows
from tests.test_core_calculation import MESSAGE, Calculating, Held, chain
from tests.test_core_served import OTHER, served  # noqa: F401 - pytest fixture
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture
from tests.test_core_turn_documents import DocumentModel, material

pytestmark = pytest.mark.class_a
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def saved(store, model, **changes):
    reply = run(store, model, **changes)
    return saved_rows(store.load(chat_matter_id("owner", reply["chat_id"])), "owner")[-1]


def paragraphs(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        for part in names - {"[Content_Types].xml"}:
            ElementTree.fromstring(archive.read(part))  # every part is well-formed XML
        tree = ElementTree.fromstring(archive.read("word/document.xml"))
    assert {"word/document.xml", "word/styles.xml", "_rels/.rels", "docProps/core.xml"} <= names
    return [("".join(t.text or "" for t in p.iter(W + "t")),
             (p.find(f"{W}pPr/{W}pStyle").get(W + "val") if p.find(f"{W}pPr/{W}pStyle") is not None else None))
            for p in tree.iter(W + "p")]


def test_the_note_keeps_the_question_answer_and_every_cited_source_word_for_word(store):
    row = saved(store, ScriptedModel(legal=True), message="Was the submission rejected?\nPlease check.")
    note = research_note.note(row, prepared_for="A. Advocate")
    assert note["question"] == "Was the submission rejected?\nPlease check."
    paragraph, = [block for block in note["blocks"] if block["kind"] == "paragraph"]
    element, = row["response"]["elements"]
    assert paragraph["text"] == element["text"] and paragraph["refs"] == list(range(1, len(note["sources"]) + 1))
    cited = {" ".join(source["text"].split()) for source in element["sources"]}
    assert {passage for source in note["sources"] for passage in source["passages"]} == cited
    assert all(source["described"] for source in note["sources"])
    assert note["prepared_for"] == "A. Advocate" and note["prepared_at"].endswith("IST")
    assert note["file_name"].startswith("Research note ") and "Was the submission rejected" in note["file_name"]


def test_the_word_file_is_well_formed_and_holds_the_note_in_order(store):
    row = saved(store, DocumentModel(), message="Please look at the memo.", documents=material())
    note = research_note.note(row, prepared_for="A. Advocate")
    data = research_note.docx(note, row["response"]["at"])
    assert data == research_note.docx(note, row["response"]["at"])  # the same note, the same bytes
    shown = paragraphs(data)
    texts = [text for text, _ in shown]
    assert shown[0] == ("Research note", "Title")
    assert texts.index("Question") < texts.index("Please look at the memo.") < texts.index("Answer") < texts.index("Sources")
    assert "• memo.pdf — 2 pages read, 1 not read" in texts
    assert "memo.pdf page 1 records the return unpaid. [1]" in texts
    assert "[1] memo.pdf · page 1 — Document you sent" in texts
    assert texts[-1] == note["provenance"]


def test_a_page_read_by_ai_is_marked_in_its_source_heading(store):
    row = saved(store, DocumentModel(), message="Please look at the memo.", documents=material())
    row["documents"][0]["pages"][0]["read_by"] = "ai"
    note = research_note.note(row, prepared_for="A. Advocate")
    assert research_note._source_heading(note["sources"][0]).endswith("(read by AI from a scan)")


def test_text_that_is_not_xml_safe_is_written_safely(store):
    row = saved(store, ScriptedModel(), message="Ampersand & <angle> \x0c form feed")
    data = research_note.docx(research_note.note(row, prepared_for="R & D <Chambers>"), row["response"]["at"])
    texts = [text for text, _ in paragraphs(data)]
    assert "Ampersand & <angle>  form feed" in texts


def test_a_time_limit_s_working_rows_are_kept_as_the_answer_showed_them(store):
    row = saved(store, Calculating(chain()), message=MESSAGE, held_acts=Held())
    note = research_note.note(row, prepared_for="A. Advocate")
    shown = [element for element in row["response"]["elements"] if element["kind"] == "WORKING"]
    working = [block for block in note["blocks"] if block["kind"] == "working"]
    assert [(b["text"], b["rows"], b["lists"]) for b in working] == [
        (e["text"], e["working"]["rows"], e["working"]["lists"]) for e in shown]
    texts = [text for text, _ in paragraphs(research_note.docx(note, row["response"]["at"]))]
    assert "Working: Last day to file the complaint" in texts
    assert "Last day: 14 October 2026 (Wednesday)" in texts and "• The dates are as reported." in texts


def test_an_answer_with_nothing_to_keep_has_no_note(store):
    row = saved(store, ScriptedModel())
    row["response"]["elements"] = []
    with pytest.raises(research_note.NoteUnavailable):
        research_note.note(row, prepared_for="A. Advocate")


def test_only_the_owner_can_fetch_a_note_and_the_word_file_downloads_as_word(served):
    reply = served.client.post("/api/turn", json={"message": "Inspect this reported account.", "turn_id": "t1"})
    assert reply.status_code == 200, reply.text
    base = f"/api/chats/{reply.json()['chat_id']}/turns/t1/note"
    note = served.client.get(base)
    assert note.status_code == 200 and note.json()["question"] == "Inspect this reported account."
    assert note.json()["prepared_for"] == "core-owner@example.test"
    word = served.client.get(base + ".docx")
    assert word.status_code == 200 and word.headers["cache-control"] == "no-store"
    assert word.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert 'attachment; filename="Research note ' in word.headers["content-disposition"]
    assert "filename*=UTF-8''Research%20note%20" in word.headers["content-disposition"]
    assert paragraphs(word.content)[0] == ("Research note", "Title")
    other = served.login(OTHER)
    assert other.get(base).status_code == 404 and other.get(base + ".docx").status_code == 404
    assert served.client.get(base.replace("/t1/", "/missing/")).status_code == 404


def test_an_answer_laid_out_for_the_advocate_keeps_its_order_with_its_folds_opened(store):
    """Rendering v18 (AN.6 piece 7; O13): In short as a line for each dispute, the line on what to
    do first, each section's sub-headings, points and numbered steps, More on this opened out under
    its heading, what NM needs by dispute and How NM checked this answer at the end."""
    from copy import deepcopy

    row = deepcopy(saved(store, ScriptedModel(legal=True)))
    plain = {"source": None, "sources": [], "refs": [], "inline_citations": [], "citation_markers": []}
    row["response"]["elements"] = [{**plain, **element} for element in [
        {"kind": "IN_SHORT", "text": "In short"},
        {"kind": "ROW", "text": "Cheque", "row": {"status": "shown", "by_when": {
            "day": "4 November 2026 (Wednesday)", "days": 14, "days_label": "Days left",
            "as_of": "21 October 2026 (Wednesday)"}}},
        {"kind": "ROW_ACTION", "text": "Criminal complaint under section 138"},
        {"kind": "ROW_READY", "text": "The cheque and the return memo"},
        {"kind": "ROW", "text": "Goods", "row": {"status": "note", "why": "the AI service did not respond"}},
        {"kind": "DO_FIRST", "text": "File the cheque complaint first."},
        {"kind": "HEADING", "text": "Cheque: Criminal complaint under section 138"},
        {"kind": "ADVICE", "text": "File by Wednesday."},
        {"kind": "SUBHEAD", "text": "Next steps"},
        {"kind": "STEP", "text": "Collect the originals."}, {"kind": "STEP", "text": "File the complaint."},
        {"kind": "MORE", "text": "Proof by affidavit."}, {"kind": "MORE", "text": "A civil suit is separate."},
        {"kind": "NEEDS", "text": "What I need from you"}, {"kind": "NEED_GROUP", "text": "Cheque"},
        {"kind": "NEED_ITEM", "text": "The cheque and the return memo"},
        {"kind": "YOUR_CALL", "text": "Your call"}, {"kind": "ASK", "text": "Pursue both debts together?"},
        {"kind": "CHECKED", "text": "How NM checked this answer", "checked": [
            {"part": "Cheque", "suggestions": [{"kind": "could_go", "text": "A paragraph repeats itself."}]}]}]]
    note = research_note.note(row, prepared_for="A. Advocate")
    assert [(block["kind"], block["text"]) for block in note["blocks"]] == [
        ("heading", "In short"),
        ("paragraph", "Cheque: by 4 November 2026 (Wednesday), 14 days left, as of 21 October 2026 (Wednesday)."),
        ("paragraph", "What to do: Criminal complaint under section 138"),
        ("paragraph", "Have ready: The cheque and the return memo"),
        ("paragraph", "Goods: not a full answer, because the AI service did not respond."),
        ("paragraph", "Do first: File the cheque complaint first."),
        ("heading", "Cheque: Criminal complaint under section 138"),
        ("paragraph", "File by Wednesday."),
        ("subheading", "Next steps"), ("paragraph", "1. Collect the originals."), ("paragraph", "2. File the complaint."),
        ("subheading", "More on this"), ("paragraph", "Proof by affidavit."), ("paragraph", "A civil suit is separate."),
        ("heading", "What I need from you"), ("subheading", "Cheque"),
        ("paragraph", "• The cheque and the return memo"),
        ("subheading", "Your call"), ("paragraph", "• Pursue both debts together?"),
        ("heading", "How NM checked this answer"), ("subheading", "Cheque"),
        ("paragraph", "Could go: A paragraph repeats itself.")]
    shown = paragraphs(research_note.docx(note, row["response"]["at"]))
    assert ("More on this", "Heading3") in shown and ("How NM checked this answer", "Heading2") in shown
