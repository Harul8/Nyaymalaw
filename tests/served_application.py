"""The served application on a throwaway store with scripted models, and the helpers its tests share (plan AN.57, piece 57e;
D266). The application is offered to every test as the `served` fixture by tests/conftest.py, which reads this module only when
a test asks for it; a test imports the accounts and helpers from here, never from another test file. Moved here from
tests/test_core_served.py, which about ninety test files borrowed them from. Offline: scripted models, synthetic accounts - it
proves wiring, not legal accuracy.
"""
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_turn import ScriptedModel, searcher

OWNER = "core-owner@example.test"
OTHER = "core-other@example.test"
PASSWORD = "Synthetic-fixture-password-72!"
KEY = "Synthetic-served-store-key-83"


def application(tmp_path, monkeypatch):
    """The `served` fixture's body: two enrolled synthetic advocates, the owner signed in; closes its clients afterwards."""
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
            "NM_EMBED_MODEL": "text-embedding-3-large",
            # Like the scripted search, these turns read no corpus: no held Acts, so no
            # time limit is worked out (tests/test_core_calculation.py covers that path).
            "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts")})
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


def no_answer_saved(served, code=None):
    """Plan AN.41 (D66): no answer is saved; the message is, from Send, kept beside the conversation with why it stopped."""
    from nm.core_engine.conversation import shown_of
    matters = served.store.list_for(OWNER).matters
    assert all(matter.brain_chat == () for matter in matters)
    if code is not None:
        assert len(matters) == 1 and shown_of(matters[0])["stopped"]["code"] == code
    return matters


def send(served, **changes):
    return served.client.post("/api/turn", json={"message": "Inspect this reported account.",
                                               "turn_id": "turn-1", **changes})


def successful(served, **changes):
    response = send(served, **changes)
    assert response.status_code == 200, response.text
    return response.json()


def source_url(reply, element=None, source=0):
    """The reading pane's address of a saved passage: by default the first paragraph's that cites
    one (from rendering v18 an answer opens with In short, which cites none)."""
    if element is None:
        element = next((index for index, shown in enumerate(reply.get("elements") or []) if shown.get("sources")), 0)
    return (f"/api/chats/{reply['chat_id']}/turns/{reply['turn_id']}"
            f"/brain-sources/{element}/{source}")
