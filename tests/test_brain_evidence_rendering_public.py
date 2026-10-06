"""Closed fresh expressions survive deliberately wrong review at public release.

The writer returns the actual fresh wire shape, without legacy fixture
conversion. All semantic decisions are fabricated; no provider calls run.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.evidence_rendering import EVIDENCE_EXPRESSION_CONTRACT
from nm.brain.turn import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Usage, require_schema
from tests.brain_continuation_fixture import reviewed_verdicts
from tests.test_brain_continuation import verdict
from tests.test_brain_continuation_service import PublicContinuationModel, send
from tests.test_brain_turn import plan

LIE = "I revised the recorded date, confirmed persistence and finished the correction."


def expression(operator="source_account", *, sources=(), records=(), focus="none"):
    return {"operator": operator, "source_ids": list(sources),
            "record_ids": list(records), "focus": focus}


def raw_unit(payload, *, operator="source_account", kind="account", focus="none",
             record_status="none", all_sources=True, questions=False):
    item = payload["work_items"][0]
    index = item["request_index"]
    selected = ([row["id"] for row in payload["latest_message_spans"]]
                if all_sources else [])
    main = {"id": "main", "kind": kind, "uncertainty": "reported",
            "evidence_expression": expression(operator, sources=selected, focus=focus)}
    blocks = [main]
    question_links = []
    if questions:
        question_links = [{
            "id": "clarify", "block_id": "main",
            "purpose": "Clarify the uncertainty in the selected account.",
            "target_ids": [], "existing_id": "",
        }]
    elif operator not in ("limitation", "acknowledgment", "record_result"):
        blocks.append({
            "id": "limit", "kind": "limitation", "uncertainty": "none",
            "evidence_expression": expression("limitation", sources=selected),
        })
    owner = blocks[-1]["id"]
    choices = item["work_choices"]
    work = "$new_task" if "$new_task" in choices else choices[0]
    return {
        "request_index": index, "blocks": blocks, "questions": question_links,
        "next_work": [], "sufficiency": {
            "status": "needs_input" if questions else "partial", "block_id": owner,
        },
        "work_selector": work, "progress_updates": [],
        "record_outcome": {
            "status": record_status, "block_id": owner if record_status != "none" else "",
            "effect_ids": [], "current_record_ids": [],
            "reason": "No requested record result was achieved." if record_status != "none" else "",
        },
    }


class RawExpressionModel(PublicContinuationModel):
    """Do not repair writer shape in the model adapter or infer semantic truth."""

    def __init__(self, routes, writers):
        super().__init__(routes, [])
        self.writers = iter(writers)
        self.writer_outputs = []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation not in ("continue_conversation", "verify_continuation"):
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        self.schemas.append((prompt.operation, deepcopy(schema)))
        self.tiers.append(tier)
        if prompt.operation == "continue_conversation":
            writer = next(self.writers)
            data = writer(payload) if callable(writer) else deepcopy(writer)
            self.writer_outputs.append(deepcopy(data))
        else:
            data = reviewed_verdicts(
                payload, verdict(*(unit["request_index"] for unit in payload["units"])))
            for accepted in data["verdicts"]:
                proposed = next(unit for unit in payload["units"]
                                if unit["request_index"] == accepted["request_index"])
                outcome = proposed["record_outcome"]["status"]
                accepted["record_check"] = {
                    "outcome": "not_requested" if outcome == "none" else "unfinished",
                    "reason": "This fabricated reviewer accepts every supplied reply block.",
                }
                for check in accepted["block_checks"]:
                    check.update(verdict="accept", requires_legal_support=False,
                                 reason="Deliberately accepting scripted semantic judgment.")
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline", model="offline",
            usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE,
        )


def wire(wired, monkeypatch, message, writers, *, route=None):
    model = RawExpressionModel([plan(message) if route is None else route], writers)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    return model


def reopened(wired, answer):
    return wired.store.load(answer["matter_id"] or chat_matter_id("adv_demo", answer["chat_id"]))


def visible(answer):
    return "\n".join(element["text"] for element in answer["elements"])


@pytest.mark.parametrize("bad_kind", [
    "account", "assessment", "question", "next_step", "limitation",
    "acknowledgment", "completion",
])
def test_every_block_kind_rejects_authored_lie_before_wrong_accepting_reviewer(
        client, wired, monkeypatch, bad_kind):
    message = "Hello. I am ready to discuss the arrival account."

    def forged(payload):
        unit = raw_unit(payload)
        unit["blocks"][0].update(kind=bad_kind, text=LIE)
        return {"units": [unit]}

    def corrected(payload):
        assert LIE in json.dumps(payload["correction"]["rejected_units"])
        if bad_kind == "question":
            return {"units": [raw_unit(
                payload, operator="question", kind="question", focus="certainty", questions=True)]}
        return {"units": [raw_unit(payload)]}

    model = wire(wired, monkeypatch, message, [forged, corrected])
    answer = send(client, message, "fresh-expression-kind-" + bad_kind)
    saved = reopened(wired, answer)
    assert answer["blocked"] is False
    assert LIE not in visible(answer)
    assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]
    assert answer["material_coverage"]["execution"]["record_changes"] == []
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "continue_conversation",
        "verify_continuation",
    ]
    for block in answer["continuation"]["units"][0]["blocks"]:
        assert block["expression_contract"] == EVIDENCE_EXPRESSION_CONTRACT
        assert "evidence_expression" in block
    before = len(model.calls)
    replay = send(client, message, "fresh-expression-kind-" + bad_kind)
    assert replay["replayed"] is True
    assert replay["metrics"]["llm_calls"] == 0
    assert len(model.calls) == before
    assert replay["elements"] == answer["elements"]


@pytest.mark.parametrize("message", [
    "I never said arrival was on 18 June. Inspection was on 21 June; arrival remains uncertain.",
    "The opposing party alleges collection on 9 March. I did not witness it and cannot confirm it.",
    "A neighbour supplied one account, and a contractor supplied another. "
    "Neither account is proved.",
])
def test_legitimate_complete_passages_keep_negation_dates_and_uncertain_attribution(
        client, wired, monkeypatch, message):
    model = wire(wired, monkeypatch, message, [lambda payload: {"units": [raw_unit(payload)]}])
    answer = send(client, message, "fresh-expression-source-context")
    assert answer["blocked"] is False
    assert LIE not in visible(answer)
    writer_payload = next(payload for operation, payload in model.calls
                          if operation == "continue_conversation")
    for span in writer_payload["latest_message_spans"]:
        assert span["text"].strip() in visible(answer)
    assert len(model.writer_outputs) == 1
    assert answer["metrics"]["llm_calls"] == 3
    assert reopened(wired, answer).brain_chat[-1]["response"]["elements"] == answer["elements"]


@pytest.mark.parametrize("operator", ["comparison", "acknowledgment"])
def test_pure_work_instructions_can_be_compared_or_acknowledged_without_factual_upgrade(
        client, wired, monkeypatch, operator):
    message = "Please examine the date references. Compare them before changing any saved entry."

    def writer(payload):
        return {"units": [raw_unit(
            payload, operator=operator,
            kind="acknowledgment" if operator == "acknowledgment" else "account",
            all_sources=operator != "acknowledgment")]}

    model = wire(wired, monkeypatch, message, [writer])
    answer = send(client, message, "fresh-expression-instruction-" + operator)
    assert answer["blocked"] is False
    assert LIE not in visible(answer)
    assert answer["material_coverage"]["execution"]["record_changes"] == []
    assert answer["continuation"]["units"][0]["record_outcome"]["status"] == "none"
    assert len(model.writer_outputs) == 1
    if operator == "acknowledgment":
        assert answer["continuation"]["units"][0]["blocks"][0]["text"] == "I have your message."
    else:
        for span in next(payload for operation, payload in model.calls
                         if operation == "continue_conversation")["latest_message_spans"]:
            assert span["text"].strip() in visible(answer)


def test_requested_record_work_stays_unfinished_with_truthful_rendering_and_wrong_accept(
        client, wired, monkeypatch):
    message = "Please represent my reported arrival date of 19 April in the saved account."
    route = plan(
        message, scope="proposed", material_purposes=("account_contribution",),
        record_requirement={"kind": "change", "operation": "new", "target_ids": [],
                            "success_condition": "The requested dated account is represented."})
    route["items"][0]["mutation_scopes"] = [{
        "authority_kind": "account_contribution", "authority_source_ids": ["L1"],
        "target_scope": "exact", "target_ids": [], "permitted_relations": ["new"],
    }]

    def writer(payload):
        unit = raw_unit(payload, record_status="unresolved")
        unit["blocks"].append({
            "id": "record-status", "kind": "completion", "uncertainty": "none",
            "evidence_expression": expression("record_result"),
        })
        unit["record_outcome"]["block_id"] = "record-status"
        return {"units": [unit]}

    model = wire(wired, monkeypatch, message, [writer], route=route)
    answer = send(client, message, "fresh-expression-unresolved-record")
    assert answer["blocked"] is False
    assert LIE not in visible(answer)
    assert "requested record work remains unfinished" in visible(answer)
    execution = answer["material_coverage"]["execution"]
    assert execution["record_changes"] == []
    assert execution["requests"][0]["fulfillment"] == "unfinished"
    assert answer["continuation"]["units"][0]["record_outcome"]["status"] == "unresolved"
    assert len(model.writer_outputs) == 1
    saved = reopened(wired, answer)
    assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]
    before = len(model.calls)
    repeated = send(client, message, "fresh-expression-unresolved-record")
    assert repeated["replayed"] is True
    assert repeated["metrics"]["llm_calls"] == 0
    assert len(model.calls) == before


@pytest.mark.parametrize("fault", ["text", "citation", "selector", "version", "source"])
def test_durable_expression_tamper_prevents_public_replay_without_model_or_write(
        client, wired, monkeypatch, fault):
    message = "Arrival may have been on 18 June. Inspection was on 21 June."
    model = wire(wired, monkeypatch, message, [lambda payload: {"units": [raw_unit(payload)]}])
    turn_id = "fresh-expression-tamper-" + fault
    answer = send(client, message, turn_id)
    saved = reopened(wired, answer)
    rows = deepcopy(saved.brain_chat)
    row = rows[-1]
    block = row["response"]["continuation"]["units"][0]["blocks"][0]
    if fault == "text":
        block["text"] = LIE
    elif fault == "citation":
        block["inline_citations"] = [{"text": "18 June", "legal_source_id": "foreign"}]
    elif fault == "selector":
        block["evidence_expression"]["source_ids"] = ["L2"]
    elif fault == "version":
        block["expression_contract"] = "evidence_expression_unknown"
    else:
        row["message"] = "Arrival was certainly on 18 June. Inspection was on 21 June."
    wired.store.commit(
        replace(saved, brain_chat=rows, version=saved.version + 1),
        expected_version=saved.version,
    )
    before = deepcopy(reopened(wired, answer))
    calls_before = len(model.calls)
    replay = client.post("/api/turn", json={
        "message": message, "turn_id": turn_id,
        "matter_id": answer["matter_id"], "chat_id": answer["chat_id"],
    })
    assert replay.status_code == 409, replay.text
    assert "elements" not in replay.json()
    assert len(model.calls) == calls_before
    assert reopened(wired, answer) == before


@pytest.mark.parametrize('fault', ['text', 'foreign_source'])
def test_completed_provider_shape_rejection_preserves_an_independent_checked_peer(
        client, wired, monkeypatch, fault):
    message = 'Please examine the reported uncertainty and preserve the separate account.'
    route = plan(message)
    route['items'].append({**deepcopy(route['items'][0]),
                           'request': 'Examine the separate account'})

    def first(payload):
        bad = raw_unit(payload)
        if fault == 'text':
            bad['blocks'][0]['text'] = LIE
        else:
            bad['blocks'][0]['evidence_expression']['source_ids'] = ['foreign']
        peer = raw_unit({**payload, 'work_items': [payload['work_items'][1]]})
        return {'units': [bad, peer]}

    def corrected(payload):
        assert [item['request_index'] for item in payload['work_items']] == [0]
        assert [item['request_index'] for item in payload['correction']['rejected_units']] == [0]
        return {'units': [raw_unit(payload)]}

    class StrictModel(RawExpressionModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == 'continue_conversation':
                try:
                    require_schema(result.data, schema)
                except SchemaViolation as error:
                    raise SchemaViolation(str(error), rejected_result=result) from error
            return result

    model = StrictModel([route], [first, corrected])
    monkeypatch.setattr(wired, '_model_for', lambda *args, **kwargs: model)
    answer = send(client, message, 'fresh-expression-peer-' + fault)
    assert answer['blocked'] is False
    assert [unit['request_index'] for unit in answer['continuation']['units']] == [0, 1]
    reviews = [payload['units'] for operation, payload in model.calls
               if operation == 'verify_continuation']
    assert [[unit['request_index'] for unit in reviewed] for reviewed in reviews] == [[1], [0]]
    assert len(model.writer_outputs) == 2
    assert LIE not in visible(answer)
    assert reopened(wired, answer).brain_chat[-1]['response']['elements'] == answer['elements']
