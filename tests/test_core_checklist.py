"""The matter's checklist (owner decisions, 17 Oct 2026; built 18 Oct): each dispute's part
returns its checklist, code checks every quote, the review judges every item, and the
matter keeps its checklist as the conversation's records, re-derived on reopening, for
the board. Scripted fixtures exercise the wiring; they do not show that a real writer
lists what the law requires."""
from copy import deepcopy
import json

import pytest

from nm.core_engine import (
    answer_sources, checklist, matter_board, response_authorities, response_rendering, response_review,
    response_writer, turn,
)
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
        "D1": [{"need": "The exception the provision makes", "group": "needed",
                "law": {"source_id": alias(sources, "provision", "Complete provision"), "quote": "including its exception"},
                "carries": None, "status": "in_hand", "evidence": {"source_id": message, "quote": "applicable law"}},
               {"need": "The words of the second provision", "group": "needed",
                "law": {"source_id": alias(sources, "provision", "Different exact"), "quote": "Different exact words"},
                "carries": None, "status": "not_given", "evidence": None}],
        "D2": [{"need": "The chunk the judgment names", "group": "would_strengthen",
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
        result.data["time_limits"] = list(self.limits.get(dispute, []))
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
    assert draft["contract"] == response_writer.CONTRACT == "core_response_writer_v6"
    assert [len(part["items"]) for part in draft["checklists"]] == [0, 2, 1]  # the opening part has none
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


@pytest.mark.parametrize("case", [
    "law_not_in_its_passage", "law_from_a_message", "evidence_not_found", "not_given_with_evidence",
    "in_hand_without_evidence", "unclear_not_in_the_advocates_words", "law_and_carried",
    "neither_law_nor_carried", "carries_an_unknown_item", "an_opening_with_a_checklist", "blank_need"])
def test_a_checklist_item_is_admitted_only_on_exact_words_of_the_right_source(case):
    ctx, record, sources = two_disputes()
    given = lists(sources)
    change(given, sources, case)
    with pytest.raises(SchemaViolation):
        response_writer.write(ChecklistModel(sources, given), ctx, record, sources)


def test_a_dispute_may_name_only_the_time_limits_code_worked_out():
    with pytest.raises(SchemaViolation, match="did not work out: Last day to file"):
        written(limits={"D1": ["Last day to file"]})
    worked = {"state": "worked_out", "worked_out": [{"what": "Last day to file"}], "not_assessed": []}
    _, _, _, draft = written(limits={"D1": ["Last day to file"]}, time_limits=worked)
    assert [part["time_limits"] for part in draft["checklists"]] == [[], ["Last day to file"], []]


def test_a_disputes_time_limits_are_kept_as_code_worked_them_out_and_shown_in_its_words():
    calculation = {"today": "2026-10-18", "not_assessed": [{"what": "Notice period", "why": "no date is given"}],
                   "calculations": [{"what": "Last day to file the suit", "provision_name": "Article 54",
                                     "working": {"last_day": "2027-01-10"}, "standing": {"state": "open", "days": 84}}]}
    kept = checklist._limits(["Last day to file the suit", "Notice period", "Last day to file the suit"], calculation)
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


def test_the_review_judges_every_item_and_a_finding_on_one_concerns_only_its_section():
    ctx, record, sources, draft = written()
    model, review = checked(ctx, record, sources, draft)
    assert review["contract"] == "core_response_review_v6" and review["accepted"]
    shown = json.loads(model.calls[0][0].user)["complete_draft_proposal"]["checklists"]
    assert [[item["id"] for item in part["items"]] for part in shown] == [[], ["C1", "C2"], ["C3"]]
    assert shown[1]["items"][0]["law"] == {"source_id": "P1", "quote": "including its exception"}
    assert shown[1]["items"][0]["evidence"] == {"source_id": "M1", "quote": "applicable law"}
    assert "checklist item ID" in " ".join(response_review.SYSTEM.split())
    # Every item needs its verdict.
    data = positive(draft, requests=[request(ctx, draft)])
    data["units"] = [row for row in data["units"] if row["unit_id"] != "t2:c3"]
    with pytest.raises(SchemaViolation, match="checklist item"):
        checked(ctx, record, sources, draft, data)
    # A rejected item, named by its short ID, concerns its own dispute's section alone.
    data = positive(draft, requests=[request(ctx, draft)])
    data["verdict"] = "reject"
    for row in data["units"]:
        if row["unit_id"] == "t2:c3":
            row.update(unit_id="C3", verdict="rejected")
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
    given["D1"] = [{"need": "Proof of service", "group": "needed", "law": None, "carries": "K1",
                    "status": "not_given", "evidence": None}, given["D1"][1], given["D1"][0]]
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
                    {"need": "Proof the notice was served", "group": "needed",
                     "law": {"source_id": passage["id"], "quote": "Counsel submitted"}, "carries": None,
                     "status": "in_hand", "evidence": {"source_id": message, "quote": "The notice was served"}},
                    {"need": "The postal receipt", "group": "would_strengthen",
                     "law": {"source_id": passage["id"], "quote": "Counsel submitted"}, "carries": None,
                     "status": "coming_or_unclear",
                     "evidence": {"source_id": message, "quote": "I will send the postal receipt"}}]
            return result

    reply = run(store, Listing(legal=True), message="The notice was served on 2 March; I will send the postal receipt.")
    assert reply["committed"] == "committed"
    matter = store.load(chat_matter_id("owner", reply["chat_id"]))
    rows = turn.saved_rows(matter, "owner")
    assert rows[0]["activities"]["contract"] == turn.CONTRACT == "core_turn_v5"
    saved = rows[0]["records"]["checklist"]
    items = saved["disputes"][0]["items"]
    assert [(item["id"], item["status"], item["evidence"]["words"]) for item in items] == [
        ("K1", "in_hand", "The notice was served"), ("K2", "coming_or_unclear", "I will send the postal receipt")]
    board = matter_board.board(rows)
    shown = board["disputes"][0]["checklist"]
    assert shown["in_hand"] == 1 and [item["status"] for item in shown["items"]] == ["in_hand", "coming_or_unclear"]
    assert shown["items"][0]["evidence"]["given_at"] == reply["at"] and shown["answered_at"] == reply["at"]
    # Records that differ from what the turn admitted are refused on reopening.
    damaged = deepcopy(matter)
    rows_ = list(damaged.brain_chat)
    rows_[0] = {**rows_[0], "records": {**rows_[0]["records"], "checklist": {**saved, "disputes": []}}}
    from dataclasses import replace
    from nm.core_engine.conversation import digest
    rows_[0]["digest"] = digest({key: value for key, value in rows_[0].items() if key != "digest"})
    with pytest.raises(ConversationRefused):
        turn.saved_rows(replace(damaged, brain_chat=tuple(rows_)), "owner")
