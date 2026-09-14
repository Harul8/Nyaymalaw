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
from nm.core.screens import Capacity as InstructingCapacity
from nm.core.screens import Engagement as ScreenedEngagement
from nm.core.screens import (
    Screen,
    ScreenKind,
    ScreenState,
    may_admit_substance,
    unscreened,
)
from nm.domain.emergency import DEFAULT_HOURS, Declaration, latest

from tests.test_professional_approval_is_separate_from_account_access import approve_fixture_account

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 11, 10, 0, 0)


def _declared(**over) -> Declaration:
    base = dict(
        actor_id="adv-1",
        basis="the client is being questioned at the police station",
        outstanding=("conflict: never run", "competence: never run"),
        now=NOW,
    )
    base.update(over)
    return Declaration.declare(**base)


def test_same_second_redeclaration_uses_later_append_not_a_longer_earlier_grant():
    older = _declared(hours=24)
    newer = _declared(hours=1)
    assert older.as_dict()["declared_at"] == newer.as_dict()["declared_at"]
    assert latest((older.as_dict(), newer.as_dict()), NOW).expires_at == newer.expires_at
    assert latest((older.as_dict(), newer.as_dict()), NOW + timedelta(hours=2)) is None


@pytest.mark.parametrize("bad", ["damaged", "", False, 99, []])
def test_malformed_stored_revocation_is_not_absent_and_never_revives_an_older_grant(bad):
    older = _declared(hours=24)
    malformed = {**_declared(hours=1).as_dict(), "revoked_at": bad}
    assert Declaration.from_stored(malformed) is None
    assert latest((older.as_dict(), malformed), NOW) is None


def test_unreadable_emergency_history_is_reported_incomplete_through_the_wire(client):
    from dataclasses import replace

    from nm.edge.api import application

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


def test_an_unavailable_screen_never_clears():
    """All three non-CLEAR states share this property and it is the reason the
    enum exists."""
    screen = Screen(
        kind=ScreenKind.CONFLICT,
        state=ScreenState.UNAVAILABLE,
        detail="the registry host did not answer",
    )
    assert screen.clears is False
    assert may_admit_substance((screen,))[0] is False


def test_unavailable_and_not_assessed_read_differently():
    """The only reason to have four states is that THE FIX DIFFERS: an
    unassessed screen needs somebody to run it, and an unavailable one needs
    the registry back before anybody can."""
    down = Screen(
        kind=ScreenKind.CONFLICT,
        state=ScreenState.UNAVAILABLE,
        detail="the registry host did not answer",
    )
    never = Screen(
        kind=ScreenKind.CONFLICT,
        state=ScreenState.NOT_ASSESSED,
        not_assessed_because="nobody has run it",
    )

    # THE CONFLICT ENTRY, not index 0 -- `unscreened` reports every screen on
    # the matter and the first is the emergency screen, identical in both.
    def conflict_line(screen):
        return next(x for x in unscreened((screen,)) if x.startswith("conflict"))

    assert conflict_line(down) != conflict_line(never)
    assert "unavailable" in conflict_line(down)
    assert "not_assessed" in conflict_line(never)


def test_every_screen_state_is_mapped_to_a_gate_state_explicitly():
    """A new enum member falling through `table.get`'s default is how a state
    nobody mapped starts reading as one somebody did."""
    from nm.core.screens import GATE_FOR

    for kind, (_gate_id, table) in GATE_FOR.items():
        missing = [s.value for s in ScreenState if s not in table]
        assert not missing, f"{kind.value} does not map {missing}"


# ======================= the declaration is a record ========================


def test_a_declaration_carries_who_why_what_was_outstanding_and_when_it_ends():
    """A boolean is exactly enough to admit substance and nothing like enough
    to answer the questions asked afterwards."""
    declared = _declared()
    assert declared.actor_id == "adv-1"
    assert "police station" in declared.basis
    assert declared.outstanding == ("conflict: never run", "competence: never run")
    assert declared.expires_at == NOW + timedelta(hours=DEFAULT_HOURS)


