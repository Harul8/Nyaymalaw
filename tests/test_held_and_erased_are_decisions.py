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

from nm.core import retention as rt
from nm.domain import retention as rd
from nm.domain.traceability import refuses

pytestmark = pytest.mark.class_a


def _request(**kw) -> rd.RetentionRequest:
    base = dict(
        request_id="rr_1", matter_id="mat_1", requested_by="adv_1",
        requested_at="2026-09-13", scope=rd.RequestScope.SELECTED_ASSETS,
        requested_action=rd.RequestedAction.ERASE, purpose="the client asked",
        authority_id="auth_1", authority_version=1,
        assets=(rd.AssetRef(id="a1", version=1),))
    base.update(kw)
    return rd.request(**base)


def _hold(hold_id: str = "h1") -> rd.Hold:
    return rd.Hold(hold_id=hold_id, reason="anticipated litigation",
                   placed_by="adv_1", placed_at="2026-09-13")


# ============================================ 1. a receipt is not an erasure ==

def test_a_received_request_can_only_ever_be_review_requested():
    """THE CONTRACT'S "receipt never means erased", made unrepresentable.

    Not forbidden by a check that a later caller could forget -- `request()`
    takes no state at all, so there is no argument to get wrong. The three
    actions all land in the same place, because what was ASKED FOR and what has
    HAPPENED are different questions and only the first has been answered.
    """
    for action in rd.RequestedAction:
        made = _request(requested_action=action)
        assert made.state is rd.RetentionState.REVIEW_REQUESTED, (
            f"a {action.value} request was received as {made.state.value}; a "
            f"receipt is a record that somebody asked, not that anything ran")

    assert "state" not in rd.request.__code__.co_varnames[
        :rd.request.__code__.co_argcount + rd.request.__code__.co_kwonlyargcount], (
        "`request()` accepts a state, so a caller can post one. The contract's "
        "receipt rule then depends on every caller remembering it")


def test_an_empty_selection_is_refused_rather_than_read_as_everything():
    """A scope naming nothing is not a scope. Read as "everything" it erases
    the matter; read as "nothing" it reports a completed erasure over an empty
    set -- which is the more dangerous of the two, because it succeeds."""
    with pytest.raises(ValueError, match="names no asset"):
        _request(assets=())


# ================================================= 2. the transition table ===

def test_a_request_cannot_jump_to_a_state_it_did_not_reach():
    """THE INCONSISTENT TRANSITION BK-85-AC4 NAMES, refused by name.

    Every pair absent from `_ALLOWED` is refused, and the refusal says what the
    request may become instead -- a caller told only "no" cannot tell the
    advocate what happened.
    """
    made = _request()
    refused = rd.refuse_transition(
        made, rd.RetentionState.COMPLETE_FOR_DECLARED_SCOPE)
    assert "not a lifecycle transition" in refused
    assert "review_requested" in refused and "complete_for_declared_scope" in refused

    with pytest.raises(ValueError, match="not a lifecycle transition"):
        rd.advance(made, rd.RetentionState.ERASED_FROM_ACTIVE_SYSTEMS)


def test_a_terminal_state_has_no_way_back():
    """A completed erasure that could return to APPROVED would let a later
    write undo the tombstone, and the material would come back with nothing
    objecting."""
    for terminal in (rd.RetentionState.COMPLETE_FOR_DECLARED_SCOPE,
                     rd.RetentionState.DECLINED):
        assert rd._ALLOWED[terminal] == frozenset(), (
            f"{terminal.value} leads somewhere; a terminal state that can be "
            f"left is not terminal")


def test_a_repeated_transition_is_refused_rather_than_bumping_the_version():
    """Re-issuing the same move is not a state change. Allowing it would let a
    retried request advance the version and lose a concurrent write."""
    made = _request()
    assert "already review_requested" in rd.refuse_transition(
        made, rd.RetentionState.REVIEW_REQUESTED)


# ========================================================== 3. holds refuse ===

