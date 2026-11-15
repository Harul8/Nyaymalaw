"""The account store puts each finished file in its place by the one publish (plan AN.50, 50h1's sweep; D194, the review's F-36).

50h1 gave the matter store one function that puts a finished file in its place: on Windows it waits a bounded moment for a reader
to let go, and elsewhere it flushes the folder after the rename, so the name a save is published under survives a power loss. The
account store kept four renames of its own, of the same shape, recorded as its next piece: the account record (its credential,
its suspension, its settings), a reset link marked used, a sign-in's last activity, and the mark of a sign-in's owner. Each now
goes through publish; the restoring of a claimed invitation's name is not a finished file put in place and keeps its rename.

Offline: a directory in a temporary folder; the people are invented; no model call.
"""
from __future__ import annotations

import inspect
from datetime import timedelta
from pathlib import Path

import pytest

from nm.arrive import store_directory
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.store_directory import FileDirectory
from tests.test_the_admin_directory_lists_what_an_admin_may_see_and_changes_nothing import KEY, NOW, PASSWORD

pytestmark = pytest.mark.class_a
WHO = "publishing@example.test"


@pytest.fixture
def published(monkeypatch):
    """Each path the account store hands to publish, in order; the real publish is still what puts it in place."""
    seen = []
    real = store_directory.publish

    def recording(finished, path):
        seen.append(Path(path))
        return real(finished, path)
    monkeypatch.setattr(store_directory, "publish", recording)
    return seen


def test_each_finished_file_of_an_account_is_put_in_place_by_publish(tmp_path, published):
    directory = FileDirectory(tmp_path, key=KEY)
    directory.enrol(Enrolment(AdvocateIdentity(WHO, "Publishing", email=WHO), enrol(PASSWORD), NOW - timedelta(days=3)))
    token = directory.open_session(WHO, "laptop", NOW - timedelta(minutes=30))
    assert directory.touch_session(token, "laptop", NOW - timedelta(minutes=10)) is not None
    link = directory.issue_password_reset(WHO, NOW - timedelta(minutes=5))
    assert link and directory.reset_password(link, enrol("Another-long-Password-1"), NOW).success
    where = {(path.parent.name, path.suffix) for path in published}
    assert ("advocates", directory._advocate_path(WHO).suffix) in where, "the account record"
    assert ("password-resets", ".nm") in where, "the reset link, marked used"
    assert any(name == "sessions" and suffix == ".active" for name, suffix in where), "a sign-in's last activity"
    assert any(name == "sessions" and suffix == ".owner" for name, suffix in where), "the mark of a sign-in's owner"
    assert not list(tmp_path.rglob("*.tmp")), "no finished file left beside its name"


def test_no_rename_of_its_own_is_left_but_the_restoring_of_a_claimed_invitation():
    source = inspect.getsource(store_directory)
    renames = [line.strip() for line in source.splitlines() if "os.replace(" in line and not line.strip().startswith("#")]
    assert renames == ["os.replace(used, active)"], renames
