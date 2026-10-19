"""What the review still finds after the rewrites only in a dispute's checklist leaves the
items it names out, or is noted beside the answer, instead of holding the section back
(owner, 18 Oct 2026: "withhold only the failed part and pass the remaining part"; rendering
v15). In the fourth live run of 19 Oct the consignment section was held for two item
statuses and an item left out of its checklist. Scripted fixtures exercise the release,
the records and the replay; they do not show that a real reviewer judges items well. From
19 Oct 2026 a turn leaves such an item out of its section's own draft instead (turn v6, owner
decision P25; tests/test_core_answer_sections.py); saved v5 turns replay as tested here."""
from copy import deepcopy

import pytest

from nm.core_engine import checklist, response_authorities, response_rendering, response_review, turn
from tests.test_core_checklist import written
from tests.test_core_response_review import Model as ReviewModel, positive, request

pytestmark = pytest.mark.class_a


def item_review(ctx, draft, items=("C3",), *, category="framing"):
    """A review that still finds the checklist items named wrong, in short IDs."""
    data = positive(draft, requests=[request(ctx, draft)])
    data.update(verdict="reject", findings=[{"category": category, "unit_ids": list(items), "sources": [],
                                              "mismatch": f"{', '.join(items)} overstates where the item stands."}])
    return data


def reviewed(ctx, record, sources, draft, data):
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    review = response_review.review(ReviewModel(data), ctx, record, sources, draft, execution,
                                    authority_evidence=authorities)
    return authorities, execution, review


def test_findings_only_in_a_checklist_are_sorted_from_the_rest():
    ctx, record, sources, draft = written()
    _, _, review = reviewed(ctx, record, sources, draft, item_review(ctx, draft))
    left_out, noted, rest = response_rendering.checklist_findings(draft, review)
    assert (left_out, noted, rest) == ({2: ["t2:c3"]}, {}, [])
    assert response_rendering.held_sections(draft, review, confined=True) == []
    assert response_rendering.held_sections(draft, review) == [2], "earlier versions hold the section"
    # An omission naming only a dispute's summary is how the review names an item its
    # checklist leaves out; any other finding is the rest.
    summary = {**deepcopy(draft), "units": [
        {**unit, "kind": "summary"} if index == 2 else unit for index, unit in enumerate(draft["units"])]}
    omission = {"accepted": False, "proposal": {"findings": [
        {"category": "omission", "unit_ids": [draft["units"][2]["id"]], "sources": [], "mismatch": "Leaves out X."},
        {"category": "grounding", "unit_ids": [draft["units"][1]["id"]], "sources": [], "mismatch": "Unsupported."}]}}
    left_out, noted, rest = response_rendering.checklist_findings(summary, omission)
    assert left_out == {} and list(noted) == [2] and [finding["category"] for finding in rest] == ["grounding"]
    assert response_rendering.held_sections(summary, omission, confined=True) == [1]


def test_the_items_are_left_out_said_so_and_dropped_from_the_matters_checklist():
    ctx, record, sources, draft = written()
    authorities, execution, review = reviewed(ctx, record, sources, draft, item_review(ctx, draft))
    release = {"parts": [], "date_findings": [], "left_out": [{"dispute_id": "D2", "items": ["t2:c3"]}]}
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities, held=release)
    # v16 (19 Oct 2026): said at the end of the dispute's own part, naming the item left out.
    assert [element["kind"] for element in elements] == [
        "QUESTION", "HEADING", "QUESTION", "HEADING", "QUESTION", "NOTICE"]
    assert elements[-1]["text"] == (
        "Left out of the checklist for Dispute 2: “The chunk the judgment names”, because the independent check "
        "still found a problem in it after the rewrites NM may make: the item framed the matter in a way its "
        "sources do not support. The rest of this section is shown, checked by the independent review.")
    # v15 said it atop the answer, by count; a v15 answer replays so.
    earlier = response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities,
                                        held=release, contract=response_rendering.CONFINED_CONTRACT)
    assert earlier[0]["kind"] == "NOTICE" and earlier[0]["text"] == (
        "Left out of the checklist for Dispute 2: 1 item, because the independent check still found a problem in "
        "it after the rewrites NM may make: the item framed the matter in a way its sources do not support. The "
        "rest of that section is shown, checked by the independent review.")
    assert "HELD" not in [element["kind"] for element in elements]
    assert "Answer for D2?" in [element["text"] for element in elements], "the section itself is shown"
    # The record must say exactly what the review found; v14 never leaves items out.
    for wrong in ({**release, "left_out": [{"dispute_id": "D2", "items": ["t2:c2"]}]},
                  {"parts": [], "date_findings": []},
                  {**release, "noted": ["D2"]}):
        with pytest.raises(ValueError):
            response_rendering.render(ctx, record, sources, draft, review, execution,
                                      authority_evidence=authorities, held=wrong)
    with pytest.raises(ValueError):
        response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities,
                                  held=release, contract=response_rendering.LAID_OUT_CONTRACT)
    # The matter's checklist keeps the rest of the dispute's items, not those left out.
    activity = {"draft": draft, "research": record, "sources": sources, "calculation": None, "release": release}
    kept = checklist.records(ctx, activity)["checklist"]
    assert [[item["need"] for item in dispute["items"]] for dispute in kept["disputes"]] == [
        ["The exception the provision makes", "The words of the second provision"], []]


def test_an_omission_naming_only_the_summary_is_noted_beside_the_answer():
    ctx, record, sources, draft = written()
    summary_id = draft["units"][2]["id"]
    noted = {**deepcopy(draft)}
    # The fixture's sections answer in one paragraph each; here Dispute 2's is its summary.
    data = positive(draft, requests=[request(ctx, draft)])
    data.update(verdict="reject", findings=[{"category": "omission", "unit_ids": ["U3"], "sources": [],
                                             "mismatch": "The checklist leaves out whether property in the goods "
                                                         "passed, which U3's section needs."}])
    authorities, execution, review = reviewed(ctx, record, sources, draft, data)
    assert review["proposal"]["findings"][0]["unit_ids"] == [summary_id]
    as_summary = {**noted, "units": [{**unit, "kind": "summary"} if unit["id"] == summary_id else unit
                                     for unit in noted["units"]]}
    left_out, found, rest = response_rendering.checklist_findings(as_summary, review)
    assert (left_out, list(found), rest) == ({}, [2], [])
