"""What the papers record - every point NM read from them - is shown with the answer, folded at its end, and the board marks what
could not be checked (plan AN.33, D18 and D20; research v14; piece 33m, with 33k folded in).

The owner, 1 Nov 2026: "this is horrible, writer shouldnt ignore any legally meaningful point s, how do we ensure this?" The writer
takes up in its advice what bears on it; whatever it takes up, every point of the papers' reading now also stands in a table code
builds from the record and folds at the end of the answer - each event once, with its paper and pages; one whose words code could not
find on a page, and a date whose numbers it finds nowhere in the papers, each said as such; the points read side by side, a difference
between papers among them; what settling set aside as not in the papers, with why; and the stretches that could not be read - so that
no point NM read disappears without trace, and no model keeps a ledger of where each went. The writer and the review are told so. The
board marks a date found nowhere and lists what was set aside, and finds a v14 record's words with the finder it was made under. The
papers are synthetic.
"""
from copy import deepcopy

import pytest

from nm.core_engine import matter_board, research, response_rendering, response_review, response_writer
from tests.test_the_answer_takes_up_every_order_and_point_or_says_why import Covering, answered, matter

pytestmark = pytest.mark.class_a

DIFFER = {"id": "C1", "kind": "papers_differ", "point": "The papers give the order a different date.", "why_it_matters": "Time runs "
          "from it.", "words": "", "anchored": False, "places": [], "quoted": "", "settled": "unanswered", "settled_why": ""}
GONE = {"kind": "event", "document": "order.pdf", "what": "An order of the court.", "words": "The court ordered the stores sealed",
        "why": "No such order is on the pages."}


def marked():
    """The synthetic matter's v14 record with a date found nowhere, a difference between papers, a point set aside and a stretch
    not read."""
    ctx, record, sources = matter()
    record = deepcopy(record)
    proposal = record["plan"]["proposal"]
    proposal["chronology"][1]["date_found"] = "nowhere"
    proposal["connections"], proposal["withdrawn"] = [DIFFER], [GONE]
    proposal["chronology_failures"] = [{"document": "order.pdf", "pages": "3", "reason": "SchemaViolation"}]
    return ctx, record, sources


def test_every_point_of_the_papers_reading_is_set_out_with_what_could_not_be_checked_said_as_such():
    ctx, record, sources = marked()
    papers = response_rendering.papers_record(record, ctx)
    events = record["plan"]["proposal"]["chronology"]
    assert [row["id"] for row in papers["events"]] == [event["id"] for event in events], "every point, once, in the plan's order"
    nowhere = papers["events"][1]
    assert (nowhere["date"], nowhere["dated"], nowhere["date_as_read"]) == ("undated", False, events[1]["date"]), (
        "a date found nowhere is shown undated with the reading's date beside it")
    assert [row["located"] for row in papers["events"]] == [event["anchored"] for event in events]
    assert any(not row["located"] for row in papers["events"]), "one whose words were not found on a page says so"
    first = papers["events"][0]
    assert set(first) >= {"id", "date", "dated", "kind", "what", "said_by", "document", "pages", "words", "located"}
    assert papers["together"] == [{"id": "C1", "kind": "papers_differ", "point": DIFFER["point"], "why": DIFFER["why_it_matters"],
                                   "located": False, "places": []}]
    assert papers["set_aside"] == [{"kind": "event", "document": "order.pdf", "what": GONE["what"], "why": GONE["why"]}]
    assert papers["unread"] == [{"document": "order.pdf", "pages": "3"}]
    assert response_rendering.papers_record({**record, "contract": research.WHOLE_FILE_CONTRACT}, ctx) is None, (
        "an answer made from a record before v14 is shown as it was made")


def test_the_answer_ends_with_the_record_of_the_papers_before_how_nm_checked_it_and_replays_as_saved():
    model = Covering(lambda round_, payload: [])
    sections, elements = answered(model)      # the turn is replayed as saved inside
    [papers] = [element for element in elements if element["kind"] == "PAPERS"]
    ctx, record, sources = matter()
    assert papers["text"] == response_rendering.PAPERS == "What your papers record"
    assert papers["papers"] == response_rendering.papers_record(record, ctx)
    kinds = [element["kind"] for element in elements]
    assert kinds.index("PAPERS") == len(kinds) - 1 - ("CHECKED" in kinds), "last, but for how NM checked the answer"
    assert "PAPERS" in response_rendering.NOT_PARAGRAPHS, "code's, not a paragraph of the answer"


def test_the_board_marks_a_date_found_nowhere_lists_what_was_set_aside_and_finds_words_as_the_record_was_made():
    ctx, record, sources = marked()
    event = record["plan"]["proposal"]["chronology"][1]
    shown = matter_board._event({"event": event, "also": []}, {})
    assert (shown["date"], shown["dated"], shown["date_as_read"]) == ("undated", False, event["date"])
    plain = matter_board._event({"event": {**event, "date_found": "words"}, "also": []}, {})
    assert "date_as_read" not in plain and plain["date"] == event["date"]
    assert matter_board._set_aside(record) == {"set_aside": [{"kind": "event", "document": "order.pdf", "what": GONE["what"],
                                                               "why": GONE["why"]}]}
    del record["plan"]["proposal"]["withdrawn"]
    assert matter_board._set_aside(record) == {}, "a plan made before v14 keeps no such list"
    rows = [{"documents": [{"name": "deed.pdf", "pages": [{"number": 1, "read_by": "local", "text": "The deed was signed."}]}]}]
    assert matter_board._pages(rows).version == research.EXACT_FINDER
    assert matter_board._pages(rows, research.TOLERANT_FINDER).version == research.TOLERANT_FINDER


def test_the_writer_and_the_review_are_told_every_point_stands_in_the_table():
    writer = " ".join(response_writer.SYSTEM_V14.split())
    assert ("one that would only add detail need not be named: every point of the papers' reading stands in the table of what the "
            "papers record, shown with the answer") in writer
    review = " ".join(response_review.SYSTEM_V12.split())
    assert ("Do not give an item that would only add detail: every point of the papers' reading stands in the table of what the "
            "papers record, shown with the answer") in review


def test_the_page_draws_the_record_of_the_papers_and_its_test_is_run():
    from tests.test_dispute_board_ui import PAGE_TESTS
    assert "papers_table.mjs" in PAGE_TESTS
