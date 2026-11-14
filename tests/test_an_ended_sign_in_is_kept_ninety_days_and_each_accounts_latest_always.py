"""A sign-in is kept ninety days after it ends, and each account's latest whatever its age (plan AN.53, D241 and D245: the
directory's sweep of what has expired).

D245: a sign-in's record holds the account, the device, a label of the browser and the address it came from, with files of its own
for when it was last used and whose it is. It was kept for ever - ENDED, NOT DELETED, so that a sign-out can be told from a forged
token. Now the directory's sweep removes each sign-in whose expiry is ninety days or more past, with its files of use and owner; but
each account's most recent sign-in is kept whatever its age, so that the Admin area's last sign-in stays true. One whose record
cannot be read is kept.

Offline: a directory in a temporary folder and stand-in moments; no model call; the people are invented.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol, token_fingerprint, utcnow
from nm.arrive.store_directory import ENDED_SIGN_INS_KEPT_DAYS, FileDirectory
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a

NOW = utcnow()
ONE, TWO = "one@example.test", "two@example.test"


def _directory(root):
    directory = FileDirectory(root, KEY)
    for who in (ONE, TWO):
        directory.enrol(Enrolment(AdvocateIdentity(id=who, name=who, email=who), enrol("Synthetic-password-42!")))
    return directory


def _signed_in(directory, who, days_ago):
    token = directory.open_session(who, "laptop", NOW - timedelta(days=days_ago))
    return token_fingerprint(token)


def _files(directory, fingerprint):
    return sorted(path.name for path in directory._sessions.glob(f"{fingerprint}.*"))


def test_an_old_sign_in_goes_with_its_files_and_the_accounts_latest_and_a_recent_one_stay(tmp_path):
    directory = _directory(tmp_path)
    old = _signed_in(directory, ONE, ENDED_SIGN_INS_KEPT_DAYS + 30)
    older_still = _signed_in(directory, ONE, ENDED_SIGN_INS_KEPT_DAYS + 60)
    recent = _signed_in(directory, ONE, 10)
    assert {".nm", ".owner"} <= {name[len(old):] for name in _files(directory, old)}
    assert directory.sweep_expired(NOW)["sign_ins"] == 2
    assert _files(directory, old) == [] and _files(directory, older_still) == [], "its record and its files of use and owner"
    assert _files(directory, recent), "a sign-in that ended within ninety days is kept"
    assert directory.sweep_expired(NOW)["sign_ins"] == 0, "a second sweep finds nothing more"


def test_each_accounts_latest_sign_in_is_kept_however_old_so_its_last_sign_in_stays_true(tmp_path):
    directory = _directory(tmp_path)
    only = _signed_in(directory, TWO, 400)
    before = _signed_in(directory, ONE, 500)
    latest = _signed_in(directory, ONE, 300)
    assert directory.sweep_expired(NOW)["sign_ins"] == 1
    assert _files(directory, only) and _files(directory, latest) and _files(directory, before) == []
    issued = [session.issued_at for session in directory.sessions_for(ONE)]
    assert issued and max(issued) <= NOW - timedelta(days=299), "the latest sign-in is still there to be said"


def test_a_sign_in_whose_record_cannot_be_read_is_kept(tmp_path):
    directory = _directory(tmp_path)
    old = _signed_in(directory, ONE, ENDED_SIGN_INS_KEPT_DAYS + 30)
    _signed_in(directory, ONE, 5)
    (directory._sessions / f"{old}.nm").write_bytes(b"damaged beyond reading")
    assert directory.sweep_expired(NOW)["sign_ins"] == 0
    assert _files(directory, old)


def test_a_signed_out_sign_in_is_kept_ninety_days_from_its_expiry_not_less(tmp_path):
    directory = _directory(tmp_path)
    token = directory.open_session(ONE, "laptop", NOW - timedelta(days=ENDED_SIGN_INS_KEPT_DAYS - 1))
    directory.close_session(token, "signed out")
    _signed_in(directory, ONE, 1)
    assert directory.sweep_expired(NOW)["sign_ins"] == 0, "ended within ninety days: kept"


def test_where_nobody_ever_signed_in_nothing_is_swept(tmp_path):
    assert FileDirectory(tmp_path, KEY).sweep_expired(NOW)["sign_ins"] == 0
