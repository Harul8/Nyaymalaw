"""The outgoing-data log's compressed day is flushed, put in place by the one publish, and only then is its plain day removed (plan
AN.50, 50h1's sweep; D194, the review's F-36; D169, the log kept a year).

The daily sweep compresses each day of the log over ninety days old: a compressed copy is written beside the day, read back and
compared, renamed into place, and the plain day deleted. The copy was renamed without its bytes being flushed, and the folder was
not flushed after: a power loss soon after the plain day was deleted could leave the kept record of that day empty or gone. The
copy's bytes are now flushed, it is put in place by the publish every store here uses (the folder flushed after the rename), and
only then does the plain day go. A copy that cannot be put in place leaves the day as it was, and nothing beside it.

Offline: a log folder in a temporary directory, with synthetic lines; no model call.
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path

import pytest

from nm.shared import egress_log_store as store
from nm.shared.egress_log_store import EgressLog
from tests.test_the_outgoing_data_log_is_kept_a_year import TODAY, day_file, half_made, names

pytestmark = pytest.mark.class_a


def _named(fd):
    try:
        return Path(os.readlink(f"/proc/self/fd/{fd}")).name
    except OSError:  # no /proc here: which file was flushed is not known, only that one was
        return None


def test_the_copy_is_flushed_put_in_place_by_publish_and_only_then_the_plain_day_goes(tmp_path, monkeypatch):
    path, body = day_file(tmp_path, 120)
    seen = []
    real_publish, real_fsync = store.publish, os.fsync

    def publishing(finished, target):
        seen.append(("publish", Path(target), path.exists()))
        return real_publish(finished, target)

    def flushing(fd):
        seen.append(("flush", _named(fd)))
        return real_fsync(fd)
    monkeypatch.setattr(store, "publish", publishing)
    monkeypatch.setattr(store.os, "fsync", flushing)
    assert EgressLog(tmp_path).sweep(TODAY)["compressed"] == 1
    published = [entry for entry in seen if entry[0] == "publish"]
    assert [(entry[1].name, entry[2]) for entry in published] == [(path.name + ".gz", True)], (
        "the copy put in place by publish while the plain day is still there")
    before = seen[:seen.index(published[0])]
    assert any(entry[0] == "flush" and (entry[1] is None or entry[1].endswith(".part")) for entry in before), (
        "the copy's own bytes flushed before it is put in place")
    assert not path.exists() and gzip.decompress(path.with_name(path.name + ".gz").read_bytes()) == body
    assert not half_made(tmp_path)


def test_a_copy_that_cannot_be_put_in_place_leaves_the_day_as_it_was(tmp_path, monkeypatch, caplog):
    path, body = day_file(tmp_path, 120)

    def refusing(finished, target):
        raise PermissionError("held by a reader past the bound")
    monkeypatch.setattr(store, "publish", refusing)
    assert EgressLog(tmp_path).sweep(TODAY)["compressed"] == 0
    assert path.read_bytes() == body and names(tmp_path) == [path.name], "the plain day, and nothing beside it"
    assert "could not be compressed" in caplog.text