def test_a_declaration_without_a_basis_is_refused():
    """A declaration with no basis is a switch, and a switch is what this
    record exists to stop the emergency route from being."""
    for blank in ("", "   "):
        with pytest.raises(ValueError):
            Declaration.declare("adv-1", blank, (), NOW)


def test_the_outstanding_screens_are_frozen_at_the_moment_of_declaration():
    """They are the justification. A list recomputed later would silently
    rewrite why the exception was taken."""
    declared = _declared()
    assert declared.outstanding == ("conflict: never run", "competence: never run")
    # Later screens clearing does not retroactively empty the justification.
    assert _declared().outstanding == declared.outstanding


# ============================ expiry is the clock ===========================


def test_expiry_is_a_question_about_a_moment_and_not_a_stored_flag():
    """Re-entry two days later must get the true answer rather than the one
    that was true when somebody last wrote a field."""
    declared = _declared()
    assert declared.active_at(NOW) is True
    assert declared.active_at(NOW + timedelta(hours=DEFAULT_HOURS + 1)) is False
    assert declared.state_at(NOW) == "live"
    assert declared.state_at(NOW + timedelta(hours=48)) == "expired"


def test_an_expired_declaration_keeps_its_urgency_on_the_file(client=None):
    """What lapses is the PERMISSION, not the history. The urgency was real
    and remains evidence of why the file was handled as it was."""
    declared = _declared()
    later = NOW + timedelta(hours=48)
    said = declared.said(later)
    assert "lapsed" in said
    assert "stands on the file" in said
    assert "ordinary screens are required" in said


def test_only_a_live_declaration_governs():
    """An expired one must never be returned as though it still permitted
    anything."""
    expired = _declared()
    later = NOW + timedelta(hours=48)
    assert latest((expired.as_dict(),), NOW) is not None
    assert latest((expired.as_dict(),), later) is None


def test_a_re_declaration_is_a_second_record():
    """Two separate moments of danger are two facts, and keeping only the
    latest would make a file that was urgent twice look urgent once."""
    first = _declared()
    later = NOW + timedelta(hours=48)
    second = _declared(now=later, basis="he has been produced before a magistrate")
    governing = latest((first.as_dict(), second.as_dict()), later)
    assert governing is not None
    assert "magistrate" in governing.basis


# ==================== it admits protection and nothing else =================


@pytest.mark.parametrize("work", ["advice", "research", "draft", "hearing", "negotiation"])
def test_no_substantive_work_product_is_admitted(work):
    """THE POINT OF THE PACKET. An emergency that could be made to admit
    substantive work would be a way of turning the screens off."""
    assert _declared().permits(work) is False


def test_protective_triage_is_admitted():
    """The negative control: a declaration that permitted nothing would be
    safe and would not help the client being questioned."""
    assert _declared().permits("protective_triage") is True


def test_no_argument_widens_what_a_declaration_permits():
    """`permits` takes the work product and nothing else. A parameter that
    could widen it is a parameter somebody passes."""
    import inspect

    signature = inspect.signature(Declaration.permits)
    assert list(signature.parameters) == ["self", "work_product"]


def test_the_exception_says_it_is_an_exception():
    """A file that took one must never read afterwards as a file whose
    screens passed."""
    said = _declared().said(NOW)
    assert "EMERGENCY EXCEPTION" in said
    assert "no substantive analysis" in said
    assert "conflict: never run" in said


def test_the_screen_owner_still_names_the_exception_when_it_admits(client=None):
    """`may_admit_substance` is the owner and P14 does not add a second one."""
    down = Screen(
        kind=ScreenKind.CONFLICT,
        state=ScreenState.UNAVAILABLE,
        detail="the registry host did not answer",
    )
    allowed, why = may_admit_substance((down,), emergency=True)
    assert allowed is True
    assert "EMERGENCY EXCEPTION" in why
    assert "outstanding" in why


# ============================= revocation ===================================


def test_revocation_is_a_new_record_and_not_an_erasure():
    declared = _declared()
    revoked = declared.revoke("adv-2", NOW + timedelta(hours=2))
    assert revoked.revoked_by == "adv-2"
    assert revoked.declared_at == declared.declared_at
    assert revoked.basis == declared.basis
    assert revoked.state_at(NOW + timedelta(hours=3)) == "revoked"
    assert revoked.active_at(NOW + timedelta(hours=3)) is False


