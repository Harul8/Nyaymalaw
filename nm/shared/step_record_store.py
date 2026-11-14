"""Content-free records of the steps a server has taken (plan AN.48, piece 48f3; owner decision D167, 10 Nov 2026).

A step goes on after its request has answered (48f1) and may wait for a free place (48f2). Should the server stop meanwhile - a
restart, an update, a crash - its record says at the next start what can be taken up again: whose step it was, which conversation
and turn, which route, a go-ahead's choice and the disputes it named, whether it had begun, and the sign-in it was asked under by
its fingerprint (never its token). Never a message, an answer, an answer to a question or a file: a step whose words were not yet
kept with its conversation cannot be taken up from here, and is said as it always was. A record goes when its step ends. SQLite
transactions follow the turn-attempt store's BEGIN IMMEDIATE pattern; a record that cannot be written never fails its step.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from nm.shared.sqlite_creation import create_if_absent, why

_log = logging.getLogger("nm.steps")

VERSION = 2
#: Plan AN.53 (D241, with the turns' attempts): a step's record is kept at most this many days from when the step was taken.
TAKEN_KEPT_DAYS = 90
ROUTES = ("send", "continue", "go", "answers", "message")
CHOICES = ("next", "research", "write", "end_to_end", "done")
_SQL = """CREATE TABLE steps (
    advocate_id TEXT NOT NULL CHECK(length(advocate_id) BETWEEN 1 AND 320),
    turn_id TEXT NOT NULL CHECK(length(turn_id) BETWEEN 1 AND 200),
    chat_id TEXT CHECK(chat_id IS NULL OR length(chat_id) BETWEEN 1 AND 200),
    route TEXT NOT NULL CHECK(route IN ('send','continue','go','answers','message')),
    choice TEXT CHECK(choice IS NULL OR choice IN ('next','research','write','end_to_end','done')),
    disputes TEXT,
    session TEXT CHECK(session IS NULL OR length(session)=64),
    begun INTEGER NOT NULL CHECK(begun IN (0,1)),
    taken_at TEXT NOT NULL,
    PRIMARY KEY (advocate_id, turn_id)
)"""
_FIELDS = "advocate_id,turn_id,chat_id,route,choice,disputes,session,begun,taken_at"
#: Version 1: version 2 without when each step was taken. Carried over with every record, each taken as at the carrying over.
_SQL_V1 = """CREATE TABLE steps (
    advocate_id TEXT NOT NULL CHECK(length(advocate_id) BETWEEN 1 AND 320),
    turn_id TEXT NOT NULL CHECK(length(turn_id) BETWEEN 1 AND 200),
    chat_id TEXT CHECK(chat_id IS NULL OR length(chat_id) BETWEEN 1 AND 200),
    route TEXT NOT NULL CHECK(route IN ('send','continue','go','answers','message')),
    choice TEXT CHECK(choice IS NULL OR choice IN ('next','research','write','end_to_end','done')),
    disputes TEXT,
    session TEXT CHECK(session IS NULL OR length(session)=64),
    begun INTEGER NOT NULL CHECK(begun IN (0,1)),
    PRIMARY KEY (advocate_id, turn_id)
)"""


def _now():
    """When a step was taken, as the store writes it: UTC to the second, so that text order is time order."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
_DISPUTE = re.compile(r"[A-Za-z0-9_.:-]{1,200}\Z")
_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")


class StepRecordsRefused(Exception):
    """The record store could not be opened or holds something it did not make."""


