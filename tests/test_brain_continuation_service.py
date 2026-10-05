"""The served turn releases checked replies and preserves their conversation."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.turn import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, TierUnavailable, Usage
from tests.brain_continuation_fixture import citation_units, interpretation, reviewed_verdicts
from tests.brain_reader_fixture import reviewed_record_verdicts, source_treatment_reply
from tests.test_brain_continuation import mixed_purpose_unit, unit, verdict
from tests.test_brain_turn import plan


class PublicContinuationModel:
    provider = "scripted"

    def __init__(self, routes, continuations, *, checks=None):
        self.routes = iter(routes)
        self.continuations = iter(continuations)
        self.checks = iter(checks) if checks is not None else None
        self.calls = []
        self.schemas = []
        self.tiers = []

    def context_budget(self, tier):
        return 100_000

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        self.schemas.append((prompt.operation, deepcopy(schema)))
        self.tiers.append(tier)
        treatment = source_treatment_reply(prompt.operation, payload)
        if treatment is not None:
            data = treatment
        elif prompt.operation == "interpret_conversation":
            planned = next(self.routes)
            data = interpretation(planned(payload) if callable(planned) else deepcopy(planned))
        elif prompt.operation == "extract_disputes":
            data = {"new_items": [], "changes": []}
        elif prompt.operation == "extract_legal_details":
            data = {"new_items": [], "changes": []}
        elif prompt.operation == "verify_material_grounding":
            data = {"verdicts": [
                {"candidate_id": row["candidate_id"], "verdict": "accept",
                 "operation_supported": True,
                 "reason": "The opening accurately describes the attributed account."}
                for row in payload["candidates"]]}
        elif prompt.operation == "continue_conversation":
            reply = next(self.continuations)
            data = reply(payload) if callable(reply) else deepcopy(reply)
            data = citation_units(payload, data)
        elif prompt.operation == "verify_continuation":
            if self.checks is None:
                data = verdict(*(row["request_index"] for row in payload["units"]))
            else:
                check = next(self.checks)
                data = check(payload) if callable(check) else deepcopy(check)
            data = reviewed_verdicts(payload, data)
        else:
            raise AssertionError(f"Unexpected public model operation: {prompt.operation}")
        if prompt.operation == "verify_material_grounding":
            data = reviewed_record_verdicts(payload, data)
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE,
        )


def opening_route(text):
    return plan(
        text, scope="proposed", step="legal_work",
        reply="I will examine your request before giving a supported assessment.",
        title="Receipt and agreement concern",
        summary="The advocate reports holding a signed receipt for a disputed transaction.")


def send(client, message, turn_id, *, opened=None):
    body = {"message": message, "turn_id": turn_id}
    if opened is not None:
        body.update(matter_id=opened["matter_id"], chat_id=opened["chat_id"])
    response = client.post("/api/turn", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_public_legal_claim_disguised_as_account_is_withheld_without_losing_a_valid_peer(
        client, wired, monkeypatch):
    message = "Review the reported account and clarify what information you need."
    routing = plan(message, scope="none", step="legal_work", reply="I will examine the account.")
    routing["items"].append({**routing["items"][0], "request": "Clarify the missing information",
                             "next_step": "clarify", "reply": "",
                             "clarification": "What should be examined?"})
    bad = unit(text="The reported agreement creates an enforceable payment obligation.")
    bad["blocks"] = [bad["blocks"][0]]
    bad.update(questions=[], sufficiency={"status": "needs_input", "block_id": "account-0"})
    good = unit(1, text="You ask what information is needed to examine the reported account.",
                question="Which part of the account should we examine?")

    def review_with_legal_requirement(payload):
        result = reviewed_verdicts(payload, verdict(*(row["request_index"]
                                                      for row in payload["units"])))
        selected = next(row for row in result["verdicts"] if row["request_index"] == 0)
        selected["block_checks"][0].update(
            requires_legal_support=True, verdict="reject",
            reason="An enforceable obligation states law; the selected user words supply none.")
        return result

    def repeated_bad(payload):
        assert [row["request_index"] for row in payload["work_items"]] == [0]
        assert payload["correction"]["rejected_units"] == citation_units(
            payload, {"units": [bad]})["units"]
        return {"units": [bad]}

    model = PublicContinuationModel(
        [routing], [{"units": [bad, good]}, repeated_bad],
        checks=[review_with_legal_requirement, review_with_legal_requirement])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    answer = send(client, message, "structured-legal-account")
    replay = send(client, message, "structured-legal-account")

    assert answer["metrics"]["llm_calls"] == 5
    assert [row["request_index"] for row in answer["continuation"]["units"]] == [1]
    assert [row["state"] for row in answer["continuation"]["coverage"]] == ["unavailable", "ok"]
    visible = "\n".join(row["text"] for row in answer["elements"])
    assert "enforceable payment obligation" not in visible
    assert "Which part of the account should we examine?" in visible
    saved = wired.store.load(answer["matter_id"] or chat_matter_id("adv_demo", answer["chat_id"]))
    assert len(saved.brain_chat) == 1 and saved.brain_chat[0]["message"] == message
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0


def test_public_hidden_question_purpose_is_rewritten_into_an_actual_visible_question(
        client, wired, monkeypatch):
    message = "I am unsure which date matters. Help me clarify the account."
    routing = plan(message, scope="none", step="clarify")
    routing["items"][0]["clarification"] = "Which date matters?"
    hidden = unit(text="You are unsure which date matters.")
    hidden["blocks"] = [hidden["blocks"][0], hidden["blocks"][-1]]
    hidden["questions"][0].update(block_id="account-0", purpose="Identify the event date.")
    repaired = unit(text="You are unsure which date matters.",
                    question="Which event's date are you unsure about?")
    repaired["questions"][0]["purpose"] = "Identify the event whose date needs clarification."

    def unexpressed(payload):
        result = reviewed_verdicts(payload, verdict(0))
        result["verdicts"][0]["proposal_checks"][0].update(
            purpose_expressed=False, reason="The recap does not ask for the event date.")
        return result

    model = PublicContinuationModel([routing], [{"units": [hidden]}, {"units": [repaired]}],
                                    checks=[unexpressed, verdict(0)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    answer = send(client, message, "structured-visible-question")

    assert answer["metrics"]["llm_calls"] == 5
    visible = "\n".join(row["text"] for row in answer["elements"])
    assert "Which event's date are you unsure about?" in visible
    metadata = answer["continuation"]["units"][0]["questions"][0]
    assert metadata["block_id"] == "question-0"
    correction = model.calls[3][1]["correction"]["validation_issues"][0]["issue"]
    assert "objective-0" in correction and "account-0" in correction


def test_public_first_turn_uses_checked_conversation_reply_and_replay_is_free(
        client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."
    model = PublicContinuationModel([opening_route(message)], [{"units": [unit()]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = send(client, message, "continuation-first")
    repeated = send(client, message, "continuation-first")

    visible = "\n".join(row["text"] for row in first["elements"])
    assert "You report holding a signed receipt." in visible
    assert "What outcome would you like to achieve?" in visible
    assert "The record and applicable legal sources have not been checked." in visible
    assert "I will examine your request" not in visible
    assert first["metrics"]["llm_calls"] == 7
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "classify_account_sources",
        "extract_disputes", "extract_legal_details",
        "verify_material_grounding", "continue_conversation", "verify_continuation"]
    assert model.tiers == [Tier.JUDGE, Tier.ROUTINE, Tier.ROUTINE, Tier.ROUTINE,
                           Tier.JUDGE, Tier.JUDGE, Tier.JUDGE]
    composition = next(payload for operation, payload in model.calls
                       if operation == "continue_conversation")
    assert all("reply" not in item and "clarification" not in item
               for item in composition["work_items"])
    assert "I will examine your request before giving a supported assessment." not in (
        json.dumps(composition))
    assert repeated["replayed"] is True
    assert repeated["metrics"]["llm_calls"] == 0
    saved = wired.store.load(first["matter_id"])
    assert len(saved.brain_chat) == 1
    assert saved.brain_chat[0]["elements"] == first["elements"]
    assert saved.brain_chat[0]["response"]["continuation"] == first["continuation"]


def test_public_contributor_keeps_chronology_and_material_review_without_requested_law(
        client, wired, monkeypatch):
    from tests.brain_research_fixture import Corpus
    from tests.test_brain_material import Model as MaterialModel
    from tests.test_brain_material import material
    from tests.test_brain_material import plan as material_plan

    first_words = ("We act for Mira concerning use of her property. The use began in 2019. "
                   "Please retain that reported account.")
    latest = "A written permission was given in 2021. I do not know when it ended."
    opening = material_plan(first_words, opening=True, candidates=[material(
        "event", "The reported use began in 2019.", "The use began in 2019.",
        placement="matter")])
    opening["opening"] = {"ready": True, "party_name": "Mira",
                          "subject": "Reported property use",
                          "summary": ("The advocate acts for Mira and reports "
                                      "use beginning in 2019.")}
    contribution = material_plan(latest, candidates=[
        material("event", "Written permission was given in 2021.",
                 "A written permission was given in 2021.", scope="current", placement="matter"),
        material("circumstance", "The advocate does not know when the permission ended.",
                 "I do not know when it ended.", scope="current", placement="matter"),
    ], items=[{"request": "Add the reported permission and its unknown duration to the account.",
               "relation": "changes", "matter_scope": "current", "priority": "ordinary",
               "next_step": "legal_work", "reply": "I will retain the attributed chronology.",
               "clarification": "", "intent": "contribution", "research_question": ""}])
    initial = unit(text="You report that the use began in 2019.", span_ids=("L2",))
    initial["blocks"] = [initial["blocks"][0]]
    initial.update(questions=[], sufficiency={"status": "complete", "block_id": "account-0"})
    continued = unit(text=("You now report written permission in 2021, while the earlier account "
                           "places the start of use in 2019. Its end remains unknown to you."),
                     span_ids=("L1", "L2", "P1S2"))
    continued["blocks"] = [continued["blocks"][0]]
    continued.update(questions=[], work={"existing_id": "", "create": False},
                     sufficiency={"status": "complete", "block_id": "account-0"})

    class ContributorModel(MaterialModel):
        def __init__(self):
            super().__init__([opening, contribution])
            self.replies = iter([initial, continued])
            self.seen = []

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            self.seen.append((prompt, json.loads(prompt.user), deepcopy(schema)))
            if prompt.operation != "continue_conversation":
                return super().structured(prompt, schema, tier, max_tokens=max_tokens)
            data = citation_units(json.loads(prompt.user), {"units": [next(self.replies)]})
            return ModelResult(text=None, data=data, tier=tier,
                               provider="offline", model="offline", usage=Usage(0, 0, 0),
                               latency_ms=0, completion=Completion.COMPLETE)

    model, corpus = ContributorModel(), Corpus()
    wired.legal_search = corpus
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "contribution-start")
    second = send(client, latest, "contribution-later", opened=first)
    replay = send(client, latest, "contribution-later", opened=first)

    assert first["metrics"]["llm_calls"] == second["metrics"]["llm_calls"] == 7
    assert replay["metrics"]["llm_calls"] == 0
    assert corpus.calls == []
    last_calls = model.seen[7:]
    assert [prompt.operation for prompt, _, _ in last_calls] == [
        "interpret_conversation", "classify_account_sources",
        "extract_disputes", "extract_legal_details",
        "verify_material_grounding", "continue_conversation", "verify_continuation"]
    composition = next(payload for prompt, payload, _ in last_calls
                       if prompt.operation == "continue_conversation")
    assert composition["work_items"][0]["intent"] == "contribution"
    assert composition["work_items"][0]["research_question"] == ""
    assert ["".join(span["text"] for span in row["source_spans"])
            for row in composition["earlier_conversation"]] == [
                first_words, "\n".join(row["text"] for row in first["elements"])]
    assert "".join(row["text"] for row in composition["latest_message_spans"]) == latest
    for prompt, _, schema in model.seen:
        if prompt.operation == "continue_conversation":
            assert "assessment" not in schema["properties"]["units"]["items"][
                "properties"]["blocks"]["items"]["properties"]["kind"]["enum"]
    assert second["continuation"]["units"][0]["work"]["progress_id"] == ""
    assert second["elements"][0]["text"] == continued["blocks"][0]["text"]
    saved = wired.store.load(first["matter_id"])
    assert len(saved.brain_chat) == 2
    details = saved.brain_chat[-1]["response"]["material"]
    assert len(details) == 2
    assert {row["quoted"] for row in details} == {
        "A written permission was given in 2021.", "I do not know when it ended."}
    assert all(row["source_turn_id"] == "contribution-later" for row in details)
    assert saved.brain_chat[-1]["response"]["research_reads"] == []


def test_public_substantive_return_has_all_history_and_diversion_preserves_work(
        client, wired, monkeypatch):
    first_message = "I have a signed receipt for the disputed transaction. Please review it."
    correction = "Correction: the receipt is unsigned."
    greeting = "Hello again."
    returned = "Please return to the review. I cannot obtain a signed copy."
    routes = [
        opening_route(first_message),
        plan(correction, scope="current", step="legal_work", relation="changes",
             reply="I will revisit the reported status of the receipt."),
        plan(greeting, scope="none", relation="aside", reply="Hello."),
        plan(returned, scope="current", step="legal_work", relation="continues",
             reply="I will continue the requested review."),
    ]
    def aside_route(payload):
        aside = plan(greeting, scope="none", relation="aside", reply="Hello.")
        aside["items"][0]["intent"] = "contribution"
        aside["active_work_after"] = payload["current_work"]
        return aside

    routes[2] = aside_route
    routes[1]["material_review"] = True
    routes[3]["material_review"] = True
    corrected = unit(
        text="You have corrected the receipt's status to unsigned.",
        question="Is any other record of the transaction available?")
    final = unit(
        text="You have said that a signed copy is unavailable.", span_ids=("L2",),
        question="Would you like to assess the record that remains available?")
    greeted = unit(text="Hello.")
    greeted["blocks"] = [greeted["blocks"][0]]
    greeted["blocks"][0].update(kind="completion", uncertainty="none")
    greeted.update(questions=[], work={"existing_id": "", "create": False},
                   sufficiency={"status": "complete", "block_id": "account-0"})
    model = PublicContinuationModel(routes, [
        {"units": [unit()]}, {"units": [corrected]},
        {"units": [greeted]}, {"units": [final]},
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = send(client, first_message, "public-first")
    second = send(client, correction, "public-correction", opened=first)
    from nm.brain.work_state import project_work

    before_aside = project_work(wired.store.load(first["matter_id"]))
    aside = send(client, greeting, "public-aside", opened=second)
    after_aside = project_work(wired.store.load(first["matter_id"]))
    assert after_aside == before_aside
    last = send(client, returned, "public-return", opened=aside)

    assert second["metrics"]["llm_calls"] == 6
    assert aside["metrics"]["llm_calls"] == 3
    assert aside["continuation"]["coverage"][0]["state"] == "ok"
    assert aside["elements"][0]["text"] == "Hello."
    assert last["metrics"]["llm_calls"] == 6
    continuation_payloads = [payload for operation, payload in model.calls
                             if operation == "continue_conversation"]
    earlier = continuation_payloads[-1]["earlier_conversation"]
    assert [row["turn_id"] for row in earlier] == [
        "public-first", "public-first", "public-correction", "public-correction",
        "public-aside", "public-aside"]
    words = ["".join(span["text"] for span in row["source_spans"]) for row in earlier]
    assert words[::2] == [first_message, correction, greeting]
    assert words[1::2] == ["\n".join(row["text"] for row in response["elements"])
                          for response in (first, second, aside)]
    assert "signed copy is unavailable" in json.dumps(last["elements"])
    saved = wired.store.load(first["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [
        first_message, correction, greeting, returned]
    assert saved.brain_chat[2]["active_work_after"] == before_aside["active_work"]


def test_public_mixed_purpose_block_uses_question_link_for_display(client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."
    proposed = mixed_purpose_unit()
    model = PublicContinuationModel([opening_route(message)], [{"units": [proposed]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    released = send(client, message, "public-mixed-block")

    assert released["metrics"]["llm_calls"] == 7
    assert released["continuation"]["units"][0]["blocks"][0]["kind"] == "limitation"
    assert released["elements"][0]["kind"] == "question"
    assert released["elements"][0]["section"] == "needed"
    assert released["elements"][0]["text"] == proposed["blocks"][0]["text"]
    checked = next(payload for operation, payload in model.calls
                   if operation == "verify_continuation")
    assert checked["units"] == [proposed]


def test_public_rejected_assessment_keeps_input_once_and_does_not_release_accusation(
        client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."
    unsupported = unit(text="You deliberately concealed a damaging record.")
    reason = "The attributed record does not establish deliberate concealment."
    model = PublicContinuationModel(
        [opening_route(message)], [{"units": [unsupported]}, {"units": [unsupported]}],
        checks=[verdict(0, accept=False, reason=reason),
                verdict(0, accept=False, reason=reason)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    response = send(client, message, "public-rejected")

    assert "deliberately concealed" not in json.dumps(response["elements"])
    assert response["continuation"]["units"] == []
    assert response["continuation"]["coverage"][0]["state"] == "unavailable"
    assert response["metrics"]["llm_calls"] == 9
    saved = wired.store.load(response["matter_id"])
    assert len(saved.brain_chat) == 1
    assert saved.brain_chat[0]["message"] == message
    assert "deliberately concealed" not in json.dumps(saved.brain_chat[0]["elements"])


def test_public_foreign_chat_and_corrupt_history_stop_before_model_dispatch(
        client, wired, monkeypatch):
    from dataclasses import replace

    message = "I have a signed receipt for the disputed transaction. Please review it."
    model = PublicContinuationModel([opening_route(message)], [{"units": [unit()]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, message, "public-owned")
    before_calls = len(model.calls)
    other = client.sign_in("adv_other", fresh=True)

    foreign = other.post("/api/turn", json={
        "message": "Continue", "turn_id": "public-foreign",
        "matter_id": first["matter_id"]})

    assert foreign.status_code == 404, foreign.text
    assert len(model.calls) == before_calls
    saved = wired.store.load(first["matter_id"])
    unreadable = deepcopy(saved.brain_chat[0])
    unreadable["release_state"] = "unknown"
    wired.store.commit(replace(
        saved, brain_chat=(unreadable,), version=saved.version + 1),
        expected_version=saved.version)

    refused = client.post("/api/turn", json={
        "message": "Continue", "turn_id": "public-corrupt",
        "matter_id": first["matter_id"], "chat_id": first["chat_id"]})

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["committed"] == "not_committed"
    assert refused.json()["detail"]["code"] == "brain_refused"
    assert len(model.calls) == before_calls
    assert len(wired.store.load(first["matter_id"]).brain_chat) == 1


def test_public_session_revoked_during_verification_cannot_save_or_release(
        client, wired, monkeypatch):
    message = "I have a signed receipt for the disputed transaction. Please review it."

    class RevokedDuringVerification(PublicContinuationModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            checked = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "verify_continuation":
                assert wired.directory.close_all_sessions(
                    "adv_demo", "Synthetic revocation during response checking") == 1
            return checked

    model = RevokedDuringVerification([opening_route(message)], [{"units": [unit()]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    response = client.post("/api/turn", json={
        "message": message, "turn_id": "public-revoked-during-check"})

    assert response.status_code == 401, response.text
    assert response.json()["detail"]["committed"] == "not_committed"
    assert "You report holding a signed receipt." not in response.text
    assert wired.store.list_for("adv_demo").matters == ()
    assert [operation for operation, _ in model.calls].count("verify_continuation") == 1


def test_public_interpreter_downgrade_stops_before_saving_or_followup_calls(
        client, wired, monkeypatch):
    from nm.shared.model_traced import TracedModel

    class MissingInterpreter(PublicContinuationModel):
        def __init__(self):
            super().__init__([plan("Hello", reply="Hello.")], [])
            self.dispatched = []

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            self.dispatched.append((prompt.operation, tier))
            if prompt.operation == "interpret_conversation" and tier is Tier.JUDGE:
                raise TierUnavailable("The synthetic interpretation tier is unavailable.")
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)

    inner = MissingInterpreter()
    traced = TracedModel(inner)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: traced)

    refused = client.post("/api/turn", json={
        "message": "Hello", "turn_id": "downgraded-interpretation"})

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["committed"] == "not_committed"
    assert inner.dispatched == [
        ("interpret_conversation", Tier.JUDGE), ("interpret_conversation", Tier.ROUTINE)]
    assert len(traced.calls) == 1
    assert traced.calls[0].downgraded_from == Tier.JUDGE.value
    assert wired.store.list_for("adv_demo").matters == ()


def test_public_interpreter_correction_keeps_configured_tier_and_saves_input_once(
        client, wired, monkeypatch):
    from nm.brain.turn import chat_matter_id

    class InitialParseFailure(PublicContinuationModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "interpret_conversation" and not self.calls:
                self.calls.append((prompt.operation, json.loads(prompt.user)))
                self.tiers.append(tier)
                raise SchemaViolation("The synthetic response omitted the declared items.")
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)

    greeted = unit(text="Hello.")
    greeted["blocks"] = [greeted["blocks"][0]]
    greeted["blocks"][0].update(kind="completion", uncertainty="none")
    greeted.update(questions=[], work={"existing_id": "", "create": False},
                   sufficiency={"status": "complete", "block_id": "account-0"})
    routed = plan("Hello", reply="Hello.")
    routed["items"][0]["intent"] = "contribution"
    model = InitialParseFailure([routed], [{"units": [greeted]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    greeting = send(client, "Hello", "repaired-interpretation")

    assert greeting["metrics"]["llm_calls"] == 4
    assert greeting["matter_id"] is None
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "interpret_conversation",
        "continue_conversation", "verify_continuation"]
    assert model.tiers == [Tier.JUDGE] * 4
    correction = model.calls[1][1]
    assert correction["original_input"]["latest_message"] == "Hello"
    assert "omitted the declared items" in correction["validation_issue"]
    saved = wired.store.load(chat_matter_id("adv_demo", "repaired-interpretation"))
    assert [turn["message"] for turn in saved.brain_chat] == ["Hello"]


def test_public_source_free_acknowledgment_in_open_matter_preserves_work_with_three_calls(
        client, wired, monkeypatch):
    from nm.brain.work_state import project_work

    first_words = "I have a signed receipt for the disputed transaction. Please review it."
    acknowledgment = "Thanks, I understand."
    acknowledged = plan(acknowledgment, scope="none", relation="continues",
                        step="answer", reply="You're welcome.")
    acknowledged["items"][0]["intent"] = "contribution"
    delivered = unit(text="You're welcome.")
    delivered["blocks"] = [delivered["blocks"][0]]
    delivered["blocks"][0].update(kind="completion", uncertainty="none")
    delivered.update(questions=[], work={"existing_id": "", "create": False},
                     sufficiency={"status": "complete", "block_id": "account-0"})
    model = PublicContinuationModel(
        [opening_route(first_words), acknowledged],
        [{"units": [unit()]}, {"units": [delivered]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "sourcefree-open")
    before = project_work(wired.store.load(first["matter_id"]))
    previous_calls = len(model.calls)

    reply = send(client, acknowledgment, "sourcefree-acknowledgment", opened=first)

    assert reply["metrics"]["llm_calls"] == 3
    assert [operation for operation, _ in model.calls[previous_calls:]] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    assert len(model.calls) == previous_calls + 3
    assert model.tiers[-3:] == [Tier.JUDGE] * 3
    assert [row["text"] for row in reply["elements"]] == ["You're welcome."]
    saved = wired.store.load(first["matter_id"])
    assert project_work(saved) == before
    assert [row["message"] for row in saved.brain_chat] == [first_words, acknowledgment]


def test_public_matter_specific_answer_is_repaired_to_checked_composition_before_release(
        client, wired, monkeypatch):
    first_words = "I have a signed receipt for the disputed transaction. Please review it."
    requested = "Please summarize the reported account."
    invalid = plan(requested, scope="current", relation="continues", step="answer",
                   reply="UNREVIEWED_ROUTER_ACCOUNT")
    corrected = plan(requested, scope="current", relation="continues", step="legal_work",
                     reply="The requested account summary will use attributed material.")
    delivered = unit(text=(
        "Your account reports a signed receipt for a disputed transaction. "
        "The receipt's contents have not been checked."), span_ids=("P1S1",))
    delivered["blocks"] = [delivered["blocks"][0], delivered["blocks"][2]]
    delivered["questions"] = []
    delivered["sufficiency"] = {"status": "complete", "block_id": "account-0"}
    delivered["progress_updates"] = [{
        "target_id": "$work", "status": "complete", "block_id": "account-0",
        "reason": "The requested reported-account summary is delivered with its limits.",
        "span_ids": ["P1S1"]}]
    model = PublicContinuationModel(
        [opening_route(first_words), invalid, corrected],
        [{"units": [unit()]}, {"units": [delivered]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "scope-repair-open")
    prior_calls = len(model.calls)

    summary = send(client, requested, "scope-repair-summary", opened=first)

    assert summary["metrics"]["llm_calls"] == 4
    assert [operation for operation, _ in model.calls[prior_calls:]] == [
        "interpret_conversation", "interpret_conversation",
        "continue_conversation", "verify_continuation"]
    assert model.tiers[prior_calls:] == [Tier.JUDGE] * 4
    repair = model.calls[prior_calls + 1][1]
    assert "matter_scope=none" in repair["validation_issue"]
    assert repair["original_input"]["latest_message"] == requested
    assert "UNREVIEWED_ROUTER_ACCOUNT" not in json.dumps(summary["elements"])
    reference = summary["continuation"]["units"][0]["blocks"][0]["references"][0]
    assert reference["role"] == "advocate"
    assert reference["turn_id"] == "scope-repair-open"
    assert reference["text"] == "I have a signed receipt for the disputed transaction."
    assert model.calls[-1][1]["units"] == [delivered]
    saved = wired.store.load(first["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [first_words, requested]


def test_public_rejected_material_notice_is_the_exact_saved_reply_on_next_turn(
        client, wired, monkeypatch):
    from nm.brain.turn import chat_matter_id
    from tests.brain_reader_fixture import reader_operations

    first_words = "I may have a note about the transaction."
    greeting = "Hello again."
    acknowledgment = plan(first_words, scope="none", step="answer", reply="Thank you.")
    acknowledgment["items"][0]["intent"] = "contribution"
    acknowledgment["material_review"] = True

    class RejectedDetail(PublicContinuationModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if prompt.operation == "extract_legal_details":
                data = reader_operations([{
                    "kind": "evidence", "statement": "The note proves the transaction was valid.",
                    "matter_scope": "proposed", "basis": "stated", "importance": "relevant",
                    "why_material": "The proposed conclusion would affect the account.",
                    "placement": "unresolved", "dispute_ids": [], "source_id": "L1",
                    "relation": "new", "related_material_ids": [],
                }], json.loads(prompt.user), link_field="related_material_ids")
            elif prompt.operation == "verify_material_grounding":
                data = {"verdicts": [{
                    "candidate_id": row["candidate_id"], "verdict": "reject",
                    "operation_supported": False,
                    "reason": "A possibly held, unexamined note does not prove its contents.",
                } for row in json.loads(prompt.user)["candidates"]]}
            else:
                return result
            if prompt.operation == "verify_material_grounding":
                data = reviewed_record_verdicts(json.loads(prompt.user), data)
            return replace(result, data=data)

    thanked = unit(text="Thank you.")
    thanked["blocks"] = [thanked["blocks"][0]]
    thanked["blocks"][0].update(kind="completion", uncertainty="none")
    thanked.update(questions=[], work={"existing_id": "", "create": False},
                   sufficiency={"status": "complete", "block_id": "account-0"})
    greeted = deepcopy(thanked)
    greeted["blocks"][0]["text"] = "Hello."
    aside = plan(greeting, relation="aside", scope="none", reply="Hello.")
    aside["items"][0]["intent"] = "contribution"
    model = RejectedDetail([
        acknowledgment, aside],
        [{"units": [thanked]}, {"units": [greeted]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "rejected-notice-first")
    saved_id = chat_matter_id("adv_demo", first["chat_id"])
    first_saved = wired.store.load(saved_id)

    assert first["metrics"]["llm_calls"] == 7
    assert first["matter_id"] is None
    assert first["material"] == []
    assert first["material_coverage"]["withheld_details"] == 1
    assert len(first["elements"]) == 2
    assert "Your message is saved" in first["elements"][1]["text"]
    assert first_saved.brain_chat[0]["elements"] == first["elements"]
    assert first_saved.brain_chat[0]["response"]["elements"] == first["elements"]

    second = send(client, greeting, "rejected-notice-second", opened=first)

    assert second["metrics"]["llm_calls"] == 3
    assert [operation for operation, _ in model.calls[-3:]] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    prior = model.calls[-3][1]["earlier_conversation"]
    assert [(row["role"], row["text"]) for row in prior] == [
        ("advocate", first_words), ("nm", "\n".join(row["text"] for row in first["elements"]))]
    saved = wired.store.load(saved_id)
    assert [row["message"] for row in saved.brain_chat] == [first_words, greeting]
    assert all(row["elements"] == row["response"]["elements"] for row in saved.brain_chat)
    assert sum(operation == "continue_conversation" for operation, _ in model.calls) == 2
    assert sum(operation == "verify_continuation" for operation, _ in model.calls) == 2


@pytest.mark.parametrize("conflict", ["preflight", "commit"])
def test_public_actual_version_conflict_is_typed_without_reclassifying_source_failures(
        client, wired, monkeypatch, conflict):
    first_words = "I have a signed receipt for the disputed transaction. Please review it."
    requested = "Please continue reviewing the reported account."

    class ConcurrentUpdate(PublicContinuationModel):
        active_matter_id = None

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if (conflict == "commit" and prompt.operation == "verify_continuation"
                    and self.active_matter_id):
                current = wired.store.load(self.active_matter_id)
                wired.store.commit(replace(current, version=current.version + 1),
                                   expected_version=current.version)
            return result

    model = ConcurrentUpdate([
        opening_route(first_words), plan(requested, scope="current", relation="continues",
                                        step="legal_work", reply="I will continue the review.")],
        [{"units": [unit()]}, {"units": [unit(span_ids=("P1S1",))]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, f"version-open-{conflict}")
    model.active_matter_id = first["matter_id"]
    before = wired.store.load(first["matter_id"])
    prior_calls = len(model.calls)
    expected = before.version - 1 if conflict == "preflight" else before.version

    stale = client.post("/api/turn", json={
        "message": requested, "turn_id": f"version-followup-{conflict}",
        "matter_id": first["matter_id"], "chat_id": first["chat_id"],
        "expected_version": expected})

    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "stale_version"
    assert stale.json()["detail"]["committed"] == "not_committed"
    assert len(model.calls) - prior_calls == (0 if conflict == "preflight" else 3)
    saved = wired.store.load(first["matter_id"])
    assert saved.brain_chat == before.brain_chat
    assert saved.version == before.version + (conflict == "commit")
