"""TWO TURNS ON ONE MATTER: one wins and one is TOLD. Reviewer finding #3.

WHAT WAS TRUE BEFORE
----------------------
`FileMatterStore.commit` read the current matter, compared its version,
encrypted, and replaced. `os.replace` makes the SWAP atomic, so a crash
mid-write leaves the previous file intact -- which the existing comment claims
and which is true. It says nothing about two writers.

Two turns both load version N. Both find the version check satisfied. Both
encrypt. The second `os.replace` wins and the first turn's work is gone, with
no error raised anywhere and nothing in the metrics. For a product whose whole
premise is that a matter ACCUMULATES -- facts, chronology, theory, deadlines
-- a silent lost update is the quietest way to be wrong.

THE COMPARISON WAS ALSO WRONG, and it is the smaller half nobody would have
found by thinking about locks. It read `current.version > expected_version`.
A writer holding a stale HIGHER version -- from a restored file, a rolled-back
matter, a bug -- satisfied that check and overwrote a newer one. `!=` is the
only comparison that asks the question that matters: is the file still what
this turn read?

WHAT THIS TEST IS, AND WHAT IT IS NOT
---------------------------------------
It is a real concurrency test: two threads, one matter, the same
`expected_version`, run against the real store on a real directory. It is not
a proof of serialisability, and the lock it exercises is not a substitute for
a transactional store -- that remains the right long-run answer and is a
migration. What this refuses is the LOST UPDATE, which is live today.
"""
from __future__ import annotations

import pathlib
import tempfile
import threading
from dataclasses import replace

import pytest
from nm.adapters.store.file_store import FileMatterStore
from nm.domain.matter import Matter
from nm.ports.store import StaleWrite

pytestmark = pytest.mark.class_a

#: A key of the shape the store requires. Not a secret: this store is created
#: inside a temp directory and destroyed with it.
KEY = "x" * 43 + "="


def _store(root: pathlib.Path) -> FileMatterStore:
    return FileMatterStore(root, key=KEY)


def _seeded(root: pathlib.Path):
    store = _store(root)
    matter = Matter.create(advocate_id="adv", title="file")
    store.commit(matter, expected_version=matter.version)
    return store, store.load(matter.id)


def test_two_writers_at_one_version_do_not_both_win():
    """THE INVARIANT. Exactly one commits; the other is refused and knows."""
    with tempfile.TemporaryDirectory() as d:
        store, base = _seeded(pathlib.Path(d))

        results: list[tuple[str, str]] = []
        barrier = threading.Barrier(2)

        def write(tag: str) -> None:
            # BOTH THREADS READ, THEN BOTH WRITE. The barrier makes the
            # interleaving the defect needs actually happen, rather than
            # hoping the scheduler produces it.
            barrier.wait()
            try:
                store.commit(
                    replace(base, version=base.version + 1, title=tag),
                    expected_version=base.version)
                results.append(("committed", tag))
            except StaleWrite:
                results.append(("refused", tag))

        threads = [threading.Thread(target=write, args=(t,)) for t in ("A", "B")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        committed = [tag for kind, tag in results if kind == "committed"]
        assert len(results) == 2, f"a writer neither committed nor was refused: {results}"
        assert len(committed) == 1, (
            f"both writers committed, so one turn's work was discarded with "
            f"no error and nothing in the metrics: {results}")


def test_the_loser_is_told_which_matter_and_why():
    """A REFUSAL NOBODY CAN ACT ON IS A CRASH WITH BETTER MANNERS.

    The turn that loses has to re-derive, and it can only do that if it knows
    the file moved rather than that something went wrong.
    """
    with tempfile.TemporaryDirectory() as d:
        store, base = _seeded(pathlib.Path(d))
        store.commit(replace(base, version=base.version + 1, title="first"),
                     expected_version=base.version)

        with pytest.raises(StaleWrite) as caught:
            store.commit(replace(base, version=base.version + 1, title="second"),
                         expected_version=base.version)
        said = str(caught.value)
        assert base.id in said, f"the refusal does not name the matter: {said}"
        assert "re-derive" in said.lower(), (
            f"the refusal does not say what to do about it: {said}")


def test_a_stale_higher_version_cannot_overwrite_a_newer_matter():
    """THE COMPARISON, and the half a lock does not fix.

    `current.version > expected_version` let a writer holding a HIGHER stale
    version through -- from a restored file or a rolled-back matter -- and it
    then overwrote something newer. The only safe question is whether the file
    is still what this turn read.
    """
    with tempfile.TemporaryDirectory() as d:
        store, base = _seeded(pathlib.Path(d))
        store.commit(replace(base, version=7, title="on disk"),
                     expected_version=base.version)

        # This writer believes the file is at 9. It is at 7. Under `>` the
        # check passed, because 7 is not greater than 9.
        with pytest.raises(StaleWrite):
            store.commit(replace(base, version=10, title="clobber"),
                         expected_version=9)

        assert store.load(base.id).title == "on disk", (
            "a writer holding a stale higher version overwrote a newer matter")


def test_an_ordinary_sequential_commit_is_unaffected():
    """POSITIVE CONTROL IN THE OTHER DIRECTION. A lock that refused ordinary
    work would be worse than the defect: every turn on every matter goes
    through this path."""
    with tempfile.TemporaryDirectory() as d:
        store, base = _seeded(pathlib.Path(d))
        current = base
        for n in range(5):
            current = store.commit(
                replace(current, version=current.version + 1, title=f"turn {n}"),
                expected_version=current.version)
        assert store.load(base.id).title == "turn 4"


def test_the_lock_is_released_when_a_commit_raises():
    """A LOCK HELD BY A FAILED COMMIT WOULD STALL THE MATTER FOREVER, and it
    would look exactly like the product hanging."""
    with tempfile.TemporaryDirectory() as d:
        store, base = _seeded(pathlib.Path(d))
        with pytest.raises(StaleWrite):
            store.commit(replace(base, version=99), expected_version=42)
        # If the lock leaked, this blocks for the timeout and then raises.
        store.commit(replace(base, version=base.version + 1, title="after"),
                     expected_version=base.version)
        assert store.load(base.id).title == "after"
