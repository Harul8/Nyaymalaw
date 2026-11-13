"""The restore drill (plan AN.50, piece 50e3; D191; the review's F-13: "No test restores a store").

The backup the hosting guide describes, rehearsed: with nothing alive on the store its whole folder is copied; work goes on; the
folder is lost; the copy is put back whole. Every conversation, account setting and step answer then opens as the backup left it,
what was made after the backup is gone and said to be absent rather than damaged, and work goes on from there. Where only some
files are put back from the older copy, the conversations saved since are refused as older copies (50e) and the rest still
open. Offline: a temporary store, invented matters and an invented account.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone

import pytest

from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.arrive.store_directory import FileDirectory
from nm.shared.step_share_store import FileStepShare
from nm.shared.store_file_store import FileMatterStore, RolledBack, _Cipher, alive_on, rekeying
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a

KEY = "restore-drill-control-" + "k" * 24
WHO = "restore-drill@example.test"


def save(root, matter_id, title, version):
    return FileMatterStore(root, key=KEY).commit(
        Matter(id=matter_id, advocate_id=WHO, title=title, version=version), expected_version=version - 1)


def setting(root):
    return FileDirectory(root, key=KEY).dictation_setting(WHO)


@pytest.fixture
def backed_up(tmp_path):
    """A store with two conversations, an account's setting and a step's answer; its whole folder copied while nothing was alive
    on it; and then the work done after the copy: one conversation saved again, a new one begun, the setting changed."""
    root, backup = tmp_path / "store", tmp_path / "backup"
    save(root, "mat_00000000", "the first, as backed up", 1)
    save(root, "mat_00000001", "the second, as backed up", 1)
    directory = FileDirectory(root, key=KEY)
    directory.enrol(Enrolment(AdvocateIdentity(WHO, WHO), enrol("Synthetic-fixture-password-72!")))
    directory.record_dictation_setting(WHO, live=True, expected_version=0, now=datetime.now(timezone.utc))
    share = FileStepShare(root / "step-share.sqlite", _Cipher(KEY))
    step = share.ask(WHO, "turn-1", {"words": "A step handed to the worker."})
    share.answer(step, {"status": 200, "body": {"words": "Its answer."}})
    del share, directory

    # Stop, then copy: nothing is alive on the store and no key rotation has it.
    assert alive_on(root) == [] and not rekeying(root)
    shutil.copytree(root, backup)

    save(root, "mat_00000000", "the first, saved after the backup", 2)
    save(root, "mat_00000002", "begun after the backup", 1)
    FileDirectory(root, key=KEY).record_dictation_setting(WHO, live=False, expected_version=1, now=datetime.now(timezone.utc))
    return root, backup, step


def test_a_store_put_back_whole_opens_as_the_backup_left_it_and_work_goes_on(backed_up):
    root, backup, step = backed_up
    shutil.rmtree(root)  # the folder is lost
    shutil.copytree(backup, root)  # and put back whole

    store = FileMatterStore(root, key=KEY)
    assert store.load("mat_00000000").title == "the first, as backed up"
    assert store.load("mat_00000001").title == "the second, as backed up"
    assert store.load("mat_00000002") is None, "what was begun after the backup is absent, not damaged"
    listed = store.list_for(WHO)
    assert listed.unreadable == () and sorted(m.title for m in listed) == ["the first, as backed up", "the second, as backed up"]
    assert setting(root)["live"] is True, "the account is as it was at the backup: a change made after it is to be made again"
    assert FileStepShare(root / "step-share.sqlite", _Cipher(KEY)).answered(step)["body"]["words"] == "Its answer."

    # Work goes on from the restored state.
    save(root, "mat_00000000", "the first, saved after the restore", 2)
    assert FileMatterStore(root, key=KEY).load("mat_00000000").title == "the first, saved after the restore"


def test_a_backup_does_not_open_without_its_key(backed_up):
    _, backup, _ = backed_up
    with pytest.raises(Exception):  # noqa: B017, PT011 - any refusal: a backup without its key is not readable
        FileMatterStore(backup, key="another-key-" + "x" * 30).load("mat_00000000")


def test_only_the_conversations_put_back_from_the_older_copy_are_refused_and_the_rest_still_open(backed_up):
    root, backup, _ = backed_up
    for path in (backup / "matters").glob("*.nm"):  # some files put back, the rest of the folder left as it is
        shutil.copy2(path, root / "matters" / path.name)

    store = FileMatterStore(root, key=KEY)
    with pytest.raises(RolledBack):
        store.load("mat_00000000")
    assert store.load("mat_00000001").title == "the second, as backed up", "not saved since the backup: the same file"
    assert store.load("mat_00000002").title == "begun after the backup"
    listed = store.list_for(WHO)
    assert listed.unreadable == ("mat_00000000",) and len(listed.matters) == 2

    # The operator means the older copy: the server stopped, that conversation's record removed.
    (root / "saved-versions" / "mat_00000000.json").unlink()
    assert FileMatterStore(root, key=KEY).load("mat_00000000").title == "the first, as backed up"
