"""Each account's usage of the paid AI service, kept content-free in one sidecar store (plan AN.17).

SQLite, with the turn-attempt store's BEGIN IMMEDIATE transactions and its refusal of any schema it
did not make (nm/shared/turn_attempt_store.py). Four tables: what each account was given (its trial,
once, and what an operator adds), what each call cost, the last usage notice it was shown, and what
was carried when old rows went (below).

KEPT EIGHT YEARS, AS A BILLING RECORD (plan AN.53, 53h4h, D241 (confirm)). A balance is summed from
the rows, so a sweep that removed old rows would change it; and the store gives an account its trial
whenever it has no trial row, so a trial swept away would be given again. So `sweep` CARRIES what it
removes: for each account, the sums of the calls and grants it took away - given, spent, how many
calls, how many whose cost was not established - are added to its row of `carried`, and every reader
of a balance or a total counts them. Each account's trial row is kept whatever its age. A store of
the first version is carried to the second in place, with nothing in it changed. An
account is named by the SHA-256 of its canonical id, as its account claim already is
(nm/arrive/store_directory.py): no email address is written here, and no prompt, message, answer or
file can be, since a call's record holds only its kind, names and numbers.
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
from nm.arrive.usage_port import (CALL_FIELDS, CALL_KINDS, NOTICE_STEPS, TRIAL_MICRO_USD, UsageRefused,
                                  percent_left)
from nm.shared.sqlite_creation import create_if_absent, why

_log = logging.getLogger("nm.usage")

VERSION = 2
#: Plan AN.53 (53h4h, D241): how many years the usage ledger keeps its rows - what each account used and was given - as a billing
#: record (confirm); what goes is carried, so that no balance changes.
USAGE_KEPT_YEARS = 8
#: The most an operator may add in one grant, in millionths of a dollar: a typo of a few zeros is
#: refused rather than given away (USD 1,000).
GRANT_LIMIT = 1_000_000_000
#: The names a call record carries (an operation, a tier, a model, an error's class): one short word
#: each, with no spaces, so no sentence can be written through a record.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}\Z")
_SQL_V1 = {
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
#: The second version (plan AN.53, 53h4h): the first, and what a sweep carried for each account.
_SQL = {
    **_SQL_V1,
    ("table", "carried"): """CREATE TABLE carried (
        account TEXT PRIMARY KEY NOT NULL CHECK(length(account)=64),
        granted INTEGER NOT NULL CHECK(granted >= 0),
        spent INTEGER NOT NULL CHECK(spent >= 0),
        calls INTEGER NOT NULL CHECK(calls >= 0),
        not_established INTEGER NOT NULL CHECK(not_established >= 0),
        through TEXT NOT NULL
    )""",
}


def years_before(moment: datetime, years: int) -> datetime:
    """The same day and time `years` years before, on the calendar; a 29 February with none that year is the 28th."""
    try:
        return moment.replace(year=moment.year - years)
    except ValueError:
        return moment.replace(year=moment.year - years, day=28)


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
        try:
            # Made complete beside its place and published whole, never built where it is to stay: a second
            # caller must not find a file that exists and is empty, which this store refuses as a lost one
            # (plan AN.24; measured: 12 of 600 first uses refused when four arrived together).
            create_if_absent(self.path, self._build)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                # The first version, exactly as it was made, is carried to the second in place (53h4h): its rows are as they
                # were, with nothing carried yet. Anything else is refused below, as it was.
                if self._version(db) == 1:
                    db.execute(_SQL[("table", "carried")])
                    db.execute(f"PRAGMA user_version={VERSION}")
                self._schema(db)
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The usage store could not be opened (%s).", why(exc))
            raise UsageRefused("storage") from None

    @staticmethod
    def _build(db):
        for sql in _SQL.values():
            db.execute(sql)
        db.execute(f"PRAGMA user_version={VERSION}")

    @staticmethod
    def _objects(db):
        return db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()

    @classmethod
    def _version(cls, db) -> int | None:
        """Which version of this store's schema the file holds - 1 or 2, each exactly as this store makes it - or None."""
        found = {(kind, name): _flat(sql) for kind, name, sql in cls._objects(db)}
        version = db.execute("PRAGMA user_version").fetchone()[0]
        for number, sql in ((1, _SQL_V1), (VERSION, _SQL)):
            if version == number and found == {key: _flat(text) for key, text in sql.items()}:
                return number
        return None

    @classmethod
    def _schema(cls, db, *, earlier: bool = False) -> int:
        """The store's own rule for a file it made: the current version, or - for a reader that only reads (the Admin area,
        which must not carry it) - the first as well. Returns which."""
        version = cls._version(db)
        if version != VERSION and not (earlier and version == 1):
            raise ValueError("the usage store has a schema it did not make")
        return version

    @contextmanager
    def _transaction(self):
        try:
            # The store must exist: usage never starts again from nothing in a newly made file.
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
                yield db
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("A usage call was refused by the store (%s).", why(exc))
            raise UsageRefused("storage") from None

    @staticmethod
    def _standing(db, account):
        # The trial, once: the partial unique index refuses a second, and the first read gives it.
        db.execute("INSERT OR IGNORE INTO grants (account,kind,micro_usd,at,note) VALUES (?,'trial',?,?,'')",
                   (account, TRIAL_MICRO_USD, _now()))
        granted = db.execute("SELECT COALESCE(SUM(micro_usd),0) FROM grants WHERE account=?", (account,)).fetchone()[0]
        spent = db.execute("SELECT COALESCE(SUM(micro_usd),0) FROM calls WHERE account=?", (account,)).fetchone()[0]
        # 53h4h: what a sweep carried counts as it did before it went.
        carried = db.execute("SELECT granted, spent FROM carried WHERE account=?", (account,)).fetchone()
        if carried is not None:
            granted, spent = granted + carried[0], spent + carried[1]
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
            # 53h4h: what a sweep carried is in the overall numbers, as it was before it went, and said apart; the groupings by
            # model and by outcome are of the calls kept.
            held, c_calls, c_cost, c_unknown, c_granted = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(calls),0),COALESCE(SUM(spent),0),COALESCE(SUM(not_established),0),"
                "COALESCE(SUM(granted),0) FROM carried WHERE calls > 0 OR granted > 0").fetchone()
            return {"accounts": accounts, "granted": granted + c_granted, "calls": calls + c_calls, "micro_usd": cost + c_cost,
                    "not_established": unknown + c_unknown, "by_model": grouped("model"), "by_outcome": grouped("outcome"),
                    "carried": {"accounts": held, "calls": c_calls, "micro_usd": c_cost, "not_established": c_unknown,
                                "granted": c_granted}}

    def sweep(self, before: datetime) -> dict:
        """D241: the calls and the operator's grants written before `before` go, each account's sums carried first, so that no
        balance or total changes; each account's trial row is kept whatever its age, so that none is given twice. In one
        transaction: carried and removed together, or neither. Returns how many of each went."""
        if not isinstance(before, datetime) or before.utcoffset() is None:
            raise ValueError("a sweep is asked for at a time that has its zone")
        cutoff = before.astimezone(timezone.utc).isoformat(timespec="seconds")  # the text the rows are written in
        carry = ("INSERT INTO carried (account,granted,spent,calls,not_established,through) VALUES (?,?,?,?,?,?) "
                 "ON CONFLICT(account) DO UPDATE SET granted=granted+excluded.granted, spent=spent+excluded.spent, "
                 "calls=calls+excluded.calls, not_established=not_established+excluded.not_established, "
                 "through=MAX(through, excluded.through)")
        with self._transaction() as db:
            for account, spent, calls, unknown in db.execute(
                    "SELECT account, COALESCE(SUM(micro_usd),0), COUNT(*), COALESCE(SUM(micro_usd IS NULL),0) FROM calls "
                    "WHERE at < ? GROUP BY account", (cutoff,)).fetchall():
                db.execute(carry, (account, 0, spent, calls, unknown, cutoff))
            for account, granted in db.execute(
                    "SELECT account, SUM(micro_usd) FROM grants WHERE at < ? AND kind <> 'trial' GROUP BY account",
                    (cutoff,)).fetchall():
                db.execute(carry, (account, granted, 0, 0, 0, cutoff))
            calls = db.execute("DELETE FROM calls WHERE at < ?", (cutoff,)).rowcount
            grants = db.execute("DELETE FROM grants WHERE at < ? AND kind <> 'trial'", (cutoff,)).rowcount
        return {"calls": calls, "grants": grants}
