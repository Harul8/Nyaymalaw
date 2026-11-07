"""The Admin area's routes answer admins and nobody else (plan AN.46, piece 46g; owner decisions D116-D119, D128, 7 Nov 2026).

No session: the edge's usual 401. A signed-in advocate not named in the settings: 404, in the words of an address the server does not
have. An admin, of either level: the pages. The password check is a sign-in check, behind the sign-in limiter, protected against a
cross-site caller like every other write. Synthetic accounts; the router is mounted on a fresh app beside the edge's own dependencies."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.admin_api import admin_router
from nm.app.composition import Application
from nm.arrive import attempts_contracts
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, csrf_token, enrol, utcnow
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
BOSS, VIEWER, ADVOCATE = "boss@example.test", "viewer@example.test", "advocate@example.test"
ADDRESSES = ("/api/admin/me", "/api/admin/overview", "/api/admin/users", f"/api/admin/users/{ADVOCATE}", "/api/admin/usage")


class World:
    def __init__(self, tmp_path, monkeypatch):
        directory = FileDirectory(tmp_path, key=KEY)
        for who in (BOSS, VIEWER, ADVOCATE):
            directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
        model = ScriptedModel(legal=True)
        model.provider = "scripted"
        self.app = Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY),
                               directory=directory, mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                               audit_root=tmp_path / "audit", environment={
                                   "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                                   "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                                   "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"),
                                   "NM_ADMINS": f"{BOSS}:admin,{VIEWER}:view-only"})
        monkeypatch.setattr(api, "_application", self.app)
        self.tmp_path = tmp_path
        self.web = FastAPI()
        self.web.include_router(admin_router(application=api.application, signed_in=api.signed_in,
                                             csrf=api.CsrfProtected, admit_attempt=api._admit_auth_attempt))
        self.clients = []

    def client(self, who=None, *, device="device-1"):
        client = TestClient(self.web)
        self.clients.append(client)
        if who is not None:
            token = self.app.directory.open_session(who, api._device(device, "testclient"), utcnow())
            client.cookies.update({"nm_session": token, "nm_device": device, "nm_csrf": csrf_token(token)})
            client.headers.update({"origin": "http://testserver", "x-nm-csrf": csrf_token(token)})
        return client

    def close(self):
        for client in self.clients:
            client.close()


@pytest.fixture
def world(tmp_path, monkeypatch):
    made = World(tmp_path, monkeypatch)
    yield made
    made.close()


def test_with_no_session_every_admin_address_is_the_edge_s_usual_401(world):
    stranger = world.client()
    for address in ADDRESSES:
        assert stranger.get(address).status_code == 401, address
    assert stranger.post("/api/admin/password", json={"password": PASSWORD}).status_code == 401


def test_a_signed_in_advocate_who_is_not_named_gets_what_an_address_the_server_does_not_have_gets(world):
    advocate = world.client(ADVOCATE)
    unknown = advocate.get("/api/admin/nothing-here")
    assert unknown.status_code == 404
    for address in ADDRESSES:
        refused = advocate.get(address)
        assert (refused.status_code, refused.json()) == (404, unknown.json()), address
    posted = advocate.post("/api/admin/password", json={"password": PASSWORD})
    assert (posted.status_code, posted.json()) == (404, unknown.json())


def test_an_admin_and_a_view_only_admin_are_both_shown_the_pages_and_told_their_level(world):
    boss, viewer = world.client(BOSS), world.client(VIEWER)
    assert boss.get("/api/admin/me").json() == {"level": "admin", "label": "Admin", "can_change": True, "password_confirmed": False}
    assert viewer.get("/api/admin/me").json() == {"level": "view-only", "label": "Admin (view only)", "can_change": False,
                                                  "password_confirmed": False}
    for client in (boss, viewer):
        for address in ADDRESSES[1:]:
            reply = client.get(address)
            assert reply.status_code == 200, (address, reply.text)
    users = boss.get("/api/admin/users").json()
    assert {row["id"]: row["level_label"] for row in users["accounts"]} == {
        BOSS: "Admin", VIEWER: "Admin (view only)", ADVOCATE: "Advocate"}
    assert boss.get(f"/api/admin/users/{ADVOCATE.upper()}").json()["id"] == ADVOCATE
    assert boss.get("/api/admin/users/nobody@example.test").status_code == 404


def test_the_usage_page_answers_the_listed_periods_only(world):
    boss = world.client(BOSS)
    for days in (7, 30, 90):
        assert boss.get(f"/api/admin/usage?days={days}").json()["period"]["days"] == days
    for bad in (0, 5, 365):
        assert boss.get(f"/api/admin/usage?days={bad}").status_code == 422
    assert boss.get("/api/admin/usage?days=abc").status_code == 422


def test_the_password_check_is_a_sign_in_check_and_covers_only_the_session_that_gave_it(world):
    boss, same_boss_elsewhere = world.client(BOSS), world.client(BOSS, device="device-2")
    wrong = boss.post("/api/admin/password", json={"password": "not the password"})
    assert wrong.status_code == 403 and wrong.json()["detail"] == "That password was not right."
    assert boss.get("/api/admin/me").json()["password_confirmed"] is False
    right = boss.post("/api/admin/password", json={"password": PASSWORD})
    assert right.status_code == 200
    ends = utcnow() + timedelta(minutes=10)
    assert abs((datetime.fromisoformat(right.json()["confirmed_until"]) - ends).total_seconds()) < 30
    assert boss.get("/api/admin/me").json()["password_confirmed"] is True
    assert same_boss_elsewhere.get("/api/admin/me").json()["password_confirmed"] is False
    assert PASSWORD not in right.text and PASSWORD not in wrong.text


def test_wrong_passwords_are_counted_with_sign_ins_and_pause_the_check_even_for_the_right_one(world):
    boss = world.client(BOSS)
    for _ in range(attempts_contracts.PER_ADVOCATE):
        assert boss.post("/api/admin/password", json={"password": "wrong"}).status_code == 403
    paused = boss.post("/api/admin/password", json={"password": PASSWORD})
    assert paused.status_code == 429 and "Retry-After" in paused.headers
    assert boss.get("/api/admin/me").json()["password_confirmed"] is False


def test_the_password_check_refuses_a_cross_site_caller_and_a_body_with_anything_extra(world):
    boss = world.client(BOSS)
    forged = boss.post("/api/admin/password", json={"password": PASSWORD}, headers={"origin": "https://elsewhere.example"})
    assert forged.status_code == 403
    no_token = boss.post("/api/admin/password", json={"password": PASSWORD}, headers={"x-nm-csrf": ""})
    assert no_token.status_code == 403
    assert boss.post("/api/admin/password", json={"password": PASSWORD, "level": "admin"}).status_code == 422
    assert boss.post("/api/admin/password", json={"password": ""}).status_code == 422
    assert boss.get("/api/admin/me").json()["password_confirmed"] is False


def test_a_page_whose_source_cannot_be_read_says_so_and_nothing_else_stops(world):
    boss = world.client(BOSS)
    (world.tmp_path / "usage.sqlite").write_bytes(b"not the usage store")
    broken = boss.get("/api/admin/usage")
    assert broken.status_code == 503 and "could not be read" in broken.json()["detail"]
    assert boss.get("/api/admin/me").status_code == 200
