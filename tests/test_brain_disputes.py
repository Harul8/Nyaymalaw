"""A focused dispute read selects saved spans and can correct a bad selection."""
import json

import pytest

from nm.brain.conversation import Message
from nm.brain.disputes import extract_disputes
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelResult, SchemaViolation, Tier, Usage
from tests.brain_reader_fixture import reader_operations, reader_repairs


class Model:
    def __init__(self, disputes, *, repair=None, budget=20_000,
                 completion=Completion.COMPLETE):
        self.disputes = disputes
        self.repair = repair
        self.budget = budget
        self.completion = completion
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.ROUTINE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        disputes = self.repair if len(self.calls) > 1 and self.repair is not None \
            else self.disputes
        data = reader_operations(disputes, json.loads(prompt.user),
                                 link_field="related_dispute_ids", infer_targets=False)
        return ModelResult(
            text=None, data=reader_repairs(data, schema), tier=tier,
            provider="offline", model="offline", usage=Usage(0, 0, 0),
            latency_ms=0, completion=self.completion,
        )


def dispute(statement, source_id, *, relation="new", scope="proposed",
            prior_source_ids=None, related=(), identification="identified",
            clarification="", label=None):
    row = {
        "statement": statement, "source_id": source_id, "relation": relation,
        "matter_scope": scope, "basis": "stated", "importance": "central",
        "why_material": "It requires a distinct practical conclusion.",
        "label": label or statement[:80], "identification": identification,
        "clarification": clarification, "related_dispute_ids": list(related),
    }
    if prior_source_ids is not None:
        row["prior_source_ids"] = prior_source_ids
    return row


def _source_text(spans):
    return "".join(span["text"] for span in spans)


def test_first_message_uses_one_focused_call_and_rehydrates_selected_words():
    latest = ("The supplier kept our tools. Separately, the customer has not "
              "paid the invoice.")
    model = Model([
        dispute("Whether the supplier must return the tools.", "L1",
                label="Supplier kept our tools"),
        dispute("Whether the customer must pay the invoice.", "L2",
                label="Customer has not paid the invoice"),
    ])

    rows = extract_disputes(model, earlier=(), latest=latest,
                            current_matter_id=None)

    assert len(model.calls) == 1
    assert [row.quoted for row in rows] == [
        "The supplier kept our tools.",
        "Separately, the customer has not paid the invoice.",
    ]
    assert all(row.kind == "dispute" and row.prior_references == () for row in rows)
    assert [row.label for row in rows] == [
        "Supplier kept our tools", "Customer has not paid the invoice"]
    prompt, schema, tier, output_limit = model.calls[0]
    assert prompt.operation == "extract_disputes" and tier is Tier.ROUTINE
    assert output_limit >= 3072
    payload = json.loads(prompt.user)
    assert payload["earlier_conversation"] == []
    assert payload["current_matter_id"] is None
    assert _source_text(payload["latest_message_spans"]) == latest
    assert [span["id"] for span in payload["latest_message_spans"]] == ["L1", "L2"]
    assert all(label in prompt.system for label in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))
    item = schema["properties"]["new_items"]["items"]
    assert item["properties"]["source_id"]["enum"] == ["L1", "L2"]
    assert "quoted" not in item["properties"]
    assert "prior_source_ids" not in item["properties"]
    assert "relation" not in item["properties"]
    assert "related_dispute_ids" not in item["properties"]
    assert "current" not in item["properties"]["matter_scope"]["enum"]
    assert "kind" not in item["properties"]


