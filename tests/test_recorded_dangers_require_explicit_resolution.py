"""Manual urgency is persisted danger, not an emergency permission or legal advice."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from nm.app.api import application
from nm.arrive.advocate_contracts import utcnow

pytestmark = pytest.mark.class_a


def _instruction(**changes):
    body = {"class": "personal_safety", "basis": "Reported immediate danger",
            "action": "Contact the responsible advocate", "owner": "Instructing advocate",
            "due": "2026-09-12T20:00:00+05:30", "unknowns": {}}
    body.update(changes)
    return body


def _matter(client):
    reply = client.post("/api/matters/intake", json={"request_key": "urgency-shell",
                                                   "title": "Supplied protective file"})
    assert reply.status_code == 200, reply.text
    return reply.json()["matter_id"]


def _offer(client, matter_id, key="raise-danger", **changes):
    observed = client.get(f"/api/matters/{matter_id}/emergency").json()
    body = {"urgency_command": "raise", "request_key": key,
            "expected_version": observed["version"], "urgency": _instruction()}
    body.update(changes)
    return body


def _post(client, matter_id, body):
    return client.post(f"/api/matters/{matter_id}/emergency", json=body)


def test_manual_urgency_is_visible_without_granting_a_protective_permission(client):
    matter_id = _matter(client)
    offered = _offer(client, matter_id)
    response = _post(client, matter_id, offered)
    assert response.status_code == 200, response.text
    assert response.json()["action_performed"] is False
    view = client.get(f"/api/matters/{matter_id}/emergency").json()
    assert view["governing"] is None
    row = view["urgency_register"]["entries"][0]
    assert row["state"] == "live"
    assert row["raised_by"] == application().store.load(matter_id).advocate_id
    assert row["due"] == "2026-09-12T14:30:00+00:00"
    assert row["assessment"] == "user_supplied_not_independently_verified"
    assert application().store.load(matter_id).facts == ()


@pytest.mark.parametrize("end", ["expiry", "revocation"])
def test_permission_ending_cannot_resolve_or_hide_a_live_danger(client, monkeypatch, end):
    from tests.test_professional_approval_is_separate_from_account_access import (
        approve_fixture_account,
    )

    approve_fixture_account(client.directory)
    matter_id = _matter(client)
    instant = utcnow()
    monkeypatch.setattr("nm.app.api.utcnow", lambda: instant)
    assert _post(client, matter_id, _offer(client, matter_id)).status_code == 200
    assert _post(client, matter_id, {"request_key": "permission", "basis": "Supplied danger",
                                   "hours": 1}).status_code == 200
    before = application().store.load(matter_id).urgency_records
    view = client.get(f"/api/matters/{matter_id}/emergency").json()
    if end == "expiry":
        monkeypatch.setattr("nm.app.api.utcnow", lambda: instant + timedelta(hours=2))
        # F-A-12: two untouched hours end the session too, so the advocate
        # signs in again at the later time before looking.
        client.sign_in()
    else:
        ended = _post(client, matter_id, {"revoke": True, "expected_version": view["version"],
                                         "governing_ref": view["governing_ref"]})
        assert ended.status_code == 200, ended.text
    current = client.get(f"/api/matters/{matter_id}/emergency").json()
    assert current["governing"] is None
    assert current["urgency_register"]["entries"][0]["state"] == "live"
    assert application().store.load(matter_id).urgency_records == before


@pytest.mark.parametrize("change", ["same_key_changed_basis", "stale_version", "unknown_id",
                                    "missing_resolution_basis", "actor_injection"])
def test_changed_or_unattributable_urgency_commands_cannot_mutate_the_register(client, change):
    matter_id = _matter(client)
    offered = _offer(client, matter_id)
    first = _post(client, matter_id, offered).json()
    if change == "same_key_changed_basis":
        request = {**offered, "urgency": _instruction(basis="Different danger")}
    elif change == "stale_version":
        request = {**offered, "request_key": "other-danger"}
    else:
        request = {"urgency_command": "resolve", "request_key": "resolve-danger",
                   "expected_version": first["version"], "urgency_id": first["urgency_id"],
                   "resolution_basis": "Specific resolution basis"}
        if change == "unknown_id":
            request["urgency_id"] = "never-recorded"
        elif change == "missing_resolution_basis":
            request["resolution_basis"] = " "
        else:
            request["actor_id"] = "someone-else"
    before = application().store.load(matter_id)
    response = _post(client, matter_id, request)
    assert response.status_code in (409, 404, 422), response.text
    assert application().store.load(matter_id) == before


@pytest.mark.parametrize("bad", ["unknown_class", "missing_unknown_reason", "naive_time",
                                 "invented_clearance", "contradictory_unknown"])
def test_urgency_input_never_guesses_a_class_time_or_clearance(client, bad):
    matter_id = _matter(client)
    instruction = _instruction()
    if bad == "unknown_class":
        instruction["class"] = "everything_is_urgent"
    elif bad == "missing_unknown_reason":
        instruction["due"] = None
    elif bad == "naive_time":
        instruction["due"] = "2026-09-12T10:00:00"
    elif bad == "invented_clearance":
        instruction["state"] = "cleared"
    else:
        instruction["unknowns"] = {"owner": "Not known"}
    before = application().store.load(matter_id)
    response = _post(client, matter_id, _offer(client, matter_id, urgency=instruction))
    assert response.status_code == 422, response.text
    assert application().store.load(matter_id) == before


def test_explicit_unknown_action_owner_and_time_survive_a_real_round_trip(client):
    matter_id = _matter(client)
    unknowns = {"action": "Awaiting instructions", "owner": "Responsible person not confirmed",
                "due": "Order has not been supplied"}
    result = _post(client, matter_id, _offer(client, matter_id, urgency=_instruction(
        action=None, owner=None, due=None, unknowns=unknowns)))
    assert result.status_code == 200, result.text
    view = client.get(f"/api/matters/{matter_id}/emergency").json()["urgency_register"]
    entry = view["entries"][0]
    assert entry["unknowns"] == unknowns and entry["due"] is None
    assert entry["state"] == "live"


def test_failed_urgency_commit_cannot_emit_a_successful_receipt(client, monkeypatch):
    matter_id = _matter(client)
    offered = _offer(client, matter_id)
    store = application().store
    before = store.load(matter_id)
    def failed(*args, **kwargs):
        raise OSError("synthetic write refusal")
    monkeypatch.setattr(store, "commit", failed)
    assert _post(client, matter_id, offered).status_code == 503
    assert store.load(matter_id) == before


def test_a_competing_file_write_is_not_overwritten_by_urgency_acceptance(client, monkeypatch):
    matter_id = _matter(client)
    offered = _offer(client, matter_id)
    store = application().store
    original = store.commit
    winners = []
    def compete(matter, *, expected_version):
        current = store.load(matter_id)
        changed = replace(current, title="Concurrent accepted title", version=current.version + 1)
        original(changed, expected_version=current.version)
        winners.append(changed)
        return original(matter, expected_version=expected_version)
    monkeypatch.setattr(store, "commit", compete)
    response = _post(client, matter_id, offered)
    assert response.status_code == 409 and len(winners) == 1
    assert store.load(matter_id) == winners[0]
    assert store.load(matter_id).urgency_records == ()


def test_unreadable_resolution_never_defaults_to_a_live_or_cleared_record(client):
    matter_id = _matter(client)
    assert _post(client, matter_id, _offer(client, matter_id)).status_code == 200
    store = application().store
    matter = store.load(matter_id)
    corrupt = {**matter.urgency_records[0], "state": "resolved", "resolver": None}
    store.commit(replace(matter, urgency_records=(corrupt,), version=matter.version + 1),
                 expected_version=matter.version)
    observed = client.get(f"/api/matters/{matter_id}/emergency").json()
    assert observed["state"] == "incomplete"
    assert observed["urgency_register"]["unreadable_records"] == 1
    assert _post(client, matter_id, _offer(client, matter_id, "new-danger")).status_code == 503


@pytest.mark.parametrize("mutation", [
    "result_extra", "result_action_true", "result_action_number", "result_assessment",
    "result_replayed_string", "result_missing", "result_version_bool", "result_version_future",
    "result_matter", "result_key", "result_urgency_other", "offer_extra", "offer_actor",
    "offer_wrong_basis", "offer_version_bool", "receipt_extra", "null_receipt", "duplicate_receipt",
])
def test_malformed_sealed_urgency_receipts_cannot_claim_actions_or_replay(client, mutation):
    matter_id = _matter(client)
    offered = _offer(client, matter_id)
    raised = _post(client, matter_id, offered)
    assert raised.status_code == 200, raised.text
    other = _post(client, matter_id, _offer(client, matter_id, "other-danger",
                  urgency=_instruction(basis="A distinct reported danger")))
    assert other.status_code == 200, other.text
    store = application().store
    path = store._path(matter_id)
    original_bytes = path.read_bytes()
    payload = json.loads(store._open(matter_id, original_bytes))
    before = copy.deepcopy(payload)
    matches = [row for row in payload["urgency_operations"]
               if row["request_key"] == offered["request_key"]]
    assert len(matches) == 1, "mutate the genuine served command, not an unused field"
    row = matches[0]
    result = row["result"]
    if mutation == "result_extra":
        result["raw_trace"] = "UNRELEASED URGENCY TRACE"
    elif mutation == "result_action_true":
        result["action_performed"] = True
    elif mutation == "result_action_number":
        result["action_performed"] = 0
    elif mutation == "result_assessment":
        result["assessment"] = "independently_verified"
    elif mutation == "result_replayed_string":
        result["replayed"] = "false"
    elif mutation == "result_missing":
        result.pop("assessment")
    elif mutation == "result_version_bool":
        result["version"] = True
    elif mutation == "result_version_future":
        result["version"] = payload["version"] + 20
    elif mutation == "result_matter":
        result["matter_id"] = "another-matter"
    elif mutation == "result_key":
        result["request_key"] = "another-key"
    elif mutation == "result_urgency_other":
        result["urgency_id"] = other.json()["urgency_id"]
    elif mutation == "offer_extra":
        row["offer"]["raw_trace"] = "UNRELEASED URGENCY TRACE"
    elif mutation == "offer_actor":
        row["offer"]["actor_id"] = "a-different-advocate"
    elif mutation == "offer_wrong_basis":
        row["offer"]["urgency"]["basis"] = "A different original instruction"
    elif mutation == "offer_version_bool":
        row["offer"]["expected_version"] = True
    elif mutation == "receipt_extra":
        row["raw_trace"] = "UNRELEASED URGENCY TRACE"
    elif mutation == "null_receipt":
        payload["urgency_operations"].append(None)
    else:
        payload["urgency_operations"].append(copy.deepcopy(row))
    assert json.dumps(payload, sort_keys=True) != json.dumps(before, sort_keys=True)
    damaged = store._seal(matter_id, json.dumps(payload).encode("utf-8"))
    path.write_bytes(damaged)
    try:
        assert store.load(matter_id).urgency_operations, "the real codec must read the changed rows"
        response = _post(client, matter_id, offered)
        assert response.status_code == 503, response.text
        assert "UNRELEASED URGENCY TRACE" not in response.text
        assert "independently_verified" not in response.text
        assert "action_performed" not in response.text
        assert path.read_bytes() == damaged, "refusal must neither erase nor repair saved evidence"
    finally:
        path.write_bytes(original_bytes)


