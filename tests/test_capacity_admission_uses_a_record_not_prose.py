"""P14: the capacity state, not the truthiness of an answer, gates substance."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from nm.core import screens
from nm.domain.capacity import Capacity, CapacityPosition
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
BRIEF = "We act for the plaintiff concerning an unpaid invoice."


def _request(**extra):
    return {
        "message": BRIEF,
        "parties": {"Capacity Client": "client", "Capacity Opponent": "adverse"},
        "release": {"scope": "advice on this recovery dispute"},
        **extra,
    }


def _saved(client, response):
    from nm.edge.api import application

    assert response.status_code == 200, response.text
    matter_id = response.json()["matter_id"]
    matter = application().store.load(matter_id)
    assert matter is not None
    return matter


def _capacity_screen(matter):
    return next(screen for screen in screens.from_stored(matter.screens)
                if screen.kind is screens.ScreenKind.CAPACITY)


@refuses("B6", 1)
@pytest.mark.parametrize("state", list(Capacity))
def test_each_explicit_state_reaches_the_actual_served_admission(client, monkeypatch, state):
    from nm.edge.api import application

    engine = application().engine
    monkeypatch.setattr(engine, "_clock", lambda: NOW)
    original = engine._admit_facts
    entered = []

    def admit(*args, **kwargs):
        entered.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "_admit_facts", admit)
    response = client.post("/api/turn", json=_request(capacity={
        "state": state.value, "basis": "The advocate records this explicit assessment."}))
    matter = _saved(client, response)
    stored = matter.intake_answers["capacity"]
    assert stored["state"] == state.value
    assert stored["raised_by"] == "adv_demo"
    assert stored["raised_at"] == NOW.isoformat()
    assert stored["resolved_by"] == ("adv_demo" if state is Capacity.NOT_IN_DOUBT else "")
    assert stored["next_step"]
    screen = _capacity_screen(matter)
    assert screen.clears is (state is Capacity.NOT_IN_DOUBT)
    assert bool(entered) is (state is Capacity.NOT_IN_DOUBT)
    if state is not Capacity.NOT_IN_DOUBT:
        assert response.json()["blocked"]
        assert not matter.facts


@pytest.mark.parametrize("answer", ["yes", "not in doubt", "in doubt", "cannot instruct",
                                       "the advocate confirms the client can give instructions"])
def test_legacy_prose_never_grandfathers_a_capacity_clearance(client, answer):
    response = client.post("/api/turn", json=_request(
        release={"scope": "recovery advice", "capacity": answer}))
    matter = _saved(client, response)
    assert response.json()["blocked"]
    assert not matter.facts
    assert _capacity_screen(matter).state is screens.ScreenState.NOT_ASSESSED
    assert matter.intake_answers["capacity"]["answer"] == answer


@refuses("B6", 0)
@pytest.mark.parametrize("basis", ["The client is distressed", "The client is elderly",
                                     "An unusual instruction was reported"])
def test_personal_description_never_creates_a_capacity_finding(basis):
    position = CapacityPosition.record(
        {"state": "not_assessed", "basis": basis}, actor="adv", now=NOW)
    assert position.state is Capacity.NOT_ASSESSED
    assert not position.authorises_at(NOW)
    assert not position.resolved_by
    assert position.basis == basis


@pytest.mark.parametrize("value", [
    {}, {"state": "assessed", "basis": "unsupported state"},
    {"state": "not_in_doubt", "basis": ""},
    {"state": "in_doubt", "basis": ""},
    {"state": "not_in_doubt", "basis": "says so", "resolved_by": "another-person"},
    {"state": "not_in_doubt", "basis": "says so", "raised_at": "2026-01-01"},
    {"state": True, "basis": "boolean is not an assessment"},
])
def test_malformed_or_self_attributed_capacity_input_is_refused(client, value):
    response = client.post("/api/turn", json=_request(capacity=value))
    assert response.status_code == 422, response.text
    assert client.get("/api/matters").json()["matters"] == []


def test_two_competing_capacity_representations_are_refused(client):
    response = client.post("/api/turn", json=_request(
        release={"scope": "recovery", "capacity": "in doubt"},
        capacity={"state": "not_in_doubt", "basis": "a conflicting claim"}))
    assert response.status_code == 422
    assert client.get("/api/matters").json()["matters"] == []


def test_uncertainty_reopens_capacity_and_preserves_the_prior_assessment(client, monkeypatch):
    from nm.adapters.store.file_store import FileMatterStore
    from nm.edge.api import application
    from tests.test_turn_contract import KEY

    engine = application().engine
    monkeypatch.setattr(engine, "_clock", lambda: NOW)
    first = _saved(client, client.post("/api/turn", json=_request(capacity={
        "state": "not_in_doubt", "basis": "The advocate's first assessment."})))
    assert _capacity_screen(first).clears
    prior = first.intake_answers["capacity"]
    monkeypatch.setattr(engine, "_clock", lambda: NOW + timedelta(minutes=5))
    changed = client.post("/api/turn", json=_request(
        matter_id=first.id,
        capacity={"state": "in_doubt", "basis": "New material requires human review."}))
    current = _saved(client, changed)
    assert changed.json()["blocked"]
    assert current.facts == first.facts
    assert _capacity_screen(current).state is screens.ScreenState.BLOCKED
    assert current.intake_answers["capacity_history"][-1] == prior
    fresh = FileMatterStore(application().store._root, key=KEY).load(first.id)
    assert fresh.intake_answers["capacity"] == current.intake_answers["capacity"]
    assert fresh.intake_answers["capacity_history"][-1] == prior
    assert not screens.capacity_screen(fresh.intake_answers["capacity"], NOW).clears


def test_a_later_explicit_resolution_can_open_capacity_without_erasing_the_question(client):
    first = _saved(client, client.post("/api/turn", json=_request(capacity={
        "state": "in_doubt", "basis": "An assessment is required."})))
    assert not _capacity_screen(first).clears
    second = _saved(client, client.post("/api/turn", json=_request(
        matter_id=first.id,
        capacity={"state": "not_in_doubt", "basis": "The advocate resolved the recorded doubt."})))
    assert _capacity_screen(second).clears
    assert second.intake_answers["capacity_history"][-1]["state"] == "in_doubt"
    assert second.intake_answers["capacity"]["resolved_by"] == "adv_demo"


def test_clear_capacity_does_not_clear_an_unanswered_scope(client):
    response = client.post("/api/turn", json=_request(
        release={}, capacity={"state": "not_in_doubt", "basis": "Explicit assessment."}))
    matter = _saved(client, response)
    assert _capacity_screen(matter).clears
    scope = next(screen for screen in screens.from_stored(matter.screens)
                 if screen.kind is screens.ScreenKind.SCOPE)
    assert not scope.clears
    assert response.json()["blocked"] and not matter.facts


def test_future_or_damaged_stored_clearance_is_not_current():
    future = CapacityPosition.record(
        {"state": "not_in_doubt", "basis": "Explicit assessment."},
        actor="adv", now=NOW + timedelta(days=1))
    assert not screens.capacity_screen(future.as_dict(), NOW).clears
    damaged = future.as_dict()
    damaged["resolved_by"] = ""
    assert CapacityPosition.from_stored(damaged).state is Capacity.NOT_ASSESSED
    assert not screens.capacity_screen(damaged, NOW + timedelta(days=2)).clears


def test_the_served_negative_control_bites_when_capacity_admission_is_bypassed(client, monkeypatch):
    def require_refusal():
        response = client.post("/api/turn", json=_request(capacity={
            "state": "in_doubt", "basis": "A human decision remains outstanding."}))
        matter = _saved(client, response)
        assert not _capacity_screen(matter).clears, "in-doubt capacity was cleared"

    require_refusal()
    monkeypatch.setattr(screens, "capacity_screen", lambda record, now: screens.Screen(
        kind=screens.ScreenKind.CAPACITY, state=screens.ScreenState.CLEAR,
        detail="mutated admission bypass"))
    with pytest.raises(AssertionError, match="in-doubt capacity was cleared"):
        require_refusal()
