"""Approved private views never turn the metadata POST into client advice.

The served path also makes an independent working-scope read. This transport
test leaves that substantive assessment unresolved rather than scripting a
false claim that the advocate's legal request has been completed.
"""
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from nm.arrive.advocate_contracts import utcnow
from nm.legal_brain.orchestrate.loop_contracts import LoopMode
from nm.legal_brain.verify.brain_release import ReviewService
from nm.legal_brain.verify.interaction_review import COMMUNICATION_REVIEW_SCHEMA
from nm.legal_brain.verify.verifier import IndependentVerifier
from nm.legal_brain.verify.working_scope import CHECK_NAME, WORKING_SCOPE_SCHEMA
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage
from nm.shared.store_loop_log import MatterLoopLog
from tests.test_interaction_words_require_an_independent_exact_review import InteractionJudge
from tests.test_private_brain_transport_cannot_approve_or_release_itself import (
    PRIVATE,
    configured,
    path,
    request,
)
from tests.test_working_record_is_source_owned_and_independently_scoped import _scope_answer

pytestmark = pytest.mark.class_a


class PreviewJudge(InteractionJudge):
    """Assess communication, but do not self-certify unfinished legal work."""

    def __init__(self, mutation):
        super().__init__(mutation)
        self.scope_prompts = []

    def structured(self, prompt, schema, tier, **kwargs):
        if schema != WORKING_SCOPE_SCHEMA:
            return super().structured(prompt, schema, tier, **kwargs)
        assert tier is Tier.JUDGE
        self.scope_prompts.append(prompt)
        data = _scope_answer(json.loads(prompt.user))
        data["population_assessed"] = None
        data["comprehensive"]["assessed"] = None
        for row in data["judgments"]:
            row["needed"] = row["covered"] = None
            row["reason"] = "No substantive working-scope judgment in this transport test"
        return ModelResult(None, data, tier, self.provider, self.resolved_model(tier),
                           Usage(40, 40, 0.02), 0, completion=Completion.COMPLETE)


def approved(client, mutation=lambda raw: raw):
    app, matter, grant, author = configured(client)
    judges = []

    def reviewer(application, scope, current):
        judge = PreviewJudge(mutation)
        judges.append(judge)
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=scope.advocate_id),
            verifier=IndependentVerifier(judge), session_current=current,
            cost_ceiling=grant.cost_ceiling)

    app.controlled_evaluations = (replace(grant, reviewer_factory=reviewer,
                                         review_interactions=True),)
    return app, matter, author, judges


def preview(matter):
    return f"/api/matters/{matter.id}/brain/reviewed-preview/private-request"


def test_actual_post_stays_private_but_separate_checked_read_reuses_exact_saved_review(client):
    app, matter, author, judges = approved(client)
    before = client.get(preview(matter))
    assert before.status_code == 200 and not before.json()["paragraphs"]
    assert not judges[0].prompts and author.tool_call.call_count == 0
    posted = client.post(path(matter), json=request(matter))
    assert posted.status_code == 200 and PRIVATE not in posted.text
    assert posted.json()["result_state"] == "not_released"
    shown = client.get(preview(matter))
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert body["paragraphs"] == [{"text": PRIVATE, "references": []}]
    assert body["result_state"] == "checked_private_interaction"
    assert body["evaluation_only"] is True
    assert body["released"] is body["client_ready"] is False
    assert "not client advice" in body["marker"]
    assert shown.headers["cache-control"] == "no-store"
    saved = app.store.load(matter.id)
    assert len(saved.loop_records) == 3 and not saved.turn_receipts and not saved.asked
    scope_record = next(row for row in saved.loop_records
                        if row.identity.turn_id.endswith(f":check:{CHECK_NAME}"))
    assert scope_record.terminal
    assert scope_record.events[-1].payload["data"]["population_assessed"] is None
    assert author.tool_call.call_count == 1
    assert sum(len(j.prompts) for j in judges) == 1
    assert sum(len(j.scope_prompts) for j in judges) == 1
    assert client.get(preview(matter)).json() == body
    assert app.store.load(matter.id) == saved
    assert sum(len(j.prompts) for j in judges) == 1
    assert sum(len(j.scope_prompts) for j in judges) == 1


