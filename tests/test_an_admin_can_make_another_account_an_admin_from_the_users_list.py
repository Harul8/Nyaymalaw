"""The user type (plan AN.46; owner, 7 Nov 2026: "a user type column ... Advocate and Admin, selected from a dropdown, everyone Advocate by
default, and admins can change it"). Every account is an Advocate until an Admin sets it to Admin from the Users list; an account so set sees
the Admin area as soon as it next asks, and loses it as soon as it is set back. The accounts the server's settings name keep the level they
are given there and are not changed from the page; nobody changes their own type; Admin (view only) cannot change anything. Through the real
sign-in and the real stack, on synthetic accounts."""
from __future__ import annotations

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
ROOT_ADMIN, VIEWER, ADVOCATE, SECOND, THIRD = ("root@example.test", "viewer@example.test", "advocate@example.test", "second@example.test",
                                              "third@example.test")


@pytest.fixture
def served(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (ROOT_ADMIN, VIEWER, ADVOCATE, SECOND, THIRD):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY),
                      directory=directory, mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                      audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"),
                          "NM_ADMINS": f"{ROOT_ADMIN}:admin,{VIEWER}:view-only"})
    monkeypatch.setattr(api, "_application", app)
    asgi = create_app(app)
    clients = []

    def login(who, *, confirmed=False):
        client = TestClient(asgi)
        clients.append(client)
        reply = client.post("/api/login", headers={"origin": "http://testserver"}, json={"advocate_id": who, "password": PASSWORD})
        assert reply.status_code == 200, reply.text
        client.headers.update({"origin": "http://testserver", "x-nm-csrf": client.cookies.get("nm_csrf")})
        if confirmed:
            assert client.post("/api/admin/password", json={"password": PASSWORD}).status_code == 200
        return client

    class Served:
        pass

    made = Served()
    made.app, made.login = app, staticmethod(login)
    yield made
    for client in clients:
        client.close()


def set_type(client, who, user_type, reason="Joins the chambers' admins"):
    return client.post(f"/api/admin/users/{who}/user-type", json={"user_type": user_type, "reason": reason})


def rows(client):
    return {row["id"]: row for row in client.get("/api/admin/users").json()["accounts"]}


def test_everyone_is_an_advocate_by_default_and_the_settings_named_are_shown_as_set_there(served):
    admin = served.login(ROOT_ADMIN)
    found = rows(admin)
    assert {who: (row["user_type"], row["level_label"], row["type_locked"]) for who, row in found.items()} == {
        ROOT_ADMIN: ("admin", "Admin", True), VIEWER: ("admin", "Admin (view only)", True), ADVOCATE: ("advocate", "Advocate", False),
        SECOND: ("advocate", "Advocate", False), THIRD: ("advocate", "Advocate", False)}


def test_an_account_made_an_admin_sees_the_admin_area_at_once_and_loses_it_at_once_when_set_back(served):
    promoted, admin = served.login(ADVOCATE), served.login(ROOT_ADMIN, confirmed=True)
    assert promoted.get("/api/admin/me").status_code == 404
    reply = set_type(admin, ADVOCATE, "admin")
    assert reply.status_code == 200 and reply.json()["user_type"] == "admin" and reply.json()["changed"] is True
    me = promoted.get("/api/admin/me")
    assert me.status_code == 200 and (me.json()["level"], me.json()["can_change"], me.json()["id"]) == ("admin", True, ADVOCATE)
    assert promoted.get("/api/admin/users").status_code == 200 and promoted.get("/admin").status_code == 200
    assert rows(admin)[ADVOCATE]["level_label"] == "Admin" and rows(admin)[ADVOCATE]["type_locked"] is False
    assert set_type(admin, ADVOCATE, "advocate").status_code == 200
    assert promoted.get("/api/admin/me").status_code == 404 and promoted.get("/admin").status_code == 404
    assert rows(admin)[ADVOCATE]["user_type"] == "advocate"


