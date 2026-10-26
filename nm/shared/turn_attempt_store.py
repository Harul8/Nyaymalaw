"""Content-free durable turn ownership and its correction allowance.

SQLite transactions follow the live model_call_budget owner's BEGIN IMMEDIATE
pattern. This store carries only opaque request digests, fencing tokens and state;
it is neither an admitted conversation nor an execution receipt. A running claim
left by a crash remains busy. Recovery of that unknown attempt needs an explicit
owner; elapsed time never grants a fresh correction or repeats a possible effect.
"""
from __future__ import annotations

import logging
import re
import secrets
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from nm.shared.sqlite_creation import create_if_absent, why
from nm.shared.turn_attempt_port import AttemptRefused

_log = logging.getLogger("nm.attempts")

VERSION = 3
#: Corrections one turn may make in all, held as a count so a retried turn never receives
#: fresh corrections. From version 3 (owner decision P25, 19 Oct 2026) each section of an
#: answer has its own rewrites, so the turn's total is larger; nm.core_engine.calls owns how
#: they are shared out.
ALLOWANCE = 32
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}\Z")
_FINAL = {"retryable", "terminal", "finished", "unconfirmed"}
_STATES = _FINAL | {"running"}
_SQL = f"""CREATE TABLE turn_attempts (
    identity TEXT PRIMARY KEY NOT NULL CHECK(length(identity)=64),
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    token TEXT NOT NULL CHECK(length(token)=64),
    corrections_used INTEGER NOT NULL CHECK(corrections_used BETWEEN 0 AND {ALLOWANCE}),
    state TEXT NOT NULL CHECK(state IN ('running','retryable','terminal','finished','unconfirmed')),
    code TEXT
)"""
_FIELDS = "identity,request_digest,token,corrections_used,state,code"
#: Version 1 held one allowance, used or not; version 2 held a count of at most two.
#: Exactly these tables are carried over with their records unchanged; any other schema
#: is still refused.
_SQL_V1 = """CREATE TABLE turn_attempts (
    identity TEXT PRIMARY KEY NOT NULL CHECK(length(identity)=64),
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    token TEXT NOT NULL CHECK(length(token)=64),
    correction_used INTEGER NOT NULL CHECK(correction_used IN (0,1)),
    state TEXT NOT NULL CHECK(state IN ('running','retryable','terminal','finished','unconfirmed')),
    code TEXT
)"""
_SQL_V2 = """CREATE TABLE turn_attempts (
    identity TEXT PRIMARY KEY NOT NULL CHECK(length(identity)=64),
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    token TEXT NOT NULL CHECK(length(token)=64),
    corrections_used INTEGER NOT NULL CHECK(corrections_used BETWEEN 0 AND 2),
    state TEXT NOT NULL CHECK(state IN ('running','retryable','terminal','finished','unconfirmed')),
    code TEXT
)"""


def _opaque(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _code(value):
    return value is None or isinstance(value, str) and _CODE.fullmatch(value) is not None


class FileTurnAttempts:
    """An atomic sidecar; never stores account names, messages or rejected drafts."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        try:
            # Made complete beside its place and published whole, never built where it is to stay: a second
            # caller must not find a file that exists and is empty, which this store refuses as a lost one
            # (plan AN.24).
            create_if_absent(self.path, self._build)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                objects = self._objects(db)
                if (version, True) in ((1, self._is(objects, _SQL_V1)), (2, self._is(objects, _SQL_V2))):
                    used = "correction_used" if version == 1 else "corrections_used"
                    db.execute("ALTER TABLE turn_attempts RENAME TO turn_attempts_earlier")
                    db.execute(_SQL)
                    db.execute(f"INSERT INTO turn_attempts ({_FIELDS}) SELECT identity,request_digest,"
                               f"token,{used},state,code FROM turn_attempts_earlier")
                    db.execute("DROP TABLE turn_attempts_earlier")
                    db.execute(f"PRAGMA user_version={VERSION}")
                self._schema(db)
        except AttemptRefused as exc:
            if exc.code == "storage":
                _log.warning("The turn-attempt store holds something it did not make.")
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The turn-attempt store could not be opened (%s).", why(exc))
            raise AttemptRefused("storage") from None

    @staticmethod
    def _build(db):
        db.execute(_SQL)
        db.execute(f"PRAGMA user_version={VERSION}")

    @staticmethod
    def _objects(db):
        return db.execute("SELECT type,name,sql FROM sqlite_master "
                          "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()

    @staticmethod
    def _is(objects, sql):
        return (len(objects) == 1 and objects[0][:2] == ("table", "turn_attempts")
                and " ".join((objects[0][2] or "").split()) == " ".join(sql.split()))

    @classmethod
    def _schema(cls, db):
        if db.execute("PRAGMA user_version").fetchone()[0] != VERSION or not cls._is(cls._objects(db), _SQL):
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
        except AttemptRefused as exc:
            if exc.code == "storage":
                _log.warning("The turn-attempt store holds something it did not make.")
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("A turn-attempt call was refused by the store (%s).", why(exc))
            raise AttemptRefused("storage") from None

    @staticmethod
    def _row(db, identity):
        row = db.execute(f"SELECT {_FIELDS} FROM turn_attempts WHERE identity=?", (identity,)).fetchone()
        if row is not None and (any(not _opaque(value) for value in row[:3])
                or type(row[3]) is not int or not 0 <= row[3] <= ALLOWANCE
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
                corrections_used = 0
                db.execute(f"INSERT INTO turn_attempts ({_FIELDS}) VALUES (?,?,?,0,'running',NULL)",
                           (identity, request_digest, token))
            else:
                if prior[1] != request_digest:
                    raise AttemptRefused("conflict")
                if prior[4] != "retryable":
                    self._refuse_state(prior[4])
                corrections_used = prior[3]
                db.execute("UPDATE turn_attempts SET token=?,state='running',code=NULL WHERE identity=?",
                           (token, identity))
        return {"token": token, "corrections_used": corrections_used}

    def consume_correction(self, identity: str, token: str) -> None:
        if not _opaque(identity) or not _opaque(token):
            raise AttemptRefused("conflict")
        with self._transaction() as db:
            prior = self._row(db, identity)
            if prior is None or prior[2] != token:
                raise AttemptRefused("conflict")
            if prior[4] != "running":
                self._refuse_state(prior[4])
            if prior[3] >= ALLOWANCE:
                raise AttemptRefused("terminal")
            changed = db.execute("UPDATE turn_attempts SET corrections_used=corrections_used+1 "
                "WHERE identity=? AND token=? AND state='running' AND corrections_used=?",
                (identity, token, prior[3]))
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
