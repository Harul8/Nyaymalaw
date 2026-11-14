"""A server killed in the middle of a save leaves no lock behind (plan AN.50, piece 50a; D187; the review's F-08).

The lock of a matter's save was the lock file's existence, made by an exclusive create and removed after the save: a process
killed between the two left the file, and every later save of that matter waited its ten seconds and was refused, until someone
removed the file by hand. The lock is now the operating system's, on the lock file, the mechanism the account claim uses: the
death of its holder lets it go. A live holder still makes a save wait and then refuses it, as before. Offline: a temporary store
and invented matters; the killed save is a second process that exits while it holds the lock.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from nm.shared import store_file_store
from nm.shared.store_file_store import FileMatterStore, claim
from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import Matter

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parent.parent
KEY = "killed-save-control-" + "k" * 24

#: A save that holds its matter's lock and is killed before it lets it go.
KILLED = """
import os
import sys
from nm.shared.store_file_store import FileMatterStore
store = FileMatterStore(sys.argv[1], key=sys.argv[2])
with store._locked(sys.argv[3]):
    os._exit(0)
"""


def saved(tmp_path):
    store = FileMatterStore(tmp_path / "store", key=KEY)
    return store, store.commit(Matter(id="matter-1", advocate_id="adv", title="First"), expected_version=0)


def test_a_lock_file_left_behind_does_not_block_the_next_save(tmp_path):
    """The file the earlier lock left after a kill holds nothing now: the next save goes through at once."""
    store, matter = saved(tmp_path)
    (tmp_path / "store" / "matters" / "matter-1.lock").write_text("pid=999 at=1.000")
    started = time.monotonic()
    store.commit(replace(matter, title="Second"), expected_version=matter.version)
    assert time.monotonic() - started < store_file_store._LOCK_TIMEOUT / 2, "it did not wait for the lock"
    assert store.load("matter-1").title == "Second"


def test_a_save_killed_while_it_holds_the_lock_leaves_the_matter_saveable(tmp_path):
    store, matter = saved(tmp_path)
    subprocess.run([sys.executable, "-c", KILLED, str(tmp_path / "store"), KEY, "matter-1"], cwd=ROOT, check=True, timeout=120)
    assert (tmp_path / "store" / "matters" / "matter-1.lock").exists(), "the killed save's lock file is still there"
    store.commit(replace(matter, title="After the kill"), expected_version=matter.version)
    assert store.load("matter-1").title == "After the kill"


def test_a_live_holder_still_makes_a_save_wait_and_then_refuses_it(tmp_path, monkeypatch):
    store, matter = saved(tmp_path)
    monkeypatch.setattr(store_file_store, "_LOCK_TIMEOUT", 0.3)
    held = claim(tmp_path / "store" / "matters" / "matter-1.lock")
    assert held is not None
    try:
        assert claim(tmp_path / "store" / "matters" / "matter-1.lock") is None, "a second claim is refused while one is held"
        started = time.monotonic()
        with pytest.raises(StaleWrite, match="being written by another turn"):
            store.commit(replace(matter, title="Must wait"), expected_version=matter.version)
        assert time.monotonic() - started >= 0.3
        assert store.load("matter-1").title == "First"
    finally:
        held.release()
    store.commit(replace(matter, title="Once free"), expected_version=matter.version)
    assert store.load("matter-1").title == "Once free"


def test_claims_racing_for_a_new_lock_file_leave_exactly_one_holder_and_none_fails(tmp_path):
    """Measured 13 Nov 2026: a first byte written by each new claimant fell, on Windows, inside the other's lock and was refused
    with an error - two password resets at once. Nothing is written now; the lock lies beyond the end of the empty file."""
    for round_ in range(40):
        path = tmp_path / f"race-{round_}.lock"
        got, failed = _race(path, claim)
        assert not failed, failed
        assert sum(held is not None for held in got) == 1
        assert path.read_bytes() == b"", "nothing is written to a lock file"


def test_a_failure_to_open_the_lock_file_is_raised_as_itself_and_never_taken_for_another_holder(tmp_path):
    with pytest.raises(OSError) as raised:
        claim(tmp_path / "no-such-folder" / "matter-1.lock")
    assert isinstance(raised.value, FileNotFoundError)


def _race(path, claiming):
    """Four claimants at once for one new lock file: what each got, and the errors any of them met."""
    start, done, got, failed = threading.Barrier(4), threading.Barrier(4), [], []

    def take():
        start.wait()
        try:
            held = claiming(path)
        except OSError as exc:  # the defect: a racing claimant's error
            failed.append(exc)
            held = None
        got.append(held)
        done.wait()
        if held is not None:
            held.release()
    threads = [threading.Thread(target=take) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return got, failed


def test_the_race_sees_a_claimant_that_fails(tmp_path):
    """The positive control (plan AN.54, D227, 14 Nov 2026): a claimant that errors is reported, so 'none fails' can fail."""
    asked = []

    def one_fails(path):
        asked.append(path)
        if len(asked) == 2:
            raise PermissionError("planted")
        return claim(path)
    got, failed = _race(tmp_path / "planted.lock", one_fails)
    assert [type(exc) for exc in failed] == [PermissionError] and sum(held is not None for held in got) == 1
