"""An account's record, and what hangs from it in the directory, go when an Admin closes the account (plan AN.53, 53h7a; D241's
closed account, with D246's safeguards).

The directory keeps, for an account: its record (its identity, its credential, its settings - the AI permission and the dictation
setting among them), each of its sign-ins with its files of use and owner, a draft key for each device it signed in from, and any
password-reset link of its still waiting. Closing removes all of them, the record last, under the directory's own claim on the
account (the one sign-in and every change hold), so a closure cannot cross a sign-in. Only a suspended account is closed (D246:
two steps, the first undone by Reinstate); one whose record cannot be read, or that is not there, is refused; a sign-in of its
that cannot be read refuses the closure, nothing removed, since what it holds cannot be known. Another account is untouched.

Offline: a directory in a temporary folder; no model call; the people are invented.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from nm.arrive.admin_directory import AdminFileDirectory
from nm.arrive.admin_port import AdminAccountsPort, AdminChangeRefused, AdminUnavailable
from nm.arrive.store_directory import FileDirectory
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from tests.test_the_admin_directory_lists_what_an_admin_may_see_and_changes_nothing import KEY, NOW, PASSWORD


def account(directory, who):
    directory.enrol(Enrolment(AdvocateIdentity(who, who.split("@")[0], email=who), enrol(PASSWORD), NOW - timedelta(days=30)))
    return who

pytestmark = pytest.mark.class_a
CLOSED, KEPT = "closing@example.test", "staying@example.test"


@pytest.fixture
def directory(tmp_path):
    return FileDirectory(tmp_path, key=KEY)


@pytest.fixture
def admin(tmp_path, directory):
    return AdminFileDirectory(tmp_path, key=KEY)


def _files(root, *names):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
                  and any(name in p.read_bytes().decode("latin-1") or name in p.name for name in names))


def _all(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def _used(directory, who):
    """An account with two sign-ins from two devices, a draft key for each, and a reset link waiting."""
    for device in ("laptop", "phone"):
        token = directory.open_session(who, device, NOW - timedelta(minutes=30))
        directory.touch_session(token, device, NOW - timedelta(minutes=10))
        directory.device_draft_key(who, device)
    assert directory.issue_password_reset(who, NOW - timedelta(minutes=5))


def test_closing_is_on_the_admin_accounts_port():
    assert "close" in vars(AdminAccountsPort)


def test_a_suspended_account_is_closed_its_record_last_and_everything_that_hangs_from_it_with_it(tmp_path, directory, admin):
    account(directory, CLOSED)
    account(directory, KEPT)
    _used(directory, CLOSED)
    _used(directory, KEPT)
    kept_before = {path for path in _all(tmp_path) if KEPT in path}
    admin.set_suspended(CLOSED, True, NOW)
    others_before = len(admin.sessions_for(KEPT))
    said = admin.close(CLOSED, NOW)
    assert said == {"sign_ins": 2, "draft_keys": 2, "reset_links": 1}
    assert not directory._advocate_path(CLOSED).exists(), "the account record is gone (a suspended one's identity is None anyway)"
    assert admin.sessions_for(CLOSED) == (), "and every sign-in of it"
    assert len(list((tmp_path / "draft-keys").glob("*.nm"))) == 2, "the other account's two draft keys stay"
    assert len(list((tmp_path / "password-resets").glob("*.nm"))) == 1, "the other account's reset link stays"
    assert directory.identity(KEPT) is not None and len(admin.sessions_for(KEPT)) == others_before
    assert {path for path in _all(tmp_path) if KEPT in path} == kept_before


def test_an_account_not_suspended_is_refused_and_nothing_goes(tmp_path, directory, admin):
    account(directory, CLOSED)
    _used(directory, CLOSED)
    before = _all(tmp_path)
    with pytest.raises(AdminChangeRefused) as refused:
        admin.close(CLOSED, NOW)
    assert refused.value.status == 409 and "Suspend" in refused.value.detail
    assert _all(tmp_path) == before


def test_an_account_that_is_not_there_is_refused(directory, admin):
    with pytest.raises(AdminChangeRefused) as refused:
        admin.close("nobody@example.test", NOW)
    assert refused.value.status == 404


def test_an_account_whose_record_cannot_be_read_is_refused(tmp_path, directory, admin):
    account(directory, CLOSED)
    admin.set_suspended(CLOSED, True, NOW)
    directory._advocate_path(CLOSED).write_bytes(b"not an account record")
    with pytest.raises(AdminChangeRefused) as refused:
        admin.close(CLOSED, NOW)
    assert refused.value.status == 409


def test_a_sign_in_that_cannot_be_read_refuses_the_closure_and_nothing_goes(tmp_path, directory, admin):
    account(directory, CLOSED)
    _used(directory, CLOSED)
    admin.set_suspended(CLOSED, True, NOW)
    session = next((tmp_path / "sessions").glob("*.nm"))
    session.write_bytes(b"not a sign-in")
    before = _all(tmp_path)
    with pytest.raises(AdminUnavailable):
        admin.close(CLOSED, NOW)
    assert _all(tmp_path) == before and directory._advocate_path(CLOSED).exists(), "nothing gone, the record kept"


def test_a_closure_made_again_after_it_finished_finds_no_account(directory, admin):
    account(directory, CLOSED)
    admin.set_suspended(CLOSED, True, NOW)
    admin.close(CLOSED, NOW)
    with pytest.raises(AdminChangeRefused) as refused:
        admin.close(CLOSED, NOW)
    assert refused.value.status == 404
