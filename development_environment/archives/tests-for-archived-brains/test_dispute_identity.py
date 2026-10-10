"""Disputes and objectives keep one identity as the account develops.

Rule (legal brain 2.4.1, 2.4.4, 2.4.5): every extracted item is either new or
names exactly one OPEN saved item of its own kind that the latest message
changes (adds, corrects, contradicts, resolves, withdraws). Saved items are
numbered D1, D2 ... and O1, O2 ... in order of first independent acceptance, so
replay reproduces every ID; a resolution or withdrawal closes an item and older
wording cannot revive it; reopening a conversation re-checks every saved change
against the items open when it was made. Scripted model outputs here prove the
mechanics, not the model's judgment -- that is measured live.
"""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from nm.brain.dispute_queries import research_input
from nm.brain.disputes_objectives import extraction_units, open_items
from nm.brain.release import _confirmation_question
from nm.brain.turn import BrainRefused, saved_items, saved_rows
from nm.shared.model_port import SchemaViolation
from tests.test_brain_disputes_objectives import ExtractionModel, extract, item, output, selection
from tests.test_current_brain_app import DEPOSIT_AIM_QUESTION, MIXED_MESSAGE, assert_ok, mixed_outputs

HISTORY = [{"role": "advocate", "text": "The supplier refuses delivery. I want the goods delivered."},
           {"role": "nm", "text": "Message received."}]
SAVED = [{"id": "D1", "kind": "disputes", "title": "Refused delivery",
          "description": "The supplier refuses delivery.", "confirmed": None},
         {"id": "O1", "kind": "objectives", "title": "Delivery of the goods",
          "description": "The user wants the goods delivered.", "confirmed": False}]
LATEST = "The supplier has now delivered the goods."


def follow_up(response):
    return extract(ExtractionModel(response), LATEST, "information", HISTORY, saved=SAVED)


def test_follow_up_shows_saved_items_and_limits_each_change_to_open_items_of_its_kind():
    model = ExtractionModel(output())
    extract(model, LATEST, "information", HISTORY, saved=SAVED)
    prompt, schema, _, _ = model.calls[0]
    payload = json.loads(prompt.user)
    assert payload["saved_items"] == [
        {"id": "D1", "kind": "dispute", "title": "Refused delivery", "description": "The supplier refuses delivery."},
        {"id": "O1", "kind": "objective", "title": "Delivery of the goods",
         "description": "The user wants the goods delivered.", "confirmed": False}]
    targets = {kind: schema["properties"][kind]["items"]["properties"]["target_id"] for kind in ("disputes", "objectives")}
    assert targets["disputes"]["anyOf"][0]["enum"] == ["D1"]
    assert targets["objectives"]["anyOf"][0]["enum"] == ["O1"]


@pytest.mark.parametrize("wrong", [
    item(operation="adds", target_id=None),          # a change that names nothing
    item(operation="new", target_id="D1"),           # a new item that claims a saved one
    item(operation="resolves", target_id="D9"),      # an item that is not open
    item(operation="adds", target_id="O1"),          # an item of the other kind
])
def test_a_change_names_exactly_one_open_saved_item_of_its_kind_or_is_held_alone(wrong):
    result = follow_up(output(disputes=[wrong, item(operation="resolves", target_id="D1",
                                                    title="Goods delivered")]))
    assert [row["id"] for row in result["proposal"]["disputes"]] == ["dispute:2"]
    assert result["proposal"]["disputes"][0]["target_id"] == "D1"
    assert result["issues"][0]["unit"] == "dispute:1"


def test_one_message_makes_at_most_one_change_to_a_saved_item():
    result = follow_up(output(disputes=[item(operation="adds", target_id="D1"),
                                        item(operation="corrects", target_id="D1")]))
    assert [row["id"] for row in result["proposal"]["disputes"]] == ["dispute:1"]
    assert "already has a change" in result["issues"][0]["reason"]


def test_saved_change_cannot_be_rewritten_into_another_shape():
    saved = follow_up(output(disputes=[item(operation="resolves", target_id="D1", title="Goods delivered",
                                            clarification="  ")]))
    record = saved["proposal"]["disputes"][0]
    assert record["clarification"] is None and record["title"] == "Goods delivered"
    assert extraction_units(saved)
    for damage in ({"operation": "new"}, {"target_id": "O1"}, {"target_id": None}, {"title": " "},
                   {"operation": "settles"}):
        changed = deepcopy(saved)
        changed["proposal"]["disputes"][0].update(damage)
        with pytest.raises(SchemaViolation):
            extraction_units(changed)


def record(identity, operation="new", target=None, title="Title", description="Description"):
    kind = "disputes" if identity.startswith("dispute") else "objectives"
    return identity, {"kind": kind, "proposal": {"id": identity, "title": title, "description": description,
                                                 "operation": operation, "target_id": target}}


