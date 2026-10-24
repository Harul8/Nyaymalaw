"""The matter's checklist (owner decisions, 17 Oct 2026; built 18 Oct): each dispute's part
returns its checklist, code checks every quote, the review judges every item, and the
matter keeps its checklist as the conversation's records, re-derived on reopening, for
the board. Scripted fixtures exercise the wiring; they do not show that a real writer
lists what the law requires."""
from copy import deepcopy
import json

import pytest

from nm.core_engine import (
    answer_sources, calculation, checklist, matter_board, response_authorities, response_rendering, response_review,
    response_writer, turn,
)
from nm.core_engine.calls import TurnCalls
from nm.core_engine.conversation import ConversationRefused, chat_matter_id
from nm.shared.citation_contracts import statute_title
from nm.shared.model_port import SchemaViolation
from tests.test_core_response_review import Model as ReviewModel, positive, request
from tests.test_core_response_writer import PartModel, two_disputes
from tests.test_core_turn import ScriptedModel, run, store  # noqa: F401 - pytest fixture

pytestmark = pytest.mark.class_a


def alias(sources, kind, words):
    offered = {identity: name for name, identity in answer_sources.aliases(sources).items()}
    return next(offered[identity] for identity, row in sources.items() if row["kind"] == kind and words in row["text"])


def lists(sources):
    message = alias(sources, "account", "Find the applicable law.")
    return {
        "D1": [{"need": "The exception the provision makes", "why": "The provision applies only with it.",
                "note": None, "group": "needed",
                "law": {"source_id": alias(sources, "provision", "Complete provision"), "quote": "including its exception"},
                "carries": None, "status": "in_hand", "evidence": {"source_id": message, "quote": "applicable law"}},
               {"need": "The words of the second provision", "why": "They set the second condition.", "note": None,
                "group": "needed",
                "law": {"source_id": alias(sources, "provision", "Different exact"), "quote": "Different exact words"},
                "carries": None, "status": "not_given", "evidence": None}],
        "D2": [{"need": "The chunk the judgment names", "why": "The court relied on it.", "note": "not sure yet",
                "group": "would_strengthen",
                "law": {"source_id": alias(sources, "judgment", "Different exact"), "quote": "same chunk ID"},
                "carries": None, "status": "coming_or_unclear",
                "evidence": {"source_id": message, "quote": "Find the applicable law"}}]}


class ChecklistModel(PartModel):
    """Each part answers in one unit and returns the checklist and time limits given for
    its dispute (None: the opening part)."""
    def __init__(self, sources, given=None, limits=None):
        super().__init__(sources)
        self.given = lists(sources) if given is None else given
        self.limits = limits or {}

    def structured(self, prompt, schema, tier, **kwargs):
        result = super().structured(prompt, schema, tier, **kwargs)
        dispute = (json.loads(prompt.user)["this_part"]["dispute"] or {}).get("id")
        result.data["checklist"] = deepcopy(self.given.get(dispute, []))
        result.data["time_limit_ids"] = list(self.limits.get(dispute, []))
        return result


def written(given=None, limits=None, time_limits=None, records=None):
    ctx, record, sources = two_disputes()
    if records is not None:
        ctx["current_records"] = records
    draft = response_writer.write(ChecklistModel(sources, given, limits), ctx, record, sources,
                                  time_limits=time_limits)
    return ctx, record, sources, draft


def test_each_dispute_returns_its_checklist_with_every_quote_checked():
    ctx, record, sources, draft = written()
    assert draft["contract"] == response_writer.CONTRACT == "core_response_writer_v11"
    assert [len(part["items"]) for part in draft["checklists"]] == [0, 2, 1]  # the opening part has none
    # v9 (18 Oct 2026): each item says why the case needs it and, where unclear, where it stands.
    assert [(item["why"], item["note"]) for part in draft["checklists"] for item in part["items"]] == [
        ("The provision applies only with it.", None), ("They set the second condition.", None),
        ("The court relied on it.", "not sure yet")]
    first, second = draft["checklists"][1]["items"]
    provision = next(identity for identity, row in sources.items() if row["text"].startswith("Complete provision")
                     and row["kind"] == "provision")
    assert (first["id"], first["law"]["source_id"], first["law"]["text"]) == ("t2:c1", provision,
                                                                              "including its exception")
    assert (first["evidence"]["source_id"], first["evidence"]["text"]) == ("t2:advocate", "applicable law")
    assert (second["id"], second["status"], second["evidence"]) == ("t2:c2", "not_given", None)
    assert draft["checklists"][2]["items"][0]["id"] == "t2:c3"
    assert response_writer.validate(deepcopy(draft), ctx, sources) == draft
    assert response_writer.part_ids(draft)[1] == {draft["units"][1]["id"], "t2:c1", "t2:c2"}


