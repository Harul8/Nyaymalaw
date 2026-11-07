"""An admin's change (plan AN.46, pieces 46j and 46k; owner decisions D116 and D121, 7 Nov 2026): add to an allowance, end an account's
sessions, suspend and reinstate. Every change takes one path - the admin's level permits it, the admin gave their password just now in
this session, the reason is one line, the audit log takes a first entry before and a second after - and a refusal at any step has
changed nothing. Through the real login and the real stack, on synthetic accounts."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.composition import Application
from nm.app.main import create_app
from nm.arrive.admin_port import AdminUnavailable
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_core_served import KEY, PASSWORD
from tests.test_core_turn import ScriptedModel, searcher

pytestmark = pytest.mark.class_a
ADMIN, VIEWER, ADVOCATE, OTHER = "admin@example.test", "viewer@example.test", "advocate@example.test", "other@example.test"
TRIAL = 300_000


@pytest.fixture
def served(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (ADMIN, VIEWER, ADVOCATE, OTHER):
        directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0].title()), enrol(PASSWORD)))
    model = ScriptedModel(legal=True)
    model.provider = "scripted"
    app = Application(root=Path(__file__).resolve().parents[1], model=model, store=FileMatterStore(tmp_path, key=KEY),
                      directory=directory, mail=FileOutbox(tmp_path, key=KEY), legal_search=searcher(),
                      audit_root=tmp_path / "audit", environment={
                          "NM_MATTER_KEY": KEY, "NM_MATTER_STORE": str(tmp_path), "NM_MODEL_PROVIDER": "scripted",
                          "NM_MODEL_ROUTINE": "scripted-1", "NM_EMBED_MODEL": "text-embedding-3-large",
                          "NM_BARE_ACTS_DIR": str(tmp_path / "no-held-acts"), "NM_ADMINS": f"{ADMIN}:admin,{VIEWER}:view-only"})
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
    made.app, made.login, made.tmp_path, made.asgi = app, staticmethod(login), tmp_path, asgi
    yield made
    for client in clients:
        client.close()


def audit(served):
    return [(e.actor, e.action, e.target, e.reason, e.outcome) for e in reversed(served.app.admin_record.entries(limit=50))]


def granted(served, who):
    return served.app.admin_usage.balances().get(__import__("hashlib").sha256(who.encode()).hexdigest())


def allowance(client, who=ADVOCATE, **changes):
    body = {"usd": "5", "reason": "Top-up agreed with the chambers"}
    body.update(changes)
    return client.post(f"/api/admin/users/{who}/allowance", json=body)


# ------------------------------------------------------------------------- who may change ---

def test_an_advocate_who_is_not_an_admin_gets_the_404_of_an_address_that_is_not_there_for_every_change(served):
    advocate = served.login(ADVOCATE)
    unknown = advocate.get("/api/admin/nothing-here").json()
    for suffix, body in (("allowance", {"usd": "5", "reason": "x"}), ("end-sessions", {"reason": "x"}), ("suspend", {"reason": "x"}),
                         ("reinstate", {"reason": "x"})):
        reply = advocate.post(f"/api/admin/users/{OTHER}/{suffix}", json=body)
        assert (reply.status_code, reply.json()) == (404, unknown), suffix
    assert audit(served) == []


def test_a_view_only_admin_is_refused_every_change_and_nothing_is_written(served):
    viewer = served.login(VIEWER, confirmed=True)
    for suffix, body in (("allowance", {"usd": "5", "reason": "x"}), ("end-sessions", {"reason": "x"}), ("suspend", {"reason": "x"}),
                         ("reinstate", {"reason": "x"})):
        reply = viewer.post(f"/api/admin/users/{ADVOCATE}/{suffix}", json=body)
        assert reply.status_code == 403 and reply.json()["detail"] == "Admin (view only) can look but cannot change anything.", suffix
    assert audit(served) == [] and granted(served, ADVOCATE) is None


def test_an_admin_who_has_not_given_their_password_is_asked_for_it_and_nothing_is_changed(served):
    admin = served.login(ADMIN)
    reply = allowance(admin)
    assert reply.status_code == 403 and reply.json()["detail"] == {"code": "password_needed", "message": "Confirm your password to make this change."}
    assert audit(served) == [] and granted(served, ADVOCATE) is None


def test_the_password_check_belongs_to_one_session_so_the_same_admin_elsewhere_is_asked_again(served):
    first, second = served.login(ADMIN, confirmed=True), served.login(ADMIN)
    assert allowance(first).status_code == 200
    assert allowance(second).status_code == 403


def test_a_change_without_the_cross_site_header_is_refused_before_anything_else(served):
    admin = served.login(ADMIN, confirmed=True)
    del admin.headers["x-nm-csrf"]
    assert allowance(admin).status_code == 403 and audit(served) == []


# ------------------------------------------------------------------------- the allowance ---

def test_an_allowance_is_added_with_a_first_and_a_second_audit_entry_and_the_new_balance_is_told(served):
    admin = served.login(ADMIN, confirmed=True)
    reply = allowance(admin, usd="5.25")
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["allowance"]["granted"] == TRIAL + 5_250_000 and body["audited"] is True
    assert audit(served) == [(ADMIN, "allowance add usd 5.25", ADVOCATE, "Top-up agreed with the chambers", "started"),
                             (ADMIN, "allowance add usd 5.25", ADVOCATE, "Top-up agreed with the chambers", "done")]
    assert granted(served, ADVOCATE).granted == TRIAL + 5_250_000
    assert served.app.admin_record.verify().ok


def test_the_grant_note_in_the_usage_store_names_the_admin_and_the_reason(served):
    admin = served.login(ADMIN, confirmed=True)
    allowance(admin, reason="Agreed on the call")
    with closing(sqlite3.connect(served.tmp_path / "usage.sqlite")) as db:
        notes = [row[0] for row in db.execute("SELECT note FROM grants WHERE kind='operator'")]
    assert notes == [f"{ADMIN}: Agreed on the call"]


@pytest.mark.parametrize("reason", ["", "   ", "two\nlines", "x" * 201, "bell\x07"])
def test_a_reason_must_be_one_line_of_at_most_200_characters_or_nothing_is_changed(served, reason):
    admin = served.login(ADMIN, confirmed=True)
    reply = allowance(admin, reason=reason)
    assert reply.status_code == 422 and reply.json()["detail"].startswith("Give a reason")
    assert audit(served) == [] and granted(served, ADVOCATE) is None


@pytest.mark.parametrize("usd", ["0", "-1", "1000.01", "0.0000001", "abc", ""])
def test_an_amount_must_be_a_positive_sum_up_to_a_thousand_dollars_to_six_places_or_nothing_is_changed(served, usd):
    admin = served.login(ADMIN, confirmed=True)
    assert allowance(admin, usd=usd).status_code == 422
    assert audit(served) == [] and granted(served, ADVOCATE) is None


def test_an_account_that_is_not_there_is_the_404_of_any_unknown_user_and_makes_no_record(served):
    admin = served.login(ADMIN, confirmed=True)
    reply = allowance(admin, who="nobody@example.test")
    assert reply.status_code == 404 and reply.json() == admin.get("/api/admin/users/nobody@example.test").json()
    assert audit(served) == []


def test_when_the_audit_log_cannot_be_written_the_change_is_not_made(served, monkeypatch):
    admin = served.login(ADMIN, confirmed=True)

    class Broken:
        def password_confirmed(self, *args):
            return True

        def append(self, entry):
            raise AdminUnavailable("storage")

    monkeypatch.setattr(served.app, "admin_record", Broken())
    reply = allowance(admin)
    assert reply.status_code == 503 and reply.json()["detail"] == "The audit record could not be written, so nothing was changed."
    assert granted(served, ADVOCATE) is None


def test_when_the_change_itself_fails_the_log_says_it_was_not_made(served, monkeypatch):
    admin = served.login(ADMIN, confirmed=True)

    class Refusing:
        def grant(self, *args, **kwargs):
            raise ValueError("the store would not take it")

    monkeypatch.setattr(served.app, "usage", Refusing())
    reply = allowance(admin)
    assert reply.status_code == 503 and "Nothing was changed" in reply.json()["detail"]
    assert [row[4] for row in audit(served)] == ["started", "not made"]


def test_when_only_the_second_entry_cannot_be_written_the_change_stands_and_the_page_is_told_it_is_not_fully_audited(served, monkeypatch):
    admin = served.login(ADMIN, confirmed=True)
    real = served.app.admin_record

    class SecondFails:
        def __init__(self):
            self.written = 0

        def password_confirmed(self, *args):
            return real.password_confirmed(*args)

        def append(self, entry):
            self.written += 1
            if self.written > 1:
                raise AdminUnavailable("storage")
            return real.append(entry)

    monkeypatch.setattr(served.app, "admin_record", SecondFails())
    reply = allowance(admin)
    assert reply.status_code == 200 and reply.json()["audited"] is False
    assert [e.outcome for e in real.entries(limit=50)] == ["started"] and granted(served, ADVOCATE).granted == TRIAL + 5_000_000


# ------------------------------------------------------------------------------ sessions ---

def test_ending_sessions_ends_every_live_one_of_the_account_and_says_how_many(served):
    advocate_a, advocate_b = served.login(ADVOCATE), served.login(ADVOCATE)
    admin = served.login(ADMIN, confirmed=True)
    reply = admin.post(f"/api/admin/users/{ADVOCATE}/end-sessions", json={"reason": "Lost laptop"})
    assert reply.status_code == 200 and reply.json()["sessions_ended"] == 2
    assert advocate_a.get("/api/session").status_code == 401 and advocate_b.get("/api/session").status_code == 401
    assert [row[1:] for row in audit(served)][-1] == ("sessions end", ADVOCATE, "Lost laptop", "done")


def test_an_admin_ending_their_own_sessions_keeps_the_one_they_are_using(served):
    mine, elsewhere = served.login(ADMIN, confirmed=True), served.login(ADMIN)
    reply = mine.post(f"/api/admin/users/{ADMIN}/end-sessions", json={"reason": "Tidying up"})
    assert reply.status_code == 200 and reply.json()["sessions_ended"] == 1
    assert mine.get("/api/session").status_code == 200 and elsewhere.get("/api/session").status_code == 401


# ------------------------------------------------------------------------------ suspension ---

def test_a_suspended_account_is_signed_out_and_shown_suspended_until_the_person_signs_in_again(served):
    advocate = served.login(ADVOCATE)
    admin = served.login(ADMIN, confirmed=True)
    reply = admin.post(f"/api/admin/users/{ADVOCATE}/suspend", json={"reason": "Chambers asked us to"})
    assert reply.status_code == 200 and reply.json() == {"suspended": True, "changed": True, "sessions_ended": 1, "audited": True}
    assert advocate.get("/api/session").status_code == 401
    assert admin.get(f"/api/admin/users/{ADVOCATE}").json()["status"] == "suspended"


def test_signing_in_again_ends_the_suspension_by_itself_with_no_message_and_a_wrong_password_does_not(served):
    admin = served.login(ADMIN, confirmed=True)
    admin.post(f"/api/admin/users/{ADVOCATE}/suspend", json={"reason": "pending a check"})
    wrong = TestClient(served.asgi).post("/api/login", headers={"origin": "http://testserver"},
                                         json={"advocate_id": ADVOCATE, "password": "not the password"})
    assert wrong.status_code == 401 and admin.get(f"/api/admin/users/{ADVOCATE}").json()["status"] == "suspended"
    again = served.login(ADVOCATE)  # the right password: in, and nothing is said about a suspension
    assert again.get("/api/session").status_code == 200
    assert admin.get(f"/api/admin/users/{ADVOCATE}").json()["status"] == "active"
    assert "suspension lifted by sign-in" in (served.tmp_path / "auth.log").read_text(encoding="utf8")


def test_suspending_again_changes_nothing_and_says_so(served):
    admin = served.login(ADMIN, confirmed=True)
    admin.post(f"/api/admin/users/{ADVOCATE}/suspend", json={"reason": "first"})
    again = admin.post(f"/api/admin/users/{ADVOCATE}/suspend", json={"reason": "second"})
    assert again.status_code == 200 and again.json()["changed"] is False


def test_reinstating_sooner_shows_the_account_active_and_matters_were_never_touched(served):
    admin = served.login(ADMIN, confirmed=True)
    admin.post(f"/api/admin/users/{ADVOCATE}/suspend", json={"reason": "pending a check"})
    reply = admin.post(f"/api/admin/users/{ADVOCATE}/reinstate", json={"reason": "Check done"})
    assert reply.status_code == 200 and reply.json()["suspended"] is False and reply.json()["changed"] is True
    again = served.login(ADVOCATE)
    assert again.get("/api/session").status_code == 200
    assert admin.get(f"/api/admin/users/{ADVOCATE}").json()["status"] == "active"
    assert [row[1] for row in audit(served)] == ["suspend", "suspend", "reinstate", "reinstate"]


def test_an_admin_account_cannot_be_suspended_from_here_because_the_settings_name_it(served):
    admin = served.login(ADMIN, confirmed=True)
    for target in (ADMIN, VIEWER):
        reply = admin.post(f"/api/admin/users/{target}/suspend", json={"reason": "no"})
        assert reply.status_code == 409 and "Admins are not suspended from here" in reply.json()["detail"]
    assert audit(served) == [] and admin.get("/api/session").status_code == 200


def test_suspending_an_account_whose_record_will_not_open_is_refused_and_leaves_it_alone(served):
    admin = served.login(ADMIN, confirmed=True)
    from nm.arrive.admin_directory import AdminFileDirectory
    target = AdminFileDirectory(served.tmp_path, key=KEY)._advocate_path(OTHER)
    assert target.exists()
    target.write_bytes(b"\x00 not a record")
    reply = admin.post(f"/api/admin/users/{OTHER}/suspend", json={"reason": "x"})
    assert reply.status_code in (404, 409)
    assert target.read_bytes() == b"\x00 not a record"