@refuses("I1", 0)
def test_material_under_a_hold_is_not_erased():
    """THE HOLD REFUSES, and the request stays visible rather than failing
    quietly. An erasure that runs under a hold destroys material somebody was
    legally required to keep, and no later step recovers it."""
    made = rt.place_hold(_request(), _hold())
    assert made.state is rd.RetentionState.UNDER_HOLD
    assert rd.RetainedReason.LEGAL_HOLD in made.retained_reason_codes

    # THE HOLD MUST BE WHAT REFUSES, AND FROM `UNDER_HOLD` IT IS NOT.
    #
    # Caught by a planted violation: disabling the hold check entirely left
    # this test green, because from UNDER_HOLD the transition TABLE already
    # refuses APPROVED and IN_PROGRESS. The test was passing for a reason it
    # did not name -- the shape CLAUDE.md calls a test that asserts current
    # behaviour rather than the rule.
    #
    # The hold check is load-bearing exactly where the table would otherwise
    # permit the move, and that state is reachable: `from_dict` reconstructs a
    # stored request at whatever state it was saved in, holds included. So the
    # request is built the way storage hands one back.
    stored = rt.from_dict({**rt.as_dict(made),
                           "state": rd.RetentionState.APPROVED.value})
    assert stored.state is rd.RetentionState.APPROVED
    assert stored.active_holds, "the fixture lost the hold it is testing"
    assert rd.RetentionState.IN_PROGRESS in rd._ALLOWED[stored.state], (
        "the table now refuses this move on its own, so this test would pass "
        "again without the hold check; pick a state where the table permits it")

    refused = rd.refuse_transition(stored, rd.RetentionState.IN_PROGRESS)
    assert refused, "a request with a live hold was allowed to start erasing"
    assert "hold" in refused.lower(), refused


def test_releasing_a_hold_does_not_resume_the_work_it_interrupted():
    """It returns to REVIEW_REQUESTED. Resuming automatically is how a hold
    placed for one purpose silently authorises the erasure it interrupted --
    the reason for the hold may have changed what should happen at all."""
    held = rt.place_hold(_request(), _hold())
    freed = rt.release_hold(held, "h1", by="adv_1", at="2026-09-20")
    assert freed.state is rd.RetentionState.REVIEW_REQUESTED
    assert freed.active_holds == ()


def test_a_hold_nobody_placed_cannot_be_released():
    """ADVERSARIAL. Releasing an unplaced hold would report material as free to
    erase on the strength of a name the caller invented."""
    with pytest.raises(ValueError, match="no hold"):
        rt.release_hold(_request(), "h-does-not-exist", by="x", at="2026-09-20")


# =================================== 4. completion is counted, not declared ===

def test_completion_is_refused_while_any_copy_is_unresolved():
    """THE CENTRAL RULE. Named copies, named refusals.

    The processor and the backup are reported separately because "our processor
    still has it" and "a backup still has it" are different things to tell a
    client, and the contract gives them different reason codes.
    """
    made = _request(copies=(
        rd.Copy(location="a1", kind="original", resolved_at="2026-09-14"),
        rd.Copy(location="a1#transcript", kind="derivative"),
        rd.Copy(location="vendor-x", kind="processor"),
        rd.Copy(location="nightly-2026-09-01", kind="backup")))
    problems = made.completion_problems()
    assert any("a1#transcript" in p for p in problems)
    assert any("vendor-x" in p for p in problems)
    assert any("nightly-2026-09-01" in p for p in problems)
    codes = made.retained_reason_codes
    assert rd.RetainedReason.PROCESSOR_PENDING in codes
    assert rd.RetainedReason.BACKUP_EXPIRY in codes


def test_an_empty_inventory_is_an_unrun_search_and_not_proof_of_no_copies():
    """CLAUDE.md §9 at the exact place it costs most. Zero known copies over a
    named asset is the absence of a search, and reading it as "nothing to
    delete" produces a completed erasure nobody performed."""
    made = _request(copies=())
    assert any("unrun search" in p for p in made.completion_problems())
    assert made.resolved_asset_count == 0


def test_restricting_access_is_never_reported_as_erasure():
    """ARCHIVING, WITHDRAWING ACCESS AND ERASING ARE THREE THINGS. A
    restriction reporting itself as a deletion is a false statement about
    material that still exists and is still discoverable."""
    made = _request(requested_action=rd.RequestedAction.RESTRICT_ACCESS,
                    copies=(rd.Copy(location="a1", kind="original",
                                    resolved_at="2026-09-14"),))
    assert any("not to erase" in p for p in made.completion_problems())


def test_a_fully_resolved_scope_may_complete_and_that_path_actually_works():
    """THE POSITIVE CONTROL. A rule that refuses everything is not a rule --
    it is an outage, and it would pass every test above."""
    made = _request(copies=(rd.Copy(location="a1", kind="original"),))
    made = rt.resolve_copy(made, "a1", at="2026-09-14")
    made = rd.advance(made, rd.RetentionState.APPROVED)
    made = rd.advance(made, rd.RetentionState.IN_PROGRESS)
    made = rt.erase_from_active_systems(made, at="2026-09-15")
    assert made.completion_problems() == ()
    done = rd.advance(made, rd.RetentionState.COMPLETE_FOR_DECLARED_SCOPE)
    assert done.state is rd.RetentionState.COMPLETE_FOR_DECLARED_SCOPE
    assert done.resolved_asset_count == done.expected_asset_count == 1