def change(given, sources, case):
    message = alias(sources, "account", "Find the applicable law.")
    first, second = given["D1"]
    if case == "law_not_in_its_passage": first["law"]["quote"] = "words the provision never says"
    elif case == "law_from_a_message": first["law"] = {"source_id": message, "quote": "applicable law"}
    elif case == "evidence_not_found": first["evidence"]["quote"] = "words nobody wrote"
    elif case == "not_given_with_evidence": second["evidence"] = {"source_id": message, "quote": "applicable law"}
    elif case == "in_hand_without_evidence": first["evidence"] = None
    elif case == "unclear_not_in_the_advocates_words":
        given["D2"][0]["evidence"] = {"source_id": alias(sources, "judgment", "Different exact"),
                                      "quote": "same chunk ID"}
    elif case == "law_and_carried": first["carries"] = "K1"
    elif case == "neither_law_nor_carried": first["law"] = None
    elif case == "carries_an_unknown_item": first.update(law=None, carries="K9")
    elif case == "an_opening_with_a_checklist": given[None] = [deepcopy(first)]
    elif case == "blank_need": first["need"] = "   "
    elif case == "blank_why": first["why"] = "[ ](P1)"
    elif case == "no_why": del first["why"]


@pytest.mark.parametrize("case", [
    "law_not_in_its_passage", "law_from_a_message", "evidence_not_found", "not_given_with_evidence",
    "in_hand_without_evidence", "unclear_not_in_the_advocates_words", "law_and_carried",
    "neither_law_nor_carried", "carries_an_unknown_item", "an_opening_with_a_checklist", "blank_need",
    "blank_why", "no_why"])
def test_a_checklist_item_is_admitted_only_on_exact_words_of_the_right_source(case):
    ctx, record, sources = two_disputes()
    given = lists(sources)
    change(given, sources, case)
    with pytest.raises(SchemaViolation):
        response_writer.write(ChecklistModel(sources, given), ctx, record, sources)


def test_a_misquoted_law_is_corrected_with_the_held_words_nearest_to_it():
    """The seventh live run (18 Oct 2026): a section's checklist quoted a held provision with
    words dropped; told only that the quotation was not exact, the correction copied the
    same words again and the answer was withheld. The correction is shown the provision's
    own words nearest to the quotation, exactly as they stand."""
    ctx, record, sources = two_disputes()
    given = lists(sources)
    given["D1"][0]["law"]["quote"] = "Complete provision including exception"
    model = ChecklistModel(sources, given)
    calls = TurnCalls(model)

    def write():
        if model.seen:  # the correction copies the held words
            model.given = lists(sources)
        return response_writer.write(calls, ctx, record, sources)

    draft = calls.checked("core_response_writer", write)
    corrected = next(payload for payload in model.seen
                     if "correction" in payload and (payload["this_part"]["dispute"] or {}).get("id") == "D1")
    assert corrected["correction"]["mismatch"].endswith(
        "The source's own words nearest to that quotation, exactly as they stand: "
        "“Complete provision including its exception.”. A quotation is one continuous stretch of its source, "
        "word for word, with nothing left out in the middle: quote a shorter stretch rather than skip words.")
    # The ninth live run (18 Oct 2026): a quotation of a list left an item out of the middle.
    assert "copying one continuous stretch of the words that say so" in " ".join(response_writer.SYSTEM.split())
    assert draft["checklists"][1]["items"][0]["law"]["text"] == "including its exception"
    assert calls.metrics()["draft_corrections"] == 1


def test_a_dispute_names_only_the_time_limits_code_worked_out_and_any_other_id_is_left_out():
    # Forensic review, 18 Oct 2026: an ID code did not work out names no time limit, so it is
    # left out rather than costing the answer a correction.
    assert [part["time_limit_ids"] for part in written(limits={"D1": ["T1"]})[3]["checklists"]] == [[], [], []]
    worked = {"state": "worked", "worked_out": [{"what": "Last day to file"}],
              "not_assessed": [{"what": "Notice period", "why": "no date"}]}
    draft = written(limits={"D1": ["Last day to file", "T2", "T9", "T1"]}, time_limits=worked)[3]
    assert [part["time_limit_ids"] for part in draft["checklists"]] == [[], ["T2", "T1"], []]
    ctx, record, sources, draft = written(limits={"D1": ["T2", "T1"]}, time_limits=worked)
    assert [part["time_limit_ids"] for part in draft["checklists"]] == [[], ["T2", "T1"], []]
    # The writer saw each time limit under its ID.
    assert response_writer.limit_ids(worked)["not_assessed"][0]["id"] == "T2"