class FileStepRecords:
    def __init__(self, path):
        self.path = Path(path).resolve()
        try:
            create_if_absent(self.path, self._build)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("PRAGMA user_version").fetchone()[0] == 1 and self._is(db, _SQL_V1):
                    db.execute("ALTER TABLE steps RENAME TO steps_earlier")
                    db.execute(_SQL)
                    db.execute(f"INSERT INTO steps ({_FIELDS}) SELECT advocate_id,turn_id,chat_id,route,choice,disputes,session,"
                               "begun,? FROM steps_earlier", (_now(),))
                    db.execute("DROP TABLE steps_earlier")
                    db.execute(f"PRAGMA user_version={VERSION}")
                self._schema(db)
        except StepRecordsRefused:
            _log.warning("The step record store holds something it did not make.")
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The step record store could not be opened (%s).", why(exc))
            raise StepRecordsRefused("storage") from None

    @staticmethod
    def _build(db):
        db.execute(_SQL)
        db.execute(f"PRAGMA user_version={VERSION}")

    @staticmethod
    def _is(db, sql):
        objects = db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        tables = [row for row in objects if row[0] == "table"]
        return len(tables) == 1 and tables[0][1] == "steps" and " ".join((tables[0][2] or "").split()) == " ".join(sql.split())

    @classmethod
    def _schema(cls, db):
        if db.execute("PRAGMA user_version").fetchone()[0] != VERSION or not cls._is(db, _SQL):
            raise StepRecordsRefused("storage")

    @contextmanager
    def _transaction(self):
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._schema(db)
            yield db

    def _quietly(self, what, change):
        """A record that cannot be written loses that record and nothing else: the step goes on; only the kind of fault is logged."""
        try:
            with self._transaction() as db:
                change(db)
        except (OSError, sqlite3.Error, ValueError, StepRecordsRefused) as exc:
            _log.warning("A step record could not be %s (%s).", what, type(exc).__name__)

    def taken(self, advocate_id, turn_id, *, route, chat_id=None, choice=None, disputes=None, session=None):
        """A step taken by the server, not yet begun."""
        if route not in ROUTES or choice is not None and choice not in CHOICES:
            raise ValueError("not a step's route or choice")
        if disputes is not None and not (isinstance(disputes, (list, tuple)) and all(
                isinstance(each, str) and _DISPUTE.match(each) for each in disputes)):
            raise ValueError("not a list of dispute identities")
        if session is not None and not (isinstance(session, str) and _FINGERPRINT.match(session)):
            raise ValueError("not a sign-in's fingerprint")
        row = (advocate_id, turn_id, chat_id, route, choice, None if disputes is None else json.dumps(list(disputes)), session, 0,
               _now())
        self._quietly("kept", lambda db: db.execute(f"INSERT OR REPLACE INTO steps ({_FIELDS}) VALUES (?,?,?,?,?,?,?,?,?)", row))

    def begun(self, advocate_id, turn_id):
        self._quietly("marked as begun", lambda db: db.execute(
            "UPDATE steps SET begun=1 WHERE advocate_id=? AND turn_id=?", (advocate_id, turn_id)))

    def ended(self, advocate_id, turn_id):
        self._quietly("let go", lambda db: db.execute("DELETE FROM steps WHERE advocate_id=? AND turn_id=?", (advocate_id, turn_id)))

    def sweep(self, before):
        """Every record of a step taken before `before` goes (plan AN.53, D241, with the turns' attempts: 90 days): a step kept
        that long - its advocate's sign-in lapsed, and never back - is let go, and its matter waits for the go-ahead as it always
        did. Returns how many. Raises where the store cannot be swept, for the daily sweep to say."""
        if not isinstance(before, datetime) or before.utcoffset() is None:
            raise ValueError("a sweep is dated with its offset")
        cut = before.astimezone(timezone.utc).isoformat(timespec="seconds")
        with self._transaction() as db:
            return db.execute("DELETE FROM steps WHERE taken_at < ?", (cut,)).rowcount

    def left(self):
        """Every step an earlier run of the server took and did not end, each as a dict - for its start, when no step of that run
        can still be at work."""
        try:
            with self._transaction() as db:
                rows = db.execute(f"SELECT {_FIELDS} FROM steps ORDER BY rowid").fetchall()
        except (OSError, sqlite3.Error, StepRecordsRefused) as exc:
            _log.warning("The steps an earlier run left could not be read (%s).", type(exc).__name__)
            return []
        names = _FIELDS.split(",")
        out = []
        for row in rows:
            record = dict(zip(names, row))
            record["disputes"] = None if record["disputes"] is None else json.loads(record["disputes"])
            record["begun"] = bool(record["begun"])
            out.append(record)
        return out
