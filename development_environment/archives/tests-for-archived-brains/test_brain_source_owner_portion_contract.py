"""Raw source-owner replies exercise exact portions and bounded corrections.

No source fixture transport runs here. These scenarios explicitly supply every
classification and endpoint; mechanically valid choices do not prove meaning.
"""
import json
from copy import deepcopy

import pytest

from nm.brain import record_review as owner
from nm.brain.conversation import Message
from nm.brain.material import addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema


class RawReplies:
    def __init__(self, replies, *, strict=False):
        self.replies = deepcopy(replies)
        self.strict = strict
        self.calls = []

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens):
        index = len(self.calls)
        assert index < len(self.replies), "An unbounded source-owner call was attempted"
        reply = deepcopy(self.replies[index])
        self.calls.append({"input": json.loads(prompt.user), "schema": deepcopy(schema),
                           "operation": prompt.operation, "tier": tier, "reply": reply})
        result = ModelResult(text=None, data=reply, tier=tier, provider="offline",
                             model="raw-source-owner", usage=Usage(0, 0, 0), latency_ms=0,
                             completion=Completion.COMPLETE)
        if self.strict:
            try:
                require_schema(reply, schema)
            except SchemaViolation as error:
                raise SchemaViolation(str(error), rejected_result=result) from error
        return result


def declared(role, portions):
    return {"source_treatments": {"L1": {
        "content_role": role, "reason": "The scenario independently declares original purpose.",
        "substantive_spans": deepcopy(portions),
    }}}


def read(operation, model, words, *, earlier=(), initial=None):
    payload, current, prior = addressed_sources(earlier, words)
    before = deepcopy(payload)
    if operation == "classify":
        result = owner.classify_account_sources(model, payload=payload, latest_turn_id="current")
        changed = None
    else:
        if initial is None:
            references = {identity: {"turn_id": reference.turn_id, "role": reference.role,
                                     "quoted": reference.quoted}
                          for identity, reference in prior.items() if reference.role == "advocate"}
            references.update({identity: {"turn_id": "current", "role": "advocate", "quoted": quote}
                               for identity, quote in current.items()})
            initial = {identity: {**reference, "content_role": "uncertain",
                                  "reason": "Explicit initial unresolved purpose.",
                                  "selection_contract": owner.SOURCE_SELECTION_CONTRACT,
                                  "substantive_spans": []}
                       for identity, reference in references.items()}
        original = deepcopy(initial)
        result, changed = owner.reconsider_account_sources(
            model, payload=payload, latest_turn_id="current",
            source_treatments=initial, source_ids=("L1",))
        assert initial == original
    assert payload == before
    return result, changed


@pytest.mark.parametrize("operation", ["classify", "reconsider"])
@pytest.mark.parametrize("role,words,portion", [
    ("mixed", "Review the receipt because I am uncertain whether the courier delivered it.",
     "I am uncertain whether the courier delivered it."),
    ("mixed", "Please examine the chronology although the clerk says the seal was not intact.",
     "the clerk says the seal was not intact."),
    ("reported_party_position", "The other party denies that its agent accepted the parcel.",
     "The other party denies that its agent accepted the parcel."),
    ("reported_matter_account", "I did not sign the register.", "I did not sign the register."),
])
def test_raw_good_portions_preserve_attribution_negation_uncertainty_and_full_source(
    operation, role, words, portion
):
    start = words.index(portion)
    selection = [{"start": start, "end": start + len(portion)}]
    reply = declared(role, selection)
    model = RawReplies([reply], strict=True)
    result, _ = read(operation, model, words)
    row = result["L1"]
    assert row["quoted"] == words and row["content_role"] == role
    assert row["substantive_spans"][0]["quoted"] == portion
    assert row["substantive_spans"][0]["start"] == start
    assert row["substantive_spans"][0]["end"] == start + len(portion)
    assert row["selection_contract"] == owner.SOURCE_SELECTION_CONTRACT
    assert owner.source_treatment_reference_valid(row, {("current", "advocate", words)})
    assert model.calls[0]["reply"] == reply and len(model.calls) == 1
    assert model.calls[0]["input"]["original_source_catalogue"]["L1"]["quoted"] == words


