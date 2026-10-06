"""The new chat owns its first message and the transition to a matter."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.turn import BrainRefused, BrainService, BrainTurn, chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ConfigurationError,
    ModelResult,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    Usage,
)
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter
from nm.work_the_file.projections_api import matter_list_projection
from tests.brain_continuation_fixture import (
    continuation_reply,
    interpretation,
    no_record_requirement,
)
from tests.brain_reader_fixture import reader_operations, reviewed_record_verdicts


class Model:
    provider = "scripted"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.all_calls = []
        self.current_items = []

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 20000

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.all_calls.append(prompt.operation)
        continuation = continuation_reply(prompt.operation, json.loads(prompt.user),
                                          scripted_items=self.current_items)
        if continuation is not None:
            data = continuation
        elif prompt.operation == "extract_disputes":
            data = {"new_items": [], "changes": []}
        elif prompt.operation == "extract_legal_details":
            data = {"new_items": [], "changes": []}
        elif prompt.operation == "verify_disputes":
            payload = json.loads(prompt.user)
            assert payload["candidates"] == [], "This fixture owns empty dispute review only"
            data = {"verdicts": []}
        elif prompt.operation == "verify_material_grounding":
            payload = json.loads(prompt.user)
            data = {"verdicts": [
                {"candidate_id": row["candidate_id"], "verdict": "accept",
                 "operation_supported": True,
                 "reason": "The proposal is attributable."}
                for row in payload["candidates"]]}
        else:
            data = next(self.replies)
            self.calls.append(json.loads(prompt.user))
            if prompt.operation == "interpret_conversation":
                data = interpretation(data)
                self.current_items = data["items"]
        if prompt.operation in ("verify_disputes", "verify_material_grounding"):
            data = reviewed_record_verdicts(
                json.loads(prompt.user), data, scripted_full_scope=True)
        return ModelResult(text=None, data=data, tier=tier,
                           provider="offline", model="offline", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def plan(quote, *, scope="none", step="answer", reply="Hello.",
         relation="new", title="", summary="", material_purposes=(), record_requirement=None):
    party_name, separator, subject = title.partition(":")
    return {"items": [{"request": quote, "relation": relation,
                       "matter_scope": scope, "priority": "ordinary",
                       "next_step": step,
                       "reply": reply if step in ("answer", "legal_work") else "",
                       "clarification": "", "material_purposes": list(material_purposes),
                       "record_requirement": (no_record_requirement() if record_requirement is None
                                              else deepcopy(record_requirement))}],
            "active_work_after": quote if step == "legal_work" else "",
            "opening": {"ready": bool(title),
                        "party_name": party_name if separator else "",
                        "subject": subject.strip() if separator else title,
                        "summary": summary,
                        }}


def service(tmp_path, replies):
    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    model = Model(replies)
    return BrainService(store, model), store, model


@pytest.mark.parametrize("damage", ["advocate_id", "matter_id", "committed", "release_state",
                                   "elements", "checked_text", "inline_owner"])
def test_replay_checks_saved_release_ownership_and_display_identity(tmp_path, monkeypatch, damage):
    brain, store, model = service(tmp_path, [plan("Hello")])
    request = BrainTurn("adv", "Hello", "replay-integrity")
    first = brain.run(request).as_dict()
    matter_id = chat_matter_id("adv", "replay-integrity")
    damaged = deepcopy(store.load(matter_id))
    row = damaged.brain_chat[0]
    if damage in ("advocate_id", "matter_id"):
        row[damage] = "foreign-owner"
    elif damage == "committed":
        row[damage] = False
    elif damage == "release_state":
        row[damage] = "withheld"
    elif damage == "elements":
        row["elements"][0]["text"] = "Unreviewed changed reply."
    elif damage == "checked_text":
        row["response"]["continuation"]["units"][0]["blocks"][0]["text"] = "Changed draft."
    else:
        row["elements"][0]["inline_citations"] = [
            {"text": "Hello", "source_id": "foreign", "source_index": 0}]
        row["response"]["elements"] = deepcopy(row["elements"])
    calls = len(model.all_calls)
    monkeypatch.setattr(store, "load", lambda _: damaged)
    with pytest.raises(BrainRefused) as refused:
        brain.run(request)
    assert refused.value.status == 409
    assert len(model.all_calls) == calls
    assert first["committed"] == "committed"


def test_first_greeting_stays_chat_and_later_concrete_message_opens_board(tmp_path):
    text = "My client has a dispute about a terminated supply agreement."
    brain, store, model = service(tmp_path, [
        plan("Hello"),
        plan(text, scope="proposed", step="legal_work",
             reply=("I understand the supply agreement is in dispute. I will "
                    "check the agreement and the relevant terms before giving "
                    "a legal view."),
             title="Supply agreement dispute", summary="The agreement was terminated.",
             material_purposes=("account_contribution",)),
    ])
    first = BrainTurn("adv", "Hello", "turn-one", offer={"message": "Hello"})
    greeting = brain.run(first).as_dict()
    assert greeting["matter_id"] is None
    assert greeting["chat_id"] == "turn-one"
    assert greeting["metrics"]["llm_calls"] == 3
    assert len(model.calls) == 1
    assert model.calls[0]["earlier_conversation"] == []
    assert matter_list_projection(store.list_for("adv"), registers={})["matters"] == []

    second = BrainTurn("adv", text, "turn-two", chat_id=greeting["chat_id"],
                       offer={"message": text, "chat_id": greeting["chat_id"]})
    opened = brain.run(second).as_dict()
    assert opened["matter_id"] == chat_matter_id("adv", "turn-one")
    assert len(model.calls) == 2
    assert model.all_calls[:4] == [
        "interpret_conversation", "continue_conversation", "verify_continuation",
        "interpret_conversation"]
    assert set(model.all_calls[4:]) == {
        "classify_account_sources", "extract_disputes", "verify_disputes", "extract_legal_details",
        "verify_material_grounding",
        "continue_conversation", "verify_continuation"}
    assert opened["metrics"]["llm_calls"] == 8
    assert [row["text"] for row in model.calls[1]["earlier_conversation"]] == [
        "Hello", "Hello.\nNo changes were made to the saved record."]
    matter = store.load(opened["matter_id"])
    assert matter.brain_ready is True
    assert [row["message"] for row in matter.brain_chat] == ["Hello", text]
    assert len(matter_list_projection(store.list_for("adv"), registers={})["matters"]) == 1
    assert opened["elements"][0]["text"] == (
        "I understand the supply agreement is in dispute. I will "
        "check the agreement and the relevant terms before giving a legal view.")
    assert opened["blocked"] is False
    assert opened["continuation"]["units"][0]["sufficiency"]["status"] == "not_completed"


def test_first_substantive_message_uses_seven_calls_and_exact_replay_uses_none(tmp_path):
    text = "Our client disputes the invoice issued on 3 March."
    brain, store, model = service(tmp_path, [
        plan(text, scope="proposed", step="legal_work",
             reply=("I will check the invoice and the underlying agreement "
                    "before giving a legal view."),
             title="Invoice dispute", summary="The client disputes an invoice.",
             material_purposes=("account_contribution",))])
    offered = BrainTurn("adv", text, "opening-id", offer={"message": text})
    first = brain.run(offered).as_dict()
    replayed = brain.run(offered).as_dict()
    assert first["matter_id"] == replayed["matter_id"]
    assert replayed["replayed"] is True
    assert replayed["metrics"]["llm_calls"] == 0
    assert len(model.calls) == 1
    assert model.all_calls[0] == "interpret_conversation"
    assert set(model.all_calls[1:]) == {
        "classify_account_sources", "extract_disputes", "verify_disputes", "extract_legal_details",
        "verify_material_grounding",
        "continue_conversation", "verify_continuation"}
    assert first["metrics"]["llm_calls"] == 8
    assert model.all_calls.count("classify_account_sources") == 1
    assert first["elements"][0]["text"] == (
        "I will check the invoice and the underlying agreement "
        "before giving a legal view.")
    assert len(store.load(first["matter_id"]).brain_chat) == 1


def test_multi_party_opening_repairs_only_heading_then_checks_it(tmp_path):
    text = ("Our clients Mira Patel and Om Rao report that opposing supplier "
            "Dev Shah retained their records after cancellation.")
    summary = "The clients report that the supplier retained their records."
    brain, store, model = service(tmp_path, [
        plan(text, scope="proposed", step="legal_work",
             reply="I will check the reported retention against the record.",
             title="Mira Patel and Om Rao vs Dev Shah: Return of records",
             summary=summary, material_purposes=("account_contribution",)),
        {"party_name": "Mira Patel", "subject": "Return of records",
         "summary": summary},
    ])

    result = brain.run(BrainTurn("adv", text, "opening-parties")).as_dict()

    assert store.load(result["matter_id"]).title == "Mira Patel: Return of records"
    assert result["material_coverage"]["opening_fallback"] is False
    assert result["metrics"]["llm_calls"] == 10
    assert model.all_calls.count("verify_material_grounding") == 2
    assert model.all_calls.count("repair_opening") == 1
    repair = model.calls[1]
    assert repair["latest_message"] == text
    assert repair["rejected_opening"]["title"].startswith("Mira Patel and Om Rao")


def test_verifier_rejection_can_repair_a_client_heading_without_losing_turn(tmp_path):
    class OpeningRejectedOnce(Model):
        def __init__(self, replies):
            super().__init__(replies)
            self.grounding_checks = 0

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if (prompt.operation == "verify_material_grounding"
                    and any(row["candidate_id"] == "O1"
                            for row in json.loads(prompt.user)["candidates"])):
                self.grounding_checks += 1
                if self.grounding_checks == 1:
                    rejected = {"verdicts": [
                        {"candidate_id": "O1", "verdict": "reject",
                         "operation_supported": False,
                         "reason": "A clearly named client was omitted."}]}
                    return replace(result, data=reviewed_record_verdicts(
                        json.loads(prompt.user), rejected, scripted_full_scope=True))
            return result

    text = "Our client Mira Patel says a supplier retained her records."
    summary = "The client reports that a supplier retained her records."
    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    model = OpeningRejectedOnce([
        plan(text, scope="proposed", step="legal_work",
             reply="I will check the reported retention against the record.",
             title="Records retention", summary=summary,
             material_purposes=("account_contribution",)),
        {"party_name": "Mira Patel", "subject": "Records retention",
         "summary": summary},
    ])
    brain = BrainService(store, model)

    result = brain.run(BrainTurn("adv", text, "repair-grounding")).as_dict()

    assert store.load(result["matter_id"]).title == "Mira Patel: Records retention"
    assert result["material_coverage"]["opening_fallback"] is False
    assert model.grounding_checks == 2
    assert model.calls[1]["validation_issue"] == (
        "A clearly named client was omitted.")
    assert model.calls[1]["rejected_opening"]["party_name"] == ""


def test_turn_metrics_separate_logical_calls_from_provider_retries(tmp_path):
    brain, _, model = service(tmp_path, [plan("Hello")])
    original = model.structured

    def with_provider_retries(*args, **kwargs):
        return replace(original(*args, **kwargs), retries=2)

    model.structured = with_provider_retries
    response = brain.run(BrainTurn("adv", "Hello", "retry-metrics")).as_dict()
    assert response["metrics"]["llm_calls"] == 3
    assert response["metrics"]["provider_retries"] == 6
    assert [row["operation"] for row in response["metrics"]["model_calls"]] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]


@pytest.mark.parametrize("usage", [None, Usage(21, 8, 0.002)])
def test_rejected_model_output_preserves_measured_usage_without_inventing_zero_cost(usage):
    from nm.brain.turn import _CountedModel
    from nm.shared.model_port import Prompt

    class FailingModel:
        def structured(self, *args, **kwargs):
            raise SchemaViolation("Rejected result", usage=usage, retries=1)

    counted = _CountedModel(FailingModel())
    with pytest.raises(SchemaViolation):
        counted.structured(Prompt(user="Synthetic test", operation="review"), {}, Tier.JUDGE)
    receipt = counted.metrics()["model_calls"][0]
    assert receipt["usage_recorded"] is (usage is not None)
    assert receipt["cost_usd"] == (usage.cost_usd if usage else None)
    assert receipt["tokens_in"] == (usage.tokens_in if usage else 0)
    assert counted.metrics()["provider_retries"] == 1


def test_context_overflow_has_a_nonretryable_plain_recovery_path(tmp_path):
    brain, store, model = service(tmp_path, [plan("Hello")])
    model.context_budget = lambda tier: 100

    with pytest.raises(BrainRefused) as failure:
        brain.run(BrainTurn("adv", "Hello", "over-limit"))

    assert failure.value.status == 413
    assert failure.value.retryable is False
    assert "Please contact the administrator to increase its context capacity" in failure.value.why
    assert model.calls == []
    assert store.list_for("adv").matters == ()


@pytest.mark.parametrize(("failure", "said", "retryable"), [
    (ProviderUnavailable("private transport detail"),
     "AI analysis is temporarily unavailable", True),
    (ConfigurationError("private configuration detail"),
     "AI service is not configured", False),
    (SchemaViolation("private validation detail"),
     "could not validate the analysis", True),
])
def test_model_failure_names_the_recovery_without_exposing_internals(
        tmp_path, failure, said, retryable):
    brain, store, model = service(tmp_path, [])

    def failed(*args, **kwargs):
        raise failure

    model.structured = failed
    with pytest.raises(BrainRefused) as refused:
        brain.run(BrainTurn("adv", "Please help", "failed-turn"))

    assert refused.value.status == 503
    assert refused.value.committed == "not_committed"
    assert refused.value.retryable is retryable
    assert said in refused.value.why
    assert "private" not in refused.value.why
    assert store.list_for("adv").matters == ()


def test_unchecked_legal_draft_from_interpretation_is_not_released(tmp_path):
    latest = "The supplier missed delivery. Please assess our remedies."
    draft = plan(latest, scope="proposed", step="legal_work",
                 reply="I will check the delivery terms and record before assessing remedies.",
                 title="Delivery dispute", summary="The advocate reports late delivery.",
                 material_purposes=("account_contribution",))
    draft["items"].insert(0, {
        "request": "Assess the missed delivery", "relation": "new",
        "matter_scope": "proposed", "priority": "ordinary",
        "next_step": "legal_work", "reply": "The law guarantees damages today.",
        "clarification": "", "material_purposes": [],
     "record_requirement": no_record_requirement()})
    class IndependentCheck(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "verify_continuation":
                data = {"verdicts": [{
                    **row, "verdict": "reject" if row["request_index"] == 0 else "accept",
                    "reason": ("The legal guarantee lacks checked supporting sources."
                               if row["request_index"] == 0 else row["reason"]),
                } for row in result.data["verdicts"]]}
                return replace(result, data=data)
            return result

    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    model = IndependentCheck([draft])
    brain = BrainService(store, model)

    response = brain.run(BrainTurn("adv", latest, "unchecked-answer")).as_dict()

    visible = "\n\n".join(row["text"] for row in response["elements"])
    assert "guarantees damages" not in visible
    assert "I will check the delivery terms and record before assessing remedies." in visible
    assert all(unit["sufficiency"]["status"] == "not_completed"
               for unit in response["continuation"]["units"])
    assert response["metrics"]["llm_calls"] == 10
    assert [row["request_index"] for row in response["continuation"]["units"]] == [1]
    assert [row["state"] for row in response["continuation"]["coverage"]] == [
        "unavailable", "ok"]
    assert model.all_calls.count("continue_conversation") == 2
    assert model.all_calls.count("verify_continuation") == 2
    assert model.all_calls[0] == "interpret_conversation"
    assert set(model.all_calls[1:]) == {
        "classify_account_sources", "extract_disputes", "verify_disputes", "extract_legal_details",
        "verify_material_grounding",
        "continue_conversation", "verify_continuation"}


def test_chat_identity_and_changed_retry_cannot_cross_records(tmp_path):
    brain, store, model = service(tmp_path, [plan("Hello")])
    brain.run(BrainTurn("adv", "Hello", "one", offer={"message": "Hello"}))
    with pytest.raises(BrainRefused) as changed:
        brain.run(BrainTurn("adv", "Hello", "one", offer={"message": "different"}))
    assert changed.value.status == 409
    with pytest.raises(BrainRefused) as foreign:
        brain.run(BrainTurn("other", "Again", "two", chat_id="one"))
    assert foreign.value.status == 404
    assert len(model.calls) == 1


def test_existing_matter_refuses_a_missing_legacy_turn_before_model_dispatch(tmp_path):
    brain, store, model = service(tmp_path, [])
    legacy = Matter(id="mat_legacy", advocate_id="adv", title="Existing matter",
                    turns_applied=("earlier-turn",))
    store.commit(legacy, expected_version=0)
    with pytest.raises(BrainRefused) as refused:
        brain.run(BrainTurn("adv", "Please continue", "new-turn", matter_id=legacy.id))
    assert refused.value.status == 409
    assert model.calls == []


def test_existing_matter_keeps_its_identity_without_a_new_chat_id(tmp_path):
    brain, store, model = service(tmp_path, [plan("Hello"), plan("Again", reply="Hello again.")])
    existing = Matter(id="mat_existing", advocate_id="adv", title="Existing matter")
    store.commit(existing, expected_version=0)
    first = brain.run(BrainTurn("adv", "Hello", "one", matter_id=existing.id)).as_dict()
    second = brain.run(BrainTurn("adv", "Again", "two", matter_id=existing.id)).as_dict()
    assert first["chat_id"] is None and second["chat_id"] is None
    assert second["matter_id"] == existing.id
    assert len(model.calls) == 2


def test_a_diversion_preserves_the_full_matter_conversation_and_current_work(tmp_path):
    facts = "Our client disputes termination of a supply agreement."
    diversion = "What is the capital of France?"
    return_to_work = "Please return to the termination issue."
    opening = plan(facts, scope="proposed", step="legal_work",
                   reply="I will check the agreement terms and related material.",
                   title="Supply agreement termination", summary="The client disputes termination.",
                   material_purposes=("account_contribution",))
    aside = plan(diversion, relation="aside", scope="none", reply="Paris.")
    aside["active_work_after"] = facts
    continued = plan(return_to_work, relation="continues", scope="current",
                     step="legal_work", reply="I will continue checking the termination issue.")
    brain, _, model = service(tmp_path, [opening, aside, continued])
    first = brain.run(BrainTurn("adv", facts, "one")).as_dict()
    brain.run(BrainTurn("adv", diversion, "two", matter_id=first["matter_id"],
                       chat_id=first["chat_id"]))
    brain.run(BrainTurn("adv", return_to_work, "three", matter_id=first["matter_id"],
                       chat_id=first["chat_id"]))
    assert [row["text"] for row in model.calls[2]["earlier_conversation"]] == [
        facts, "\n".join(row["text"] for row in first["elements"]),
        diversion, "Paris.\nNo changes were made to the saved record."]
    assert model.calls[2]["current_work"] == facts


def test_legal_work_and_unrelated_aside_each_get_a_response(tmp_path):
    account = "My landlord withheld the deposit after I moved out."
    mixed = "Please assess recovery of the deposit; also, what is the capital of France?"
    legal_reply = ("I can assess deposit recovery after checking the agreement "
                   "and the stated reason for withholding it.")
    modelled_mixed = {
        "items": [
            {"request": "Assess recovery of the deposit", "relation": "continues",
             "matter_scope": "current", "priority": "ordinary",
             "next_step": "legal_work", "reply": legal_reply, "clarification": "",
             "material_purposes": [], "record_requirement": no_record_requirement()},
            {"request": "What is the capital of France?", "relation": "aside",
             "matter_scope": "none", "priority": "ordinary",
             "next_step": "answer", "reply": "Paris.", "clarification": "",
             "material_purposes": [], "record_requirement": no_record_requirement()},
        ],
        "active_work_after": "assess deposit recovery",
        "opening": {"ready": False, "party_name": "", "subject": "",
                    "summary": ""},
    }
    reported_account = plan(
        account, scope="proposed", step="legal_work",
        reply="I can review the deposit dispute once I have the agreement.",
        title="Deposit dispute", summary="The advocate reports a withheld deposit.",
                            material_purposes=("account_contribution",))
    reported_account["items"][0]["intent"] = "contribution"
    brain, _, model = service(tmp_path, [
        reported_account,
        modelled_mixed,
        plan("Please continue with the deposit review.", relation="continues",
             scope="current", step="legal_work",
             reply="I will continue reviewing the deposit and agreement."),
    ])
    opened = brain.run(BrainTurn("adv", account, "deposit-first")).as_dict()
    reply = brain.run(BrainTurn("adv", mixed, "deposit-mixed",
                                matter_id=opened["matter_id"],
                                chat_id=opened["chat_id"])).as_dict()
    assert [row["text"] for row in reply["elements"]] == [
        legal_reply, "Paris.", "No changes were made to the saved record."]
    assert reply["continuation"]["units"][0]["sufficiency"]["status"] == "not_completed"
    assert reply["metrics"]["llm_calls"] == 3

    brain.run(BrainTurn("adv", "Please continue with the deposit review.",
                        "deposit-continue", matter_id=opened["matter_id"],
                        chat_id=opened["chat_id"]))
    assert [row["text"] for row in model.calls[2]["earlier_conversation"]][-2:] == [
        mixed, "\n".join(row["text"] for row in reply["elements"])]
    assert model.calls[2]["current_work"] == "Assess recovery of the deposit"


def test_served_urgent_work_is_addressed_before_ordinary_work(client, wired,
                                                                monkeypatch):
    account = "Our client disputes termination of a supply agreement."
    latest = "A filing deadline is tomorrow. Please also review the draft response."
    urgent_reply = ("The reported deadline needs immediate attention. Please send "
                    "the order and exact deadline so I can check the filing requirement.")
    ordinary_reply = "I can review the draft response once I have its current version."
    urgent_plan = {
        "items": [
            {"request": "Review the draft response", "relation": "continues",
             "matter_scope": "current", "priority": "ordinary",
             "next_step": "legal_work", "reply": ordinary_reply, "clarification": "",
             "material_purposes": [], "record_requirement": no_record_requirement()},
            {"request": "Address the filing deadline", "relation": "continues",
             "matter_scope": "current", "priority": "urgent",
             "next_step": "legal_work", "reply": urgent_reply, "clarification": "",
             "material_purposes": ["account_contribution"],
             "record_requirement": no_record_requirement()},
        ],
        "active_work_after": "check deadline and review draft response",
        "opening": {"ready": False, "party_name": "", "subject": "",
                    "summary": ""},
    }
    model = Model([
        plan(account, scope="proposed", step="legal_work",
             reply="I will check the agreement and termination record.",
             title="Supply termination", summary="The client disputes termination.",
             material_purposes=("account_contribution",)),
        urgent_plan,
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = client.post("/api/turn", json={
        "message": account, "turn_id": "urgent-account"}).json()
    served = client.post("/api/turn", json={
        "message": latest, "turn_id": "urgent-followup",
        "matter_id": opened["matter_id"], "chat_id": opened["chat_id"]})

    assert served.status_code == 200, served.text
    response = served.json()
    assert [row["text"] for row in response["elements"]] == [
        urgent_reply, ordinary_reply, "No changes were made to the saved record."]
    assert all(unit["sufficiency"]["status"] == "not_completed"
               for unit in response["continuation"]["units"])
    assert response["metrics"]["llm_calls"] == 8


def test_served_factual_correction_keeps_its_direct_reply_and_source(
        client, wired, monkeypatch):
    account = "Our client contests the notice; the hearing is on Tuesday."
    correction = "Correction: the hearing is on Thursday, not Tuesday."
    direct_reply = ("You have corrected the hearing date to Thursday. "
                    "I will use that as provisional while checking the notice.")
    update = plan(correction, relation="continues", scope="current",
                  step="legal_work", reply=direct_reply)
    update["items"][0]["intent"] = "contribution"
    update["items"][0]["material_purposes"] = ["account_contribution"]

    class SourcedModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation != "extract_legal_details":
                return result
            payload = json.loads(prompt.user)
            payload = payload.get("original_input", payload)
            if not any("Correction:" in span["text"]
                       for span in payload["latest_message_spans"]):
                source_id = next(span["id"] for span in payload["latest_message_spans"]
                                 if "hearing is on Tuesday" in span["text"])
                return replace(result, data=reader_operations([{
                    "kind": "event", "statement": "The advocate reports a Tuesday hearing.",
                    "matter_scope": "proposed", "basis": "stated",
                    "importance": "central",
                    "why_material": "The hearing date affects the next step.",
                    "placement": "unresolved", "dispute_ids": [], "source_id": source_id,
                }], payload, link_field="related_material_ids"))
            earlier_id = next(
                span["id"] for message in payload["earlier_conversation"]
                if message["role"] == "advocate"
                for span in message["source_spans"]
                if "hearing is on Tuesday" in span["text"])
            return replace(result, data=reader_operations([{
                "kind": "event", "statement": "The advocate corrects the hearing date to Thursday.",
                "relation": "corrects", "matter_scope": "current",
                "basis": "stated", "importance": "central",
                "why_material": "The hearing date may affect the next step.",
                "placement": "unresolved", "dispute_ids": [],
                "related_material_ids": [],
                "source_id": payload["latest_message_spans"][0]["id"],
                "prior_source_ids": [earlier_id],
            }], payload, link_field="related_material_ids"))

    model = SourcedModel([
        plan(account, scope="proposed", step="legal_work",
             reply="I can review the notice and hearing schedule.",
             title="Notice dispute", summary="The client contests a notice.",
             material_purposes=("account_contribution",)),
        update,
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = client.post("/api/turn", json={
        "message": account, "turn_id": "correction-account"}).json()
    served = client.post("/api/turn", json={
        "message": correction, "turn_id": "correction-update",
        "matter_id": opened["matter_id"], "chat_id": opened["chat_id"]})

    assert served.status_code == 200, served.text
    response = served.json()
    assert response["elements"][0]["text"] == direct_reply
    assert response["blocked"] is False
    assert response["material"][0]["quoted"] == correction
    assert response["material"][0]["prior_references"][0]["quoted"] == (
        "the hearing is on Tuesday.")
    assert response["metrics"]["llm_calls"] == 8


def test_served_first_chat_stays_blank_until_matter_details_arrive(client, wired, monkeypatch):
    text = "Our client disputes the termination of a supply agreement."
    model = Model([
        plan("Hello"),
        plan(text, scope="proposed", step="legal_work",
             reply=("I will review the termination terms and the available "
                    "record before giving a legal view."),
             title="Supply agreement termination", summary="The client disputes termination.",
             material_purposes=("account_contribution",)),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = client.post("/api/turn", json={"message": "Hello", "turn_id": "first-chat"})
    assert first.status_code == 200, first.text
    greeting = first.json()
    assert greeting["matter_id"] is None
    assert greeting["elements"][0]["text"] == "Hello."
    assert client.get("/api/matters").json()["matters"] == []
    pending = client.get(f"/api/chats/{greeting['chat_id']}")
    assert pending.status_code == 200
    assert [row["message"] for row in pending.json()["turns"]] == ["Hello"]

    second = client.post("/api/turn", json={"message": text, "turn_id": "second-chat",
                                             "chat_id": greeting["chat_id"]})
    assert second.status_code == 200, second.text
    opened = second.json()
    assert opened["matter_id"]
    board = client.get(f"/api/matters/{opened['matter_id']}")
    assert board.status_code == 200, board.text
    assert board.json()["opening_summary"]["state"] == "provisional"
    transcript = client.get(f"/api/matters/{opened['matter_id']}/transcript")
    assert transcript.status_code == 200, transcript.text
    assert [row["message"] for row in transcript.json()["turns"]] == ["Hello", text]
    assert len(model.calls) == 2


def test_unattributed_detail_and_opening_are_withheld_without_losing_good_detail(
        tmp_path):
    latest = "We sent a notice. The supplier kept the drawings."
    drafted = plan(
        latest, scope="proposed", step="legal_work",
        reply="I will review the reported events.",
        title="Supplier admitted wrongdoing",
        summary="The supplier admitted wrongdoing and retained the drawings.",
                   material_purposes=("account_contribution",))

    class GroundingModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "repair_opening":
                raise SchemaViolation("No grounded opening correction is available")
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation == "extract_legal_details":
                spans = json.loads(prompt.user)["latest_message_spans"]
                return replace(result, data=reader_operations([
                    {"kind": "event", "statement": "We sent a notice.",
                     "relation": "new", "matter_scope": "proposed",
                     "basis": "stated", "importance": "relevant",
                     "why_material": "The notice may matter to the request.",
                     "placement": "unresolved", "dispute_ids": [],
                     "related_material_ids": [], "source_id": spans[0]["id"]},
                    {"kind": "event", "statement": "The supplier admitted wrongdoing.",
                     "relation": "new", "matter_scope": "proposed",
                     "basis": "stated", "importance": "central",
                     "why_material": "The admission would matter to the request.",
                     "placement": "unresolved", "dispute_ids": [],
                     "related_material_ids": [], "source_id": spans[1]["id"]},
                ], json.loads(prompt.user), link_field="related_material_ids"))
            if prompt.operation == "verify_material_grounding":
                return replace(result, data=reviewed_record_verdicts(json.loads(prompt.user), {
                    "verdicts": [
                    {"candidate_id": "D1", "verdict": "accept",
                     "operation_supported": True,
                     "reason": "The notice is reported."},
                    {"candidate_id": "D2", "verdict": "reject",
                     "operation_supported": False,
                     "reason": "No admission was reported."},
                    {"candidate_id": "O1", "verdict": "reject",
                     "operation_supported": False,
                     "reason": "The opening adds an admission."},
                ], "coverage": {
                    "state": "partial", "missing_source_ids": ["L2"],
                    "reason": ("The supplier's reported retention of the drawings remains "
                               "unrepresented after rejecting the invented admission."),
                }}, scripted_full_scope=True))
            return result

    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    model = GroundingModel([drafted])
    response = BrainService(store, model).run(
        BrainTurn("adv", latest, "grounding-turn")).as_dict()

    assert response["metrics"]["llm_calls"] == 10
    assert [row["statement"] for row in response["material"]] == [
        "We sent a notice."]
    assert {key: response["material_coverage"][key] for key in (
        "state", "rejected_details", "withheld_details", "unread_details", "opening_fallback")} == {
        "state": "partial", "rejected_details": 1, "withheld_details": 0,
        "unread_details": 0, "opening_fallback": True}
    assert len(response["material_coverage"]["rejected_proposals"]) == 1
    saved = store.load(response["matter_id"])
    assert saved.title == "Matter"
    assert "admitted" not in saved.brain_opening_summary
    assert "The record reading remains unfinished." in "\n".join(
        row["text"] for row in response["elements"])
    receipt = response["material_coverage"]["execution"]
    assessment = receipt["stages"]["detail_review"]["account_coverage"]
    assert assessment["state"] == "partial" and assessment["missing_source_ids"] == ["L2"]
    assert receipt["record_changes"][0]["after_record"]["statement"] == "We sent a notice."


def test_source_bound_legal_reply_preserves_distinct_clarification(tmp_path):
    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    matter = Matter(id="mat_clarification", advocate_id="adv",
                    title="Current matter", brain_ready=True)
    store.commit(matter, expected_version=0)
    mixed = {"items": [
        {"request": "Check the legal position", "relation": "continues",
         "matter_scope": "current", "priority": "ordinary",
         "next_step": "legal_work", "reply": "I will check the law.",
         "clarification": "", "material_purposes": [],
         "record_requirement": no_record_requirement()},
        {"request": "Identify the order", "relation": "uncertain",
         "matter_scope": "current", "priority": "ordinary",
         "next_step": "clarify", "reply": "",
         "clarification": "Which order do you mean?", "material_purposes": [],
         "record_requirement": no_record_requirement()},
    ], "active_work_after": "check legal position",
       "opening": {"ready": False, "party_name": "", "subject": "",
                   "summary": ""}}
    model = Model([mixed])
    response = BrainService(store, model, legal_search=object()).run(
        BrainTurn("adv", "Please check the law for that order.", "mixed-turn",
                  matter_id=matter.id)).as_dict()

    assert "Which order do you mean?" in "\n".join(
        row["text"] for row in response["elements"])
    assert any(unit["questions"] for unit in response["continuation"]["units"])
    assert response["metrics"]["llm_calls"] == 3
