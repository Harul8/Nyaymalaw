"""The writer, the overview, the review and the date check are shown an event once that several papers record (plan AN.27, P22, part c).

The board lists such an event once (part b); the writer of a section, the writer of the overview and the independent review are now
shown the same events - the papers' chronology with an event that a copy of a page records again set out once, naming where else it
is (also_in: the other paper, its pages and their short IDs to cite) - and told what that means; and the date check is given the date
of an event as often as the writer was shown it. The papers here are synthetic: two papers that are copies of one page, each read
for the one event the page records, to different lengths.
"""
import pytest

from nm.core_engine import answer_sources, research, response_authorities, response_review, response_writer
from nm.core_engine.research import plan, retrieve
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_core_research import Model, searcher, understanding
from tests.test_core_writer_v13 import item, unit
from tests.test_the_chronology_of_each_document import event, row
from tests.test_the_plan_records_the_chronology import Beside, sent
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_and_review_are_shown_copies_read_differently import quiet
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a

SHORT = "Sale deed number 596/80 dated 5.1.1980 the vendor sold to the purchasers"
LONG = SHORT + " an extent of 6.06 acres in the survey number of the village"
SCRIPT = {
    "deed.pdf": [event("5.1.1980", "transaction", "The vendor sold the land.", SHORT, "the deed")],
    "scan.pdf": [event("5.1.1980", "transaction", "A sale of 6.06 acres.", LONG, "the scan")]}
SECTIONS = [{"dispute": "Dispute 1", "paragraphs": [{"kind": "summary", "text": "File by Wednesday."}]},
            {"dispute": "Dispute 2", "paragraphs": [{"kind": "summary", "text": "Serve the notice."}]}]


