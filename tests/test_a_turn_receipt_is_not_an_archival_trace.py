"""Exact served replay and safe readback, with real canonical persistence."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from nm.edge.api import application

from tests.test_a_brief_lands_exactly_once import BRIEF
from tests.test_a_withheld_turn_commits_no_conclusion import _Ungrounded
from tests.test_turn_contract import _model_config

pytestmark = pytest.mark.class_a


def _opened(client):
    response = client.post("/api/turn", json={"message": BRIEF, "turn_id": "receipt-opening"})
    assert response.status_code == 200, response.text
    assert response.json()["input_admitted"] is True
    return response.json()


def _no_model(*args, **kwargs):
    raise AssertionError("an exact committed replay reached model-backed routing")


def test_an_opening_with_a_lost_file_id_replays_the_same_owned_matter(client, monkeypatch):
    offer = {"message": BRIEF, "turn_id": "lost-opening-identity"}
    first = client.post("/api/turn", json=offer)
    assert first.status_code == 200, first.text
    monkeypatch.setattr(application().engine, "_read_route", _no_model)
    repeated = client.post("/api/turn", json=offer)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["matter_id"] == first.json()["matter_id"]
    assert repeated.json()["replayed"] is True
    assert repeated.json()["elements"] == first.json()["elements"]
    assert client.get("/api/matters").json()["row_count"] == 1


def test_exact_receipt_reconciles_before_stale_version_and_without_archive(client, monkeypatch):
    opened = _opened(client)
    offer = {"matter_id": opened["matter_id"], "expected_version": opened["matter_version"],
             "turn_id": "ack-lost", "message": "Keep the invoice date on this file."}
    first = client.post("/api/turn", json=offer)
    assert first.status_code == 200, first.text
    store = application().store
    saved = store.load(opened["matter_id"])
    assert saved.version > offer["expected_version"]
    # A later unrelated mutation does not invalidate a past operation receipt.
    store.commit(replace(saved, version=saved.version + 1), expected_version=saved.version)
    monkeypatch.setattr(application().engine, "_read_route", _no_model)
    monkeypatch.setattr(store, "transcripts_for", lambda matter_id: ())
    repeated = client.post("/api/turn", json=offer)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["committed"] == "replayed"
    assert repeated.json()["elements"] == first.json()["elements"]
    restored = client.get(f"/api/matters/{opened['matter_id']}/transcript").json()
    rows = [row for row in restored["turns"] if row["turn_id"] == offer["turn_id"]]
    assert len(rows) == 1 and rows[0]["committed"] is True
    assert rows[0]["release_state"] == "released"


def test_a_concurrent_write_after_admission_is_not_silently_adopted(client, monkeypatch):
    opened = _opened(client)
    store = application().store
    engine = application().engine
    read_route = engine._read_route
    intervened = []

    def advance_after_admission(*args, **kwargs):
        result = read_route(*args, **kwargs)
        saved = store.load(opened["matter_id"])
        moved = store.commit(replace(saved, title="Concurrent instruction remains",
                                     version=saved.version + 1), expected_version=saved.version)
        intervened.append(moved)
        return result

    monkeypatch.setattr(engine, "_read_route", advance_after_admission)
    response = client.post("/api/turn", json={
        "matter_id": opened["matter_id"], "expected_version": opened["matter_version"],
        "turn_id": "version-moved-after-admission", "message": "Keep the invoice date."})
    assert len(intervened) == 1, "the actual admitted snapshot must have been superseded"
    assert response.status_code == 409, response.text
    assert store.load(opened["matter_id"]) == intervened[0]
    assert not intervened[0].has_applied("version-moved-after-admission")


@pytest.mark.parametrize(("field", "changed"), [
    ("message", "A different instruction."), ("expected_version", 900),
    ("thread_id", "different-thread"), ("today", "2026-09-10"),
    ("jurisdiction", "different-forum"), ("work_product", "protective_triage"),
    ("parties", {"Different client": "client"}), ("release", {"scope": "different scope"}),
    ("capacity", {"state": "in_doubt", "basis": "A new unresolved assessment"}),
])
def test_reused_turn_identity_refuses_every_changed_offer_field(
    client, monkeypatch, field, changed,
):
    opened = _opened(client)
    offer = {"matter_id": opened["matter_id"], "expected_version": opened["matter_version"],
             "turn_id": "unchangeable-offer", "message": "Retain the supplied invoice date."}
    first = client.post("/api/turn", json=offer)
    assert first.status_code == 200, first.text
    before = application().store.load(opened["matter_id"])
    monkeypatch.setattr(application().engine, "_read_route", _no_model)
    changed_response = client.post("/api/turn", json={**offer, field: changed})
    assert changed_response.status_code == 409, changed_response.text
    assert "different original instructions" in changed_response.json()["detail"]["why"]
    assert application().store.load(opened["matter_id"]) == before


@pytest.mark.parametrize("commit_fails", [False, True])
def test_a_grounding_withheld_archive_is_never_released_or_marked_committed(
    client, monkeypatch, commit_fails,
):
    opened = _opened(client)
    store = application().store
    before = store.load(opened["matter_id"])
    application().engine._model = _Ungrounded(_model_config())
    if commit_fails:
        def refuse_commit(*args, **kwargs):
            raise OSError("controlled canonical commit failure")
        monkeypatch.setattr(store, "commit", refuse_commit)
    offer = {"message": BRIEF, "matter_id": opened["matter_id"],
             "turn_id": "withheld-archival-only"}
    refused = client.post("/api/turn", json=offer)
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["withheld_by"], "must actually reach a withholding gate"
    archived = [row for row in store.transcripts_for(opened["matter_id"])
                if row["turn_id"] == offer["turn_id"]]
    assert len(archived) == 1 and archived[0]["withheld_by"]
    assert any("Imaginary Act" in row["text"] for row in archived[0]["elements"])
    view = client.get(f"/api/matters/{opened['matter_id']}/transcript").json()
    row = next(row for row in view["turns"] if row["turn_id"] == offer["turn_id"])
    assert row["release_state"] == "withheld" and row["committed"] is False
    assert row["elements"] == []
    assert "File under section 999" not in str(row)
    after = store.load(opened["matter_id"])
    assert not after.has_applied(offer["turn_id"])
    assert not any(r.turn_id == offer["turn_id"] for r in after.turn_receipts)
    if commit_fails:
        assert after == before


def test_unassessed_legacy_archive_cannot_invent_release_evidence(client):
    opened = _opened(client)
    store = application().store
    store.record_turn({"turn_id": "legacy-unproven", "matter_id": opened["matter_id"],
                       "message": "Historical instruction", "at": "2026-09-10",
                       "elements": [{"kind": "action", "text": "UNRELEASED ARCHIVE"}]})
    view = client.get(f"/api/matters/{opened['matter_id']}/transcript").json()
    row = next(row for row in view["turns"] if row["turn_id"] == "legacy-unproven")
    assert row["release_state"] == "not_established" and row["committed"] is False
    assert not row["elements"] and "UNRELEASED ARCHIVE" not in str(view)
    assert view["state"] == "incomplete"


def test_a_failed_screen_commit_does_not_claim_a_saved_instruction(client, monkeypatch):
    from fastapi.testclient import TestClient
    from nm.edge.api import app

    actor = client.get("/api/session").json()["advocate"]["id"]
    attempts = []

    def refuse_commit(*args, **kwargs):
        attempts.append(args[0].id)
        raise OSError("controlled screen commit failure")

    monkeypatch.setattr(application().store, "commit", refuse_commit)
    # Explicit unassessed capacity prevents the fixture's successful-intake convenience.
    with TestClient(app, raise_server_exceptions=False, cookies=client.cookies) as raw:
        response = raw.post("/api/turn", headers={"origin": "http://testserver",
                            "x-nm-csrf": client.cookies.get("nm_csrf")},
                            json={"message": BRIEF,
                                  "turn_id": "screen-not-saved",
                                  "capacity": {"state": "not_assessed", "basis": "Not assessed"}})
    assert response.status_code >= 500
    assert len(attempts) == 1, "the intended canonical write must actually have failed"
    assert application().store.list_for(actor).matters == ()


@pytest.mark.parametrize("mutation", [
    "receipt_unknown", "answer_unknown", "admission_string", "blocked_string",
    "blocked_number", "disclosure_string", "wrong_section", "missing_message",
    "invalid_digest", "undated_receipt", "missing_applied", "duplicate_receipt",
    "duplicate_applied",
])
def test_a_malformed_sealed_receipt_never_certifies_release_or_replay(
    client, monkeypatch, mutation,
):
    from fastapi.testclient import TestClient
    from nm.edge.api import app

    opened = _opened(client)
    matter_id = opened["matter_id"]
    store = application().store
    path = store._path(matter_id)
    original_bytes = path.read_bytes()
    payload = json.loads(store._open(matter_id, original_bytes))
    before = copy.deepcopy(payload)
    rows = [row for row in payload["turn_receipts"]
            if row["turn_id"] == opened["turn_id"]]
    assert len(rows) == 1, "mutate the actual receipt released by the served turn"
    row = rows[0]
    if mutation == "receipt_unknown":
        row["unsupported_raw_trace"] = "UNRELEASED INTERNAL TRACE"
    elif mutation == "answer_unknown":
        row["answer"]["model_calls"] = {"prompt": "UNRELEASED INTERNAL TRACE"}
    elif mutation == "admission_string":
        row["input_admitted"] = "false"
    elif mutation == "blocked_string":
        row["answer"]["blocked"] = "false"
    elif mutation == "blocked_number":
        row["answer"]["blocked"] = 0
    elif mutation == "disclosure_string":
        assert row["answer"]["elements"]
        row["answer"]["elements"][0]["disclosure"] = "false"
    elif mutation == "wrong_section":
        assert row["answer"]["elements"]
        row["answer"]["elements"][0]["section"] = "unregistered_hidden_section"
    elif mutation == "missing_message":
        row.pop("message")
    elif mutation == "invalid_digest":
        row["offer_fingerprint"] = "not-an-original-offer-digest"
    elif mutation == "undated_receipt":
        row["recorded_at"] = "2026-09-12"
    elif mutation == "missing_applied":
        assert payload["turns_applied"].count(opened["turn_id"]) == 1
        payload["turns_applied"].remove(opened["turn_id"])
    elif mutation == "duplicate_receipt":
        payload["turn_receipts"].append(copy.deepcopy(row))
    elif mutation == "duplicate_applied":
        assert payload["turns_applied"].count(opened["turn_id"]) == 1
        payload["turns_applied"].append(opened["turn_id"])
    assert json.dumps(payload, sort_keys=True) != json.dumps(before, sort_keys=True), (
        "the probe must change the serialized subject, including false versus numeric zero")
    sealed = store._seal(matter_id, json.dumps(payload).encode("utf-8"))
    assert b"UNRELEASED INTERNAL TRACE" not in sealed
    path.write_bytes(sealed)
    ledger_fault = mutation in {"missing_applied", "duplicate_receipt", "duplicate_applied"}
    if ledger_fault:
        decoded = store.load(matter_id)
        assert decoded is not None, "exercise release/ledger validation after real decoding"
    else:
        with pytest.raises(ValueError):
            store.load(matter_id)
    model_read_attempts = []

    def refuse_model(*args, **kwargs):
        model_read_attempts.append("routing")
        return _no_model(*args, **kwargs)

    monkeypatch.setattr(application().engine, "_read_route", refuse_model)
    try:
        with TestClient(app, raise_server_exceptions=False, cookies=client.cookies) as raw:
            view = raw.get(f"/api/matters/{matter_id}/transcript")
            assert "UNRELEASED INTERNAL TRACE" not in view.text
            if ledger_fault:
                assert view.status_code == 200, view.text
                assert view.json()["state"] == "incomplete"
                targeted = [item for item in view.json()["turns"]
                            if item["turn_id"] == opened["turn_id"]]
                assert len(targeted) == 1
                assert targeted[0]["committed"] is False
                assert targeted[0]["release_state"] == "not_established"
                assert targeted[0]["elements"] == []
            else:
                assert view.status_code >= 500
            replay = raw.post("/api/turn", json={"message": BRIEF,
                              "turn_id": opened["turn_id"]}, headers={
                                  "origin": "http://testserver",
                                  "x-nm-csrf": client.cookies.get("nm_csrf")})
            if ledger_fault:
                assert replay.status_code == 422, replay.text
            else:
                assert replay.status_code >= 500
            assert "UNRELEASED INTERNAL TRACE" not in replay.text
            assert model_read_attempts == [], "malformed release evidence reached model work"
    finally:
        path.write_bytes(original_bytes)
    assert store.load(matter_id).turn_receipts[0].input_admitted is True


def _protective_context(client, monkeypatch):
    from tests.test_the_emergency_route_admits_only_protection import _declaration_context

    matter_id, path, clock = _declaration_context(client, monkeypatch)
    monkeypatch.setattr(application().engine, "_clock", lambda: clock[0])
    monkeypatch.setattr(application().engine, "_read_route", _no_model)
    body = {"matter_id": matter_id, "turn_id": "exact-protective-receipt",
            "message": "The private request remains unadmitted.",
            "work_product": "protective_triage"}
    return matter_id, path, clock, body


@pytest.mark.parametrize("change", ["expiry", "revocation"])
def test_a_protective_receipt_cannot_replay_lapsed_permission(client, monkeypatch, change):
    matter_id, path, clock, body = _protective_context(client, monkeypatch)
    assert client.post(path, json={"request_key": "live-protection", "basis": "Supplied danger",
                                  "hours": 1}).status_code == 200
    first = client.post("/api/turn", json=body)
    assert first.status_code == 200 and first.json()["blocked"] is False
    if change == "expiry":
        clock[0] += timedelta(hours=2)
    else:
        observed = client.get(path).json()
        revoked = client.post(path, json={"revoke": True, "expected_version": observed["version"],
                                         "governing_ref": observed["governing_ref"]})
        assert revoked.status_code == 200
    before = application().store.load(matter_id)
    refused = client.post("/api/turn", json=body)
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["committed"] == "previously_committed"
    assert detail["prior_receipt_saved"] is True and detail["release_state"] == "replay_refused"
    assert "elements" not in detail and "new request" in detail["why"]
    assert application().store.load(matter_id) == before
    assert len([r for r in before.turn_receipts if r.turn_id == body["turn_id"]]) == 1


def test_a_recorded_protective_refusal_cannot_upgrade_under_the_same_key(client, monkeypatch):
    matter_id, path, _clock, body = _protective_context(client, monkeypatch)
    first = client.post("/api/turn", json=body)
    assert first.status_code == 200 and first.json()["blocked"] is True
    assert client.post(path, json={"request_key": "later-permission",
                                  "basis": "A newly supplied emergency"}).status_code == 200
    before = application().store.load(matter_id)
    repeated = client.post("/api/turn", json=body)
    assert repeated.status_code == 200 and repeated.json()["replayed"] is True
    assert repeated.json()["blocked"] is True
    assert repeated.json()["elements"] == first.json()["elements"]
    assert application().store.load(matter_id) == before
    fresh = client.post("/api/turn", json={**body, "turn_id": "new-protective-instruction"})
    assert fresh.status_code == 200 and fresh.json()["blocked"] is False
    assert fresh.json()["replayed"] is False
    after = application().store.load(matter_id)
    assert len(after.emergency_triage) == len(before.emergency_triage) + 1
    assert after.facts == before.facts


def test_protective_replay_keeps_exact_answer_after_urgency_resolution_and_addition(
    client, monkeypatch,
):
    matter_id, path, _clock, body = _protective_context(client, monkeypatch)
    store = application().store
    assert client.post(path, json={"request_key": "unchanged-permission",
                                  "basis": "Supplied emergency"}).status_code == 200

    def record(key, basis):
        response = client.post(path, json={
            "urgency_command": "raise", "request_key": key,
            "expected_version": store.load(matter_id).version,
            "urgency": {"class": "personal_safety", "basis": basis,
                        "action": "Contact the responsible advocate", "owner": "Named advocate",
                        "due": None, "unknowns": {"due": "No verified deadline supplied"}}})
        assert response.status_code == 200, response.text
        return response.json()

    danger = record("earlier-danger", "Earlier reported danger")
    first = client.post("/api/turn", json=body)
    assert first.status_code == 200 and first.json()["blocked"] is False
    assert "Earlier reported danger" in str(first.json()["elements"])
    resolved = client.post(path, json={
        "urgency_command": "resolve", "request_key": "resolve-earlier-danger",
        "expected_version": store.load(matter_id).version,
        "urgency_id": danger["urgency_id"], "resolution_basis": "An explicit supplied resolution"})
    assert resolved.status_code == 200, resolved.text
    record("newly-reported-danger", "A distinct later reported danger")
    before = store.load(matter_id)
    repeated = client.post("/api/turn", json=body)
    assert repeated.status_code == 200 and repeated.json()["replayed"] is True
    fields = ("route", "mode", "mode_statement", "blocked", "blocked_reason", "elements")
    assert {key: repeated.json()[key] for key in fields} == {
        key: first.json()[key] for key in fields}
    assert "A distinct later reported danger" not in str(repeated.json()["elements"])
    assert store.load(matter_id) == before


@pytest.mark.parametrize(
    "mutation", ["null_entry", "null_collection", "null_ledger", "append_null"])
def test_malformed_receipt_population_never_promotes_legacy_archives(client, mutation):
    opened = _opened(client)
    matter_id = opened["matter_id"]
    store = application().store
    path = store._path(matter_id)
    original = path.read_bytes()
    payload = json.loads(store._open(matter_id, original))
    assert len(payload["turn_receipts"]) == 1
    if mutation == "null_entry":
        payload["turn_receipts"] = [None]
    elif mutation == "null_collection":
        payload["turn_receipts"] = None
    elif mutation == "null_ledger":
        payload["turns_applied"] = None
    else:
        payload["turn_receipts"].append(None)
    path.write_bytes(store._seal(matter_id, json.dumps(payload).encode("utf-8")))
    try:
        assert store.load(matter_id) is not None, "exercise actual decoded malformed population"
        response = client.get(f"/api/matters/{matter_id}/transcript")
        assert response.status_code == 200, response.text
        view = response.json()
        assert view["state"] == "incomplete" and view["release_problems"]
        targeted = [row for row in view["turns"] if row["turn_id"] == opened["turn_id"]]
        assert len(targeted) == 1
        if mutation == "append_null":
            assert targeted[0]["release_state"] == "released"
            assert targeted[0]["committed"] is True
            assert targeted[0]["elements"], "independent valid canonical evidence is retained"
        else:
            assert targeted[0]["release_state"] == "not_established"
            assert targeted[0]["committed"] is False and targeted[0]["elements"] == []
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize("mutation", [
    "valid", "extra_top_level_trace", "extra_element_trace", "string_disclosure",
    "unknown_section", "null_elements", "numeric_blocked",
])
def test_only_a_valid_legacy_answer_can_be_projected_from_a_sealed_archive(client, mutation):
    opened = _opened(client)
    matter_id = opened["matter_id"]
    store = application().store
    matter_path = store._path(matter_id)
    archive_path = store._transcripts / f"{matter_id}__{opened['turn_id']}.nm"
    original_matter, original_archive = matter_path.read_bytes(), archive_path.read_bytes()
    matter = json.loads(store._open(matter_id, original_matter))
    archive = json.loads(store._open(matter_id, original_archive))
    archive_before = json.dumps(archive, sort_keys=True)
    assert archive["withheld_by"] == [] and opened["turn_id"] in matter["turns_applied"]
    assert archive["elements"] and matter["turn_receipts"]
    # Real historic schema: applied turn plus its ungated archive, no newer receipt field.
    matter.pop("turn_receipts")
    if mutation == "extra_top_level_trace":
        archive["model_calls"] = {"raw": "UNRELEASED LEGACY TRACE"}
    elif mutation == "extra_element_trace":
        archive["elements"][0]["raw_trace"] = "UNRELEASED LEGACY TRACE"
    elif mutation == "string_disclosure":
        archive["elements"][0]["disclosure"] = "false"
    elif mutation == "unknown_section":
        archive["elements"][0]["section"] = "unregistered_hidden_section"
    elif mutation == "null_elements":
        archive["elements"] = None
    elif mutation == "numeric_blocked":
        archive["blocked"] = 0
    if mutation != "valid":
        assert json.dumps(archive, sort_keys=True) != archive_before
    matter_path.write_bytes(store._seal(matter_id, json.dumps(matter).encode("utf-8")))
    archive_path.write_bytes(store._seal(matter_id, json.dumps(archive).encode("utf-8")))
    try:
        response = client.get(f"/api/matters/{matter_id}/transcript")
        assert response.status_code == 200, response.text
        view = response.json()
        assert "UNRELEASED LEGACY TRACE" not in str(view)
        targeted = [row for row in view["turns"] if row["turn_id"] == opened["turn_id"]]
        assert len(targeted) == 1
        if mutation in {"valid", "extra_top_level_trace"}:
            assert view["state"] == "ok"
            assert targeted[0]["release_state"] == "legacy_released"
            assert targeted[0]["committed"] is True
            assert targeted[0]["exact_replay_available"] is False
            assert [row["text"] for row in targeted[0]["elements"]] == [
                row["text"] for row in opened["elements"]]
            assert client.post("/api/turn", json={"message": BRIEF,
                               "turn_id": opened["turn_id"]}).status_code == 422
        else:
            assert view["state"] == "incomplete"
            assert targeted[0]["release_state"] == "not_established"
            assert targeted[0]["committed"] is False and targeted[0]["elements"] == []
    finally:
        matter_path.write_bytes(original_matter)
        archive_path.write_bytes(original_archive)