def test_a_use_naming_a_time_limit_is_left_out_as_code_s_own_result_not_a_source():
    """The live run of 19 Oct 2026 (writer v10): a section grounded the last day it stated
    in the time limit's ID, as if a source, and its rewrite did again; the section was held
    back for it. A time limit is code's own result, shown with the answer's time limits:
    such a use is left out. An ID code did not give still names nothing and is refused."""
    worked = {"state": "worked", "worked_out": [{"what": "Last day to file"}], "not_assessed": []}

    class Grounded(ChecklistModel):
        def structured(self, prompt, schema, tier, **kwargs):
            result = super().structured(prompt, schema, tier, **kwargs)
            result.data["units"][0]["uses"].append({"source_kind": "nm_context", "source_id": self.named})
            return result

    ctx, record, sources = two_disputes()
    model = Grounded(sources, limits={"D1": ["T1"]})
    model.named = "T1"
    draft = response_writer.write(model, ctx, record, sources, time_limits=worked)
    assert all(use["source_id"] != "T1" for unit in draft["units"] for use in unit["uses"])
    assert [part["time_limit_ids"] for part in draft["checklists"]] == [[], ["T1"], []]
    assert response_writer.validate(deepcopy(draft), ctx, sources) == draft
    model.named = "T2"
    with pytest.raises(SchemaViolation, match="'T2' is not in the owned answer catalogue"):
        response_writer.write(model, ctx, record, sources, time_limits=worked)


def test_a_disputes_time_limits_are_kept_as_code_worked_them_out_and_shown_in_its_words():
    calculation = {"today": "2026-10-18", "not_assessed": [{"what": "Notice period", "why": "no date is given"}],
                   "calculations": [{"what": "Last day to file the suit", "provision_name": "Article 54",
                                     "working": {"last_day": "2027-01-10"}, "standing": {"state": "open", "days": 84}}]}
    kept = checklist._limits({"time_limit_ids": ["T1", "T2", "T1", "T9"]}, calculation)
    assert kept == checklist._limits({"time_limits": ["Last day to file the suit", "Notice period"]}, calculation)
    assert kept == [{"what": "Last day to file the suit", "provision": "Article 54", "last_day": "2027-01-10",
                     "standing": {"state": "open", "days": 84}, "as_of": "2026-10-18"},
                    {"what": "Notice period", "not_assessed": "no date is given"}]
    assert response_rendering.limit_rows(kept[0]) == [
        ["Last day", "10 January 2027 (Sunday)"], ["As of", "18 October 2026 (Sunday)"], ["Result", "Open"],
        ["Days left", "84"]]
    assert response_rendering.limit_rows(kept[1]) == [["Not assessed", "no date is given"]]


def checked(ctx, record, sources, draft, data=None):
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    model = ReviewModel(data or positive(draft, requests=[request(ctx, draft)]))
    return model, response_review.review(model, ctx, record, sources, draft, execution,
                                         authority_evidence=authorities)


