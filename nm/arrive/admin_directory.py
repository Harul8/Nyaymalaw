"""The directory as the Admin area reads it: every account in one pass, with its sessions (plan AN.46, piece 46d; D118-D119).

A SUBCLASS OF THE DIRECTORY, NOT A CHANGE TO IT. It lists accounts, which the directory port deliberately cannot (A1), so it is a
separate class that only the Admin routes are given; the instance the sign-in edge holds is the plain `FileDirectory`. It inherits
the directory's own way of opening an account's files and sealed parts, so a record is read exactly as sign-in reads it.

READS ONLY. Unlike `FileDirectory._read`, which rewrites an older sealed account in the open as it goes past, this reads the file
and leaves it alone: an admin opening the list changes no account. It returns the fields an admin may see (`AdminAccount`) and
nothing else: no credential, no security counters, no token, no source address, no consent text.

A RECORD THAT WILL NOT OPEN IS SHOWN, NOT SKIPPED. An account whose file cannot be read is listed with `readable=False`; a part of
an account that cannot be read (its approval, its AI permission) is None, which the page shows as unknown and never as "none";
session files that will not open are counted, because the sessions shown may then be incomplete.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from nm.arrive.admin_port import (AdminAccount, AdminUnavailable, DirectoryListing, SessionLine, WaitingRegistration)
from nm.arrive.advocate_contracts import AdvocateIdentity, canonical_id
from nm.arrive.professional_access_contracts import ProfessionalApproval
from nm.arrive.store_directory import FileDirectory

#: The most sessions listed for one account (the newest); older ones are history the page does not need.
SESSIONS_SHOWN = 20
_PENDING = "pending-accounts.sqlite3"


def _when(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.utcoffset() is not None else None


class AdminFileDirectory(FileDirectory):
    """The directory's files, listed for the Admin area. See the module's note."""

    def _peek(self, path: Path) -> dict:
        """The account document, plain or sealed, with nothing rewritten. Raises if it will not open."""
        raw = path.read_bytes()
        try:
            doc = json.loads(raw.decode("utf8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            doc = json.loads(self._cipher.decrypt(raw).decode("utf8"))
        if not isinstance(doc, dict):
            raise ValueError("account record must be an object")
        return doc

    def _account_files(self) -> list[Path]:
        try:
            ordinary = [p for p in self._advocates.glob("*.nm") if not p.name.startswith("invalid-")]
            long_ids = list(self._advocates_by_digest.glob("*.nm"))
        except OSError as exc:
            raise AdminUnavailable("the accounts could not be listed") from exc
        return sorted(ordinary + long_ids)

    def _sessions_by_account(self) -> tuple[dict[str, list], int]:
        found: dict[str, list] = {}
        unreadable = 0
        try:
            paths = sorted(self._sessions.glob("*.nm"))
        except OSError as exc:
            raise AdminUnavailable("the sessions could not be listed") from exc
        for path in paths:
            session = self._read_session(path.stem)
            if session is None:
                unreadable += 1
            else:
                found.setdefault(canonical_id(session.advocate_id), []).append(session)
        return found, unreadable

    def _professional(self, doc: dict, account_id: str, now: datetime) -> tuple[str | None, datetime | None]:
        try:
            rows = self._professional_records(doc, account_id)
            if not rows:
                return "none", None
            approval = ProfessionalApproval.from_record(rows[-1])
            if approval is None:
                return None, None
            if approval.revoked_at is not None:
                return "revoked", approval.valid_until
            if approval.permits(account_id, now):
                return "approved", approval.valid_until
            return ("expired" if now >= approval.valid_until else "none"), approval.valid_until
        except Exception:  # noqa: BLE001 -- a record that will not open is unknown, not "none"
            return None, None

    def _sharing(self, doc: dict, account_id: str, now: datetime) -> tuple[bool | None, str | None]:
        try:
            rows = self._model_permissions(doc, account_id)
            if not rows:
                return False, None
            return rows[-1].permits(account_id, now), rows[-1].notice_version
        except Exception:  # noqa: BLE001 -- unknown, not "off"
            return None, None

    def _account(self, path: Path, sessions_of: dict[str, list], now: datetime) -> AdminAccount:
        try:
            doc = self._peek(path)
            identity = AdvocateIdentity(**doc["identity"])
        except Exception:  # noqa: BLE001 -- the file will not open; it is listed as such
            return AdminAccount(id=path.stem, readable=False)
        if canonical_id(identity.id) != identity.id or (path.parent == self._advocates and identity.id != path.stem):
            return AdminAccount(id=path.stem, readable=False)
        state, until = self._professional(doc, identity.id, now)
        sharing, notice = self._sharing(doc, identity.id, now)
        mine = sorted(sessions_of.get(identity.id, ()), key=lambda s: s.issued_at, reverse=True)
        lines = tuple(SessionLine(s.client_label, s.issued_at, s.expires_at, s.last_active_at, s.live_at(now))
                      for s in mine[:SESSIONS_SHOWN])
        activity = [s.last_active_at for s in mine if s.last_active_at is not None]
        return AdminAccount(
            id=identity.id, readable=True, name=identity.name, enrolment=identity.enrolment,
            firm_id=identity.firm_id, created_at=_when(doc.get("created_at")),
            professional_state=state, professional_valid_until=until,
            ai_sharing=sharing, ai_notice_version=notice,
            last_sign_in=max((s.issued_at for s in mine), default=None),
            last_active=max(activity, default=None), sessions=lines,
            suspended=bool(doc.get("suspended")))

    def _waiting(self, now: datetime) -> tuple[tuple[WaitingRegistration, ...], bool]:
        path = self._root / _PENDING
        if not path.exists():
            return (), True
        try:
            if self._cipher.scheme != "fernet":
                return (), False
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
                rows = db.execute("SELECT sealed FROM pending WHERE expires > ?", (now.timestamp(),)).fetchall()
            found = []
            for (sealed,) in rows:
                doc = json.loads(self._cipher.decrypt(sealed))
                if doc.get("used"):
                    continue
                who = doc.get("identity") or {}
                found.append(WaitingRegistration(str(who.get("email") or who.get("id") or ""), str(who.get("name") or ""),
                                                 _when(doc.get("created")), _when(doc.get("expires"))))
            return tuple(sorted(found, key=lambda w: (w.requested_at is None, w.requested_at, w.email))), True
        except Exception:  # noqa: BLE001 -- unknown, not empty
            return (), False

    def listing(self, now: datetime) -> DirectoryListing:
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("the listing is made at a time that has its zone")
        sessions_of, unreadable_sessions = self._sessions_by_account()
        accounts = tuple(sorted((self._account(path, sessions_of, now) for path in self._account_files()),
                                key=lambda a: (not a.readable, a.id)))
        waiting, waiting_readable = self._waiting(now)
        return DirectoryListing(accounts, waiting, unreadable_sessions, waiting_readable)
