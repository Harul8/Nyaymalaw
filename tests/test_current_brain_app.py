"""Shipped current-brain wiring with real sealed storage and authenticated HTTP.

Synthetic model outputs prove handoff/release/persistence mechanics, not model
semantic accuracy. No provider adapter or live model dispatch is used here.
"""
from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.store_directory import FileDirectory
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from nm.shared.store_file_store import FileMatterStore

ROOT = Path(__file__).resolve().parents[1]
KEY = "synthetic-current-brain-store-key"
PASSWORD = "Synthetic-Brain-Password-42!"
ORIGIN = "http://testserver"
OPERATIONS = ["label_message", "extract_disputes_objectives", "review_prepared_response"]
MIXED_MESSAGE = "The supplier refuses to return my deposit. I want the deposit returned."


def greeting_outputs():
    return [{"label": "greeting"},
            {"disputes": [], "objectives": []},
            {"greeting": True, "unit_reviews": [], "omissions": []}]


def mixed_outputs(message):
    assert message == MIXED_MESSAGE, "This fixture's two selectors belong to its two supplied sentences"
    return [{"label": "mixed"}, {
        "disputes": [{"description": "The advocate reports the supplier refusing to return their deposit.",
                      "selections": [{"passage_id": "current:p1", "purpose": "support"}],
                      "uncertainty": None}],
        "objectives": [{"description": "The advocate wants the deposit returned.",
                        "selections": [{"passage_id": "current:p2", "purpose": "support"}],
                        "uncertainty": None}]},
        {"greeting": False, "unit_reviews": [
            {"unit_id": identity, "verdict": "supported", "reason": "none"}
            for identity in ("dispute:1", "objective:1")], "omissions": []}]


class WiredModel:
    provider = "scripted"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def resolved_model(self, tier):
        return "scripted-1"

    def context_budget(self, tier):
        return 100000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        assert self.outputs, "The service made an unexpected additional model call"
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return ModelResult(text=None, data=deepcopy(value), tier=tier,
            provider=self.provider, model="scripted-1", usage=Usage(10, 5, 0),
            latency_ms=1, completion=Completion.COMPLETE)


class Harness:
    def __init__(self, path, model):
        from nm.app.composition import Application
        from nm.app.main import create_app
        self.path, self.model = path, model
        self.store = FileMatterStore(path, key=KEY)
        self.directory = FileDirectory(path, key=KEY)
        for identity in ("adv_wiring", "adv_other"):
            self.directory.enrol(Enrolment(AdvocateIdentity(identity, identity), enrol(PASSWORD)))
        self.application = Application(root=ROOT, model=model, store=self.store,
            directory=self.directory, audit_root=path / "audit", environment={
                "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(path),
                "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1",
                "NM_EMBED_MODEL": "text-embedding-3-large"})
        self.asgi = create_app(self.application)
        self.client = TestClient(self.asgi)
        self.login(self.client)

    def login(self, client, identity="adv_wiring"):
        result = client.post("/api/login", headers={"origin": ORIGIN},
                             json={"advocate_id": identity, "password": PASSWORD})
        assert result.status_code == 200, result.text
        client.headers.update({"origin": ORIGIN, "x-nm-csrf": client.cookies.get("nm_csrf")})
        return result

    def post(self, message="Hello.", turn_id="turn_first", **values):
        return self.client.post("/api/turn",
                                json={"message": message, "turn_id": turn_id, **values})

    def held(self, chat_id):
        from nm.brain.turn import chat_matter_id
        return self.store.load(chat_matter_id("adv_wiring", chat_id))


@pytest.fixture
def harness(tmp_path):
    models = []
    def build(*outputs):
        result = Harness(tmp_path / str(len(models)), WiredModel(*outputs))
        models.append(result)
        return result
    yield build
    for result in models:
        result.client.close()


