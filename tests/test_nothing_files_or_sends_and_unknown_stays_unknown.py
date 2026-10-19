"""NOTHING FILES OR SENDS, AND UNKNOWN STAYS UNKNOWN. BK-56-AC4. P30.

WHAT THESE DEFEND
-------------------
The wire goes quiet on a filing. The product has two comfortable states and
both are lies:

    read as DELIVERED  -- the advocate stops watching a live deadline
    read as REFUSED    -- the advocate files again, and files twice

`DELIVERY_UNKNOWN` is the honest third, and it is a DESTINATION rather than a
transient: it leaves only on validated evidence. The command contract says the
same thing from its own end -- *inconclusive remains outcome_unknown*, *user
cannot submit success=true*, *no automatic redispatch in reconciliation*.

AND THE CONNECTOR IS OFF. CHOICE-09's `approval` field reads `None`, so
`CONNECTOR_ENABLED` is a module constant rather than configuration: a flag a
deployment could flip is a flag a deployment will flip, and what sits on the
other side is an irreversible act against a court.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.class_a

DIGEST = "abc123def456"


# =============================== 1. the connector is off =====================


# ========================== 2. approval is for exact bytes ===================


# ================= 3. seven distinct states, and unknown is one ==============


# ============================ 4. reconciliation ==============================


# ================================ 5. the audit record ========================


# ================================ 6. the served path =========================

BRIEF = ("We act for Ledger Traders in a recovery suit against Kiran Steels. "
         "Goods were supplied on 14 March 2023 and were never paid for.")


def _matter(client) -> tuple[str, int]:
    r = client.post("/api/turn", json={
        "message": BRIEF, "today": "2026-09-13",
        "parties": {"Ledger Traders": "client", "Kiran Steels": "adverse"},
        "release": {"scope": "recover the price of goods sold"},
        "capacity": {"state": "not_in_doubt",
                     "basis": "The advocate assessed that the client "
                              "instructs directly."}})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"], r.json()["matter_version"]


def _package(client, matter_id, version):
    r = client.post("/api/drafting-packages", json={
        "matter_id": matter_id, "document": "plaint",
        "audience": "the City Civil Court", "purpose": "recover the price",
        "posture": "plaintiff",
        "cause_title": {"court": "City Civil Court"},
        "theory_sentence": "the price is due", "reliefs": ["a decree"],
        "expected_matter_version": version})
    assert r.status_code == 201, r.text
    return r.json()["package"]["package_id"], r.json()["version"]


def _propose(client, matter_id, package_id, version):
    return client.post("/api/action-proposals", json={
        "matter_id": matter_id, "package_id": package_id,
        "authority": "the instructing advocate", "object": "the plaint",
        "destination": "City Civil Court, Hyderabad",
        "expected_matter_version": version})


def test_the_dispatch_route_always_refuses_with_connector_disabled(client):
    """It EXISTS so the answer is a stated refusal rather than a 404 somebody
    reads as "not built yet"."""
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _propose(client, matter_id, pid, version).json()
    apid = made["proposal"]["proposal_id"]

    r = client.post(f"/api/action-proposals/{apid}/execution", json={
        "matter_id": matter_id, "content_digest": "x",
        "expected_matter_version": made["version"]})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "CONNECTOR_DISABLED"
    assert "CHOICE-09" in r.json()["detail"]["why"]


def test_the_proposal_takes_its_digest_from_the_package_not_the_caller(client):
    """An approval is for exact bytes; letting the proposer state which bytes
    would make it meaningless."""
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _propose(client, matter_id, pid, version)
    assert made.status_code == 201, made.text
    assert made.json()["proposal"]["content_digest"]


def test_confirming_against_a_different_digest_is_refused_on_the_wire(client):
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _propose(client, matter_id, pid, version).json()
    apid = made["proposal"]["proposal_id"]
    r = client.post(f"/api/action-proposals/{apid}/confirmation", json={
        "matter_id": matter_id, "content_digest": "not-the-one",
        "expected_matter_version": made["version"]})
    assert r.status_code == 409, r.text
    assert "content moved" in r.json()["detail"]["why"]


def test_a_timeout_recorded_on_the_wire_stays_unknown(client):
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _propose(client, matter_id, pid, version).json()
    apid, digest = made["proposal"]["proposal_id"], made["proposal"]["content_digest"]

    ok = client.post(f"/api/action-proposals/{apid}/confirmation", json={
        "matter_id": matter_id, "content_digest": digest,
        "expected_matter_version": made["version"]})
    assert ok.status_code == 201, ok.text

    out = client.post(f"/api/action-proposals/{apid}/outcome", json={
        "matter_id": matter_id, "state": "delivery_unknown",
        "because": "the court portal timed out",
        "expected_matter_version": ok.json()["version"]})
    assert out.status_code == 201, out.text
    assert out.json()["state"] == "delivery_unknown"
    assert out.json()["proposal"]["claims_arrival"] is False

    again = client.post(f"/api/action-proposals/{apid}/reconciliation", json={
        "matter_id": matter_id, "basis": "portal lookup found nothing",
        "expected_matter_version": out.json()["version"]})
    assert again.status_code == 201, again.text
    assert again.json()["state"] == "delivery_unknown"
    assert again.json()["resolved"] is False


def test_the_wire_refuses_delivered_without_a_receipt(client):
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _propose(client, matter_id, pid, version).json()
    apid, digest = made["proposal"]["proposal_id"], made["proposal"]["content_digest"]
    ok = client.post(f"/api/action-proposals/{apid}/confirmation", json={
        "matter_id": matter_id, "content_digest": digest,
        "expected_matter_version": made["version"]}).json()

    r = client.post(f"/api/action-proposals/{apid}/outcome", json={
        "matter_id": matter_id, "state": "delivered",
        "expected_matter_version": ok["version"]})
    assert r.status_code == 422, r.text
    assert "receipt" in r.json()["detail"]["why"]


def test_the_reconciliation_body_has_no_success_field(client):
    """*user cannot submit success=true*, enforced by the closed schema."""
    matter_id, version = _matter(client)
    pid, version = _package(client, matter_id, version)
    made = _propose(client, matter_id, pid, version).json()
    apid = made["proposal"]["proposal_id"]
    r = client.post(f"/api/action-proposals/{apid}/reconciliation", json={
        "matter_id": matter_id, "basis": "I think it went",
        "success": True, "expected_matter_version": made["version"]})
    assert r.status_code == 422, r.text
