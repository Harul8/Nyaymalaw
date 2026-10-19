"""P14: the capacity STATE, not the truthiness of an answer, decides what capacity allows.

Owner, 28 September 2026: every message is worked. G-CAPACITY is a STEP gate
in the matrix, so an UNASSESSED capacity is a stated limit on relying on the
advice, not a bar on working the file. Capacity recorded as IN DOUBT still
holds the file until a person resolves it, and no prose ever clears it.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


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
    from nm.app.api import application

    assert response.status_code == 200, response.text
    matter_id = response.json()["matter_id"]
    matter = application().store.load(matter_id)
    assert matter is not None
    return matter


def _states_the_limit(response, word: str) -> bool:
    """The reply says the limit out loud, as a disclosure the advocate reads."""
    return any(word in e["text"].lower() and e["disclosure"]
               for e in response.json()["elements"])


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


@pytest.mark.parametrize('extra', [{'basis': ' '}, {'raised_by': 'forged'},
                                  {'raised_at': '2026-01-01'}, {'state': 'yes'}])
def test_capacity_correction_rejects_forged_or_incomplete_records(client, extra):
    first = _saved(client, client.post('/api/turn', json=_request()))
    value = {'expected_version': first.version, 'state': 'not_in_doubt',
             'basis': 'Explicit assessment.', **extra}
    assert client.post(f'/api/matters/{first.id}/capacity', json=value).status_code == 422
    stranger = client.sign_in('adv_capacity_stranger', fresh=True)
    assert stranger.post(f'/api/matters/{first.id}/capacity', json={
        'expected_version': first.version, 'state': 'not_in_doubt',
        'basis': 'Explicit assessment.'}).status_code == 404


