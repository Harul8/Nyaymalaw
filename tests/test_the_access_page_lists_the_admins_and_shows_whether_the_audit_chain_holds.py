"""The Access page (plan AN.46, piece 46s; owner decisions D117, D118, D126, 7 Nov 2026): who the server's settings name as admins and at
what level, how many settings entries were ignored, and what admins have done - the audit log, newest first, with whether its chain still
holds. Admins of both levels may look; an advocate gets the 404 of an address that is not there."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.admin_api import admin_router
from nm.app.composition import Application
from nm.arrive.admin_port import AuditEntry
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, csrf_token, enrol, utcnow
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
BOSS, VIEWER, ADVOCATE, GHOST = "boss@example.test", "viewer@example.test", "advocate@example.test", "ghost@example.test"


@pytest.fixture
def world(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (BOSS, VIEWER, ADVOCATE):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY),
                      directory=directory, mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                      audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"),
                          "NM_ADMINS": f"{BOSS}:admin, {VIEWER}:view-only, {GHOST}:admin, broken-entry, x@example.test:owner"})
    monkeypatch.setattr(api, "_application", app)
    web = FastAPI()
    web.include_router(admin_router(application=api.application, signed_in=api.signed_in, csrf=api.CsrfProtected,
                                    admit_attempt=api._admit_auth_attempt))
    clients = []

    def client(who):
        made = TestClient(web)
        clients.append(made)
        token = app.directory.open_session(who, api._device("device-1", "testclient"), utcnow())
        made.cookies.update({"nm_session": token, "nm_device": "device-1", "nm_csrf": csrf_token(token)})
        made.headers.update({"origin": "http://testserver", "x-nm-csrf": csrf_token(token)})
        return made

    class World:
        pass

    made = World()
    made.app, made.client, made.tmp_path = app, client, tmp_path
    yield made
    for each in clients:
        each.close()


def log(world, **changes):
    entry = {"at": datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc), "actor": BOSS, "action": "allowance",
             "target": ADVOCATE, "reason": "granted a top-up", "outcome": "done"}
    entry.update(changes)
    return world.app.admin_record.append(AuditEntry(**entry))


def test_the_page_lists_the_admins_with_their_level_and_counts_the_entries_that_were_ignored(world):
    page = world.client(BOSS).get("/api/admin/access").json()
    assert {a["id"]: (a["level"], a["label"], a["has_account"]) for a in page["admins"]} == {
        BOSS: ("admin", "Admin", True), VIEWER: ("view-only", "Admin (view only)", True), GHOST: ("admin", "Admin", False)}
    assert next(a for a in page["admins"] if a["id"] == GHOST)["status"] == "no account"
    assert next(a for a in page["admins"] if a["id"] == BOSS)["name"] == "Boss"
    assert page["rejected_entries"] == 2


def test_an_empty_log_is_shown_as_a_chain_that_holds(world):
    page = world.client(VIEWER).get("/api/admin/access").json()
    assert page["audit"]["available"] is True and page["audit"]["entries"] == []
    assert page["audit"]["chain"]["ok"] is True and page["audit"]["chain"]["entries"] == 0


def test_the_log_is_shown_newest_first_with_each_fingerprint_and_the_chains_newest(world):
    first = log(world, reason="first")
    second = log(world, at=datetime(2026, 11, 7, 11, 0, tzinfo=timezone.utc), reason="second", action="approval")
    audit = world.client(BOSS).get("/api/admin/access").json()["audit"]
    assert [e["reason"] for e in audit["entries"]] == ["second", "first"]
    assert [e["fingerprint"] for e in audit["entries"]] == [second.fingerprint, first.fingerprint]
    assert audit["chain"] == {"ok": True, "entries": 2, "first_bad_id": None, "newest": second.fingerprint}
    assert set(audit["entries"][0]) == {"id", "at", "actor", "action", "target", "reason", "outcome", "fingerprint"}


def test_a_changed_entry_shows_as_a_broken_chain_at_the_first_bad_entry(world):
    import sqlite3
    from contextlib import closing
    log(world, reason="first")
    log(world, reason="second")
    path = world.tmp_path / "admin.sqlite"
    with closing(sqlite3.connect(path)) as db, db:
        triggers = db.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall()
        for name, _ in triggers:
            db.execute(f"DROP TRIGGER {name}")
        db.execute("UPDATE audit SET reason='altered' WHERE id=1")
        for _, sql in triggers:
            db.execute(sql)
    chain = world.client(BOSS).get("/api/admin/access").json()["audit"]["chain"]
    assert chain["ok"] is False and chain["first_bad_id"] == 1


def test_a_log_that_cannot_be_read_leaves_the_admins_standing(world):
    (world.tmp_path / "admin.sqlite").write_bytes(b"not a database")
    page = world.client(BOSS).get("/api/admin/access").json()
    assert page["audit"] == {"available": False} and len(page["admins"]) == 3


def test_an_advocate_gets_the_404_of_an_address_that_is_not_there(world):
    advocate = world.client(ADVOCATE)
    assert advocate.get("/api/admin/access").json() == advocate.get("/api/admin/nothing-here").json()
    assert advocate.get("/api/admin/access").status_code == 404
