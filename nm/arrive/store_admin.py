"""The Admin area's own record: what admins did, and who just confirmed their password (plan AN.46, piece 46c; D116, D126).

ONE SIDECAR FILE, admin.sqlite, beside the usage and turn-attempt stores and made the way they are (a file published whole or not
at all, a schema it will not open if it did not make it, BEGIN IMMEDIATE for every use).

THE AUDIT ONLY GROWS. Each entry holds the time, the acting admin, what was done, the target (an account's email or a batch), the
reason the admin typed, how it ended, and a fingerprint that includes the previous entry's. The file's own triggers refuse any
UPDATE or DELETE, so not even a statement run against the file can change an entry, and `verify` recomputes every fingerprint,
so a file edited with those triggers taken away and put back shows; one whose triggers are left off is refused outright, like any
file whose schema this store did not make. THIS IS TAMPER-EVIDENT AND NOT TAMPER-PROOF: anyone who can rewrite the
server's files can rewrite the whole chain, and cutting off its last entries leaves a chain that still follows. The newest
fingerprint `verify` returns is what to write down elsewhere to catch that. The page says so.

NOTHING OF AN ADVOCATE'S WORK CAN BE WRITTEN HERE. An entry names an account or a batch and holds a one-line reason of at most 200
characters; an action and an outcome are short names. The password is never passed to this store: the edge checks it through the
directory's own sign-in check and tells this store only that the session's holder just did, for ten minutes (D116).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from nm.arrive.admin_port import AdminUnavailable, AuditEntry, ChainCheck
from nm.shared.sqlite_creation import create_if_absent, why

_log = logging.getLogger("nm.admin")

VERSION = 1
#: How long one password check covers the admin's changes (D116).
CONFIRMATION_MINUTES = 10
#: The most entries one read returns.
READ_LIMIT = 500
_FIRST = "0" * 64
_SHORT_NAME = re.compile(r"[a-z][a-z0-9 ._:/-]{0,63}\Z")
_SESSION = re.compile(r"[0-9a-f]{64}\Z")
_SQL = {
    ("table", "audit"): """CREATE TABLE audit (
        id INTEGER PRIMARY KEY,
        at TEXT NOT NULL,
        actor TEXT NOT NULL CHECK(length(actor) BETWEEN 1 AND 254),
        action TEXT NOT NULL,
        target TEXT NOT NULL CHECK(length(target) BETWEEN 1 AND 254),
        reason TEXT NOT NULL CHECK(length(reason) <= 200),
        outcome TEXT NOT NULL,
        previous TEXT NOT NULL CHECK(length(previous)=64),
        fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64)
    )""",
    ("trigger", "audit_is_never_changed"): """CREATE TRIGGER audit_is_never_changed BEFORE UPDATE ON audit
        BEGIN SELECT RAISE(ABORT, 'the audit only grows'); END""",
    ("trigger", "audit_is_never_removed"): """CREATE TRIGGER audit_is_never_removed BEFORE DELETE ON audit
        BEGIN SELECT RAISE(ABORT, 'the audit only grows'); END""",
    ("table", "confirmations"): """CREATE TABLE confirmations (
        session TEXT PRIMARY KEY NOT NULL CHECK(length(session)=64),
        until TEXT NOT NULL
    )""",
}


def _flat(sql):
    return " ".join((sql or "").split())


def _line(value, name, *, limit, allow_empty=False) -> str:
    """One line of text with no control characters, within its limit."""
    if (not isinstance(value, str) or len(value) > limit or (not value.strip() and not allow_empty)
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(f"an audit entry's {name} is one line of at most {limit} characters")
    return value.strip()


def _fingerprint(number, at, actor, action, target, reason, outcome, previous) -> str:
    body = json.dumps([number, at, actor, action, target, reason, outcome, previous], separators=(",", ":"))
    return hashlib.sha256(("nm-admin-audit:" + body).encode("utf8")).hexdigest()


def _checked(entry) -> tuple:
    if not isinstance(entry, AuditEntry):
        raise ValueError("an audit entry is an AuditEntry")
    actor = _line(entry.actor, "actor", limit=254)
    action = _line(entry.action, "action", limit=64)
    outcome = _line(entry.outcome, "outcome", limit=64)
    if not _SHORT_NAME.fullmatch(action) or not _SHORT_NAME.fullmatch(outcome):
        raise ValueError("an audit entry's action and outcome are short names")
    return (actor, action, _line(entry.target, "target", limit=254),
            _line(entry.reason, "reason", limit=200, allow_empty=True), outcome)


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text)


class FileAdminRecord:
    """The Admin record of one installation; see the module's note."""

    def __init__(self, path, *, clock: Callable[[], datetime] | None = None):
        self.path = Path(path).resolve()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        try:
            create_if_absent(self.path, self._build)
            with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                self._schema(db)
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The admin record could not be opened (%s).", why(exc))
            raise AdminUnavailable("storage") from None

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
            raise ValueError("the admin record has a schema it did not make")

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
            _log.warning("The admin record refused a call (%s).", why(exc))
            raise AdminUnavailable("storage") from None

    # --------------------------------------------------------------------- audit ---

    def append(self, entry: AuditEntry) -> AuditEntry:
        actor, action, target, reason, outcome = _checked(entry)
        at = self._clock().astimezone(timezone.utc).isoformat(timespec="seconds")
        with self._transaction() as db:
            last = db.execute("SELECT id,fingerprint FROM audit ORDER BY id DESC LIMIT 1").fetchone()
            number, previous = (last[0] + 1, last[1]) if last else (1, _FIRST)
            fingerprint = _fingerprint(number, at, actor, action, target, reason, outcome, previous)
            db.execute("INSERT INTO audit (id,at,actor,action,target,reason,outcome,previous,fingerprint) "
                       "VALUES (?,?,?,?,?,?,?,?,?)",
                       (number, at, actor, action, target, reason, outcome, previous, fingerprint))
        return AuditEntry(_time(at), actor, action, target, reason, outcome, number, fingerprint)

    def entries(self, *, limit: int = 100, before_id: int | None = None) -> tuple[AuditEntry, ...]:
        if type(limit) is not int or limit < 1 or (before_id is not None and type(before_id) is not int):
            raise ValueError("a read asks for a whole number of entries")
        limit = min(limit, READ_LIMIT)
        with self._transaction() as db:
            rows = db.execute(
                "SELECT id,at,actor,action,target,reason,outcome,fingerprint FROM audit "
                "WHERE (? IS NULL OR id < ?) ORDER BY id DESC LIMIT ?", (before_id, before_id, limit)).fetchall()
        return tuple(AuditEntry(_time(at), actor, action, target, reason, outcome, number, fingerprint)
                     for number, at, actor, action, target, reason, outcome, fingerprint in rows)

    def verify(self) -> ChainCheck:
        with self._transaction() as db:
            rows = db.execute("SELECT id,at,actor,action,target,reason,outcome,previous,fingerprint "
                              "FROM audit ORDER BY id").fetchall()
        previous = _FIRST
        for expected, (number, at, actor, action, target, reason, outcome, before, fingerprint) in enumerate(rows, 1):
            if (number != expected or before != previous
                    or fingerprint != _fingerprint(number, at, actor, action, target, reason, outcome, before)):
                return ChainCheck(False, len(rows), number)
            previous = fingerprint
        return ChainCheck(True, len(rows), None, previous if rows else "")

    # --------------------------------------------------------- password checks ---

    def confirm_password(self, session: str, now: datetime) -> datetime:
        if not isinstance(session, str) or not _SESSION.fullmatch(session):
            raise ValueError("a password check belongs to one session")
        # Whole seconds, so the stored text compares in time order.
        now = now.astimezone(timezone.utc).replace(microsecond=0)
        until = now + timedelta(minutes=CONFIRMATION_MINUTES)
        with self._transaction() as db:
            # A check that has lapsed is of no use to anyone; clear them as new ones are made.
            db.execute("DELETE FROM confirmations WHERE until <= ?", (now.isoformat(),))
            db.execute("INSERT INTO confirmations (session,until) VALUES (?,?) "
                       "ON CONFLICT(session) DO UPDATE SET until=excluded.until", (session, until.isoformat()))
        return until

    def password_confirmed(self, session: str, now: datetime) -> bool:
        if not isinstance(session, str) or not _SESSION.fullmatch(session):
            return False
        with self._transaction() as db:
            row = db.execute("SELECT until FROM confirmations WHERE session=?", (session,)).fetchone()
        return bool(row) and _time(row[0]) > now.astimezone(timezone.utc)