def test_contextual_correction_uses_full_attributed_history_and_exact_reference():
    earlier = (
        Message("turn-1", "advocate", "The contractor says we owe freight."),
        Message("turn-1", "nm", "Is freight payable under your agreement?"),
    )
    latest = "Correction: the contract puts freight on the contractor."
    model = Model([dispute(
        "Who must pay freight under the contract?", "L1", relation="corrects",
        scope="current", prior_source_ids=["P1S1"],
        related=["turn-1:material:1"])])
    prior_disputes = ({"id": "turn-1:material:1", "label": "Freight",
                       "statement": "Who must pay freight?",
                       "identification": "identified", "clarification": "",
                       "source_turn_id": "turn-1", "quoted": earlier[0].text},)

    rows = extract_disputes(model, earlier=earlier, latest=latest,
                            current_matter_id="matter-1",
                            prior_disputes=prior_disputes)

    assert len(rows) == 1
    assert rows[0].relation == "corrects"
    assert rows[0].quoted == latest
    assert rows[0].prior_references[0].quoted == earlier[0].text
    assert rows[0].prior_references[0].turn_id == "turn-1"
    assert rows[0].prior_references[0].role == "advocate"
    assert rows[0].related_dispute_ids == ("turn-1:material:1",)
    prompt, schema, _, _ = model.calls[0]
    payload = json.loads(prompt.user)
    assert [(message["turn_id"], message["role"],
             _source_text(message["source_spans"]))
            for message in payload["earlier_conversation"]] == [
                (message.turn_id, message.role, message.text) for message in earlier]
    assert _source_text(payload["latest_message_spans"]) == latest
    assert [{key: value for key, value in row.items() if key not in ("source_ids", "record_role")}
            for row in payload["prior_disputes"]] == list(prior_disputes)
    assert payload["prior_disputes"][0]["record_role"] == "nm_interpretation"
    assert payload["prior_disputes"][0]["source_ids"] == ["P1S1"]
    item = schema["properties"]["changes"]["items"]
    assert item["properties"]["prior_source_ids"]["items"]["enum"] == [
        "P1S1", "P2S1"]
    assert "prior_source_ids" in item["required"]
    assert "current" in item["properties"]["matter_scope"]["enum"]
    assert item["properties"]["related_dispute_ids"]["items"]["enum"] == [
        "turn-1:material:1"]


def test_uncertain_issue_carries_one_question_without_treating_merits_as_uncertain():
    model = Model([dispute(
        "Whether the payment was due.", "L1",
        identification="needs_clarification",
        clarification="Which agreement governs this payment?")])

    rows = extract_disputes(model, earlier=(), latest="The payment is disputed.",
                            current_matter_id=None)

    assert rows[0].identification == "needs_clarification"
    assert rows[0].clarification == "Which agreement governs this payment?"
    assert rows[0].recorded("turn", 1)["label"] == "Whether the payment was due."


def test_linked_canonical_source_is_added_without_replacing_selected_context():
    earlier = (Message("first", "advocate", "Delivery is disputed. Fee is disputed."),)
    model = Model([dispute(
        "Whether delivery occurred.", "L1", relation="corrects",
        scope="current", prior_source_ids=["P1S1"], related=["fee"])])
    prior_disputes = ({"id": "fee", "label": "Fee", "statement": "Fee issue",
                       "identification": "identified", "clarification": "",
                       "source_turn_id": "first", "quoted": "Fee is disputed."},)

    rows = extract_disputes(model, earlier=earlier,
                            latest="Correction: delivery occurred.",
                            current_matter_id="matter-1",
                            prior_disputes=prior_disputes)
    assert len(model.calls) == 1
    assert rows[0].related_dispute_ids == ("fee",)
    assert {ref.quoted for ref in rows[0].prior_references} == {
        "Delivery is disputed.", "Fee is disputed."}


def test_original_source_and_selected_context_do_not_require_a_copying_retry():
    earlier = (Message("first", "advocate",
                       "Return was promised within seven days. Keys were handed over on Monday."),)
    prior = ({"id": "return", "label": "Return", "statement": "When must it be returned?",
              "identification": "identified", "clarification": "",
              "source_turn_id": "first",
              "quoted": "Return was promised within seven days."},)
    invalid = dispute("When must it be returned?", "L1", relation="corrects",
                      scope="current", prior_source_ids=["P1S2"],
                      related=["return"])
    corrected = {**invalid, "prior_source_ids": ["P1S1", "P1S2"]}
    model = Model([invalid], repair=[corrected])

    rows = extract_disputes(model, earlier=earlier,
                            latest="Correction: keys were handed over on Tuesday.",
                            current_matter_id="matter-1", prior_disputes=prior)

    assert len(model.calls) == 1
    assert rows[0].related_dispute_ids == ("return",)
    assert {ref.quoted for ref in rows[0].prior_references} == {
        "Return was promised within seven days.",
        "Keys were handed over on Monday."}


def test_selected_prior_dispute_resolves_an_empty_source_list():
    earlier = (Message("first", "advocate", "The payment is disputed."),)
    prior = ({"id": "payment", "label": "Payment", "statement": "Who must pay?",
              "source_turn_id": "first", "quoted": "The payment is disputed."},)
    model = Model([dispute(
        "Who must pay?", "L1", relation="corrects", scope="current",
        prior_source_ids=[], related=["payment"])])

    result = extract_disputes(model, earlier=earlier,
                              latest="Correction: payment has now been made.",
                              current_matter_id="matter-1",
                              prior_disputes=prior)

    assert len(model.calls) == 1
    assert result[0].prior_references[0].quoted == "The payment is disputed."