def turn(*records, accepted=None):
    units = dict(records)
    return units, set(units) if accepted is None else set(accepted)


def test_ids_follow_first_acceptance_changes_update_and_closed_items_stay_closed():
    first = turn(record("dispute:1", title="Refused delivery"), record("dispute:2", title="Never accepted"),
                 record("objective:1", title="Delivery"), accepted=["dispute:1", "objective:1"])
    second = turn(record("dispute:1", "adds", "D1", title="Refused delivery and kept tools"),
                  record("dispute:2", title="Unpaid invoice"))
    third = turn(record("dispute:1", "withdraws", "D1"))
    assert [(row["id"], row["title"]) for row in open_items([first])] == [("D1", "Refused delivery"), ("O1", "Delivery")]
    assert [(row["id"], row["title"]) for row in open_items([first, second])] == [
        ("D1", "Refused delivery and kept tools"), ("O1", "Delivery"), ("D2", "Unpaid invoice")]
    assert [row["id"] for row in open_items([first, second, third])] == ["O1", "D2"]
    assert open_items([first, second, third]) == open_items([first, second, third])  # replay is exact
    with pytest.raises(SchemaViolation):
        open_items([first, second, third, turn(record("dispute:1", "adds", "D1"))])  # D1 is closed
    legacy = {"dispute:1": {"kind": "disputes", "proposal": {"id": "dispute:1", "description": "Old record"}}}
    assert open_items([(legacy, {"dispute:1"})])[0] == {
        "id": "D1", "kind": "disputes", "title": "Old record", "description": "Old record", "confirmed": None}


def test_only_an_objective_awaiting_confirmation_is_confirmed_and_always_by_its_saved_wording():
    confirmed = follow_up(output(objectives=[item(operation="confirms", target_id="O1",
                                                  title="Retyped title", description="Retyped words")]))
    record = confirmed["proposal"]["objectives"][0]
    assert (record["title"], record["description"]) == ("Delivery of the goods",
                                                        "The user wants the goods delivered.")
    dispute = follow_up(output(disputes=[item(operation="confirms", target_id="D1")]))
    assert dispute["proposal"]["disputes"] == [] and "never put to the user" in dispute["issues"][0]["reason"]
    settled = [{**row, "confirmed": True} if row["kind"] == "objectives" else row for row in SAVED]
    again = extract(ExtractionModel(output(objectives=[item(operation="confirms", target_id="O1")])),
                    LATEST, "information", HISTORY, saved=settled)
    assert again["proposal"]["objectives"] == [] and "already confirmed" in again["issues"][0]["reason"]


def test_nm_wording_awaits_confirmation_until_confirmed_and_rewording_asks_again():
    first = turn(record("objective:1", title="Delivery"), record("dispute:1", title="Refused delivery"))
    confirm = turn(record("objective:1", "confirms", "O1", title="Delivery"))
    reword = turn(record("objective:1", "corrects", "O1", title="Delivery by Friday"))
    states = lambda turns: {row["id"]: row["confirmed"] for row in open_items(turns)}  # noqa: E731
    assert states([first]) == {"D1": None, "O1": False}
    assert states([first, confirm]) == {"D1": None, "O1": True}
    assert states([first, confirm, reword]) == {"D1": None, "O1": False}
    with pytest.raises(SchemaViolation):  # a confirmation repeats the wording it confirms
        open_items([first, turn(record("objective:1", "confirms", "O1", title="Other words"))])
    with pytest.raises(SchemaViolation):  # and settles it only once
        open_items([first, confirm, confirm])


def asked(kind, operation, title):
    return {"kind": kind, "proposal": {"title": title, "operation": operation}}


def test_reply_asks_once_about_each_accepted_objective_nm_worded_and_never_about_disputes():
    units = {"dispute:1": asked("disputes", "new", "Refused delivery"),
             "objective:1": asked("objectives", "new", "Delivery of the goods"),
             "objective:2": asked("objectives", "corrects", "Delivery by Friday"),
             "objective:3": asked("objectives", "confirms", "Refund"),
             "objective:4": asked("objectives", "withdraws", "Compensation"),
             "objective:5": asked("objectives", "new", "Not accepted")}
    proof = {"unit_reviews": [{"unit_id": key, "verdict": "unsupported" if key == "objective:5" else "supported"}
                              for key in units]}
    assert _confirmation_question(units, proof) == (
        "I've noted these aims: “Delivery of the goods”; “Delivery by Friday”. Are they right?")
    single = {key: value for key, value in units.items() if key != "objective:2"}
    assert _confirmation_question(single, proof) == (
        "I've noted this aim: “Delivery of the goods”. Is that right?")
    assert _confirmation_question({"dispute:1": units["dispute:1"]}, proof) is None


