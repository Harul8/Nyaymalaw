"""Offline contract checks for the new, standalone message labeller.

These supplied outputs exercise shape and call admission, not model accuracy.
"""

import json
from copy import deepcopy

import pytest

from nm.brain.message_labels import label_message, validate_label
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow,
    ModelError,
    ModelResult,
    Tier,
    Usage,
    estimate_tokens,
)


class RecordingModel:
    def __init__(self, data, *, completion=Completion.COMPLETE, budget=100_000):
        self.data = data
        self.completion = completion
        self.budget = budget
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        return ModelResult(
            text=None,
            data=deepcopy(self.data),
            tier=tier,
            provider="offline",
            model="supplied-output",
            usage=Usage(tokens_in=10, tokens_out=5, cost_usd=0),
            latency_ms=1,
            completion=self.completion,
        )


def test_first_position_and_one_routine_call_with_only_label_output():
    message = "Good morning. Please compare these terms."
    model = RecordingModel({"label": "mixed"})

    result = label_message(model, message, history=[], history_complete=True)

    assert result == {"message_position": "first", "label": "mixed"}
    assert len(model.calls) == 1
    prompt, schema, tier, max_tokens = model.calls[0]
    payload = json.loads(prompt.user)
    assert payload == {"latest_message": message}
    assert tier is Tier.ROUTINE
    assert max_tokens == 128
    assert set(schema["properties"]) == {"label"}


def test_follow_up_position_and_complete_unmodified_attributed_history():
    history = [
        {"role": "advocate", "text": "Keep this as a draft.", "turn_id": "a-1"},
        {"role": "nm", "text": "Which version should I compare?", "turn_id": "n-1"},
        {"role": "advocate", "text": "The one received yesterday."},
        {"role": "nm", "text": "Should the comparison cover the whole draft?"},
    ]
    saved = deepcopy(history)
    model = RecordingModel({"label": "action"})

    result = label_message(model, "Yes, the whole draft.", history=history, history_complete=True)

    assert result == {"message_position": "follow_up", "label": "action"}
    payload = json.loads(model.calls[0][0].user)
    assert payload == {
        "latest_message": "Yes, the whole draft.",
        "earlier_conversation": saved,
    }
    assert history == saved
    assert len(model.calls) == 1


def test_code_selects_distinct_first_and_follow_up_prompts():
    model = RecordingModel({"label": "information"})
    label_message(model, "The parcel arrived.", history=[], history_complete=True)
    label_message(model, "The parcel arrived.", history=[
        {"role": "advocate", "text": "I am waiting for a parcel."},
    ], history_complete=True)
    first, follow_up = [call[0] for call in model.calls]
    assert first.system != follow_up.system
    assert json.loads(first.user) == {"latest_message": "The parcel arrived."}
    assert "message_position" not in json.loads(follow_up.user)


@pytest.mark.parametrize("label", ["greeting", "information", "action", "mixed"])
def test_each_permitted_whole_message_label_is_admitted(label):
    assert validate_label({"label": label}) == label


def test_harmless_label_whitespace_and_case_are_normalized_without_mutating_draft():
    draft = {"label": " \n MiXeD\t"}
    original = deepcopy(draft)
    assert validate_label(draft) == "mixed"
    assert draft == original


@pytest.mark.parametrize("data", [
    {"label": "request"},
    {"label": ""},
    {"label": ["greeting", "information"]},
    {"label": "action", "message_position": "follow_up"},
    {"parts": [{"text": "Hello", "labels": ["greeting"]}]},
    {},
])
def test_unknown_labels_and_nonexclusive_or_extra_output_fields_are_rejected(data):
    with pytest.raises((ModelError, ValueError)):
        validate_label(data)


def test_validator_does_not_claim_to_judge_semantic_label_accuracy():
    # Deliberately wrong meaning, but an allowed shape.
    # This establishes the scope of the mechanical checker, not an endorsement.
    model = RecordingModel({"label": "greeting"})
    result = label_message(model, "The parcel arrived.", history=[], history_complete=True)
    assert result["label"] == "greeting"


@pytest.mark.parametrize("message,history,complete", [
    ("   ", [], True),
    ("Hello", [], False),
    ("Hello", [{"role": "unknown", "text": "Prior words"}], True),
    ("Hello", [{"role": "advocate", "text": "  "}], True),
    ("Hello", [{"role": "advocate"}], True),
])
def test_invalid_context_is_rejected_before_model_dispatch(message, history, complete):
    model = RecordingModel({"label": "greeting"})
    with pytest.raises((ModelError, ValueError)):
        label_message(model, message, history=history, history_complete=complete)
    assert model.calls == []


def test_context_overflow_is_rejected_before_dispatch_instead_of_trimming():
    model = RecordingModel({"label": "greeting"}, budget=1)
    with pytest.raises(ContextOverflow):
        label_message(model, "Hello", history=[], history_complete=True)
    assert model.calls == []


@pytest.mark.parametrize("completion", [
    Completion.LENGTH_LIMITED,
    Completion.FILTERED,
    Completion.NOT_ESTABLISHED,
])
def test_noncomplete_provider_result_is_not_admitted_or_retried(completion):
    model = RecordingModel({"label": "greeting"}, completion=completion)
    with pytest.raises(ModelError) as failure:
        label_message(model, "Hello", history=[], history_complete=True)
    assert len(model.calls) == 1
    assert failure.value.usage == Usage(tokens_in=10, tokens_out=5, cost_usd=0)
    assert failure.value.latency_ms == 1


def test_invalid_model_output_does_not_start_a_private_retry_loop():
    model = RecordingModel({"label": "unknown"})
    with pytest.raises(ModelError) as failure:
        label_message(model, "Actual words", history=[], history_complete=True)
    assert len(model.calls) == 1
    assert failure.value.usage == Usage(tokens_in=10, tokens_out=5, cost_usd=0)
    assert failure.value.latency_ms == 1


def test_context_budget_reserves_space_for_the_output_schema_too():
    model = RecordingModel({"label": "greeting"})
    label_message(model, "Hello", history=[], history_complete=True)
    prompt, _, _, output_limit = model.calls[0]
    model.budget = estimate_tokens(prompt.system + prompt.user) + output_limit
    model.calls.clear()
    with pytest.raises(ContextOverflow):
        label_message(model, "Hello", history=[], history_complete=True)
    assert model.calls == []
