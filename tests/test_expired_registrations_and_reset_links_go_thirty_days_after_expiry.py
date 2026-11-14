"""A pending registration and a password-reset link are kept at most thirty days after they expire (plan AN.53, D241's retention:
the directory's sweep).

D241: 'a pending registration or a reset link, 30 days after it expires'. Each was removed only when the next of its kind was
asked for - an expired registration when someone next registered, an expired link when someone next asked for one - and with
nobody asking, never: a registration holds the name, address and enrolment of someone who never became an account. Now the
directory's one sweep removes every one that expired thirty days or more ago, whoever asks for what. The earlier clean-up is left
as it was. A link whose record cannot be read has an expiry that cannot be known, and is kept. Nothing asks for the sweep yet (the
daily sweep is the next piece).

Offline: a directory in a temporary folder and stand-in moments; no model call, no mail sent; the people are invented.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from nm.arrive.account_confirmation_contracts import PENDING_HOURS
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol, registration_consent, utcnow
from nm.arrive.store_directory import EXPIRED_KEPT_DAYS, FileDirectory
from tests.registration import CONSENT
from tests.test_core_served import served  # noqa: F401 - served is a fixture
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a

PASSWORD = "Synthetic-password-42!"
NOW = utcnow()


def _enrolment(email, at):
    consent = registration_consent(CONSENT["notice_version"], True, True, at)
    return Enrolment(AdvocateIdentity(id=email, name=email, email=email), enrol(PASSWORD), at, consent)


def _pending(directory):
    with sqlite3.connect(directory._root / "pending-accounts.sqlite3") as db:
        return db.execute("SELECT count(*) FROM pending").fetchone()[0]


def _begun(directory, email, expired_days_ago):
    """A registration begun so that it expired that many days before NOW (negative: still waiting)."""
    at = NOW - timedelta(days=expired_days_ago) - timedelta(hours=PENDING_HOURS)
    directory.begin_pending_registration(_enrolment(email, at), at)


def test_a_registration_that_expired_thirty_days_ago_goes_and_the_rest_wait(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    # The youngest first: beginning one clears those already expired at that moment, as it always did.
    _begun(directory, "waiting@example.test", -1)
    _begun(directory, "lately-expired@example.test", EXPIRED_KEPT_DAYS - 1)
    _begun(directory, "long-expired@example.test", EXPIRED_KEPT_DAYS + 1)
    assert _pending(directory) == 3
    assert directory.sweep_expired(NOW) == {"registrations": 1, "resets": 0, "sign_ins": 0}
    assert _pending(directory) == 2
    assert directory.sweep_expired(NOW) == {"registrations": 0, "resets": 0, "sign_ins": 0}, "a second sweep finds nothing more"


def test_where_no_registration_was_ever_held_nothing_is_made(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    assert directory.sweep_expired(NOW) == {"registrations": 0, "resets": 0, "sign_ins": 0}
    assert not (tmp_path / "pending-accounts.sqlite3").exists()


def _links(directory):
    return sorted(path.name for path in directory._resets.glob("*.nm"))


def test_a_reset_link_that_expired_thirty_days_ago_goes_and_the_rest_are_kept(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    for email in ("young@example.test", "old@example.test", "live@example.test"):
        directory.enrol(_enrolment(email, NOW - timedelta(days=400)))
    # The youngest first: asking for one clears those already expired at that moment, as it always did.
    assert directory.issue_password_reset("live@example.test", NOW)
    assert directory.issue_password_reset("young@example.test", NOW - timedelta(days=EXPIRED_KEPT_DAYS - 1))
    assert directory.issue_password_reset("old@example.test", NOW - timedelta(days=EXPIRED_KEPT_DAYS + 1))
    before = _links(directory)
    assert len(before) == 3
    assert directory.sweep_expired(NOW) == {"registrations": 0, "resets": 1, "sign_ins": 0}
    assert len(_links(directory)) == 2


def test_a_link_whose_record_cannot_be_read_is_kept(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    (directory._resets / ("0" * 64 + ".nm")).write_bytes(b"damaged beyond reading")
    assert directory.sweep_expired(NOW + timedelta(days=3650))["resets"] == 0
    assert _links(directory) == ["0" * 64 + ".nm"]


def test_the_directory_port_declares_the_sweep_so_the_policed_wrapper_gates_it():
    from nm.arrive.directory_port import DirectoryPort
    from nm.shared.policed_port_adapter import port_methods
    assert "sweep_expired" in port_methods(DirectoryPort)


# ---------------------------------------------------------------------------- swept daily (53h4b2) ---

def test_the_daily_sweep_removes_them_from_the_served_directory(served, capsys):
    from nm.app import main
    _begun(served.app.directory, "long-expired@example.test", EXPIRED_KEPT_DAYS + 1)
    main._sweep_expired(served.app, NOW)
    said = capsys.readouterr().err
    assert f"1 registration(s) and 0 password-reset link(s) expired {EXPIRED_KEPT_DAYS} days ago or more were removed." in said
    assert "long-expired" not in said, "counts, never a name"
    main._sweep_expired(served.app, NOW)
    assert capsys.readouterr().err == "", "nothing more to say"


def test_a_directory_that_cannot_be_swept_is_said_and_tried_again(served, monkeypatch, capsys):
    from nm.app import main

    def refuses(now):
        raise PermissionError("the folder refuses")
    monkeypatch.setattr(served.app.directory, "sweep_expired", refuses)
    main._sweep_expired(served.app, NOW)
    assert "Expired registrations and reset links could not be swept (PermissionError)." in capsys.readouterr().err


def test_the_daily_loop_sweeps_them_after_the_papers():
    import inspect

    from nm.app import main
    loop = inspect.getsource(main._keep_deleted)
    assert loop.index("_sweep_unsent_papers(application, now)") < loop.index("_sweep_expired(application, now)")
