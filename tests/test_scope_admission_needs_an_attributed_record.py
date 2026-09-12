"""P14 instruction capture cannot invent an answer or its provenance."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from nm.core import screens

pytestmark = pytest.mark.class_a
NOW = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)


def _request(**extra):
    return {
        "message": "We act for the plaintiff in an unpaid invoice dispute.",
        "parties": {"Scope Client": "client", "Scope Opponent": "adverse"},
        "capacity": {"state": "not_in_doubt", "basis": "The advocate assessed capacity."},
        **extra,
    }


@pytest.mark.parametrize("value", ["", " \t\n", None, 7, True, ["advice"], {"answer": "advice"}])
def test_supplied_nontext_or_blank_instruction_cannot_create_a_matter(client, value):
    from nm.edge.api import application

    response = client.post("/api/turn", json=_request(release={"scope": value}))
    assert response.status_code == 422
    listing = application().store.list_for("adv_demo")
    assert listing.complete
    assert listing.unreadable == ()
    assert listing.matters == ()


@pytest.mark.parametrize("record", [
    None, "advice", {"by": "adv_demo"},
    {"by": "adv_demo", "answer": " \t", "at": "2026-09-11"},
    {"by": "", "answer": "advice", "at": "2026-09-11"},
    {"by": "another", "answer": "advice", "at": "2026-09-11"},
    {"by": "adv_demo", "answer": 1, "at": "2026-09-11"},
    {"by": "adv_demo", "answer": "advice", "at": "unknown"},
    {"by": "adv_demo", "answer": "advice", "at": "2026-09-13"},
    {"by": "adv_demo", "answer": "advice", "at": "2026-09-12T12:00:00"},
    {"by": "adv_demo", "answer": "advice", "at": "2026-09-12T12:00:00+00:00"},
    {"by": "adv_demo", "answer": "advice", "at": "2026-09-11", "confirmed": True},
])
def test_stored_instruction_requires_actual_source_text_and_nonfuture_date(record):
    screen = screens.scope_screen(record, "adv_demo", NOW)
    assert screen.kind is screens.ScreenKind.SCOPE
    assert screen.state is screens.ScreenState.NOT_ASSESSED
    assert not screen.clears
    assert "confirmed at intake" not in screen.not_assessed_because


@pytest.mark.parametrize("at", ["2026-09-11", "2026-09-12T09:00:00+00:00"])
def test_attributed_legacy_date_and_server_timestamp_keep_capture_usable(at):
    screen = screens.scope_screen(
        {"by": "adv_demo", "answer": "advice on the invoice", "at": at}, "adv_demo", NOW)
    assert screen.clears
    assert "advice on the invoice" in screen.detail
    assert "adv_demo" in screen.detail


def _malformed_served_witness(client, monkeypatch):
    from nm.edge.api import application

    app = application()
    monkeypatch.setattr(app.engine, "_clock", lambda: NOW)
    initial = client.post("/api/turn", json=_request())
    assert initial.status_code == 200
    matter = app.store.load(initial.json()["matter_id"])
    assert matter is not None
    damaged = replace(matter, version=matter.version + 1, intake_answers={
        **matter.intake_answers, "scope": {"by": "adv_demo"}})
    app.store.commit(damaged, expected_version=matter.version)
    admitted = []
    original = app.engine._admit_facts

    def observe(*args, **kwargs):
        admitted.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(app.engine, "_admit_facts", observe)
    response = client.post("/api/turn", json=_request(matter_id=matter.id))
    assert response.status_code == 200
    assert not admitted, "malformed scope reached fact admission"
    current = app.store.load(matter.id)
    scope = next(row for row in screens.from_stored(current.screens)
                 if row.kind is screens.ScreenKind.SCOPE)
    assert scope.state is screens.ScreenState.NOT_ASSESSED
    assert not current.facts


def test_malformed_stored_scope_cannot_reach_served_fact_admission(client, monkeypatch):
    _malformed_served_witness(client, monkeypatch)


def test_bypassing_the_shared_scope_guard_breaks_the_served_witness(client, monkeypatch):
    monkeypatch.setattr(screens, "scope_screen", lambda record, actor, now: screens.Screen(
        kind=screens.ScreenKind.SCOPE, state=screens.ScreenState.CLEAR,
        detail="planted false clearance"))
    with pytest.raises(AssertionError, match="malformed scope reached fact admission"):
        _malformed_served_witness(client, monkeypatch)


def test_real_stored_screens_reach_the_emergency_consumer_without_losing_state(client):
    from nm.edge.api import _outstanding_screens, application

    response = client.post("/api/turn", json=_request(release={"scope": "invoice advice"}))
    assert response.status_code == 200
    matter = application().store.load(response.json()["matter_id"])
    assert matter is not None
    assert matter.screens and all(isinstance(row, dict) for row in matter.screens)
    restored = screens.from_stored(matter.screens)
    assert {row.kind for row in restored} == set(screens.ScreenKind)
    assert all(row.clears for row in restored)
    assert _outstanding_screens(matter) == ()
    damaged = replace(matter, screens=(*matter.screens, matter.screens[0]))
    assert _outstanding_screens(damaged) == ("the screen set on this matter could not be read",)


@pytest.mark.parametrize("change", ["missing", "unknown", "duplicate", "state", "release"])
def test_malformed_persisted_screen_never_becomes_a_clearance(change):
    from nm.adapters.store.file_store import _enc

    record = _enc(screens.Screen(kind=screens.ScreenKind.CONFLICT,
                                 state=screens.ScreenState.CLEAR))
    population = [record]
    if change == "missing":
        del record["state"]
    elif change == "unknown":
        record["kind"] = "unknown-screen"
    elif change == "duplicate":
        population.append(dict(record))
    elif change == "state":
        record["state"] = "unknown-state"
    else:
        record["released"] = {"by": "adv_demo"}
    with pytest.raises(ValueError):
        screens.unscreened(population)
