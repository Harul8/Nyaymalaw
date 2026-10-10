"""Raw public replies preserve legitimate neighbouring-span corrections.

The independent scope is authored before extraction. Reader and response
reviewers are scripted accepting judges; only the owned source, operation and
target contracts constrain their proposals. No live model is contacted.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as boundary
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.brain_reader_fixture import (
    fixture_scoped_coverage,
    fresh_review_reply,
    reader_operations,
    reader_repairs,
)
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import (
    RawExpressionModel,
    expression,
    raw_unit,
    reopened,
    visible,
)
from tests.test_brain_material import _with_source_ids, material
from tests.test_brain_turn import plan

ORIGINAL = "The cartons arrived on 17 April."
CUSTODY = "The tablet remains with the client."
INSTRUCTION = "Correct the arrival entry."
REVISED = "The cartons arrived on 19 April."
SAME_TURN = "same_original_advocate_turn_v1"


def account_scope_judgment(payload, reviewed, *, distinct_disputes=False,
                           dated_candidate_id=None):
    """The scenario author declares factual events and the separate instruction.

    Arrival and custody are event-record work, outside distinct-dispute
    formulation. These declarations precede extraction; a rejected operation
    cannot convert the dated account into non-account content.
    """
    purposes = {ORIGINAL: "account", CUSTODY: "account", REVISED: "account",
                INSTRUCTION: "non_account"}
    choices = {identity: purposes[reference["quoted"]]
               for identity, reference in payload["source_treatments"].items()}
    if distinct_disputes:
        choices = {identity: "outside_scope" if purpose == "account" else purpose
                   for identity, purpose in choices.items()}
    # The scenario owner separately declares that the one arrival correction
    # represents each verbatim repetition of the same reported date. Selecting
    # its owned coverage link does not broaden source support or permission.
    links = {identity: {"record_ids": [], "candidate_ids": [dated_candidate_id]}
             for identity, reference in payload["source_treatments"].items()
             if dated_candidate_id is not None and reference["quoted"] == REVISED}
    return fixture_scoped_coverage(payload, reviewed, source_decisions=choices,
                                   representation_choices=links)


def result(data, tier):
    return ModelResult(text=None, data=data, tier=tier, provider="offline", model="offline",
                       usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


class SpanNeighbourModel(RawExpressionModel):
    """Only extractor fixtures are transported; every writer expression is raw."""

    def __init__(self, routes, writers, *, records, selected_source=None, fulfilled=False,
                 omit_failed_units=False):
        super().__init__(routes, writers)
        self.records = records
        self.selected_source = selected_source
        self.fulfilled = fulfilled
        self.omit_failed_units = omit_failed_units

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation == "extract_legal_details":
            payload = json.loads(prompt.user)
            self.calls.append((prompt.operation, payload))
            self.schemas.append((prompt.operation, deepcopy(schema)))
            self.tiers.append(tier)
            source = payload.get("original_input", payload)
            if self.omit_failed_units and "repairs" in schema.get("properties", {}):
                return result({"repairs": {
                    identity: {"proposals": []} for identity in
                    schema["properties"]["repairs"]["properties"]}}, tier)
            rows = [_with_source_ids(row, source) for row in self.records]
            if self.selected_source is not None:
                for row in rows:
                    row["source_id"] = self.selected_source
            data = reader_operations(rows, source, link_field="related_material_ids")
            return result(reader_repairs(data, schema), tier)
        checked = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        if prompt.operation == "classify_account_sources":
            payload = json.loads(prompt.user)
            original = payload.get("original_input", payload)
            data = deepcopy(checked.data)
            # This explicit scenario judgment distinguishes permission from
            # evidence; no fixture or production code classifies by keywords.
            for identity, row in data["source_treatments"].items():
                if original["original_source_catalogue"][identity]["quoted"] == INSTRUCTION:
                    row.update(content_role="work_instruction", substantive_spans=[],
                               reason="The scenario owner declares this source an instruction.")
            return replace(checked, data=data)
        if prompt.operation in ("verify_disputes", "verify_material_grounding"):
            payload = json.loads(prompt.user)
            data = deepcopy(checked.data)
            if prompt.operation == "verify_material_grounding" and self.selected_source:
                reference = payload["source_treatments"].get(self.selected_source)
                for verdict in data["verdicts"]:
                    if verdict["verdict"] == "accept":
                        verdict["account_check"]["source_ids"] = [self.selected_source]
                        verdict["account_check"]["source_checks"] = [{
                            "source_id": self.selected_source, "supplies_account_content": True,
                            "supports_proposal": True,
                            "support_spans": [{"start": 0, "end": len(reference["quoted"])}]
                            if reference is not None else [],
                            "reason": "The scripted independent judge selects this dated account.",
                        }]
            data["coverage"] = account_scope_judgment(
                payload, data, distinct_disputes=prompt.operation == "verify_disputes",
                dated_candidate_id="D1"
                if prompt.operation == "verify_material_grounding" and self.selected_source
                else None)
            return replace(checked, data=fresh_review_reply(payload, data))
        if prompt.operation == "verify_continuation" and self.fulfilled:
            data = deepcopy(checked.data)
            for verdict in data["verdicts"]:
                verdict["record_check"] = {
                    "outcome": "fulfilled",
                    "reason": "The independent scripted judgment confirms the requested date.",
                }
            return replace(checked, data=data)
        return checked


def seed(client, wired, monkeypatch, turn_id):
    message = ORIGINAL + " " + CUSTODY
    model = SpanNeighbourModel(
        [plan(message, scope="proposed", title="Arrival and custody account", summary=message,
              material_purposes=("account_contribution",))],
        [lambda payload: {"units": [raw_unit(payload)]}],
        records=[material("event", ORIGINAL, ORIGINAL, placement="matter"),
                 material("event", CUSTODY, CUSTODY, placement="matter")])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, message, turn_id + "-seed")
    saved = reopened(wired, opened)
    conversation, _, _ = boundary._current_records(wired.store, saved)
    before = deepcopy(conversation.open_material)
    assert len(before) == 2, "Both owned target neighbours must actually be saved."
    targets = {row["statement"]: row["id"] for row in before}
    return opened, before, targets[ORIGINAL], targets[CUSTODY]


def route(message, target, *, permission="L1"):
    interpreted = plan(
        message, scope="current", relation="continues",
        material_purposes=("account_contribution",),
        record_requirement={"kind": "change", "operation": "corrects", "target_ids": [target],
                            "success_condition": "The entry records the reported 19 April date."})
    interpreted["items"][0]["mutation_scopes"] = [{
        "authority_kind": "account_contribution", "authority_source_ids": [permission],
        "target_scope": "exact", "target_ids": [target], "permitted_relations": ["corrects"],
    }]
    return interpreted


def correction(turn_id, target, *, relation="corrects"):
    return material(
        "event", REVISED, REVISED, relation=relation, scope="current", placement="matter",
        related_material_ids=[target],
        references=[{"turn_id": turn_id + "-seed", "role": "advocate", "quoted": ORIGINAL}])


def writer(payload, *, fulfilled):
    if fulfilled:
        assert any(effect["performed"] for effect in payload["record_effect_catalogue"].values()), (
            "The legitimate owned correction was held before the writer.")
    unit = raw_unit(payload, record_status="performed" if fulfilled else "unresolved")
    unit["blocks"].append({
        "id": "record-status", "kind": "completion", "uncertainty": "none",
        "evidence_expression": expression("record_result"),
    })
    unit["record_outcome"].update(
        block_id="record-status",
        effect_ids=[identity for identity, effect in payload["record_effect_catalogue"].items()
                    if effect["performed"]] if fulfilled else [],
        reason="The scripted judgment confirms the requested result." if fulfilled else
        "The requested result remains unfinished.")
    return {"units": [unit]}


def saved_and_replayed(client, wired, model, answer, opened, turn_id, message):
    saved = reopened(wired, answer)
    assert saved.brain_chat[-1]["message"] == message
    assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]
    assert saved.brain_chat[-1]["elements"] == answer["elements"]
    calls, version = len(model.calls), saved.version
    replay = send(client, message, turn_id, opened=opened)
    assert replay["replayed"] is True
    assert replay["metrics"]["llm_calls"] == 0
    assert replay["elements"] == answer["elements"]
    assert replay["material_coverage"]["execution"] == answer["material_coverage"]["execution"]
    assert len(model.calls) == calls
    assert reopened(wired, answer).version == version
    return saved


@pytest.mark.parametrize("permission,selected_source,repeated", [
    ("L1", "L2", False), ("L2", "L2", False), ("L1", "L3", True),
])
def test_owned_same_turn_support_saves_requested_correction_with_raw_reply_and_exact_replay(
        client, wired, monkeypatch, permission, selected_source, repeated):
    turn_id = "scope-span-neighbour-" + permission + "-" + selected_source
    opened, before, target, custody = seed(client, wired, monkeypatch, turn_id)
    message = INSTRUCTION + " " + REVISED + (" " + REVISED if repeated else "")
    model = SpanNeighbourModel(
        [route(message, target, permission=permission)],
        [lambda payload: writer(payload, fulfilled=True)],
        records=[correction(turn_id, target)], selected_source=selected_source, fulfilled=True)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, turn_id, opened=opened)
    assert answer["blocked"] is False
    assert answer["metrics"]["llm_calls"] == 8
    execution = answer["material_coverage"]["execution"]
    assert execution["requests"][0]["fulfillment"] == "fulfilled"
    assert execution["mutation_authorities"]["source_match_contract"] == SAME_TURN
    proposal, = answer["material"]
    binding = proposal["mutation_authority"]
    assert binding["current_source_reference"]["source_id"] == selected_source
    assert binding["supporting_source_ids"] == [selected_source]
    scope, = execution["mutation_authorities"]["authorities"]
    assert scope["authority_source_ids"] == [permission]
    assert scope["target_ids"] == binding["target_ids"] == [target]
    assert binding["attached_context_source_ids"]
    assert execution["effects"]["details"]["retired_record_ids"] == [target]
    saved = saved_and_replayed(client, wired, model, answer, opened, turn_id, message)
    conversation, _, _ = boundary._current_records(wired.store, saved)
    assert {row["statement"] for row in conversation.open_material} == {REVISED, CUSTODY}
    assert next(row for row in conversation.open_material if row["id"] == custody) == (
        next(row for row in before if row["id"] == custody))
    assert len(model.writer_outputs) == 1
    assert sum(operation == "extract_legal_details" for operation, _ in model.calls) == 1
    assert sum(operation == "verify_material_grounding" for operation, _ in model.calls) == 1
    assert sum(operation == "verify_continuation" for operation, _ in model.calls) == 1


@pytest.mark.parametrize("fault", ["wrong_owned_target", "wrong_relation", "foreign_source"])
def test_wrong_accepting_judges_cannot_widen_neighbor_scope_or_own_foreign_source(
        client, wired, monkeypatch, fault):
    turn_id = "scope-span-rejected-" + fault
    opened, before, target, custody = seed(client, wired, monkeypatch, turn_id)
    message = INSTRUCTION + " " + REVISED
    candidate = correction(turn_id, custody if fault == "wrong_owned_target" else target,
                           relation="adds" if fault == "wrong_relation" else "corrects")
    model = SpanNeighbourModel(
        [route(message, target)], [lambda payload: writer(payload, fulfilled=False)],
        records=[candidate],
        selected_source="foreign-source" if fault == "foreign_source" else "L2",
        omit_failed_units=fault == "foreign_source")
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, turn_id, opened=opened)
    assert answer["blocked"] is False
    assert "requested record work remains unfinished" in visible(answer)
    execution = answer["material_coverage"]["execution"]
    assert execution["requests"][0]["fulfillment"] == "unfinished"
    assert execution["record_changes"] == []
    assert answer["material"] == []
    saved = saved_and_replayed(client, wired, model, answer, opened, turn_id, message)
    conversation, _, _ = boundary._current_records(wired.store, saved)
    assert conversation.open_material == before
    assert len(model.writer_outputs) == 1
