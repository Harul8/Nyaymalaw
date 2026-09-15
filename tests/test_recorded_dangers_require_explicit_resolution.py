"""Manual urgency is persisted danger, not an emergency permission or legal advice."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from nm.domain.advocate import utcnow
from nm.domain.urgency import (
    UrgencyClass,
    UrgencyReceipt,
    UrgencyRegister,
    UrgencyState,
    normalise_instruction,
    project,
    read_receipts,
)
from nm.edge.api import application

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


def test_manual_urgency_taxonomy_is_the_named_prd_population_not_an_invented_eleventh_class():
    assert len(UrgencyClass) == 10
    view = project(())
    assert len(view["classes"]) == 10 and view["entries"] == []
    assert all(row["assessment"] == "not_assessed" for row in view["classes"])
    assert "eleven" in view["taxonomy_basis"] and view["unknown_due_is_safe"] is False
    assert {state.value for state in UrgencyState} == {
        "live", "resolved", "cleared", "not_assessed"}


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


def test_nine_real_protective_turns_and_a_fresh_process_preserve_the_same_urgency(
        client, monkeypatch):
    from tests.test_professional_approval_is_separate_from_account_access import (
        approve_fixture_account,
    )

    approve_fixture_account(client.directory)
    matter_id = _matter(client)
    instant = utcnow()
    monkeypatch.setattr("nm.edge.api.utcnow", lambda: instant)
    engine = application().engine
    monkeypatch.setattr(engine, "_clock", lambda: instant)
    raised = _post(client, matter_id, _offer(client, matter_id))
    assert raised.status_code == 200, raised.text
    assert _post(client, matter_id, {"request_key": "permission", "basis": "Supplied danger"}) \
        .status_code == 200
    def forbidden(*args, **kwargs):
        raise AssertionError("manual protective record reached a model or ordinary narrative")
    monkeypatch.setattr(engine, "_read_route", forbidden)
    before = application().store.load(matter_id)
    for turn in range(1, 10):
        version = client.get(f"/api/matters/{matter_id}/emergency").json()["version"]
        reply = client.post("/api/turn", json={"matter_id": matter_id, "turn_id": f"manual-{turn}",
                            "expected_version": version, "message": "Protective handoff requested",
                            "work_product": "protective_triage"})
        assert reply.status_code == 200, reply.text
        first = reply.json()["elements"][0]["text"]
        assert "RECORDED LIVE URGENCY" in first
        for supplied in ("Contact the responsible advocate", "Instructing advocate", "14:30"):
            assert supplied in first
        assert "not independently verified" in first
    stored = application().store.load(matter_id)
    assert stored.urgency_records == before.urgency_records
    assert len(stored.emergency_triage) == 9 and stored.facts == before.facts
    from tests.test_turn_contract import KEY
    script = ("import json,sys; from pathlib import Path; "
              "from nm.adapters.store.file_store import FileMatterStore; "
              "from nm.domain.urgency import project; "
              "m=FileMatterStore(Path(sys.argv[1]),key=sys.argv[2]).load(sys.argv[3]); "
              "print(json.dumps({'urgency':project(m.urgency_records),'turns':len(m.emergency_triage)}))")
    restarted = subprocess.run([sys.executable, "-c", script, str(application().store._root),
                                KEY, matter_id], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=20)
    assert restarted.returncode == 0, restarted.stderr
    recovered = json.loads(restarted.stdout)
    assert recovered["turns"] == 9
    assert recovered["urgency"] == project(stored.urgency_records)


@pytest.mark.parametrize("end", ["expiry", "revocation"])
def test_permission_ending_cannot_resolve_or_hide_a_live_danger(client, monkeypatch, end):
    from tests.test_professional_approval_is_separate_from_account_access import (
        approve_fixture_account,
    )

    approve_fixture_account(client.directory)
    matter_id = _matter(client)
    instant = utcnow()
    monkeypatch.setattr("nm.edge.api.utcnow", lambda: instant)
    assert _post(client, matter_id, _offer(client, matter_id)).status_code == 200
    assert _post(client, matter_id, {"request_key": "permission", "basis": "Supplied danger",
                                   "hours": 1}).status_code == 200
    before = application().store.load(matter_id).urgency_records
    view = client.get(f"/api/matters/{matter_id}/emergency").json()
    if end == "expiry":
        monkeypatch.setattr("nm.edge.api.utcnow", lambda: instant + timedelta(hours=2))
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


def test_two_known_windows_and_an_unknown_remain_visible_with_nearest_known_first(client):
    matter_id = _matter(client)
    for key, due in (("late", "2026-09-13T09:00:00Z"), ("early", "2026-09-12T09:00:00Z"),
                     ("unknown", None)):
        instruction = _instruction(
            basis=key, due=due,
            unknowns={"due": "Awaiting the served order"} if due is None else {})
        result = _post(client, matter_id, _offer(client, matter_id, key, urgency=instruction))
        assert result.status_code == 200, result.text
    view = client.get(f"/api/matters/{matter_id}/emergency").json()["urgency_register"]
    assert [row["basis"] for row in view["entries"]] == ["early", "late", "unknown"]
    assert len({row["urgency_id"] for row in view["entries"]}) == 3
    assert all(row["state"] == "live" for row in view["entries"])
    assert view["entries"][-1]["unknowns"]["due"] == "Awaiting the served order"
    assert all(row["assessment"] == "not_assessed" for row in view["classes"])
    observed = client.get(f"/api/matters/{matter_id}/emergency").json()
    resolved = _post(client, matter_id, {
        "urgency_command": "resolve", "request_key": "resolve-only-earliest",
        "expected_version": observed["version"], "urgency_id": view["entries"][0]["urgency_id"],
        "resolution_basis": "Only this reported danger has been addressed"})
    assert resolved.status_code == 200, resolved.text
    current = project(application().store.load(matter_id).urgency_records)["entries"]
    assert {row["basis"]: row["state"] for row in current} == {
        "early": "resolved", "late": "live", "unknown": "live"}


def test_exact_raise_and_resolution_replays_never_duplicate_or_revive_the_danger(client):
    matter_id = _matter(client)
    offered = _offer(client, matter_id)
    first = _post(client, matter_id, offered)
    assert first.status_code == 200, first.text
    assert _post(client, matter_id, offered).json()["replayed"] is True
    row = first.json()
    resolution = {"urgency_command": "resolve", "urgency_id": row["urgency_id"],
                  "resolution_basis": "Responsible advocate confirmed the danger was addressed",
                  "expected_version": row["version"], "request_key": "resolve-danger"}
    resolved = _post(client, matter_id, resolution)
    assert resolved.status_code == 200, resolved.text
    before = application().store.load(matter_id)
    assert _post(client, matter_id, resolution).json()["replayed"] is True
    assert _post(client, matter_id, offered).json()["replayed"] is True
    assert application().store.load(matter_id) == before
    saved = project(before.urgency_records)["entries"][0]
    assert saved["state"] == "resolved" and saved["resolver"] == before.advocate_id
    assert saved["resolved_at"] and saved["resolution_basis"]
    assert before.emergencies == () and len(before.urgency_operations) == 2
    handoff = client.post("/api/turn", json={"matter_id": matter_id, "turn_id": "after-resolution",
                          "expected_version": before.version, "message": "Protective handoff",
                          "work_product": "protective_triage"})
    assert handoff.status_code == 200, handoff.text
    assert not any("RECORDED LIVE URGENCY" in element["text"]
                   for element in handoff.json()["elements"])
    assert application().store.load(matter_id).urgency_records == before.urgency_records


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


def test_postgres_uses_the_same_complete_urgency_and_receipt_serialization_without_columns():
    from nm.adapters.store.postgres import _decode, _encode
    from nm.domain.matter import Matter

    row = UrgencyRegister.raise_manual("urgency-1", _instruction(), "advocate-1", utcnow())
    receipt = UrgencyReceipt(
        "r", {"actor_id": "advocate-1", "command": "raise", "expected_version": 0,
              "urgency": normalise_instruction(_instruction())}, "matter-1", row.urgency_id, 1)
    matter = Matter(id="matter-1", advocate_id="advocate-1", title="Synthetic", version=1,
                    urgency_records=(row.as_dict(),), urgency_operations=(receipt.as_dict(),))
    recovered = _decode(json.loads(json.dumps(_encode(matter))))
    assert recovered.urgency_records == matter.urgency_records
    assert recovered.urgency_operations == matter.urgency_operations
    assert UrgencyRegister.from_stored(recovered.urgency_records[0]) == row
    assert read_receipts(recovered.urgency_operations, (row,), recovered.id, recovered.version) == {
        "r": receipt}


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


@pytest.mark.parametrize("mutation", ["live_again", "different_resolver", "different_basis"])
def test_a_resolution_receipt_must_match_its_named_saved_resolution(client, mutation):
    matter_id = _matter(client)
    first = _post(client, matter_id, _offer(client, matter_id))
    assert first.status_code == 200, first.text
    resolution = {"urgency_command": "resolve", "request_key": "resolved",
                  "expected_version": first.json()["version"],
                  "urgency_id": first.json()["urgency_id"],
                  "resolution_basis": "The responsible advocate recorded the danger addressed"}
    assert _post(client, matter_id, resolution).status_code == 200
    store = application().store
    path = store._path(matter_id)
    original = path.read_bytes()
    payload = json.loads(store._open(matter_id, original))
    assert len(payload["urgency_records"]) == 1
    row = payload["urgency_records"][0]
    if mutation == "live_again":
        row.update(state="live", resolver=None, resolved_at=None, resolution_basis=None)
    elif mutation == "different_resolver":
        row["resolver"] = "a-different-resolver"
    else:
        row["resolution_basis"] = "A different resolution basis"
    damaged = store._seal(matter_id, json.dumps(payload).encode("utf-8"))
    assert damaged != original
    path.write_bytes(damaged)
    try:
        # The danger alone still parses; the cross-record claim is what must fail.
        assert project(store.load(matter_id).urgency_records)["state"] == "ok"
        response = _post(client, matter_id, resolution)
        assert response.status_code == 503, response.text
        assert path.read_bytes() == damaged
    finally:
        path.write_bytes(original)


def test_historical_raise_and_resolution_replay_reconstruct_only_their_accepted_result(client):
    matter_id = _matter(client)
    offered = _offer(client, matter_id)
    raised = _post(client, matter_id, offered)
    assert raised.status_code == 200, raised.text
    resolution = {"urgency_command": "resolve", "request_key": "resolved",
                  "expected_version": raised.json()["version"],
                  "urgency_id": raised.json()["urgency_id"],
                  "resolution_basis": "The responsible advocate recorded the danger addressed"}
    resolved = _post(client, matter_id, resolution)
    assert resolved.status_code == 200, resolved.text
    later = _post(client, matter_id, _offer(client, matter_id, "later-danger"))
    assert later.status_code == 200, later.text
    store = application().store
    before = store.load(matter_id)
    for offer, accepted in ((offered, raised.json()), (resolution, resolved.json())):
        replay = _post(client, matter_id, offer)
        assert replay.status_code == 200, replay.text
        assert replay.json() == {**accepted, "replayed": True}
        assert replay.json()["assessment"] == "user_supplied_not_independently_verified"
        assert replay.json()["action_performed"] is False
    assert store.load(matter_id) == before
    states = {row["urgency_id"]: row["state"] for row in project(before.urgency_records)["entries"]}
    assert states == {raised.json()["urgency_id"]: "resolved", later.json()["urgency_id"]: "live"}