def test_the_review_names_a_wrong_item_in_a_finding_and_it_concerns_only_its_section():
    ctx, record, sources, draft = written()
    model, review = checked(ctx, record, sources, draft)
    assert review["contract"] == "core_response_review_v8" and review["accepted"]
    shown = json.loads(model.calls[0][0].user)["complete_draft_proposal"]["checklists"]
    assert [[item["id"] for item in part["items"]] for part in shown] == [[], ["C1", "C2"], ["C3"]]
    assert shown[1]["items"][0]["law"] == {"source_id": "P1", "quote": "including its exception"}
    assert shown[1]["items"][0]["evidence"] == {"source_id": "M1", "quote": "applicable law"}
    # Writer v9 (18 Oct 2026): the review sees why each item is needed and where it stands.
    assert [(item["why"], item["note"]) for item in shown[2]["items"]] == [("The court relied on it.", "not sure yet")]
    assert "naming any item" in " ".join(response_review.SYSTEM.split())
    assert "an item's why and note, where given, say only what its law words and the messages bear out" in " ".join(
        response_review.SYSTEM.split())
    # Review v7: verdict rows are for the units; a row for an item is refused as unknown (a
    # saved v7 review is still held to it; v8 gives no rows).
    from tests.test_core_response_review import admitted
    data = positive(draft, requests=[request(ctx, draft)], items=True)
    with pytest.raises(SchemaViolation, match="unknown draft unit IDs"):
        admitted(data, (ctx, record, sources, draft), contract=response_review.ROWS_CONTRACT)
    # A wrong item, named by its short ID in a finding, concerns its own dispute's section alone.
    data = positive(draft, requests=[request(ctx, draft)])
    data["verdict"] = "reject"
    data["findings"] = [{"category": "grounding", "unit_ids": ["C3"], "sources": [],
                         "mismatch": "C3 is not what the passage requires."}]
    _, rejected = checked(ctx, record, sources, draft, data)
    findings = rejected["proposal"]["findings"]
    assert findings[0]["unit_ids"] == ["t2:c3"] and not rejected["accepted"]
    assert sorted(response_writer.kept_parts(draft, findings)) == [0, 1]
    assert response_rendering.held_sections(draft, rejected) == [2]
    # An omission's explanation is shown, its short IDs as words.
    assert "a checklist item is not what" in response_rendering.found_words([{**findings[0], "category": "omission"}])


def previous_records(sources):
    p2 = next(row for row in sources.values() if row["kind"] == "provision" and row["text"].startswith("Different"))
    old_law = {"kind": "provision", "title": "Old Act", "locator": "s.9", "words": "served within thirty days",
               "source_id": "an earlier passage", "held_in": "t1"}
    same_law = {"kind": "provision", "title": statute_title(p2["title"], p2["source_identity"]["act_id"]),
                "locator": p2["locator"], "words": "Different exact words", "source_id": "an earlier passage",
                "held_in": "t1"}

    def item(identity, law, status="not_given"):
        return {"id": identity, "need": "Earlier need", "group": "needed", "law": law, "status": status,
                "evidence": None, "asked_in": "t1" if status == "not_given" else None, "noted_in": "t1"}
    return {"other": "kept as it was", "checklist": {"contract": checklist.CONTRACT, "turn_id": "t1", "disputes": [
        {"id": "D1", "name": "Dispute 1", "answered_in": "t1", "time_limits": [],
         "items": [item("K1", old_law), item("K2", same_law)]},
        {"id": "D2", "name": "Dispute 2", "answered_in": "t1", "time_limits": [], "items": [item("K3", old_law)]},
        {"id": "D9", "name": "A dispute no longer understood", "answered_in": "t1", "time_limits": [],
         "items": [item("K4", old_law)]}]}}


def test_the_matter_keeps_its_checklist_and_when_nm_first_asked():
    ctx, record, sources = two_disputes()
    before = previous_records(sources)
    given = lists(sources)
    given["D1"] = [{"need": "Proof of service", "why": "Service starts the time.", "note": None, "group": "needed",
                    "law": None, "carries": "K1", "status": "not_given", "evidence": None},
                   given["D1"][1], given["D1"][0]]
    _, record, sources, draft = written(given=given, records=deepcopy(before))
    ctx["current_records"] = deepcopy(before)
    # Dispute 2's section was held back, so its checklist is kept as it was.
    activity = {"draft": draft, "research": record, "sources": sources, "calculation": None,
                "release": {"parts": [2], "date_findings": []}}
    after = checklist.records(ctx, activity)
    assert after["other"] == "kept as it was"
    saved = after["checklist"]
    assert [(d["id"], d["answered_in"]) for d in saved["disputes"]] == [("D1", "t2"), ("D2", "t1")]
    carried, again, held = saved["disputes"][0]["items"]
    assert carried["law"] == before["checklist"]["disputes"][0]["items"][0]["law"]  # its saved law words
    assert (carried["id"], carried["asked_in"]) == ("K1", "t1")
    assert (again["law"]["words"], again["asked_in"]) == ("Different exact words", "t1")  # the same law words
    assert held["status"] == "in_hand" and held["asked_in"] is None
    assert held["evidence"] == {"from": "message", "turn_id": "t2", "words": "applicable law",
                                "source_id": "t2:advocate"}
    assert saved["disputes"][1]["items"][0]["id"] == "K4"  # renumbered, otherwise as saved
    assert checklist.records(ctx, {**activity, "draft": {"contract": "core_response_writer_v5"}}) == before
    # An answer that covers no dispute, here with every section held back, changes nothing.
    assert checklist.records(ctx, {**activity, "release": {"parts": [1, 2], "date_findings": []}}) == before


