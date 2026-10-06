"""The detail reader resolves cited source IDs against the full saved record."""
import json

import pytest

from nm.brain.conversation import Message
from nm.brain.material import extract_details
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ContextOverflow,
    ModelResult,
    SchemaViolation,
    Tier,
    Usage,
    on_the_wire,
)
from tests.brain_reader_fixture import reader_operations, reader_repairs


class Model:
    def __init__(self, data, *, repair=None, budget=20000,
                 completion=Completion.COMPLETE):
        self.data = data
        self.repair = repair
        self.budget = budget
        self.completion = completion
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        data = self.repair if len(self.calls) > 1 and self.repair is not None \
            else self.data
        result = reader_operations(data["details"], json.loads(prompt.user),
                                   link_field="related_material_ids", infer_targets=False)
        result = reader_repairs(result, schema)
        return ModelResult(text=None, data=result, tier=tier,
                           provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0,
                           completion=self.completion)


def candidate(*, source_id, kind="circumstance", relation="new",
              prior_source_ids=None, scope="current"):
    row = {
        "kind": kind,
        "statement": "The advocate now says the deposit was three units.",
        "source_id": source_id,
        "relation": relation,
        "matter_scope": scope,
        "basis": "stated",
        "importance": "relevant",
        "why_material": "The amount may affect the next step.",
        "placement": "unresolved", "dispute_ids": [],
        "related_material_ids": [],
    }
    if prior_source_ids is not None:
        row["prior_source_ids"] = prior_source_ids
    return row


def _source_text(spans):
    return "".join(span["text"] for span in spans)


def test_complete_attributed_conversation_and_sourced_change_use_one_call():
    earlier = (
        Message("t1", "advocate", "The deposit was four units."),
        Message("t1", "nm", "Please check the amount of the deposit."),
        Message("t2", "advocate", "I will check the receipt."),
        Message("t2", "nm", "Let me know what it says."),
    )
    latest = "Correction: the deposit was three units, not four."
    row = candidate(source_id="L1", relation="corrects",
                    prior_source_ids=["P1S1"])
    row["related_material_ids"] = ["t1:material:1"]
    model = Model({"details": [row]})

    material = extract_details(model, earlier=earlier, latest=latest,
                               current_matter_id="matter-1", prior_material=({
                                   "id": "t1:material:1", "kind": "circumstance",
                                   "statement": earlier[0].text, "source_turn_id": "t1",
                                   "quoted": earlier[0].text,
                                   "placement": "unresolved", "dispute_ids": []},))

    assert len(model.calls) == 1
    prompt, schema, tier, ceiling = model.calls[0]
    assert tier is Tier.ROUTINE
    assert ceiling >= 6144
    assert prompt.operation == "extract_legal_details"
    assert all(label in prompt.system for label in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))
    assert "independently material account details" in prompt.system
    payload = json.loads(prompt.user)
    assert payload["current_matter_id"] == "matter-1"
    assert [(entry["turn_id"], entry["role"],
             _source_text(entry["source_spans"]))
            for entry in payload["earlier_conversation"]] == [
                (msg.turn_id, msg.role, msg.text) for msg in earlier]
    assert _source_text(payload["latest_message_spans"]) == latest
    assert set(schema["properties"]) == {"new_items", "changes"}
    item = schema["properties"]["changes"]["items"]
    assert "dispute" not in item["properties"]["kind"]["enum"]
    assert item["properties"]["source_id"]["enum"] == ["L1"]
    assert item["properties"]["prior_source_ids"]["items"]["enum"] == [
        "P1S1", "P2S1", "P3S1", "P4S1"]
    assert "quoted" not in item["properties"]
    assert material[0].quoted == latest
    assert material[0].prior_references[0].quoted == earlier[0].text
    assert material[0].prior_references[0].role == "advocate"


def test_invalid_source_selection_gets_one_feedback_guided_correction():
    latest = "The deposit was three units. A receipt is available."
    rejected = candidate(source_id="missing", scope="proposed")
    corrected = candidate(source_id="L1", scope="proposed")
    model = Model({"details": [rejected]}, repair={"details": [corrected]})

    result = extract_details(model, earlier=(), latest=latest,
                             current_matter_id=None)

    assert len(model.calls) == 2
    assert result[0].quoted == "The deposit was three units."
    repair_prompt = model.calls[1][0]
    feedback = json.loads(repair_prompt.user)
    assert feedback["original_input"] == json.loads(model.calls[0][0].user)
    assert feedback["failed_units"][0]["proposal"] == reader_operations(
        [rejected], feedback["original_input"], link_field="related_material_ids",
        infer_targets=False)["new_items"][0]
    assert feedback["validation_issue"]
    assert feedback["failed_units"][0]["unit_id"] == "new_items:1"
    assert feedback["retained_proposal_context"] == []
    assert repair_prompt.operation == "extract_legal_details"
    assert set(model.calls[1][1]["properties"]) == {"repairs"}


