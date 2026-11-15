"""Each file given its name by an exclusive link has its folder flushed once named (plan AN.50: the deferral recorded on 15 Nov
2026, built; D194, the review's F-36).

Three files are made whole beside their name and then given it by a link, which names a file only where no file has that name:
the sealer's key record for a matter, an account's record at enrolment, and a SQLite file's creation. Their bytes were flushed
first, but not their folder, so the name could be gone after a power loss - for a key record, with every matter sealed under it
then unreadable. Each now flushes its folder by the one folder flush (nm/shared/names_contracts.py), once the name is given; a
file already there gives no new name and asks nothing.

Offline: temporary folders; the people are invented; no model call.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nm.arrive import store_directory
from nm.arrive.advocate_contracts import AdvocateIdentity, Enrolment, enrol
from nm.shared import sqlite_creation, store_sealing

pytestmark = pytest.mark.class_a
SEAL = "exclusive-link-flush-control-" + "k" * 24
WHO, PASSWORD = "lasting@example.test", "A-long-Synthetic-passw0rd"


def _following(monkeypatch, module):
    """Each folder `module` flushes, in order; the real flush is still what runs."""
    seen = []
    real = module.flush_folder

    def flushing(folder, **kwargs):
        seen.append(Path(folder))
        return real(folder, **kwargs)
    monkeypatch.setattr(module, "flush_folder", flushing)
    return seen


def test_a_new_key_record_has_its_folder_flushed_once_named(tmp_path, monkeypatch):
    seen = _following(monkeypatch, store_sealing)
    keys = tmp_path / "keys"
    store_sealing.MatterSealer(SEAL, keys).matter_key("matter-1")
    assert seen == [keys] and (keys / "matter-1.key").exists()
    seen.clear()
    store_sealing.MatterSealer(SEAL, keys).matter_key("matter-1")
    assert seen == [], "a key already made gives no new name"


def test_an_account_enrolled_has_its_folder_flushed_once_named(tmp_path, monkeypatch):
    seen = _following(monkeypatch, store_directory)
    directory = store_directory.FileDirectory(tmp_path, key=SEAL)
    directory.enrol(Enrolment(AdvocateIdentity(WHO, "Lasting", email=WHO), enrol(PASSWORD),
                              datetime(2026, 11, 15, tzinfo=timezone.utc)))
    record = directory._advocate_path(WHO)
    assert record.exists() and record.parent in seen


def test_a_new_sqlite_file_has_its_folder_flushed_once_named(tmp_path, monkeypatch):
    seen = _following(monkeypatch, sqlite_creation)
    path = tmp_path / "made.sqlite"
    sqlite_creation.create_if_absent(path, lambda db: db.execute("CREATE TABLE kept (x)"))
    assert seen == [tmp_path] and path.exists()
    seen.clear()
    sqlite_creation.create_if_absent(path, lambda db: db.execute("CREATE TABLE kept (x)"))
    assert seen == [], "a file already there is left as it is"
