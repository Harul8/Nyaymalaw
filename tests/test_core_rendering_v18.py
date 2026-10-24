"""Rendering v18: the answer as the advocate reads it (owner decisions P39-P41 and P44, 24 Oct
2026; plan AN.6 piece 5b).

Fixtures build saved sections from writer v13 drafts and review v11 records, as the switch-on
(piece 8) will save them, and lay them out. They check code's layout - In short, each section's
order and folds, what is asked once, the checks folded last - not that a real writer or reviewer
writes or judges well.
"""
from copy import deepcopy

import pytest

from nm.core_engine import (
    answer_sources, response_authorities, response_rendering, response_review, response_writer, turn,
)
from tests.test_core_response_writer import two_disputes

pytestmark = pytest.mark.class_a

V18 = response_rendering.PRESENTED_CONTRACT


def unit(kind, text, place):
    return {"kind": kind, "text": text, "uses": [], "place": place}


def reviewed(ctx, record, sources, draft, returned=None, **kwargs):
    """A v11 review of a v13 piece, admitted from what the scripted review returned."""
    authorities = response_authorities.check(ctx, record, sources, draft)
    deps = response_review._dependencies(ctx, record, sources, draft, turn.execution_record(record),
                                         authority_evidence=authorities, contract=response_review.PRESENTED_CONTRACT,
                                         **kwargs)
    review = response_review._accept_v10(returned or {"misleading": [], "could_be_better": [], "keep_shown": []},
                                         deps, response_review.PRESENTED_CONTRACT)
    return {"draft": draft, "authority_evidence": authorities, "review": review, "date_findings": []}


def saved(index, dispute_id, piece=None, fallback=None):
    return {"part": index, "dispute_id": dispute_id, "reviewed": piece, "trims": [],
            "fallback": None if piece is not None else {"reason": fallback}, "edit": None, "refused": []}


def item(sources, need, asked):
    passage = sources[answer_sources.aliases(sources)["P1"]]
    return {"need": need, "why": "The law requires it.", "note": None, "group": "needed",
            "law": {"source_id": "P1", "quote": " ".join(passage["text"].split()[:4])}, "carries": None,
            "status": "not_given", "evidence": None, "asked_words": asked}


def cheque(ctx, sources):
    units = [unit("summary", "Criminal complaint under section 138", "row_action"),
             unit("summary", "Have the cheque and the return memo ready", "row_ready"),
             unit("limitation", "On the dates you gave.", "basis"),
             unit("summary", "File the complaint promptly.", "advice"),
             unit("summary", "Before a Magistrate where your branch is.", "where"),
             unit("summary", "The presentation date is not given.", "risks"),
             unit("next_step", "Collect the originals.", "next_steps"),
             unit("summary", "Proof can be given by affidavit.", "more"),
             unit("summary", "A civil suit is separate.", "more"),
             unit("question", "Was any part-payment made before presentation?", "ask")]
    return response_writer.accept({"units": units, "checklists": [{
        "checklist": [item(sources, "The cheque and the return memo", ["the cheque and the return memo"])],
        "time_limit_ids": [], "by_when": None}]}, ctx, sources, contract=response_writer.PRESENTED_CONTRACT,
        parts=[{"dispute_id": "D1", "units": len(units)}], section=1)


def goods(ctx, sources):
    units = [unit("summary", "Civil suit for the price", "row_action"),
             unit("summary", "Sue for the price.", "advice")]
    return response_writer.accept({"units": units, "checklists": [{"checklist": [], "time_limit_ids": [],
                                                                    "by_when": None}]}, ctx, sources,
                                  contract=response_writer.PRESENTED_CONTRACT,
                                  parts=[{"dispute_id": "D2", "units": len(units)}], section=2)


def opening(ctx, sources):
    units = [unit("next_step", "File the cheque complaint first.", "do_first"),
             unit("summary", "Both debts are owed by one buyer.", "ties"),
             unit("question", "Pursue both debts together, or separately?", "ask")]
    return response_writer.accept({"units": units, "checklists": [{"checklist": [], "time_limit_ids": [],
                                                                    "by_when": None}]}, ctx, sources,
                                  contract=response_writer.PRESENTED_CONTRACT,
                                  parts=[{"dispute_id": None, "units": len(units)}], section=response_writer.OVERVIEW)