def assert_ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def test_application_starts_serves_existing_browser_and_account_session(harness):
    app = harness()
    root = app.client.get("/")
    assert root.status_code == 200 and "Nyaymalaw" in root.text
    assets = app.application.browser_asset_paths()
    javascript = next(name for name in assets if name.endswith(".js"))
    assert app.client.get("/static/" + javascript).status_code == 200
    assert app.client.get("/static/composition.py").status_code == 404
    assert app.client.get("/static/../../.env").status_code == 404
    assert assert_ok(app.client.get("/api/session"))["advocate"]["id"] == "adv_wiring"
    assert assert_ok(app.client.get("/api/health"))["brain"]["stages"] == [
        "message_labelling", "disputes_objectives", "response_review"]
    assert app.model.calls == []


def test_first_followup_full_context_saved_reopened_and_replay_without_calls(harness):
    app = harness(*greeting_outputs(), *greeting_outputs())
    first_message = "  Good evening.\n "
    first = assert_ok(app.post(first_message))
    chat_id = first["chat_id"]
    assert first["matter_id"] is None and first["input_admitted"] is True
    assert first["committed"] == "committed" and first["matter_version"] == 1
    assert first["metrics"]["llm_calls"] == 3
    assert "earlier_conversation" not in json.loads(app.model.calls[0][0].user)
    follow_message = "Thank you."
    second = assert_ok(app.post(follow_message, "turn_second", chat_id=chat_id, expected_version=1))
    assert second["matter_version"] == 2 and second["metrics"]["llm_calls"] == 3
    assert [call[0].operation for call in app.model.calls] == OPERATIONS * 2
    original_history = json.loads(app.model.calls[3][0].user)["earlier_conversation"]
    assert [(row["role"], row["text"]) for row in original_history] == [
        ("advocate", first_message), ("nm", "Hello. How can I help?")]
    prepared_history = json.loads(app.model.calls[4][0].user)["earlier_conversation"]
    assert [{**{key: value for key, value in row["message"].items() if key != "passages"},
             "text": "".join(passage["text"] for passage in row["message"]["passages"])}
            for row in prepared_history] == original_history
    held = app.held(chat_id)
    assert [row["message"] for row in held.brain_chat] == [first_message, follow_message]
    assert [row["label"]["message_position"] for row in held.brain_chat] == ["first", "follow_up"]
    assert FileMatterStore(app.path, key=KEY).load(held.id) == held
    reopened = assert_ok(app.client.get("/api/chats/" + chat_id))
    assert reopened["turn_count"] == 2
    assert [row["message"] for row in reopened["turns"]] == [first_message, follow_message]
    assert [row["elements"] for row in reopened["turns"]] == [first["elements"], second["elements"]]
    for row in reopened["turns"]:
        assert not ({"preparation", "release", "request", "response_digest"} & set(row))
    listed = assert_ok(app.client.get("/api/work"))
    assert listed["chats"][0]["chat_id"] == chat_id and listed["matters"] == []
    app.application._model_for = lambda *args, **kwargs: pytest.fail("Replay acquired a model")
    replay = assert_ok(app.post(first_message))
    assert replay == {**first, "replayed": True}
    assert len(app.model.calls) == 6


def test_disputes_and_objectives_remain_private_without_losing_saved_proposals(harness):
    message = MIXED_MESSAGE
    app = harness(*mixed_outputs(message))
    response = assert_ok(app.post(message))
    text = "\n".join(row["text"] for row in response["elements"])
    assert text == "Message received."
    assert "UNREVIEWED" not in text and "I filed" not in text
    assert "does not carry out" not in text
    held = app.held(response["chat_id"])
    proposed = held.brain_chat[0]["preparation"]["proposal"]
    assert set(proposed) == {"disputes", "objectives"}
    selected_words = {"disputes": "The supplier refuses to return my deposit.",
                      "objectives": " I want the deposit returned."}
    for kind, collection in proposed.items():
        assert collection[0]["state"] == "proposed"
        assert collection[0]["source_ids"] == ["current"]
        quote = selected_words[kind]
        start = message.index(quote)
        assert collection[0]["passages"] == [{"source_id": "current", "quote": quote,
            "passage_id": "current:p1" if kind == "disputes" else "current:p2",
            "purpose": "support", "start": start, "end": start + len(quote)}]
    assert held.brain_chat[0]["preparation"]["contract"] == "disputes_objectives_v2"
    assert held.brain_chat[0]["contract"] == "current_brain_turn_v3"
    assert held.facts == () and held.threads == ()
    assert response["board_changes"] == [] and response["material"] == []


