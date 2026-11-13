"""What is alive on a store is known, and a crash leaves nothing that says alive (plan AN.50, piece 50d1; D190; the review's F-01).

The key rotation must refuse while a server or worker is alive on the store, and a server or worker must refuse to start while a
rotation has the store to itself. Each server and worker holds an operating-system lock on a file of its own in the store's
`alive` folder for its life; the operating system lets go of it when the process ends, however it ends. A file nobody holds was
left by a process that ended, and is removed when next looked at. Offline: temporary folders and second processes.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from nm.shared.store_file_store import ALIVE, REKEYING, alive_on, claim, hold_alive, rekeying

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parent.parent

#: A worker that marks itself alive, says so, and waits to be ended.
LIVING = """
import sys
from nm.shared.store_file_store import hold_alive
held = hold_alive(sys.argv[1], "worker")
print("alive", flush=True)
sys.stdin.read()
"""

#: A server that marks itself alive and is killed before it lets go.
KILLED = """
import os
import sys
from nm.shared.store_file_store import hold_alive
held = hold_alive(sys.argv[1], "server")
os._exit(0)
"""


def test_a_mark_is_seen_while_it_is_held_and_gone_once_it_is_let_go(tmp_path):
    held = hold_alive(tmp_path, "server")
    (seen,) = alive_on(tmp_path)
    assert seen.startswith("server-")
    held.release()
    assert alive_on(tmp_path) == [] and list((tmp_path / ALIVE).iterdir()) == [], "the file it left is removed"


def test_a_process_killed_while_alive_leaves_nothing_that_says_alive(tmp_path):
    subprocess.run([sys.executable, "-c", KILLED, str(tmp_path)], cwd=ROOT, check=True, timeout=120)
    assert len(list((tmp_path / ALIVE).glob("*.lock"))) == 1, "the killed server's file is still there"
    assert alive_on(tmp_path) == []
    assert list((tmp_path / ALIVE).glob("*.lock")) == []


def test_another_process_alive_on_the_store_is_seen_until_it_ends(tmp_path):
    living = subprocess.Popen([sys.executable, "-c", LIVING, str(tmp_path)], cwd=ROOT, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True)
    try:
        assert living.stdout.readline().strip() == "alive"
        (seen,) = alive_on(tmp_path)
        assert seen.startswith("worker-")
        assert alive_on(tmp_path) == [seen], "looking does not take its mark away"
    finally:
        living.stdin.close()
        living.wait(timeout=120)
    assert alive_on(tmp_path) == []


def test_a_rotation_holding_the_store_is_known_and_a_store_never_rotated_is_not_rotating(tmp_path):
    assert not rekeying(tmp_path)
    held = claim(tmp_path / REKEYING)
    assert rekeying(tmp_path), "a rotation that holds the store is known"
    held.release()
    assert not rekeying(tmp_path), "one that ended is not"


def test_what_is_alive_is_named_by_one_word(tmp_path):
    with pytest.raises(ValueError):
        hold_alive(tmp_path, "../elsewhere")