def test_a_copy_nobody_inventoried_cannot_be_resolved():
    """ADVERSARIAL. Resolving an unlisted location raises the resolved count
    without resolving anything, which is the cheapest possible way to forge a
    completion."""
    with pytest.raises(ValueError, match="no copy at"):
        rt.resolve_copy(_request(copies=()), "invented", at="2026-09-14")


# ======================================= 5. tombstones and the restore guard ==

def test_erasure_writes_a_tombstone_for_every_asset_in_one_step():
    """A tombstone that could be written separately from the erasure can be
    missing when the restore asks -- which has the same effect as never having
    erased: the material returns and nothing objects."""
    made = _request(assets=(rd.AssetRef(id="a1", version=1),
                            rd.AssetRef(id="a2", version=3)),
                    copies=(rd.Copy(location="a1", resolved_at="x"),
                            rd.Copy(location="a2", resolved_at="x")))
    made = rd.advance(made, rd.RetentionState.APPROVED)
    made = rd.advance(made, rd.RetentionState.IN_PROGRESS)
    made = rt.erase_from_active_systems(made, at="2026-09-15")
    assert {t.asset_id for t in made.tombstones} == {"a1", "a2"}
    assert all(t.request_id == "rr_1" for t in made.tombstones)


def test_a_pre_erasure_restore_cannot_bring_tombstoned_material_back():
    """THE DEFECT THIS PACKET EXISTS FOR, on the served rule.

    A backup predates the erasure and does not know about it. Restoring it
    looks like a successful recovery while it re-exposes exactly the material
    the client was told was gone. The guard reads the WHOLE matter's
    tombstones, because the restore has no idea which request erased what.
    """
    made = _request(copies=(rd.Copy(location="a1", resolved_at="x"),))
    made = rd.advance(made, rd.RetentionState.APPROVED)
    made = rd.advance(made, rd.RetentionState.IN_PROGRESS)
    made = rt.erase_from_active_systems(made, at="2026-09-15")

    refused = rt.refuse_restore((made,), ("a1", "a-never-erased"))
    assert refused == ("a1",), (
        "the restore guard let an erased asset back in, or refused one that "
        "was never erased")


def test_the_restore_guard_permits_a_restore_that_touches_nothing_erased():
    """THE NEGATIVE CONTROL. A guard that refuses every restore is an outage
    dressed as a control, and it would satisfy the test above."""
    assert rt.refuse_restore((_request(),), ("a1", "a2")) == ()


# ================================================== 6. persistence and decay ==

def test_a_request_survives_the_round_trip_with_its_state_and_lineage():
    made = _request(copies=(rd.Copy(location="a1", kind="processor"),),
                    holds=(_hold(),))
    back = rt.from_dict(rt.as_dict(made))
    assert back.state is made.state
    assert back.copies == made.copies
    assert back.holds == made.holds
    assert back.retained_reason_codes == made.retained_reason_codes


def test_an_unreadable_stored_state_falls_to_the_claim_that_says_least():
    """ADVERSARIAL, and the direction matters. A corrupt row must not read as
    a completed erasure: that is the one value which tells the next reader the
    material is gone when nobody knows whether it is."""
    row = rt.as_dict(_request())
    row["state"] = "obliterated"
    assert rt.from_dict(row).state is rd.RetentionState.REVIEW_REQUESTED


def test_the_served_projection_cannot_say_complete_on_its_own():
    """The word can only appear because the request reached the state through
    `refuse_transition`, which counts. There is no path from the projection to
    that string."""
    # THE COMPILED CONSTANTS, NOT THE SOURCE. The docstring names the state to
    # explain the rule, and reading the source caught that instead of the code
    # -- a check that fails on its own explanation is a check nobody keeps.
    # `co_consts[0]` is the docstring; everything after it is a literal the
    # function can actually emit.
    literals = [c for c in rt.projection.__code__.co_consts[1:]
                if isinstance(c, str)]
    assert "complete_for_declared_scope" not in literals, (
        f"the projection carries the completion state as a literal {literals}, "
        f"so it can emit it without the request having reached it")


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
