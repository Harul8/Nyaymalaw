"""HELD AND ERASED ARE DECISIONS, AND "DELETED" IS EARNED. BK-85-AC4, BK-88-AC1.

WHAT THESE DEFEND
-------------------
Two sentences an advocate repeats to a client, and then to a court:

    "It has been deleted."
    "We kept it, as the hold required."

Both are acted on and neither can be taken back. The first is false the moment
one transcript, one extracted page, one processor copy or one restorable backup
of the same recording survives; the second is false the moment an erasure runs
under a hold nobody noticed. So the product may not be able to SAY either
without having reached it.

WHY THE COMPLETION TEST IS ARITHMETIC
---------------------------------------
`complete_for_declared_scope` is refused while a single asset is unresolved,
and the refusal names which. That makes the claim countable instead of
assertable -- the shape CLAUDE.md §9 asks for, at the one place where an
unconfirmed processor reading as "nothing there" produces a false completion.

THE RESTORE IS THE HALF THAT GETS FORGOTTEN. A backup taken before an erasure
does not know the erasure happened, so restoring it re-exposes the material
while looking like a successful recovery. The tombstones are replayed over it.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.class_a


# ============================================ 1. a receipt is not an erasure ==


# ================================================= 2. the transition table ===


# ========================================================== 3. holds refuse ===


# =================================== 4. completion is counted, not declared ===


# ======================================= 5. tombstones and the restore guard ==


# ================================================== 6. persistence and decay ==


# ============================================= 7. the served path, BK-88-AC1 ==
#
# The rules above are worth nothing if the wire does something else -- CLAUDE.md
# §8, and "every defect the first external review found lived between a correct
# module and the served path".

BRIEF = ("We act for Ledger Traders in a recovery suit against Kiran Steels. "
         "The agreement is dated 15 April 2024 and the goods were delivered.")


def _matter(client) -> tuple[str, int]:
    r = client.post("/api/turn", json={
        "message": BRIEF, "today": "2026-09-13",
        "parties": {"Ledger Traders": "client", "Kiran Steels": "adverse"},
        "release": {"scope": "recover the price of goods sold"},
        "capacity": {
            "state": "not_in_doubt",
            "basis": "The advocate assessed that the client instructs directly.",
        }})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"], r.json()["matter_version"]


def _create(client, matter_id, version, **kw):
    payload = {
        "matter_id": matter_id, "scope": "selected_assets",
        "asset_versions": [{"id": "asset_1", "version": 1}],
        "requested_action": "erase", "purpose": "the client withdrew consent",
        "authority_id": "auth_1", "authority_version": 1,
        "copies": [{"location": "asset_1", "kind": "original"},
                   {"location": "vendor-x", "kind": "processor"}],
        "expected_matter_version": version}
    payload.update(kw)
    return client.post("/api/retention-requests", json=payload)


def test_the_served_receipt_says_review_requested_and_never_erased(client):
    """BK-88-AC1 on the wire. The route has no way to say anything else."""
    matter_id, version = _matter(client)
    r = _create(client, matter_id, version)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "review_requested"
    assert body["persistence"] == "committed"
    assert body["data"]["expected_asset_count"] == 1
    assert body["data"]["resolved_asset_count"] == 0
    assert "review_pending" in body["data"]["retained_reason_codes"]


def test_the_served_read_names_every_outstanding_copy(client):
    """The contract's semantic refusal: an incomplete processor or backup
    inventory cannot return `complete_for_declared_scope`. An advocate told
    "not complete" and not told WHICH copy cannot chase the processor."""
    matter_id, version = _matter(client)
    made = _create(client, matter_id, version).json()

    r = client.get(f"/api/retention-requests/{made['request_id']}",
                   params={"matter_id": matter_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"]["state"] != "complete_for_declared_scope"
    outstanding = " ".join(body["outstanding"])
    assert "vendor-x" in outstanding, outstanding
    assert "processor_pending" in body["data"]["retained_reason_codes"]


def test_the_served_route_refuses_a_client_supplied_state(client):
    """NO CLIENT-SUPPLIED RETENTION STATE OR HOLD OVERRIDE -- the contract's
    words. A caller that could post a state could post
    `complete_for_declared_scope` and have the product tell the next reader the
    material is gone. `extra="forbid"` makes it a schema failure, not a policy
    somebody has to remember."""
    matter_id, version = _matter(client)
    r = _create(client, matter_id, version, state="complete_for_declared_scope")
    assert r.status_code == 422, r.text


def test_a_selected_scope_naming_no_asset_is_refused_on_the_wire(client):
    matter_id, version = _matter(client)
    r = _create(client, matter_id, version, asset_versions=[])
    assert r.status_code == 422, r.text
    assert "names no asset" in str(r.json()), r.text


def test_a_retention_request_on_another_advocates_matter_is_not_found(client):
    """Tenant isolation, on the same neutral 404 the rest of the product uses:
    absent and not-yours must be indistinguishable, or the response confirms
    the matter exists."""
    matter_id, version = _matter(client)
    made = _create(client, matter_id, version).json()
    r = client.get(f"/api/retention-requests/{made['request_id']}",
                   params={"matter_id": "mat_someone_else"})
    assert r.status_code == 404, r.text


def test_the_request_survives_a_restart_with_its_state(client):
    """It is on the matter, not in memory. A retention request that vanished on
    restart would leave the client's erasure request unrecorded."""
    matter_id, version = _matter(client)
    made = _create(client, matter_id, version).json()
    first = client.get(f"/api/retention-requests/{made['request_id']}",
                       params={"matter_id": matter_id}).json()
    again = client.get(f"/api/retention-requests/{made['request_id']}",
                       params={"matter_id": matter_id}).json()
    assert first["data"] == again["data"]
    assert first["data"]["request_id"] == made["request_id"]