def answer(first_review=None, *, second=True, overview=True, waiting=()):
    ctx, record, sources = two_disputes()
    first = cheque(ctx, sources)
    sections = [saved(1, "D1", reviewed(ctx, record, sources, first, first_review))]
    if second:
        sections.append(saved(2, "D2", reviewed(ctx, record, sources, goods(ctx, sources))))
    elif not waiting:
        sections.append(saved(2, "D2", fallback="service"))
    drafts = [piece["reviewed"]["draft"] for piece in sections if piece["reviewed"]]
    made = None
    if overview:
        draft = opening(ctx, sources)
        made = {"reviewed": reviewed(ctx, record, sources, draft, sections=drafts), "trims": [], "fallback": None,
                "refused": []}
    elements = response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=None,
                                                  overview=made, time_limits=None, waiting=waiting, contract=V18)
    return elements, first


def kinds(elements):
    return [element["kind"] for element in elements]


def test_the_answer_opens_in_short_then_each_section_in_its_order_then_what_is_needed():
    elements, _ = answer()
    assert kinds(elements) == [
        "IN_SHORT", "ROW", "ROW_ACTION", "ROW_READY", "ROW", "ROW_ACTION", "DO_FIRST", "TIES",
        "HEADING", "BASIS", "ADVICE", "WHERE", "SUBHEAD", "RISK", "SUBHEAD", "STEP", "MORE", "MORE",
        "HEADING", "ADVICE",
        "NEEDS", "NEED_GROUP", "NEED_ITEM", "ASK", "YOUR_CALL", "ASK"]
    rows = [element for element in elements if element["kind"] == "ROW"]
    assert [(row["text"], row["row"]["status"]) for row in rows] == [("Dispute 1", "shown"), ("Dispute 2", "shown")]
    headings = [element["text"] for element in elements if element["kind"] == "HEADING"]
    assert headings == ["Dispute 1: Criminal complaint under section 138", "Dispute 2: Civil suit for the price"]
    assert [element["text"] for element in elements if element["kind"] == "SUBHEAD"] == [
        "What could still go wrong", "Next steps"]


def test_an_item_asked_for_is_listed_once_and_a_question_for_no_item_as_written():
    elements, first = answer()
    need = next(element for element in elements if element["kind"] == "NEED_ITEM")
    assert need["text"] == "The cheque and the return memo" and need["dispute"] == {"id": "D1", "name": "Dispute 1"}
    ready = next(element for element in elements if element["kind"] == "ROW_READY")
    assert [ask["text"] for ask in ready["asks"]] == ["the cheque and the return memo"]
    asked = [element["text"] for element in elements if element["kind"] == "ASK"]
    assert asked == ["Was any part-payment made before presentation?", "Pursue both debts together, or separately?"]


def test_the_checks_suggestions_fold_last_and_what_may_mislead_stays_beside_its_section():
    def returned(draft):
        return {"misleading": [{"kind": "unsupported", "where": [], "evidence": [],
                                "why": "The section frames the matter as settled."}],
                "keep_shown": [], "could_be_better": [
                    {"where": ["U4"], "what": "Say which court hears it.", "change": "add_or_put_better"},
                    {"where": ["U8"], "what": "U8 repeats the next section.", "change": "could_go"}]}
    ctx, record, sources = two_disputes()
    elements, _ = answer(returned(None))
    assert not any("could add or put this better" in element["text"] for element in elements)
    note, = [element for element in elements if element["kind"] == "NOTE"]
    assert "may mislead" in note["text"] and kinds(elements).index("NOTE") < kinds(elements).index("MORE")
    checked = elements[-1]
    assert checked["kind"] == "CHECKED" and checked["text"] == "How NM checked this answer"
    assert checked["checked"] == [{"part": "Dispute 1", "suggestions": [
        {"kind": "better", "text": "Say which court hears it."},
        {"kind": "could_go", "text": "a paragraph repeats the next section."}]}]