def matter(copies=True, disputes=1):
    other = passage() if copies else "A different paper entirely, of other words, about nothing the deed says. " * 12
    ctx = sent(row("t1", 1, "deed.pdf", 1, passage()), row("t1", 2, "scan.pdf", 1, other))
    kept = plan(Beside(SCRIPT, subject=understanding(1, disputes)), ctx)
    record = retrieve(kept, searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def cites_also(payload):
    shown = payload["papers_chronology"]
    return shown[0]["also_in"][0]["cite"][0]


def section(payload):
    return {"units": [
        unit("summary", "Appeal against the order", "row_action"),
        unit("summary", "Have the sale deed ready", "row_ready"),
        {"kind": "summary", "text": "The land was sold on 5.1.1980.", "place": "advice",
         "uses": [{"source_kind": "document", "source_id": cites_also(payload), "link_words": "land was sold"}]}],
        "checklist": [item(payload, "The sale deed", ["the sale deed"])], "time_limit_ids": [], "by_when": None}


def test_the_writer_is_shown_an_event_once_that_a_copy_of_its_page_records_again_and_may_cite_either_page():
    ctx, record, sources = matter()
    model = Writer(section)
    draft = response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    shown = model.seen[0][1]["papers_chronology"]
    assert len(record["plan"]["proposal"]["chronology"]) == 2 and len(shown) == 1
    (only,) = shown
    assert (only["paper"], only["pages"], only["what"]) == ("scan.pdf", [1], "A sale of 6.06 acres."), "the fullest quotation stands"
    (also,) = only["also_in"]
    assert (also["paper"], also["pages"]) == ("deed.pdf", [1]) and len(also["cite"]) == 1 and also["cite"] != only["cite"]
    assert all(c.startswith("DOC") and model.seen[0][1]["source_kinds"][c] == "document" for c in also["cite"] + only["cite"])
    (cited,) = [use for unit_ in draft["units"] for use in unit_.get("uses", ())]
    assert cited["role"] == "supplied_document" and cited["source_id"] == "t1:d1p1", "a page of the other paper is cited and admitted"
    assert response_writer.validate(draft, ctx, sources) == draft


def test_papers_that_are_not_copies_are_shown_each_event_and_an_event_alone_names_no_other_paper():
    ctx, record, sources = matter(copies=False)
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    shown = model.seen[0][1]["papers_chronology"]
    assert len(shown) == 2 and all("also_in" not in each for each in shown)
    ctx, record, sources = matter()
    offered = {tag: alias for alias, tag in answer_sources.aliases(sources).items()}
    assert len(response_writer._chronology_shown(record, offered)) == 2, "asked without the pages, every event is its own"
    assert len(response_writer._chronology_shown(record, offered, ctx)) == 1


def test_what_the_writer_is_shown_is_its_own_to_change_and_leaves_the_plan_as_it_was():
    ctx, record, sources = matter()
    offered = {tag: alias for alias, tag in answer_sources.aliases(sources).items()}
    shown = response_writer._chronology_shown(record, offered, ctx)
    shown[0]["pages"].append(99)
    shown[0]["also_in"][0]["pages"].append(98)
    again = response_writer._chronology_shown(record, offered, ctx)
    assert again[0]["pages"] == [1] and again[0]["also_in"][0]["pages"] == [1]
    assert [e["pages"] for e in record["plan"]["proposal"]["chronology"]] == [[1], [1]]


def test_the_overview_and_the_review_are_shown_the_same_events_once():
    ctx, record, sources = matter(disputes=2)
    writing = Writer(lambda payload: {"units": [{"kind": "next_step", "text": "File first.", "uses": []}]})
    response_writer.write_overview(writing, ctx, record, sources, sections=SECTIONS, contract=response_writer.PRESENTED_CONTRACT)
    overview = writing.seen[0][1]["papers_chronology"]
    assert len(overview) == 1 and overview[0]["also_in"][0]["paper"] == "deed.pdf"
    ctx, record, sources = matter()
    draft = response_writer.write_section(Writer(section), ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    reviewing = Reviewer()
    response_review.review(reviewing, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           contract=response_review.PRESENTED_CONTRACT)
    reviewed = reviewing.seen[0][1]["papers_chronology"]
    writer_saw = Writer(section)
    response_writer.write_section(writer_saw, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert reviewed == writer_saw.seen[0][1]["papers_chronology"] and len(reviewed) == 1


def test_the_date_check_is_given_the_date_of_an_event_as_often_as_the_writer_was_shown_it():
    ctx, record, sources = matter()
    stated = {"contract": response_writer.PRESENTED_CONTRACT, "units": [{"id": "t1:b1", "text": "The vendor sold it."}]}
    assert response_writer._shown_dates(stated, record, ctx).count("5.1.1980") == 1
    assert response_writer._shown_dates(stated, record).count("5.1.1980") == 2
    sold = {"contract": response_writer.PRESENTED_CONTRACT, "units": [{"id": "t1:b1", "text": "The land was sold on 5 January 1980."}]}
    assert response_writer.dates_not_given(sold, ctx, sources, None, record) == []
    other = {"contract": response_writer.PRESENTED_CONTRACT, "units": [{"id": "t1:b1", "text": "The land was sold on 6 January 1980."}]}
    assert [f["unit_ids"] for f in response_writer.dates_not_given(other, ctx, sources, None, record)] == [["t1:b1"]]


def test_the_prompts_say_what_also_in_is():
    writer = " ".join(response_writer.SYSTEM_V13.split())
    assert ("An event with also_in is one event that other papers record too, as a copy of a page does: set it out once, "
            "and cite whichever of its pages you rely on") in writer
    overview = " ".join(response_writer.OVERVIEW_SYSTEM_V13.split())
    assert "An event with also_in is one event that other papers record too: set it out once" in overview
    review = " ".join(response_review.SYSTEM_V11.split())
    assert "An event with also_in is one event that other papers record too; a piece that sets it out once leaves nothing out" in review
    for old in (response_writer.SYSTEM, response_writer.OVERVIEW_SYSTEM, response_review.SYSTEM_V10):
        assert "also_in" not in old
