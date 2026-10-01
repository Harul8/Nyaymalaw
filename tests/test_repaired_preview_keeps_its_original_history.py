"""Repaired words reopen only through their original sealed private evaluation."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.Archives.legal_brain.evaluate.evaluation_history import resolve_preview_parent
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopRecord
from nm.Archives.legal_brain.communicate.preview_display import displayed_questions, interaction_text
from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
from nm.shared.budget_contracts import Budget
from nm.shared.model_port import ToolCall
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_communication_reviews_see_actual_work import WorkJudge
from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    path,
    request,
)
from tests.test_scoped_preview_uses_the_actual_application_boundary import approved, preview
from tests.test_the_loop_records_work_before_using_it import _response

pytestmark = pytest.mark.class_a
REPAIR = "Which record supplies the date you want assessed?"


def _repair(client, *, repeated=False):
    app, matter, author, _ = approved(client)
    count, judges = [0], []

    def judged(raw):
        count[0] += 1
        if count[0] == 1 or repeated:
            raw["relevance"]["assessed"] = False
            raw["relevance"]["reason"] = f"Actual controlled rejection {count[0]}"
        return raw

    def reviewer(application, scope, current):
        judge = WorkJudge(judged)
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling)

    grant = replace(app.controlled_evaluations[0], reviewer_factory=reviewer,
                    interaction_protocol_version=4, max_repairs=2,
                    limits=replace(app.controlled_evaluations[0].limits,
                        budget=Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1)))
    app.controlled_evaluations = (grant,)
    author.tool_call.side_effect = [
        _response(ToolCall("first", "ask_advocate", {"question": PRIVATE})),
        _response(ToolCall("second", "ask_advocate", {
            "question": PRIVATE if repeated else REPAIR}))]
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200, posted.text
    assert PRIVATE not in posted.text and REPAIR not in posted.text
    assert [row["turn_id"] for row in posted.json()["attempts"]] == [
        "private-request", "private-request:repair:1"]
    return app, matter, author, judges


def test_served_repair_reopens_with_original_input_without_relabeled_failures_or_paid_reads(client):
    app, matter, author, judges = _repair(client)
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert body["turn_id"] == "private-request"
    assert body["paragraphs"] == [{"text": REPAIR, "references": []}], (
        body, app.store.load(matter.id).loop_records[-1].events[-1].payload)
    assert body["original_instruction"]["text"] == request(matter)["message"]
    assert body["released"] is body["client_ready"] is False
    saved = app.store.load(matter.id)
    initial = next(row for row in saved.loop_records if row.identity.turn_id == "private-request")
    failed = next(row for row in saved.loop_records if row.identity.turn_id == (
        "private-request:check:communication_work"))
    assert failed.events[-1].payload["data"]["relevance"]["assessed"] is False
    with pytest.raises(ReviewRefused):
        interaction_text(initial, failed)
    assert client.post(f"{preview(matter)}/seen", json={}).status_code == 200
    latest = app.store.load(matter.id)
    history = displayed_questions(latest, before_version=latest.version, selected_issue_ids=())
    assert len(history) == 1 and history[0]["text"] == REPAIR
    assert history[0]["turn_id"] == "private-request:repair:1"
    for _ in range(2):
        assert client.get(preview(matter)).json()["paragraphs"] == body["paragraphs"]
        assert client.post(f"{preview(matter)}/seen", json={}).status_code == 200
    assert app.store.load(matter.id) == latest
    assert author.tool_call.call_count == 2 and sum(len(j.prompts) for j in judges) == 2
    assert not latest.turn_receipts and not latest.asked
    assert client.get(f"{preview(matter)}:repair:1").status_code == 422


def test_repeated_rejected_repair_never_becomes_a_visible_or_seen_response(client):
    app, matter, author, judges = _repair(client, repeated=True)
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    assert not shown.json()["paragraphs"]
    assert shown.json()["result_state"] == "wording_review_failed"
    assert PRIVATE not in shown.text
    assert client.post(f"{preview(matter)}/seen", json={}).status_code == 409
    saved = app.store.load(matter.id)
    result = next(row for row in saved.loop_records if row.identity.turn_id == (
        "private-request:evaluation_result"))
    assert result.events[-1].payload["stop"] == "no_progress"
    assert result.events[-1].payload["budget"]["spend"]["discarded_results"] == 1
    assert author.tool_call.call_count == 2 and sum(len(j.prompts) for j in judges) == 2


@pytest.mark.parametrize("mutation", ["attempt", "original", "parent", "missing", "release"])
def test_a_repair_selection_cannot_substitute_omit_or_promote_the_original(client, mutation):
    app, matter, _, _ = _repair(client)
    saved = app.store.load(matter.id)
    result = next(row for row in saved.loop_records if row.identity.turn_id == (
        "private-request:evaluation_result"))
    body = deepcopy(result.events[-1].payload)
    if mutation == "attempt":
        body["attempts"][-1]["terminal"] = "0" * 64
    elif mutation == "original":
        body["original_instruction_identity"] = "0" * 64
    elif mutation == "parent":
        body["attempts"][-1]["turn_id"] = "a-different-turn"
    elif mutation == "missing":
        body["attempts"] = body["attempts"][:1]
    else:
        body["released"] = True
    stop = LoopEvent.create(2, result.events[-1].kind, result.events[-1].at, body,
                             result.events[0].fingerprint)
    corrupt = LoopRecord(result.identity, (result.events[0], stop))
    view = replace(saved, loop_records=tuple(corrupt if row == result else row
                                             for row in saved.loop_records))
    with pytest.raises(ReviewRefused):
        resolve_preview_parent(view, "private-request")


def test_current_approval_loss_still_blocks_the_checked_repair_and_display(client):
    app, matter, author, judges = _repair(client)
    before = app.store.load(matter.id)
    app.controlled_evaluations = ()
    assert client.get(preview(matter)).status_code == 403
    assert client.post(f"{preview(matter)}/seen", json={}).status_code == 403
    assert app.store.load(matter.id) == before
    assert author.tool_call.call_count == 2 and sum(len(j.prompts) for j in judges) == 2
