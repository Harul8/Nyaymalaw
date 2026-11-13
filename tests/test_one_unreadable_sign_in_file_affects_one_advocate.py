"""One sign-in file that cannot be read affects one advocate (plan AN.53, 53c2, D218; the review's F-28).

Whose a sign-in is was known only by reading its file. So every listing of one advocate's sign-ins read every
advocate's files, and one file that could not be read had no owner: it refused 'where am I signed in', 'sign out
everywhere' and - since a reset ends every earlier sign-in - the password reset of every advocate, each of whose
links was then spent on a reset that could not finish. The directory now keeps, beside each sign-in file, a record
of its owner (a hash, no address). Another's file is passed over without being read; a file of the advocate's own
that cannot be read still makes their list incomplete, and is ENDED, not skipped, when they sign out everywhere or
reset their password; and a file nobody is recorded as owning still refuses, as it did.
"""
from __future__ import annotations

import pytest

from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol, token_fingerprint, utcnow
from nm.arrive.directory_port import SessionsUnavailable
from nm.arrive.store_directory import FileDirectory

pytestmark = pytest.mark.class_a

KEY = "sign-in-owner-control-" + "k" * 24
FIRST, SECOND = "first@example.com", "second@example.com"
PASSWORD, NEW_PASSWORD = "Cinder-lantern-42", "Harbour-meadow-17!"


@pytest.fixture
def two(tmp_path):
    """Two enrolled advocates, each signed in once: (directory, the first's token, the second's token)."""
    directory = FileDirectory(tmp_path, key=KEY)
    for who in (FIRST, SECOND):
        directory.enrol(Enrolment(AdvocateIdentity(id=who, name=who, email=who), enrol(PASSWORD), utcnow()))
    return directory, directory.open_session(FIRST, "device-1", utcnow()), directory.open_session(SECOND, "device-2", utcnow())


def _file(directory, token):
    return directory._sessions / f"{token_fingerprint(token)}.nm"


def _damage(directory, token):
    _file(directory, token).write_bytes(b"not a sign-in record")


def test_anothers_damaged_sign_in_does_not_stop_ones_own_list_or_sign_out(two):
    directory, first, second = two
    _damage(directory, first)
    assert [s.token_fingerprint for s in directory.sessions_for(SECOND)] == [token_fingerprint(second)]
    assert directory.close_all_sessions(SECOND, "signed out everywhere") == 1
    assert directory.session(second, "device-2", utcnow()) is None


def test_anothers_damaged_sign_in_does_not_stop_ones_password_reset(two):
    directory, first, second = two
    _damage(directory, first)
    link = directory.issue_password_reset(SECOND, utcnow())
    result = directory.reset_password(link, enrol(NEW_PASSWORD), utcnow())
    assert result.success and result.sessions_ended == 1
    assert directory.authenticate(SECOND, NEW_PASSWORD) is not None
    assert directory.session(second, "device-2", utcnow()) is None, "the reset ended the earlier sign-in"


def test_ones_own_damaged_sign_in_still_makes_ones_list_incomplete(two):
    directory, first, _second = two
    _damage(directory, first)
    with pytest.raises(SessionsUnavailable):
        directory.sessions_for(FIRST)


def test_ones_own_damaged_sign_in_is_ended_not_skipped_when_one_signs_out_everywhere_or_resets(two):
    directory, first, _second = two
    other = directory.open_session(FIRST, "device-3", utcnow())
    _damage(directory, first)
    link = directory.issue_password_reset(FIRST, utcnow())
    result = directory.reset_password(link, enrol(NEW_PASSWORD), utcnow())
    assert result.success and result.sessions_ended == 2, "the readable one, and the one that could not be read"
    for token, device in ((first, "device-1"), (other, "device-3")):
        assert directory.session(token, device, utcnow()) is None
    ended = {s.token_fingerprint: s.ended_because for s in directory.sessions_for(FIRST)}
    assert ended == {token_fingerprint(first): "password reset", token_fingerprint(other): "password reset"}, (
        "the list is whole again, and says both were ended")


def test_anothers_sign_in_file_is_not_read_for_ones_list(two, monkeypatch):
    directory, first, second = two
    read, real = [], directory._read_session
    monkeypatch.setattr(directory, "_read_session", lambda fingerprint: (read.append(fingerprint), real(fingerprint))[1])
    assert len(directory.sessions_for(SECOND)) == 1
    assert read == [token_fingerprint(second)]


def test_the_owner_record_holds_no_address_and_a_fresh_process_reads_it(two, tmp_path):
    directory, first, second = two
    record = (directory._sessions / f"{token_fingerprint(first)}.owner").read_bytes()
    assert FIRST.encode() not in record and b"example" not in record
    _damage(directory, first)
    assert len(FileDirectory(tmp_path, key=KEY).sessions_for(SECOND)) == 1


def test_a_sign_in_from_before_there_were_owner_records_is_recorded_when_it_is_first_listed(two):
    directory, first, second = two
    for token in (first, second):
        _file(directory, token).with_suffix(".owner").unlink()
    assert len(directory.sessions_for(SECOND)) == 1, "with no record, the file itself says whose it is"
    assert all(_file(directory, token).with_suffix(".owner").exists() for token in (first, second))
    _damage(directory, first)
    assert len(directory.sessions_for(SECOND)) == 1


def test_a_damaged_sign_in_nobody_is_recorded_as_owning_still_refuses_as_it_did(two):
    """The limit that remains, pinned: such a file may be anyone's sign-in, so nobody's list is called whole and nobody's
    'every sign-in ended' is claimed. Every sign-in opened since this piece has its owner's record."""
    directory, first, second = two
    _file(directory, first).with_suffix(".owner").unlink()
    _damage(directory, first)
    for who in (FIRST, SECOND):
        with pytest.raises(SessionsUnavailable):
            directory.sessions_for(who)
        with pytest.raises(SessionsUnavailable):
            directory.close_all_sessions(who, "signed out everywhere")


def test_a_sign_in_whose_owner_record_could_not_be_written_is_still_a_sign_in(tmp_path, monkeypatch):
    directory = FileDirectory(tmp_path, key=KEY)
    directory.enrol(Enrolment(AdvocateIdentity(id=FIRST, name=FIRST, email=FIRST), enrol(PASSWORD), utcnow()))
    monkeypatch.setattr(directory, "_session_owner_path", lambda fingerprint: tmp_path / "advocates" / "no" / "such" / "x")
    token = directory.open_session(FIRST, "device-1", utcnow())
    assert directory.session(token, "device-1", utcnow()) is not None
    assert len(directory.sessions_for(FIRST)) == 1