def confirming_outputs():
    return [{"label": "information"},
            {"disputes": [], "objectives": [{
                "title": "Retyped", "description": "Retyped", "operation": "confirms", "target_id": "O1",
                "uncertainty": None, "clarification": None,
                "selections": [{"passage_id": "current:p1", "purpose": "support"}]}]},
            {"greeting": False, "unit_reviews": [{"unit_id": "objective:1", "verdict": "supported"}],
             "readings": {"current:p1": [{
                 "kind": "objective", "contribution": "reported", "description": "The user confirms the aim.",
                 "support_passage_ids": ["current:p1"], "context_passage_ids": [], "uncertainty": None,
                 "represented_by": ["objective:1"]}]}}]


RESOLVED = "The supplier has now returned the deposit."


def resolving_outputs():
    def change(kind, target, title):
        return {"title": title, "description": f"The advocate reports the supplier returned the deposit ({kind}).",
                "operation": "resolves", "target_id": target, "uncertainty": None, "clarification": None,
                "selections": [{"passage_id": "current:p1", "purpose": "support"}]}

    def reading(kind, unit):
        return {"kind": kind, "contribution": "resolved", "description": "The deposit was returned.",
                "support_passage_ids": ["current:p1"], "context_passage_ids": [], "uncertainty": None,
                "represented_by": [unit]}

    return [{"label": "information"},
            {"disputes": [change("dispute", "D1", "Deposit returned")],
             "objectives": [change("objective", "O1", "Deposit returned")]},
            {"greeting": False, "readings": {"current:p1": [reading("dispute", "dispute:1"),
                                                            reading("objective", "objective:1")]},
             "unit_reviews": [{"unit_id": "dispute:1", "verdict": "supported"},
                              {"unit_id": "objective:1", "verdict": "supported"}]}]


def test_a_saved_dispute_is_resolved_by_name_closes_and_replays_its_check(harness):
    app = harness(*mixed_outputs(MIXED_MESSAGE), *resolving_outputs())
    chat_id = assert_ok(app.post(MIXED_MESSAGE))["chat_id"]
    assert [row["id"] for row in saved_items(saved_rows(app.held(chat_id), "adv_wiring"))] == ["D1", "O1"]
    assert_ok(app.post(RESOLVED, "turn_second", chat_id=chat_id, expected_version=1))
    extraction = json.loads(app.model.calls[4][0].user)
    assert [row["id"] for row in extraction["saved_items"]] == ["D1", "O1"]
    review = json.loads(app.model.calls[5][0].user)
    assert [row["id"] for row in review["saved_items"]] == ["D1", "O1"]
    assert review["proposals"]["disputes"][0]["operation"] == "resolves"
    held = app.held(chat_id)
    rows = saved_rows(held, "adv_wiring")
    assert saved_items(rows) == []  # both closed; older wording cannot revive them
    assert research_input(rows[1]["preparation"], rows[1]["release"])["disputes"] == {}  # nothing to research
    assert_ok(app.client.get("/api/chats/" + chat_id))
    tampered = deepcopy(held.brain_chat)
    for record_ in (tampered[1]["preparation"]["proposal"]["disputes"][0],
                    tampered[1]["release"]["units"]["dispute:1"]["proposal"]):
        record_["target_id"] = "D2"  # an item that was never open
    with pytest.raises(BrainRefused):
        saved_rows(replace(held, brain_chat=tampered), "adv_wiring")


def test_a_yes_confirms_the_saved_objective_by_name_and_it_is_not_asked_again(harness):
    app = harness(*mixed_outputs(MIXED_MESSAGE), *confirming_outputs())
    first = assert_ok(app.post(MIXED_MESSAGE))
    assert [element["text"] for element in first["elements"]] == ["Message received.", DEPOSIT_AIM_QUESTION]
    chat_id = first["chat_id"]
    second = assert_ok(app.post("Yes, that's right.", "turn_second", chat_id=chat_id, expected_version=1))
    assert [element["text"] for element in second["elements"]] == ["Message received."]
    extraction = json.loads(app.model.calls[4][0].user)
    assert extraction["saved_items"][1] == {"id": "O1", "kind": "objective", "title": "Return of the deposit",
                                            "description": "The advocate wants the deposit returned.",
                                            "confirmed": False}
    rows = saved_rows(app.held(chat_id), "adv_wiring")
    assert {row["id"]: row["confirmed"] for row in saved_items(rows)} == {"D1": None, "O1": True}
    stored = rows[1]["preparation"]["proposal"]["objectives"][0]
    assert (stored["title"], stored["description"]) == ("Return of the deposit",
                                                        "The advocate wants the deposit returned.")


@pytest.fixture
def harness(tmp_path):
    from tests.test_current_brain_app import Harness, WiredModel
    built = []

    def build(*outputs):
        result = Harness(tmp_path / str(len(built)), WiredModel(*outputs))
        built.append(result)
        return result

    yield build
    for result in built:
        result.client.close()