def test_internal_material_stays_private_through_followup_reopen_and_idempotent_replay(harness):
    message = MIXED_MESSAGE
    app = harness(*mixed_outputs(message), *greeting_outputs())
    first = assert_ok(app.post(message))
    chat_id = first["chat_id"]
    snapshot = app.held(chat_id)
    assert snapshot.brain_chat[0]["response"]["elements"] == first["elements"]
    assert snapshot.brain_chat[0]["release"]["renderer_version"] == "disputes_objectives_release_v2"
    assert snapshot.brain_chat[0]["preparation"]["proposal"]["disputes"]
    assert snapshot.brain_chat[0]["preparation"]["proposal"]["objectives"]
    second = assert_ok(app.post("Thank you.", "turn_second", chat_id=chat_id, expected_version=1))
    history = json.loads(app.model.calls[3][0].user)["earlier_conversation"]
    assert [(row["role"], row["text"]) for row in history] == [
        ("advocate", message), ("nm", "Message received.")]
    assert app.held(chat_id).brain_chat[0] == snapshot.brain_chat[0]
    reopened = assert_ok(app.client.get("/api/chats/" + chat_id))
    assert [row["elements"] for row in reopened["turns"]] == [first["elements"], second["elements"]]
    for row in reopened["turns"]:
        assert not ({"preparation", "release", "proof", "units", "issues"} & set(row))
    replayed = assert_ok(app.post(message))
    assert replayed == {**first, "replayed": True}
    assert len(app.model.calls) == 6


@pytest.mark.parametrize("version", ["initial_brain_release_v1", "initial_brain_release_v2"])
def test_legacy_preparation_read_replay_and_followup_preserve_the_original_transcript(harness, version):
    from nm.brain.turn import _digest
    from tests.test_new_brain_release import historical_v1_release, prepared as legacy_prepared
    message = "I received a draft."
    outputs = [{"label": "information"}, {"disputes": [], "objectives": []},
               {"greeting": False, "unit_reviews": [], "omissions": []}]
    app = harness(*outputs, *greeting_outputs())
    first = assert_ok(app.post(message))
    held = app.held(first["chat_id"])
    rows = deepcopy(held.brain_chat)
    historical = historical_v1_release(message, information=True)
    historical["renderer_version"] = version
    if version == "initial_brain_release_v2":
        historical["elements"][0]["text"] = "Message received."
    rows[0]["contract"] = "current_brain_turn_v1"
    rows[0]["preparation"] = legacy_prepared(message, material=True)
    rows[0]["release"] = historical
    rows[0]["response"]["elements"] = deepcopy(historical["elements"])
    rows[0]["response"]["metrics"]["calls"][1]["operation"] = "prepare_response"
    rows[0]["response_digest"] = _digest(rows[0]["response"])
    app.store.commit(replace(held, brain_chat=rows), expected_version=held.version)
    persisted = app.held(first["chat_id"])
    reopened = assert_ok(app.client.get("/api/chats/" + first["chat_id"]))
    assert reopened["turns"][0]["elements"] == historical["elements"]
    replayed = assert_ok(app.post(message))
    assert replayed["elements"] == historical["elements"] and replayed["replayed"] is True
    assert len(app.model.calls) == 3 and app.held(first["chat_id"]) == persisted
    assert_ok(app.post("Thank you.", "turn_second", chat_id=first["chat_id"], expected_version=1))
    history = json.loads(app.model.calls[3][0].user)["earlier_conversation"]
    assert [(row["role"], row["text"]) for row in history] == [
        ("advocate", message), ("nm", historical["elements"][0]["text"])]
    assert app.held(first["chat_id"]).brain_chat[0] == persisted.brain_chat[0]


