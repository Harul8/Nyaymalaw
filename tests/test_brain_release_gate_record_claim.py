"""Every released answer crosses independent review, even with a mistaken router scope."""
import json
from copy import deepcopy
from dataclasses import replace

from nm.brain.work_state import project_work
from tests.brain_continuation_fixture import citation_units, reviewed_verdicts
from tests.test_brain_continuation import verdict
from tests.test_brain_material import Model, material, plan, send


def response_unit(text, *, completed):
    return {
        "request_index": 0,
        "blocks": [{"id": "response", "kind": "completion" if completed else "limitation",
                    "text": text, "span_ids": ["L1"] if completed else [],
                    "record_ids": [], "legal_source_ids": [],
                    "uncertainty": "none"}],
        "questions": [], "next_work": [],
        "sufficiency": {"status": "complete" if completed else "not_completed",
                        "block_id": "response"},
        "work": {"existing_id": "", "create": True},
        "progress_updates": [{"target_id": "$work", "status": "complete",
                              "block_id": "response", "reason": "The request was completed.",
                              "span_ids": ["L1"]}] if completed else [],
    }


class ReleaseModel(Model):
    def __init__(self, plans, replies, checks):
        super().__init__(plans)
        self.replies = iter(replies)
        self.checks = iter(checks)
        self.seen = []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.seen.append((prompt.operation, deepcopy(payload)))
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if len(self.calls) > 1 and prompt.operation == "continue_conversation":
            scripted = next(self.replies)
            data = scripted(payload) if callable(scripted) else deepcopy(scripted)
            return replace(result, data=citation_units(payload, data))
        if len(self.calls) > 1 and prompt.operation == "verify_continuation":
            scripted = next(self.checks)
            data = scripted(payload) if callable(scripted) else deepcopy(scripted)
            return replace(result, data=reviewed_verdicts(payload, data))
        return result


def test_public_false_record_completion_is_reviewed_and_repaired_before_saving(
        client, wired, monkeypatch):
    account = "The records are held by an unidentified custodian."
    request = "Review the saved entry and correct any wording unsupported by my account."
    false_claim = "I have corrected the matter record and saved the updated entry."
    remaining_gap = ("The requested record revision remains unfinished; "
                     "the saved entry is unchanged.")
    stored_item = material("circumstance", account, account, placement="matter")
    opening = plan(account, candidates=[stored_item], opening=True,
                   material_purposes=("account_contribution",))
    opening["opening"].update(subject="Reported record custody", summary=account)
    mistaken_route = plan(request, items=[{
        "request": request, "relation": "continues", "matter_scope": "none",
        "priority": "ordinary", "next_step": "answer", "reply": false_claim,
        "clarification": "", "intent": "request",
        "record_requirement": {"kind": "none", "target_ids": [],
                               "operation": "none", "success_condition": ""}}])
    assert mistaken_route["items"][0]["material_purposes"] == []
    unsupported = response_unit(false_claim, completed=True)
    corrected = response_unit(remaining_gap, completed=False)

    def reject_unexecuted_change(payload):
        assert payload["units"][0]["blocks"][0]["text"] == false_claim
        records = payload["input"]["record_catalogue"]
        assert records["seed:material:1"]["record"]["source_turn_id"] == "seed"
        reason = "The selected current record has no change supporting this completion claim."
        data = reviewed_verdicts(payload, verdict(0, accept=False, reason=reason))
        row = data["verdicts"][0]
        row["block_checks"][0].update(verdict="reject", reason=reason)
        row["progress_checks"][0].update(result_supported=False, verdict="reject", reason=reason)
        return data

    def repair_response(payload):
        assert [item["request_index"] for item in payload["work_items"]] == [0]
        issues = payload["correction"]["validation_issues"]
        assert "no change supporting this completion claim" in issues[0]["issue"]
        return {"units": [corrected]}

    model = ReleaseModel([opening, mistaken_route],
                         [{"units": [unsupported]}, repair_response],
                         [reject_unexecuted_change, verdict(0)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first_response = send(client, account, "seed")
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    before = deepcopy(wired.store.load(first["matter_id"]).brain_chat)
    before_record = client.get(f"/api/matters/{first['matter_id']}").json()["material_record"]
    call_start = len(model.seen)

    response = send(client, request, "review-request", opened=first)

    assert response.status_code == 200, response.text
    answer = response.json()
    visible = "\n".join(row["text"] for row in answer["elements"])
    assert false_claim not in visible and remaining_gap in visible
    operations = [operation for operation, _ in model.seen[call_start:]]
    assert operations == ["interpret_conversation", "continue_conversation", "verify_continuation",
                          "continue_conversation", "verify_continuation"]
    assert answer["metrics"]["llm_calls"] == 5
    assert answer["material"] == []
    after_record = client.get(f"/api/matters/{first['matter_id']}").json()["material_record"]
    assert after_record == before_record
    saved = wired.store.load(first["matter_id"])
    assert saved.brain_chat[:-1] == before
    assert saved.brain_chat[-1]["message"] == request
    assert false_claim not in json.dumps(saved.brain_chat[-1]["elements"])
    unit = answer["continuation"]["units"][0]
    assert unit["sufficiency"]["status"] == "not_completed"
    assert unit["progress_updates"] == []
    assert next(row for row in project_work(saved)["rows"]
                if row["id"] == unit["work"]["progress_id"])["status"] == "pending"
    assert saved.facts == ()
    call_count = len(model.seen)
    replay = send(client, request, "review-request", opened=first).json()
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    assert len(model.seen) == call_count
