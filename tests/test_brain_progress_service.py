"""Public turns persist independently checked scoped work without another call."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.work_state import project_work
from nm.shared.model_port import Tier
from tests.brain_continuation_fixture import citation_units
from tests.test_brain_continuation import verdict
from tests.test_brain_continuation_service import PublicContinuationModel, send
from tests.test_brain_turn import plan

FIRST = "The transaction is disputed. Please review the reported account."
QUESTION = "What scope would you like for this review?"


def route(message, *, intent="request", opening=False, aside=False):
    proposal = plan(
        message, scope="none" if aside else "proposed" if opening else "current",
        step="answer" if aside else "legal_work",
        relation="aside" if aside else "new" if opening else "continues",
        reply="Hello." if aside else "The interpreter's draft is not a delivered assessment.",
        title="Disputed transaction" if opening else "",
        summary="The advocate reports that the transaction is disputed." if opening else "")
    proposal["items"][0]["intent"] = intent
    return proposal


def block(index, text, *, kind="account", spans=("L1",)):
    return {"id": f"block-{index}", "kind": kind, "text": text,
            "span_ids": list(spans), "record_ids": [], "legal_source_ids": [],
            "inline_citations": [],
            "uncertainty": "reported"}


def link(index, *, existing=""):
    return {"id": f"scope-{index}", "block_id": f"question-{index}",
            "purpose": "Establish the user's requested review scope.",
            "target_ids": [], "existing_id": existing}


def update(target, status, *, index=0, spans=("L1",)):
    return {"target_id": target, "status": status, "block_id": f"block-{index}",
            "reason": "The displayed response and attributed words support this scoped change.",
            "span_ids": list(spans)}


def response(index=0, *, text="You report that the transaction is disputed.",
             existing="", create=False, question=False, updates=(), complete=False,
             spans=("L1",)):
    blocks = [block(index, text, spans=spans)]
    questions = []
    if question:
        blocks.append({**block(index, QUESTION, kind="question"),
                       "id": f"question-{index}"})
        questions.append(link(index))
    return {"request_index": index, "blocks": blocks, "questions": questions,
            "next_work": [], "work": {"existing_id": existing, "create": create},
            "progress_updates": list(updates),
            "sufficiency": {"status": "complete" if complete else "needs_input",
                            "block_id": f"block-{index}"}}


def work_ids(payload):
    rows = payload["progress"]["rows"]
    task = next(row["id"] for row in rows if row["kind"] == "task"
                and row["origin"] == "requested")
    question = next(row["id"] for row in rows if row["kind"] == "question")
    return task, question


def question_transition(status, text):
    def proposal(payload):
        task_id, question_id = work_ids(payload)
        return {"units": [response(existing=task_id, text=text,
                                   updates=[update(question_id, status)])]}
    return proposal


def wire(wired, monkeypatch, routes, replies, *, checks=None):
    model = PublicContinuationModel(routes, replies, checks=checks)
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    return model


def progress(wired, opened):
    return project_work(wired.store.load(opened["matter_id"]))


def test_public_answer_completes_question_once_and_preserves_the_requested_task(
        client, wired, monkeypatch):
    answered = "A neutral summary of the reported account, without legal conclusions."
    model = wire(wired, monkeypatch,
                 [route(FIRST, opening=True), route(answered, intent="contribution")],
                 [{"units": [response(create=True, question=True)]},
                  question_transition("complete", "You want a neutral summary of the account.")])
    first = send(client, FIRST, "progress-first")
    before = progress(wired, first)
    second = send(client, answered, "progress-answer", opened=first)
    after = progress(wired, second)
    replay = send(client, answered, "progress-answer", opened=first)

    assert first["metrics"]["llm_calls"] == 7
    assert second["metrics"]["llm_calls"] == 3
    assert replay["metrics"]["llm_calls"] == 0
    assert after == progress(wired, replay)
    assert [(row["kind"], row["origin"], row["status"]) for row in after["rows"]] == [
        ("task", "requested", "pending"), ("question", "proposed", "complete")]
    assert after["rows"][0] == before["rows"][0]
    assert after["rows"][1]["last_update_turn_id"] == "progress-answer"
    unit = second["continuation"]["units"][0]
    assert unit["progress_version"] == 2
    assert unit["progress_updates"][0]["target_id"] == before["rows"][1]["id"]
    assert unit["blocks"][0]["references"][0]["turn_id"] == "progress-answer"
    writer_input = [payload for operation, payload in model.calls
                    if operation == "continue_conversation"][-1]
    assert writer_input["progress"] == before
    assert model.tiers[-3:] == [Tier.JUDGE, Tier.JUDGE, Tier.JUDGE]
    assert len(wired.store.load(first["matter_id"]).brain_chat) == 2


def test_public_promise_unavailable_diversion_and_reask_repair_keep_question_identity(
        client, wired, monkeypatch):
    promised = "I will decide the review scope tomorrow."
    unavailable = "I cannot choose the review scope now."
    greeting = "Hello again."
    returned = "Continue with the reported account."

    def reask(payload):
        task_id, question_id = work_ids(payload)
        unit = response(existing=task_id, question=True,
                        text="You have asked to continue with the reported account.")
        unit["questions"][0]["existing_id"] = question_id
        return {"units": [unit]}

    def proceed(payload):
        task_id, _ = work_ids(payload)
        return {"units": [response(existing=task_id, text=(
            "We can continue with the account already reported; the review scope is undecided."))]}

    model = wire(wired, monkeypatch, [
        route(FIRST, opening=True), route(promised, intent="contribution"),
        route(unavailable, intent="contribution"), route(greeting, aside=True), route(returned)],
        [{"units": [response(create=True, question=True)]},
         question_transition("promised", "You intend to decide the review scope tomorrow."),
         question_transition("unavailable", "You cannot choose the review scope now."),
         reask, proceed])
    first = send(client, FIRST, "progress-open")
    promise = send(client, promised, "progress-promise", opened=first)
    assert progress(wired, promise)["rows"][1]["status"] == "promised"
    absent = send(client, unavailable, "progress-unavailable", opened=first)
    before_aside = progress(wired, absent)
    aside = send(client, greeting, "progress-aside", opened=first)
    assert progress(wired, aside) == before_aside
    returned_reply = send(client, returned, "progress-return", opened=first)
    after = progress(wired, returned_reply)

    assert promise["metrics"]["llm_calls"] == absent["metrics"]["llm_calls"] == 3
    assert aside["metrics"]["llm_calls"] == 1
    assert returned_reply["metrics"]["llm_calls"] == 4
    assert after["rows"][1]["status"] == "unavailable"
    assert after["rows"][1]["id"] == before_aside["rows"][1]["id"]
    assert len(after["rows"]) == 2
    assert after["rows"][0]["status"] == "pending"
    assert QUESTION not in json.dumps(returned_reply["elements"])
    repair = [payload for operation, payload in model.calls
              if operation == "continue_conversation"][-1]
    assert "correction" in repair
    assert repair["progress"]["rows"][1]["status"] == "unavailable"
    assert [row["turn_id"] for row in repair["earlier_conversation"]][::2] == [
        "progress-open", "progress-promise", "progress-unavailable", "progress-aside"]


def test_public_reviewer_reconciles_answer_omission_through_one_bounded_repair(
        client, wired, monkeypatch):
    answer = "Please limit this review to a neutral summary of the reported account."

    def omitted(payload):
        task_id, _ = work_ids(payload)
        return {"units": [response(existing=task_id, text="You want a neutral summary.")]}

    model = wire(wired, monkeypatch,
                 [route(FIRST, opening=True), route(answer, intent="contribution")],
                 [{"units": [response(create=True, question=True)]}, omitted,
                  question_transition("complete", "You have chosen a neutral summary.")],
                 checks=[verdict(0), verdict(0, accept=False, reason=(
                     "The latest words answer the prior scope question, but its pending status "
                     "was not reconciled.")), verdict(0)])
    first = send(client, FIRST, "omission-open")
    answered = send(client, answer, "omission-answer", opened=first)

    assert answered["metrics"]["llm_calls"] == 5
    assert progress(wired, answered)["rows"][1]["status"] == "complete"
    generation = [payload for operation, payload in model.calls
                  if operation == "continue_conversation"][-1]
    assert "pending status" in json.dumps(generation["correction"])
    assert len(wired.store.load(first["matter_id"]).brain_chat) == 2


def test_public_complete_immediate_reply_leaves_new_requested_task_pending(
        client, wired, monkeypatch):
    delivered = "The reported account says that the transaction is disputed."
    immediate = response(create=True, text=delivered, complete=True)
    model = wire(wired, monkeypatch, [route(FIRST, opening=True)],
                 [{"units": [immediate]}])
    result = send(client, FIRST, "completion-open")
    saved = wired.store.load(result["matter_id"])
    projected = project_work(saved)

    assert result["metrics"]["llm_calls"] == 7
    assert projected["rows"][0]["status"] == "pending"
    assert projected["active_work"] == FIRST
    unit = result["continuation"]["units"][0]
    assert unit["sufficiency"]["status"] == "complete"
    assert unit["progress_updates"] == []
    assert saved.closure == {}
    assert saved.brain_ready is True
    assert [operation for operation, _ in model.calls].count("verify_continuation") == 1


def test_public_mixed_completion_keeps_checked_task_and_withholds_rejected_peer(
        client, wired, monkeypatch):
    first_words = ("The transaction is disputed. Please assess the legal position and available "
                   "legal responses. Please also prepare a neutral summary.")
    next_words = "Give the neutral summary now. Also assess the legal position."
    opening = route(first_words, opening=True)
    opening["items"][0]["request"] = "Assess the legal position and available legal responses."
    summary_request = deepcopy(opening["items"][0])
    summary_request["request"] = "Prepare a neutral summary."
    opening["items"].append(summary_request)
    later = route(next_words)
    assessment_request = deepcopy(later["items"][0])
    later["items"][0]["request"] = "Give the neutral summary now."
    assessment_request["request"] = "Assess the legal position."
    later["items"].append(assessment_request)
    deliveries = {}

    def draft(payload):
        tasks = [row for row in payload["progress"]["rows"] if row["kind"] == "task"]
        good = response(existing=tasks[1]["id"], complete=True,
                        text="The reported account says the transaction is disputed.",
                        spans=("P1S1",), updates=[update("$work", "complete", spans=("P1S1",))])
        bad = response(1, existing=tasks[0]["id"], complete=True, text=(
            "The account describes a disputed transaction; this factual summary does not "
            "complete the requested legal assessment."), spans=("P1S1",),
                       updates=[update("$work", "complete", index=1, spans=("P1S1",))])
        deliveries.update(good=deepcopy(good), bad=deepcopy(bad))
        return {"units": [good, bad]}

    def repair(payload):
        assert [item["request_index"] for item in payload["work_items"]] == [1]
        assert payload["correction"]["rejected_units"] == citation_units(
            payload, {"units": [deliveries["bad"]]})["units"]
        return {"units": [deepcopy(deliveries["bad"])]}

    reason = ("The immediate factual summary does not deliver the saved task's legal assessment "
              "and available responses; its broader task must not be marked complete.")
    mixed_check = {"verdicts": [*verdict(0)["verdicts"],
                                *verdict(1, accept=False, reason=reason)["verdicts"]]}
    model = wire(wired, monkeypatch, [opening, later], [
        {"units": [response(create=True), response(1, create=True)]}, draft, repair],
        checks=[verdict(0, 1), mixed_check, verdict(1, accept=False, reason=reason)])
    first = send(client, first_words, "mixed-progress-open")
    before = progress(wired, first)
    released = send(client, next_words, "mixed-progress-deliver", opened=first)
    after = progress(wired, released)

    assert first["metrics"]["llm_calls"] == 7
    assert released["metrics"]["llm_calls"] == 5
    assert [(row["id"], row["status"]) for row in after["rows"]] == [
        (before["rows"][0]["id"], "pending"), (before["rows"][1]["id"], "complete")]
    assert after["rows"][0] == before["rows"][0]
    assert [row["request_index"] for row in released["continuation"]["units"]] == [0]
    assert [row["state"] for row in released["continuation"]["coverage"]] == [
        "ok", "unavailable"]
    visible = json.dumps(released["elements"])
    assert "does not complete the requested legal assessment" not in visible
    saved = wired.store.load(first["matter_id"])
    assert saved.closure == {}
    assert len(saved.brain_chat) == 2
    assert saved.brain_chat[-1]["message"] == next_words
    assert model.calls[-1][1]["units"][0]["request_index"] == 1


def test_public_selected_answer_source_is_bound_to_displayed_owner_and_saved_once(
        client, wired, monkeypatch):
    answer = ("I have considered your scope question. "
              "Please provide a neutral summary of the reported account.")

    def reconcile(payload):
        task_id, question_id = work_ids(payload)
        return {"units": [response(existing=task_id, text="You have chosen a neutral summary.",
                                   updates=[update(question_id, "complete", spans=("L2",))])]}

    model = wire(wired, monkeypatch,
                 [route(FIRST, opening=True), route(answer, intent="contribution")],
                 [{"units": [response(create=True, question=True)]}, reconcile])
    first = send(client, FIRST, "source-binding-open")
    answered = send(client, answer, "source-binding-answer", opened=first)
    projected = progress(wired, answered)

    assert answered["metrics"]["llm_calls"] == 3
    assert projected["rows"][1]["status"] == "complete"
    unit = answered["continuation"]["units"][0]
    assert unit["blocks"][0]["span_ids"] == ["L1", "L2"]
    assert unit["progress_updates"][0]["span_ids"] == ["L2"]
    assert [row["text"] for row in unit["blocks"][0]["references"]] == [
        "I have considered your scope question.",
        "Please provide a neutral summary of the reported account."]
    checked = [payload for operation, payload in model.calls
               if operation == "verify_continuation"][-1]
    assert checked["units"][0]["blocks"][0]["span_ids"] == ["L1", "L2"]
    saved = wired.store.load(first["matter_id"])
    assert len(saved.brain_chat) == 2
    assert saved.brain_chat[-1]["response"]["continuation"] == answered["continuation"]


def test_public_redisplayed_completed_scope_is_checked_without_new_completion_event(
        client, wired, monkeypatch):
    first_words = "The transaction is disputed. Please give a neutral summary of that account."
    requested = "Show that same summary again."
    summary = "Your reported account says that the transaction is disputed."
    delivered = response(create=True, text=summary, complete=True,
                         updates=[update("$work", "complete")])

    def redisplayed(payload):
        task = payload["progress"]["rows"][0]
        assert task["status"] == "complete"
        return {"units": [response(existing=task["id"], text=summary, complete=True,
                                   spans=("P1S1",))]}

    model = wire(wired, monkeypatch,
                 [route(first_words, opening=True), route(requested)],
                 [{"units": [delivered]}, redisplayed])
    first = send(client, first_words, "idempotent-complete")
    before = progress(wired, first)
    repeated = send(client, requested, "idempotent-redisplay", opened=first)
    after = progress(wired, repeated)

    assert first["metrics"]["llm_calls"] == 7
    assert repeated["metrics"]["llm_calls"] == 3
    assert after == before
    assert len(after["rows"]) == 1
    unit = repeated["continuation"]["units"][0]
    assert unit["work"]["progress_id"] == before["rows"][0]["id"]
    assert unit["progress_updates"] == []
    assert unit["blocks"][0]["references"][0]["turn_id"] == "idempotent-complete"
    assert model.calls[-1][0] == "verify_continuation"
    checked = model.calls[-1][1]
    assert checked["units"][0]["blocks"][0]["text"] == summary
    assert checked["input"]["latest_message_spans"][0]["text"] == requested
    saved = wired.store.load(first["matter_id"])
    assert len(saved.brain_chat) == 2
    assert saved.closure == {}


def test_public_complete_scoped_summary_keeps_broader_assessment_pending_with_three_calls(
        client, wired, monkeypatch):
    first_words = ("The transaction is disputed. Please assess the legal position and available "
                   "legal responses.")
    requested = "First give me a neutral summary of the reported account."

    def narrow_reply(payload):
        task = payload["progress"]["rows"][0]
        return {"units": [response(existing=task["id"], complete=True, spans=("P1S1",),
                                   text="Your reported account says the transaction is disputed.")]}

    model = wire(wired, monkeypatch,
                 [route(first_words, opening=True), route(requested)],
                 [{"units": [response(create=True)]}, narrow_reply])
    first = send(client, first_words, "scope-independence-open")
    before = progress(wired, first)
    immediate = send(client, requested, "scope-independence-summary", opened=first)

    assert immediate["metrics"]["llm_calls"] == 3
    assert immediate["blocked"] is False
    assert progress(wired, immediate) == before
    assert before["rows"][0]["status"] == "pending"
    unit = immediate["continuation"]["units"][0]
    assert unit["sufficiency"]["status"] == "complete"
    assert unit["progress_updates"] == []
    assert unit["work"]["progress_id"] == before["rows"][0]["id"]
    checked = model.calls[-1][1]
    assert checked["input"]["progress"]["rows"][0]["text"] == first_words
    assert checked["input"]["latest_message_spans"][0]["text"] == requested
    assert checked["units"][0]["sufficiency"]["status"] == "complete"
    assert wired.store.load(first["matter_id"]).closure == {}


@pytest.mark.parametrize("damage", ["version", "identity", "source", "display"])
def test_public_corrupt_progress_stops_before_models_and_save(
        client, wired, monkeypatch, damage):
    model = wire(wired, monkeypatch, [route(FIRST, opening=True)],
                 [{"units": [response(create=True, question=True)]}])
    first = send(client, FIRST, f"corrupt-open-{damage}")
    matter = wired.store.load(first["matter_id"])
    changed = deepcopy(matter.brain_chat[0])
    unit = changed["response"]["continuation"]["units"][0]
    if damage == "version":
        unit.pop("progress_version")
    elif damage == "identity":
        unit["work"]["progress_id"] = "wp_unowned_identity"
    elif damage == "source":
        unit["blocks"][0]["references"][0]["text"] = "Substituted account."
    else:
        unit["blocks"][0]["text"] = "A substituted displayed conclusion."
    tampered = replace(matter, brain_chat=(changed,), version=matter.version + 1)
    wired.store.commit(tampered, expected_version=matter.version)
    calls_before = len(model.calls)

    refused = client.post("/api/turn", json={
        "message": "Continue the review.", "turn_id": f"corrupt-followup-{damage}",
        "matter_id": first["matter_id"], "chat_id": first["chat_id"]})

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["committed"] == "not_committed"
    assert len(model.calls) == calls_before
    assert wired.store.load(first["matter_id"]).version == tampered.version
    assert len(wired.store.load(first["matter_id"]).brain_chat) == 1