def test_legacy_focused_quotes_reopen_replay_and_followup_without_upgrading_saved_records(harness):
    from nm.brain.disputes_objectives import _prepare
    from nm.brain.turn import _digest

    app = harness(*mixed_outputs(MIXED_MESSAGE), *greeting_outputs())
    first = assert_ok(app.post(MIXED_MESSAGE))
    held = app.held(first["chat_id"])
    rows = deepcopy(held.brain_chat)
    original_sources = [{"id": "current", "message": {"role": "advocate", "text": MIXED_MESSAGE}}]
    # The historical writer copied original quotations; it did not select
    # passage IDs. Build that old projection from its actual raw contract.
    historical = _prepare({
        "disputes": [{"description": "The advocate reports the supplier refusing to return their deposit.",
            "passages": [{"source_id": "current", "quote": "The supplier refuses to return my deposit.",
                          "purpose": "support"}], "uncertainty": None}],
        "objectives": [{"description": "The advocate wants the deposit returned.",
            "passages": [{"source_id": "current", "quote": "I want the deposit returned.",
                          "purpose": "support"}], "uncertainty": None}],
    }, original_sources)
    assert historical["contract"] == "disputes_objectives_v1"
    assert historical["issues"] == []
    assert all("passage_id" not in passage for collection in historical["proposal"].values()
               for item in collection for passage in item["passages"])
    rows[0]["contract"] = "current_brain_turn_v2"
    rows[0]["preparation"] = historical
    rows[0]["release"] = {
        "renderer_version": "disputes_objectives_release_v1", "label": "mixed",
        "sources": deepcopy(original_sources), "issues": [],
        "units": {item["id"]: {"kind": kind, "proposal": deepcopy(item)}
                  for kind, collection in historical["proposal"].items() for item in collection},
        "proof": {"greeting": False, "unit_reviews": [
            {"unit_id": identity, "verdict": "supported", "reason": "none"}
            for identity in ("dispute:1", "objective:1")], "omissions": []},
        "elements": deepcopy(first["elements"]), "service_status": None, "state": "ready",
    }
    rows[0]["response_digest"] = _digest(rows[0]["response"])
    app.store.commit(replace(held, brain_chat=rows), expected_version=held.version)
    persisted = app.held(first["chat_id"])
    reopened = assert_ok(app.client.get("/api/chats/" + first["chat_id"]))
    assert reopened["turns"][0]["elements"] == first["elements"]
    replay = assert_ok(app.post(MIXED_MESSAGE))
    assert replay == {**first, "replayed": True}
    assert len(app.model.calls) == 3 and app.held(first["chat_id"]) == persisted
    assert_ok(app.post("Thank you.", "turn_second", chat_id=first["chat_id"], expected_version=1))
    history = json.loads(app.model.calls[3][0].user)["earlier_conversation"]
    assert [(row["role"], row["text"]) for row in history] == [
        ("advocate", MIXED_MESSAGE), ("nm", "Message received.")]
    final_rows = app.held(first["chat_id"]).brain_chat
    assert final_rows[0] == persisted.brain_chat[0]
    assert final_rows[1]["contract"] == "current_brain_turn_v3"
    assert final_rows[1]["preparation"]["contract"] == "disputes_objectives_v2"


@pytest.mark.parametrize("label,message", [
    ("information", "My client moved office last month."),
    ("action", "Summarise our conversation."),
])
def test_reviewed_absence_is_valid_without_manufacturing_disputes_or_objectives(harness, label, message):
    app = harness({"label": label}, {"disputes": [], "objectives": []},
                  {"greeting": False, "unit_reviews": [], "omissions": []})
    response = assert_ok(app.post(message))
    assert [row["text"] for row in response["elements"]] == ["Message received."]
    row = app.held(response["chat_id"]).brain_chat[0]
    assert row["preparation"]["proposal"] == {"disputes": [], "objectives": []}
    assert row["release"]["state"] == "ready"
    assert [call[0].operation for call in app.model.calls] == OPERATIONS


@pytest.mark.parametrize("label", ["greeting", "action"])
def test_advisory_label_does_not_filter_dispute_or_objective_extraction(harness, label):
    outputs = mixed_outputs(MIXED_MESSAGE)
    outputs[0]["label"] = label
    app = harness(*outputs)
    response = assert_ok(app.post(MIXED_MESSAGE))
    payload = json.loads(app.model.calls[1][0].user)
    assert "".join(passage["text"] for passage in
                   payload["current_message"]["message"]["passages"]) == MIXED_MESSAGE
    assert "proposed_label" not in payload
    proposal = app.held(response["chat_id"]).brain_chat[0]["preparation"]["proposal"]
    assert proposal["disputes"] and proposal["objectives"]
    assert [call[0].operation for call in app.model.calls] == OPERATIONS


