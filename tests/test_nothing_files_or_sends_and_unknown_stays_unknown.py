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
from nm.domain.action import (
    CONNECTOR_ENABLED,
    REQUIRED_BEFORE_CONFIRMATION,
    ActionProposal,
    ActionState,
    audit_row,
    confirm,
    export,
    reconcile,
    record_outcome,
    refuse_dispatch,
)

pytestmark = pytest.mark.class_a

DIGEST = "abc123def456"


def _proposal(**kw) -> ActionProposal:
    base = dict(proposal_id="ap_1", matter_id="m1", package_id="pkg_1",
                actor="adv_1", authority="the instructing advocate",
                object="the plaint", destination="City Civil Court, Hyderabad",
                content_digest=DIGEST)
    base.update(kw)
    return ActionProposal(**base)


def _exported() -> ActionProposal:
    return export(confirm(_proposal(), by="adv_1", at="2026-09-13",
                          digest=DIGEST))


# =============================== 1. the connector is off =====================

def test_the_connector_is_a_constant_and_it_is_off():
    """Not configuration. A flag a deployment could flip is a flag a
    deployment will flip, and the act on the other side is irreversible."""
    assert CONNECTOR_ENABLED is False


def test_dispatch_is_refused_and_the_refusal_names_the_decision():
    """An advocate told only "no" cannot tell whether this is a bug or the
    product working as designed."""
    refused = refuse_dispatch(confirm(_proposal(), by="adv_1",
                                      at="2026-09-13", digest=DIGEST))
    assert "CHOICE-09" in refused
    assert "disabled" in refused
    assert "nothing here can send it" in refused


def test_an_incomplete_proposal_is_refused_before_the_connector_line():
    """An advocate about to file this BY HAND needs to know it names no
    destination just as much as an automated sender would."""
    refused = refuse_dispatch(ActionProposal(
        proposal_id="ap_1", matter_id="m1", package_id="pkg_1"))
    assert "does not record" in refused
    assert "acted on by hand" in refused


def test_every_consequential_field_is_required_before_confirmation():
    """BK-56-AC4: current actor authority, object, destination, final content
    digest and explicit confirmation."""
    bare = ActionProposal(proposal_id="ap_1", matter_id="m1", package_id="p")
    assert len(bare.absent()) == len(REQUIRED_BEFORE_CONFIRMATION) == 5
    with pytest.raises(ValueError, match="does not record"):
        confirm(bare, by="adv_1", at="2026-09-13", digest=DIGEST)


# ========================== 2. approval is for exact bytes ===================

def test_an_approval_does_not_survive_an_edit():
    """The whole failure mode an approval exists to prevent. Confirming
    against whatever the object currently says would let a later change ride
    on an approval nobody gave it."""
    with pytest.raises(ValueError, match="content moved"):
        confirm(_proposal(), by="adv_1", at="2026-09-13", digest="something-else")


def test_a_matching_digest_confirms():
    """THE POSITIVE CONTROL."""
    done = confirm(_proposal(), by="adv_1", at="2026-09-13", digest=DIGEST)
    assert done.state is ActionState.APPROVED and done.confirmed is True


def test_only_an_approved_proposal_can_be_exported():
    with pytest.raises(ValueError, match="only an approved proposal"):
        export(_proposal())


# ================= 3. seven distinct states, and unknown is one ==============

def test_the_seven_states_are_distinct():
    assert {s.value for s in ActionState} == {
        "prepared", "approved", "exported", "delivery_unknown", "delivered",
        "refused", "cancelled"}


def test_delivery_unknown_is_not_settled_and_claims_nothing():
    """It needs somebody to find out. Treating it as settled is how a live
    deadline stops being watched."""
    assert ActionState.DELIVERY_UNKNOWN.is_settled is False
    assert ActionState.DELIVERY_UNKNOWN.claims_arrival is False
    assert ActionState.DELIVERED.claims_arrival is True


def test_cancelled_and_refused_are_different_states():
    """Cancelled is stopped before anything left; refused is an answer from
    outside. Collapsing them loses whether the outside ever saw it."""
    assert ActionState.CANCELLED is not ActionState.REFUSED
    assert ActionState.CANCELLED.is_settled and ActionState.REFUSED.is_settled


def test_delivered_requires_a_receipt():
    """*receipt required for completed*, and CHOICE-09's fallback: never
    simulate a filed or sent status."""
    with pytest.raises(ValueError, match="carries the receipt"):
        record_outcome(_exported(), state=ActionState.DELIVERED, at="t")


