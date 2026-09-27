"""Actual authenticated transport, configured grant, loop and saved progress."""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest
from nm.adapters.store.loop_log import MatterLoopLog
from nm.bootstrap.controlled_evaluations import (
    ControlledEvaluation,
    EvaluationUnavailable,
    grant_for,
)
from nm.core.brain_release import ReviewService
from nm.core.controlled_brain import EvaluationScope
from nm.core.verifier import IndependentVerifier
from nm.domain.advocate import utcnow
from nm.domain.loop import LoopMode
from nm.domain.matter import Matter
from nm.edge import api
from nm.ports.model import ToolCall

from tests.test_independent_claim_verifier import Judge
from tests.test_the_loop_records_work_before_using_it import _limits, _response

pytestmark = pytest.mark.class_a
PRIVATE = "UNRELEASED LEGAL QUESTION AND MODEL CONTENT"


def configured(client):
    app = api.application()
    matter = replace(Matter.create("adv_demo", "Controlled transport file"), version=1)
    app.store.commit(matter, expected_version=0)
    scope = EvaluationScope("OWNER-20260927-USD5", "adv_demo",
                            frozenset({matter.id}), LoopMode.SYNTHETIC)

    def reviewer(application, approved, current):
        return ReviewService(store=application.store,
            log=MatterLoopLog(application.store, advocate_id=approved.advocate_id),
            verifier=IndependentVerifier(Judge()), session_current=current,
            cost_ceiling=lambda *_: 0.03)

    grant = ControlledEvaluation(scope, _limits(), utcnow() + timedelta(hours=1),
        "controlled-source-generation", "controlled-table-generation",
        lambda *_: 0.03, reviewer, max_repairs=0)
    app.controlled_evaluations = (grant,)
    model = Mock()
    model.provider = "scripted"
    model.resolved_model.return_value = "recorded-v1"
    model.context_budget.return_value = 100000
    model.tool_call.return_value = _response(
        ToolCall("ask", "ask_advocate", {"question": PRIVATE}))
    app.model.inner.inner = model
    return app, matter, grant, model


def request(matter, **changes):
    return {"version": matter.version, "turn_id": "private-request",
            "message": "Review the recorded material.", **changes}


def path(matter):
    return f"/api/matters/{matter.id}/brain/preview"


def test_actual_route_records_work_but_cannot_transport_the_question_or_candidate(client):
    app, matter, _, model = configured(client)
    served = client.post(path(matter), json=request(matter))
    assert served.status_code == 200, served.text
    assert served.json()["result_state"] == "not_released"
    assert served.json()["client_ready"] is False
    assert served.json()["assessment_count"] == 0
    assert served.headers["cache-control"] == "no-store"
    assert PRIVATE not in served.text and "proposal" not in served.text
    saved = app.store.load(matter.id)
    assert len(saved.loop_records) == 1 and not saved.turn_receipts
    assert saved.loop_records[0].terminal and model.tool_call.call_count == 1
    stages = client.get(f"/api/matters/{matter.id}/loops/private-request")
    assert stages.status_code == 200 and PRIVATE not in stages.text
    assert client.post("/api/logout").status_code == 200
    assert client.get(f"/api/matters/{matter.id}/loops/private-request").status_code == 401


@pytest.mark.parametrize("extra", ["scope", "approval_reference", "limits", "max_repairs",
                                    "reviewer", "source_version", "advocate_id"])
def test_http_cannot_author_its_own_grant_or_replace_trusted_contracts(client, extra):
    app, matter, _, model = configured(client)
    served = client.post(path(matter), json=request(matter, **{extra: "self-approved"}))
    assert served.status_code == 422
    assert not app.store.load(matter.id).loop_records and model.tool_call.call_count == 0


@pytest.mark.parametrize("state", ["absent", "expired", "duplicate", "untyped"])
def test_missing_expired_ambiguous_or_untyped_grant_refuses_before_dispatch(client, state):
    app, matter, grant, model = configured(client)
    app.controlled_evaluations = {
        "absent": (), "expired": (replace(grant, expires_at=utcnow() - timedelta(seconds=1)),),
        "duplicate": (grant, grant), "untyped": ({"scope": grant.scope},),
    }[state]
    assert client.post(path(matter), json=request(matter)).status_code == 403
    assert model.tool_call.call_count == 0 and not app.store.load(matter.id).loop_records


def test_actual_route_is_owned_versioned_authenticated_and_csrf_protected(client):
    app, matter, _, model = configured(client)
    foreign = client.sign_in("another_advocate", fresh=True)
    unknown = path(matter).replace(matter.id, "absent")
    assert foreign.post(path(matter), json=request(matter)).json() == foreign.post(
        unknown, json=request(matter)).json()
    assert foreign.post(path(matter), json=request(matter)).status_code == 404
    assert client.post(path(matter), json=request(matter),
                       headers={"x-nm-csrf": "wrong"}).status_code == 403
    assert client.post(path(matter), json=request(matter, version=99)).status_code == 409
    assert model.tool_call.call_count == 0 and not app.store.load(matter.id).loop_records


def test_revocation_between_rounds_cancels_real_work_and_never_returns_private_output(client):
    app, matter, _, model = configured(client)
    actual = model.tool_call.return_value

    def revoke(*_args, **_kwargs):
        app.controlled_evaluations = ()
        return actual

    model.tool_call.side_effect = revoke
    served = client.post(path(matter), json=request(matter))
    assert served.status_code == 200 and PRIVATE not in served.text
    saved = app.store.load(matter.id)
    assert saved.loop_records[0].events[-1].payload["reason"] == "cancelled"
    assert not saved.turn_receipts


def test_replacement_with_a_new_equal_grant_cannot_extend_the_running_approval(client):
    app, matter, grant, model = configured(client)
    actual = model.tool_call.return_value

    def replace_approval(*_args, **_kwargs):
        app.controlled_evaluations = (replace(grant),)
        return actual

    model.tool_call.side_effect = replace_approval
    assert client.post(path(matter), json=request(matter)).status_code == 200
    assert app.store.load(matter.id).loop_records[0].events[-1].payload["reason"] == "cancelled"


def test_approval_expiry_is_typed_and_a_body_cannot_supply_a_blank_instruction(client):
    _, matter, grant, model = configured(client)
    with pytest.raises(ValueError, match="aware"):
        replace(grant, expires_at=utcnow().replace(tzinfo=None))
    with pytest.raises(EvaluationUnavailable):
        grant_for([grant], actor=grant.scope.advocate_id, matter_id=matter.id, now=utcnow())
    assert client.post(path(matter), json=request(matter, message="   ")).status_code == 422
    assert client.post(path(matter), json=request(matter,
        selected_issue_ids=["a" * 161])).status_code == 422
    assert model.tool_call.call_count == 0
