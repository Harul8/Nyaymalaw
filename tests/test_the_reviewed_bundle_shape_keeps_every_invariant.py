"""The reviewed bundle, as a regression example with its invariants (plan AN.27, P15).

A 7-document, 56-page bundle of land papers was answered from an understanding of 18 or 19 facts that had lost the research, the
chronology, the pending proceedings and the figures. This is a synthetic matter of the same SHAPE - no word of the real papers: a
direction that runs over a page break past a stamp and a signature; orders and suits still pending; a scan that is a copy of another
page with one figure read differently; an understanding NM's own check never settled and a dispute with no legal question - carried
through the same steps, to show that each invariant AN.27 named holds where the pieces meet, not only where each was built:

I1 words quoted from a paper are found wherever it holds them; I2 the check is told what the advocate restricted and that research is
the point; I3 what has not been assessed is said so; I4 the papers' events are a list, anchored to pages, dated and ordered by code;
I5 each paper is read on its own and what it gave reaches the writer and the review; I6 a figure two copies give differently is
flagged by code, never settled by a model; I7 whom the advocate acts for is asked.

Scripted models prove the wiring and the invariants, not the quality of any reading; the live measurements are on AN.27.
"""
from functools import cache

import pytest

from nm.core_engine import answer_sources, matter_board, research, response_authorities, response_review, response_writer
from nm.core_engine.research import plan, retrieve
from tests.test_copies_that_read_a_figure_differently import passage
from tests.test_core_research import Model, searcher, understanding
from tests.test_core_writer_v13 import unit
from tests.test_the_chronology_of_each_document import event, row
from tests.test_the_plan_records_the_chronology import Beside, sent
from tests.test_the_review_is_shown_the_chronology import Reviewer
from tests.test_the_writer_is_shown_the_chronology import Writer

pytestmark = pytest.mark.class_a

DIRECTION = "the name of the original owner shall continue to be maintained in the revenue records pending the decision of the civil court"
REGISTER = [
    (1, "Register of the village, certified. The High Court directed that the name of the original owner shall continue to be maintained in the"
        "\n\nPage 1 of 3"),
    (2, "Certified copy No. 55\n[stamp: CERTIFIED TRUE COPY]\n[signature]\nrevenue records pending the decision of the civil court. "
        "Mutation was ordered on 17-3-2008 in file B/54/2008."),
    (3, passage("6.06"))]
ORDERS = [(1, "ORDER. The Joint Collector allowed the revision on 17 August 2019. "
              "Suits O.S. 891 of 2014 and 892 of 2014 are pending before the District Court.")]
COPY = [(1, passage("6.16"))]

SCRIPT = {
    "register.pdf": [
        event("17-3-2008", "order", "Mutation was ordered in file B/54/2008.", "Mutation was ordered on 17-3-2008 in file B/54/2008"),
        event("undated", "order", "The High Court directed that the original owner's name stay in the revenue records.", DIRECTION,
              "the High Court")],
    "order.pdf": [
        event("17 August 2019", "order", "The revision was allowed.", "The Joint Collector allowed the revision on 17 August 2019",
              "the Joint Collector"),
        event("undated", "pending", "Two suits are pending before the District Court.",
              "Suits O.S. 891 of 2014 and 892 of 2014 are pending before the District Court"),
        event("1 January 2021", "filing", "A petition was filed.", "The petition was filed on a day no page gives")],
}
REVISE = {"verdict": "revise", "problems": [{"problem": "The understanding does not set out the chronology.", "fix": "Add it."}]}


def saved(name, pages):
    return {"document_ref": "doc", "name": name, "unread": [], "pages": [{"number": n, "text": text, "read_by": "local"} for n, text in pages]}


@cache
def matter():
    papers = [("register.pdf", REGISTER), ("order.pdf", ORDERS), ("copy.pdf", COPY)]
    ctx = sent(*[row("t1", index, name, number, text) for index, (name, pages) in enumerate(papers, 1) for number, text in pages])
    subject = understanding(1, 1)
    subject["facts"].append({"id": "F2", "fact": "The High Court directed that the original owner's name stay in the records.",
                             "advocate_words": "the name of the original owner shall continue to be maintained in the revenue records",
                             "certainty": "reported"})
    subject["disputes"].append({"id": "D2", "name": "Dispute 2", "between": ["client", "other party"], "fact_ids": ["F2"],
                                "legal_questions": [], "rights_at_stake": [], "relief_sought": [], "missing_facts": [],
                                "why_it_matters": "Dispute 2 decides what the client keeps."})
    model = Beside(SCRIPT, subject=subject, checks=[REVISE, REVISE], revisions=[subject])
    kept = plan(model, ctx, restrictions=lambda: [])
    record = retrieve(kept, searcher(), ctx, model=Model())
    sources = answer_sources.build(ctx, record)
    first = {"turn_id": "t1", "message": "m1", "documents": [saved(name, pages) for name, pages in papers],
             "response": {"at": "2026-10-28T10:00:00+00:00"}, "records": {}, "activities": {}}
    second = {"turn_id": "t2", "message": "Find the applicable law.", "documents": [],
              "response": {"at": "2026-10-28T10:05:00+00:00"}, "records": {}, "activities": {"research": record}}
    return {"ctx": ctx, "subject": subject, "model": model, "kept": kept, "record": record, "sources": sources,
            "board": matter_board.board([first, second])}


