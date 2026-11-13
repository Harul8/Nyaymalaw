"""What the web server and the step worker share, when the steps run in a worker process of their own (plan AN.48, piece 48f4;
owner decision D167, 10 Nov 2026).

One SQLite file beside the conversations. The steps the web server takes and what each answered; what the advocate asks of a step
at work - Stop, Steer, answers to NM's questions, what they type meanwhile - and the worker's verdict on each; NM's open questions as
the advocate's page reads them; each turn's progress (stage names, counts and times only, as nm.app.turn_progress keeps them); and
the worker's heartbeat. Everything that carries the advocate's words or NM's answer - a message, answers, a steer, a question asked,
an answer released, a refusal - is sealed under the installation's key, as conversations are; only identities, states and times are
plain. SQLite transactions follow the turn-attempt store's BEGIN IMMEDIATE pattern.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path

from nm.shared.sqlite_creation import create_if_absent, why

_log = logging.getLogger("nm.steps")

VERSION = 1
_TABLES = {
    "steps": """CREATE TABLE steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        advocate_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('new','taken','done')),
        asked BLOB NOT NULL,
        answered BLOB,
        at REAL NOT NULL
    )""",
    "controls": """CREATE TABLE controls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        advocate_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('stop','steer','answers','queued')),
        state TEXT NOT NULL CHECK(state IN ('new','done')),
        asked BLOB NOT NULL,
        answered BLOB,
        at REAL NOT NULL
    )""",
    "windows": """CREATE TABLE windows (
        advocate_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        view BLOB NOT NULL,
        at REAL NOT NULL,
        PRIMARY KEY (advocate_id, turn_id)
    )""",
    "progress": """CREATE TABLE progress (
        advocate_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        row TEXT NOT NULL,
        at REAL NOT NULL,
        PRIMARY KEY (advocate_id, turn_id)
    )""",
    "worker": """CREATE TABLE worker (
        name TEXT PRIMARY KEY NOT NULL,
        at REAL NOT NULL,
        waiting INTEGER NOT NULL,
        working INTEGER NOT NULL
    )""",
}


#: Plan AN.52 (52g): what stands in a request's answer while the worker has taken it and not yet answered. Not sealed: it
#: holds nothing.
_TAKING = b"taking"


class StepShareRefused(Exception):
    """The shared store could not be opened or holds something it did not make."""


class FileStepShare:
    """cipher: the installation's sealing (encrypt/decrypt bytes), as the conversation store uses it."""

    def __init__(self, path, cipher, *, clock=time.time):
        self.path, self._cipher, self._clock = Path(path).resolve(), cipher, clock
        try:
            create_if_absent(self.path, self._build)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
        except StepShareRefused:
            _log.warning("The shared step store holds something it did not make.")
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The shared step store could not be opened (%s).", why(exc))
            raise StepShareRefused("storage") from None

    @staticmethod
    def _build(db):
        for sql in _TABLES.values():
            db.execute(sql)
        db.execute(f"PRAGMA user_version={VERSION}")

    @staticmethod
    def _schema(db):
        found = {name: " ".join((sql or "").split()) for kind, name, sql in db.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall() if kind == "table"}
        if (db.execute("PRAGMA user_version").fetchone()[0] != VERSION
                or found != {name: " ".join(sql.split()) for name, sql in _TABLES.items()}):
            raise StepShareRefused("storage")

    @contextmanager
    def _transaction(self):
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                yield db
        except (OSError, sqlite3.Error) as exc:
            _log.warning("A shared step store call was refused (%s).", why(exc))
            raise StepShareRefused("storage") from None

    def _seal(self, value):
        return self._cipher.encrypt(json.dumps(value, ensure_ascii=False).encode("utf8"))

    def _open(self, blob):
        return None if blob is None else json.loads(self._cipher.decrypt(blob).decode("utf8"))

    # --- the steps -------------------------------------------------------------------------------------------------------------
    def ask(self, advocate_id, turn_id, asked) -> int:
        """A step the web server takes, for the worker: what it asks, sealed. Returns its number."""
        with self._transaction() as db:
            return db.execute("INSERT INTO steps (advocate_id,turn_id,state,asked,at) VALUES (?,?,'new',?,?)",
                              (advocate_id, turn_id, self._seal(asked), self._clock())).lastrowid

    def take(self):
        """The worker takes every step not yet taken, oldest first: [(number, advocate_id, turn_id, asked)]."""
        with self._transaction() as db:
            rows = db.execute("SELECT id,advocate_id,turn_id,asked FROM steps WHERE state='new' ORDER BY id").fetchall()
            db.executemany("UPDATE steps SET state='taken' WHERE id=?", [(row[0],) for row in rows])
        return [(number, advocate_id, turn_id, self._open(asked)) for number, advocate_id, turn_id, asked in rows]

    def answer(self, number, answered):
        """What the step answered - {"status": 200, "body": ...} or a refusal's {"status", "detail"} - sealed, for the web server."""
        with self._transaction() as db:
            db.execute("UPDATE steps SET state='done',answered=?,at=? WHERE id=?", (self._seal(answered), self._clock(), number))

    def answered(self, number):
        """What that step answered, or None while it waits or works."""
        with self._transaction() as db:
            row = db.execute("SELECT state,answered FROM steps WHERE id=?", (number,)).fetchone()
        return None if row is None or row[0] != "done" else self._open(row[1])

    def latest(self, advocate_id, turn_id):
        """The newest step of that turn: (number, done) - or None."""
        with self._transaction() as db:
            row = db.execute("SELECT id,state FROM steps WHERE advocate_id=? AND turn_id=? ORDER BY id DESC LIMIT 1",
                             (advocate_id, turn_id)).fetchone()
        return None if row is None else (row[0], row[1] == "done")

    def forget(self, older_than):
        """Steps and controls done before older_than (a time) are let go: what they answered was the page's to read."""
        with self._transaction() as db:
            db.execute("DELETE FROM steps WHERE state='done' AND at<?", (older_than,))
            db.execute("DELETE FROM controls WHERE state='done' AND at<?", (older_than,))

    # --- what is asked of a step at work ------------------------------------------------------------------------------------------
    def control(self, advocate_id, turn_id, kind, asked) -> int:
        with self._transaction() as db:
            return db.execute("INSERT INTO controls (advocate_id,turn_id,kind,state,asked,at) VALUES (?,?,?,'new',?,?)",
                              (advocate_id, turn_id, kind, self._seal(asked), self._clock())).lastrowid

    def controls(self):
        """The worker TAKES what is asked, oldest first: [(number, advocate_id, turn_id, kind, asked)]. Plan AN.52 (52g, D213):
        each is marked as taken in the same transaction that reads it, so a request is either taken here or withdrawn by the one
        who asked (`withdraw`), never both - a request the page was told had not landed cannot land later."""
        with self._transaction() as db:
            rows = db.execute("SELECT id,advocate_id,turn_id,kind,asked FROM controls WHERE state='new' AND answered IS NULL "
                              "ORDER BY id").fetchall()
            db.executemany("UPDATE controls SET answered=? WHERE id=?", [(_TAKING, row[0]) for row in rows])
        return [(number, advocate_id, turn_id, kind, self._open(asked)) for number, advocate_id, turn_id, kind, asked in rows]

    def withdraw(self, number) -> bool:
        """The one who asked stops waiting (52g): the request is removed unless the worker has taken it. True where it was
        withdrawn (or is no longer there); False where the worker has it, and its word is still to come."""
        with self._transaction() as db:
            gone = db.execute("DELETE FROM controls WHERE id=? AND state='new' AND answered IS NULL", (number,)).rowcount
            return bool(gone) or db.execute("SELECT 1 FROM controls WHERE id=?", (number,)).fetchone() is None

    def withdraw_all(self) -> int:
        """At the worker's start (52g): what was asked of the run before it is asked of no one now - a Stop left from before a
        restart must not stop the step taken up after it. Returns how many were let go."""
        with self._transaction() as db:
            return db.execute("DELETE FROM controls WHERE state='new'").rowcount

    def verdict(self, number, answered):
        with self._transaction() as db:
            db.execute("UPDATE controls SET state='done',answered=?,at=? WHERE id=?", (self._seal(answered), self._clock(), number))

    def verdict_of(self, number):
        with self._transaction() as db:
            row = db.execute("SELECT state,answered FROM controls WHERE id=?", (number,)).fetchone()
        return None if row is None or row[0] != "done" else self._open(row[1])

    # --- NM's open questions -------------------------------------------------------------------------------------------------------
    def show_window(self, advocate_id, turn_id, view):
        with self._transaction() as db:
            db.execute("INSERT OR REPLACE INTO windows (advocate_id,turn_id,view,at) VALUES (?,?,?,?)",
                       (advocate_id, turn_id, self._seal(view), self._clock()))

    def close_window(self, advocate_id, turn_id):
        with self._transaction() as db:
            db.execute("DELETE FROM windows WHERE advocate_id=? AND turn_id=?", (advocate_id, turn_id))

    def window(self, advocate_id, turn_id):
        with self._transaction() as db:
            row = db.execute("SELECT view FROM windows WHERE advocate_id=? AND turn_id=?", (advocate_id, turn_id)).fetchone()
        return None if row is None else self._open(row[0])

    def close_windows(self):
        """At the worker's start: no window of an earlier run of it is open any longer."""
        with self._transaction() as db:
            db.execute("DELETE FROM windows")

    # --- progress ------------------------------------------------------------------------------------------------------------------
    def put_progress(self, advocate_id, turn_id, row):
        with self._transaction() as db:
            db.execute("INSERT OR REPLACE INTO progress (advocate_id,turn_id,row,at) VALUES (?,?,?,?)",
                       (advocate_id, turn_id, json.dumps(row), self._clock()))

    def progress(self, advocate_id, turn_id):
        with self._transaction() as db:
            row = db.execute("SELECT row FROM progress WHERE advocate_id=? AND turn_id=?", (advocate_id, turn_id)).fetchone()
        return None if row is None else json.loads(row[0])

    def drop_progress(self, advocate_id, turn_id):
        with self._transaction() as db:
            db.execute("DELETE FROM progress WHERE advocate_id=? AND turn_id=?", (advocate_id, turn_id))

    def all_progress(self):
        with self._transaction() as db:
            rows = db.execute("SELECT advocate_id,turn_id,row FROM progress").fetchall()
        return [(advocate_id, turn_id, json.loads(row)) for advocate_id, turn_id, row in rows]

    # --- the worker ------------------------------------------------------------------------------------------------------------------
    def beat(self, name, *, waiting, working):
        with self._transaction() as db:
            db.execute("INSERT OR REPLACE INTO worker (name,at,waiting,working) VALUES (?,?,?,?)",
                       (name, self._clock(), int(waiting), int(working)))

    def workers(self):
        """[(name, seconds since its last beat, steps waiting, steps working)]."""
        now = self._clock()
        with self._transaction() as db:
            rows = db.execute("SELECT name,at,waiting,working FROM worker").fetchall()
        return [(name, now - at, waiting, working) for name, at, waiting, working in rows]
