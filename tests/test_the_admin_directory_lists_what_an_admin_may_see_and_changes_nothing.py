"""The Admin area's listing of accounts (plan AN.46, piece 46d; owner decisions D118-D119, 7 Nov 2026).

Every account in one pass, with the fields an admin may see and no others; nothing on disk is changed by looking; an account or
part that will not open is shown as unknown, never as absent. Synthetic accounts, written through the directory's own methods."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from nm.arrive.admin_directory import SESSIONS_SHOWN, AdminFileDirectory
from nm.arrive.advocate_contracts import (PRIVACY_NOTICE_VERSION, AdvocateIdentity, Enrolment, enrol,
                                          registration_consent)
from nm.arrive.store_directory import FileDirectory
from nm.shared.external_ai_contracts import NOTICE_VERSION, ModelPermission

pytestmark = pytest.mark.class_a

KEY = "Synthetic-admin-directory-key-61"
PASSWORD = "Synthetic-fixture-password-72!"
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
REVIEWER = "reviewer@example.test"


@pytest.fixture
def directory(tmp_path):
    return FileDirectory(tmp_path, key=KEY)


@pytest.fixture
def admin(tmp_path, directory):
    return AdminFileDirectory(tmp_path, key=KEY)


def account(directory, who, *, name=None, enrolment="", firm=""):
    directory.enrol(Enrolment(AdvocateIdentity(who, name or who.split("@")[0], enrolment=enrolment, firm_id=firm),
                              enrol(PASSWORD), NOW - timedelta(days=30)))
    return who


def share(directory, who, accepted=True):
    directory.record_model_permission(ModelPermission(who, NOTICE_VERSION, accepted, NOW - timedelta(days=5), 1),
                                      expected_version=0)


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_each_account_is_listed_once_with_the_fields_an_admin_may_see(directory, admin):
    account(directory, "meera@example.test", name="Meera Iyer", enrolment="D/1234/2015", firm="chambers-1")
    account(directory, "anita@example.test", name="Anita Rao")
    share(directory, "meera@example.test")
    token = directory.open_session("meera@example.test", "device-1", NOW - timedelta(minutes=40), client_label="Chrome on Windows")
    directory.touch_session(token, "device-1", NOW - timedelta(minutes=15))
    listing = admin.listing(NOW)
    assert [a.id for a in listing.accounts] == ["anita@example.test", "meera@example.test"]
    anita, meera = listing.accounts
    assert meera.readable and (meera.name, meera.enrolment, meera.firm_id) == ("Meera Iyer", "D/1234/2015", "chambers-1")
    assert meera.created_at == NOW - timedelta(days=30)
    assert (meera.ai_sharing, meera.ai_notice_version) == (True, NOTICE_VERSION)
    assert meera.last_sign_in == NOW - timedelta(minutes=40) and meera.last_active == NOW - timedelta(minutes=15)
    assert [(s.client_label, s.live) for s in meera.sessions] == [("Chrome on Windows", True)]
    assert (anita.ai_sharing, anita.ai_notice_version) == (False, None)
    assert anita.sessions == () and anita.last_sign_in is None and not anita.suspended


def test_a_session_that_has_ended_is_listed_as_not_live_and_only_the_newest_are_shown(directory, admin):
    account(directory, "busy@example.test")
    tokens = [directory.open_session("busy@example.test", f"d{n}", NOW - timedelta(minutes=n + 1)) for n in range(SESSIONS_SHOWN + 5)]
    directory.close_session(tokens[0], "signed out")
    shown = admin.listing(NOW).accounts[0].sessions
    assert len(shown) == SESSIONS_SHOWN
    assert [s.issued_at for s in shown] == sorted((s.issued_at for s in shown), reverse=True)
    assert not shown[0].live and all(s.live for s in shown[1:])


def test_looking_changes_nothing_on_disk_not_even_the_migration_a_sign_in_does_to_an_older_sealed_record(tmp_path, directory, admin):
    who = account(directory, "legacy@example.test")
    account(directory, "plain@example.test")
    path = directory._advocate_path(who)
    path.write_bytes(directory._cipher.encrypt(path.read_bytes()))  # an account sealed before the credential was left in the open
    directory.open_session("plain@example.test", "d", NOW)
    before = snapshot(tmp_path)
    listing = admin.listing(NOW)
    assert [a.id for a in listing.accounts] == ["legacy@example.test", "plain@example.test"]
    assert all(a.readable for a in listing.accounts)
    assert snapshot(tmp_path) == before


def test_an_account_that_will_not_open_is_listed_as_unreadable_and_the_others_are_unharmed(tmp_path, directory, admin):
    account(directory, "fine@example.test")
    (tmp_path / "advocates" / "broken@example.test.nm").write_bytes(b"\x00not an account at all")
    (tmp_path / "advocates" / ("invalid-" + "0" * 64 + ".nm")).write_bytes(b"x")
    (tmp_path / "advocates" / ".fine@example.test.nm.1a2b.tmp").write_bytes(b"half written")
    accounts = {a.id: a for a in admin.listing(NOW).accounts}
    assert set(accounts) == {"fine@example.test", "broken@example.test"}
    assert accounts["fine@example.test"].readable and not accounts["broken@example.test"].readable
    broken = accounts["broken@example.test"]
    assert (broken.name, broken.ai_sharing, broken.sessions) == ("", None, ())


def test_an_account_filed_under_another_name_is_not_adopted(tmp_path, directory, admin):
    account(directory, "real@example.test")
    source = directory._advocate_path("real@example.test")
    (tmp_path / "advocates" / "someone-else@example.test.nm").write_bytes(source.read_bytes())
    found = {a.id: a.readable for a in admin.listing(NOW).accounts}
    assert found == {"real@example.test": True, "someone-else@example.test": False}


def test_a_part_that_will_not_open_is_unknown_and_not_none(tmp_path, directory, admin):
    who = account(directory, "odd@example.test")
    path = directory._advocate_path(who)
    doc = json.loads(path.read_text())
    doc["model_permission"] = "not sealed text"
    path.write_text(json.dumps(doc))
    odd = admin.listing(NOW).accounts[0]
    assert odd.readable and odd.ai_sharing is None


def test_a_session_file_that_will_not_open_is_counted_so_the_page_can_say_the_sessions_may_be_incomplete(tmp_path, directory, admin):
    account(directory, "a@example.test")
    directory.open_session("a@example.test", "d", NOW)
    (tmp_path / "sessions" / ("f" * 64 + ".nm")).write_bytes(b"\x00damaged")
    listing = admin.listing(NOW)
    assert listing.unreadable_sessions == 1 and len(listing.accounts[0].sessions) == 1


def test_a_suspended_account_is_marked_and_an_account_without_the_mark_is_not(tmp_path, directory, admin):
    who = account(directory, "paused@example.test")
    account(directory, "active@example.test")
    path = directory._advocate_path(who)
    doc = json.loads(path.read_text())
    doc["suspended"] = {"by": "admin@example.test", "at": NOW.isoformat()}
    path.write_text(json.dumps(doc))
    assert {a.id: a.suspended for a in admin.listing(NOW).accounts} == {"active@example.test": False, "paused@example.test": True}


def test_an_email_waiting_to_be_confirmed_is_listed_apart_from_the_accounts(tmp_path, directory, admin):
    account(directory, "member@example.test")
    consent = registration_consent(PRIVACY_NOTICE_VERSION, True, True, NOW)
    for who in ("waiting@example.test", "later@example.test"):
        directory.begin_pending_registration(Enrolment(AdvocateIdentity(id=who, name=who, email=who), enrol(PASSWORD),
                                                       NOW - timedelta(hours=1 if who.startswith("w") else 2), consent),
                                             NOW - timedelta(hours=1 if who.startswith("w") else 2))
    listing = admin.listing(NOW)
    assert [a.id for a in listing.accounts] == ["member@example.test"]
    assert [w.email for w in listing.waiting] == ["later@example.test", "waiting@example.test"]
    assert listing.waiting_readable and all(w.expires_at > NOW for w in listing.waiting)
    assert admin.listing(NOW + timedelta(days=3)).waiting == ()


def test_a_waiting_list_that_will_not_open_is_unknown_and_not_empty(tmp_path, directory, admin):
    (tmp_path / "pending-accounts.sqlite3").write_bytes(b"not a database at all")
    listing = admin.listing(NOW)
    assert listing.waiting == () and not listing.waiting_readable


def test_nothing_secret_is_in_what_comes_back(tmp_path, directory, admin):
    who = account(directory, "secret@example.test")
    directory.open_session(who, "device-with-a-distinct-name", NOW)
    doc = json.loads(directory._advocate_path(who).read_text())
    shown = repr(admin.listing(NOW))
    for secret in (doc["credential"]["hash"], doc["credential"]["salt"], "device-with-a-distinct-name"):
        assert secret not in shown
    assert "token" not in shown and "fingerprint" not in shown


def test_the_listing_wants_a_time_with_its_zone(admin):
    with pytest.raises(ValueError):
        admin.listing(datetime(2026, 11, 7, 12, 0))