def written(contract=response_writer.PRESENTED_CONTRACT):
    m = matter()
    model = Writer(lambda payload: {"units": [unit("summary", "Appeal against the order", "row_action"),
                                              unit("summary", "Have the register ready", "row_ready")],
                                    "checklist": [], "time_limit_ids": [], "by_when": None})
    draft = response_writer.write_section(model, m["ctx"], m["record"], m["sources"], index=0, contract=contract)
    return model.seen[0][1], draft


def test_i1_a_direction_that_runs_over_a_page_break_past_a_stamp_is_found_and_a_changed_word_is_named():
    m = matter()
    assert research.code_checks(m["subject"], m["ctx"]) == [], "the quotation is found across the break"
    damaged = {**m["subject"], "facts": [m["subject"]["facts"][0], {
        **m["subject"]["facts"][1], "advocate_words": "the name of the original owner shall be struck from the revenue records"}]}
    (problem,) = research.code_checks(damaged, m["ctx"])
    assert "not found from" in problem["problem"] and "struck" in problem["problem"]
    assert m["board"]["facts"][1]["from"] == "document", "and the board knows where it comes from"


def test_i2_the_check_is_told_what_the_advocate_restricted_and_that_research_is_the_point():
    calls = [prompt for prompt in matter()["model"].calls if prompt.operation == "core_research_check"]
    assert calls and all("Instructions from the advocate limiting our work" in prompt.user and prompt.user.count("none.") >= 1
                         for prompt in calls)
    assert "Do not report research as a problem because the advocate's words did not literally ask for advice" in research.CHECK


def test_i3_what_has_not_been_assessed_is_said_so_on_the_board():
    board = matter()["board"]
    by_name = {d["name"]: d for d in board["disputes"]}
    assert by_name["Dispute 2"]["law"]["state"] == "not_assessed" and "has not been assessed" in by_name["Dispute 2"]["law"]["why"]
    assert board["understanding"]["confirmed"] is False and board["understanding"]["open_points"], "NM's own check was not satisfied"


def test_i4_the_papers_events_are_a_list_anchored_dated_and_ordered_by_code_with_the_pending_and_the_unlocated_marked():
    events = matter()["kept"]["proposal"]["chronology"]
    assert [(e["sort"], e["kind"], e["anchored"]) for e in events] == [
        ("2008-03-17", "order", True), ("2019-08-17", "order", True), ("2021-01-01", "filing", False),
        ("", "order", True), ("", "pending", True)]
    run_over = next(e for e in events if e["words"] == DIRECTION)
    assert run_over["pages"] == [1, 2] and run_over["document"] == "register.pdf", "the direction over the break has both pages"
    assert next(e for e in events if e["kind"] == "pending")["pages"] == [1]
    assert [e["id"] for e in events] == ["E1", "E2", "E3", "E4", "E5"]


def test_i5_each_paper_is_read_on_its_own_and_what_it_gave_reaches_the_board_the_writer_and_the_review():
    m = matter()
    reads = [prompt.user for prompt in m["model"].calls if prompt.operation == "core_research_chronology"]
    assert len(reads) == 3 and all(sum(f'Document: "{name}"' in text for name in ("register.pdf", "order.pdf", "copy.pdf")) == 1
                                   for text in reads)
    payload, draft = written()
    assert [e["id"] for e in payload["papers_chronology"]] == ["E1", "E2", "E3", "E4", "E5"]
    assert next(e for e in payload["papers_chronology"] if e["kind"] == "pending")["cite"][0].startswith("DOC")
    review = Reviewer()
    response_review.review(review, m["ctx"], m["record"], m["sources"], draft, research.execution(m["record"]),
                           authority_evidence=response_authorities.check(m["ctx"], m["record"], m["sources"], draft),
                           contract=response_review.PRESENTED_CONTRACT)
    assert [e["id"] for e in review.seen[0][1]["papers_chronology"]] == ["E1", "E2", "E3", "E4", "E5"]
    timeline = m["board"]["timeline"]
    assert timeline["state"] == "ready" and [d["name"] for d in timeline["documents"]] == ["register.pdf", "order.pdf", "copy.pdf"]


def test_i6_a_figure_two_copies_read_differently_is_flagged_by_code_to_the_board_the_writer_and_the_review():
    m = matter()
    (found,) = m["board"]["copies"]
    assert {found["first"]["document"], found["second"]["document"]} == {"register.pdf", "copy.pdf"}
    assert [(f["first"], f["second"]) for f in found["figures"]] == [("6.06", "6.16")]
    payload, draft = written()
    (shown,) = payload["copies_read_differently"]
    assert (shown["figures"][0]["first"], shown["figures"][0]["second"]) == ("6.06", "6.16")
    review = Reviewer()
    response_review.review(review, m["ctx"], m["record"], m["sources"], draft, research.execution(m["record"]),
                           authority_evidence=response_authorities.check(m["ctx"], m["record"], m["sources"], draft),
                           contract=response_review.PRESENTED_CONTRACT)
    assert review.seen[0][1]["copies_read_differently"] == payload["copies_read_differently"]
    assert "Counting is code's work for extents" in response_writer.SYSTEM_V13


def test_i7_whom_the_advocate_acts_for_is_asked_where_the_papers_show_opposite_sides():
    assert "ask that first, as one question" in " ".join(response_writer.SYSTEM_V13.split())
    assert "that is the first such question" in " ".join(response_writer.OVERVIEW_SYSTEM_V13.split())
    assert "leave ruled_out empty" in " ".join(research.UNDERSTAND.split()), "and 'ruled_out' is the advocate's own instructions only"
