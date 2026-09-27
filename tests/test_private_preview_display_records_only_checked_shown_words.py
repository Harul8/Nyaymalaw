"""Actual owned preview/journal + labelled controlled ASGI acknowledgements."""
from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from nm.core.brain_finalization import SavedCheckReader
from nm.core.brain_release import ReviewRefused
from nm.core.interaction_review import InteractionReviewService
from nm.core.interaction_subject import InteractionSubjectOwner
from nm.core.preview_display import displayed_questions
from nm.core.preview_seen import PreviewSeenService
from nm.domain.budget import Budget
from nm.domain.loop import LoopLimits, LoopMode
from nm.edge.preview_seen import router
from nm.ports.model import ToolCall
from nm.ports.store import StaleWrite

from tests.test_independent_claim_verifier import premise
from tests.test_interaction_words_require_an_independent_exact_review import InteractionJudge
from tests.test_reviewed_private_preview_checks_saved_words import (
    changed_payload,
    ready,
    replace_record,
)
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
PATH = "/api/matters/mat_loop/brain/reviewed-preview/shown_question/seen"
QUESTION = "Which date was the notice sent?"


def _question(tmp_path, *, checked=True):
    store, brain, _, _, preview, _, _ = ready(tmp_path, terminal="ask_advocate")
    brain.model.tool_call.side_effect = [replace(_response(ToolCall(
        "question", "ask_advocate", {"question": QUESTION})), model="scripted:author")]
    outcome = brain.run(matter_id="mat_loop", turn_id="shown_question", message=
        "Ask what is needed to understand whether notice was sent.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    judge = InteractionJudge()
    owner = InteractionSubjectOwner(principles=brain.principles)
    brain.interaction_review = InteractionReviewService(reader=SavedCheckReader(
        store=store, log=brain.log, model=judge, session_current=lambda: True,
        cost_ceiling=lambda *_: 0.03, current_tools_version=lambda: brain.registry.version,
        current_principles_version=lambda: brain.principles.load().version,
        subject_packages=owner.packages, max_tokens=2048), owner=owner)
    if checked:
        brain.interaction_review.review(outcome)
    return store, brain, outcome, preview, PreviewSeenService(preview=preview, log=brain.log), judge


def acknowledge(service):
    return service.record(actor="adv_loop", matter_id="mat_loop", turn_id="shown_question")


def test_actual_checked_question_display_is_private_sealed_idempotent_and_not_normal_delivery(
        tmp_path):
    store, brain, outcome, preview, service, judge = _question(tmp_path)
    original = store.load("mat_loop")
    reviewed = brain.interaction_review.recorded(outcome)
    assert preview.read(actor="adv_loop", matter_id="mat_loop", turn_id="shown_question").paragraphs
    first = acknowledge(service)
    saved = store.load("mat_loop")
    assert saved.version == original.version + 2
    assert saved.facts == original.facts and saved.asked == original.asked
    assert not saved.turn_receipts and not store.transcripts_for("mat_loop")
    row = next(row for row in saved.loop_records if row.identity.turn_id == first.receipt_id)
    assert row.terminal and len(row.events) == 2
    assert row.events[-1].payload["released"] is False
    assert row.events[-1].payload["client_ready"] is False
    assert QUESTION not in row.events[0].payload_json + row.events[-1].payload_json
    assert first.as_dict()["result_state"] == "private_preview_display_recorded"
    judge.structured = lambda *_args, **_kwargs: pytest.fail("Display/replay cannot spend")
    assert acknowledge(service) == first
    assert store.load("mat_loop") == saved
    # Own acknowledgement does not restale its check.
    assert brain.interaction_review.recorded(outcome) == reviewed


def test_next_actual_loop_context_sees_only_previously_displayed_questions(tmp_path):
    store, brain, _, _, service, _ = _question(tmp_path)
    acknowledge(service)
    brain.model.tool_call.side_effect = [replace(_response(ToolCall(
        "ack", "propose_conversation", {"text": "Understood."})), model="scripted:author")]
    outcome = brain.run(matter_id="mat_loop", turn_id="next_turn", message="Thank you.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    subject = brain.interaction_review.owner.build(outcome, store.load("mat_loop"))
    assert subject.payload["delivered_questions"] == []  # No ordinary client-delivery claim.
    shown = subject.payload["displayed_private_questions"]
    assert len(shown) == 1 and shown[0]["text"] == QUESTION
    assert shown[0]["state"] == "historical_private_preview_display_not_current_legal_validity"
    assert not store.load("mat_loop").asked


def test_unseen_private_question_candidates_never_populate_display_history(tmp_path):
    store, brain, outcome, _, _, _ = _question(tmp_path)
    subject = brain.interaction_review.owner.build(outcome, store.load("mat_loop"))
    assert subject.payload["displayed_private_questions"] == []
    matter = store.load("mat_loop")
    assert displayed_questions(matter, before_version=matter.version,
                               selected_issue_ids=()) == ()


def test_a_historical_display_is_not_erased_when_the_case_is_later_corrected(tmp_path):
    store, brain, _, _, service, _ = _question(tmp_path)
    acknowledge(service)
    current = store.load("mat_loop")
    corrected = replace(premise(), statement="The certificate is disputed.")
    store.commit(replace(current, facts=(corrected,),
                         version=current.version + 1), expected_version=current.version)
    with pytest.raises(ReviewRefused):
        acknowledge(service)  # It is no longer a current checked preview.
    brain.model.tool_call.side_effect = [replace(_response(ToolCall(
        "ack", "propose_conversation", {"text": "Understood."})), model="scripted:author")]
    next_turn = brain.run(matter_id="mat_loop", turn_id="corrected_turn", message=
        "Use the correction rather than the earlier account.",
        limits=LoopLimits(Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1), 12, 400))
    subject = brain.interaction_review.owner.build(next_turn, store.load("mat_loop"))
    assert subject.payload["displayed_private_questions"][0]["text"] == QUESTION
    assert subject.payload["checked_file"]["facts"][0]["statement"] == (
        "The certificate is disputed.")


@pytest.mark.parametrize("what", ["owner", "scope", "mode", "grant", "session", "principles"])
def test_foreign_unapproved_revoked_or_changed_preview_cannot_be_acknowledged(tmp_path, what):
    store, brain, _, preview, service, _ = _question(tmp_path)
    args = {"actor": "adv_loop", "matter_id": "mat_loop", "turn_id": "shown_question"}
    if what == "owner":
        args["actor"] = "another"
    elif what == "scope":
        brain.scope = replace(brain.scope, matter_ids=frozenset({"other"}))
    elif what == "mode":
        brain.scope = replace(brain.scope, mode=LoopMode.RECORDED)
    elif what == "grant":
        preview.current = lambda: False
    elif what == "session":
        brain._session_current = lambda: False
    else:
        brain.interaction_review.reader.current_principles_version = lambda: "changed"
    before = store.load("mat_loop")
    with pytest.raises((PermissionError, ReviewRefused)):
        service.record(**args)
    assert store.load("mat_loop") == before


def test_no_independent_wording_review_means_no_display_receipt(tmp_path):
    store, _, _, _, service, _ = _question(tmp_path, checked=False)
    before = store.load("mat_loop")
    with pytest.raises(ReviewRefused, match="No checked"):
        acknowledge(service)
    assert store.load("mat_loop") == before


def test_real_merits_preview_display_requires_actual_full24_atomic_publication(tmp_path):
    store, brain, _, assessment, preview, _, _ = ready(tmp_path)
    assert assessment.checks_complete
    service = PreviewSeenService(preview=preview, log=brain.log)
    receipt = service.record(actor="adv_loop", matter_id="mat_loop", turn_id="private-turn")
    assert receipt.as_dict()["released"] is False and not store.load("mat_loop").turn_receipts
    matter = store.load("mat_loop")
    assert displayed_questions(matter, before_version=matter.version,
                               selected_issue_ids=()) == ()  # Not every paragraph is a question.


@pytest.mark.parametrize("what", ["word_hash", "parent", "proof", "release", "scope"])
def test_changed_display_receipts_do_not_become_authenticated_question_history(tmp_path, what):
    store, _, _, _, service, _ = _question(tmp_path)
    acknowledge(service)

    def alter(record):
        payload = record.events[0].payload
        binding = dict(payload["binding"])
        if what == "release":
            return changed_payload(record, 1, released=True)
        if what == "scope":
            binding["scope"] = {**binding["scope"], "advocate_id": "another"}
        else:
            binding[{"word_hash": "words_identity", "parent": "parent", "proof": "proof"}[what]] = (
                "forged")
        return changed_payload(record, 0, binding=binding)
    replace_record(store, "shown_question:preview_seen", alter)
    with pytest.raises(ReviewRefused):
        matter = store.load("mat_loop")
        displayed_questions(matter, before_version=matter.version,
                            selected_issue_ids=())


@pytest.mark.parametrize("what", ["dispatch", "spend", "downgrade", "stop", "offer"])
def test_historical_question_review_requires_actual_dispatch_spend_and_identity(tmp_path, what):
    from nm.core.preview_display import interaction_text
    from nm.domain.loop import LoopEvent, LoopRecord

    store, _, _, _, _, _ = _question(tmp_path)
    matter = store.load("mat_loop")
    parent = next(row for row in matter.loop_records
                  if row.identity.turn_id == "shown_question")
    proof = next(row for row in matter.loop_records
                 if row.identity.turn_id == "shown_question:check:communication")
    assert interaction_text(parent, proof)[0] == QUESTION
    if what == "dispatch":
        prompt = {**proof.events[1].payload["prompt"], "user": "Different unchecked subject"}
        changed = changed_payload(proof, 1, prompt=prompt)
    elif what == "spend":
        spend = {**proof.events[-1].payload["spend"], "tokens": 0}
        changed = changed_payload(proof, len(proof.events) - 1, spend=spend)
    elif what == "downgrade":
        result = {**proof.events[2].payload["result"], "downgraded_from": "hard"}
        changed = changed_payload(proof, 2, result=result)
    elif what == "stop":
        changed = changed_payload(proof, len(proof.events) - 1, stop="boundary_refused")
    else:
        identity = replace(proof.identity, offer_hash="0" * 64)
        events, previous = [], identity.fingerprint
        for event in proof.events:
            rebuilt = LoopEvent.create(event.sequence, event.kind, event.at,
                                       event.payload, previous)
            events.append(rebuilt)
            previous = rebuilt.fingerprint
        changed = LoopRecord(identity, tuple(events))
    assert changed != proof  # A rejecting control must actually change its owned field.
    with pytest.raises(ReviewRefused):
        interaction_text(parent, changed)


@pytest.mark.parametrize("what", ["session", "principles", "file"])
def test_late_boundary_loss_leaves_only_an_incomplete_acknowledgement_not_asked_history(
        tmp_path, what):
    store, brain, _, _, service, _ = _question(tmp_path)
    append = brain.log.append

    def lose_boundary(identity, event):
        result = append(identity, event)
        if identity.turn_id.endswith(":preview_seen") and event.sequence == 1:
            if what == "session":
                brain._session_current = lambda: False
            elif what == "principles":
                brain.interaction_review.reader.current_principles_version = lambda: "changed"
            else:
                current = store.load("mat_loop")
                store.commit(replace(current, version=current.version + 1),
                             expected_version=current.version)
        return result

    brain.log.append = lose_boundary
    with pytest.raises((ReviewRefused, StaleWrite, PermissionError)):
        acknowledge(service)
    matter = store.load("mat_loop")
    row = next(row for row in matter.loop_records if row.identity.turn_id.endswith(":preview_seen"))
    assert not row.terminal and len(row.events) == 1
    assert displayed_questions(matter, before_version=matter.version, selected_issue_ids=()) == ()
    assert not matter.asked and not matter.turn_receipts


def test_concurrent_file_change_refuses_receipt_without_overwriting_or_authoring_delivery(tmp_path):
    store, _, _, preview, service, _ = _question(tmp_path)
    original = preview.read
    calls = 0

    def change(**arguments):
        nonlocal calls
        result = original(**arguments)
        calls += 1
        if calls == 2:
            current = store.load("mat_loop")
            store.commit(replace(current, version=current.version + 1),
                         expected_version=current.version)
        return result
    preview.read = change
    with pytest.raises(StaleWrite):
        acknowledge(service)
    assert not any(row.identity.turn_id.endswith(":preview_seen")
                   for row in store.load("mat_loop").loop_records)
    assert not store.load("mat_loop").asked and not store.load("mat_loop").turn_receipts


def configured(tmp_path, *, checked=True):
    store, brain, _, preview, _, _ = _question(tmp_path, checked=checked)
    state = {"active": True, "grant": True}

    def signed(request: Request):
        if request.headers.get("x-test-session") != "active" or not state["active"]:
            raise HTTPException(401, "Sign in again.")
        return "adv_loop"

    def csrf(request: Request):
        if request.headers.get("x-test-csrf") != "same-session":
            raise HTTPException(403, "Wrong session CSRF.")

    def owned(ident, actor):
        matter = store.load(ident)
        if matter is None or matter.advocate_id != actor:
            raise HTTPException(404, "Matter unavailable.")
        return matter

    def record(*, session_current, **arguments):
        if state.get("failure"):
            raise state["failure"]
        preview.current = lambda: state["grant"] and session_current()
        receipt = PreviewSeenService(preview=preview, log=brain.log).record(**arguments)
        if state.get("after"):
            state["after"]()
        return receipt

    app = FastAPI()
    app.include_router(router(owned=owned, signed_in=signed, csrf_protected=csrf,
        session_current=lambda *_: state["active"], record=record))
    return TestClient(app, headers={"x-test-session": "active", "x-test-csrf": "same-session"}), (
        store, brain, state)


def test_served_display_receipt_is_structural_uncacheable_and_not_client_history(tmp_path):
    client, (store, _, _) = configured(tmp_path)
    result = client.post(PATH, json={})
    assert result.status_code == 200, result.text
    assert result.json()["result_state"] == "private_preview_display_recorded"
    assert result.json()["released"] is False and result.json()["client_ready"] is False
    assert QUESTION not in result.text
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["x-content-type-options"] == "nosniff"
    assert not store.load("mat_loop").asked and not store.load("mat_loop").turn_receipts


@pytest.mark.parametrize("field", ["text", "approved", "PASS", "scope", "display_identity",
                                 "actor", "version"])
def test_http_cannot_author_checked_words_approval_or_display_identity(tmp_path, field):
    client, (store, _, _) = configured(tmp_path)
    before = store.load("mat_loop")
    response = client.post(PATH, json={field: "authored"})
    assert response.status_code == 422
    assert store.load("mat_loop") == before


@pytest.mark.parametrize("what", ["session", "csrf", "foreign", "grant", "pending"])
def test_http_requires_current_session_csrf_finite_grant_owned_file_and_actual_review(
        tmp_path, what):
    client, (store, _, state) = configured(tmp_path, checked=what != "pending")
    path = PATH
    if what == "session":
        state["active"] = False
    elif what == "csrf":
        client.headers["x-test-csrf"] = "wrong"
    elif what == "foreign":
        path = PATH.replace("mat_loop", "foreign")
    elif what == "grant":
        state["grant"] = False
    before = store.load("mat_loop")
    result = client.post(path, json={})
    assert result.status_code == {"session": 401, "csrf": 403, "foreign": 404,
                                  "grant": 403, "pending": 409}[what]
    assert QUESTION not in result.text and store.load("mat_loop") == before


def test_late_http_logout_or_file_movement_does_not_return_a_stale_receipt(tmp_path):
    client, (store, _, state) = configured(tmp_path)
    state["after"] = lambda: state.__setitem__("active", False)
    assert client.post(PATH, json={}).status_code == 401
    state["active"] = True

    def move():
        current = store.load("mat_loop")
        store.commit(replace(current, version=current.version + 1),
                     expected_version=current.version)
    state["after"] = move
    assert client.post(PATH, json={}).status_code == 409


def test_error_details_do_not_disclose_private_preview_words(tmp_path):
    client, (_, _, state) = configured(tmp_path)
    state["failure"] = ReviewRefused("WITHHELD PRIVATE RESPONSE TEXT")
    response = client.post(PATH, json={})
    assert response.status_code == 409 and "WITHHELD" not in response.text
    assert response.headers["cache-control"] == "no-store"
