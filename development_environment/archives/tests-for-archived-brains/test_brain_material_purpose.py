"""Declared material purposes drive checked extraction through the public boundary.

These tests script meaning and reviewer judgments. They establish routing,
owned source/target handoffs, saving and bounded recovery, not model quality
or independent coverage of an empty extraction result.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.brain_continuation_fixture import no_record_requirement
from tests.brain_reader_fixture import scripted_support_spans
from tests.test_brain_material import (
    Model,
    fixture_scope_judgment,
    material,
    mutation_scope,
    plan,
    send,
)


def item(request, reply, *, purposes=(), intent="request", opening=False,
         record_requirement=None):
    return {
        "request": request, "reply": reply, "clarification": "",
        "relation": "new" if opening else "continues",
        "matter_scope": "proposed" if opening else "current",
        "priority": "ordinary", "next_step": "answer", "intent": intent,
        "response_basis": "conversation_record", "research_question": "",
        "material_purposes": list(purposes),
        "record_requirement": (no_record_requirement() if record_requirement is None
                               else record_requirement),
    }


def routed(message, *, items, candidates=(), opening=False, record_disposition=None,
           source_purposes=None):
    result = plan(message, items=items, candidates=candidates, opening=opening,
                  record_disposition=record_disposition, source_purposes=source_purposes)
    # These cases deliberately supply no independent turn-wide routing switch.
    result.pop("material_review", None)
    if opening:
        result["opening"].update(subject="Reported freight custody", summary=message)
    return result


def seed_plan(account):
    candidate = material("circumstance", account, account, placement="matter")
    return routed(account, candidates=[candidate], opening=True, items=[
        item(account, account, purposes=("account_contribution",),
             intent="contribution", opening=True),
    ])


class PurposeModel(Model):
    def __init__(self, plans, *, review_authority_only=False, malformed_purpose=None):
        plans = list(plans)
        if review_authority_only:
            # These cases independently declare that follow-up review requests
            # supply authority, while only the original account supplies facts.
            from nm.brain.material import addressed_sources

            for planned in plans[1:]:
                for request in planned["items"]:
                    _, spans, _ = addressed_sources((), request["request"])
                    planned.setdefault("_source_purposes", {}).update(
                        {words.strip(): "non_account" for words in spans.values()})
        super().__init__(plans)
        self.seen = []
        self.review_authority_only = review_authority_only
        self.malformed_purpose = malformed_purpose

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.seen.append((prompt.operation, deepcopy(payload)))
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        data = deepcopy(result.data)
        if len(self.calls) > 1 and prompt.operation == "interpret_conversation":
            if self.malformed_purpose == "missing":
                data["items"][0].pop("material_purposes", None)
            elif self.malformed_purpose == "unknown":
                data["items"][0]["material_purposes"] = ["unsupported_purpose"]
        if len(self.calls) > 1 and self.review_authority_only:
            if prompt.operation == "verify_material_grounding":
                candidates = {row["candidate_id"]: row for row in payload["candidates"]}
                for verdict in data["verdicts"]:
                    sources = [identity for identity in candidates[
                        verdict["candidate_id"]]["allowed_account_source_ids"]
                               if identity.startswith("P")]
                    verdict["account_check"]["source_ids"] = sources
                    verdict["account_check"]["source_checks"] = [{
                        "source_id": identity, "supplies_account_content": True,
                        "supports_proposal": True,
                        "reason": "The earlier advocate account supplies this content.",
                    } for identity in sources]
                data = scripted_support_spans(payload, data, scripted_source_account=True)
                data["coverage"] = fixture_scope_judgment(
                    payload, data, source_purposes=self.source_purposes)
        return replace(result, data=data)


def operations(response):
    return [row["operation"] for row in response["metrics"]["model_calls"]]


def public_record(client, matter_id):
    response = client.get(f"/api/matters/{matter_id}")
    assert response.status_code == 200, response.text
    return response.json()["material_record"]


def open_account(client, wired, monkeypatch, model, account, *, turn_id="custody-original"):
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    response = send(client, account, turn_id)
    assert response.status_code == 200, response.text
    return response.json()


def test_answer_account_purpose_saves_correction_and_replays_without_duplicate_work(
        client, wired, monkeypatch):
    account = "The freight was delivered on 11 August."
    correction = "Correction: the freight was delivered on 12 August."
    changed = material(
        "event", "The freight was delivered on 12 August.", correction,
        relation="corrects", scope="current", placement="matter",
        references=({"turn_id": "custody-original", "role": "advocate",
                     "quoted": account},),
        related_material_ids=("custody-original:material:1",))
    followup = routed(correction, candidates=[changed], record_disposition="performed", items=[
        item(correction, "Your corrected account reports delivery on 12 August.",
             purposes=("account_contribution",), intent="contribution"),
    ])
    followup["items"][0]["mutation_scopes"] = [mutation_scope("custody-original:material:1")]
    model = PurposeModel([seed_plan(account), followup])
    opened = open_account(client, wired, monkeypatch, model, account)
    original_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])

    response = send(client, correction, "custody-corrected", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert operations(result) == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "continue_conversation", "verify_continuation"]
    assert result["metrics"]["llm_calls"] == 8
    record = public_record(client, opened["matter_id"])
    assert [(row["id"], row["statement"]) for row in record["rows"]] == [
        ("custody-corrected:material:1", changed["statement"])]
    assert record["rows"][0]["related_material_ids"] == ["custody-original:material:1"]
    assert len(record["history"]) == 2
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[0] == original_turn
    assert [row["message"] for row in saved.brain_chat] == [account, correction]
    assert saved.brain_chat[-1]["elements"] == result["elements"]
    call_count = len(model.seen)

    replay = send(client, correction, "custody-corrected", opened=opened)

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert len(model.seen) == call_count
    assert public_record(client, opened["matter_id"]) == record


def test_interpretation_review_repairs_from_prior_account_without_new_account_facts(
        client, wired, monkeypatch):
    account = "The freight is held at the depot by someone whose identity I do not know."
    request = "Reconcile your description with my earlier account and retain its uncertainty."
    initial = material("circumstance", "The freight is held at the depot.", account,
                       placement="matter")
    seed = routed(account, candidates=[initial], opening=True, items=[
        item(account, account, purposes=("account_contribution",),
             intent="contribution", opening=True),
    ])
    revised = material(
        "circumstance", "The freight is held at the depot; its custodian is unidentified.",
        request, relation="corrects", scope="current", placement="matter",
        references=({"turn_id": "custody-original", "role": "advocate",
                     "quoted": account},),
        related_material_ids=("custody-original:material:1",))
    repair = routed(request, candidates=[revised], record_disposition="performed", items=[
        item(request, revised["statement"], purposes=("interpretation_review",),
             record_requirement={
                 "kind": "change",
                 "target_ids": ["custody-original:material:1"],
                 "operation": "corrects",
                 "success_condition": (
                     "The saved custody description retains the original "
                     "unidentified custodian."
                 ),
             }),
    ])
    model = PurposeModel([seed, repair], review_authority_only=True)
    opened = open_account(client, wired, monkeypatch, model, account)
    original_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])

    response = send(client, request, "custody-review", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["llm_calls"] == 8
    assert "extract_legal_details" in operations(result)
    reader = next(payload for operation, payload in reversed(model.seen)
                  if operation == "extract_legal_details")
    assert reader["source_treatments"]["L1"]["content_role"] == "work_instruction"
    assert reader["source_treatments"]["P1S1"]["content_role"] == "reported_matter_account"
    assert reader["earlier_conversation"][0]["source_spans"][0]["text"] == account
    saved_row = public_record(client, opened["matter_id"])["rows"][0]
    assert saved_row["statement"] == revised["statement"]
    assert saved_row["quoted"] == request
    assert saved_row["prior_references"] == [{
        "turn_id": "custody-original", "role": "advocate", "quoted": account}]
    assert saved_row["related_material_ids"] == ["custody-original:material:1"]
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[0] == original_turn
    assert saved.facts == ()


def test_read_only_recap_preserves_record_without_unnecessary_extraction(
        client, wired, monkeypatch):
    account = "The freight is held at the depot."
    request = "Repeat the custody location in my saved account."
    recap = routed(request, items=[item(request, account)])
    recap["_response_expressions"] = {0: {
        "operator": "source_account", "source_ids": [],
        "record_ids": ["custody-original:material:1"], "focus": "none",
    }}
    model = PurposeModel([seed_plan(account), recap])
    opened = open_account(client, wired, monkeypatch, model, account)
    before = public_record(client, opened["matter_id"])
    reader_count = len(model.material_calls)

    response = send(client, request, "custody-recap", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert operations(result) == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    assert result["metrics"]["llm_calls"] == 3
    assert result["material"] == []
    assert account in "\n".join(row["text"] for row in result["elements"])
    assert len(model.material_calls) == reader_count
    assert public_record(client, opened["matter_id"]) == before


def test_authorised_review_without_new_rows_preserves_existing_material(
        client, wired, monkeypatch):
    account = "The freight is held at the depot."
    request = "Check your custody description against my saved account."
    review = routed(request, record_disposition="review_no_change", items=[
        item(request, "The saved description reports custody at the depot.",
             purposes=("interpretation_review",),
             record_requirement={
                 "kind": "review",
                 "target_ids": ["custody-original:material:1"],
                 "operation": "none",
                 "success_condition": (
                     "The saved custody description faithfully reports the "
                     "depot location."
                 ),
             }),
    ])
    model = PurposeModel([seed_plan(account), review], review_authority_only=True)
    opened = open_account(client, wired, monkeypatch, model, account)
    before = public_record(client, opened["matter_id"])

    response = send(client, request, "custody-no-change", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert operations(result) == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "continue_conversation", "verify_continuation"]
    assert result["metrics"]["llm_calls"] == 8
    assert result["material"] == []
    assert public_record(client, opened["matter_id"]) == before
    assert wired.store.load(opened["matter_id"]).brain_chat[-1]["message"] == request


def test_mixed_requests_keep_independent_responses_and_one_material_pass(
        client, wired, monkeypatch):
    account = "The freight is held at the depot."
    update = "The custodian is unidentified."
    recap = "Repeat the recorded custody location."
    ambiguity = "Review the effect of the earlier notice."
    message = f"{update} {recap} {ambiguity}"
    candidate = material("circumstance", update, update, scope="current", placement="matter")
    clarification = item(ambiguity, "")
    clarification.update(next_step="clarify", clarification="Which earlier notice do you mean?")
    mixed = routed(message, candidates=[candidate],
                   source_purposes={recap: "non_account", ambiguity: "non_account"}, items=[
        item(update, update, purposes=("account_contribution",), intent="contribution"),
        item(recap, account), clarification,
    ])
    mixed["_response_expressions"] = {
        0: {"operator": "source_account", "source_ids": ["L1"],
            "record_ids": [], "focus": "none"},
        1: {"operator": "source_account", "source_ids": [],
            "record_ids": ["custody-original:material:1"], "focus": "none"},
        2: {"operator": "question", "source_ids": ["L3"],
            "record_ids": [], "focus": "meaning"},
    }
    model = PurposeModel([seed_plan(account), mixed])
    opened = open_account(client, wired, monkeypatch, model, account)

    response = send(client, message, "custody-mixed", opened=opened)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["llm_calls"] == 8
    assert operations(result).count("extract_legal_details") == 1
    units = result["continuation"]["units"]
    assert [unit["request_index"] for unit in units] == [0, 1, 2]
    assert [unit["sufficiency"]["status"] for unit in units] == [
        "complete", "complete", "needs_input"]
    text = "\n".join(row["text"] for row in result["elements"])
    assert all(expected in text for expected in (update, account, ambiguity))
    question, = [block for block in units[2]["blocks"] if block["kind"] == "question"]
    assert units[2]["questions"][0]["block_id"] == question["id"]
    assert question["evidence_expression"]["source_ids"] == ["L3"]
    record = public_record(client, opened["matter_id"])
    assert [row["statement"] for row in record["rows"]] == [account, update]
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[-1]["message"] == message
    assert saved.brain_chat[-1]["elements"] == result["elements"]


@pytest.mark.parametrize("malformed_purpose", ["missing", "unknown"])
def test_invalid_material_purpose_exhausts_one_repair_without_saving_or_losing_history(
        client, wired, monkeypatch, malformed_purpose):
    account = "The freight is held at the depot."
    request = "Correct the custody date in the saved account."
    update = routed(request, items=[
        item(request, "The requested change remains unsupported.",
             purposes=("account_contribution",),
             record_requirement={
                 "kind": "change",
                 "target_ids": ["custody-original:material:1"],
                 "operation": "corrects",
                 "success_condition": (
                     "The requested custody-date correction has sourced "
                     "support and retains any uncertainty."
                 ),
             }),
    ])
    model = PurposeModel([seed_plan(account), update, update],
                         malformed_purpose=malformed_purpose)
    opened = open_account(client, wired, monkeypatch, model, account)
    before = deepcopy(wired.store.load(opened["matter_id"]))
    call_start = len(model.seen)

    response = send(client, request, "custody-invalid-purpose", opened=opened)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["committed"] == "not_committed"
    attempts = model.seen[call_start:]
    assert [operation for operation, _ in attempts] == [
        "interpret_conversation", "interpret_conversation"]
    assert "material_purposes" in attempts[-1][1]["validation_issue"]
    after = wired.store.load(opened["matter_id"])
    assert after.version == before.version
    assert after.brain_chat == before.brain_chat
    assert public_record(client, opened["matter_id"])["rows"][0]["statement"] == account
