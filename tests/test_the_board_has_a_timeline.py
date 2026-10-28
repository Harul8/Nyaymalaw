"""The board has a timeline (plan AN.27, P9; invariant I4).

The papers an advocate sent are read for what they record (P8) and the plan keeps that list (P8c); the board now shows it: the events in
the plan's own order, each with where its words are and whether they were located on the page, and every paper with what NM could read
of it - so that a paper NM could not read, or could not make a timeline from, is said to be so and never reads as having nothing in it.
The board only reads what was saved; nothing is read again or added to. The papers here are synthetic.
"""
import pytest

from nm.core_engine import matter_board, research

pytestmark = pytest.mark.class_a

SOUND = {"code_problems": [], "verdict": "sound", "problems": []}


def understanding(empty=False):
    return {"summary": "s", "asked": [], "ruled_out": [], "parties": [], "related_points": [],
            "facts": [] if empty else [{"id": "F1", "fact": "A fact.", "certainty": "reported", "advocate_words": "a fact"}],
            "disputes": [] if empty else [{"id": "D1", "name": "Dispute 1", "between": ["a", "b"], "fact_ids": ["F1"],
                                           "legal_questions": [], "rights_at_stake": [], "relief_sought": [],
                                           "missing_facts": []}]}


def paper(name, pages=(1, 2), *, unread=(), recording=False):
    return {"document_ref": "doc", "name": name,
            "pages": [{"number": n, "text": f"{name} page {n}", "read_by": "local"} for n in pages],
            "unread": [{"number": n, "reason": "could not be made out"} for n in unread],
            **({"recording": True} if recording else {})}


def event(number, date, what, *, document="deed.pdf", source="t1:d1", pages=(1,), located=True, **more):
    return {"id": f"E{number}", "date": date, "sort": research.read_date(date), "kind": "transaction", "what": what,
            "said_by": "the deed", "document": document, "source": source, "pages": list(pages) if located else [],
            "words": f"words of {number}", "anchored": located, **more}


def turn(documents, events=None, failures=(), *, turn_id="t1", empty=False):
    """A saved turn whose plan kept `events` (None: a plan made before research v12)."""
    proposal = {"understanding": understanding(empty), "review_rounds": [SOUND]}
    if events is not None:
        proposal["chronology"], proposal["chronology_failures"] = events, list(failures)
    record = {"contract": research.CONTRACT if events is not None else "core_research_v11",
              "plan": {"proposal": proposal, "work": [], "issues": []}, "searches": {}, "failures": {}}
    return {"turn_id": turn_id, "message": "m", "documents": documents, "response": {"at": "2026-10-28T10:00:00+00:00"},
            "records": {}, "activities": {"research": record}}


def timeline(*args, **kw):
    return matter_board.board([turn(*args, **kw)])["timeline"]


def test_the_timeline_is_the_plans_events_in_its_order_with_where_each_is():
    events = [event(1, "30-10-1985", "A sale."),
              event(2, "17 August 2019", "A revision was allowed.", document="order.pdf", source="t1:d2", pages=(1, 2)),
              event(3, "undated", "Two suits are pending.", document="order.pdf", source="t1:d2", pages=(2,), kind="pending")]
    shown = timeline([paper("deed.pdf"), paper("order.pdf")], events)
    assert shown["state"] == "ready"
    assert [(e["id"], e["date"], e["dated"], e["document"], e["pages"], e["located"]) for e in shown["events"]] == [
        ("E1", "30-10-1985", True, "deed.pdf", [1], True), ("E2", "17 August 2019", True, "order.pdf", [1, 2], True),
        ("E3", "undated", False, "order.pdf", [2], True)]
    first, third = shown["events"][0], shown["events"][2]
    assert (first["what"], first["words"], first["said_by"], first["kind"]) == ("A sale.", "words of 1", "the deed", "transaction")
    assert third["kind"] == "pending" and "recording" not in first


def test_an_event_whose_words_were_not_located_is_not_shown_as_located():
    shown = timeline([paper("deed.pdf")], [event(1, "1985", "Something.", located=False)])
    assert shown["events"][0]["located"] is False and shown["events"][0]["pages"] == []