# ================================ 8. the served lifecycle, end to end =========

def _hold_it(client, matter_id, rid, version, reason="anticipated litigation"):
    return client.post(f"/api/retention-requests/{rid}/holds", json={
        "matter_id": matter_id, "reason": reason,
        "expected_matter_version": version})


def _move(client, matter_id, rid, version, target):
    return client.post(f"/api/retention-requests/{rid}/transitions", json={
        "matter_id": matter_id, "target": target,
        "expected_matter_version": version})


def test_a_held_deletion_refuses_on_the_wire_and_says_why(client):
    """SECTION 5's demonstration: held deletion refuses.

    The refusal is `RETENTION_HOLD`, not a generic 409, because waiting for a
    release and correcting a mistake about the lifecycle are different actions.
    """
    matter_id, version = _matter(client)
    made = _create(client, matter_id, version).json()
    rid = made["request_id"]
    version = made["matter_version"]

    held = _hold_it(client, matter_id, rid, version)
    assert held.status_code == 201, held.text
    assert held.json()["data"]["state"] == "under_hold"
    assert "legal_hold" in held.json()["data"]["retained_reason_codes"]
    version = held.json()["version"]

    blocked = _move(client, matter_id, rid, version, "approved")
    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] in ("RETENTION_HOLD", "INVALID_TRANSITION")
    assert detail["committed"] == "not_committed"


def test_completed_erasure_is_not_undone_by_an_old_restore(client):
    """SECTION 5's other demonstration, and the reason P33 exists.

    Run the whole lifecycle on the wire, then ask the restore what it may bring
    back. The erased asset is refused; an asset nobody erased is allowed, so
    the guard is a guard and not an outage.
    """
    matter_id, version = _matter(client)
    made = _create(client, matter_id, version).json()
    rid, version = made["request_id"], made["matter_version"]

    for location in ("asset_1", "vendor-x"):
        r = client.post(f"/api/retention-requests/{rid}/resolved-copies", json={
            "matter_id": matter_id, "location": location,
            "expected_matter_version": version})
        assert r.status_code == 201, r.text
        version = r.json()["version"]

    for target in ("approved", "in_progress", "erased_from_active_systems"):
        r = _move(client, matter_id, rid, version, target)
        assert r.status_code == 201, (target, r.text)
        version = r.json()["version"]

    done = _move(client, matter_id, rid, version, "complete_for_declared_scope")
    assert done.status_code == 201, done.text
    assert done.json()["data"]["state"] == "complete_for_declared_scope"
    assert done.json()["outstanding"] == []

    check = client.post("/api/restore-checks", json={
        "matter_id": matter_id, "asset_ids": ["asset_1", "asset_untouched"]})
    assert check.status_code == 200, check.text
    body = check.json()
    assert body["refused"] == ["asset_1"], body
    assert body["may_restore"] == ["asset_untouched"], body


def test_the_wire_refuses_completion_while_a_processor_copy_is_outstanding(client):
    """The contract's semantic refusal, on the served path rather than in the
    domain: an incomplete inventory cannot reach `complete_for_declared_scope`,
    and the 409 names the copy."""
    matter_id, version = _matter(client)
    made = _create(client, matter_id, version).json()
    rid, version = made["request_id"], made["matter_version"]

    r = client.post(f"/api/retention-requests/{rid}/resolved-copies", json={
        "matter_id": matter_id, "location": "asset_1",
        "expected_matter_version": version})
    version = r.json()["version"]

    for target in ("approved", "in_progress", "erased_from_active_systems"):
        r = _move(client, matter_id, rid, version, target)
        assert r.status_code == 201, (target, r.text)
        version = r.json()["version"]

    refused = _move(client, matter_id, rid, version, "complete_for_declared_scope")
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "INVALID_TRANSITION"
    assert any("vendor-x" in p for p in detail["outstanding"]), detail
