"""Focused extraction contracts; scripted outputs do not establish model semantics."""
from copy import deepcopy
import json

import pytest

from nm.brain.disputes_objectives import extract_disputes_objectives, extraction_units
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelResult, SchemaViolation, Tier, Usage,
)


class ExtractionModel:
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


def passage(quote="The supplier refuses delivery.", source="current", purpose="support"):
    return {"source_id": source, "quote": quote, "purpose": purpose}


def item(description="Supplier's refusal to deliver", passages=None, uncertainty=None):
    return {"description": description,
            "passages": [passage()] if passages is None else passages,
            "uncertainty": uncertainty}


def output(*, disputes=None, objectives=None):
    return {"disputes": disputes or [], "objectives": objectives or []}


def extract(model, message="The supplier refuses delivery.", label="information", history=None,
            **kwargs):
    return extract_disputes_objectives(
        model, message, label=label, history=[] if history is None else history,
        history_complete=kwargs.pop("history_complete", True), **kwargs)


def extracted():
    return extract(ExtractionModel(output(disputes=[item()])))


def test_first_input_makes_one_call_and_returns_only_private_extraction():
    message = "  Good evening.  "
    model = ExtractionModel(output())
    prepared = extract(model, message, "greeting")
    assert len(model.calls) == 1
    prompt, schema, tier, maximum = model.calls[0]
    assert prompt.operation == "extract_disputes_objectives"
    assert tier is Tier.ROUTINE and maximum > 0
    assert set(schema["properties"]) == {"disputes", "objectives"}
    for kind in ("disputes", "objectives"):
        item_schema = schema["properties"][kind]["items"]["properties"]
        passage_schema = item_schema["passages"]["items"]["properties"]
        assert passage_schema["source_id"]["enum"] == ["current"]
        assert "enum" not in item_schema["description"]
        assert "enum" not in passage_schema["quote"]
    for section in ("Message:", "Purpose:", "Look for:", "Outcome:"):
        assert section in prompt.system
    payload = json.loads(prompt.user)
    assert payload["current_message"] == {
        "id": "current", "message": {"role": "advocate", "text": message}}
    assert payload["proposed_label"] == "greeting"
    assert "earlier_conversation" not in payload
    assert prepared == {
        "contract": "disputes_objectives_v1", "state": "prepared_unreviewed",
        "proposal": output(), "sources": [payload["current_message"]], "issues": []}
    assert extraction_units(prepared) == {}


def test_followup_preserves_complete_attributed_history_and_has_its_own_header():
    history = [
        {"role": "advocate", "text": "The property is held jointly.\nI am not sure of the shares.",
         "turn_id": "old-1", "metadata": {"record": "reported"}},
        {"role": "nm", "text": "Message received.", "turn_id": "old-1"},
        {"role": "advocate", "text": "I only want access restored.", "turn_id": "old-2"},
        {"role": "nm", "text": "Message received.", "turn_id": "old-2"},
    ]
    original = deepcopy(history)
    model = ExtractionModel(output(), output())
    result = extract(model, "Thanks.", "greeting", history)
    extract(model, "Thanks.", "greeting")
    followup, first = [call[0] for call in model.calls]
    assert followup.system != first.system
    earlier = [{"id": f"history_{index}", "message": entry}
               for index, entry in enumerate(history, 1)]
    payload = json.loads(followup.user)
    assert payload["earlier_conversation"] == earlier
    assert result["sources"] == [*earlier, payload["current_message"]]
    assert history == original


@pytest.mark.parametrize("label", ["greeting", "information", "action", "mixed"])
def test_label_does_not_require_nonempty_extraction_or_filter_supplied_items(label):
    empty = extract(ExtractionModel(output()), "Please explain the process.", label)
    assert empty["proposal"] == output() and empty["issues"] == []
    nonempty = extract(ExtractionModel(output(disputes=[item()])), label=label)
    assert len(nonempty["proposal"]["disputes"]) == 1


