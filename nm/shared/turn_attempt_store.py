"""Content-free durable turn ownership and the one correction allowance.

SQLite transactions follow the live model_call_budget owner's BEGIN IMMEDIATE
pattern. This store carries only opaque request digests, fencing tokens and state;
it is neither an admitted conversation nor an execution receipt. A running claim
left by a crash remains busy. Recovery of that unknown attempt needs an explicit
owner; elapsed time never grants a fresh correction or repeats a possible effect.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from nm.shared.turn_attempt_port import AttemptRefused

VERSION = 1
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}\Z")
_FINAL = {"retryable", "terminal", "finished", "unconfirmed"}
_STATES = _FINAL | {"running"}
_SQL = """CREATE TABLE turn_attempts (
    identity TEXT PRIMARY KEY NOT NULL CHECK(length(identity)=64),
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    token TEXT NOT NULL CHECK(length(token)=64),
    correction_used INTEGER NOT NULL CHECK(correction_used IN (0,1)),
    state TEXT NOT NULL CHECK(state IN ('running','retryable','terminal','finished','unconfirmed')),
    code TEXT
)"""
_FIELDS = "identity,request_digest,token,correction_used,state,code"


def _opaque(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _code(value):
    return value is None or isinstance(value, str) and _CODE.fullmatch(value) is not None


class FileTurnAttempts:
    """An atomic sidecar; never stores account names, messages or rejected drafts."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        existed = self.path.exists()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                objects = self._objects(db)
                if version == 0 and not objects and not existed:
                    db.execute(_SQL)
                    db.execute(f"PRAGMA user_version={VERSION}")
                self._schema(db)
        except (OSError, sqlite3.Error, ValueError):
            raise AttemptRefused("storage") from None

    @staticmethod
    def _objects(db):
        return db.execute("SELECT type,name,sql FROM sqlite_master "
                          "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()

    @classmethod
    def _schema(cls, db):
        objects = cls._objects(db)
        if (db.execute("PRAGMA user_version").fetchone()[0] != VERSION
                or len(objects) != 1 or objects[0][:2] != ("table", "turn_attempts")
                or " ".join((objects[0][2] or "").split()) != " ".join(_SQL.split())):
            raise AttemptRefused("storage")

    @contextmanager
    def _transaction(self):
        try:
            # Existing ownership must not disappear into a newly created empty DB.
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                                          timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
                yield db
        except (OSError, sqlite3.Error, ValueError):
            raise AttemptRefused("storage") from None

    @staticmethod
    def _row(db, identity):
        row = db.execute(f"SELECT {_FIELDS} FROM turn_attempts WHERE identity=?", (identity,)).fetchone()
        if row is not None and (any(not _opaque(value) for value in row[:3])
                or type(row[3]) is not int or row[3] not in (0, 1)
                or row[4] not in _STATES or not _code(row[5])
                or row[4] == "running" and row[5] is not None):
            raise AttemptRefused("storage")
        return row

    @staticmethod
    def _refuse_state(state):
        if state == "running":
            raise AttemptRefused("busy")
        if state == "unconfirmed":
            raise AttemptRefused("unconfirmed")
        raise AttemptRefused("terminal")

    def claim(self, identity: str, request_digest: str) -> dict:
        if not _opaque(identity) or not _opaque(request_digest):
            raise AttemptRefused("conflict")
        token = secrets.token_hex(32)
        with self._transaction() as db:
            prior = self._row(db, identity)
            if prior is None:
                correction_used = 0
                db.execute(f"INSERT INTO turn_attempts ({_FIELDS}) VALUES (?,?,?,0,'running',NULL)",
                           (identity, request_digest, token))
            else:
                if prior[1] != request_digest:
                    raise AttemptRefused("conflict")
                if prior[4] != "retryable":
                    self._refuse_state(prior[4])
                correction_used = prior[3]
                db.execute("UPDATE turn_attempts SET token=?,state='running',code=NULL WHERE identity=?",
                           (token, identity))
        return {"token": token, "correction_used": bool(correction_used)}

    def consume_correction(self, identity: str, token: str) -> None:
        if not _opaque(identity) or not _opaque(token):
            raise AttemptRefused("conflict")
        with self._transaction() as db:
            prior = self._row(db, identity)
            if prior is None or prior[2] != token:
                raise AttemptRefused("conflict")
            if prior[4] != "running":
                self._refuse_state(prior[4])
            if prior[3]:
                raise AttemptRefused("terminal")
            changed = db.execute("UPDATE turn_attempts SET correction_used=1 "
                "WHERE identity=? AND token=? AND state='running' AND correction_used=0",
                (identity, token))
            if changed.rowcount != 1:
                raise AttemptRefused("conflict")

    def finish(self, identity: str, token: str, state: str, code: str | None = None) -> None:
        if (not _opaque(identity) or not _opaque(token) or not isinstance(state, str)
                or state not in _FINAL or not _code(code)):
            raise AttemptRefused("conflict")
        with self._transaction() as db:
            prior = self._row(db, identity)
            if prior is None or prior[2] != token:
                raise AttemptRefused("conflict")
            if prior[4] != "running":
                if (prior[4], prior[5]) == (state, code):
                    return  # Exact retry after a lost acknowledgement, not a new transition.
                self._refuse_state(prior[4])
            changed = db.execute("UPDATE turn_attempts SET state=?,code=? "
                "WHERE identity=? AND token=? AND state='running'", (state, code, identity, token))
            if changed.rowcount != 1:
                raise AttemptRefused("conflict")