def test_a_folded_paragraph_the_advice_depends_on_is_shown_with_the_advice():
    elements, first = answer({"misleading": [], "could_be_better": [], "keep_shown": ["U8"]})
    advice = [element["text"] for element in elements if element["kind"] == "ADVICE"]
    assert advice[:2] == ["File the complaint promptly.", "Proof can be given by affidavit."]
    assert [element["text"] for element in elements if element["kind"] == "MORE"] == ["A civil suit is separate."]


def test_each_paragraph_names_its_section_and_place_for_the_reading_pane():
    elements, first = answer()
    for index, element in enumerate(elements):
        if element["kind"] in response_rendering.NOT_PARAGRAPHS:
            with pytest.raises(IndexError):
                response_rendering.unit_index(elements, index)
            continue
        section = element["section"]
        assert section in (1, 2, response_writer.OVERVIEW)
        if section == 1:
            assert first["units"][response_rendering.unit_index(elements, index)]["text"] == element["text"]


def test_a_dispute_not_written_in_full_or_still_being_written_says_so_in_its_row():
    elements, _ = answer(second=False, overview=False)
    rows = [element for element in elements if element["kind"] == "ROW"]
    assert rows[1]["row"] == {"status": "note", "why": "the AI service did not respond"}
    assert "FALLBACK" in kinds(elements)
    waiting, _ = answer(second=False, overview=False, waiting=(2,))
    assert [element["row"]["status"] for element in waiting if element["kind"] == "ROW"] == ["shown", "waiting"]
    assert "WAITING" in kinds(waiting)


def test_by_when_is_code_s_last_day_as_of_the_day_it_was_worked_out():
    boxes = [{"working": {"what": "Make a written complaint", "last_day": "2026-11-04",
                          "standing": {"state": "open", "days": 14},
                          "rows": [["Last day", "4 November 2026 (Wednesday)"], ["As of", "21 October 2026 (Wednesday)"]]}},
             {"working": {"what": "Sue for the price", "not_assessed": "the credit terms are not given"}}]
    piece = {"draft": {"checklists": [{"by_when": "T1"}]}}
    assert response_rendering._by_when(piece, boxes) == {
        "what": "Make a written complaint", "last_day": "2026-11-04", "day": "4 November 2026 (Wednesday)",
        "result": "Open", "days": 14, "days_label": "Days left", "as_of": "21 October 2026 (Wednesday)"}
    piece["draft"]["checklists"][0]["by_when"] = "T2"
    assert response_rendering._by_when(piece, boxes) == {"what": "Sue for the price",
                                                         "not_assessed": "the credit terms are not given"}
    piece["draft"]["checklists"][0]["by_when"] = None
    assert response_rendering._by_when(piece, boxes) is None


def test_v18_shows_only_sections_written_for_the_advocate_and_v17_is_unchanged():
    ctx, record, sources = two_disputes()
    draft = response_writer.accept({"units": [{"kind": "summary", "text": "In short.", "uses": []}],
                                    "checklists": [{"checklist": [], "time_limit_ids": []}]}, ctx, sources,
                                   contract=response_writer.SECTION_CONTRACT, parts=[{"dispute_id": "D1", "units": 1}],
                                   section=1)
    authorities = response_authorities.check(ctx, record, sources, draft)
    deps = response_review._dependencies(ctx, record, sources, draft, turn.execution_record(record),
                                         authority_evidence=authorities, contract=response_review.MISLEADS_CONTRACT)
    piece = {"draft": draft, "authority_evidence": authorities, "date_findings": [],
             "review": response_review._accept_v10({"misleading": [], "could_be_better": []}, deps)}
    sections = [saved(1, "D1", piece), saved(2, "D2", fallback="service")]
    with pytest.raises(ValueError, match="v18"):
        response_rendering.render_sections(ctx, record, sources, sections=sections, cross_check=None, overview=None,
                                           time_limits=None, contract=V18)
    before = response_rendering.render_sections(ctx, record, sources, sections=deepcopy(sections), cross_check=None,
                                                overview=None, time_limits=None)
    assert "IN_SHORT" not in kinds(before) and "SUMMARY" in kinds(before)
