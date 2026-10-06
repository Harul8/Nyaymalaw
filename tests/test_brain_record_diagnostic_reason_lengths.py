"""Offline diagnostic-length boundaries; no real model/API/browser calls."""

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.brain.record_review import classify_account_sources
from nm.shared.model_port import SchemaViolation
from tests.test_brain_account_source_treatment import SourceModel, reply
from tests.test_brain_dispute_verification import Model, _candidate, _verdict, verify_disputes

LONG_REASON = (
    "The advocate's original span reports the supplier's retention of tools in this matter. "
    "Its speaker and exact words establish source purpose without establishing legal merit. "
    "The selected prior reference belongs to that same original advocate account. "
    "The current review instruction authorises examination and does not add underlying facts. "
    "The target remains a formulation of that original supplier account, with its attribution "
    "preserved rather than replaced by legal analysis or an unrelated reported event. "
    "The independently selected source and target therefore support the declared same-account "
    "operation within the supplied ownership and restoration choices."
)
assert len(LONG_REASON) >= 600


def test_long_source_treatment_reason_is_accepted_on_first_call_with_exact_owned_reference():
    words = "The supplier retained tools."
    payload, _, _ = addressed_sources((), words)
    answer = reply({"L1": "reported_matter_account"})
    answer["source_treatments"]["L1"]["reason"] = LONG_REASON
    model = SourceModel([answer, answer])
    result = classify_account_sources(model, payload=payload, latest_turn_id="current")
    assert len(model.calls) == 1
    assert result["L1"]["reason"] == LONG_REASON
    assert result["L1"]["quoted"] == words
    assert result["L1"]["turn_id"] == "current"
    assert (
        "maxLength"
        not in model.calls[0][1]["properties"]["source_treatments"]["properties"]["L1"][
            "properties"
        ]["reason"]
    )


@pytest.mark.parametrize("reason", ["", "   "])
def test_blank_source_treatment_reason_is_rejected_after_exactly_one_correction(reason):
    payload, _, _ = addressed_sources((), "The supplier retained tools.")
    answer = reply({"L1": "reported_matter_account"})
    answer["source_treatments"]["L1"]["reason"] = reason
    model = SourceModel([answer, answer])
    with pytest.raises(SchemaViolation):
        classify_account_sources(model, payload=payload, latest_turn_id="current")
    assert len(model.calls) == 2


class ReasonModel(Model):
    def __init__(self, field, reason):
        super().__init__([{"verdicts": [_verdict("C1", accept=True)]}] * 2)
        self.field, self.reason = field, reason

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        data = deepcopy(result.data)
        row = data["verdicts"][0]
        if self.field == "account":
            row["account_check"]["reason"] = self.reason
        elif self.field == "source":
            row["account_check"]["source_checks"][0]["reason"] = self.reason
        else:
            row["target_checks"][0]["reason"] = self.reason
        return replace(result, data=data)


def independent_review(model):
    original = "The supplier retained tools."
    latest = "Review the original supplier account."
    earlier = (Message("old", "advocate", original),)
    candidate = replace(
        _candidate(latest, "Supplier retention of tools", relation="corrects", earlier=original),
        related_dispute_ids=("owned-target",),
    )
    target = {
        "id": "owned-target",
        "label": "Supplier retention of tools",
        "statement": "Whether the supplier's retention of tools is contested.",
        "quoted": original,
        "source_turn_id": "old",
        "basis": "stated",
        "prior_references": [],
    }
    result = verify_disputes(
        model, candidates=(candidate,), earlier=earlier, latest=latest, active_disputes=(target,)
    )
    return result, candidate


@pytest.mark.parametrize("field", ["account", "source", "target"])
def test_long_independent_account_source_target_reason_is_accepted_once(field):
    model = ReasonModel(field, LONG_REASON)
    result, candidate = independent_review(model)
    assert result == (candidate,)
    assert len(model.calls) == 1
    properties = model.calls[0][1]["properties"]["verdicts"]["items"]["properties"]
    reason = (
        properties["account_check"]["properties"]["reason"]
        if field == "account"
        else properties["account_check"]["properties"]["source_checks"]["items"]["properties"][
            "reason"
        ]
        if field == "source"
        else properties["target_checks"]["items"]["properties"]["reason"]
    )
    assert "maxLength" not in reason


@pytest.mark.parametrize("field", ["account", "source", "target"])
@pytest.mark.parametrize("reason", ["", "   "])
def test_blank_independent_account_source_target_reason_is_rejected_with_one_correction(
    field, reason
):
    model = ReasonModel(field, reason)
    with pytest.raises(SchemaViolation):
        independent_review(model)
    assert len(model.calls) == 2