def test_a_saved_turn_keeps_its_checklist_as_records_and_the_board_shows_it(store):
    class Listing(ScriptedModel):
        def structured(self, prompt, schema, tier, **kwargs):
            result = super().structured(prompt, schema, tier, **kwargs)
            if prompt.operation == "core_response_writer":
                data = json.loads(prompt.user)
                passage = next(p for p in data["held_passages"]["passages"] if "Counsel submitted" in p["text"])
                message = data["original_context"]["latest"]["source_id"]
                result.data["checklist"] = [
                    {"need": "Proof the notice was served", "why": "Service must be shown.", "note": None,
                     "group": "needed",
                     "law": {"source_id": passage["id"], "quote": "Counsel submitted"}, "carries": None,
                     "status": "in_hand", "evidence": {"source_id": message, "quote": "The notice was served"}},
                    {"need": "The postal receipt", "why": "It proves the date of posting.", "note": "promised",
                     "group": "would_strengthen",
                     "law": {"source_id": passage["id"], "quote": "Counsel submitted"}, "carries": None,
                     "status": "coming_or_unclear",
                     "evidence": {"source_id": message, "quote": "I will send the postal receipt"}}]
            return result

    reply = run(store, Listing(legal=True), message="The notice was served on 2 March; I will send the postal receipt.")
    assert reply["committed"] == "committed"
    matter = store.load(chat_matter_id("owner", reply["chat_id"]))
    rows = turn.saved_rows(matter, "owner")
    assert rows[0]["activities"]["contract"] == turn.CONTRACT == "core_turn_v8"
    saved = rows[0]["records"]["checklist"]
    items = saved["disputes"][0]["items"]
    assert [(item["id"], item["status"], item["evidence"]["words"]) for item in items] == [
        ("K1", "in_hand", "The notice was served"), ("K2", "coming_or_unclear", "I will send the postal receipt")]
    board = matter_board.board(rows)
    shown = board["disputes"][0]["checklist"]
    assert shown["in_hand"] == 1 and [item["status"] for item in shown["items"]] == ["in_hand", "coming_or_unclear"]
    assert shown["items"][0]["evidence"]["given_at"] == reply["at"] and shown["answered_at"] == reply["at"]
    # Writer v9: why each item is needed and where it stands, kept and shown (18 Oct 2026).
    assert [(item["why"], item["note"]) for item in items] == [("Service must be shown.", None),
                                                              ("It proves the date of posting.", "promised")]
    assert [(item["why"], item["note"]) for item in shown["items"]] == [("Service must be shown.", None),
                                                                       ("It proves the date of posting.", "promised")]
    # Records changed after saving are refused on reopening: the turn's own digest is made whole
    # here, but the chain's tail no longer matches (P46: the record is checked, never rebuilt).
    damaged = deepcopy(matter)
    rows_ = list(damaged.brain_chat)
    rows_[0] = {**rows_[0], "records": {**rows_[0]["records"], "checklist": {**saved, "disputes": []}}}
    from dataclasses import replace
    from nm.core_engine.conversation import digest
    rows_[0]["digest"] = digest({key: value for key, value in rows_[0].items() if key != "digest"})
    with pytest.raises(ConversationRefused):
        turn.saved_rows(replace(damaged, brain_chat=tuple(rows_)), "owner")


def test_a_saved_v6_review_with_a_verdict_row_for_each_item_replays():
    ctx, record, sources, draft = written()
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    dependencies = response_review._dependencies(ctx, record, sources, draft, execution, authority_evidence=authorities,
                                                 contract=response_review.CHECKLIST_CONTRACT)
    saved = response_review._accept(positive(draft, requests=[request(ctx, draft)], items=True), dependencies,
                                    contract=response_review.CHECKLIST_CONTRACT)
    assert saved["accepted"] and saved["contract"] == "core_response_review_v6"
    with pytest.raises(SchemaViolation, match="and every checklist item one"):
        response_review._accept(positive(draft, requests=[request(ctx, draft)]), dependencies,
                                contract=response_review.CHECKLIST_CONTRACT)