@pytest.mark.parametrize("collection,prefix", [("disputes", "dispute"), ("objectives", "objective")])
def test_each_collection_is_independent_and_gets_owned_proposal_ids(collection, prefix):
    supplied = output(**{collection: [item()]})
    original = deepcopy(supplied)
    result = extract(ExtractionModel(supplied))
    unit = result["proposal"][collection][0]
    assert unit["id"] == f"{prefix}:1" and unit["state"] == "proposed"
    assert unit["source_ids"] == ["current"]
    assert len(result["proposal"]["objectives" if collection == "disputes" else "disputes"]) == 0
    assert extraction_units(result) == {unit["id"]: {"kind": collection, "proposal": unit}}
    assert supplied == original


def test_code_resolves_exact_words_with_unicode_and_original_whitespace():
    message = "Hello.\n  She said ‘access denied’—I disagree.  Please research it."
    quote = "She said ‘access denied’—I disagree."
    result = extract(ExtractionModel(output(disputes=[item(passages=[passage(quote)])])),
                     message, "mixed")
    resolved = result["proposal"]["disputes"][0]["passages"][0]
    assert resolved == {**passage(quote), "start": message.index(quote),
                        "end": message.index(quote) + len(quote)}
    assert message[resolved["start"]:resolved["end"]] == quote
    assert result["sources"][-1]["message"]["text"] == message


def test_authorised_review_can_use_earlier_original_support_and_current_context():
    history = [
        {"role": "advocate", "text": "I want access restored, not ownership."},
        {"role": "nm", "text": "You seek ownership."},
    ]
    supporting = [passage("I want access restored, not ownership.", "history_1"),
                  passage("You seek ownership.", "history_2", "context"),
                  passage("Review your earlier interpretation.", "current", "context")]
    proposal = item("Restoration of access", supporting,
                    "The earlier NM interpretation does not match the reported objective.")
    result = extract(ExtractionModel(output(objectives=[proposal])),
                     "Review your earlier interpretation.", "action", history)
    assert result["issues"] == []
    actual = result["proposal"]["objectives"][0]
    assert actual["description"] == proposal["description"]
    assert actual["uncertainty"] == proposal["uncertainty"]
    assert actual["source_ids"] == ["history_1", "history_2", "current"]
    assert [p["purpose"] for p in actual["passages"]] == ["support", "context", "context"]


@pytest.mark.parametrize("passages", [
    [passage("You seek ownership.", "history_2"), passage("Review it.", purpose="context")],
    [passage("I want access.", "history_1")],
    [passage("Review it.", purpose="context")],
    [passage("Review it.", "absent")],
])
def test_nm_support_missing_current_missing_support_or_foreign_source_is_held(passages):
    history = [{"role": "advocate", "text": "I want access."},
               {"role": "nm", "text": "You seek ownership."}]
    supplied = item(passages=passages)
    result = extract(ExtractionModel(output(objectives=[supplied])), "Review it.", "action", history)
    assert result["proposal"]["objectives"] == []
    assert result["issues"][0]["unit"] == "objective:1"
    assert result["issues"][0]["rejected_proposal"] == supplied


@pytest.mark.parametrize("message,quote", [
    ("He refused delivery.", "He refuses delivery."),
    ("He refused delivery.", "he refused delivery."),
    ("He refused delivery.", "He refused  delivery."),
    ("No. No.", "No."),
    ("aaaa", "aa"),
])
def test_changed_or_ambiguous_quotes_are_held_without_fuzzy_repair(message, quote):
    supplied = item(passages=[passage(quote)])
    result = extract(ExtractionModel(output(disputes=[supplied])), message)
    assert result["proposal"]["disputes"] == []
    assert result["issues"][0]["rejected_proposal"] == supplied


def test_longer_unique_passage_resolves_repeated_wording_without_choosing_arbitrarily():
    message = "No. No. The second answer concerns access."
    quote = "No. The second answer concerns access."
    result = extract(ExtractionModel(output(disputes=[item(passages=[passage(quote)])])), message)
    assert result["issues"] == []
    assert result["proposal"]["disputes"][0]["passages"][0]["start"] == 4


