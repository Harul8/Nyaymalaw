"""The rename that puts a saved file in its place, run on Linux with the operating system's own calls (plan AN.50, piece 50h1;
D194; the review's F-36).

50h1's tests exercise the half of `publish` that runs outside Windows with the operating system's calls stood in for, and its
record says that half had not been run on Linux - the hosting machine (D176) is Linux. Here a real store on this machine saves a
matter and its history line, and every file the store puts in place is followed, through the real calls, by a flush of the
folder that holds its name, made after the rename (the finished file is gone from beside it) and succeeding. The spies only
record and call through. What this cannot show is that the file system keeps its promise across a real power loss: that is the
file system's, on the hosted machine's own disk.

Offline: a temporary store and an invented matter; Linux only.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from nm.shared import store_file_store
from nm.shared.store_file_store import FileMatterStore
from nm.work_the_file.matter_contracts import Matter

pytestmark = [pytest.mark.class_a,
              pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the half of publish that runs on Linux, run there")]
KEY = "publishing-rename-on-linux-" + "k" * 24


@pytest.fixture
def followed(monkeypatch):
    """Every publish of the store, and every flush, in order, through the real calls."""
    seen = []
    real_publish, real_fsync = store_file_store.publish, os.fsync

    def publishing(finished, path):
        seen.append(("publish", Path(path), Path(finished)))
        return real_publish(finished, path)

    def flushing(fd):
        kind = "folder" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
        where = Path(os.readlink(f"/proc/self/fd/{fd}"))
        # Which finished files, of those handed to publish so far, are still beside their names (not yet renamed).
        waiting = {entry[2] for entry in seen if entry[0] == "publish" and entry[2].exists()} if kind == "folder" else set()
        real_fsync(fd)  # raises as the real call does
        seen.append(("flush", kind, where, waiting))
    monkeypatch.setattr(store_file_store, "publish", publishing)
    monkeypatch.setattr(os, "fsync", flushing)
    return seen


def test_each_file_a_save_puts_in_place_is_followed_by_a_real_flush_of_its_folder(tmp_path, followed):
    store = FileMatterStore(tmp_path / "store", key=KEY)
    store.commit(Matter(id="matter-1", advocate_id="adv", title="First", version=1), expected_version=0)
    store.commit(Matter(id="matter-1", advocate_id="adv", title="Second", version=2), expected_version=1)
    signature = store.signature("matter-1")
    store.keep_line("matter-1", signature, {"chat": {"chat_id": "c1", "preview": "p", "title": "Second", "turn_count": 1}})
    published = [(index, entry[1], entry[2]) for index, entry in enumerate(followed) if entry[0] == "publish"]
    assert len(published) >= 3, "the store put its files in place through publish: two saves and a history line"
    for index, path, finished in published:
        flushed = next((entry for entry in followed[index + 1:] if entry[0] == "flush" and entry[1] == "folder"), None)
        assert flushed is not None and flushed[2] == path.parent.resolve(), f"{path.name}: its folder flushed after the rename"
        assert finished not in flushed[3], f"{path.name}: the finished file had already been put in place when the folder was flushed"
        assert not finished.exists() and path.exists()
    assert store.load("matter-1").title == "Second"
    assert store.kept_line("matter-1", signature)["chat"]["title"] == "Second"


def test_the_flush_is_of_the_real_folder_and_lets_it_go(tmp_path, monkeypatch):
    """No folder is left open: each one opened to be flushed is closed again (the count of this process's open files)."""
    store = FileMatterStore(tmp_path / "store", key=KEY)
    before = len(os.listdir("/proc/self/fd"))
    for version in range(1, 21):
        store.commit(Matter(id="matter-1", advocate_id="adv", title=f"T{version}", version=version), expected_version=version - 1)
    assert len(os.listdir("/proc/self/fd")) <= before + 1, "twenty saves leave no folder open"