def test_empty_extraction_with_reported_omission_is_not_admitted_as_reviewed_absence(harness):
    app = harness({"label": "information"}, {"disputes": [], "objectives": []},
                  {"greeting": False, "unit_reviews": [],
                   "omissions": [{"source_id": "current", "kind": "disputes"}]})
    response = app.post("The supplier refuses to return my deposit.")
    assert response.status_code == 503
    assert response.json()["detail"]["committed"] == "not_committed"
    assert not app.store.list_for("adv_wiring").matters
    assert len(app.model.calls) == 3


def test_missing_login_csrf_and_foreign_owner_do_not_dispatch_models(harness):
    app = harness(*greeting_outputs())
    with TestClient(app.asgi) as anonymous:
        assert anonymous.post("/api/turn", json={"message": "Hello."}).status_code == 401
    assert app.client.post("/api/turn", headers={"x-nm-csrf": "wrong"},
                           json={"message": "Hello."}).status_code == 403
    first = assert_ok(app.post())
    calls = len(app.model.calls)
    with TestClient(app.asgi) as other:
        app.login(other, "adv_other")
        assert other.get("/api/chats/" + first["chat_id"]).status_code == 404
        assert other.get("/api/matters/" + app.held(first["chat_id"]).id).status_code == 404
        assert assert_ok(other.get("/api/work"))["chats"] == []
    assert len(app.model.calls) == calls


def test_stale_version_and_reused_request_id_do_not_run_again(harness):
    app = harness(*greeting_outputs())
    first = assert_ok(app.post())
    stale = app.post("Follow up", "turn_next", chat_id=first["chat_id"], expected_version=0)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_version"
    changed = app.post("Different original words")
    assert changed.status_code == 409 and changed.json()["detail"]["code"] == "request_conflict"
    assert len(app.model.calls) == 3 and app.held(first["chat_id"]).version == 1


@pytest.mark.parametrize("damage", ["release_version", "source_words", "missing_last_turn"])
def test_unreadable_or_incomplete_history_cannot_be_used_as_a_new_context(harness, damage):
    app = harness(*greeting_outputs(), *greeting_outputs())
    first = assert_ok(app.post())
    second = assert_ok(app.post("Thanks.", "turn_second",
                                chat_id=first["chat_id"], expected_version=1))
    held = app.held(first["chat_id"])
    rows = deepcopy(held.brain_chat)
    if damage == "release_version":
        rows[0]["release"]["renderer_version"] = "future_unknown_version"
    elif damage == "source_words":
        rows[0]["release"]["sources"][0]["message"]["text"] = "Changed source words."
    else:
        rows = rows[:-1]
    app.store.commit(replace(held, brain_chat=rows), expected_version=held.version)
    assert app.client.get("/api/chats/" + first["chat_id"]).status_code == 409
    failed = app.post("Another follow up", "turn_third", chat_id=first["chat_id"],
                      expected_version=second["matter_version"])
    assert failed.status_code == 409
    assert len(app.model.calls) == 6


def test_unknown_historical_matter_stays_unchanged_and_is_not_replayed(harness):
    from nm.work_the_file.matter_contracts import Matter
    app = harness()
    historical = Matter(id="mat_historical", advocate_id="adv_wiring",
                        title="Earlier matter", version=1)
    app.store.commit(historical, expected_version=0)
    listed = assert_ok(app.client.get("/api/work"))
    assert listed["matters"][0]["state"] == "historical"
    assert app.client.get("/api/matters/mat_historical").status_code == 409
    assert app.post("Change this old matter", matter_id="mat_historical").status_code == 409
    assert app.store.load(historical.id) == historical and app.model.calls == []