def test_withdrawal_needs_an_exact_active_link_and_gets_one_correction():
    earlier = (Message("first", "advocate", "The payment is disputed."),)
    prior = ({"id": "payment", "label": "Payment", "statement": "Who must pay?",
              "source_turn_id": "first", "quoted": earlier[0].text},)
    unlinked = dispute(
        "The payment dispute is withdrawn.", "L1", relation="withdraws",
        scope="current", prior_source_ids=["P1S1"])
    linked = {**unlinked, "related_dispute_ids": ["payment"]}
    model = Model([unlinked], repair=[linked])

    result = extract_disputes(
        model, earlier=earlier, latest="I withdraw the payment dispute.",
        current_matter_id="matter-1", prior_disputes=prior)

    assert len(model.calls) == 2
    assert result[0].relation == "withdraws"
    assert result[0].related_dispute_ids == ("payment",)
    feedback = json.loads(model.calls[1][0].user)
    failed = feedback["failed_units"][0]
    assert "related_dispute_ids" in failed["validation_issue"]
    assert failed["field"] == "changes" and failed["unit_id"] == "changes:1"

    persistent = Model([unlinked])
    with pytest.raises(SchemaViolation, match="related_dispute_ids"):
        extract_disputes(
            persistent, earlier=earlier,
            latest="I withdraw the payment dispute.",
            current_matter_id="matter-1", prior_disputes=prior)
    assert len(persistent.calls) == 2


def test_invalid_source_id_gets_one_feedback_guided_correction():
    latest = "The invoice remains unpaid. A receipt may be available."
    rejected = dispute("Whether payment is owed.", "unknown")
    corrected = dispute("Whether payment is owed.", "L1")
    model = Model([rejected], repair=[corrected])

    rows = extract_disputes(model, earlier=(), latest=latest,
                            current_matter_id=None)

    assert [row.quoted for row in rows] == ["The invoice remains unpaid."]
    assert len(model.calls) == 2
    repair_prompt, repair_schema, _, _ = model.calls[1]
    feedback = json.loads(repair_prompt.user)
    assert feedback["original_input"] == json.loads(model.calls[0][0].user)
    failed = feedback["failed_units"][0]
    first_wire = reader_operations(
        [rejected], feedback["original_input"], link_field="related_dispute_ids",
        infer_targets=False)
    assert failed["proposal"] == first_wire["new_items"][0]
    assert failed["unit_id"] == "new_items:1" and failed["field"] == "new_items"
    assert "source_id" in failed["validation_issue"] or "source" in failed[
        "validation_issue"].lower()
    repairs = repair_schema["properties"]["repairs"]
    assert repairs["required"] == ["new_items:1"]
    assert (repairs["properties"]["new_items:1"]["anyOf"][0]["properties"]["proposals"]["items"]
            == model.calls[0][1]["properties"]["new_items"]["items"])
    assert repair_prompt.operation == "extract_disputes"
    assert all(label in repair_prompt.system for label in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))


def test_persistently_invalid_prior_id_or_scope_refuses_after_bounded_retry():
    earlier = (Message("turn-1", "advocate", "We were given possession."),)
    latest = "Correction: we were never given possession."
    invalid = dispute("Whether possession was delivered.", "L1",
                      relation="corrects", scope="proposed",
                      prior_source_ids=["missing"])
    model = Model([invalid])

    with pytest.raises(SchemaViolation):
        extract_disputes(model, earlier=earlier, latest=latest,
                         current_matter_id=None)
    assert len(model.calls) == 2

    wrong_scope = Model([dispute("Whether payment is owed.", "L1",
                                 scope="current")])
    with pytest.raises(SchemaViolation):
        extract_disputes(wrong_scope, earlier=(), latest="The bill is unpaid.",
                         current_matter_id=None)
    assert len(wrong_scope.calls) == 2


def test_empty_dispute_inventory_is_valid_but_incomplete_read_is_not():
    empty = Model([])
    assert extract_disputes(empty, earlier=(), latest="Hello",
                            current_matter_id=None) == ()
    assert len(empty.calls) == 1

    incomplete = Model([], completion=Completion.LENGTH_LIMITED)
    with pytest.raises(SchemaViolation):
        extract_disputes(incomplete, earlier=(), latest="Hello",
                         current_matter_id=None)
    assert len(incomplete.calls) == 2


def test_full_context_overflow_refuses_before_dispatch():
    model = Model([], budget=100)
    with pytest.raises(ContextOverflow):
        extract_disputes(model, earlier=(), latest="A contested payment.",
                         current_matter_id=None)
    assert model.calls == []
