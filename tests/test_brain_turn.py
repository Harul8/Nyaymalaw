"""The new chat owns its first message and the transition to a matter."""
import json
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


class Model:
    provider = "scripted"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.all_calls = []

    def context_budget(self, tier):
        return 20000

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.all_calls.append(prompt.operation)
        if prompt.operation == "extract_disputes":
            data = {"disputes": []}
        elif prompt.operation == "extract_legal_details":
            data = {"details": []}
        elif prompt.operation == "verify_material_grounding":
            payload = json.loads(prompt.user)
            data = {"verdicts": [
                {"candidate_id": row["candidate_id"], "verdict": "accept",
                 "reason": "The proposal is attributable."}
                for row in payload["candidates"]]}
        else:
            data = next(self.replies)
            self.calls.append(json.loads(prompt.user))
        return ModelResult(text=None, data=data, tier=Tier.ROUTINE,
                           provider="offline", model="offline", usage=Usage(0, 0, 0),
                           latency_ms=0, completion=Completion.COMPLETE)


def plan(quote, *, scope="none", step="answer", reply="Hello.",
         relation="new", title="", summary=""):
    party_name, separator, subject = title.partition(":")
    return {"items": [{"request": quote, "relation": relation,
                       "matter_scope": scope, "priority": "ordinary",
                       "next_step": step,
                       "reply": reply if step in ("answer", "legal_work") else "",
                       "clarification": ""}],
            "active_work_after": quote if step == "legal_work" else "",
            "material_review": bool(title),
            "opening": {"ready": bool(title),
                        "party_name": party_name if separator else "",
                        "subject": subject.strip() if separator else title,
                        "summary": summary,
                        }}


def service(tmp_path, replies):
    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    model = Model(replies)
    return BrainService(store, model), store, model


def test_first_greeting_stays_chat_and_later_concrete_message_opens_board(tmp_path):
    text = "My client has a dispute about a terminated supply agreement."
    brain, store, model = service(tmp_path, [
        plan("Hello"),
        plan(text, scope="proposed", step="legal_work",
             reply=("I understand the supply agreement is in dispute. I will "
                    "check the agreement and the relevant terms before giving "
                    "a legal view."),
             title="Supply agreement dispute", summary="The agreement was terminated."),
    ])
    first = BrainTurn("adv", "Hello", "turn-one", offer={"message": "Hello"})
    greeting = brain.run(first).as_dict()
    assert greeting["matter_id"] is None
    assert greeting["chat_id"] == "turn-one"
    assert len(model.calls) == 1
    assert model.calls[0]["earlier_conversation"] == []
    assert matter_list_projection(store.list_for("adv"), registers={})["matters"] == []

    second = BrainTurn("adv", text, "turn-two", chat_id=greeting["chat_id"],
                       offer={"message": text, "chat_id": greeting["chat_id"]})
    opened = brain.run(second).as_dict()
    assert opened["matter_id"] == chat_matter_id("adv", "turn-one")
    assert len(model.calls) == 2
    assert model.all_calls[:2] == ["interpret_conversation", "interpret_conversation"]
    assert set(model.all_calls[2:]) == {
        "extract_disputes", "extract_legal_details", "verify_material_grounding"}
    assert opened["metrics"]["llm_calls"] == 4
    assert [row["text"] for row in model.calls[1]["earlier_conversation"]] == [
        "Hello", "Hello."]
    matter = store.load(opened["matter_id"])
    assert matter.brain_ready is True
    assert [row["message"] for row in matter.brain_chat] == ["Hello", text]
    assert len(matter_list_projection(store.list_for("adv"), registers={})["matters"]) == 1
    assert opened["elements"][0]["text"] == (
        "I understand the supply agreement is in dispute. I will "
        "check the agreement and the relevant terms before giving a legal view.")
    assert opened["blocked"] is True


