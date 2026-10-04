"""Source-purpose correction names exact coverage gaps and remains atomic."""
import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.brain.record_review import classify_account_sources
from nm.brain.turn import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage
from tests.brain_reader_fixture import source_treatment_reply
from tests.test_brain_account_source_treatment import SourceModel, reply
from tests.test_brain_continuation import unit
from tests.test_brain_continuation_service import PublicContinuationModel, send
from tests.test_brain_turn import plan


def incomplete_catalogue(correct, fault):
    result = deepcopy(correct)
    rows = result["source_treatments"]
    if fault in ("missing", "missing_and_duplicate"):
        rows.pop()
        rows.pop(0)
    if fault in ("duplicate", "missing_and_duplicate"):
        rows.append(deepcopy(rows[0]))
    return result


def coverage_feedback(correction):
    return json.loads(correction["validation_issue"].split("coverage_mismatch=", 1)[1])


@pytest.mark.parametrize("fault", ["missing", "duplicate", "missing_and_duplicate"])
def test_source_correction_names_each_gap_and_preserves_the_complete_input(fault):
    earlier = (Message("prior", "advocate", "The receipt is unsigned. The date is disputed."),
               Message("answer", "nm", "The reported details remain uncertain."))
    payload, _, _ = addressed_sources(earlier, "Review the record. The original is unavailable.")
    roles = {"P1S1": "reported_matter_account", "P1S2": "reported_matter_account",
             "L1": "work_instruction", "L2": "uncertain"}
    correct = reply(roles)
    wrong = incomplete_catalogue(correct, fault)
    model = SourceModel([wrong, correct])

    result = classify_account_sources(model, payload=payload, latest_turn_id="current")

    assert len(model.calls) == 2 and set(result) == set(roles)
    correction = json.loads(model.calls[1][0].user)
    assert correction["original_input"] == json.loads(model.calls[0][0].user)
    assert correction["original_input"]["earlier_conversation"] == payload["earlier_conversation"]
    assert correction["rejected_output"] == wrong
    assert coverage_feedback(correction) == {
        "missing_source_ids": ["P1S1", "L2"] if fault != "duplicate" else [],
        "duplicate_source_ids": ["P1S2" if fault == "missing_and_duplicate" else "P1S1"]
        if fault != "missing" else [],
        "unexpected_source_ids": [],
    }
    assert result["L1"]["content_role"] == "work_instruction"
    assert result["L2"]["content_role"] == "uncertain"
    assert result["P1S1"]["turn_id"] == "prior"
    assert result["L2"]["quoted"] == "The original is unavailable."
    assert all(section in model.calls[1][0].system for section in (
        "Message:", "Purpose:", "Look for:", "Outcome:"))


def test_unexpected_source_id_keeps_the_closed_schema_and_exact_reference_feedback():
    payload, _, _ = addressed_sources((), "Review the record. The original is unavailable.")
    correct = reply({"L1": "work_instruction", "L2": "uncertain"})
    wrong = deepcopy(correct)
    wrong["source_treatments"][1]["source_id"] = "unowned-source"
    model = SourceModel([wrong, correct])

    result = classify_account_sources(model, payload=payload, latest_turn_id="current")

    assert set(result) == {"L1", "L2"} and len(model.calls) == 2
    schema = model.calls[0][1]["properties"]["source_treatments"]["items"]["properties"]
    assert schema["source_id"]["enum"] == ["L1", "L2"]
    issue = json.loads(model.calls[1][0].user)["validation_issue"]
    assert "source_treatments[1].source_id" in issue
    assert "unowned-source" in issue and "outside the permitted vocabulary" in issue


@pytest.mark.parametrize("fault", ["missing", "duplicate", "missing_and_duplicate"])
def test_source_coverage_failure_exhausts_only_the_existing_correction(fault):
    payload, _, _ = addressed_sources((), "One reported detail. A second detail. Review both.")
    correct = reply({"L1": "reported_matter_account", "L2": "reported_matter_account",
                     "L3": "work_instruction"})
    wrong = incomplete_catalogue(correct, fault)
    model = SourceModel([wrong, wrong])

    with pytest.raises(SchemaViolation, match="coverage_mismatch="):
        classify_account_sources(model, payload=payload, latest_turn_id="current")

    assert len(model.calls) == 2


class CoverageModel(PublicContinuationModel):
    def __init__(self, routes, continuations, *, fault, recover):
        super().__init__(routes, continuations)
        self.fault = fault
        self.recover = recover
        self.source_calls = 0

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation != "classify_account_sources":
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        self.schemas.append((prompt.operation, deepcopy(schema)))
        self.tiers.append(tier)
        original = payload.get("original_input", payload)
        correct = source_treatment_reply(prompt.operation, original)
        self.source_calls += 1
        data = (correct if self.recover and self.source_calls == 2 else
                incomplete_catalogue(correct, self.fault))
        return ModelResult(text=None, data=data, tier=tier, provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


@pytest.mark.parametrize("message", [
    "The inventory is unsigned. The receipt is dated. Review both records.",
    "The dispatch date is disputed. The shipment arrived later. Record these reported details.",
])
@pytest.mark.parametrize("fault", ["missing", "duplicate", "missing_and_duplicate"])
@pytest.mark.parametrize("recover", [False, True])
def test_public_source_coverage_recovers_atomically_or_stops_before_saving(
        client, wired, monkeypatch, message, fault, recover):
    route = plan(message, step="legal_work")
    route["material_review"] = True
    model = CoverageModel([plan("Hello."), route], [{"units": [unit()]}],
                          fault=fault, recover=recover)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, "Hello.", "coverage-before")
    matter_id = chat_matter_id("adv_demo", opened["chat_id"])
    original = deepcopy(wired.store.load(matter_id))

    response = client.post("/api/turn", json={
        "message": message, "turn_id": "coverage-current", "chat_id": opened["chat_id"],
    })

    assert model.source_calls == 2
    source_calls = [payload for operation, payload in model.calls
                    if operation == "classify_account_sources"]
    assert source_calls[1]["original_input"] == source_calls[0]
    assert coverage_feedback(source_calls[1]) == {
        "missing_source_ids": ["P1S1", "L3"] if fault != "duplicate" else [],
        "duplicate_source_ids": ["L1" if fault == "missing_and_duplicate" else "P1S1"]
        if fault != "missing" else [],
        "unexpected_source_ids": [],
    }
    saved = wired.store.load(matter_id)
    assert saved.brain_chat[0] == original.brain_chat[0]
    if not recover:
        assert response.status_code == 503
        assert saved == original
        assert [operation for operation, _ in model.calls[1:]] == [
            "interpret_conversation", "classify_account_sources", "classify_account_sources"]
        assert "coverage_mismatch" not in response.text
        return
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["metrics"]["llm_calls"] == 7
    assert [row["message"] for row in saved.brain_chat] == ["Hello.", message]
    catalogue = saved.brain_chat[-1]["response"]["material_coverage"]["source_treatments"]
    assert set(catalogue) == {"P1S1", "L1", "L2", "L3"}
    assert catalogue["P1S1"]["turn_id"] == "coverage-before"
    assert catalogue["L3"]["turn_id"] == "coverage-current"
    before_replay = len(model.calls)
    replay = send(client, message, "coverage-current", opened=opened)
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    assert len(model.calls) == before_replay
    assert wired.store.load(matter_id).brain_chat == saved.brain_chat