@pytest.mark.parametrize("state", ["absent", "expired", "client_mode", "revoked", "foreign"])
def test_actual_read_cannot_borrow_scope_session_or_client_approval(client, state):
    app, matter, author, judges = approved(client)
    grant = app.controlled_evaluations[0]
    actor = client
    if state == "absent":
        app.controlled_evaluations = ()
    elif state == "expired":
        app.controlled_evaluations = (replace(grant, expires_at=utcnow()-timedelta(seconds=1)),)
    elif state == "client_mode":
        app.controlled_evaluations = (replace(grant, scope=replace(grant.scope,
                                                                 mode=LoopMode.RECORDED)),)
    elif state == "revoked":
        assert client.post("/api/logout").status_code == 200
    else:
        actor = client.sign_in("someone_else", fresh=True)
    response = actor.get(preview(matter))
    assert response.status_code in {401, 403, 404}
    assert PRIVATE not in response.text and author.tool_call.call_count == 0
    assert not judges and not app.store.load(matter.id).loop_records


def test_missing_interaction_owner_does_not_become_a_wording_pass(client):
    app, matter, _, _ = approved(client)
    app.controlled_evaluations = (
        replace(app.controlled_evaluations[0], review_interactions=False),)
    assert client.post(path(matter), json=request(matter)).status_code == 200
    response = client.get(preview(matter))
    assert response.status_code == 200
    assert response.json()["result_state"] == "wording_review_pending"
    assert not response.json()["paragraphs"] and PRIVATE not in response.text


def test_actual_application_records_only_the_exact_checked_private_display(client):
    app, matter, author, judges = approved(client)
    assert client.post(path(matter), json=request(matter)).status_code == 200
    shown = client.get(preview(matter))
    assert shown.status_code == 200 and shown.json()["paragraphs"]
    before = app.store.load(matter.id)
    seen = client.post(f"{preview(matter)}/seen", json={})
    assert seen.status_code == 200, seen.text
    saved = app.store.load(matter.id)
    assert saved.version == before.version + 2
    assert seen.json()["matter_version"] == saved.version
    assert seen.json()["result_state"] == "private_preview_display_recorded"
    assert seen.json()["released"] is seen.json()["client_ready"] is False
    assert PRIVATE not in seen.text
    assert saved.facts == before.facts and saved.asked == before.asked
    assert not saved.turn_receipts
    assert client.post(f"{preview(matter)}/seen", json={}).json() == seen.json()
    assert app.store.load(matter.id) == saved
    assert author.tool_call.call_count == 1
    assert sum(len(j.prompts) for j in judges) == 1
    assert sum(len(j.scope_prompts) for j in judges) == 1


@pytest.mark.parametrize("body", [{"text": PRIVATE}, {"approved": True}, {"released": True}])
def test_actual_display_route_cannot_accept_supplied_words_or_approval(client, body):
    app, matter, author, judges = approved(client)
    before = app.store.load(matter.id)
    refused = client.post(f"{preview(matter)}/seen", json=body)
    assert refused.status_code == 422 and PRIVATE not in refused.text
    assert app.store.load(matter.id) == before
    assert author.tool_call.call_count == 0 and not judges


def test_actual_display_route_keeps_csrf_and_missing_review_boundaries(client):
    app, matter, author, _ = approved(client)
    before = app.store.load(matter.id)
    assert client.post(f"{preview(matter)}/seen", json={},
                       headers={"x-nm-csrf": "wrong"}).status_code == 403
    assert client.post(f"{preview(matter)}/seen", json={}).status_code == 409
    assert app.store.load(matter.id) == before and author.tool_call.call_count == 0


def test_distinct_verifier_facade_admits_only_the_owned_communication_schema():
    from copy import deepcopy
    from unittest.mock import Mock

    from nm.legal_brain.evaluate.evaluation_models import VerifierOnly
    from nm.shared.external_ai_contracts import ModelPermissionRefused
    from nm.shared.model_port import Prompt

    inner = Mock()
    verifier = VerifierOnly(inner)
    verifier.structured(Prompt("Only supplied words"), deepcopy(COMMUNICATION_REVIEW_SCHEMA),
                        Tier.JUDGE, max_tokens=2048)
    assert inner.structured.call_count == 1
    altered = deepcopy(COMMUNICATION_REVIEW_SCHEMA)
    altered["properties"]["new_answer"] = {"type": "string"}
    with pytest.raises(ModelPermissionRefused):
        verifier.structured(Prompt("Write an answer"), altered, Tier.JUDGE)
    assert inner.structured.call_count == 1