def test_an_admin_made_by_an_admin_can_change_other_accounts_and_appears_on_the_access_page_as_set_by_an_admin(served):
    admin = served.login(ROOT_ADMIN, confirmed=True)
    set_type(admin, ADVOCATE, "admin")
    second = served.login(ADVOCATE, confirmed=True)
    assert set_type(second, SECOND, "admin").status_code == 200
    page = admin.get("/api/admin/access").json()
    assert {(a["id"], a["label"], a["source"]) for a in page["admins"]} == {
        (ROOT_ADMIN, "Admin", "server settings"), (VIEWER, "Admin (view only)", "server settings"),
        (ADVOCATE, "Admin", "set by an admin"), (SECOND, "Admin", "set by an admin")}


def test_each_change_is_audited_before_and_after_with_the_reason(served):
    admin = served.login(ROOT_ADMIN, confirmed=True)
    set_type(admin, ADVOCATE, "admin", reason="Covers while Meera is away")
    entries = [(e.actor, e.action, e.target, e.reason, e.outcome) for e in reversed(served.app.admin_record.entries(limit=10))]
    assert entries == [(ROOT_ADMIN, "user type admin", ADVOCATE, "Covers while Meera is away", "started"),
                       (ROOT_ADMIN, "user type admin", ADVOCATE, "Covers while Meera is away", "done")]


def test_setting_the_type_it_already_has_changes_nothing_and_says_so(served):
    admin = served.login(ROOT_ADMIN, confirmed=True)
    assert set_type(admin, ADVOCATE, "advocate").json()["changed"] is False


def test_nobody_changes_their_own_type_and_the_settings_named_are_not_changed_here(served):
    admin = served.login(ROOT_ADMIN, confirmed=True)
    assert set_type(admin, ROOT_ADMIN, "advocate").status_code == 409
    assert "named in the server's settings" in set_type(admin, VIEWER, "advocate").json()["detail"]
    set_type(admin, ADVOCATE, "admin")
    own = served.login(ADVOCATE, confirmed=True)
    assert set_type(own, ADVOCATE, "advocate").status_code == 409
    assert rows(admin)[ADVOCATE]["user_type"] == "admin" and served.app.admin_record.verify().entries == 2


def test_view_only_an_unconfirmed_admin_and_an_advocate_cannot_change_a_type(served):
    advocate, unconfirmed, viewer = served.login(ADVOCATE), served.login(ROOT_ADMIN), served.login(VIEWER, confirmed=True)
    assert set_type(advocate, SECOND, "admin").status_code == 404
    assert set_type(viewer, SECOND, "admin").status_code == 403
    refused = set_type(unconfirmed, SECOND, "admin")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "password_needed"
    assert rows(served.login(ROOT_ADMIN))[SECOND]["user_type"] == "advocate"


def test_an_unknown_account_an_unknown_type_and_a_missing_reason_change_nothing(served):
    admin = served.login(ROOT_ADMIN, confirmed=True)
    assert set_type(admin, "nobody@example.test", "admin").status_code == 404
    assert set_type(admin, SECOND, "owner").status_code == 422
    assert set_type(admin, SECOND, "admin", reason="  ").status_code == 422
    assert rows(admin)[SECOND]["user_type"] == "advocate" and served.app.admin_record.verify().entries == 0


def test_an_admin_is_not_suspended_from_the_page_whichever_way_they_became_one(served):
    admin = served.login(ROOT_ADMIN, confirmed=True)
    set_type(admin, ADVOCATE, "admin")
    for who in (ADVOCATE, VIEWER, ROOT_ADMIN):
        reply = admin.post(f"/api/admin/users/{who}/suspend", json={"reason": "no"})
        assert reply.status_code == 409 and "Admins are not suspended from here" in reply.json()["detail"], who


def test_the_user_type_survives_a_sign_in_and_a_suspension_and_its_lifting(served):
    admin = served.login(ROOT_ADMIN, confirmed=True)
    set_type(admin, SECOND, "admin")
    set_type(admin, SECOND, "advocate")
    admin.post(f"/api/admin/users/{SECOND}/suspend", json={"reason": "away"})
    served.login(SECOND)  # signing in lifts the suspension
    again = rows(admin)[SECOND]
    assert (again["status"], again["user_type"]) == ("active", "advocate")
    set_type(admin, THIRD, "admin")
    admin.post(f"/api/admin/users/{THIRD}/end-sessions", json={"reason": "tidy"})
    assert served.login(THIRD).get("/api/admin/me").status_code == 200
