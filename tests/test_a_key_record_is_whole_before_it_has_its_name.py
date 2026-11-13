"""A matter's key record never exists half-written (plan AN.50, piece 50h2; D194, its Low item).

The record was created under its name and then written, so a process that ended between the two left an empty record: every
later use of that matter's identifier waited and was refused, and no new key may be made over a record that exists. It is now
written and flushed beside its name and given the name in one step that fails where the name is taken. An empty record left by
an earlier crash is still refused and never replaced here: a key made over a record that once opened something would lose it.
Offline: temporary key folders and invented matters; the process that ends is a second process.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from nm.shared import store_sealing
from nm.shared.store_envelope import WrappedKeyUnreadable
from nm.shared.store_sealing import MatterSealer

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parent.parent
KEY = "whole-key-record-control-" + "k" * 24

#: A start that ends at the very step that would give the finished record its name.
ENDED = """
import os
import sys
from nm.shared.store_sealing import MatterSealer
os.link = lambda *_: os._exit(0)
MatterSealer(sys.argv[2], sys.argv[1]).matter_key("matter-1")
"""


def works(sealer):
    return sealer.open("matter-1", sealer.seal("matter-1", b"what was sealed")) == b"what was sealed"


def test_a_start_that_ends_while_the_record_is_being_made_does_not_block_the_identifier(tmp_path, monkeypatch):
    sealer = MatterSealer(KEY, tmp_path / "keys")

    class Ended(BaseException):
        """The process ends here."""

    def ending(*_, **__):
        raise Ended
    monkeypatch.setattr(store_sealing.json, "dumps", ending)
    with pytest.raises(Ended):
        sealer.matter_key("matter-1")
    monkeypatch.undo()
    assert not (tmp_path / "keys" / "matter-1.key").exists(), "no record under the name, so nothing to wait for"
    monkeypatch.setattr(store_sealing, "KEY_RECORD_TIMEOUT", 0.3)
    assert works(sealer)


def test_a_process_killed_before_the_record_has_its_name_leaves_the_identifier_free(tmp_path):
    keys = tmp_path / "keys"
    subprocess.run([sys.executable, "-c", ENDED, str(keys), KEY], cwd=ROOT, check=True, timeout=120)
    assert not (keys / "matter-1.key").exists()
    left = [path.name for path in keys.iterdir()]
    assert len(left) == 1 and left[0].endswith(".new"), "the finished record, never named, is all the killed start left"
    sealer = MatterSealer(KEY, keys)
    assert works(sealer), "and it is never taken for the matter's key"
    assert json.loads((keys / "matter-1.key").read_bytes())["matter_id"] == "matter-1"


def test_the_record_is_complete_at_the_moment_it_gets_its_name(tmp_path, monkeypatch):
    seen = []
    real = store_sealing.os.link

    def linking(source, target):
        seen.append(json.loads(Path(source).read_bytes()))
        return real(source, target)
    monkeypatch.setattr(store_sealing.os, "link", linking)
    MatterSealer(KEY, tmp_path / "keys").matter_key("matter-1")
    monkeypatch.undo()
    assert len(seen) == 1 and seen[0]["matter_id"] == "matter-1"
    assert [path.name for path in (tmp_path / "keys").iterdir()] == ["matter-1.key"], "nothing is left beside it"


def test_of_many_starts_making_the_same_matters_key_one_wins_and_the_rest_read_it(tmp_path):
    keys, together, made, failed = tmp_path / "keys", threading.Barrier(8), [], []

    def make():
        try:
            together.wait(10)
            made.append(MatterSealer(KEY, keys).matter_key("matter-1")[1])
        except Exception as exc:  # noqa: BLE001 - reported below
            failed.append(exc)
    starts = [threading.Thread(target=make) for _ in range(8)]
    for each in starts:
        each.start()
    for each in starts:
        each.join(30)
    assert not failed and len(made) == 8 and len(set(made)) == 1, "one data key, whoever asked"
    assert [path.name for path in keys.iterdir()] == ["matter-1.key"]


def test_a_folder_that_gives_a_file_no_second_name_still_makes_the_record_once(tmp_path, monkeypatch):
    def refusing(source, target):
        raise OSError("this folder gives a file no second name")
    monkeypatch.setattr(store_sealing.os, "link", refusing)
    first = MatterSealer(KEY, tmp_path / "keys").matter_key("matter-1")[1]
    second = MatterSealer(KEY, tmp_path / "keys").matter_key("matter-1")[1]
    monkeypatch.undo()
    assert first == second and [path.name for path in (tmp_path / "keys").iterdir()] == ["matter-1.key"]


def test_an_empty_record_left_by_an_earlier_crash_is_refused_and_never_replaced(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "matter-1.key").write_bytes(b"")
    monkeypatch.setattr(store_sealing, "KEY_RECORD_TIMEOUT", 0.2)
    with pytest.raises(WrappedKeyUnreadable, match="never deleted here"):
        MatterSealer(KEY, keys).matter_key("matter-1")
    assert (keys / "matter-1.key").read_bytes() == b"", "no key is made over a record that exists"
