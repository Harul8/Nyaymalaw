"""Single assignment proposals still need independent semantic acceptance."""
import json
from dataclasses import replace

import pytest

from nm.brain.material import extract_details
from nm.shared.model_port import SchemaViolation
from tests.test_brain_material import Model as ServiceModel
from tests.test_brain_material import material, plan, send
from tests.test_brain_material_specialist import Model, candidate


@pytest.mark.parametrize("targets", [["foreign"], ["matter:other", "matter:discussion"],
                                    ["issue", "matter:uncertain"]])
def test_unknown_or_mixed_assignment_is_refused_after_existing_bounded_correction(targets):
    issue = dict(id="issue", label="Contested payment", statement="Payment is contested.",
                 quoted="Payment is contested.", source_turn_id="first")
    row = {**candidate(source_id="L1", scope="proposed"), "assignment_ids": targets}
    model = Model({"details": [row]})
    with pytest.raises(SchemaViolation):
        extract_details(model, earlier=(), latest="Payment is contested.",
                        current_matter_id=None, disputes=(issue,))
    assert len(model.calls) == 2


def test_public_mixed_correction_and_diversion_preserve_peers_when_assignment_is_semantically_wrong(
        client, wired, monkeypatch):
    first = "Delivery was delayed. Payment was twenty units."
    initial = [material("dispute", "Delivery delay", "Delivery was delayed."),
               material("dispute", "Contested payment", "Payment was twenty units."),
               material("circumstance", "Payment was twenty units.", "Payment was twenty units.",
                        dispute_ids=("assignment-first:material:2",))]
    latest = "Correction: payment was ten units. A receipt is available. Hello."
    changed = material("circumstance", "Payment was ten units.",
                       "Correction: payment was ten units.", relation="corrects", scope="current",
                       dispute_ids=("assignment-first:material:1",),
                       related_material_ids=("assignment-first:material:3",), references=({
                           "turn_id": "assignment-first", "role": "advocate",
                           "quoted": "Payment was twenty units."},))
    receipt = material("evidence", "A receipt is reported.", "A receipt is available.",
                       scope="current", basis="described_record",
                       dispute_ids=("assignment-first:material:2",))

    class Reviewing(ServiceModel):
        def __init__(self, plans):
            super().__init__(plans)
            self.grounding_inputs = []

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "verify_material_grounding":
                self.grounding_inputs.append(json.loads(prompt.user))
                if len(self.grounding_inputs) == 2:
                    result = replace(result, data={"verdicts": [
                        {**row, "verdict": "reject", "reason": (
                            "The payment correction does not bear on the delivery dispute.")}
                        if row["candidate_id"] == "D2" else row
                        for row in result.data["verdicts"]]})
            return result

    model = Reviewing([plan(first, candidates=initial, opening=True),
                       plan(latest, candidates=[changed, receipt], items=[
                           {"request": "Update the reported amount and receipt",
                            "relation": "changes", "matter_scope": "current",
                            "intent": "contribution",
                            "priority": "ordinary", "next_step": "legal_work",
                            "reply": "I will review the corrected account.", "clarification": ""},
                           {"request": "Hello", "relation": "aside", "matter_scope": "none",
                            "priority": "ordinary", "next_step": "answer",
                            "reply": "Hello.", "clarification": ""}])])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, first, "assignment-first")
    assert opened.status_code == 200, opened.text
    result = send(client, latest, "assignment-second", opened=opened.json())
    assert result.status_code == 200, result.text
    response = result.json()
    assert len(response["material"]) == 1
    assert response["material"][0]["statement"] == "A receipt is reported."
    assert response["material_coverage"]["state"] == "partial"
    assert response["material_coverage"]["withheld_details"] == 1
    reviewed = model.grounding_inputs[1]
    linked = {row["id"]: row for row in reviewed["linked_records"]}
    assert linked["assignment-first:material:1"]["record"]["quoted"] == "Delivery was delayed."
    assert linked["assignment-first:material:3"]["record"]["quoted"] == "Payment was twenty units."
    record = client.get(f"/api/matters/{response['matter_id']}").json()["material_record"]
    assert "assignment-first:material:3" in {row["id"] for row in record["rows"]}
    saved = wired.store.load(response["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [first, latest]
    assert sum(call.operation == "extract_legal_details" for call in model.material_calls) == 2
    assert len(model.grounding_inputs) == 2
    assert response["metrics"]["llm_calls"] == 7
