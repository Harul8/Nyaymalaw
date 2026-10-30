"""The writer and the independent review are shown the figures that copies of a page read differently (plan AN.27, P13; invariant I6).

Two scans of one passage gave 6.06 and 6.16 and NM called it a disagreement in the papers; copies are now found by code (copy_figures)
and the current writer and the review of its section are shown both readings with the short IDs of the two pages, told to give both and
choose neither, and to leave the arithmetic of extents to code. The earlier writers and reviews see what they always did. The papers
here are synthetic.
"""
import json

import pytest

from nm.core_engine import answer_sources, research, response_authorities, response_review, response_writer
from nm.core_engine.research import plan, retrieve
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_core_research import Model, searcher
from tests.test_core_writer_v13 import unit
from tests.test_the_chronology_of_each_document import row
from tests.test_the_plan_records_the_chronology import Beside, sent
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a


def quiet(payload):
    return {"units": [unit("summary", "Appeal against the order", "row_action"), unit("summary", "Have the sale deed ready", "row_ready")],
            "checklist": [], "time_limit_ids": [], "by_when": None}


def copies(first="6.06", second="6.16"):
    ctx = sent(row("t1", 1, "deed.pdf", 3, passage(first)), row("t1", 2, "scan.pdf", 1, passage(second)))
    record = retrieve(plan(Beside({}), ctx), searcher(), ctx, model=Model())
    return ctx, record, answer_sources.build(ctx, record)


def test_the_current_writer_is_shown_both_readings_with_the_short_ids_of_the_pages():
    ctx, record, sources = copies()
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    prompt, payload = model.seen[0]
    (found,) = payload["copies_read_differently"]
    assert (found["first"]["paper"], found["first"]["page"], found["second"]["paper"], found["second"]["page"]) == (
        "deed.pdf", 3, "scan.pdf", 1)
    assert found["first"]["cite"].startswith("DOC") and found["second"]["cite"].startswith("DOC") and found["first"]["cite"] != found["second"]["cite"]
    assert payload["source_kinds"][found["first"]["cite"]] == "document" == payload["source_kinds"][found["second"]["cite"]]
    (figure,) = found["figures"]
    assert (figure["first"], figure["second"]) == ("6.06", "6.16") and figure["after"].endswith("an extent of")
    assert "papers_chronology" not in payload, "no events were read from these papers"
    assert "id" not in json.dumps(found["first"]) and "t1:d1" not in json.dumps(found)


def test_nothing_is_shown_where_no_copy_reads_differently_and_the_earlier_writer_is_shown_nothing():
    ctx, record, sources = copies("6.06", "6.06")
    model = Writer(quiet)
    response_writer.write_section(model, ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    assert "copies_read_differently" not in model.seen[0][1]
    ctx, record, sources = copies()
    earlier = Writer(lambda payload: {"units": [{"kind": "summary", "text": "In short.", "uses": []}], "checklist": [],
                                      "time_limit_ids": []})
    response_writer.write_section(earlier, ctx, record, sources, index=0)
    assert "copies_read_differently" not in earlier.seen[0][1]


def test_the_review_of_a_section_is_shown_the_same_and_the_earlier_review_is_not():
    ctx, record, sources = copies()
    draft = response_writer.write_section(Writer(quiet), ctx, record, sources, index=0, contract=response_writer.PRESENTED_CONTRACT)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, draft, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, draft),
                           contract=response_review.PRESENTED_CONTRACT)
    prompt, payload = model.seen[0]
    assert payload["copies_read_differently"][0]["figures"][0]["second"] == "6.16" and prompt.system == response_review.SYSTEM_V11
    older = response_writer.write_section(Writer(lambda payload: {"units": [{"kind": "summary", "text": "In short.", "uses": []}],
                                                                 "checklist": [], "time_limit_ids": []}),
                                          ctx, record, sources, index=0)
    model = Reviewer()
    response_review.review(model, ctx, record, sources, older, research.execution(record),
                           authority_evidence=response_authorities.check(ctx, record, sources, older),
                           contract=response_review.MISLEADS_CONTRACT)
    assert "copies_read_differently" not in model.seen[0][1]


def test_the_prompts_say_to_give_both_readings_and_to_leave_the_arithmetic_of_extents_to_code():
    writer = " ".join(response_writer.SYSTEM_V13.split())
    for part in ("Where copies_read_differently is given, it lists figures that two copies of one page read differently",
                 "give both readings and say that the copies differ, never choose between them, and do not call it a disagreement "
                 "in the papers themselves",
                 "Counting is code's work for extents as it is for days: do not add, subtract or convert acres, guntas or cents yourself",
                 "say what would be added or taken away and that it has not been worked out"):
        assert part in writer, part
    review = " ".join(response_review.SYSTEM_V11.split())
    for part in ("When copies_read_differently is given, the piece must give both readings of such a figure and choose neither",
                 "adds, subtracts or converts extents (acres, guntas, cents) where the papers do not state the result"):
        assert part in review, part
    assert "copies_read_differently" not in response_writer.SYSTEM and "copies_read_differently" not in response_review.SYSTEM_V10


def shown(*rows):
    ctx = sent(*rows)
    record = retrieve(plan(Beside({}), ctx), searcher(), ctx, model=Model())
    sources = answer_sources.build(ctx, record)
    return response_writer._payload(ctx, record, sources, None, None, response_writer.parts(record), 0, None, worded=True)


def test_two_files_of_one_name_are_two_papers_and_a_recording_is_not_compared():
    payload = shown(row("t1", 1, "deed.pdf", 1, passage("6.06")), row("t2", 1, "deed.pdf", 1, passage("6.16")))
    (found,) = payload["copies_read_differently"]
    assert found["first"]["paper"] == found["second"]["paper"] == "deed.pdf" and found["first"]["cite"] != found["second"]["cite"]
    payload = shown(row("t1", 1, "a.mp3", 1, passage("6.06"), recording=True), row("t1", 2, "b.mp3", 1, passage("6.16"), recording=True))
    assert "copies_read_differently" not in payload