def test_a_revoked_declaration_still_shows_the_urgency_that_was_recorded():
    revoked = _declared().revoke("adv-2", NOW + timedelta(hours=2))
    said = revoked.said(NOW + timedelta(hours=3))
    assert "revoked by adv-2" in said
    assert "stands on the file" in said


# ================= capacity to instruct is not account access ===============


def test_capacity_to_instruct_is_recorded_and_not_inferred_from_the_account():
    """BK-53-AC2. An account is a way of signing in. It says nothing about
    whether this person can give instructions, and inferring one from the
    other is how a file gets run on somebody's behalf who could not ask."""
    unassessed = ScreenedEngagement(
        identity="the client",
        authority="a signed authority",
        scope="the possession claim",
        decision_owner="the client",
    )
    assert unassessed.capacity is InstructingCapacity.NOT_ASSESSED
    assert unassessed.reliance_ready is False
    assert any("capacity to instruct" in m for m in unassessed.missing())


def test_capacity_in_doubt_blocks_reliance_even_when_everything_else_is_set():
    in_doubt = ScreenedEngagement(
        identity="the client",
        authority="a signed authority",
        scope="the possession claim",
        decision_owner="the client",
        capacity=InstructingCapacity.IN_DOUBT,
    )
    assert in_doubt.reliance_ready is False
    assert any("in doubt" in m for m in in_doubt.missing())


def test_capacity_not_in_doubt_with_everything_set_is_reliance_ready():
    """The negative control for the two above."""
    ready = ScreenedEngagement(
        identity="the client",
        authority="a signed authority",
        scope="the possession claim",
        decision_owner="the client",
        capacity=InstructingCapacity.NOT_IN_DOUBT,
    )
    assert ready.reliance_ready is True
    assert ready.missing() == ()


def test_the_two_capacity_vocabularies_are_not_the_same_type():
    """`nm.core.screens.Capacity` asks whether the client's capacity TO
    INSTRUCT is in doubt. `nm.domain.authority.ActingAs` asks what part a
    person plays. Two enums called `Capacity` would be one word for both."""
    from nm.domain.authority import ActingAs

    assert InstructingCapacity is not ActingAs
    assert {c.value for c in InstructingCapacity} & {a.value for a in ActingAs} == set()


def test_revoking_the_latest_declaration_never_revives_an_older_one():
    first = _declared()
    second = _declared(now=NOW + timedelta(hours=1))
    revoked = second.revoke("adv-1", NOW + timedelta(hours=2))
    assert latest((first.as_dict(), revoked.as_dict()), NOW + timedelta(hours=3)) is None


@pytest.mark.parametrize("hours", [0, -1, 25, 999999, True, "24"])
def test_emergency_duration_is_bounded_in_the_domain(hours):
    with pytest.raises((TypeError, ValueError)):
        _declared(hours=hours)


def test_the_real_protective_turn_uses_the_live_declaration_without_a_model(client, monkeypatch):
    approve_fixture_account(client.directory)
    from nm.domain.advocate import utcnow
    from nm.edge.api import application

    created = client.post(
        "/api/turn", json={"message": "we act for the plaintiff about an unpaid invoice"}
    )
    assert created.status_code == 200, created.text
    matter_id = client.get("/api/matters").json()["matters"][0]["matter_id"]
    instant = utcnow()
    monkeypatch.setattr("nm.edge.api.utcnow", lambda: instant)
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


def test_declared_emergency_never_clears_ordinary_merits_admission(client):
    approve_fixture_account(client.directory)
    from nm.core.turn import TurnInput
    from nm.domain.metrics import TurnMetrics
    from nm.edge.api import application

    created = client.post(
        "/api/turn", json={"message": "we act for the plaintiff about an invoice"}
    )
    assert created.status_code == 200
    matter_id = client.get("/api/matters").json()["matters"][0]["matter_id"]
    declared = client.post(
        f"/api/matters/{matter_id}/emergency",
        json={"request_key": "merits-check", "basis": "a stated urgency"}
    )
    assert declared.status_code == 200
    matter = application().store.load(matter_id)
    turn = TurnInput(advocate_id="adv_demo", matter_id=matter_id, message="give merits")
    screen = application().engine._screen(
        ScreenKind.EMERGENCY, matter, turn, TurnMetrics(turn_id=turn.turn_id)
    )
    assert screen.state is ScreenState.BLOCKED
    assert "protective_triage" in screen.detail


