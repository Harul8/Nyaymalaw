"""Authenticated core integration; scripted review proves wiring, not legal accuracy."""
from copy import deepcopy
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.core_engine.conversation import HEADER, chat_matter_id, digest
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
OWNER = "core-owner@example.test"
OTHER = "core-other@example.test"
PASSWORD = "Synthetic-fixture-password-72!"
KEY = "Synthetic-served-store-key-83"


@pytest.fixture
def served(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    store = FileMatterStore(tmp_path, key=KEY)
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    for who in (OWNER, OTHER):
        directory.enrol(Enrolment(AdvocateIdentity(who, who), enrol(PASSWORD)))
    app = Application(root=Path(__file__).resolve().parents[1], model=model,
        store=store, directory=directory, mail=FileOutbox(tmp_path, key=KEY),
        legal_search=searcher(), audit_root=tmp_path / "audit", environment={
            "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path),
            "NM_MODEL_PROVIDER": "scripted", "NM_MODEL_ROUTINE": "scripted-1",
            "NM_EMBED_MODEL": "text-embedding-3-large"})
    monkeypatch.setattr(api, "_application", app)
    asgi = create_app(app)
    clients = []

    def login(who=OWNER, client=None):
        if client is None:
            client = TestClient(asgi)
            clients.append(client)
        reply = client.post("/api/login", headers={"origin": "http://testserver"},
                            json={"advocate_id": who, "password": PASSWORD})
        assert reply.status_code == 200, reply.text
        client.headers.update({"origin": "http://testserver",
                              "x-nm-csrf": client.cookies.get("nm_csrf")})
        return client

    yield SimpleNamespace(app=app, store=store, directory=directory, model=model,
                          client=login(), login=login)
    for client in clients:
        client.close()


def send(served, **changes):
    return served.client.post("/api/turn", json={"message": "Inspect this reported account.",
                                               "turn_id": "turn-1", **changes})


def successful(served, **changes):
    response = send(served, **changes)
    assert response.status_code == 200, response.text
    return response.json()


def source_url(reply, element=0, source=0):
    return (f"/api/chats/{reply['chat_id']}/turns/{reply['turn_id']}"
            f"/brain-sources/{element}/{source}")


def test_public_turn_saves_exact_input_reopens_and_reads_exact_sources_without_calls(served):
    message = "  Original account: नमस्ते.\nDo not contact anyone.  "
    reply = successful(served, message=message)
    assert reply["committed"] == "committed" and reply["matter_id"] is None
    assert reply["metrics"]["llm_calls"] == 4
    matter = served.store.load(chat_matter_id(OWNER, reply["chat_id"]))
    assert matter.brain_chat[0]["message"] == message
    assert matter.brain_chat[0]["response"]["committed"] == "committed"
    reopened = served.client.get(f"/api/chats/{reply['chat_id']}")
    assert reopened.status_code == 200
    assert reopened.headers["cache-control"] == "no-store"
    turn = reopened.json()["turns"][0]
    assert turn["message"] == message and turn["elements"] == reply["elements"]
    assert turn["committed"] is True and turn["release_state"] == "released"
    for index, source in enumerate(reply["elements"][0]["sources"]):
        read = served.client.get(source_url(reply, source=index))
        assert read.status_code == 200
        viewed = read.json()
        inspection = viewed.pop('authority_inspection')
        assert viewed == source and inspection['source_id'] == source['id']
        assert read.headers["cache-control"] == "no-store"
    work = served.client.get("/api/work").json()
    assert work["state"] == "ok" and work["chat_count"] == 1 and not work["matters"]
    assert work["chats"][0]["preview"] == message
    replay = successful(served, message=message, expected_version=0)
    assert replay == {**reply, "replayed": True}
    assert len(served.model.calls) == 4


def test_followup_preserves_complete_saved_context_at_every_stage(served):
    first = successful(served, message="The account is contested. Do not write to the supplier.")
    successful(served, turn_id="turn-2", chat_id=first["chat_id"], message="Hello again.")
    for operation, payload in served.model.calls[4:]:
        context = payload if operation == "core_understanding" else payload["original_context"]
        assert context["conversation"][0]["text"] == "The account is contested. Do not write to the supplier."
        assert context["conversation"][1]["text"] == first["elements"][0]["text"]
    assert served.client.get(f"/api/chats/{first['chat_id']}").json()["turns"][1]["turn_id"] == "turn-2"


def test_another_authenticated_account_cannot_read_or_continue_owned_chat(served):
    reply = successful(served)
    other = served.login(OTHER)
    for url in (f"/api/chats/{reply['chat_id']}", source_url(reply)):
        read = other.get(url)
        assert read.status_code == 404 and "Counsel" not in read.text
    post = other.post("/api/turn", json={"message": "Continue.", "turn_id": "foreign-turn",
                                         "chat_id": reply["chat_id"]})
    unknown = other.post("/api/turn", json={"message": "Continue.", "turn_id": "foreign-turn",
                                            "chat_id": "unknown-chat"})
    assert post.status_code == unknown.status_code == 409
    assert post.json()["detail"]["why"] == unknown.json()["detail"]["why"]
    assert other.get("/api/work").json()["chats"] == []
    assert len(served.model.calls) == 4 and not served.store.list_for(OTHER).matters


@pytest.mark.parametrize("headers", [{"x-nm-csrf": "wrong"}, {"origin": "https://foreign.invalid"}])
def test_csrf_refuses_before_any_model_or_save(served, headers):
    response = served.client.post("/api/turn", headers=headers,
                                  json={"message": "Hello", "turn_id": "t"})
    assert response.status_code == 403
    assert not served.model.calls and not served.store.list_for(OWNER).matters


def test_unauthenticated_access_discloses_nothing(served):
    with TestClient(api.app) as anonymous:
        for url in ("/api/work", "/api/chats/unknown", "/api/chats/x/turns/y/brain-sources/0/0"):
            assert anonymous.get(url).status_code == 401
        assert anonymous.post("/api/turn", json={"message": "Hello", "turn_id": "t"}).status_code == 401
    assert not served.model.calls


@pytest.mark.parametrize("fields", [{"turn_id": None}, {"turn_id": "  "}, {"message": "  "}])
def test_missing_request_identity_or_empty_message_is_not_minted_or_admitted(served, fields):
    response = send(served, **fields)
    assert response.status_code == 422
    assert not served.model.calls and not served.store.list_for(OWNER).matters


@pytest.mark.parametrize("fields", [{"work_product": "draft"}, {"keep_in_matter": True},
    {"parties": {"Person": "client"}}, {"thread_id": "prior-work"}, {"today": "2026-10-10"}])
def test_unsupported_action_fields_are_refused_not_silently_ignored(served, fields):
    response = send(served, **fields)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_action_settings"
    assert not served.model.calls


def test_empty_legacy_presentation_fields_do_not_reject_current_browser_request(served):
    successful(served, parties={}, release={}, thread_id=None, capacity=None, keep_in_matter=False)


def test_session_revoked_during_review_prevents_save_and_disclosure(served, monkeypatch):
    original = served.model.structured
    token = served.client.cookies.get("nm_session")
    def revoke(prompt, *args, **kwargs):
        result = original(prompt, *args, **kwargs)
        if prompt.operation == "core_response_review":
            served.directory.close_session(token, "Synthetic revocation")
        return result
    monkeypatch.setattr(served.model, "structured", revoke)
    response = send(served)
    assert response.status_code == 401 and "Counsel" not in response.text
    assert not served.store.list_for(OWNER).matters


def test_revocation_after_atomic_save_withholds_reply_but_relogin_replays_once(served, monkeypatch):
    original = served.store.commit
    token = served.client.cookies.get("nm_session")
    def revoke(matter, **kwargs):
        result = original(matter, **kwargs)
        served.directory.close_session(token, "Synthetic post-save revocation")
        return result
    monkeypatch.setattr(served.store, "commit", revoke)
    response = send(served)
    assert response.status_code == 401 and "Counsel" not in response.text
    assert len(served.store.list_for(OWNER).matters) == 1
    served.login(client=served.client)
    replay = successful(served)
    assert replay["replayed"] and len(served.model.calls) == 4


@pytest.mark.parametrize("route", ["chat", "source", "work"])
def test_revocation_during_saved_read_prevents_disclosure(served, monkeypatch, route):
    reply = successful(served)
    method = "list_for" if route == "work" else "load"
    original = getattr(served.store, method)
    token = served.client.cookies.get("nm_session")
    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        served.directory.close_session(token, "Synthetic read revocation")
        return result
    monkeypatch.setattr(served.store, method, revoke)
    url = "/api/work" if route == "work" else source_url(reply) if route == "source" else f"/api/chats/{reply['chat_id']}"
    response = served.client.get(url)
    assert response.status_code == 401
    assert "Counsel" not in response.text and "reported account" not in response.text
    assert len(served.model.calls) == 4


def test_unknown_saved_renderer_is_not_upgraded_or_released(served):
    reply = successful(served)
    matter = served.store.load(chat_matter_id(OWNER, reply["chat_id"]))
    rows, metadata = deepcopy(matter.brain_chat), deepcopy(matter.intake_answers)
    rows[0]["activities"]["rendering_contract"] = "unknown_future"
    rows[0]["digest"] = digest({key: value for key, value in rows[0].items() if key != "digest"})
    metadata[HEADER]["tail_digest"] = rows[0]["digest"]
    served.store.commit(replace(matter, brain_chat=rows, intake_answers=metadata,
                               version=matter.version + 1), expected_version=matter.version)
    for url in (f"/api/chats/{reply['chat_id']}", source_url(reply)):
        response = served.client.get(url)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "saved_response_unavailable"
        assert "Counsel" not in response.text
    assert send(served).status_code == 409
    work = served.client.get("/api/work").json()
    assert work["state"] == "partial" and not work["chats"] and not work["matters"]
    assert len(served.model.calls) == 4


def test_old_matter_is_listed_as_history_without_reinterpretation(served):
    matter = Matter.create(OWNER, "Historic matter")
    served.store.commit(matter, expected_version=0)
    work = served.client.get("/api/work").json()
    assert work["matters"][0]["state"] == "historical" and not work["chats"]
    assert served.client.get(f"/api/matters/{matter.id}").status_code == 409
    assert not served.model.calls


def test_lost_save_acknowledgement_returns_durable_receipt_without_reexecution(served, monkeypatch):
    original = served.store.commit
    def lose(matter, **kwargs):
        original(matter, **kwargs)
        raise OSError("Synthetic lost acknowledgement")
    monkeypatch.setattr(served.store, "commit", lose)
    reply = successful(served)
    assert successful(served)["replayed"]
    assert len(served.store.load(chat_matter_id(OWNER, reply["chat_id"])).brain_chat) == 1
    assert len(served.model.calls) == 4


def test_unconfirmed_save_retry_only_reads_receipt_and_never_reexecutes_effects(served, monkeypatch):
    original = served.store.commit
    pending = []
    def fail(matter, **kwargs):
        pending.append((matter, kwargs))
        raise OSError("Synthetic unavailable store")
    monkeypatch.setattr(served.store, "commit", fail)
    response = send(served)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "save_unconfirmed" and detail["committed"] == "unconfirmed"
    assert detail["retryable"] and detail["turn_id"] == "turn-1"
    assert "Counsel" not in response.text and not served.store.list_for(OWNER).matters
    monkeypatch.setattr(served.store, "commit", original)
    unconfirmed = send(served)
    assert unconfirmed.status_code == 503
    assert unconfirmed.json()["detail"]["code"] == "attempt_unconfirmed"
    assert len(served.model.calls) == 4 and not served.store.list_for(OWNER).matters
    # A delayed confirmation supplies the exact original candidate. A retry
    # reads that durable receipt; it does not generate or apply another effect.
    original(pending[0][0], **pending[0][1])
    reply = successful(served)
    assert reply["replayed"] and len(served.model.calls) == 4
    assert len(served.store.load(chat_matter_id(OWNER, reply["chat_id"])).brain_chat) == 1


def test_review_correction_rechecks_complete_context_and_saves_once(served):
    served.model.reject = 1
    reply = successful(served)
    assert reply["metrics"]["llm_calls"] == 6 and reply["metrics"]["draft_corrections"] == 1
    correction, review = served.model.calls[4:]
    assert "correction" in correction[1] and "correction" not in review[1]
    assert correction[1]["original_context"] == review[1]["original_context"]
    assert len(served.store.load(chat_matter_id(OWNER, reply["chat_id"])).brain_chat) == 1


def test_shape_and_semantic_repair_share_one_bound_and_terminal_failure_never_saves(served):
    served.model.malformed_writer = served.model.reject = 1
    response = send(served)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "answer_withheld" and not detail["retryable"]
    assert detail["committed"] == "not_committed" and "Counsel" not in response.text
    assert len(served.model.calls) == 5 and not served.store.list_for(OWNER).matters


def test_terminal_review_gate_survives_same_identity_http_retry(served):
    served.model.reject = 2
    first = send(served)
    assert first.status_code == 503 and first.json()["detail"]["code"] == "answer_withheld"
    assert len(served.model.calls) == 6
    served.model.reject = 0
    second = send(served)
    assert second.status_code == 409 and second.json()["detail"]["code"] == "answer_withheld"
    assert not second.json()["detail"]["retryable"] and len(served.model.calls) == 6
    assert not served.store.list_for(OWNER).matters
    successful(served, turn_id="distinct-new-turn")
    assert len(served.model.calls) == 10


def test_provider_outage_does_not_save_an_empty_success(served):
    served.model.failure = "core_response_review"
    response = send(served)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "response_unavailable" and detail["retryable"]
    assert detail["committed"] == "not_committed" and not served.store.list_for(OWNER).matters


def test_saved_replay_requires_no_new_model_permission_but_new_work_does(served, monkeypatch):
    reply = successful(served)
    def refuse(*args, **kwargs): raise ModelPermissionRefused("External model permission is required.")
    monkeypatch.setattr(served.app, "_model_for", refuse)
    assert successful(served)["replayed"]
    response = send(served, turn_id="turn-2", chat_id=reply["chat_id"])
    assert response.status_code == 403 and response.json()["detail"]["code"] == "model_permission_required"
    assert len(served.model.calls) == 4


def test_permission_denied_before_first_call_can_resume_same_request_after_grant(served, monkeypatch):
    original = served.app._model_for
    def refuse(*args, **kwargs): raise ModelPermissionRefused("External model permission is required.")
    monkeypatch.setattr(served.app, "_model_for", refuse)
    response = send(served)
    assert response.status_code == 403 and response.json()["detail"]["code"] == "model_permission_required"
    assert not served.model.calls and not served.store.list_for(OWNER).matters
    monkeypatch.setattr(served.app, "_model_for", original)
    reply = successful(served)
    assert len(served.model.calls) == 4
    assert len(served.store.load(chat_matter_id(OWNER, reply["chat_id"])).brain_chat) == 1


@pytest.mark.parametrize("damage", ["unknown_version", "corrupt"])
def test_saved_chat_replay_survives_unavailable_attempt_sidecar_after_restart(served, monkeypatch, damage):
    reply = successful(served)
    path = Path(served.app.environment["NM_MATTER_STORE"]) / "turn-attempts.sqlite"
    if damage == "unknown_version":
        with closing(sqlite3.connect(path)) as database:
            database.execute("PRAGMA user_version=999")
    else:
        path.write_bytes(b"Synthetic corrupt sidecar")
    restarted = Application(root=served.app.root, model=served.model,
        store=served.store, directory=served.directory, mail=served.app.mail.inner,
        legal_search=searcher(), audit_root=served.app.audit_root,
        environment=served.app.environment)
    monkeypatch.setattr(api, "_application", restarted)
    assert served.client.get(f"/api/chats/{reply['chat_id']}").status_code == 200
    viewed = served.client.get(source_url(reply)).json()
    viewed.pop('authority_inspection')
    assert viewed == reply["elements"][0]["source"]
    assert successful(served)["replayed"] and len(served.model.calls) == 4
    fresh = send(served, turn_id="turn-2", chat_id=reply["chat_id"])
    assert fresh.status_code == 503 and fresh.json()["detail"]["code"] == "attempt_unconfirmed"
    assert not fresh.json()["detail"]["retryable"] and len(served.model.calls) == 4


@pytest.mark.parametrize("element,source", [(-1, 0), (0, -1), (1, 0), (0, 99)])
def test_saved_source_index_must_select_an_actual_checked_passage(served, element, source):
    reply = successful(served)
    response = served.client.get(source_url(reply, element, source))
    assert response.status_code == 404 and len(served.model.calls) == 4