def test_a_paragraph_or_item_given_among_a_findings_sources_is_what_the_finding_concerns():
    """Two of four live runs (18 Oct 2026) gave a paragraph or checklist item among a
    finding's sources, and the answer was lost; it joins the finding's unit_ids instead."""
    ctx, record, sources, draft = written()
    data = positive(draft, requests=[request(ctx, draft)])
    data["verdict"] = "reject"
    data["findings"] = [{"category": "grounding", "unit_ids": [], "sources": [
        {"source_id": "C3", "quote": None}, {"source_id": "M1", "quote": "applicable law"}],
        "mismatch": "C3 is not what the passage requires."}]
    _, review = checked(ctx, record, sources, draft, data)
    finding, = review["proposal"]["findings"]
    assert finding["unit_ids"] == ["t2:c3"] and [ref["source_id"] for ref in finding["sources"]] == ["M1"]
    assert response_rendering.held_sections(draft, review) == [2]


def test_an_omission_may_name_the_supported_summary_it_is_missing_from():
    """The review is asked to raise a missing item as an omission naming the dispute's
    summary unit, whose own words may be right; the sixth live run (18 Oct 2026) was
    refused for leaving that unit supported. A finding of any other kind still rejects
    what it names."""
    ctx, record, sources, draft = written()
    summary = draft["units"][1]["id"]  # Dispute 1's unit
    data = positive(draft, requests=[request(ctx, draft)])
    data["verdict"] = "reject"
    data["findings"] = [{"category": "omission", "unit_ids": [summary], "sources": [],
                         "mismatch": "The checklist leaves out the court the complaint goes to."}]
    _, review = checked(ctx, record, sources, draft, data)
    assert not review["accepted"] and response_rendering.held_sections(draft, review) == [1]
    data["findings"][0]["category"] = "grounding"
    # Review v8 gives no verdict rows: a finding of any other kind rejects what it names.
    _, rejected = checked(ctx, record, sources, draft, data)
    assert not rejected["accepted"] and response_rendering.held_sections(draft, rejected) == [1]
    # A saved v7 review could not leave such a unit supported in its rows.
    from tests.test_core_response_review import admitted
    with pytest.raises(SchemaViolation, match="cannot label its affected reply unit supported"):
        admitted(data, (ctx, record, sources, draft), contract=response_review.ROWS_CONTRACT)


def test_the_writer_keeps_short_ids_out_of_its_text_and_the_opening_quiet_about_law():
    system = " ".join(response_writer.SYSTEM.split())
    assert "never write one in your text, and call a time limit by what it is" in system
    # From 19 Oct 2026 the opening is the overview, written after the sections (P26).
    overview = " ".join(response_writer.OVERVIEW_SYSTEM.split())
    assert "The overview is given no legal passages and needs none: do not remark on that" in overview
    assert "Never write a short ID" in overview
    from nm.core_engine import calculation
    assert 'leave them out altogether, not under "not_assessed" either' in calculation.SYSTEM


def test_a_need_written_with_link_markup_keeps_its_words():
    # Forensic review, 18 Oct 2026: a need is plain words; markup around them is taken out.
    ctx, record, sources = two_disputes()
    given = lists(sources)
    given["D1"][0]["need"] = "[The exception](P1) the provision makes"
    draft = response_writer.write(ChecklistModel(sources, given), ctx, record, sources)
    assert draft["checklists"][1]["items"][0]["need"] == "The exception the provision makes"
    assert response_writer.validate(deepcopy(draft), ctx, sources) == draft


def test_an_items_why_and_note_are_plain_words_and_a_blank_note_is_none():
    # Writer v9 (18 Oct 2026): why the case needs an item, and where it stands in a few words.
    ctx, record, sources = two_disputes()
    given = lists(sources)
    given["D1"][0].update(why="[The provision](P1) applies only with it.", note="  ")
    given["D2"][0]["note"] = "[promised](M1) tomorrow"
    draft = response_writer.write(ChecklistModel(sources, given), ctx, record, sources)
    first, unclear = draft["checklists"][1]["items"][0], draft["checklists"][2]["items"][0]
    assert (first["why"], first["note"]) == ("The provision applies only with it.", None)
    assert unclear["note"] == "promised tomorrow"
    assert response_writer.validate(deepcopy(draft), ctx, sources) == draft
    # A date in an item's why or note is checked like any other date the answer states.
    unclear["note"] = "promised for 3 March 2031"
    found = response_writer.dates_not_given(draft, ctx, sources)
    assert [finding["unit_ids"] for finding in found] == [[unclear["id"]]]


