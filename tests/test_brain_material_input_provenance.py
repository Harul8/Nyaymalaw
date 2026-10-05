"""Material input handoff only; scripted output does not establish model quality."""
import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.material import extract_details
from tests.test_brain_material_specialist import Model, _source_text, candidate


@pytest.mark.parametrize(
    "basis,account,importance",
    [
        ("uncertain", "The carrier may have received three crates, but I cannot confirm the count.",
         "uncertain"),
        ("attributed", "The carrier says it received three crates, and I dispute that count.",
         "relevant"),
    ],
)
def test_interpretation_review_receives_saved_status_and_original_account_lineage(
        basis, account, importance):
    first_review = "Review your description against my original account."
    earlier = (
        Message("account", "advocate", account),
        Message("account", "nm", "The carrier received three crates."),
        Message("first-review", "advocate", first_review),
        Message("first-review", "nm", "I have retained your qualified account."),
    )
    original_reference = {"turn_id": "account", "role": "advocate", "quoted": account}
    reason = "The qualified count may affect assessment of the reported delivery."
    saved = {
        "id": "first-review:material:1", "source_turn_id": "first-review",
        "state": "proposed", "kind": "circumstance",
        "statement": "The carrier received three crates.", "quoted": first_review,
        "relation": "corrects", "matter_scope": "current", "placement": "matter",
        "dispute_ids": [], "related_material_ids": ["account:material:1"],
        "basis": basis, "importance": importance, "why_material": reason,
        "prior_references": [original_reference],
    }
    before = deepcopy(saved)
    latest = ("Reconcile the saved description with my original account "
              "and preserve its qualifications.")
    proposed = {
        **candidate(source_id="L1", relation="corrects", prior_source_ids=["P1S1"]),
        "statement": account, "basis": basis, "importance": importance,
        "why_material": reason, "placement": "matter",
        "related_material_ids": [saved["id"]],
    }
    model = Model({"details": [proposed]})

    rows = extract_details(model, earlier=earlier, latest=latest,
                           current_matter_id="matter-1", prior_material=(saved,))

    assert len(model.calls) == 1
    payload = json.loads(model.calls[0][0].user)
    supplied = payload["active_material"][0]
    assert supplied["record_role"] == "nm_interpretation"
    assert supplied["basis"] == basis
    assert supplied["importance"] == importance
    assert supplied["why_material"] == reason
    assert supplied["prior_references"] == [original_reference]
    # This record's direct source is review authority; its original account
    # remains explicitly attributed rather than being replaced by that request.
    assert supplied["quoted"] == first_review
    assert supplied["source_ids"] == ["P3S1"]
    assert [(entry["turn_id"], entry["role"], _source_text(entry["source_spans"]))
            for entry in payload["earlier_conversation"]] == [
                (message.turn_id, message.role, message.text) for message in earlier]
    assert _source_text(payload["latest_message_spans"]) == latest
    assert saved == before
    assert rows[0].basis == basis and rows[0].importance == importance
    assert rows[0].statement == account and rows[0].quoted == latest
    assert rows[0].related_material_ids == (saved["id"],)
    assert [vars(reference) for reference in rows[0].prior_references] == [
        original_reference,
        {"turn_id": "first-review", "role": "advocate", "quoted": first_review},
    ]