def test_first_substantive_message_uses_four_calls_and_exact_replay_uses_none(tmp_path):
    text = "Our client disputes the invoice issued on 3 March."
    brain, store, model = service(tmp_path, [
        plan(text, scope="proposed", step="legal_work",
             reply=("I will check the invoice and the underlying agreement "
                    "before giving a legal view."),
             title="Invoice dispute", summary="The client disputes an invoice.")])
    offered = BrainTurn("adv", text, "opening-id", offer={"message": text})
    first = brain.run(offered).as_dict()
    replayed = brain.run(offered).as_dict()
    assert first["matter_id"] == replayed["matter_id"]
    assert replayed["replayed"] is True
    assert replayed["metrics"]["llm_calls"] == 0
    assert len(model.calls) == 1
    assert model.all_calls[0] == "interpret_conversation"
    assert set(model.all_calls[1:]) == {
        "extract_disputes", "extract_legal_details", "verify_material_grounding"}
    assert first["metrics"]["llm_calls"] == 4
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
             summary=summary),
        {"party_name": "Mira Patel", "subject": "Return of records",
         "summary": summary},
    ])

    result = brain.run(BrainTurn("adv", text, "opening-parties")).as_dict()

    assert store.load(result["matter_id"]).title == "Mira Patel: Return of records"
    assert result["material_coverage"]["opening_fallback"] is False
    assert result["metrics"]["llm_calls"] == 6
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
            if prompt.operation == "verify_material_grounding":
                self.grounding_checks += 1
                if self.grounding_checks == 1:
                    rejected = {"verdicts": [
                        {"candidate_id": "O1", "verdict": "reject",
                         "reason": "A clearly named client was omitted."}]}
                    return replace(result, data=rejected)
            return result

    text = "Our client Mira Patel says a supplier retained her records."
    summary = "The client reports that a supplier retained her records."
    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    model = OpeningRejectedOnce([
        plan(text, scope="proposed", step="legal_work",
             reply="I will check the reported retention against the record.",
             title="Records retention", summary=summary),
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
    assert response["metrics"] == {"llm_calls": 1, "provider_retries": 2}


def test_context_overflow_has_a_nonretryable_plain_recovery_path(tmp_path):
    brain, store, model = service(tmp_path, [plan("Hello")])
    model.context_budget = lambda tier: 100

    with pytest.raises(BrainRefused) as failure:
        brain.run(BrainTurn("adv", "Hello", "over-limit"))

    assert failure.value.status == 413
    assert failure.value.retryable is False
    assert "retrying this unchanged turn will not help" in failure.value.why
    assert model.calls == []
    assert store.list_for("adv").matters == ()


@pytest.mark.parametrize(("failure", "said", "retryable"), [
    (ProviderUnavailable("private transport detail"),
     "AI service could not be reached", True),
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
                 title="Delivery dispute", summary="The advocate reports late delivery.")
    draft["items"].insert(0, {
        "request": "Assess the missed delivery", "relation": "new",
        "matter_scope": "proposed", "priority": "ordinary",
        "next_step": "answer", "reply": "The law guarantees damages today.",
        "clarification": "",
    })
    brain, _, model = service(tmp_path, [draft])

    response = brain.run(BrainTurn("adv", latest, "unchecked-answer")).as_dict()

    assert response["blocked"] is True
    assert "guarantees damages" not in response["elements"][0]["text"]
    assert response["elements"][0]["text"] == (
        "I will check the delivery terms and record before assessing remedies.")
    assert response["metrics"]["llm_calls"] == 4
    assert model.all_calls[0] == "interpret_conversation"
    assert set(model.all_calls[1:]) == {
        "extract_disputes", "extract_legal_details", "verify_material_grounding"}


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
                   title="Supply agreement termination", summary="The client disputes termination.")
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
        facts, first["elements"][0]["text"],
        diversion, "Paris."]
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
             "next_step": "legal_work", "reply": legal_reply, "clarification": ""},
            {"request": "What is the capital of France?", "relation": "aside",
             "matter_scope": "none", "priority": "ordinary",
             "next_step": "answer", "reply": "Paris.", "clarification": ""},
        ],
        "active_work_after": "assess deposit recovery",
        "material_review": False,
        "opening": {"ready": False, "party_name": "", "subject": "",
                    "summary": ""},
    }
    brain, _, model = service(tmp_path, [
        plan(account, scope="proposed", step="legal_work",
             reply="I can review the deposit dispute once I have the agreement.",
             title="Deposit dispute", summary="The advocate reports a withheld deposit."),
        modelled_mixed,
        plan("Please continue with the deposit review.", relation="continues",
             scope="current", step="legal_work",
             reply="I will continue reviewing the deposit and agreement."),
    ])
    opened = brain.run(BrainTurn("adv", account, "deposit-first")).as_dict()
    reply = brain.run(BrainTurn("adv", mixed, "deposit-mixed",
                                matter_id=opened["matter_id"],
                                chat_id=opened["chat_id"])).as_dict()
    assert reply["elements"][0]["text"] == f"{legal_reply}\n\nParis."
    assert reply["blocked"] is True
    assert reply["metrics"]["llm_calls"] == 1

    brain.run(BrainTurn("adv", "Please continue with the deposit review.",
                        "deposit-continue", matter_id=opened["matter_id"],
                        chat_id=opened["chat_id"]))
    assert [row["text"] for row in model.calls[2]["earlier_conversation"]][-2:] == [
        mixed, f"{legal_reply}\n\nParis."]
    assert model.calls[2]["current_work"] == "assess deposit recovery"


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
             "next_step": "legal_work", "reply": ordinary_reply, "clarification": ""},
            {"request": "Address the filing deadline", "relation": "continues",
             "matter_scope": "current", "priority": "urgent",
             "next_step": "legal_work", "reply": urgent_reply, "clarification": ""},
        ],
        "active_work_after": "check deadline and review draft response",
        "material_review": True,
        "opening": {"ready": False, "party_name": "", "subject": "",
                    "summary": ""},
    }
    model = Model([
        plan(account, scope="proposed", step="legal_work",
             reply="I will check the agreement and termination record.",
             title="Supply termination", summary="The client disputes termination."),
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
    assert response["elements"][0]["text"] == f"{urgent_reply}\n\n{ordinary_reply}"
    assert response["blocked"] is True
    assert response["metrics"]["llm_calls"] == 3


def test_served_factual_correction_keeps_its_direct_reply_and_source(
        client, wired, monkeypatch):
    account = "Our client contests the notice; the hearing is on Tuesday."
    correction = "Correction: the hearing is on Thursday, not Tuesday."
    direct_reply = ("You have corrected the hearing date to Thursday. "
                    "I will use that as provisional while checking the notice.")
    update = plan(correction, relation="continues", scope="current",
                  step="answer", reply=direct_reply)
    update["material_review"] = True

    class SourcedModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation != "extract_legal_details":
                return result
            payload = json.loads(prompt.user)
            if not any("Correction:" in span["text"]
                       for span in payload["latest_message_spans"]):
                return result
            earlier_id = next(
                span["id"] for message in payload["earlier_conversation"]
                if message["role"] == "advocate"
                for span in message["source_spans"]
                if "hearing is on Tuesday" in span["text"])
            return replace(result, data={"details": [{
                "kind": "event", "statement": "The advocate corrects the hearing date to Thursday.",
                "relation": "corrects", "matter_scope": "current",
                "basis": "stated", "importance": "central",
                "why_material": "The hearing date may affect the next step.",
                "placement": "unresolved", "dispute_ids": [],
                "related_material_ids": [],
                "source_id": payload["latest_message_spans"][0]["id"],
                "prior_source_ids": [earlier_id],
            }]})

    model = SourcedModel([
        plan(account, scope="proposed", step="legal_work",
             reply="I can review the notice and hearing schedule.",
             title="Notice dispute", summary="The client contests a notice."),
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
    assert response["metrics"]["llm_calls"] == 4


def test_served_first_chat_stays_blank_until_matter_details_arrive(client, wired, monkeypatch):
    text = "Our client disputes the termination of a supply agreement."
    model = Model([
        plan("Hello"),
        plan(text, scope="proposed", step="legal_work",
             reply=("I will review the termination terms and the available "
                    "record before giving a legal view."),
             title="Supply agreement termination", summary="The client disputes termination."),
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
        summary="The supplier admitted wrongdoing and retained the drawings.")

    class GroundingModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "repair_opening":
                raise SchemaViolation("No grounded opening correction is available")
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation == "extract_legal_details":
                spans = json.loads(prompt.user)["latest_message_spans"]
                return replace(result, data={"details": [
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
                ]})
            if prompt.operation == "verify_material_grounding":
                return replace(result, data={"verdicts": [
                    {"candidate_id": "D1", "verdict": "accept",
                     "reason": "The notice is reported."},
                    {"candidate_id": "D2", "verdict": "reject",
                     "reason": "No admission was reported."},
                    {"candidate_id": "O1", "verdict": "reject",
                     "reason": "The opening adds an admission."},
                ]})
            return result

    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    model = GroundingModel([drafted])
    response = BrainService(store, model).run(
        BrainTurn("adv", latest, "grounding-turn")).as_dict()

    assert response["metrics"]["llm_calls"] == 6
    assert [row["statement"] for row in response["material"]] == [
        "We sent a notice."]
    assert response["material_coverage"] == {
        "state": "partial", "withheld_details": 1, "opening_fallback": True}
    saved = store.load(response["matter_id"])
    assert saved.title == "Matter"
    assert "admitted" not in saved.brain_opening_summary
    assert "could not be confirmed" in response["elements"][0]["text"]


def test_source_bound_legal_reply_preserves_distinct_clarification(tmp_path):
    store = FileMatterStore(tmp_path, key="a-test-sealing-key")
    matter = Matter(id="mat_clarification", advocate_id="adv",
                    title="Current matter", brain_ready=True)
    store.commit(matter, expected_version=0)
    mixed = {"items": [
        {"request": "Check the legal position", "relation": "continues",
         "matter_scope": "current", "priority": "ordinary",
         "next_step": "legal_work", "reply": "I will check the law.",
         "clarification": ""},
        {"request": "Identify the order", "relation": "uncertain",
         "matter_scope": "current", "priority": "ordinary",
         "next_step": "clarify", "reply": "",
         "clarification": "Which order do you mean?"},
    ], "active_work_after": "check legal position",
       "material_review": False,
       "opening": {"ready": False, "party_name": "", "subject": "",
                   "summary": ""}}
    model = Model([mixed])
    response = BrainService(store, model, legal_search=object()).run(
        BrainTurn("adv", "Please check the law for that order.", "mixed-turn",
                  matter_id=matter.id)).as_dict()

    assert "Which order do you mean?" in response["elements"][0]["text"]
    assert "I will check the law." not in response["elements"][0]["text"]
    assert response["metrics"]["llm_calls"] == 1