def test_an_earlier_draft_without_why_or_note_replays_as_it_was():
    # A writer v8 draft has no why or note; it is admitted, and its records kept, as before.
    ctx, record, sources = two_disputes()
    draft = response_writer.write(ChecklistModel(sources), ctx, record, sources)
    proposal = deepcopy(draft["proposal"])
    for part in proposal["checklists"]:
        for item in part["checklist"]:
            del item["why"], item["note"]
    earlier = response_writer.accept(proposal, ctx, sources, contract=response_writer.ADDRESSLESS_CONTRACT,
                                     parts=draft["parts"])
    assert all("why" not in item and "note" not in item for part in earlier["checklists"] for item in part["items"])
    assert response_writer.validate(deepcopy(earlier), ctx, sources) == earlier


def test_v11_each_ask_for_an_item_opens_it_from_the_writers_own_words():
    """The readability design (owner, 18 Oct 2026: "exactly the way your artifact has
    presented"): each ask under "What I need from you", and an ask in "In short", opens the
    checklist item it asks for. From writer v11 an item names the words of each ask for it,
    copied from its part's questions or summary; code places them as it places link words.
    An ask's link takes the place of a source's link on the same words (the source is then
    listed beneath its paragraph), and two asks never share words."""
    ctx, record, sources = two_disputes()
    given = lists(sources)["D1"]
    provision = alias(sources, "provision", "Complete provision")
    units = [{"kind": "summary", "text": "File in time; I need the exception and the second provision's words.",
              "uses": []},
             {"kind": "question", "text": "Does the exception apply to your client?",
              "uses": [{"source_kind": "provision", "source_id": provision, "link_words": "the exception apply"}]},
             {"kind": "question", "text": "Can you send the words of the second provision?", "uses": []}]
    given[0]["asked_words"] = ["the exception", "DOES the  exception apply"]
    given[1]["asked_words"] = ["send the words of the second provision", "the exception", "words"]

    def drafted(contract=response_writer.CONTRACT, items=given):
        return response_writer.accept({"units": deepcopy(units), "checklists": [
            {"checklist": deepcopy(items), "time_limit_ids": []}]}, ctx, sources,
            parts=[{"dispute_id": "D1", "units": 3}], contract=contract)

    draft = drafted()
    summary, first, second = draft["units"]
    one, two = draft["checklists"][0]["items"]
    at = summary["text"].index("the exception")
    assert one["asked"] == [
        {"unit_id": summary["id"], "text": "the exception", "start": at, "end": at + len("the exception")},
        {"unit_id": first["id"], "text": "Does the exception apply", "start": 0, "end": 24}]
    # "the exception" is already an ask in both places, and one word is no link.
    at = second["text"].index("send")
    assert two["asked"] == [{"unit_id": second["id"], "text": "send the words of the second provision",
                             "start": at, "end": len(second["text"]) - 1}]
    assert "words" not in first["uses"][0]  # the ask's link holds those words; the passage is listed
    assert response_writer.validate(deepcopy(draft), ctx, sources) == draft
    # An ask goes to the item that named it first: every item's first asked words are placed
    # before any item's second (the live run of 19 Oct 2026 named one question for two items).
    ranked = deepcopy(given)
    ranked[0]["asked_words"] = ["the exception", "send the words of the second provision"]
    ranked[1]["asked_words"] = ["send the words of the second provision"]
    one, two = drafted(items=ranked)["checklists"][0]["items"]
    assert [ask["text"] for ask in one["asked"]] == ["the exception"]
    assert [ask["text"] for ask in two["asked"]] == ["send the words of the second provision"]
    # The model must give asked_words (strict output names every field); admission takes an
    # item without them as one no ask is for.
    wire = response_writer.PART_SCHEMA_V11["properties"]["checklist"]["items"]
    admitted = response_writer.SCHEMA_V11["properties"]["checklists"]["items"]["properties"]["checklist"]["items"]
    assert "asked_words" in wire["required"] and "asked_words" not in admitted["required"]
    plain = [{key: value for key, value in item.items() if key != "asked_words"} for item in given]
    assert [item["asked"] for item in drafted(items=plain)["checklists"][0]["items"]] == [[], []]
    assert "asked_words" in " ".join(response_writer.SYSTEM.split())
    # A v10 draft has no asks, and its source keeps its link.
    earlier = drafted(response_writer.PLACED_CONTRACT, plain)
    assert all("asked" not in item for item in earlier["checklists"][0]["items"])
    assert earlier["units"][1]["uses"][0]["words"]["text"] == "the exception apply"
    assert response_writer.validate(deepcopy(earlier), ctx, sources) == earlier


