"""The served app has the Admin area, and nothing an admin is shown is an advocate's work (plan AN.46, piece 46g; owner decisions D116-D119,
7 Nov 2026: "Admins should only see the usage stats, balance available, consumption etc. not the actual conversations, files, records").

Through the real login and the real stack with a scripted model: an advocate sends a message with words of their own and a conversation is
saved; the admin then opens every Admin page; none of the advocate's words, conversation or turn identities appears in any response."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
ADMIN, VIEWER, ADVOCATE = "admin@example.test", "viewer@example.test", "advocate@example.test"
WORDS = "PURPLE-ELEPHANT-4471 the tenant of Plot 88 refused the notice"


@pytest.fixture
def served(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (ADMIN, VIEWER, ADVOCATE):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY),
                      directory=directory, mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                      audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"),
                          "NM_ADMINS": f"{ADMIN}:admin,{VIEWER}:view-only"})
    monkeypatch.setattr(api, "_application", app)
    asgi = create_app(app)
    clients = []

    def login(who):
        client = TestClient(asgi)
        clients.append(client)
        reply = client.post("/api/login", headers={"origin": "http://testserver"}, json={"advocate_id": who, "password": PASSWORD})
        assert reply.status_code == 200, reply.text
        client.headers.update({"origin": "http://testserver", "x-nm-csrf": client.cookies.get("nm_csrf")})
        return client

    yield type("Served", (), {"app": app, "login": staticmethod(login), "tmp_path": tmp_path})
    for client in clients:
        client.close()


PAGES = ("/api/admin/me", "/api/admin/overview", "/api/admin/users", f"/api/admin/users/{ADVOCATE}", "/api/admin/usage?days=7",
         "/api/admin/usage?days=90")


def test_the_admin_pages_are_in_the_served_app_and_an_advocate_who_is_not_an_admin_does_not_find_them(served):
    advocate, admin = served.login(ADVOCATE), served.login(ADMIN)
    for page in PAGES:
        assert advocate.get(page).status_code == 404, page
        assert admin.get(page).status_code == 200, page
    assert advocate.post("/api/admin/password", json={"password": PASSWORD}).status_code == 404


def test_what_an_advocate_wrote_and_saved_is_in_no_admin_response(served):
    advocate = served.login(ADVOCATE)
    sent = advocate.post("/api/turn", json={"message": WORDS, "turn_id": "turn-1"})
    assert sent.status_code == 200, sent.text
    reply = sent.json()
    assert WORDS.split()[0] in json.dumps(advocate.get(f"/api/chats/{reply['chat_id']}").json()), "the conversation was saved"
    for who in (ADMIN, VIEWER):
        admin = served.login(who)
        for page in PAGES:
            body = admin.get(page).text
            for private in ("PURPLE-ELEPHANT", "Plot 88", "tenant", reply["chat_id"], reply["turn_id"], "Inspect this"):
                assert private not in body, (page, private)
    users = {row["id"]: row for row in served.login(ADMIN).get("/api/admin/users").json()["accounts"]}
    assert users[ADVOCATE]["allowance"]["started"] and users[ADVOCATE]["status"] == "active"
    page = served.login(ADMIN).get(f"/api/admin/users/{ADVOCATE}").json()
    assert page["usage"]["totals"]["calls"] > 0  # the consumption of the turn is shown; its words are not


def test_the_view_only_admin_sees_the_same_pages_and_the_password_check_still_needs_the_page_s_token(served):
    viewer = served.login(VIEWER)
    assert viewer.get("/api/admin/me").json()["can_change"] is False
    refused = viewer.post("/api/admin/password", json={"password": PASSWORD}, headers={"x-nm-csrf": ""})
    assert refused.status_code == 403


def test_the_edge_s_other_routes_are_unchanged_by_the_admin_area(served):
    advocate = served.login(ADVOCATE)
    assert advocate.get("/api/usage").status_code == 200
    assert advocate.get("/api/health").status_code == 200
    assert not hasattr(served.app.directory, "listing")
