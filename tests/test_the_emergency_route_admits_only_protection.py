"""ORDINARY ADMISSION, AND A BOUNDED WAY ROUND IT. BK-78, BK-53, BK-34. P14.

THE RULE, stated without the scenario that exposed it
-------------------------------------------------------
**An exception is recorded as an exception. A file that took one must never
read afterwards as a file whose screens passed.**

Liberty does not wait for a registry, so there has to be a way through — and
the entire risk of that way is that it becomes the comfortable one. So it
expires, it names what it permitted, it carries the screens that were
outstanding when it was taken, and it admits exactly one work product.

WHAT IS ASSERTED
------------------
    an unavailable screen never clears, and says so differently from unrun
    a declaration persists with actor, basis, outstanding screens and expiry
    expiry is a question about the clock, not a stored flag
    an expired declaration keeps its urgency on the file and permits nothing
    no work product but protective triage is admitted, and no argument widens it
    revocation is a new record, never an erasure
    capacity to instruct is recorded separately from account access
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.test_professional_approval_is_separate_from_account_access import approve_fixture_account

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 11, 10, 0, 0)


def test_unreadable_emergency_history_is_reported_incomplete_through_the_wire(client):
    from dataclasses import replace

    from nm.app.api import application
    from tests.test_the_commission_is_served_and_authority_refuses import _matter

    matter_id = _matter(client)
    store = application().store
    matter = store.load(matter_id)
    store.commit(
        replace(
            matter,
            emergencies=(
                {"actor_id": "adv_demo", "basis": "synthetic danger", "declared_at": "damaged"},
            ),
        ),
        expected_version=matter.version,
    )
    response = client.get(f"/api/matters/{matter_id}/emergency")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "incomplete" and body["unreadable_records"] == 1
    assert body["governing"] is None and "could not be assessed" in body["said"]


# ===================== the fourth screen state ==============================


# ======================= the declaration is a record ========================


# ============================ expiry is the clock ===========================


# ==================== it admits protection and nothing else =================


# ============================= revocation ===================================


# ================= capacity to instruct is not account access ===============


def test_the_real_protective_turn_uses_the_live_declaration_without_a_model(client, monkeypatch):
    approve_fixture_account(client.directory)
    from nm.app.api import application
    from nm.arrive.advocate_contracts import utcnow

    created = client.post(
        "/api/turn", json={"message": "we act for the plaintiff about an unpaid invoice"}
    )
    assert created.status_code == 200, created.text
    matter_id = client.get("/api/matters").json()["matters"][0]["matter_id"]
    instant = utcnow()
    monkeypatch.setattr("nm.app.api.utcnow", lambda: instant)
    declared = client.post(
        f"/api/matters/{matter_id}/emergency",
        json={"request_key": "protective-check",
              "basis": "a protective deadline needs immediate checking"},
    )
    assert declared.status_code == 200, declared.text
    frozen = declared.json()["outstanding"]
    before = application().store.load(matter_id)

    def forbidden(*args, **kwargs):
        raise AssertionError("protective handoff reached a model or ordinary admission")

    engine = application().engine
    monkeypatch.setattr(engine, "_clock", lambda: instant)
    monkeypatch.setattr(engine, "_read_route", forbidden)
    body = {
        "matter_id": matter_id,
        "turn_id": "triage-one",
        "message": "unadmitted private words",
        "work_product": "protective_triage",
    }
    answer = client.post("/api/turn", json=body)
    assert answer.status_code == 200, answer.text
    assert answer.json()["blocked"] is False
    assert "no legal merits" in answer.json()["mode_statement"].lower()
    stored = application().store.load(matter_id)
    assert stored.facts == before.facts
    assert stored.screens == before.screens
    assert stored.emergency_triage[-1]["declaration"]["outstanding"] == frozen
    assert "unadmitted private words" not in str(stored.emergency_triage)
    repeated = client.post("/api/turn", json=body)
    assert repeated.status_code == 200 and repeated.json()["replayed"]
    assert len(application().store.load(matter_id).emergency_triage) == 1

    # Even the same accepted turn ID cannot replay a permission after expiry.
    monkeypatch.setattr(engine, "_clock", lambda: instant + timedelta(hours=25))
    expired = client.post("/api/turn", json=body)
    assert expired.status_code == 422
    assert expired.json()["detail"]["release_state"] == "replay_refused"
    assert expired.json()["detail"]["prior_receipt_saved"] is True
    assert "elements" not in expired.json()["detail"]
    assert application().store.load(matter_id).emergencies == stored.emergencies
    assert application().store.load(matter_id) == stored


def _declaration_context(client, monkeypatch):
    approve_fixture_account(client.directory)
    from nm.arrive.advocate_contracts import utcnow
    from tests.test_the_commission_is_served_and_authority_refuses import _matter

    matter_id = _matter(client)
    clock = [utcnow()]
    monkeypatch.setattr("nm.app.api.utcnow", lambda: clock[0])
    return matter_id, f"/api/matters/{matter_id}/emergency", clock


def test_declaration_retry_reads_the_original_expiry_and_frozen_screens(client, monkeypatch):
    from dataclasses import replace

    from nm.app.api import application

    matter_id, path, clock = _declaration_context(client, monkeypatch)
    offer = {"request_key": "one-declaration", "basis": "  A supplied urgent risk  ", "hours": 1}
    first = client.post(path, json=offer)
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    original = first.json()["emergency"]
    saved = application().store.load(matter_id)
    assert saved.emergencies[0]["request_offer"] == {
        "actor_id": "adv_demo", "basis": "A supplied urgent risk", "hours": 1}
    # A changed screen set must not rewrite what the first declaration saw.
    application().store.commit(replace(saved, screens=(), version=saved.version + 1),
                               expected_version=saved.version)
    version = application().store.load(matter_id).version
    clock[0] += timedelta(minutes=20)
    repeated = client.post(path, json={**offer, "basis": "A supplied urgent risk"})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["replayed"] is True
    assert repeated.json()["emergency"] == original
    assert repeated.json()["declaration_state"] == "live"
    assert application().store.load(matter_id).version == version
    assert len(application().store.load(matter_id).emergencies) == 1


def test_expired_declaration_retry_never_renews_but_a_new_explicit_key_can(client, monkeypatch):
    from nm.app.api import application

    matter_id, path, clock = _declaration_context(client, monkeypatch)
    offer = {"request_key": "expired-original", "basis": "Synthetic urgent review", "hours": 1}
    first = client.post(path, json=offer)
    assert first.status_code == 200
    saved = application().store.load(matter_id)
    clock[0] += timedelta(hours=2)
    # F-A-12: two untouched hours end the session too, so the advocate signs
    # in again at the later time before retrying.
    client.sign_in()
    replay = client.post(path, json=offer)
    assert replay.status_code == 200
    assert replay.json()["emergency"] == first.json()["emergency"]
    assert replay.json()["declaration_state"] == "expired"
    assert client.get(path).json()["governing"] is None
    assert application().store.load(matter_id) == saved
    fresh = client.post(path, json={**offer, "request_key": "deliberately-new"})
    assert fresh.status_code == 200 and fresh.json()["replayed"] is False
    assert fresh.json()["emergency"]["expires_at"] != first.json()["emergency"]["expires_at"]
    assert len(application().store.load(matter_id).emergencies) == 2


def test_revocation_preserves_request_identity_and_retry_cannot_revive_it(client, monkeypatch):
    from nm.app.api import application

    matter_id, path, clock = _declaration_context(client, monkeypatch)
    offer = {"request_key": "revoked-original", "basis": "Synthetic risk", "hours": 1}
    first = client.post(path, json=offer)
    assert first.status_code == 200
    # Two equal, same-second declarations are still two separate accepted keys.
    second = client.post(path, json={**offer, "request_key": "second-original"})
    assert second.status_code == 200
    clock[0] += timedelta(minutes=10)
    observed = client.get(path).json()
    assert client.post(path, json={"revoke": True, "expected_version": observed["version"],
                                   "governing_ref": observed["governing_ref"]}).status_code == 200
    saved = application().store.load(matter_id)
    assert len(saved.emergencies) == 2
    assert saved.emergencies[0]["revoked_at"] is None
    assert saved.emergencies[1]["request_key"] == "second-original"
    replay = client.post(path, json={**offer, "request_key": "second-original"})
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["declaration_state"] == "revoked"
    assert replay.json()["emergency"]["expires_at"] == first.json()["emergency"]["expires_at"]
    assert client.get(path).json()["governing"] is None
    assert application().store.load(matter_id) == saved


@pytest.mark.parametrize("changed", [{"basis": "A different danger"}, {"hours": 2}])
def test_declaration_key_cannot_name_different_instructions(client, monkeypatch, changed):
    from nm.app.api import application

    matter_id, path, _ = _declaration_context(client, monkeypatch)
    offer = {"request_key": "one-offer", "basis": "Original danger", "hours": 1}
    assert client.post(path, json=offer).status_code == 200
    saved = application().store.load(matter_id)
    assert client.post(path, json={**offer, **changed}).status_code == 409
    assert application().store.load(matter_id) == saved


@pytest.mark.parametrize("change", ["replacement", "file_version", "wrong_target", "expired"])
def test_revocation_cannot_end_a_declaration_other_than_the_observed_one(
    client, monkeypatch, change,
):
    from dataclasses import replace

    from nm.app.api import application

    matter_id, path, clock = _declaration_context(client, monkeypatch)
    offer = {"request_key": "reviewed", "basis": "Supplied danger", "hours": 1}
    assert client.post(path, json=offer).status_code == 200
    observed = client.get(path).json()
    payload = {"revoke": True, "expected_version": observed["version"],
               "governing_ref": observed["governing_ref"]}
    assert len(payload["governing_ref"]) == 64
    store = application().store
    if change == "replacement":
        assert client.post(path, json={**offer, "request_key": "replacement"}).status_code == 200
    elif change == "file_version":
        current = store.load(matter_id)
        store.commit(replace(current, version=current.version + 1),
                     expected_version=current.version)
    elif change == "wrong_target":
        payload["governing_ref"] = "0" * 64
    else:
        clock[0] += timedelta(hours=2)
        # F-A-12: the session ended with the idle hours; sign in again.
        client.sign_in()
    before = store.load(matter_id)
    response = client.post(path, json=payload)
    assert response.status_code == 409, response.text
    assert store.load(matter_id) == before
    assert all(record["revoked_at"] is None for record in before.emergencies)


@pytest.mark.parametrize("field,value", [
    ("expected_version", None), ("expected_version", True), ("expected_version", "2"),
    ("governing_ref", None), ("governing_ref", ""), ("governing_ref", "x" * 64),
    ("revoke", "true"), ("revoke", 1), ("revoke", False),
])
def test_revocation_needs_an_explicit_observed_command(client, monkeypatch, field, value):
    from nm.app.api import application

    matter_id, path, _ = _declaration_context(client, monkeypatch)
    assert client.post(path, json={"request_key": "observed", "basis": "Supplied danger"}
                       ).status_code == 200
    observed = client.get(path).json()
    payload = {"revoke": True, "expected_version": observed["version"],
               "governing_ref": observed["governing_ref"], field: value}
    before = application().store.load(matter_id)
    assert client.post(path, json=payload).status_code == 422
    assert application().store.load(matter_id) == before


@pytest.mark.parametrize("key", [None, "", " ", 17, "bad/key", "x" * 101])
def test_declaration_requires_an_explicit_stable_key_before_writing(client, monkeypatch, key):
    from nm.app.api import application

    matter_id, path, _ = _declaration_context(client, monkeypatch)
    saved = application().store.load(matter_id)
    offer = {"basis": "Supplied danger"}
    if key is not None:
        offer["request_key"] = key
    assert client.post(path, json=offer).status_code == 422
    assert application().store.load(matter_id) == saved


@pytest.mark.parametrize("damage,expected", [("request_offer", 409), ("declared_at", 503)])
def test_damaged_saved_declaration_identity_cannot_be_recreated(
    client, monkeypatch, damage, expected,
):
    from dataclasses import replace

    from nm.app.api import application

    matter_id, path, _ = _declaration_context(client, monkeypatch)
    offer = {"request_key": "damaged-receipt", "basis": "Original danger", "hours": 1}
    assert client.post(path, json=offer).status_code == 200
    saved = application().store.load(matter_id)
    damaged = {**saved.emergencies[0], damage: "not-readable"}
    application().store.commit(
        replace(saved, emergencies=(damaged,), version=saved.version + 1),
        expected_version=saved.version)
    before = application().store.load(matter_id)
    assert client.post(path, json=offer).status_code == expected
    assert application().store.load(matter_id) == before


def test_concurrent_same_key_declarations_commit_once_and_loser_replays(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    from nm.app.api import application

    matter_id, path, _ = _declaration_context(client, monkeypatch)
    offer = {"request_key": "contested-key", "basis": "Same supplied danger", "hours": 1}
    store = application().store
    load = store.load
    barrier = Barrier(2)
    lock = Lock()
    observed = []

    def both_read(matter):
        result = load(matter)
        if matter == matter_id:
            with lock:
                observed.append(result.version)
                hold = len(observed) <= 2
            if hold:
                barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(store, "load", both_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(path, json=offer), range(2)))
    monkeypatch.setattr(store, "load", load)
    assert len(observed) == 2 and observed[0] == observed[1]
    assert sorted(reply.status_code for reply in results) == [200, 409]
    saved = store.load(matter_id)
    assert len(saved.emergencies) == 1
    replay = client.post(path, json=offer)
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert store.load(matter_id) == saved


def test_failed_declaration_commit_emits_no_acceptance_and_retry_can_create_once(
    client, monkeypatch,
):
    from nm.app.api import application

    matter_id, path, _ = _declaration_context(client, monkeypatch)
    store = application().store
    saved = store.load(matter_id)
    commit = store.commit

    def fail(*args, **kwargs):
        raise OSError("synthetic declaration save failure")

    monkeypatch.setattr(store, "commit", fail)
    offer = {"request_key": "failed-save", "basis": "Supplied danger", "hours": 1}
    with pytest.raises(OSError, match="synthetic declaration save failure"):
        client.post(path, json=offer)
    assert store.load(matter_id) == saved
    monkeypatch.setattr(store, "commit", commit)
    accepted = client.post(path, json=offer)
    assert accepted.status_code == 200 and accepted.json()["replayed"] is False
    assert len(store.load(matter_id).emergencies) == 1