class Asking(ChecklistModel):
    """Dispute 1's part asks for its first item in its one question (writer v11), whose held
    passage it names on the same words."""
    def structured(self, prompt, schema, tier, **kwargs):
        result = super().structured(prompt, schema, tier, **kwargs)
        if (json.loads(prompt.user)["this_part"]["dispute"] or {}).get("id") == "D1":
            result.data["units"][0].update(kind="question", text="Can you send the exception it makes?", uses=[
                {"source_kind": "provision", "source_id": alias(self.sources, "provision", "Complete provision"),
                 "link_words": "send the exception"}])
            result.data["checklist"][0]["asked_words"] = ["send the exception"]
        return result


def test_v11_the_review_sees_which_ask_opens_which_item():
    """Writer v11 (19 Oct 2026): the review is shown the asks that open each item, so a
    question linked to an item it does not ask for can be found like any other fault."""
    ctx, record, sources = two_disputes()
    draft = response_writer.write(Asking(sources), ctx, record, sources)
    model, review = checked(ctx, record, sources, draft)
    assert review["accepted"]
    shown = json.loads(model.calls[0][0].user)["complete_draft_proposal"]["checklists"]
    assert shown[1]["items"][0]["asked_in"] == [{"unit": "U2", "words": "send the exception"}]
    assert "asked_in" not in shown[1]["items"][1] and "asked_in" not in shown[2]["items"][0]
    assert "asked_in" in " ".join(response_review.SYSTEM.split())


def test_v16_an_ask_carries_the_item_it_opens_as_the_answer_admitted_it():
    """Rendering v16 (19 Oct 2026; the readability design): a question or summary carries
    each ask in it with the item it opens - as the matter keeps it, so the page can show it
    in the reading pane - and the dispute it belongs to. An item left out carries no ask, and
    an earlier rendering shows none."""
    ctx, record, sources = two_disputes()
    draft = response_writer.write(Asking(sources), ctx, record, sources)
    model, review = checked(ctx, record, sources, draft)
    authorities = response_authorities.check(ctx, record, sources, draft)
    execution = turn.execution_record(record)
    elements = response_rendering.render(ctx, record, sources, draft, review, execution,
                                         authority_evidence=authorities)
    asking = next(element for element in elements if element["text"] == "Can you send the exception it makes?")
    ask, = asking["asks"]
    item = draft["checklists"][1]["items"][0]
    assert {key: ask[key] for key in ("start", "end", "text", "dispute")} == {
        "start": 8, "end": 26, "text": "send the exception", "dispute": {"id": "D1", "name": "Dispute 1"}}
    assert ask["item"] == {key: value for key, value in checklist.records(ctx, {
        "draft": draft, "research": record, "sources": sources, "calculation": None,
        "release": None})["checklist"]["disputes"][0]["items"][0].items() if key != "id"}
    assert ask["item"]["need"] == item["need"] and ask["item"]["law"]["held_in"] == ctx["latest"]["turn_id"]
    assert [element["asks"] for element in elements if element["kind"] == "QUESTION" and element is not asking] == [
        [], []]
    # The ask lists no sources beneath it: the item it opens shows the law that requires it.
    assert asking["inline_citations"] == [] and asking["citation_markers"] == []
    activity = {"contract": turn.RECORDS_CONTRACT, "interpretation": {"units": []}, "research": record,
                "sources": sources,
                "draft": draft, "review": review, "execution": execution,
                "rendering_contract": response_rendering.CONTRACT, "authority_evidence": authorities,
                "calculation": calculation.skipped(), "release": None}
    assert turn.validate_activity(activity, ctx, elements) == activity
    # An item the review still faults is left out, and its ask opens nothing.
    data = positive(draft, requests=[request(ctx, draft)])
    data.update(verdict="reject", findings=[{"category": "framing", "unit_ids": ["C1"], "sources": [],
                                              "mismatch": "C1 overstates it."}])
    _, faulted = checked(ctx, record, sources, draft, data)
    left = response_rendering.render(ctx, record, sources, draft, faulted, execution, authority_evidence=authorities,
                                     held={"parts": [], "date_findings": [],
                                           "left_out": [{"dispute_id": "D1", "items": [item["id"]]}]})
    assert next(element for element in left if element["text"] == asking["text"])["asks"] == []
    earlier = response_rendering.render(ctx, record, sources, draft, review, execution, authority_evidence=authorities,
                                        contract=response_rendering.CONFINED_CONTRACT)
    assert all("asks" not in element for element in earlier)
    assert next(element for element in earlier if element["text"] == asking["text"])["citation_markers"]
