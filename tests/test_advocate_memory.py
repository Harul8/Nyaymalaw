"""LB-151's bounded vocabulary on real authenticated account routes, not model learning.

These tests install the injected route owner on the existing local ASGI app.
The root separately owns loading PreferenceContext into its conversation prefix.
No live model, server, account, matter store or external processor is used.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from nm.arrive.advocate_contracts import utcnow
from nm.arrive.directory_port import DirectoryPort, MemoryStale, MemoryUnavailable
from nm.Archives.legal_brain.understand.advocate_memory import (
    decode_memory,
    delete_memory,
    preference_context,
    save_memory,
)
from nm.Archives.legal_brain.understand.advocate_memory_contracts import (
    CHOICES,
    AdvocateMemory,
    PreferenceKey,
    Preferences,
)
from nm.Archives.legal_brain.understand.advocate_memory_routes_api import install_advocate_memory_routes

pytestmark = pytest.mark.class_a
PATH = "/api/account/advocate-memory"
SETTINGS = {"advice_length": "short", "authorities_position": "end",
            "court_ids": ["hc_telangana"],
            "standing_instructions": ["explain_abbreviations"]}


@pytest.fixture
def memory_client(client):
    from nm.app.api import application, csrf_protected, signed_in

    original = list(client.app.router.routes)
    install_advocate_memory_routes(client.app, authenticated=signed_in,
        csrf_protected=csrf_protected, directory=lambda: application().directory, clock=utcnow)
    try:
        yield client
    finally:
        client.app.router.routes[:] = original


def put(client, settings=SETTINGS, version=0, approved=True, **extra):
    return client.put(PATH, json={"settings": settings, "expected_version": version,
                                 "approved": approved, **extra})


def remove(client, version, key=None, approved=True):
    return client.request("DELETE", PATH + (f"/{key}" if key else ""),
                          json={"expected_version": version, "approved": approved})


def test_authenticated_owner_approves_views_edits_and_deletes_each_entry(memory_client, tmp_path):
    c = memory_client
    before = c.directory._read("adv_demo")
    empty = c.get(PATH)
    assert empty.status_code == 200 and empty.json()["version"] == 0
    assert empty.json()["settings"] == {}
    saved = put(c)
    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"] == SETTINGS and saved.json()["version"] == 1
    record = c.directory.advocate_memory("adv_demo")
    assert record.approved_by == "adv_demo" and record.approved_at.utcoffset() is not None
    assert c.get(PATH).json()["settings"] == SETTINGS
    assert {key: value for key, value in c.directory._read("adv_demo").items()
            if key != "advocate_memory"} == before
    account_bytes = (tmp_path / "advocates" / "adv_demo.nm").read_bytes()
    assert b'"advice_length"' not in account_bytes and b'"settings"' not in account_bytes
    encrypted = json.loads(account_bytes)["advocate_memory"]
    assert type(encrypted) is str and c.directory._cipher.decrypt(encrypted.encode())
    from nm.arrive.store_directory import FileDirectory
    from tests.test_turn_contract import KEY

    fresh = FileDirectory(tmp_path, key=KEY)
    assert fresh.advocate_memory("adv_demo") == record
    edited = put(c, {**SETTINGS, "advice_length": "detailed"}, 1)
    assert edited.status_code == 200 and edited.json()["version"] == 2
    for key in tuple(edited.json()["settings"]):
        current = c.get(PATH).json()
        deleted = remove(c, current["version"], key)
        assert deleted.status_code == 200, deleted.text
        assert key not in deleted.json()["settings"]
    cleared = c.get(PATH).json()
    assert cleared["settings"] == {} and cleared["version"] == 6
    decoded = c.directory._cipher.decrypt(c.directory._read("adv_demo")["advocate_memory"].encode())
    assert json.loads(decoded)["settings"] == {}  # no discarded-values history
    stale = put(c, SETTINGS, 0)
    assert stale.status_code == 409 and c.get(PATH).json() == cleared


def test_every_supported_choice_is_closed_typed_and_round_trips():
    for key, choices in CHOICES.items():
        for value in choices:
            raw = {key.value: [value] if key in (
                PreferenceKey.COURT_IDS, PreferenceKey.STANDING_INSTRUCTIONS) else value}
            assert Preferences.from_values(raw).as_dict() == raw
    assert Preferences.from_values({"court_ids": ["hc_telangana", "supreme_court"]}) == (
        Preferences.from_values({"court_ids": ["supreme_court", "hc_telangana"]}))


@pytest.mark.parametrize("settings", [
    {"client_name": "A Rao"}, {"standing_instructions": "Our client A Rao owns the land."},
    {"advice_length": "A Rao"}, {"court_ids": ["A Rao v B Reddy"]},
    {"court_ids": ["District Court for the client's claim"]},
    {"legal_proposition": "A benefit requires notice."}, {"document": "agreement contents"},
    {"matter_id": "mat_other"}, {"advice_form": True},
    {"standing_instructions": ["show_action_owners", "the claimant wins"]},
    {"court_ids": ["hc_telangana", "hc_telangana"]},
    {"standing_instructions": [False]}, {"draft_date_format": {"fact": "client account"}},
])
def test_client_names_case_material_and_unbounded_instructions_are_refused(memory_client, settings):
    c = memory_client
    before = c.get(PATH).json()
    result = put(c, settings)
    assert result.status_code == 422, result.text
    assert "A Rao" not in result.text and "agreement contents" not in result.text
    assert c.get(PATH).json() == before and c.directory.advocate_memory("adv_demo") is None


@pytest.mark.parametrize("approved", [False, 1, "true", None])
def test_approval_cannot_be_implicit_or_coerced(memory_client, approved):
    c = memory_client
    assert put(c, approved=approved).status_code == 422
    assert c.directory.advocate_memory("adv_demo") is None
    assert put(c).status_code == 200
    assert remove(c, 1, approved=approved).status_code == 422
    assert c.get(PATH).json()["settings"] == SETTINGS


def test_foreign_account_has_no_memory_route_or_approval_selector(memory_client):
    c = memory_client
    assert put(c).status_code == 200
    stranger = c.sign_in("adv_foreign", fresh=True)
    assert stranger.get(PATH).json()["settings"] == {}
    assert stranger.get(PATH + "?account_id=adv_demo").json()["settings"] == {}
    assert put(stranger, account_id="adv_demo").status_code == 422
    assert put(stranger, {"advice_length": "detailed"}).status_code == 200
    assert c.get(PATH).json()["settings"] == SETTINGS
    assert remove(stranger, 1).status_code == 200
    assert c.get(PATH).json()["settings"] == SETTINGS


def test_real_login_and_csrf_are_required_for_every_memory_write(memory_client):
    anonymous = TestClient(memory_client.app)
    assert anonymous.get(PATH).status_code == 401
    assert put(anonymous).status_code in (401, 403)
    wrong_origin = memory_client.put(PATH, json={"approved": True, "expected_version": 0,
        "settings": SETTINGS}, headers={"origin": "https://foreign.invalid"})
    assert wrong_origin.status_code == 403
    assert memory_client.directory.advocate_memory("adv_demo") is None
    assert put(memory_client).status_code == 200
    assert memory_client.post("/api/logout").status_code == 200
    assert memory_client.get(PATH).status_code == 401
    assert remove(memory_client, 1).status_code in (401, 403)


def test_two_workers_cannot_overwrite_current_preferences_or_bypass_account_lock(memory_client, tmp_path):
    from nm.arrive.store_directory import FileDirectory
    from tests.test_turn_contract import KEY

    c = memory_client
    assert put(c).status_code == 200
    second = FileDirectory(tmp_path, key=KEY)
    with pytest.raises(MemoryStale):
        save_memory(second, "adv_demo", {"advice_length": "detailed"}, approved=True,
                    expected_version=0, now=utcnow())
    claim = second._claim_account("adv_demo")
    assert claim is not None
    try:
        assert put(c, {"advice_length": "detailed"}, 1).status_code == 409
        assert remove(c, 1).status_code == 409
    finally:
        claim.release()
    assert c.get(PATH).json()["settings"] == SETTINGS
    assert remove(c, 1).status_code == 200


@pytest.mark.parametrize("damage", ["ciphertext", "unsealed", "foreign", "boolean_schema",
                                  "boolean_version", "extra", "no_approval", "client_text",
                                  "duplicate_json", "oversize"])
def test_damaged_memory_uses_visible_defaults_and_cannot_be_silently_repaired(memory_client, damage):
    from nm.app.api import application

    c = memory_client
    assert put(c).status_code == 200
    doc = c.directory._read("adv_demo")
    raw = c.directory.advocate_memory("adv_demo").as_dict()
    if damage == "ciphertext":
        doc["advocate_memory"] = "not a sealed record"
    elif damage == "unsealed":
        doc["advocate_memory"] = json.dumps(raw)
    else:
        if damage == "foreign":
            raw["account_id"] = raw["approved_by"] = "adv_foreign"
        elif damage == "boolean_schema":
            raw["schema"] = True
        elif damage == "boolean_version":
            raw["version"] = True
        elif damage == "extra":
            raw["override"] = True
        elif damage == "no_approval":
            raw["approved"] = 1
        elif damage == "client_text":
            raw["settings"] = {"client_name": "A Rao"}
        encoded = json.dumps(raw).encode()
        if damage == "duplicate_json":
            encoded = encoded[:-1] + b',"schema":1}'
        elif damage == "oversize":
            encoded = b" " * 5000 + encoded
        doc["advocate_memory"] = c.directory._cipher.encrypt(encoded).decode()
    c.directory._replace_advocate(c.directory._advocate_path("adv_demo"), doc)
    damaged = c.directory._read("adv_demo")["advocate_memory"]
    assert c.get(PATH).status_code == 503
    context = preference_context(application().directory, "adv_demo")
    assert context.version is None and context.preferences.as_dict() == {} and context.notice
    assert json.loads(context.prefix_input)["settings"] == {}
    assert "A Rao" not in context.prefix_input
    assert put(c, SETTINGS, 1).status_code == 503
    assert remove(c, 1).status_code == 503
    assert c.directory._read("adv_demo")["advocate_memory"] == damaged
    # Unreadable optional memory cannot change authentication or ordinary file access.
    assert c.get("/api/matters").status_code == 200


def test_preference_prefix_is_account_scoped_stable_across_matters_and_not_a_fact(memory_client):
    from nm.app.api import application

    c = memory_client
    assert put(c).status_code == 200
    context = preference_context(application().directory, "adv_demo")
    assert context.account_id == "adv_demo"
    data = json.loads(context.prefix_input)
    assert data["settings"]["advice_length"] == "short"
    assert data["settings"]["authorities_position"] == "end"
    assert data["scope"] == "presentation_and_practice_only_not_facts_law_forum_or_authority"
    assert not {"facts", "documents", "legal_propositions", "matter_id"} & set(data)
    from nm.work_the_file.matter_contracts import Matter

    one = Matter.create("adv_demo", "First isolated matter")
    two = Matter.create("adv_demo", "Second isolated matter")
    assert one.id != two.id and one.facts == two.facts == ()
    assert preference_context(application().directory, one.advocate_id).prefix_input == context.prefix_input
    assert preference_context(application().directory, two.advocate_id).prefix_input == context.prefix_input
    assert remove(c, 1).status_code == 200
    after = preference_context(application().directory, "adv_demo")
    assert after.version == 2 and after.preferences.as_dict() == {}
    assert "short" not in json.loads(after.prefix_input)["settings"].values()


def test_declared_directory_methods_use_the_existing_policed_sink(memory_client, monkeypatch):
    from nm.app.api import application
    from nm.shared.policed_port_adapter import port_methods

    port = application().directory
    assert {"advocate_memory", "record_advocate_memory"} <= port_methods(DirectoryPort)
    assert {"advocate_memory", "record_advocate_memory"} <= port._gated
    audit = []
    prior = port.gate.audit
    def record(line):
        audit.append(line)
        if prior is not None:
            prior(line)
    monkeypatch.setattr(port.gate, "audit", record)
    assert put(memory_client).status_code == 200
    assert memory_client.get(PATH).status_code == 200
    assert remove(memory_client, 1).status_code == 200
    assert len(audit) >= 6
    assert all("storage" in line and "restricted" in line for line in audit)
    assert not any("advice_length" in line or "hc_telangana" in line for line in audit)


def test_exact_record_decoding_and_typed_constructor_reject_forged_approval():
    record = AdvocateMemory("adv_demo", 1, Preferences.from_values(SETTINGS), "adv_demo", utcnow())
    assert decode_memory(json.dumps(record.as_dict()).encode(), "adv_demo") == record
    with pytest.raises(ValueError):
        decode_memory(json.dumps(record.as_dict()).encode(), "adv_foreign")
    with pytest.raises(ValueError):
        replace(record, approved_by="adv_foreign")
    with pytest.raises(ValueError):
        replace(record, version=True)
    with pytest.raises(ValueError):
        replace(record, approved_at=utcnow().replace(tzinfo=None))