def test_a_protective_handoff_cannot_emit_a_commit_success_when_save_fails(client, monkeypatch):
    approve_fixture_account(client.directory)
    from nm.core.turn import TurnInput
    from nm.edge.api import application

    made = client.post("/api/turn", json={"message": "we act for the plaintiff about an invoice"})
    assert made.status_code == 200
    matter_id = client.get("/api/matters").json()["matters"][0]["matter_id"]
    assert (
        client.post(
            f"/api/matters/{matter_id}/emergency",
            json={"request_key": "save-check", "basis": "a stated urgent risk"}
        ).status_code
        == 200
    )

    def fail(*args, **kwargs):
        raise OSError("synthetic save failure")

    monkeypatch.setattr(application().store, "commit", fail)
    with pytest.raises(OSError, match="synthetic save failure"):
        application().engine.run(
            TurnInput(
                advocate_id="adv_demo",
                matter_id=matter_id,
                message="do not retain this",
                work_product="protective_triage",
            )
        )


def _declaration_context(client, monkeypatch):
    approve_fixture_account(client.directory)
    from nm.domain.advocate import utcnow

    from tests.test_the_commission_is_served_and_authority_refuses import _matter

    matter_id = _matter(client)
    clock = [utcnow()]
    monkeypatch.setattr("nm.edge.api.utcnow", lambda: clock[0])
    return matter_id, f"/api/matters/{matter_id}/emergency", clock


def test_declaration_retry_reads_the_original_expiry_and_frozen_screens(client, monkeypatch):
    from dataclasses import replace

    from nm.edge.api import application

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
    from nm.edge.api import application

    matter_id, path, clock = _declaration_context(client, monkeypatch)
    offer = {"request_key": "expired-original", "basis": "Synthetic urgent review", "hours": 1}
    first = client.post(path, json=offer)
    assert first.status_code == 200
    saved = application().store.load(matter_id)
    clock[0] += timedelta(hours=2)
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
    from nm.edge.api import application

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
    from nm.edge.api import application

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

    from nm.edge.api import application

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
    from nm.edge.api import application

    matter_id, path, _ = _declaration_context(client, monkeypatch)
    assert client.post(path, json={"request_key": "observed", "basis": "Supplied danger"}
                       ).status_code == 200
    observed = client.get(path).json()
    payload = {"revoke": True, "expected_version": observed["version"],
               "governing_ref": observed["governing_ref"], field: value}
    before = application().store.load(matter_id)
    assert client.post(path, json=payload).status_code == 422
    assert application().store.load(matter_id) == before


def test_legacy_declaration_can_be_ended_only_from_its_observed_reference(client, monkeypatch):
    from dataclasses import replace

    from nm.edge.api import application

    matter_id, path, clock = _declaration_context(client, monkeypatch)
    store = application().store
    current = store.load(matter_id)
    # A historic record has no modern request key. It still has an observed identity.
    store.commit(replace(current, emergencies=(_declared(hours=1, now=clock[0]).as_dict(),),
                         version=current.version + 1), expected_version=current.version)
    observed = client.get(path).json()
    assert observed["governing"] and observed["governing_ref"]
    response = client.post(path, json={"revoke": True, "expected_version": observed["version"],
                                      "governing_ref": observed["governing_ref"]})
    assert response.status_code == 200, response.text
    assert response.json()["governing_ref"] == observed["governing_ref"]
    assert response.json()["version"] == observed["version"] + 1
    assert client.get(path).json()["governing"] is None


@pytest.mark.parametrize("key", [None, "", " ", 17, "bad/key", "x" * 101])
def test_declaration_requires_an_explicit_stable_key_before_writing(client, monkeypatch, key):
    from nm.edge.api import application

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

    from nm.edge.api import application

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

    from nm.edge.api import application

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
    from nm.edge.api import application

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