def test_an_unknown_or_refused_outcome_records_why():
    with pytest.raises(ValueError, match="records why"):
        record_outcome(_exported(), state=ActionState.DELIVERY_UNKNOWN, at="t")


def test_a_timeout_becomes_unknown_and_never_delivered():
    """THE PACKET'S CENTRAL CASE. The wire went quiet; the filing may have
    landed."""
    out = record_outcome(_exported(), state=ActionState.DELIVERY_UNKNOWN,
                         because="the court portal timed out", at="t")
    assert out.state is ActionState.DELIVERY_UNKNOWN
    assert out.state.claims_arrival is False


# ============================ 4. reconciliation ==============================

def test_reconciliation_without_a_receipt_leaves_the_state_alone():
    """*inconclusive remains outcome_unknown*. A reconciliation that cannot
    answer must not guess -- and the attempt is recorded so the advocate can
    see it was looked into."""
    unknown = record_outcome(_exported(), state=ActionState.DELIVERY_UNKNOWN,
                             because="timed out", at="t1")
    after = reconcile(unknown, evidence="portal lookup returned nothing", at="t2")
    assert after.state is ActionState.DELIVERY_UNKNOWN
    assert "still unknown" in after.outcome_because
    assert len(after.attempts) == len(unknown.attempts) + 1


def test_reconciliation_has_no_way_for_a_person_to_assert_success():
    """*user cannot submit success=true*. The person who wants it to have
    arrived is not the evidence that it did."""
    names = reconcile.__code__.co_varnames[
        :reconcile.__code__.co_argcount + reconcile.__code__.co_kwonlyargcount]
    for forbidden in ("success", "delivered", "state", "outcome"):
        assert forbidden not in names, (
            f"reconcile takes {forbidden!r}, so a caller can assert the answer")


def test_a_receipt_resolves_it_and_a_duplicate_receipt_changes_nothing():
    """Reconciling the same receipt twice is idempotent by construction: the
    outcome is derived from the evidence, so nothing is repeated."""
    unknown = record_outcome(_exported(), state=ActionState.DELIVERY_UNKNOWN,
                             because="timed out", at="t1")
    first = reconcile(unknown, evidence="registry lookup", receipt="RCT-99",
                      at="t2")
    assert first.state is ActionState.DELIVERED and first.receipt == "RCT-99"

    with pytest.raises(ValueError, match="only an unknown outcome"):
        reconcile(first, evidence="registry lookup", receipt="RCT-99", at="t3")


def test_reconciliation_never_redispatches():
    """*no automatic redispatch in reconciliation endpoint*. Asking whether it
    arrived must not be a way to send it again -- that is how a duplicate
    filing happens."""
    # WHAT THE FUNCTION CAN CALL, not what its prose mentions.
    #
    # Third time in this session that a check of mine matched an explanation
    # instead of the code -- the docstring here contains the word "redispatch"
    # BECAUSE it is explaining the rule. `co_names` is every global the
    # compiled function can reach, which is the thing that would have to
    # change for a redispatch to appear.
    reachable = set(reconcile.__code__.co_names)
    for sending in ("dispatch", "send", "post", "transmit", "execute"):
        assert not any(sending in name for name in reachable), (
            f"reconcile can reach {sorted(n for n in reachable if sending in n)}; "
            f"asking about an outcome must never cause one")
    assert "record_outcome" in reachable, (
        "reconcile no longer routes its result through the one place that "
        "requires a receipt for DELIVERED")


# ================================ 5. the audit record ========================

def test_the_audit_row_carries_the_digest_and_never_the_content():
    """BK-56-AC4 asks for a complete attributable record; the material is
    privileged. The same line P26 drew when the plaintext metrics record
    turned out to be quoting the advocate's own words."""
    row = audit_row(_exported())
    assert row["content_digest"] == DIGEST
    assert "object" not in row
    assert "the plaint" not in repr(row)
    assert row["actor"] and row["authority"] and row["destination"]


def test_the_audit_row_says_whether_a_receipt_exists_without_quoting_it():
    delivered = record_outcome(_exported(), state=ActionState.DELIVERED,
                               receipt="RCT-99", because="filed", at="t")
    row = audit_row(delivered)
    assert row["has_receipt"] is True
    assert "RCT-99" not in repr(row)


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
