"""The attributed detail record follows source-linked disputes across turns."""
import json
from dataclasses import replace

import pytest

from nm.brain.dispute_state import proposed_disputes
from nm.brain.material_state import material_record
from nm.work_the_file.matter_contracts import Matter
from tests.test_brain_board_proposals import dispute, saved_turn
from tests.test_brain_material import Model, material, plan, send


def _record(candidate, turn_id, index):
    return {**candidate, "id": f"{turn_id}:material:{index}",
            "source_turn_id": turn_id, "state": "proposed"}


def _board(client, matter_id):
    response = client.get(f"/api/matters/{matter_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_first_turn_links_shared_details_and_preserves_other_placements(
        client, wired, monkeypatch):
    message = ("The supplier missed delivery. The buyer withheld payment. "
               "The contract covers both transactions. A bank statement exists. "
               "A courier mentioned another address.")
    candidates = [
        material("dispute", "Late delivery", "The supplier missed delivery."),
        material("dispute", "Withheld payment", "The buyer withheld payment."),
        material("evidence", "The contract covers both transactions.",
                 "The contract covers both transactions.", placement="disputes",
                 dispute_ids=("first:material:1", "first:material:2")),
        material("evidence", "A bank statement exists.",
                 "A bank statement exists.", placement="matter"),
        material("circumstance", "A courier mentioned another address.",
                 "A courier mentioned another address.", placement="unresolved"),
    ]
    model = Model([plan(message, candidates=candidates, opening=True)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    answer = send(client, message, "first")

    assert answer.status_code == 200, answer.text
    result = answer.json()
    assert result["metrics"]["llm_calls"] == 8
    assert [call.operation for call in model.material_calls] == [
        "extract_disputes", "extract_legal_details"]
    detail_input = json.loads(model.material_calls[1].user)
    assert [row["id"] for row in detail_input["assignment_targets"]
            if row["kind"] == "dispute"] == [
        "first:material:1", "first:material:2"]
    board = _board(client, result["matter_id"])
    record = board["material_record"]
    assert record["state"] == "ok"
    assert [row["id"] for row in record["by_dispute"]["first:material:1"]] == [
        "first:material:3"]
    assert [row["id"] for row in record["by_dispute"]["first:material:2"]] == [
        "first:material:3"]
    assert [row["id"] for row in record["matter"]] == ["first:material:4"]
    assert [row["id"] for row in record["unresolved"]] == ["first:material:5"]
    assert [row["id"] for row in record["history"]] == [
        "first:material:3", "first:material:4", "first:material:5"]
    assert record["by_dispute"]["first:material:1"][0]["quoted"] in message
    assert wired.store.load(result["matter_id"]).facts == ()

    replay = send(client, message, "first")
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert len(model.calls) == 1 and len(model.material_calls) == 2


def test_later_possible_matter_and_uncertain_material_stay_out_of_current_record(
        client, wired, monkeypatch):
    opening = ("My client contests a delivery charge. "
               "A receipt for that charge is held.")
    diversion = ("A different client contests a wage deduction. "
                 "Their wage slip is held. An unrelated issue may concern this file.")
    continuation = "The first client's delivery note is also available."
    opening_rows = [
        material("dispute", "Delivery charge dispute",
                 "My client contests a delivery charge."),
        material("evidence", "A receipt for the charge is held.",
                 "A receipt for that charge is held.", placement="disputes",
                 dispute_ids=("opening:material:1",)),
    ]
    diversion_rows = [
        material("dispute", "Wage deduction dispute",
                 "A different client contests a wage deduction.", scope="proposed"),
        material("evidence", "A wage slip is held for the other client.",
                 "Their wage slip is held.", scope="proposed"),
        material("circumstance", "The file association is uncertain.",
                 "An unrelated issue may concern this file.", scope="uncertain"),
    ]
    current_rows = [material(
        "evidence", "A delivery note is available for the first client.",
        continuation, scope="current", placement="disputes",
        dispute_ids=("opening:material:1",))]
    proposed_item = {"request": diversion, "relation": "new",
                     "matter_scope": "proposed", "priority": "ordinary",
                     "next_step": "legal_work",
                     "reply": "I will keep the new issue separate while reviewing the first file.",
                     "clarification": ""}
    model = Model([
        plan(opening, candidates=opening_rows, opening=True),
        plan(diversion, candidates=diversion_rows, items=[proposed_item]),
        plan(continuation, candidates=current_rows),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = send(client, opening, "opening")
    assert first.status_code == 200, first.text
    opened = first.json()
    second = send(client, diversion, "diversion", opened=opened)
    assert second.status_code == 200, second.text
    board = _board(client, opened["matter_id"])
    assert [row["id"] for row in board["proposed_disputes"]["rows"]] == [
        "opening:material:1"]
    assert [row["id"] for row in board["proposed_disputes"]["history"]] == [
        "opening:material:1"]
    assert [row["id"] for row in board["material_record"]["rows"]] == [
        "opening:material:2"]
    assert [row["id"] for row in board["material_record"]["history"]] == [
        "opening:material:2"]
    assert [row["id"] for row in board["material_record"]["excluded_scope"]] == [
        "diversion:material:3"]
    assert board["material_record"]["coverage"]["state"] == "partial"
    saved_diversion = wired.store.load(opened["matter_id"]).brain_chat[1]
    assert [row["matter_scope"] for row in saved_diversion["response"]["material"]] == [
        "proposed", "other", "uncertain"]

    third = send(client, continuation, "continuation", opened=opened)
    assert third.status_code == 200, third.text
    detail_inputs = [json.loads(call.user) for call in model.material_calls
                     if call.operation == "extract_legal_details"]
    assert [row["id"] for row in detail_inputs[2]["assignment_targets"]
            if row["kind"] == "dispute"] == [
        "opening:material:1"]
    assert [row["id"] for row in detail_inputs[2]["active_material"]] == [
        "opening:material:2", "diversion:material:3"]
    assert detail_inputs[2]["active_material"][1]["matter_scope"] == "uncertain"
    after = _board(client, opened["matter_id"])["material_record"]
    assert [row["id"] for row in after["by_dispute"]["opening:material:1"]] == [
        "opening:material:2", "continuation:material:1"]


def test_route_less_legacy_opening_is_kept_but_later_proposal_is_unassigned():
    first = "The delivery charge is disputed. A receipt exists."
    later = "A different charge is disputed. Another receipt exists."
    first_rows = [
        _record(dispute("Delivery charge", "The delivery charge is disputed."),
                "first", 1),
        _record(material("evidence", "A receipt exists.", "A receipt exists.",
                         placement="disputes", dispute_ids=("first:material:1",)),
                "first", 2),
    ]
    later_rows = [
        _record(dispute("Different charge", "A different charge is disputed."),
                "later", 1),
        _record(material("evidence", "Another receipt exists.",
                         "Another receipt exists.", placement="disputes",
                         dispute_ids=("later:material:1",)), "later", 2),
    ]
    matter = Matter(id="mat_links", advocate_id="adv", title="Charge matter",
                    brain_ready=True, brain_chat=(
                        saved_turn("first", first, first_rows),
                        saved_turn("later", later, later_rows)))

    disputes = proposed_disputes(matter)
    details = material_record(matter, disputes=disputes)
    assert disputes["state"] == details["state"] == "ok"
    assert [row["id"] for row in disputes["rows"]] == ["first:material:1"]
    assert [row["id"] for row in disputes["history"]] == ["first:material:1"]
    assert [row["id"] for row in details["rows"]] == ["first:material:2"]
    assert [row["id"] for row in details["history"]] == ["first:material:2"]
    assert [row["id"] for row in matter.brain_chat[1]["response"]["material"]] == [
        "later:material:1", "later:material:2"]


def test_unlinked_detail_withdrawal_marks_record_incomplete():
    first = "A receipt exists."
    later = "I withdraw the receipt account."
    original = _record(material("evidence", "A receipt exists.", first,
                                placement="matter"), "first", 1)
    withdrawal = _record(material(
        "evidence", "The receipt account is withdrawn.", later,
        relation="withdraws", scope="current", placement="matter",
        references=({"turn_id": "first", "role": "advocate",
                     "quoted": first},)), "later", 1)
    matter = Matter(id="mat_links", advocate_id="adv", title="Receipt matter",
                    brain_ready=True, brain_chat=(
                        saved_turn("first", first, [original]),
                        saved_turn("later", later, [withdrawal])))

    disputes = proposed_disputes(matter)
    record = material_record(matter, disputes=disputes)
    assert disputes["state"] == "ok"
    assert record["state"] == "incomplete"
    assert [row["id"] for row in record["rows"]] == ["first:material:1"]
    assert record["problems"]
    assert matter.brain_chat[1]["response"]["material"][0]["relation"] == "withdraws"


def test_correction_and_withdrawal_retire_only_cited_details(
        client, wired, monkeypatch):
    first = ("The shipment was late. It arrived on 4 May. "
             "The invoice was due on 8 May.")
    next_message = ("Correction: the shipment arrived on 6 May, not 4 May. "
                    "Withdraw my statement that the invoice was due on 8 May.")
    first_rows = [
        material("dispute", "Shipment delay", "The shipment was late."),
        material("event", "The advocate reports arrival on 4 May.",
                 "It arrived on 4 May.", placement="disputes",
                 dispute_ids=("original:material:1",)),
        material("circumstance", "The invoice was due on 8 May.",
                 "The invoice was due on 8 May.", placement="matter"),
    ]
    next_rows = [
        material("event", "The advocate corrects arrival to 6 May.",
                 "Correction: the shipment arrived on 6 May, not 4 May.",
                 relation="corrects", scope="current", placement="disputes",
                 dispute_ids=("original:material:1",),
                 related_material_ids=("original:material:2",),
                 references=({"turn_id": "original", "role": "advocate",
                              "quoted": "It arrived on 4 May."},)),
        material("circumstance", "The invoice due date is withdrawn.",
                 "Withdraw my statement that the invoice was due on 8 May.",
                 relation="withdraws", scope="current", placement="matter",
                 related_material_ids=("original:material:3",),
                 references=({"turn_id": "original", "role": "advocate",
                              "quoted": "The invoice was due on 8 May."},)),
    ]
    model = Model([plan(first, candidates=first_rows, opening=True),
                   plan(next_message, candidates=next_rows)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "original")
    assert opened.status_code == 200, opened.text
    changed = send(client, next_message, "change", opened=opened.json())

    assert changed.status_code == 200, changed.text
    assert changed.json()["metrics"]["llm_calls"] == 7
    record = _board(client, opened.json()["matter_id"])["material_record"]
    assert record["state"] == "ok"
    assert [row["id"] for row in record["rows"]] == ["change:material:1"]
    assert [row["id"] for row in record["history"]] == [
        "original:material:2", "original:material:3",
        "change:material:1", "change:material:2"]
    assert [row["id"] for row in record["by_dispute"]["original:material:1"]] == [
        "change:material:1"]
    assert record["matter"] == []
    assert record["history"][2]["prior_references"][0]["quoted"] == (
        "It arrived on 4 May.")
    detail_inputs = [json.loads(call.user) for call in model.material_calls
                     if call.operation == "extract_legal_details"]
    assert [row["id"] for row in detail_inputs[1]["active_material"]] == [
        "original:material:2", "original:material:3"]
    assert wired.store.load(opened.json()["matter_id"]).facts == ()


@pytest.mark.parametrize("supported", (True, False))
def test_linked_original_sources_and_selected_context_reach_independent_check(
        client, wired, monkeypatch, supported):
    first = ("The work stopped. It stopped on 4 May. "
             "We want to understand the sequence.")
    latest = "Correction: it stopped on 6 May."
    context = "We want to understand the sequence."
    original = [
        material("dispute", "Stopped work", "The work stopped."),
        material("event", "The advocate reports work stopped on 4 May.",
                 "It stopped on 4 May.", placement="disputes",
                 dispute_ids=("original:material:1",)),
    ]
    revised = material(
        "event", "The advocate corrects the reported date to 6 May."
        if supported else "The corrected event date is proved by a record.",
        latest, relation="corrects", scope="current", placement="disputes",
        dispute_ids=("original:material:1",),
        related_material_ids=("original:material:2",),
        references=({"turn_id": "original", "role": "advocate",
                     "quoted": context},))

    class CheckingModel(Model):
        def __init__(self):
            super().__init__([plan(first, candidates=original, opening=True),
                              plan(latest, candidates=[revised])])
            self.check_inputs = []

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation != "verify_material_grounding":
                return result
            payload = json.loads(prompt.user)
            self.check_inputs.append(payload)
            if supported:
                return result
            candidates = {row["candidate_id"]: row
                          for row in payload["candidates"]}
            rejected = [{**row, "verdict": "reject",
                         "reason": "A reported correction does not prove the event."}
                        if candidates[row["candidate_id"]].get("relation") == "corrects"
                        else row for row in result.data["verdicts"]]
            return replace(result, data={"verdicts": rejected})

    model = CheckingModel()
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, first, "original")
    assert opened.status_code == 200, opened.text
    corrected = send(client, latest, "correction", opened=opened.json())

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["metrics"]["llm_calls"] == 7
    checked = [row for payload in model.check_inputs
               for row in payload["candidates"] if row.get("relation") == "corrects"]
    assert checked
    expected_sources = {("original", "advocate", words) for words in
                        (context, "It stopped on 4 May.")}
    for row in checked:
        assert {(ref["turn_id"], ref["role"], ref["quoted"])
                for ref in row["cited_earlier_passages"]} == expected_sources
    board = _board(client, opened.json()["matter_id"])["material_record"]
    assert [row["id"] for row in board["by_dispute"]["original:material:1"]] == (
        ["correction:material:1"] if supported else ["original:material:2"])
    if supported:
        saved = corrected.json()["material"][0]
        assert {(ref["turn_id"], ref["role"], ref["quoted"])
                for ref in saved["prior_references"]} == expected_sources
    else:
        assert corrected.json()["material"] == []
        assert [row["id"] for row in board["history"]] == ["original:material:2"]
    assert wired.store.load(opened.json()["matter_id"]).facts == ()


def test_invalid_detail_link_gets_one_repair_before_an_atomic_commit(
        client, wired, monkeypatch):
    message = "The tenant contests the charge. A receipt was retained."
    candidate = material("evidence", "The advocate reports retaining a receipt.",
                         "A receipt was retained.", placement="disputes",
                         dispute_ids=("repaired:material:1",))

    class RepairingModel(Model):
        def __init__(self):
            super().__init__([plan(message, candidates=[
                material("dispute", "Contested charge",
                         "The tenant contests the charge."), candidate],
                         opening=True)])
            self.rejected = False

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation == "extract_legal_details" and not self.rejected:
                self.rejected = True
                invalid = {**result.data["new_items"][0],
                           "assignment_ids": ["missing-dispute"]}
                return replace(result, data={"new_items": [invalid], "changes": []})
            return result

    model = RepairingModel()
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    response = send(client, message, "repaired")

    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["llm_calls"] == 9
    repair_inputs = [json.loads(call.user) for call in model.material_calls
                     if "original_input" in json.loads(call.user)]
    assert len(repair_inputs) == 1
    assert "assignment" in repair_inputs[0]["validation_issue"].lower()
    assert _board(client, response.json()["matter_id"])[
        "material_record"]["by_dispute"]["repaired:material:1"][0]["id"] == (
        "repaired:material:2")
    assert len(wired.store.load(response.json()["matter_id"]).brain_chat) == 1


def test_twice_invalid_detail_link_refuses_turn_without_partial_write(
        client, wired, monkeypatch):
    first = "The tenant contests the charge."
    next_message = "A receipt was retained."
    invalid = material("evidence", "A receipt was retained.", next_message,
                       scope="current", placement="disputes",
                       dispute_ids=("unknown:material:1",))
    model = Model([plan(first, candidates=[material(
        "dispute", "Contested charge", first)], opening=True),
                   plan(next_message, candidates=[invalid])])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "valid")
    assert opened.status_code == 200, opened.text
    refused = send(client, next_message, "invalid", opened=opened.json())

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["committed"] == "not_committed"
    saved = wired.store.load(opened.json()["matter_id"])
    assert [row["turn_id"] for row in saved.brain_chat] == ["valid"]
    assert [row["id"] for row in _board(client, opened.json()["matter_id"])[
        "proposed_disputes"]["rows"]] == ["valid:material:1"]
    assert [row["id"] for row in _board(client, opened.json()["matter_id"])[
        "material_record"]["history"]] == []
    assert len(model.material_calls) == 5


def test_legacy_detail_without_placement_stays_unresolved():
    message = "The delivery is disputed. The tracking number is available."
    issue = _record(dispute("Delivery dispute", "The delivery is disputed."),
                    "legacy", 1)
    old_detail = _record(material(
        "evidence", "The tracking number is available.",
        "The tracking number is available."), "legacy", 2)
    for field in ("placement", "dispute_ids", "related_material_ids"):
        old_detail.pop(field)
    matter = Matter(id="mat_legacy_detail", advocate_id="adv", title="Delivery",
                    brain_ready=True, brain_chat=(
                        saved_turn("legacy", message, [issue, old_detail],
                                   matter_id="mat_legacy_detail"),))

    disputes = proposed_disputes(matter)
    record = material_record(matter, disputes=disputes)

    assert disputes["state"] == record["state"] == "ok"
    assert record["by_dispute"]["legacy:material:1"] == []
    assert [row["id"] for row in record["unresolved"]] == ["legacy:material:2"]
    assert record["unresolved"][0]["quoted"] in message


def test_damaged_saved_detail_is_visible_as_incomplete_and_blocks_next_read(
        client, wired, monkeypatch):
    message = "The shipment is disputed. A dispatch note is available."
    model = Model([plan(message, candidates=[
        material("dispute", "Shipment dispute", "The shipment is disputed."),
        material("evidence", "A dispatch note is available.",
                 "A dispatch note is available.", placement="disputes",
                 dispute_ids=("first:material:1",))], opening=True)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, message, "first")
    assert opened.status_code == 200, opened.text
    matter_id = opened.json()["matter_id"]

    matter = wired.store.load(matter_id)
    saved = dict(matter.brain_chat[0])
    response = dict(saved["response"])
    proposals = [dict(row) for row in response["material"]]
    proposals[1]["quoted"] = "words absent from the advocate's message"
    response["material"] = proposals
    saved["response"] = response
    damaged = replace(matter, brain_chat=(saved,), version=matter.version + 1)
    wired.store.commit(damaged, expected_version=matter.version)

    board = _board(client, matter_id)
    assert board["proposed_disputes"]["state"] == "ok"
    assert board["material_record"]["state"] == "incomplete"
    assert board["material_record"]["problems"]
    continued = send(client, "The note was posted yesterday.", "second",
                     opened=opened.json())
    assert continued.status_code == 409, continued.text
    assert len(model.calls) == 1 and len(model.material_calls) == 2
    assert len(wired.store.load(matter_id).brain_chat) == 1


def test_old_dispute_link_follows_one_replacement_but_not_a_split():
    first_message = "The deal is disputed. The contract is signed."
    old_dispute = _record(dispute("Deal dispute", "The deal is disputed."),
                          "first", 1)
    old_detail = _record(material(
        "evidence", "The contract is signed.", "The contract is signed.",
        placement="disputes", dispute_ids=("first:material:1",)), "first", 2)
    old_detail["grounding"] = "advocate_semantic_v1"
    next_message = "Delivery and payment are separate disputes."
    prior = [{"turn_id": "first", "role": "advocate",
              "quoted": "The deal is disputed."}]

    def projected(labels):
        replacements = [_record(dispute(
            label, next_message, relation="corrects", scope="current",
            prior=prior, related=("first:material:1",)), "second", index)
            for index, label in enumerate(labels, start=1)]
        matter = Matter(id="mat_material_links", advocate_id="adv",
                        title="Deal", brain_ready=True, brain_chat=(
                            saved_turn("first", first_message,
                                       [old_dispute, old_detail],
                                       matter_id="mat_material_links"),
                            saved_turn("second", next_message, replacements,
                                       matter_id="mat_material_links")))
        disputes = proposed_disputes(matter)
        return material_record(matter, disputes=disputes), disputes

    replacement, one_issue = projected(["Updated deal dispute"])
    assert replacement["state"] == one_issue["state"] == "ok"
    assert [row["id"] for row in replacement["by_dispute"][
        "second:material:1"]] == ["first:material:2"]
    assert replacement["unresolved"] == []

    split, two_issues = projected(["Delivery dispute", "Payment dispute"])
    assert split["state"] == two_issues["state"] == "ok"
    assert all(rows == [] for rows in split["by_dispute"].values())
    assert [row["id"] for row in split["unresolved"]] == ["first:material:2"]


def test_legacy_detail_keeps_its_exact_quote_but_cannot_feed_research():
    message = "The notice is disputed. We have a letter."
    issue = _record(dispute("Notice dispute", "The notice is disputed."),
                    "old", 1)
    old_detail = _record(material(
        "evidence", "The other party admitted liability.",
        "We have a letter.", placement="disputes",
        dispute_ids=("old:material:1",)), "old", 2)
    matter = Matter(id="mat_legacy_detail", advocate_id="adv", title="Notice",
                    brain_ready=True, brain_chat=(saved_turn(
                        "old", message, [issue, old_detail],
                        matter_id="mat_legacy_detail"),))

    projection = material_record(matter, disputes=proposed_disputes(matter))

    assert projection["state"] == "ok"
    assert projection["unverified_count"] == 1
    assert projection["by_dispute"]["old:material:1"] == []
    assert projection["rows"][0]["statement"] == "We have a letter."
    assert projection["rows"][0]["grounding"] == "legacy_unverified"
    assert projection["unresolved"][0]["id"] == "old:material:2"


def test_transcript_exposes_legacy_detail_quote_without_old_model_assertion(
        client, wired, monkeypatch):
    message = "We have a signed letter."
    model = Model([plan(message, candidates=[material(
        "evidence", "We have a signed letter.", message)], opening=True)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, message, "legacy-transcript")
    assert opened.status_code == 200, opened.text
    matter_id = opened.json()["matter_id"]

    matter = wired.store.load(matter_id)
    saved = dict(matter.brain_chat[0])
    response = dict(saved["response"])
    proposal = dict(response["material"][0])
    proposal.pop("grounding")
    proposal["statement"] = "The other party admitted liability."
    response["material"] = [proposal]
    saved["response"] = response
    wired.store.commit(
        replace(matter, brain_chat=(saved,), version=matter.version + 1),
        expected_version=matter.version)

    transcript = client.get(f"/api/matters/{matter_id}/transcript")
    assert transcript.status_code == 200, transcript.text
    shown = transcript.json()["turns"][0]["material"][0]
    assert shown["statement"] == message
    assert shown["grounding"] == "legacy_unverified"
    assert "admitted" not in json.dumps(shown)
    assert wired.store.load(matter_id).brain_chat[0]["response"][
        "material"][0]["statement"] == "The other party admitted liability."

    replay = send(client, message, "legacy-transcript")
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["material"][0]["statement"] == message
    assert replay.json()["material"][0]["grounding"] == "legacy_unverified"