def test_changed_detail_adds_its_saved_source_without_replacing_selected_context():
    earlier = (Message("first", "advocate",
                       "The delivery was late. It arrived on Monday."),)
    prior_material = ({"id": "arrival", "kind": "event",
                       "statement": "It arrived on Monday.",
                       "source_turn_id": "first", "quoted": "It arrived on Monday.",
                       "placement": "unresolved", "dispute_ids": []},)
    wrong = candidate(source_id="L1", relation="corrects",
                      prior_source_ids=["P1S1"])
    wrong["related_material_ids"] = ["arrival"]
    repaired = {**wrong, "prior_source_ids": ["P1S2"]}
    model = Model({"details": [wrong]}, repair={"details": [repaired]})

    rows = extract_details(
        model, earlier=earlier, latest="Correction: it arrived on Tuesday.",
        current_matter_id="matter-1", prior_material=prior_material)

    assert len(model.calls) == 1
    assert json.loads(model.calls[0][0].user)["active_material"][0][
        "source_ids"] == ["P1S2"]
    assert rows[0].related_material_ids == ("arrival",)
    assert {ref.quoted for ref in rows[0].prior_references} == {
        "The delivery was late.", "It arrived on Monday."}


def test_selected_prior_detail_resolves_an_empty_source_list():
    earlier = (Message("first", "advocate", "The receipt is available."),)
    prior_material = ({"id": "receipt", "kind": "evidence",
                       "statement": "A receipt is available.",
                       "source_turn_id": "first",
                       "quoted": "The receipt is available."},)
    row = candidate(source_id="L1", kind="evidence", relation="adds",
                    prior_source_ids=[])
    row["related_material_ids"] = ["receipt"]
    model = Model({"details": [row]})

    result = extract_details(model, earlier=earlier,
                             latest="The receipt records the date.",
                             current_matter_id="matter-1",
                             prior_material=prior_material)

    assert len(model.calls) == 1
    assert result[0].prior_references[0].quoted == "The receipt is available."


def test_withdrawal_needs_an_exact_active_detail_link_and_gets_one_correction():
    earlier = (Message("first", "advocate", "The receipt is available."),)
    prior_material = ({"id": "receipt", "kind": "evidence",
                       "statement": "A receipt is available.",
                       "source_turn_id": "first", "quoted": earlier[0].text},)
    unlinked = candidate(
        source_id="L1", kind="evidence", relation="withdraws",
        prior_source_ids=["P1S1"])
    linked = {**unlinked, "related_material_ids": ["receipt"]}
    model = Model({"details": [unlinked]}, repair={"details": [linked]})

    result = extract_details(
        model, earlier=earlier, latest="I withdraw what I said about a receipt.",
        current_matter_id="matter-1", prior_material=prior_material)

    assert len(model.calls) == 2
    assert result[0].relation == "withdraws"
    assert result[0].related_material_ids == ("receipt",)
    feedback = json.loads(model.calls[1][0].user)
    assert "related_material_ids" in feedback["failed_units"][0]["validation_issue"]
    assert feedback["failed_units"][0]["field"] == "changes"

    persistent = Model({"details": [unlinked]})
    with pytest.raises(SchemaViolation, match="related_material_ids"):
        extract_details(
            persistent, earlier=earlier,
            latest="I withdraw what I said about a receipt.",
            current_matter_id="matter-1", prior_material=prior_material)
    assert len(persistent.calls) == 2


def test_invalid_prior_selection_remains_rejected_after_one_correction():
    earlier = (Message("t1", "advocate", "The deposit was four units."),)
    latest = "Correction: the deposit was three units."
    row = candidate(source_id="L1", relation="corrects",
                    prior_source_ids=["not-an-id"])
    model = Model({"details": [row]})

    with pytest.raises(SchemaViolation):
        extract_details(model, earlier=earlier, latest=latest,
                        current_matter_id="matter-1")

    assert len(model.calls) == 2


def test_details_reader_forbids_dispute_rows():
    latest = "A member denied my voting right. The notice was sent yesterday."
    event = candidate(source_id="L1", kind="event", scope="proposed")
    detail = candidate(source_id="L2", scope="proposed")
    model = Model({"details": [event, detail]})

    result = extract_details(model, earlier=(), latest=latest,
                             current_matter_id=None)

    assert [row.quoted for row in result] == [
        "A member denied my voting right.", "The notice was sent yesterday."]
    assert [row.kind for row in result] == ["event", "circumstance"]
    with pytest.raises(SchemaViolation):
        extract_details(Model({"details": [{**event, "kind": "dispute"}]}),
                        earlier=(), latest=latest, current_matter_id=None)