def test_every_paper_is_listed_with_what_it_gave_and_whether_it_was_read():
    papers = [paper("deed.pdf"), paper("order.pdf", unread=(3,)), paper("scan.pdf", pages=(), unread=(1, 2)), paper("memo.pdf")]
    events = [event(1, "1985", "A sale."), event(2, "2019", "An order.", document="order.pdf", source="t1:d2")]
    failures = [{"document": "memo.pdf", "pages": "1-2", "reason": "SchemaViolation"}]
    by_name = {d["name"]: d for d in timeline(papers, events, failures)["documents"]}
    assert by_name["deed.pdf"] == {"name": "deed.pdf", "pages_read": 2, "events": 1, "state": "read", "why": ""}
    assert (by_name["order.pdf"]["state"], by_name["order.pdf"]["why"]) == ("partly_read", "NM could not read page 3 of this paper.")
    assert (by_name["scan.pdf"]["state"], by_name["scan.pdf"]["why"]) == ("not_read", "NM could not read pages 1, 2 of this paper.")
    assert (by_name["memo.pdf"]["state"], by_name["memo.pdf"]["why"]) == (
        "not_read", "NM could not make a timeline from pages 1-2 of this paper.")


def test_a_stretch_that_failed_in_part_of_a_paper_leaves_it_partly_read():
    failures = [{"document": "deed.pdf", "pages": "3", "reason": "ModelError"}]
    (listed,) = timeline([paper("deed.pdf", pages=(1, 2, 3))], [event(1, "1985", "A sale.")], failures)["documents"]
    assert (listed["state"], listed["why"]) == ("partly_read", "NM could not make a timeline from page 3 of this paper.")


def test_a_paper_that_could_not_be_read_at_all_says_so_even_when_nothing_else_is_said():
    (listed,) = timeline([paper("scan.pdf", pages=())], [])["documents"]
    assert (listed["state"], listed["why"]) == ("not_read", "NM could not read this paper.")


def test_a_recording_is_listed_by_its_parts():
    shown = timeline([paper("call.mp3", pages=(1,), unread=(2,), recording=True)],
                     [event(1, "1 May 2020", "The sum was agreed.", document="call.mp3")])
    assert shown["documents"][0]["recording"] is True and shown["documents"][0]["why"] == "NM could not read part 2 of this paper."
    assert shown["events"][0]["recording"] is True


def test_papers_with_no_event_are_read_and_say_none():
    shown = timeline([paper("deed.pdf")], [])
    assert shown["state"] == "ready" and shown["events"] == []
    assert (shown["documents"][0]["state"], shown["documents"][0]["events"]) == ("read", 0)


def test_a_plan_made_before_the_timeline_says_none_was_made_and_no_papers_say_nothing():
    assert timeline([paper("deed.pdf")], None) == {
        "state": "not_made",
        "why": "NM did not make a timeline of the papers when it answered this conversation, so there is none to show."}
    assert timeline([], []) == {"state": "none"}
    assert matter_board.board([turn([paper("deed.pdf")], None)])["state"] == "ready"


def test_two_files_of_one_name_are_two_papers():
    shown = timeline([paper("deed.pdf"), paper("deed.pdf")], [event(1, "1985", "One."), event(2, "1986", "Two.", source="t1:d2")])
    assert [(d["name"], d["events"]) for d in shown["documents"]] == [("deed.pdf", 1), ("deed.pdf", 1)]


def test_papers_sent_in_earlier_turns_are_listed_with_those_of_the_turn_shown():
    first = turn([paper("deed.pdf")], [event(1, "1985", "A sale.")])
    second = turn([paper("order.pdf")], [event(1, "1985", "A sale."),
                                          event(2, "2019", "An order.", document="order.pdf", source="t2:d1")], turn_id="t2")
    shown = matter_board.board([first, second])
    assert shown["turn_id"] == "t2"
    assert [(d["name"], d["events"]) for d in shown["timeline"]["documents"]] == [("deed.pdf", 1), ("order.pdf", 1)]


def test_a_later_turn_that_set_out_no_matter_does_not_change_the_timeline_or_its_papers():
    first = turn([paper("deed.pdf")], [event(1, "1985", "A sale.")])
    thanks = turn([paper("late.pdf")], [], turn_id="t2", empty=True)
    shown = matter_board.board([first, thanks])
    assert shown["turn_id"] == "t1" and [d["name"] for d in shown["timeline"]["documents"]] == ["deed.pdf"]
