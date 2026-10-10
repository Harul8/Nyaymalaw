"""Mechanical sanity checks do not certify semantic label accuracy."""
import json

import pytest

from nm.brain.message_labels import label_message, validate_message_labels
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelResult, SchemaViolation, Tier, Usage


def part(text, *labels):
    return {"text": text, "labels": list(labels)}


class LabelModel:
    def __init__(self, *responses, budget=20000):
        self.responses = iter(responses)
        self.budget = budget
        self.calls = []

    def context_budget(self, tier):
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier))
        return ModelResult(text=None, data=next(self.responses), tier=tier,
                           provider="offline", model="offline", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def test_independent_call_only_receives_message_and_attributed_history():
    message = "Hello, please explain this."
    response = {"parts": [part("Hello,", "social"), part("please explain this.", "work_request")]}
    for history, position in [((), "first"), (({"role": "advocate", "turn_id": "t1",
                                              "text": "Original account."},), "follow_up")]:
        model = LabelModel(response)
        result = label_message(model, message, earlier_conversation=history)
        prompt, schema, tier = model.calls[0]
        assert len(model.calls) == 1 and tier is Tier.ROUTINE
        assert prompt.operation == "label_message"
        assert json.loads(prompt.user) == {"message_position": position,
                                          "latest_message": message,
                                          "earlier_conversation": list(history)}
        assert set(schema["properties"]) == {"parts"}
        assert [row["category"] for row in result] == ["social", "work_request"]


def test_repetition_multiple_labels_and_boundary_punctuation_are_not_false_rejections():
    message = "  Yes; yes! Please wait.  "
    result = validate_message_labels({"parts": [
        part("Yes", "social", "information", "social"),
        part("yes", "information"), part("Please wait", "work_request"),
    ]}, message)
    assert [row["category"] for row in result] == ["social", "information", "information", "work_request"]
    spans = [row["sources"][0] for row in result]
    assert all(row["text"] == message[row["start"]:row["end"]] for row in spans)
    assert spans[0]["start"] == 0 and spans[-1]["end"] == len(message)
    assert spans[2]["start"] > spans[0]["start"]
    # Canonical selections still satisfy the durable v1 replay contract.
    from nm.brain.conversation import checked_message_parts
    wire = [{"category": row["category"], "selections": [{"source_id": "$message",
             "start": row["sources"][0]["start"], "end": row["sources"][0]["end"]}]}
            for row in result]
    assert checked_message_parts(wire, message) == result


@pytest.mark.parametrize("message,parts", [
    ("It was not signed.", [part("It was signed.", "information")]),
    ("Hello. Explain this.", [part("Hello.", "social")]),
    ("Hello. Explain this.", [part("Explain this.", "work_request")]),
    ("Signed yesterday.", [part("Signed yesterday.", "proven")]),
    ("Hello.", [part(" ", "social")]),
    ("Hello. Explain this.", [part("Explain this.", "work_request"), part("Hello.", "social")]),
    ("Hello 👋", [part("Hello", "social")]),
])
def test_sanity_check_rejects_altered_missing_or_unowned_content(message, parts):
    with pytest.raises(SchemaViolation):
        validate_message_labels({"parts": parts}, message)


def test_valid_shape_does_not_claim_semantic_judgment_or_enforce_a_part_count():
    message = "Please explain the wording."
    for label in ("social", "information", "work_request"):
        assert validate_message_labels({"parts": [part(message, label)]}, message)


@pytest.mark.parametrize("original", ["Please  wait.", "Please\nwait."])
def test_copied_whitespace_layout_is_not_a_false_rejection(original):
    result = validate_message_labels({"parts": [part("Please wait.", "work_request")]}, original)
    assert result[0]["sources"] == [{"start": 0, "end": len(original), "text": original}]


def test_bad_original_words_receive_one_precise_correction_with_original_context():
    model = LabelModel({"parts": [part("Changed words", "information")]},
                       {"parts": [part("Original words", "information")]})
    assert label_message(model, "Original words")
    assert len(model.calls) == 2
    feedback = json.loads(model.calls[1][0].user)
    assert feedback["original_input"]["latest_message"] == "Original words"
    assert "parts[0].text" in feedback["validation_issue"]


def test_context_is_not_trimmed_to_fit():
    model = LabelModel(budget=1)
    with pytest.raises(ContextOverflow):
        label_message(model, "Original words")
    assert model.calls == []
