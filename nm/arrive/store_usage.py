"""Each account's usage of the paid AI service, kept content-free in one sidecar store (plan AN.17).

SQLite, with the turn-attempt store's BEGIN IMMEDIATE transactions and its refusal of any schema it
did not make (nm/shared/turn_attempt_store.py). Three tables: what each account was given (its trial,
once, and what an operator adds), what each call cost, and the last usage notice it was shown. An
account is named by the SHA-256 of its canonical id, as its account claim already is
(nm/arrive/store_directory.py): no email address is written here, and no prompt, message, answer or
file can be, since a call's record holds only its kind, names and numbers.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from nm.arrive.advocate_contracts import canonical_id
from nm.arrive.usage_port import (CALL_FIELDS, CALL_KINDS, NOTICE_STEPS, TRIAL_MICRO_USD, UsageRefused,
                                  percent_left)

VERSION = 1
#: The most an operator may add in one grant, in millionths of a dollar: a typo of a few zeros is
#: refused rather than given away (USD 1,000).
GRANT_LIMIT = 1_000_000_000
#: The names a call record carries (an operation, a tier, a model, an error's class): one short word
#: each, with no spaces, so no sentence can be written through a record.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}\Z")
_SQL = {
    ("table", "grants"): """CREATE TABLE grants (
        id INTEGER PRIMARY KEY,
        account TEXT NOT NULL CHECK(length(account)=64),
        kind TEXT NOT NULL CHECK(kind IN ('trial','operator')),
        micro_usd INTEGER NOT NULL CHECK(micro_usd > 0),
        at TEXT NOT NULL,
        note TEXT NOT NULL
    )""",
    ("index", "one_trial_per_account"): "CREATE UNIQUE INDEX one_trial_per_account ON grants(account) WHERE kind='trial'",
    ("table", "calls"): """CREATE TABLE calls (
        id INTEGER PRIMARY KEY,
        account TEXT NOT NULL CHECK(length(account)=64),
        at TEXT NOT NULL,
        kind TEXT NOT NULL,
        operation TEXT NOT NULL,
        tier TEXT NOT NULL,
        model TEXT NOT NULL,
        outcome TEXT NOT NULL,
        attempts INTEGER NOT NULL CHECK(attempts >= 1),
        tokens_in INTEGER CHECK(tokens_in IS NULL OR tokens_in >= 0),
        tokens_out INTEGER CHECK(tokens_out IS NULL OR tokens_out >= 0),
        cached_tokens INTEGER CHECK(cached_tokens IS NULL OR cached_tokens >= 0),
        cache_write_tokens INTEGER CHECK(cache_write_tokens IS NULL OR cache_write_tokens >= 0),
        audio_seconds REAL CHECK(audio_seconds IS NULL OR audio_seconds >= 0),
        micro_usd INTEGER CHECK(micro_usd IS NULL OR micro_usd >= 0)
    )""",
    ("index", "calls_by_account"): "CREATE INDEX calls_by_account ON calls(account)",
    ("table", "notices"): """CREATE TABLE notices (
        account TEXT PRIMARY KEY NOT NULL CHECK(length(account)=64),
        step INTEGER NOT NULL CHECK(step BETWEEN 1 AND 50)
    )""",
}


def _flat(sql):
    return " ".join((sql or "").split())


def _account(account_id) -> str:
    if not isinstance(account_id, str) or not canonical_id(account_id):
        raise ValueError("usage belongs to a named account")
    return hashlib.sha256(canonical_id(account_id).encode("utf8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _checked(call) -> tuple:
    """The record's values in CALL_FIELDS order, or ValueError: a record is a fixed set of names and
    numbers, so nothing else can be written through it."""
    if not isinstance(call, dict) or tuple(sorted(call)) != tuple(sorted(CALL_FIELDS)):
        raise ValueError("a call record holds exactly its declared fields")
    if call["kind"] not in CALL_KINDS:
        raise ValueError("a call record names a model port call")
    for name in ("operation", "tier", "model", "outcome"):
        value = call[name]
        if not isinstance(value, str) or (value and not _NAME.fullmatch(value)):
            raise ValueError(f"a call record's {name} is a short name")
    if not call["outcome"] or type(call["attempts"]) is not int or call["attempts"] < 1:
        raise ValueError("a call record says how it ended and how many attempts it took")
    for name in ("tokens_in", "tokens_out", "cached_tokens", "cache_write_tokens", "micro_usd"):
        if call[name] is not None and (type(call[name]) is not int or call[name] < 0):
            raise ValueError(f"a call record's {name} is a whole number or not established")
    seconds = call["audio_seconds"]
    if seconds is not None and (type(seconds) not in (int, float) or not 0 <= seconds < 10**7):
        raise ValueError("a call record's audio seconds are a number or not established")
    return tuple(float(call[name]) if name == "audio_seconds" and call[name] is not None else call[name]
                 for name in CALL_FIELDS)


class FileUsage:
    """The usage sidecar of one installation; see the module's note."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        existed = self.path.exists()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                if db.execute("PRAGMA user_version").fetchone()[0] == 0 and not self._objects(db) and not existed:
                    for sql in _SQL.values():
                        db.execute(sql)
                    db.execute(f"PRAGMA user_version={VERSION}")
                self._schema(db)
        except (OSError, sqlite3.Error, ValueError):
            raise UsageRefused("storage") from None

    @staticmethod
    def _objects(db):
        return db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()

    @classmethod
    def _schema(cls, db):
        found = {(kind, name): _flat(sql) for kind, name, sql in cls._objects(db)}
        if (db.execute("PRAGMA user_version").fetchone()[0] != VERSION
                or found != {key: _flat(sql) for key, sql in _SQL.items()}):
            raise ValueError("the usage store has a schema it did not make")

    @contextmanager
    def _transaction(self):
        try:
            # The store must exist: usage never starts again from nothing in a newly made file.
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
                yield db
        except (OSError, sqlite3.Error, ValueError):
            raise UsageRefused("storage") from None

    @staticmethod
    def _standing(db, account):
        # The trial, once: the partial unique index refuses a second, and the first read gives it.
        db.execute("INSERT OR IGNORE INTO grants (account,kind,micro_usd,at,note) VALUES (?,'trial',?,?,'')",
                   (account, TRIAL_MICRO_USD, _now()))
        granted = db.execute("SELECT COALESCE(SUM(micro_usd),0) FROM grants WHERE account=?", (account,)).fetchone()[0]
        spent = db.execute("SELECT COALESCE(SUM(micro_usd),0) FROM calls WHERE account=?", (account,)).fetchone()[0]
        row = db.execute("SELECT step FROM notices WHERE account=?", (account,)).fetchone()
        return {"granted": granted, "spent": spent, "left": percent_left(granted, spent),
                "noticed": row[0] if row else None}

    def standing(self, account_id: str) -> dict:
        account = _account(account_id)
        with self._transaction() as db:
            return self._standing(db, account)

    def record(self, account_id: str, call: dict) -> None:
        account, values = _account(account_id), _checked(call)
        with self._transaction() as db:
            db.execute(f"INSERT INTO calls (account,at,{','.join(CALL_FIELDS)}) "
                       f"VALUES (?,?,{','.join('?' * len(CALL_FIELDS))})", (account, _now(), *values))

    def grant(self, account_id: str, micro_usd: int, *, note: str) -> dict:
        account = _account(account_id)
        if type(micro_usd) is not int or not 0 < micro_usd <= GRANT_LIMIT:
            raise ValueError("a grant is a positive number of millionths of a dollar, at most USD 1,000")
        if not isinstance(note, str) or not note.strip() or len(note) > 200:
            raise ValueError("a grant says who made it and why, in at most 200 characters")
        with self._transaction() as db:
            self._standing(db, account)
            db.execute("INSERT INTO grants (account,kind,micro_usd,at,note) VALUES (?,'operator',?,?,?)",
                       (account, micro_usd, _now(), note.strip()))
            # A larger allowance starts its notices again (P53): 50%, 25%, then every 1% from 10%.
            db.execute("DELETE FROM notices WHERE account=?", (account,))
            return self._standing(db, account)

    def noticed(self, account_id: str, step: int) -> None:
        account = _account(account_id)
        if type(step) is not int or step not in NOTICE_STEPS:
            raise ValueError("a notice is one of the usage steps")
        with self._transaction() as db:
            # Only ever lower: a page left open on an earlier notice cannot bring it back.
            db.execute("INSERT INTO notices (account,step) VALUES (?,?) "
                       "ON CONFLICT(account) DO UPDATE SET step=MIN(step, excluded.step)", (account, step))

    def totals(self) -> dict:
        """What every call cost, for the operator: across all accounts, by model and by outcome, with the
        calls whose cost was not established counted apart. Accounts appear only as digests."""
        with self._transaction() as db:
            def grouped(column):
                return [{column: key, "calls": calls, "micro_usd": cost, "not_established": unknown}
                        for key, calls, cost, unknown in db.execute(
                            f"SELECT {column},COUNT(*),COALESCE(SUM(micro_usd),0),"
                            f"SUM(micro_usd IS NULL) FROM calls GROUP BY {column} ORDER BY {column}")]
            calls, cost, unknown = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(micro_usd),0),COALESCE(SUM(micro_usd IS NULL),0) FROM calls").fetchone()
            granted = db.execute("SELECT COALESCE(SUM(micro_usd),0) FROM grants").fetchone()[0]
            accounts = db.execute("SELECT COUNT(DISTINCT account) FROM grants").fetchone()[0]
            return {"accounts": accounts, "granted": granted, "calls": calls, "micro_usd": cost,
                    "not_established": unknown, "by_model": grouped("model"), "by_outcome": grouped("outcome")}