def test_startup_and_served_login_static_paths_never_import_archived_engine():
    script = r'''
import importlib.abc
import sys
import tempfile
from pathlib import Path
class NoArchive(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "nm.Archives" or fullname.startswith("nm.Archives."):
            raise AssertionError("Archived engine import: " + fullname)
sys.meta_path.insert(0, NoArchive())
from tests.test_current_brain_app import Harness, WiredModel, greeting_outputs
with tempfile.TemporaryDirectory() as folder:
    harness = Harness(Path(folder), WiredModel(*greeting_outputs()))
    assert harness.client.get("/").status_code == 200
    assert harness.client.get("/api/session").status_code == 200
    response = harness.post()
    assert response.status_code == 200, response.text
    assert len(harness.model.calls) == 3
    assert harness.client.get("/api/chats/" + response.json()["chat_id"]).status_code == 200
    harness.client.close()
assert not any(name == "nm.Archives" or name.startswith("nm.Archives.") for name in sys.modules)
'''
    completed = subprocess.run([sys.executable, "-c", script], cwd=ROOT, text=True,
                               capture_output=True, timeout=45)
    assert completed.returncode == 0, completed.stderr


def test_lost_save_acknowledgement_uses_the_owned_receipt_without_model_rerun(harness):
    app = harness(*greeting_outputs())
    commit = app.store.commit
    calls = []
    def saved_then_lost(matter, *, expected_version):
        calls.append((matter.id, expected_version))
        commit(matter, expected_version=expected_version)
        raise OSError("Synthetic lost acknowledgement after durable replace")
    app.store.commit = saved_then_lost
    response = assert_ok(app.post())
    assert response["replayed"] is True and response["committed"] == "committed"
    assert len(app.model.calls) == 3 and len(calls) == 1
    assert app.held(response["chat_id"]).version == 1
    replay = assert_ok(app.post())
    assert replay == response and len(calls) == 1 and len(app.model.calls) == 3


def test_unconfirmed_save_does_not_publish_a_draft_or_claim_success(harness):
    app = harness(*greeting_outputs())
    def fail_save(matter, *, expected_version):
        raise OSError("Synthetic failure before replacing any bytes")
    app.store.commit = fail_save
    response = app.post()
    assert response.status_code == 503
    assert response.json()["detail"]["committed"] == "unconfirmed"
    assert "elements" not in response.json() and "UNREVIEWED" not in response.text
    assert not app.store.list_for("adv_wiring").matters
    assert len(app.model.calls) == 3


def test_retained_account_boundaries_do_not_lose_their_failure_paths(harness):
    from nm.shared.external_ai_contracts import NOTICE_VERSION
    app = harness()
    with TestClient(app.asgi) as unsigned:
        bad = unsigned.post("/api/login", headers={"origin": ORIGIN},
                            json={"advocate_id": "adv_wiring", "password": "Wrong-password"})
        absent = unsigned.post("/api/login", headers={"origin": ORIGIN},
                               json={"advocate_id": "nobody", "password": "Wrong-password"})
        assert bad.status_code == absent.status_code == 401
        assert bad.json() == absent.json()
        forgot = unsigned.post("/api/password/forgot", headers={"origin": ORIGIN},
                               json={"email": "absent@example.invalid"})
        assert forgot.status_code == 202
        invalid_reset = unsigned.post("/api/password/reset", headers={"origin": ORIGIN}, json={
            "token": "nonexistent-reset-token", "password": PASSWORD, "password_again": PASSWORD})
        assert invalid_reset.status_code == 400
    assert app.client.get("/api/account-capabilities").status_code == 200
    assert app.client.get("/api/sessions").status_code == 200
    assert app.client.get("/api/drafts/key").status_code == 200
    assert app.client.post("/api/session/activity").status_code == 200
    permission = assert_ok(app.client.get("/api/account/model-permission"))
    assert permission["accepted"] is False
    updated = app.client.post("/api/account/model-permission", json={
        "accepted": True, "notice_version": NOTICE_VERSION,
        "expected_version": permission["version"]})
    assert assert_ok(updated)["accepted"] is True
    assert app.client.post("/api/logout").status_code == 200
    assert app.client.get("/api/session").status_code == 401
    assert app.model.calls == []
