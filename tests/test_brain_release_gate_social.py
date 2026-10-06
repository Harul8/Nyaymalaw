"""Every public reply crosses composition and review without disturbing prior work."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

from nm.brain.dispute_state import proposed_disputes
from nm.brain.material_state import material_record
from nm.brain.work_state import project_work
from tests.brain_reader_fixture import reader_operations
from tests.test_brain_continuation_service import (
    PublicContinuationModel,
    opening_route,
    plan,
    send,
    unit,
)

FIRST = "I have a signed receipt for the disputed transaction. Please review it."
RECEIPT = "I have a signed receipt for the disputed transaction."
OPERATIONS = ["interpret_conversation", "continue_conversation", "verify_continuation"]


def reported_material(saved):
    return material_record(saved, disputes=proposed_disputes(saved))


class SeededModel(PublicContinuationModel):
    """The opening fixture saves actual attributed material alongside pending work."""

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation != "extract_legal_details":
            return result
        payload = json.loads(prompt.user)
        source_id = payload["latest_message_spans"][0]["id"]
        data = reader_operations([{
            "kind": "evidence", "statement": "The advocate reports holding a signed receipt.",
            "source_id": source_id, "matter_scope": "proposed",
            "basis": "described_record", "importance": "relevant",
            "why_material": "The reported receipt forms part of the requested review.",
            "placement": "matter", "dispute_ids": [], "related_material_ids": [],
        }], payload, link_field="related_material_ids")
        return replace(result, data=data)


def completed_reply(index, text, *, span_ids, kind="completion", create=False):
    proposed = unit(index, text=text, span_ids=span_ids)
    proposed["blocks"] = [proposed["blocks"][0]]
    proposed["blocks"][0].update(kind=kind, uncertainty="none" if kind == "completion"
                                  else "reported")
    proposed.update(questions=[], next_work=[], progress_updates=[],
                    work={"existing_id": "", "create": create},
                    sufficiency={"status": "complete", "block_id": f"account-{index}"})
    return proposed


def starting_state(client, wired, monkeypatch, route, reply, *, prefix):
    model = SeededModel([opening_route(FIRST), route],
                        [{"units": [unit()]}, reply])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, FIRST, f"{prefix}-open")
    saved = wired.store.load(opened["matter_id"])
    progress = project_work(saved)
    record = reported_material(saved)
    assert {row["kind"] for row in progress["rows"]} == {"task", "question"}
    assert all(row["status"] == "pending" for row in progress["rows"])
    assert record["state"] == "ok"
    assert len(record["rows"]) == 1 and record["rows"][0]["quoted"] == RECEIPT
    return model, opened, deepcopy(progress), deepcopy(record), len(model.calls)


def test_public_greeting_is_composed_and_reviewed_without_changing_pending_matter_work(
        client, wired, monkeypatch):
    greeting = "Hello again."
    routed = plan(greeting, scope="none", relation="aside", step="answer",
                  reply="UNREVIEWED_ROUTER_GREETING")
    routed["items"][0]["intent"] = "contribution"
    delivered = completed_reply(0, "Hello. We can continue when you are ready.",
                                span_ids=("L1",))
    model, opened, before_work, before_material, offset = starting_state(
        client, wired, monkeypatch, routed, {"units": [delivered]}, prefix="checked-greeting")

    answer = send(client, greeting, "checked-greeting-reply", opened=opened)

    assert answer["metrics"]["llm_calls"] == 3
    calls = model.calls[offset:]
    assert [operation for operation, _ in calls] == OPERATIONS
    assert [row["request_index"] for row in calls[1][1]["work_items"]] == [0]
    assert [row["request_index"] for row in calls[2][1]["units"]] == [0]
    assert [row["request_index"] for row in answer["continuation"]["units"]] == [0]
    assert [row["text"] for row in answer["elements"]] == [delivered["blocks"][0]["text"]]
    assert "UNREVIEWED_ROUTER_GREETING" not in json.dumps(answer["elements"])
    saved = wired.store.load(opened["matter_id"])
    assert project_work(saved) == before_work
    assert reported_material(saved) == before_material
    assert [row["message"] for row in saved.brain_chat] == [FIRST, greeting]
    assert saved.brain_chat[-1]["response"]["material"] == []


def test_public_mixed_greeting_and_account_summary_are_both_composed_and_reviewed_once(
        client, wired, monkeypatch):
    message = "Hello. Please summarize the reported account."
    routed = plan("Hello", scope="none", relation="aside", step="answer",
                  reply="UNREVIEWED_ROUTER_GREETING")
    routed["items"][0]["intent"] = "contribution"
    routed["items"].append({
        "request": "Summarize the reported account", "relation": "continues",
        "matter_scope": "current", "priority": "ordinary", "next_step": "legal_work",
        "reply": "UNREVIEWED_ROUTER_SUMMARY", "clarification": "", "intent": "request",
        "material_purposes": [],
        "record_requirement": {"kind": "none", "target_ids": [],
                               "operation": "none", "success_condition": ""}})
    greeting = completed_reply(0, "Hello.", span_ids=("L1",))
    summary = completed_reply(
        1, "You report holding a signed receipt for the disputed transaction; "
        "its contents have not been examined.",
        span_ids=("P1S1", "L2"), kind="account", create=True)
    summary["progress_updates"] = [{
        "target_id": "$work", "status": "complete", "block_id": "account-1",
        "reason": "The requested reported-account summary is delivered with its limit.",
        "span_ids": ["P1S1", "L2"],
    }]

    def compose(payload):
        assert [row["request_index"] for row in payload["work_items"]] == [0, 1]
        assert [row["next_step"] for row in payload["work_items"]] == ["answer", "legal_work"]
        return {"units": [greeting, summary]}

    model, opened, before_work, before_material, offset = starting_state(
        client, wired, monkeypatch, routed, compose, prefix="checked-mixed")

    answer = send(client, message, "checked-mixed-reply", opened=opened)

    assert answer["metrics"]["llm_calls"] == 3
    calls = model.calls[offset:]
    assert [operation for operation, _ in calls] == OPERATIONS
    assert [row["request_index"] for row in calls[1][1]["work_items"]] == [0, 1]
    assert [row["request_index"] for row in calls[2][1]["units"]] == [0, 1]
    assert [row["request_index"] for row in answer["continuation"]["units"]] == [0, 1]
    assert [row["text"] for row in answer["elements"]] == [
        greeting["blocks"][0]["text"], summary["blocks"][0]["text"]]
    assert "UNREVIEWED_ROUTER" not in json.dumps(answer["elements"])
    saved = wired.store.load(opened["matter_id"])
    after_work = project_work(saved)
    original_ids = {row["id"] for row in before_work["rows"]}
    assert [row for row in after_work["rows"] if row["id"] in original_ids] == before_work["rows"]
    assert after_work["active_work"] == before_work["active_work"]
    assert reported_material(saved) == before_material
    assert [row["message"] for row in saved.brain_chat] == [FIRST, message]
    assert saved.brain_chat[-1]["response"]["material"] == []