@pytest.mark.parametrize("operation", ["classify", "reconsider"])
def test_raw_portion_selection_keeps_whole_ordered_conversation_and_unselected_owner(operation):
    earlier = (Message("previous", "advocate", "I did not authorize disposal."),
               Message("previous-nm", "nm", "The distinction remains unresolved."))
    words = ("Review the account because I cannot confirm delivery "
             "unless the register identifies it.")
    portion = "I cannot confirm delivery unless the register identifies it."
    start = words.index(portion)
    reply = declared("mixed", [{"start": start, "end": len(words)}])
    if operation == "classify":
        reply["source_treatments"]["P1S1"] = {
            "content_role": "reported_matter_account", "reason": "Explicit earlier account.",
            "substantive_spans": [{"start": 0, "end": len(earlier[0].text)}],
        }
    model = RawReplies([reply], strict=True)
    result, _ = read(operation, model, words, earlier=earlier)
    sent = model.calls[0]["input"]
    assert [row["turn_id"] for row in sent["earlier_conversation"]] == [
        "previous", "previous-nm"]
    assert [row["source_spans"][0]["text"] for row in sent["earlier_conversation"]] == [
        earlier[0].text, earlier[1].text]
    assert sent["latest_message_spans"][0]["text"] == words
    assert result["L1"]["quoted"] == words
    assert result["L1"]["substantive_spans"][0]["quoted"] == portion
    assert result["P1S1"]["quoted"] == earlier[0].text
    if operation == "reconsider":
        assert result["P1S1"]["content_role"] == "uncertain"
        assert result["P1S1"]["substantive_spans"] == []
    assert len(model.calls) == 1


@pytest.mark.parametrize("operation", ["classify", "reconsider"])
@pytest.mark.parametrize("role", [
    "examination_material", "work_instruction", "nm_interpretation", "uncertain",
])
def test_raw_nonaccount_and_unresolved_choices_with_empty_portions_need_no_correction(
    operation, role
):
    words = "Please examine the supplied passage without adopting its assertions."
    model = RawReplies([declared(role, [])], strict=True)
    result, _ = read(operation, model, words)
    assert result["L1"]["content_role"] == role
    assert result["L1"]["substantive_spans"] == [] and len(model.calls) == 1


BAD_RANGES = [
    ("mixed", []),
    ("work_instruction", [{"start": 0, "end": 10}]),
    ("reported_matter_account", [{"start": True, "end": 10}]),
    ("reported_matter_account", [{"start": 0, "end": False}]),
    ("reported_matter_account", [{"start": -1, "end": 10}]),
    ("reported_matter_account", [{"start": 0, "end": 1000}]),
    ("reported_matter_account", [{"start": 10, "end": 10}]),
    ("reported_matter_account", [{"start": 10, "end": 5}]),
    ("reported_matter_account", [{"start": 0, "end": 10, "anchor_id": "model-owned"}]),
]


@pytest.mark.parametrize("operation", ["classify", "reconsider"])
@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("role,portions", BAD_RANGES)
def test_raw_bad_portions_get_one_original_evidence_correction(operation, strict, role, portions):
    words = "The witness did not identify the sender."
    bad = declared(role, portions)
    good = declared("reported_matter_account", [{"start": 0, "end": len(words)}])
    model = RawReplies([bad, good], strict=strict)
    result, _ = read(operation, model, words)
    assert len(model.calls) == 2
    assert model.calls[0]["reply"] == bad and model.calls[1]["reply"] == good
    correction = model.calls[1]["input"]
    assert correction["original_input"] == model.calls[0]["input"]
    assert correction["validation_issue"]
    assert result["L1"]["substantive_spans"][0]["quoted"] == words


@pytest.mark.parametrize("operation", ["classify", "reconsider"])
def test_repeated_raw_bad_portions_exhaust_one_correction_without_mutating_input(operation):
    words = "The witness did not identify the sender."
    bad = declared("reported_matter_account", [])
    model = RawReplies([bad, bad])
    with pytest.raises(SchemaViolation, match="role-consistent"):
        read(operation, model, words)
    assert len(model.calls) == 2 and all(call["reply"] == bad for call in model.calls)


def test_same_version_same_portions_and_new_reason_leave_reconsideration_dependencies_unchanged():
    words = "The witness did not identify the sender."
    reference = {"turn_id": "current", "role": "advocate", "quoted": words}
    selection = [{"start": 0, "end": len(words)}]
    initial = {"L1": {**reference, "content_role": "reported_matter_account",
                       "reason": "First explanation of original purpose.",
                       "selection_contract": owner.SOURCE_SELECTION_CONTRACT,
                       "substantive_spans": owner.owned_source_portions(reference, selection)}}
    model = RawReplies([declared("reported_matter_account", selection)], strict=True)
    result, changed = read("reconsider", model, words, initial=initial)
    assert changed == () and result["L1"]["reason"] != initial["L1"]["reason"]
    assert owner.source_dependency(result["L1"]) == owner.source_dependency(initial["L1"])
    assert len(model.calls) == 1
