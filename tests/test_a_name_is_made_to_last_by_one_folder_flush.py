"""A name given in a folder is made to last by one folder flush (plan AN.50, 50h1 and its sweep; D194, the review's F-36).

A file's bytes are flushed by its writer, but the name it is given - by a rename, or by a link that gives it a name only where none
is taken - is the folder's, and until the folder is flushed it can be gone after a power loss. publish (nm/shared/
store_file_store.py) flushed its folder itself; three exclusive creations by link flushed none (AN.50, recorded 15 Nov 2026). The
flush now has one owner beside the removal of a name, nm/shared/names_contracts.py, below every store that gives names, so the
sealer, which the matter store imports, can use it too; publish uses it. Windows offers no way to flush a folder.

Offline: a temporary folder; the operating system's calls stood in for where the platform cannot run them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from nm.shared import names_contracts, store_file_store
from nm.shared.names_contracts import flush_folder

pytestmark = pytest.mark.class_a
linux = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the real calls, where they can run")


def _stood_in(monkeypatch, calls, *, refuse=False):
    def flushing(fd):
        calls.append(("flush", fd))
        if refuse:
            raise OSError("the folder refused")
    monkeypatch.setattr(names_contracts.os, "open", lambda path, flags: calls.append(("open", Path(path), flags)) or 7)
    monkeypatch.setattr(names_contracts.os, "fsync", flushing)
    monkeypatch.setattr(names_contracts.os, "close", lambda fd: calls.append(("close", fd)))


def test_the_folder_is_opened_flushed_and_let_go(tmp_path, monkeypatch):
    calls = []
    _stood_in(monkeypatch, calls)
    try:
        assert flush_folder(tmp_path, windows=False) is True
    finally:
        monkeypatch.undo()
    assert calls == [("open", tmp_path, os.O_RDONLY), ("flush", 7), ("close", 7)]


def test_a_folder_that_cannot_be_flushed_is_said_and_still_let_go(tmp_path, monkeypatch):
    calls = []
    _stood_in(monkeypatch, calls, refuse=True)
    try:
        with pytest.raises(OSError):
            flush_folder(tmp_path, windows=False)
    finally:
        monkeypatch.undo()
    assert calls[-1] == ("close", 7)


def test_on_windows_nothing_is_asked_of_the_folder(tmp_path, monkeypatch):
    calls = []
    _stood_in(monkeypatch, calls)
    try:
        assert flush_folder(tmp_path, windows=True) is False
    finally:
        monkeypatch.undo()
    assert calls == []


@linux
def test_on_linux_the_real_folder_is_flushed_and_nothing_is_left_open(tmp_path):
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(20):
        assert flush_folder(tmp_path) is True
    assert len(os.listdir("/proc/self/fd")) <= before + 1


def test_publish_flushes_its_folder_by_it(tmp_path, monkeypatch):
    old, new = tmp_path / "kept.json", tmp_path / "kept.json.tmp"
    old.write_text("old", encoding="utf8")
    new.write_text("new", encoding="utf8")
    seen = []
    monkeypatch.setattr(store_file_store, "_WINDOWS", False)
    monkeypatch.setattr(store_file_store, "flush_folder",
                        lambda folder, *, windows=None: seen.append((Path(folder), windows, old.read_text(encoding="utf8"))))
    store_file_store.publish(new, old)
    assert seen == [(tmp_path, False, "new")], "its folder, flushed once the new file is under its name"
