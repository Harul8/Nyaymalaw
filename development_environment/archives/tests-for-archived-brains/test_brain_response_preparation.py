"""Exercise preparation contracts; scripted outputs do not prove model semantics."""
from copy import deepcopy
import json

import pytest

from nm.brain.message_labels import label_message
from nm.brain.response_preparation import prepare_response
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage,
)


class PreparationModel:
    def __init__(self, *outputs, budget=30000, completion=Completion.COMPLETE):
        self.outputs = iter(outputs)
        self.budget = budget
        self.completion = completion
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        return ModelResult(
            text=None, data=deepcopy(next(self.outputs)), tier=tier,
            provider="offline", model="offline", usage=Usage(10, 5, 0),
            latency_ms=7, completion=self.completion,
        )


def material(text="The advocate reports receiving a draft.", sources=None):
    return {"understanding": text,
            "source_ids": ["current"] if sources is None else sources}


def action(sources=None, **changes):
    value = {
        "requested_outcome": "Explain the supplied wording.",
        "source_ids": ["current"] if sources is None else sources,
        "constraints": ["Do not send anything."],
        "activities": ["Read the supplied wording.", "Explain its meaning."],
        "missing_information": [],
    }
    return {**value, **changes}


def output(*, reply="Hello. How can I help?", materials=None, actions=None):
    return {"reply_draft": reply, "material": materials or [], "actions": actions or []}


def prepare(model, message="Hello.", label="greeting", history=None, **kwargs):
    return prepare_response(model, message, label=label,
                            history=[] if history is None else history,
                            history_complete=kwargs.pop("history_complete", True), **kwargs)


def test_first_message_has_one_focused_call_and_an_unreviewed_result():
    message = "  Good evening.  "
    model = PreparationModel(output())
    result = prepare(model, message)
    assert len(model.calls) == 1
    prompt, schema, tier, max_tokens = model.calls[0]
    assert prompt.operation == "prepare_response" and tier is Tier.ROUTINE
    assert isinstance(max_tokens, int) and max_tokens > 0
    payload = json.loads(prompt.user)
    assert payload["current_message"] == {
        "id": "current", "message": {"role": "advocate", "text": message},
    }
    assert payload["label"] == "greeting"
    assert "earlier_conversation" not in payload
    assert set(schema["properties"]) == {"reply_draft", "material", "actions"}
    assert result == {
        "state": "prepared_unreviewed", "proposal": output(),
        "sources": [payload["current_message"]], "issues": [],
    }


def test_follow_up_keeps_every_original_entry_and_uses_a_different_prompt():
    history = [
        {"id": "original-a", "role": "advocate", "turn_id": "t1", "text": "I have only a draft.\nNot signed.",
         "metadata": {"attachment": "reported"}},
        {"role": "nm", "turn_id": "t1", "text": "Shall I explain its terms?"},
        {"role": "advocate", "turn_id": "t2", "text": "Please keep the draft private."},
        {"role": "nm", "turn_id": "t2", "text": "Which part should I examine?"},
    ]
    original = deepcopy(history)
    model = PreparationModel(output(actions=[action()]), output())
    result = prepare(model, "The payment wording, please.", "action", history)
    prepare(model)
    follow, first = (call[0] for call in model.calls)
    assert follow.system != first.system
    payload = json.loads(follow.user)
    expected_history = [{"message": row, "id": f"history_{index}"}
                        for index, row in enumerate(history, 1)]
    assert payload["earlier_conversation"] == expected_history
    assert len(result["sources"]) == len(history) + 1
    assert {row["id"]: row for row in result["sources"]} == {
        **{row["id"]: row for row in expected_history},
        "current": payload["current_message"],
    }
    assert history == original


