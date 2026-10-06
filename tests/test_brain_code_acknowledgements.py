"""Code-owned acknowledgements through the public turn and durable replay boundary.

Scripted semantic decisions exercise mechanical publication behavior. They do
not qualify real-model source interpretation or semantic reviewer accuracy.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as boundary
from nm.brain.conversation import SchemaViolation
from tests.test_brain_material import send
from tests.test_brain_pressure_release import (
    BASE_TURN,
    DATE_ID,
    NEW_DATE,
    OLD_DATE,
    OLD_RIG,
    ORIGINAL,
    PassageModel,
    answer_plan,
    date_requirement,
    initial_plan,
    reopened,
    revision,
)


def record_plan(message, *, candidates=(), mode="record_acknowledgement", requirement=None):
    value = answer_plan(
        message, purposes=("interpretation_review",), candidates=candidates,
        requirement=requirement or date_requirement(),
        reply="The requested record result still needs its checked outcome.")
    value["items"][0]["response_mode"] = mode
    return value


def install(wired, monkeypatch, plans, controls=(), *, model_type=PassageModel):
    model = model_type(plans, controls)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    return model


def test_false_pure_acknowledgement_is_replaced_while_task_stays_pending(
        client, wired, monkeypatch):
    message = "Correct the northern carton record to show 19 April."
    lie = "I changed and saved the carton date as requested."
    model = install(wired, monkeypatch, [initial_plan(), record_plan(message)],
                    [{}, {"status": "unresolved", "prose": lie}])
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    before = len(model.seen)
    delivered = send(client, message, "pure-pending", opened=baseline)
    assert delivered.status_code == 200
    result = delivered.json()
    saved, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG]
    assert lie not in json.dumps(result["elements"])
    execution = result["material_coverage"]["execution"]
    assert execution["requests"][0]["acknowledgement_delivery"] == "code_only"
    assert execution["requests"][0]["fulfillment"] == "unfinished"
    unit = result["continuation"]["units"][0]
    assert unit["record_outcome"]["status"] == "unresolved"
    assert unit["progress_updates"] == []
    assert all("remains unfinished" in block["text"] for block in unit["blocks"])
    assert saved.brain_chat[-1]["response"]["elements"] == result["elements"]
    progress = boundary._current_records(wired.store, saved)[0].progress
    task = next(row for row in progress["rows"]
                if row.get("record_requirement") == date_requirement())
    assert task["status"] == "pending"
    assert task["record_requirement"] == date_requirement()
    operations = [row["operation"] for row in model.seen[before:]]
    assert operations.count("continue_conversation") == 1
    assert operations.count("verify_continuation") == 1


def test_actual_change_acknowledgement_uses_saved_exact_entries(client, wired, monkeypatch):
    message = "The northern carton arrival was 19 April, correcting the earlier account."
    lie = "I deleted the entire delivery account."
    change = record_plan(message, candidates=[revision(NEW_DATE, message, OLD_DATE, DATE_ID)])
    install(wired, monkeypatch, [initial_plan(), change],
            [{}, {"status": "performed", "prose": lie}])
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    delivered = send(client, message, "pure-performed", opened=baseline)
    assert delivered.status_code == 200
    result = delivered.json()
    saved, active = reopened(wired, result)
    assert active == [OLD_RIG, NEW_DATE]
    text = json.dumps(result["elements"])
    assert lie not in text and OLD_DATE in text and NEW_DATE in text
    assert OLD_DATE + " → " + NEW_DATE in result["continuation"]["units"][0]["blocks"][0]["text"]
    assert result["material_coverage"]["execution"]["persistence"] == "committed"
    assert saved.brain_chat[-1]["response"]["elements"] == result["elements"]


def test_current_state_acknowledgement_does_not_claim_prior_operation(client, wired, monkeypatch):
    message = "Keep the carton entry at its already recorded 17 April date."
    requirement = {**date_requirement(),
                   "success_condition": "The carton entry remains at 17 April."}
    lie = "I changed and saved the date again."
    install(wired, monkeypatch, [initial_plan(), record_plan(message, requirement=requirement)],
            [{}, {"status": "already_current", "prose": lie}])
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    result = send(client, message, "pure-current", opened=baseline).json()
    _, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG]
    execution = result["material_coverage"]["execution"]
    assert execution["record_changes"] == []
    assert execution["requests"][0]["acknowledgement_delivery"] == "code_only"
    text = result["continuation"]["units"][0]["blocks"][0]["text"]
    assert OLD_DATE in text and lie not in json.dumps(result["elements"])
    assert text.startswith("Current record entries:")


def test_substantive_mode_remains_under_independent_semantic_review(client, wired, monkeypatch):
    message = "Correct the carton record and explain the unresolved account distinction."
    prose = "I changed the carton date and saved it."
    install(wired, monkeypatch,
            [initial_plan(), record_plan(message, mode="substantive")],
            [{}, {"status": "unresolved", "prose": prose}])
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    result = send(client, message, "mixed-semantic-dependency", opened=baseline).json()
    _, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG]
    assert prose in json.dumps(result["elements"])
    execution = result["material_coverage"]["execution"]
    assert "acknowledgement_delivery" not in execution["requests"][0]
    assert execution["requests"][0]["fulfillment"] == "unfinished"


class FollowupModel(PassageModel):
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation != "continue_conversation" or not self.control.get("followup"):
            return result
        data = deepcopy(result.data)
        payload = json.loads(prompt.user)
        for unit in data["units"]:
            question = deepcopy(unit["blocks"][0])
            question.update(id="necessary-distinction", kind="question",
                            text="Which reported delivery account should this entry represent?")
            question["span_ids"] = [payload["latest_message_spans"][0]["id"]]
            unit["blocks"].append(question)
            unit["questions"] = [{"id": "account-distinction", "block_id": question["id"],
                                  "purpose": "Resolve the account identity required for this edit.",
                                  "target_ids": [], "existing_id": ""}]
            unit["sufficiency"] = {"status": "needs_input", "block_id": question["id"]}
        return replace(result, data=data)


def test_reviewed_substantive_followup_is_preserved_and_identified(client, wired, monkeypatch):
    message = "Correct this date, but my two delivery accounts may describe different events."
    install(wired, monkeypatch, [initial_plan(), record_plan(message)],
            [{}, {"status": "unresolved", "followup": True}], model_type=FollowupModel)
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    delivered = send(client, message, "necessary-followup", opened=baseline)
    assert delivered.status_code == 200
    result = delivered.json()
    _, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG]
    request = result["material_coverage"]["execution"]["requests"][0]
    assert request["acknowledgement_delivery"] == "substantive_followup"
    assert request["fulfillment"] == "unfinished"
    assert result["continuation"]["units"][0]["questions"]
    assert any(element["kind"] == "question" for element in result["elements"])


def test_pure_acknowledgement_cannot_release_before_confirmed_save(client, wired, monkeypatch):
    message = "The northern carton arrival was 19 April, correcting the earlier account."
    change = record_plan(message, candidates=[revision(NEW_DATE, message, OLD_DATE, DATE_ID)])
    install(wired, monkeypatch, [initial_plan(), change], [{}, {"status": "performed"}])
    baseline = send(client, ORIGINAL, BASE_TURN).json()

    def fail_commit(*args, **kwargs):
        raise OSError("Synthetic save failure")

    monkeypatch.setattr(wired.store, "commit", fail_commit)
    result = send(client, message, "unconfirmed-pure", opened=baseline)
    assert result.status_code == 503
    assert "elements" not in result.json()
    saved, active = reopened(wired, baseline)
    assert active == [OLD_DATE, OLD_RIG] and len(saved.brain_chat) == 1


def test_pure_acknowledgement_lost_ack_and_replay_do_not_repeat_effect(client, wired, monkeypatch):
    message = "The northern carton arrival was 19 April, correcting the earlier account."
    change = record_plan(message, candidates=[revision(NEW_DATE, message, OLD_DATE, DATE_ID)])
    model = install(wired, monkeypatch, [initial_plan(), change], [{}, {"status": "performed"}])
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    commit = wired.store.commit

    def lost_ack(matter, *, expected_version):
        commit(matter, expected_version=expected_version)
        raise OSError("Synthetic lost acknowledgement")

    monkeypatch.setattr(wired.store, "commit", lost_ack)
    first = send(client, message, "durable-pure", opened=baseline)
    before = len(model.seen)
    replay = send(client, message, "durable-pure", opened=baseline)
    assert first.status_code == replay.status_code == 200
    assert replay.json()["elements"] == first.json()["elements"]
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert len(model.seen) == before
    saved, active = reopened(wired, replay.json())
    assert active == [OLD_RIG, NEW_DATE] and len(saved.brain_chat) == 2


@pytest.mark.parametrize("field,value", [
    ("intent", "contribution"), ("next_step", "legal_work"),
    ("record_requirement", {"kind": "none", "operation": "none", "target_ids": [],
                            "success_condition": ""}),
])
def test_acknowledgement_mode_requires_compatible_typed_deliverable(field, value):
    from nm.brain import conversation
    from tests.test_brain_record_requirement import context, item, requirement, response

    row = item("Correct the sourced record.", record_requirement=requirement(
        "change", targets=("earlier:material:2",), operation="corrects", condition="Sourced edit."),
        purposes=("interpretation_review",))
    row.update(response_mode="record_acknowledgement")
    row[field] = value
    with pytest.raises(SchemaViolation, match="record_acknowledgement requires"):
        conversation._turn_plan(response(row), context())


class MultipleBlockModel(PassageModel):
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation != "continue_conversation" or not self.control.get("second_prose"):
            return result
        data = deepcopy(result.data)
        for unit in data["units"]:
            extra = deepcopy(unit["blocks"][0])
            extra.update(id="separate-account", kind="account", text=self.control["second_prose"])
            unit["blocks"].append(extra)
            unit["sufficiency"]["block_id"] = extra["id"]
        return replace(result, data=data)


def test_every_pure_block_is_canonical_without_changing_its_identity(client, wired, monkeypatch):
    message = "Correct the northern carton date using the attributed account."
    lies = ["I saved a new delivery date.", "I completed every outstanding record task."]
    model = install(wired, monkeypatch, [initial_plan(), record_plan(message)],
                    [{}, {"status": "unresolved", "prose": lies[0], "second_prose": lies[1]}],
                    model_type=MultipleBlockModel)
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    result = send(client, message, "multiple-pure-blocks", opened=baseline).json()
    _, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG]
    unit = result["continuation"]["units"][0]
    assert [block["id"] for block in unit["blocks"]] == ["block:0", "separate-account"]
    assert unit["sufficiency"]["block_id"] == "separate-account"
    assert unit["record_outcome"]["block_id"] == "block:0"
    assert all(lie not in json.dumps(result["elements"]) for lie in lies)
    assert all("remains unfinished" in block["text"] for block in unit["blocks"])
    assert model.seen


def test_completed_no_change_review_is_a_legitimate_code_acknowledgement(
        client, wired, monkeypatch):
    message = "Review the recorded delivery against my original account."
    requirement = {"kind": "review", "operation": "none", "target_ids": [DATE_ID],
                   "success_condition": "The delivery entry faithfully represents the account."}
    install(wired, monkeypatch, [initial_plan(), record_plan(message, requirement=requirement)],
            [{}, {"status": "review_no_change"}])
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    delivered = send(client, message, "pure-no-change-review", opened=baseline)
    assert delivered.status_code == 200
    result = delivered.json()
    _, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG] and result["blocked"] is False
    execution = result["material_coverage"]["execution"]
    assert execution["record_changes"] == []
    assert execution["requests"][0]["fulfillment"] == "no_change_justified"
    assert execution["requests"][0]["acknowledgement_delivery"] == "code_only"
    assert "review completed" in result["continuation"]["units"][0]["blocks"][0]["text"]


class ContentRejectingModel(PassageModel):
    """A scripted reviewer rejects the known fabricated unsupported prose."""
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation != "verify_continuation" or not self.control.get("reject_text"):
            return result
        payload = json.loads(prompt.user)
        data = deepcopy(result.data)
        units = {unit["request_index"]: unit for unit in payload["units"]}
        for verdict in data["verdicts"]:
            unit = units[verdict["request_index"]]
            if any(block["text"] == self.control["reject_text"] for block in unit["blocks"]):
                verdict.update(verdict="reject",
                               reason="This prose claims an unperformed operation.")
                for check in verdict["block_checks"]:
                    check.update(verdict="reject", reason=verdict["reason"])
        return replace(result, data=data)


def test_discarded_pure_prose_never_reaches_review_or_causes_retry(client, wired, monkeypatch):
    message = "Correct the northern carton record using the saved original account."
    lie = "I saved the correction and completed all record work."
    model = install(wired, monkeypatch, [initial_plan(), record_plan(message)],
                    [{}, {"status": "unresolved", "prose": lie, "reject_text": lie}],
                    model_type=ContentRejectingModel)
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    before = len(model.seen)
    delivered = send(client, message, "pure-prereview", opened=baseline)
    assert delivered.status_code == 200
    result = delivered.json()
    _, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG] and result["blocked"] is False
    assert lie not in json.dumps(result["elements"])
    calls = model.seen[before:]
    assert sum(row["operation"] == "continue_conversation" for row in calls) == 1
    assert sum(row["operation"] == "verify_continuation" for row in calls) == 1
    review = next(row["input"] for row in calls if row["operation"] == "verify_continuation")
    assert all(block["text"] != lie for unit in review["units"] for block in unit["blocks"])
    assert review["input"]["material_coverage"]["execution"]["requests"][0][
        "acknowledgement_delivery"] == "code_only"
    assert result["continuation"]["units"][0]["record_check"]["outcome"] == "unfinished"


def test_same_fault_in_substantive_prose_still_requires_semantic_rejection(
        client, wired, monkeypatch):
    message = "Correct the carton entry and explain the broader account distinction."
    lie = "I saved the correction and completed all record work."
    model = install(wired, monkeypatch,
                    [initial_plan(), record_plan(message, mode="substantive")],
                    [{}, {"status": "unresolved", "prose": lie, "reject_text": lie}],
                    model_type=ContentRejectingModel)
    baseline = send(client, ORIGINAL, BASE_TURN).json()
    before = len(model.seen)
    result = send(client, message, "substantive-prereview", opened=baseline).json()
    _, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG] and result["blocked"] is True
    assert lie not in json.dumps(result["elements"])
    assert sum(row["operation"] == "continue_conversation" for row in model.seen[before:]) == 2


def test_repeated_none_outcome_keeps_saved_input_and_truthful_unfinished_fallback(
        client, wired, monkeypatch):
    message = 'Correct the northern carton record to show 19 April.'
    lie = 'I changed and saved the carton date as requested.'
    model = install(wired, monkeypatch, [initial_plan(), record_plan(message)],
                    [{}, {'status': 'none', 'prose': lie}])
    opened = send(client, ORIGINAL, BASE_TURN).json()
    before = len(model.seen)
    delivered = send(client, message, 'pure-none-repeated', opened=opened)
    assert delivered.status_code == 200
    result = delivered.json()
    saved, active = reopened(wired, result)
    assert active == [OLD_DATE, OLD_RIG]
    assert saved.brain_chat[-1]['message'] == message
    assert result['continuation']['units'] == []
    assert result['continuation']['coverage'][0]['state'] == 'unavailable'
    assert lie not in json.dumps(result['elements'])
    assert any('remains unfinished' in row['text'] for row in result['elements'])
    assert result['material_coverage']['execution']['requests'][0][
        'acknowledgement_delivery'] == 'code_only'
    calls = [row['operation'] for row in model.seen[before:]]
    assert calls.count('continue_conversation') == 2
    assert calls.count('verify_continuation') == 0
