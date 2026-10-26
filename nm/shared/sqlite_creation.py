"""A store file that is published whole or not at all (plan AN.24; owner decision O30).

THE DEFECT THIS CLOSES. The usage store and the turn-attempt store were made where they were meant to stay: the first caller
created an empty file and then built the tables inside it. A second caller arriving in that moment found a file that existed
and was empty - exactly what a damaged or emptied store looks like, which both stores refuse on purpose, so that usage and
turn ownership never start again from nothing in a store that was lost - and refused it. Measured on 26 Oct 2026: 12 of 600
callers were refused when four first uses arrived together ("the usage store has a schema it did not make"). It surfaced as a
503 "usage could not be checked" on the first turn of a new store about once in ten test runs.

THE INVARIANT. Nobody, at any moment, can find an empty or half-made file where the store is meant to be. The file is made
complete beside it and linked into place in one step that refuses to replace an existing file; the creator that loses uses the
winner's store and removes its own copy. A file that is there and is empty or foreign is still refused by the store that opens
it, as before: only this module ever makes one, and it never leaves one like that.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from nm.shared.names_contracts import discard


def create_if_absent(path: str | Path, build: Callable[[sqlite3.Connection], None]) -> None:
    """Make the SQLite file at `path`, complete, with `build(db)` inside one transaction - unless one is there already.

    A file that exists is left exactly as it is, and `build` is not called. If another caller publishes the file while this
    one is making its copy, the other's is the store and this copy is removed. A build that fails leaves nothing at `path`
    and nothing beside it."""
    path = Path(path)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".creating")
    os.close(handle)
    made = Path(name)
    try:
        with closing(sqlite3.connect(made, timeout=10)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            build(db)
        try:
            os.link(made, path)  # atomic, and it refuses to replace: one creator wins
        except FileExistsError:
            pass  # another caller published first; its store is the store
    finally:
        discard(made)


def why(error: BaseException) -> str:
    """What kind of fault this was, for a log: the error's class and, where there is one, SQLite's name for it or the
    operating system's number. Never its message, which can carry a path or a word of a matter."""
    parts = [type(error).__name__]
    name = getattr(error, "sqlite_errorname", None)
    if isinstance(name, str):
        parts.append(name)
    for label in ("errno", "winerror"):
        number = getattr(error, label, None)
        if isinstance(number, int):
            parts.append(f"{label} {number}")
    return " ".join(parts)