def test_material_and_actions_are_proposals_with_code_owned_ids():
    response = output(reply="I understand you received a draft and want an explanation.",
                      materials=[material()], actions=[action()])
    original = deepcopy(response)
    result = prepare(PreparationModel(response), "I received a draft. Explain it.", "mixed")
    assert result["state"] == "prepared_unreviewed" and result["issues"] == []
    assert result["proposal"]["material"] == [{**material(), "id": "material:1", "state": "proposed"}]
    assert result["proposal"]["actions"] == [{**action(), "id": "action:1", "state": "planned"}]
    assert response == original


def test_advisory_label_does_not_suppress_supported_material_or_actions():
    response = output(materials=[material()], actions=[action()])
    result = prepare(PreparationModel(response), "I received a draft. Explain it.", "greeting")
    assert len(result["proposal"]["material"]) == 1
    assert len(result["proposal"]["actions"]) == 1
    assert result["issues"] == []


def test_invalid_independent_units_are_held_without_losing_valid_peers():
    response = output(materials=[material(sources=["absent"]), material()],
                      actions=[action(activities=["   "]), action()])
    model = PreparationModel(response)
    result = prepare(model, "I received a draft. Explain it.", "mixed")
    assert [row["id"] for row in result["proposal"]["material"]] == ["material:2"]
    assert [row["id"] for row in result["proposal"]["actions"]] == ["action:2"]
    assert {issue["unit"] for issue in result["issues"]} == {"material:1", "action:1"}
    assert all(issue["reason"].strip() for issue in result["issues"])
    assert {issue["unit"]: issue["rejected_proposal"] for issue in result["issues"]} == {
        "material:1": response["material"][0], "action:1": response["actions"][0],
    }
    assert len(model.calls) == 1


def test_nm_words_alone_cannot_substantiate_material_or_a_request():
    history = [{"role": "nm", "text": "You signed the document."}]
    response = output(materials=[material(sources=["history_1"])],
                      actions=[action(sources=["history_1"])])
    result = prepare(PreparationModel(response), "That may not be right.", "information", history)
    assert result["proposal"]["material"] == [] and result["proposal"]["actions"] == []
    assert {issue["unit"] for issue in result["issues"]} == {"material:1", "action:1"}


def test_nm_context_may_accompany_an_advocates_original_source():
    history = [{"role": "advocate", "text": "The document is unsigned."},
               {"role": "nm", "text": "Would you like me to explain it?"}]
    response = output(materials=[material("The document is reported unsigned.", ["history_1", "history_2"])],
                      actions=[action(sources=["current", "history_2"])])
    result = prepare(PreparationModel(response), "Yes, explain it.", "action", history)
    assert len(result["proposal"]["material"]) == len(result["proposal"]["actions"]) == 1
    assert result["issues"] == []


def test_historical_request_needs_current_message_link_before_becoming_an_action():
    history = [{"role": "advocate", "text": "Explain the draft."}]
    response = output(actions=[action(sources=["history_1"]),
                               action(sources=["current", "history_1"])])
    result = prepare(PreparationModel(response), "Please continue.", "action", history)
    assert [row["id"] for row in result["proposal"]["actions"]] == ["action:2"]
    assert [issue["unit"] for issue in result["issues"]] == ["action:1"]


def test_blank_material_is_held_and_does_not_erase_the_next_item():
    response = output(materials=[material(" \n "), material()])
    result = prepare(PreparationModel(response), "I received a draft.", "information")
    assert [row["id"] for row in result["proposal"]["material"]] == ["material:2"]
    assert [issue["unit"] for issue in result["issues"]] == ["material:1"]


def test_empty_optional_metadata_does_not_block_a_valid_action():
    response = output(actions=[action(constraints=["", "  ", "Do not send anything."],
                                      missing_information=["", "\n"])])
    result = prepare(PreparationModel(response), "Explain it without sending it.", "action")
    assert result["issues"] == []
    planned = result["proposal"]["actions"][0]
    assert planned["constraints"] == ["Do not send anything."]
    assert planned["missing_information"] == []


