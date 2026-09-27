"""Recorded work can retain repairs without borrowing fictional preview rights."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nm.legal_brain.evaluate.brain_evaluation import EvaluationResult
from nm.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.legal_brain.evaluate.evaluation_history import record_repaired_evaluation, resolve_preview_parent
from nm.legal_brain.orchestrate.loop import _budget_from
from nm.legal_brain.orchestrate.loop_contracts import (
    LoopEvent,
    LoopMode,
    LoopOutcome,
    LoopRecord,
    StopReason,
    digest,
)
from nm.legal_brain.verify.verifier import IndependentVerifier
from nm.legal_brain.verify.working_scope import WORKING_SCOPE_SCHEMA
from nm.shared.budget_contracts import Budget, Completion
from nm.shared.model_port import ModelResult, Tier, ToolCall, Usage
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
REPAIRED_WORDS = "Which record supplies the date you want assessed?"


class ModeJudge(WorkJudge):
    """The mode fixture assesses wording, not completeness of the legal work."""

    def structured(self, prompt, schema, tier, **kwargs):
        if schema != WORKING_SCOPE_SCHEMA:
            return super().structured(prompt, schema, tier, **kwargs)
        assert tier is Tier.JUDGE and prompt.operation == "working_scope_v1"
        packet = json.loads(prompt.user)
        inventory = packet["subject"]["inventory"]
        sources = packet["subject"]["quote_sources"]
        references = {row["reference"]["id"]: row["reference"] for row in inventory["references"]}
        words = [{"source_id": "original_instruction", "quote": sources["original_instruction"]}]
        reason = "This wording/mode fixture does not establish request completeness."
        judgments = []
        for row in (*inventory["areas"], *inventory["needs"]):
            reference = (
                row["reference"]["id"]
                if "reference" in row
                else "thread:" + row["thread_id"]
                if row["thread_id"] is not None
                else "original_instruction"
            )
            judgments.append(
                {
                    "id": row["id"],
                    "needed": None,
                    "covered": None,
                    "reason": reason,
                    "supporting_words": words,
                    "references": [references[reference]],
                    "annotation_ids": [],
                }
            )
        data = {
            "subject_identity": packet["subject_identity"],
            "request_identity": digest(inventory["original_instruction"]),
            "population_assessed": None,
            "comprehensive": {"assessed": None, "reason": reason, "supporting_words": words},
            "judgments": judgments,
            "reason": reason,
        }
        return ModelResult(
            None,
            data,
            tier,
            self.provider,
            self.resolved_model(tier),
            Usage(80, 80, 0.02),
            1,
            completion=Completion.COMPLETE,
        )


def _completed(client, mode):
    app, matter, author, _ = approved(client)
    count, judges = [0], []

    def mutation(raw):
        count[0] += 1
        if count[0] == 1:
            raw["relevance"]["assessed"] = False
            raw["relevance"]["reason"] = "The initial controlled wording missed the request."
        return raw

    def reviewer(application, scope, current):
        judge = ModeJudge(mutation)
        judges.append(judge)
        return ReviewService(
            store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge),
            session_current=current,
            cost_ceiling=app.controlled_evaluations[0].cost_ceiling,
        )

    grant = app.controlled_evaluations[0]
    app.controlled_evaluations = (
        replace(
            grant,
            scope=replace(grant.scope, mode=mode),
            reviewer_factory=reviewer,
            interaction_protocol_version=4,
            max_repairs=2,
            limits=replace(
                grant.limits, budget=Budget(max_ms=60000, max_tokens=100000, max_cost_usd=1)
            ),
        ),
    )
    author.tool_call.side_effect = [
        _response(ToolCall("initial", "ask_advocate", {"question": PRIVATE})),
        _response(ToolCall("reconsidered", "ask_advocate", {"question": REPAIRED_WORDS})),
    ]
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200, posted.text
    assert PRIVATE not in posted.text and REPAIRED_WORDS not in posted.text
    saved = app.store.load(matter.id)
    actual = next(
        row
        for row in saved.loop_records
        if row.identity.turn_id == "private-request:evaluation_result"
    )
    body = actual.events[-1].payload
    records = [
        next(row for row in saved.loop_records if row.identity.turn_id == ref["turn_id"])
        for ref in body["attempts"]
    ]
    attempts = tuple(
        LoopOutcome(
            StopReason(row.events[-1].payload["reason"]),
            row,
            _budget_from(row.events[-1].payload["budget"]),
            row.events[-1].payload["proposal"],
        )
        for row in records
    )
    result = EvaluationResult(
        attempts, (), _budget_from(body["budget"]), body["stop"], tuple(body["limitations"])
    )
    return app, matter, saved, result, author, judges


@pytest.mark.parametrize("mode", tuple(LoopMode))
def test_served_repairs_keep_the_original_mode_without_granting_a_client_view(client, mode):
    app, matter, saved, result, author, judges = _completed(client, mode)
    assert result.stop == "interaction_checks_complete_private_candidate"
    assert len(result.attempts) == 2
    assert all(row.identity.mode is mode for row in saved.loop_records)
    assert not saved.turn_receipts and not saved.asked
    assert saved.facts == matter.facts and saved.threads == matter.threads
    assert saved.loop_records[-1].events[-1].payload["released"] is False
    brain = SimpleNamespace(
        store=app.store, log=MatterLoopLog(app.store, advocate_id=matter.advocate_id)
    )
    record_repaired_evaluation(brain, result, "private-request")
    assert app.store.load(matter.id) == saved  # Exact neutral recorder replay is read-only.
    if mode is LoopMode.RECORDED:
        with pytest.raises(ReviewRefused):
            resolve_preview_parent(saved, "private-request", brain.log)
        assert client.get(preview(matter)).status_code == 403
        assert client.post(f"{preview(matter)}/seen", json={}).status_code == 403
        assert app.store.load(matter.id) == saved
    else:
        shown = client.get(preview(matter))
        assert shown.status_code == 200, shown.text
        assert shown.json()["paragraphs"] == [{"text": REPAIRED_WORDS, "references": []}]
        assert client.post(f"{preview(matter)}/seen", json={}).status_code == 200
    assert author.tool_call.call_count == 2
    assert sum(len(judge.prompts) for judge in judges) == 2


def _rebind(record, identity):
    events, previous = [], identity.fingerprint
    for old in record.events:
        current = LoopEvent.create(old.sequence, old.kind, old.at, old.payload, previous)
        events.append(current)
        previous = current.fingerprint
    return LoopRecord(identity, tuple(events))


@pytest.mark.parametrize("mode", tuple(LoopMode))
@pytest.mark.parametrize("mutation", ["mode", "actor", "matter"])
def test_neutral_result_journaling_refuses_a_repair_with_a_different_owner_or_mode(
    client, mode, mutation
):
    _, matter, saved, result, _, _ = _completed(client, mode)
    parent = result.attempts[-1].record
    if mutation == "mode":
        alternate = LoopMode.RECORDED if mode is LoopMode.SYNTHETIC else LoopMode.SYNTHETIC
        identity = replace(parent.identity, mode=alternate)
    elif mutation == "actor":
        identity = replace(parent.identity, advocate_id="not-the-instructing-advocate")
    else:
        identity = replace(parent.identity, matter_id="not-the-admitted-matter")
    changed = _rebind(parent, identity)
    assert changed.identity != parent.identity
    view = replace(
        saved, loop_records=tuple(changed if row == parent else row for row in saved.loop_records)
    )
    altered = replace(
        result, attempts=(*result.attempts[:-1], replace(result.attempts[-1], record=changed))
    )
    store, log = Mock(), Mock()
    store.load.return_value = view
    log.read.side_effect = lambda ident: next(
        row for row in view.loop_records if row.identity.turn_id == ident.turn_id
    )
    with pytest.raises(ReviewRefused, match="exact owned saved attempt"):
        record_repaired_evaluation(
            SimpleNamespace(store=store, log=log), altered, "private-request"
        )
    log.append.assert_not_called()
