"""A staged batch's record is put in its place by the one publish (plan AN.50, 50h1's sweep; D194, the review's F-36).

The Admin staging (plan AN.46, 46m) keeps each batch's state in batch.json, rewritten when it is checked and when it is approved. It
renamed its own temporary file into place, without flushing it first, and a write that failed left the temporary behind. It is now
written whole, flushed, and put in place by the publish every store of this codebase uses - on Windows a reader is waited for a
bounded moment, and elsewhere the folder is flushed after the rename - and a temporary is never left beside the record.

Offline: a staging folder in a temporary directory; the reading job is not run; no model call.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

from nm.arrive import admin_staging
from nm.arrive.admin_port import AdminUnavailable
from nm.arrive.admin_staging import AdminStaging

pytestmark = pytest.mark.class_a
BATCH = "0123456789ab"


@pytest.fixture
def staging(tmp_path):
    kept = AdminStaging(tmp_path / "staging", root=tmp_path, held=lambda: set())
    kept._path(BATCH).mkdir(parents=True)
    return kept


def _batch(state):
    return {"id": BATCH, "created_at": "2026-11-15T09:00:00+00:00", "jurisdiction": "Telangana", "staged": [], "acts": [],
            "state": state, "problem": ""}


def test_the_record_is_flushed_then_put_in_place_by_publish(staging, monkeypatch):
    seen = []
    real_publish, real_fsync = admin_staging.publish, os.fsync

    def publishing(finished, path):
        seen.append(("publish", Path(path), Path(finished).read_text(encoding="utf8")))
        return real_publish(finished, path)

    def flushing(fd):
        seen.append(("flush",))
        return real_fsync(fd)
    monkeypatch.setattr(admin_staging, "publish", publishing)
    monkeypatch.setattr(admin_staging.os, "fsync", flushing)
    staging._save(_batch("checked"))
    staging._save(_batch("approved"))
    published = [entry for entry in seen if entry[0] == "publish"]
    assert [entry[1] for entry in published] == [staging._path(BATCH) / "batch.json"] * 2
    assert all('"state": "' in entry[2] for entry in published), "the whole record, written before it is put in place"
    first = seen.index(published[0])
    assert ("flush",) in seen[:first], "the record's own bytes flushed before the rename"
    assert staging._load(BATCH)["state"] == "approved"


def test_a_record_that_cannot_be_put_in_place_is_said_and_leaves_no_temporary(staging, monkeypatch):
    staging._save(_batch("checked"))

    def refusing(finished, path):
        raise PermissionError("held by a reader past the bound")
    monkeypatch.setattr(admin_staging, "publish", refusing)
    with pytest.raises(AdminUnavailable):
        staging._save(_batch("approved"))
    assert sorted(p.name for p in staging._path(BATCH).iterdir()) == ["batch.json"], "no temporary left beside it"
    assert staging._load(BATCH)["state"] == "checked", "the record as it was"


def test_no_rename_of_its_own_is_left():
    assert "os.replace(" not in inspect.getsource(admin_staging)