@pytest.mark.parametrize("invalid", [material(""), material(sources=[]), {}])
def test_invalid_unit_shape_is_held_without_discarding_a_valid_peer(invalid):
    result = prepare(PreparationModel(output(materials=[invalid, material()])),
                     "I received a draft.", "information")
    assert [row["id"] for row in result["proposal"]["material"]] == ["material:2"]
    assert result["issues"][0]["rejected_proposal"] == invalid


def test_completed_provider_rejection_still_requires_each_unit_check():
    class QuarantinedModel(PreparationModel):
        def structured(self, *args, **kwargs):
            receipt = super().structured(*args, **kwargs)
            raise SchemaViolation("Completed object has a malformed unit", rejected_result=receipt)

    model = QuarantinedModel(output(materials=[material(""), material()],
                                    actions=[action(activities=[]), action()]))
    result = prepare(model, "I received a draft. Explain it.", "mixed")
    assert result["state"] == "prepared_unreviewed"
    assert [row["id"] for row in result["proposal"]["material"]] == ["material:2"]
    assert [row["id"] for row in result["proposal"]["actions"]] == ["action:2"]
    assert {issue["unit"] for issue in result["issues"]} == {"material:1", "action:1"}
    assert len(model.calls) == 1


@pytest.mark.parametrize("response", [
    {"reply_draft": "Hello", "material": []},
    {**output(), "public_ready": True},
    {**output(), "state": "completed"},
    {**output(), "actions": "I will do it"},
])
def test_bad_envelope_is_typed_failure_without_internal_retry(response):
    model = PreparationModel(response)
    with pytest.raises(SchemaViolation) as caught:
        prepare(model)
    assert len(model.calls) == 1
    assert caught.value.usage == Usage(10, 5, 0) and caught.value.latency_ms == 7


def test_incomplete_provider_output_is_not_salvaged_or_retried():
    model = PreparationModel(output(materials=[material()]), completion=Completion.NOT_ESTABLISHED)
    with pytest.raises(ModelError) as caught:
        prepare(model, "I received a draft.", "information")
    assert len(model.calls) == 1
    assert caught.value.usage == Usage(10, 5, 0)


@pytest.mark.parametrize("kwargs,error", [
    ({"message": "  "}, ValueError),
    ({"label": "verified"}, SchemaViolation),
    ({"history_complete": False}, ValueError),
    ({"history": [{"role": "unknown", "text": "Something"}]}, ValueError),
    ({"history": [{"role": "advocate", "text": ""}]}, ValueError),
])
def test_invalid_context_is_rejected_before_dispatch(kwargs, error):
    model = PreparationModel()
    with pytest.raises(error):
        prepare(model, **kwargs)
    assert model.calls == []


def test_context_overflow_preserves_history_and_makes_no_call():
    history = [{"role": "advocate", "text": "Original account. " * 300}]
    original = deepcopy(history)
    model = PreparationModel(budget=1)
    with pytest.raises(ContextOverflow):
        prepare(model, history=history)
    assert history == original and model.calls == []


@pytest.mark.parametrize("message,label,response", [
    ("Good evening.", "greeting", output()),
    ("I received a draft.", "information", output(materials=[material()])),
    ("Explain the supplied wording.", "action", output(actions=[action()])),
    ("Hello. I received a draft; explain it.", "mixed", output(materials=[material()], actions=[action()])),
])
def test_two_stage_handoff_uses_two_calls_without_execution(message, label, response):
    model = PreparationModel({"label": label}, response)
    classified = label_message(model, message, history=[], history_complete=True)
    prepared = prepare_response(model, message, label=classified["label"],
                                history=[], history_complete=True)
    assert [call[0].operation for call in model.calls] == ["label_message", "prepare_response"]
    assert all(call[2] is Tier.ROUTINE for call in model.calls)
    assert prepared["state"] == "prepared_unreviewed"
    assert prepared["proposal"]["reply_draft"] == response["reply_draft"]
    assert len(prepared["proposal"]["material"]) == len(response["material"])
    assert len(prepared["proposal"]["actions"]) == len(response["actions"])
    assert prepared["issues"] == []