def test_unfinished_result_and_context_overflow_never_release_material():
    latest = "The deposit was three units."
    row = candidate(source_id="L1", scope="proposed")
    unfinished = Model({"details": [row]},
                       completion=Completion.NOT_ESTABLISHED)
    with pytest.raises(SchemaViolation):
        extract_details(unfinished, earlier=(), latest=latest,
                        current_matter_id=None)
    assert len(unfinished.calls) == 2

    too_small = Model({"details": [row]}, budget=100)
    with pytest.raises(ContextOverflow):
        extract_details(too_small, earlier=(), latest=latest,
                        current_matter_id=None)
    assert too_small.calls == []


def test_first_turn_schema_cannot_name_nonexistent_prior_words():
    latest = "I paid the deposit yesterday."
    row = candidate(source_id="L1", scope="proposed")
    model = Model({"details": [row]})

    result = extract_details(model, earlier=(), latest=latest,
                             current_matter_id=None)

    detail_schema = model.calls[0][1]["properties"]["new_items"]["items"]
    assert "prior_source_ids" not in detail_schema["properties"]
    assert "prior_source_ids" not in detail_schema["required"]
    assert "relation" not in detail_schema["properties"]
    assert "related_material_ids" not in detail_schema["properties"]
    wire = on_the_wire(model.calls[0][1])
    fields = wire["properties"]["new_items"]["items"]["properties"]
    assert "uniqueItems" not in fields["assignment_ids"]
    assert fields["assignment_ids"]["items"]["enum"] == [
        "matter:discussion", "matter:unlinked", "matter:other", "matter:none", "matter:uncertain"]
    assert not {"matter_scope", "placement", "dispute_ids"}.intersection(fields)
    assert wire["properties"]["changes"]["maxItems"] == 0
    assert set(wire["properties"]["new_items"]["items"]["required"]) == set(
        wire["properties"]["new_items"]["items"]["properties"])
    assert result[0].relation == "new"
    assert result[0].prior_references == ()

    with_prior = {**row, "prior_source_ids": ["invented"]}
    for invalid in (with_prior, {**row, "relation": "adds"}):
        invalid_model = Model({"details": [invalid]})
        with pytest.raises(SchemaViolation):
            extract_details(invalid_model, earlier=(), latest=latest,
                            current_matter_id=None)
        assert len(invalid_model.calls) == 2


def test_detail_placement_follows_selected_dispute_ids_without_losing_source():
    latest = "A payment was made. The record is available."
    dispute = {"id": "dispute-1", "label": "Payment disagreement",
               "statement": "The payment is contested.",
               "source_turn_id": "first", "quoted": "A payment was made."}
    linked = {**candidate(source_id="L1", scope="proposed"),
              "placement": "matter", "dispute_ids": ["dispute-1"]}
    unlinked = {**candidate(source_id="L2", scope="proposed"),
                "placement": "disputes", "dispute_ids": []}
    model = Model({"details": [linked, unlinked]})

    result = extract_details(model, earlier=(), latest=latest,
                             current_matter_id=None, disputes=(dispute,))

    assert len(model.calls) == 1
    assert [(item.placement, item.dispute_ids, item.quoted) for item in result] == [
        ("disputes", ("dispute-1",), "A payment was made."),
        ("unresolved", (), "The record is available."),
    ]


def test_no_current_matter_excludes_current_scope_even_with_prior_conversation():
    earlier = (Message("t1", "advocate", "I asked for the deposit back."),)
    latest = "They have kept the deposit."
    row = candidate(source_id="L1", prior_source_ids=[], scope="proposed")
    model = Model({"details": [row]})

    result = extract_details(model, earlier=earlier, latest=latest,
                             current_matter_id=None)

    wire = on_the_wire(model.calls[0][1])
    item = wire["properties"]["new_items"]["items"]
    assert "prior_source_ids" in item["properties"]
    assert "matter_scope" not in item["properties"]
    assert result[0].matter_scope == "proposed"

    invalid = {**row, "assignment_ids": ["matter:current"]}
    with pytest.raises(SchemaViolation):
        extract_details(Model({"details": [invalid]}),
                        earlier=earlier, latest=latest, current_matter_id=None)

    repeated = {**row, "assignment_ids": ["matter:discussion", "matter:discussion"]}
    repeated_model = Model({"details": [repeated]})
    result = extract_details(repeated_model, earlier=earlier, latest=latest,
                             current_matter_id=None)
    assert result[0].placement == "matter"
    assert result[0].dispute_ids == ()
    assert len(repeated_model.calls) == 1
