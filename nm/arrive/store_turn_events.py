"""The turn record, kept content-free in its own sidecar store (plan AN.46, piece 46h; owner decision D120).

SQLite in its own file (turn-events.sqlite), made the way the usage and Admin stores are: published whole or not at all, a schema it did
not make refused, BEGIN IMMEDIATE for every use. Its own file, so the usage store's strict schema is not changed. One table, one row
per finished turn; an account is named by the SHA-256 of its canonical id, as the usage store names it, so no address is written here,
and a row is a fixed set of names and numbers that no sentence can be written through (see nm/arrive/turn_event_port.py).
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from nm.arrive.advocate_contracts import canonical_id
from nm.arrive.turn_event_port import EVENT_FIELDS, OUTCOMES, TurnEventRefused
from nm.shared.sqlite_creation import create_if_absent, why

_log = logging.getLogger("nm.turns")

VERSION = 1
#: Plan AN.53 (D241): the counts and timings of turns, which hold no content, are kept two years - a leap day included.
KEPT_DAYS = 731
#: The names a line carries (a model, an effort): one short word each, with no spaces, so no sentence can be written through one.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}\Z")
_SQL = {
    ("table", "turns"): """CREATE TABLE turns (
        id INTEGER PRIMARY KEY,
        account TEXT NOT NULL CHECK(length(account)=64),
        started_at TEXT NOT NULL,
        ended_at TEXT NOT NULL,
        seconds INTEGER NOT NULL CHECK(seconds >= 0),
        outcome TEXT NOT NULL CHECK(outcome IN ('answered','stopped','refused','failed')),
        model TEXT NOT NULL,
        effort TEXT NOT NULL,
        calls INTEGER CHECK(calls IS NULL OR calls >= 0),
        micro_usd INTEGER CHECK(micro_usd IS NULL OR micro_usd >= 0),
        documents INTEGER NOT NULL CHECK(documents >= 0)
    )""",
    ("index", "turns_by_end"): "CREATE INDEX turns_by_end ON turns(ended_at)",
}


def _flat(sql):
    return " ".join((sql or "").split())


def _account(account_id) -> str:
    if not isinstance(account_id, str) or not canonical_id(account_id):
        raise ValueError("a turn belongs to a named account")
    return hashlib.sha256(canonical_id(account_id).encode("utf8")).hexdigest()


def _utc(value, name) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"a turn's {name} is a time with its zone")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _checked(event) -> tuple:
    """The row's values, or ValueError: a line is a fixed set of names, times and numbers, so nothing else can be written through it."""
    if not isinstance(event, dict) or tuple(sorted(event)) != tuple(sorted(EVENT_FIELDS)):
        raise ValueError("a turn line holds exactly its declared fields")
    started, ended = _utc(event["started_at"], "start"), _utc(event["ended_at"], "end")
    if ended < started:
        raise ValueError("a turn ends after it starts")
    if event["outcome"] not in OUTCOMES:
        raise ValueError("a turn ends as answered, stopped, refused or failed")
    for name in ("model", "effort"):
        if not isinstance(event[name], str) or not _NAME.fullmatch(event[name]):
            raise ValueError(f"a turn line's {name} is a short name")
    for name in ("calls", "micro_usd"):
        if event[name] is not None and (type(event[name]) is not int or event[name] < 0):
            raise ValueError(f"a turn line's {name} is a whole number or not established")
    if type(event["documents"]) is not int or event["documents"] < 0:
        raise ValueError("a turn line counts the documents sent")
    return (started.isoformat(), ended.isoformat(), int((ended - started).total_seconds()), event["outcome"], event["model"],
            event["effort"], event["calls"], event["micro_usd"], event["documents"])


class FileTurnEvents:
    """The turn record of one installation; see the module's note."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        try:
            create_if_absent(self.path, self._build)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The turn record could not be opened (%s).", why(exc))
            raise TurnEventRefused("storage") from None

    @staticmethod
    def _build(db):
        for sql in _SQL.values():
            db.execute(sql)
        db.execute(f"PRAGMA user_version={VERSION}")

    @classmethod
    def _schema(cls, db):
        found = {(kind, name): _flat(sql) for kind, name, sql in
                 db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()}
        if (db.execute("PRAGMA user_version").fetchone()[0] != VERSION
                or found != {key: _flat(sql) for key, sql in _SQL.items()}):
            raise ValueError("the turn record has a schema it did not make")

    @contextmanager
    def _transaction(self):
        try:
            # The record must exist: it never starts again from nothing in a newly made file.
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
                yield db
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("A turn line was refused by the record (%s).", why(exc))
            raise TurnEventRefused("storage") from None

    def sweep(self, before) -> int:
        """Every line of a turn that ended before `before` goes (plan AN.53, D241: the counts and timings of turns, which hold no
        content, are kept two years); returns how many."""
        cut = _utc(before, "sweep").isoformat()
        with self._transaction() as db:
            return db.execute("DELETE FROM turns WHERE ended_at < ?", (cut,)).rowcount

    def record(self, account_id: str, event: dict) -> None:
        account, values = _account(account_id), _checked(event)
        with self._transaction() as db:
            db.execute("INSERT INTO turns (account,started_at,ended_at,seconds,outcome,model,effort,calls,micro_usd,documents) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)", (account, *values))
