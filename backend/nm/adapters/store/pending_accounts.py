"""Sealed pending account records, with one transactional owner of code limits.

No active account exists until mailbox proof succeeds. SQLite serialises workers;
the directory's exclusive account creation prevents replacement on activation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta

from cryptography.fernet import InvalidToken

from nm.domain.account_confirmation import (
    CODE_ATTEMPTS,
    CODE_MINUTES,
    PENDING_HOURS,
    REFUSED,
    REQUESTS_PER_HOUR,
    RESEND_SECONDS,
    ConfirmationRefused,
)
from nm.domain.advocate import (
    AdvocateIdentity,
    Consent,
    Credential,
    Enrolment,
    registration_email,
    token_fingerprint,
)
from nm.ports.directory import AlreadyEnrolled, RegistrationUnavailable

MAX_PENDING = 10_000


class PendingAccounts:
    def __init__(self, directory):
        self.directory = directory
        self.path = directory._root / "pending-accounts.sqlite3"
        self.cipher = directory._cipher

    @contextmanager
    def transaction(self):
        if self.cipher.scheme != "fernet":
            raise RegistrationUnavailable("Account confirmation is unavailable.")
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute(
                    "CREATE TABLE IF NOT EXISTS pending "
                    "(address TEXT PRIMARY KEY, sealed BLOB NOT NULL, expires REAL NOT NULL)"
                )
                db.execute("BEGIN IMMEDIATE")
                yield db
        except (sqlite3.Error, InvalidToken, json.JSONDecodeError) as exc:
            raise RegistrationUnavailable("Account confirmation is unavailable.") from exc

    def address_key(self, email):
        return hashlib.sha256(registration_email(email).encode()).hexdigest()

    def read(self, db, email):
        row = db.execute(
            "SELECT sealed FROM pending WHERE address=?", (self.address_key(email),)
        ).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else None

    def write(self, db, email, doc):
        db.execute(
            "INSERT OR REPLACE INTO pending VALUES (?,?,?)",
            (
                self.address_key(email),
                self.cipher.encrypt(json.dumps(doc).encode()),
                datetime.fromisoformat(doc["expires"]).timestamp(),
            ),
        )

    @staticmethod
    def new_code(doc, now):
        doc.update(
            code=f"{secrets.randbelow(1_000_000):06d}",
            attempts=0,
            code_expires=(now + timedelta(minutes=CODE_MINUTES)).isoformat(),
        )

    def begin(self, enrolment, now):
        email = enrolment.identity.email
        flow = secrets.token_urlsafe(32)
        with self.transaction() as db:
            db.execute("DELETE FROM pending WHERE expires <= ?", (now.timestamp(),))
            current = self.read(db, email)
            if self.directory.identity(email) is not None or (
                current and now < datetime.fromisoformat(current["expires"])
            ):
                # Exactly the same public outcome; never overwrite an existing
                # credential or renew someone else's pending reservation.
                return {"flow": flow, "code": None}
            if (
                current is None
                and db.execute("SELECT COUNT(*) FROM pending").fetchone()[0] >= MAX_PENDING
            ):
                raise RegistrationUnavailable("Registration is temporarily unavailable.")
            doc = {
                "identity": enrolment.identity.as_dict(),
                "credential": self.directory._credential_record(enrolment.credential),
                "consent": enrolment.consent.as_dict(),
                "created": now.isoformat(),
                "expires": (now + timedelta(hours=PENDING_HOURS)).isoformat(),
                "flow": token_fingerprint(flow),
                "requests": [now.isoformat()],
                "used": False,
                "activation_id": secrets.token_hex(24),
            }
            self.new_code(doc, now)
            self.write(db, email, doc)
            return {"flow": flow, "code": doc["code"]}

    def resend(self, email, now):
        with self.transaction() as db:
            doc = self.read(db, email)
            if not doc or doc["used"] or now >= datetime.fromisoformat(doc["expires"]):
                return None
            requests = [
                datetime.fromisoformat(t)
                for t in doc["requests"]
                if now - datetime.fromisoformat(t) < timedelta(hours=1)
            ]
            retry = (
                max(0, RESEND_SECONDS - int((now - requests[-1]).total_seconds()))
                if requests
                else 0
            )
            if len(requests) >= REQUESTS_PER_HOUR:
                retry = max(
                    retry, int((requests[0] + timedelta(hours=1) - now).total_seconds()) + 1
                )
            if retry:
                # Do not expose per-address state: the route always returns
                # the same acknowledgement. No code or attempt limit changes.
                return None
            if doc["attempts"] >= CODE_ATTEMPTS or now >= datetime.fromisoformat(
                doc["code_expires"]
            ):
                self.new_code(doc, now)
            doc["requests"] = [t.isoformat() for t in requests] + [now.isoformat()]
            self.write(db, email, doc)
            return doc["code"]

    def cancel(self, email, flow, now):
        with self.transaction() as db:
            doc = self.read(db, email)
            if (not doc or doc['used'] or now >= datetime.fromisoformat(doc['expires'])
                    or not hmac.compare_digest(doc['flow'], token_fingerprint(flow))):
                return False
            db.execute('DELETE FROM pending WHERE address=?', (self.address_key(email),))
            return True

    def confirm(self, email, code, flow, credential, now):
        refused = None
        identity = None
        with self.transaction() as db:
            doc = self.read(db, email)
            if (
                not doc
                or doc["used"]
                or now >= datetime.fromisoformat(doc["expires"])
                or now >= datetime.fromisoformat(doc["code_expires"])
                or doc["attempts"] >= CODE_ATTEMPTS
            ):
                refused = REFUSED
            elif not hmac.compare_digest(doc["code"], code):
                doc["attempts"] += 1
                self.write(db, email, doc)
                refused = REFUSED
            elif (
                not hmac.compare_digest(doc["flow"], token_fingerprint(flow or ""))
                and credential is None
            ):
                refused = (
                    "Choose a new password to confirm from this browser. No account was activated."
                )
            else:
                identity = AdvocateIdentity(**doc["identity"])
                consent = Consent(
                    doc["consent"]["notice_version"],
                    datetime.fromisoformat(doc["consent"]["given_at"]),
                    True,
                )
                chosen = credential or Credential(**doc["credential"])
                try:
                    self.directory.enrol(
                        Enrolment(
                            identity,
                            chosen,
                            now,
                            consent,
                            mailbox_confirmed_at=now,
                            activation_id=doc["activation_id"],
                        )
                    )
                except AlreadyEnrolled:
                    # A crash after the atomic account publication but before
                    # this transaction commits is an interrupted activation,
                    # not permission to replace the now-active credential.
                    existing = self.directory._read(identity.id)
                    if not existing or existing.get("activation_id") != doc["activation_id"]:
                        refused = REFUSED
                doc["used"] = True
                # Do not retain the active code or pending password hash after
                # activation. The minimal used marker refuses replays.
                doc["code"] = ""
                doc["credential"] = {}
                self.write(db, email, doc)
        # Wrong attempts must commit before reporting failure.
        if refused:
            raise ConfirmationRefused(refused)
        return identity