@pytest.mark.parametrize("invalid", [
    {}, item(description="  "), item(passages=[]),
    item(passages=[passage(purpose="proof")]),
    {**item(), "activities": ["Send a notice."]},
    {**item(), "id": "dispute:99"},
])
def test_malformed_independent_item_does_not_erase_valid_peer(invalid):
    response = output(disputes=[invalid, item()], objectives=[item()])
    model = ExtractionModel(response)
    result = extract(model)
    assert [unit["id"] for unit in result["proposal"]["disputes"]] == ["dispute:2"]
    assert [unit["id"] for unit in result["proposal"]["objectives"]] == ["objective:1"]
    assert result["issues"][0]["unit"] == "dispute:1"
    assert result["issues"][0]["rejected_proposal"] == invalid
    assert result["issues"][0]["reason"].strip()
    assert len(model.calls) == 1
    assert set(extraction_units(result)) == {"dispute:2", "objective:1"}


def test_completed_quarantined_output_still_needs_per_item_admission():
    class QuarantinedModel(ExtractionModel):
        def structured(self, *args, **kwargs):
            receipt = super().structured(*args, **kwargs)
            raise SchemaViolation("Completed object contains an invalid item", rejected_result=receipt)

    model = QuarantinedModel(output(disputes=[item(description=""), item()]))
    result = extract(model)
    assert [unit["id"] for unit in result["proposal"]["disputes"]] == ["dispute:2"]
    assert len(result["issues"]) == len(model.calls) == 1


@pytest.mark.parametrize("response", [
    {"disputes": []}, {**output(), "reply_draft": "Completed."},
    {**output(), "actions": []}, {"disputes": "none", "objectives": []},
])
def test_bad_envelope_is_typed_failure_without_a_private_retry(response):
    model = ExtractionModel(response)
    with pytest.raises(SchemaViolation) as caught:
        extract(model)
    assert len(model.calls) == 1
    assert caught.value.usage == Usage(10, 5, 0)
    assert caught.value.latency_ms == 7


def test_incomplete_provider_result_is_never_salvaged():
    model = ExtractionModel(output(disputes=[item()]), completion=Completion.NOT_ESTABLISHED)
    with pytest.raises(ModelError) as caught:
        extract(model)
    assert len(model.calls) == 1 and caught.value.usage == Usage(10, 5, 0)


@pytest.mark.parametrize("kwargs,error", [
    ({"message": "  "}, ValueError), ({"label": "verified"}, SchemaViolation),
    ({"history_complete": False}, ValueError),
    ({"history": [{"role": "unknown", "text": "Original words."}]}, ValueError),
    ({"history": [{"role": "advocate", "text": ""}]}, ValueError),
])
def test_invalid_original_context_prevents_dispatch(kwargs, error):
    model = ExtractionModel()
    with pytest.raises(error):
        extract(model, **kwargs)
    assert model.calls == []


def test_context_overflow_does_not_summarise_or_trim_original_history():
    history = [{"role": "advocate", "text": "Original account. " * 300}]
    original = deepcopy(history)
    model = ExtractionModel(budget=1)
    with pytest.raises(ContextOverflow):
        extract(model, history=history)
    assert history == original and model.calls == []


@pytest.mark.parametrize("mutate", [
    lambda saved: saved.update(contract="future_extraction_v2"),
    lambda saved: saved.update(state="admitted"),
    lambda saved: saved["sources"][-1].update(id="history_1"),
    lambda saved: saved["sources"][-1]["message"].update(role="nm"),
    lambda saved: saved["sources"][-1]["message"].update(text="Changed original words."),
    lambda saved: saved["proposal"]["disputes"][0].update(source_ids=["history_1"]),
    lambda saved: saved["proposal"]["disputes"][0].update(id="objective:1"),
    lambda saved: saved["proposal"]["disputes"][0].update(state="verified"),
    lambda saved: saved["proposal"]["disputes"][0]["passages"][0].update(start=1),
    lambda saved: saved["proposal"]["disputes"][0]["passages"][0].update(end=1),
    lambda saved: saved["proposal"]["disputes"][0]["passages"][0].update(quote="The supplier delivered."),
])
def test_saved_extraction_requires_owned_contract_sources_ids_and_actual_offsets(mutate):
    saved = extracted()
    mutate(saved)
    with pytest.raises(SchemaViolation):
        extraction_units(saved)


def test_saved_catalogue_is_separate_from_the_snapshot_it_validates():
    saved = extracted()
    original = deepcopy(saved)
    catalogue = extraction_units(saved)
    catalogue["dispute:1"]["proposal"]["description"] = "Changed by downstream consumer"
    assert saved == original
