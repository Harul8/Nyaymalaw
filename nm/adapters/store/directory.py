"""A1 — the file-backed directory. Sealed with the same key as the matters.

WHY THE SAME CIPHER AND NOT A SECOND ONE
------------------------------------------
CLAUDE.md §4 asks what refuses the second copy. Two encryption paths in one
product means one of them gets hardened and the other does not, and the one
that does not is discovered by an incident. `_Cipher` is imported from the
matter store rather than reimplemented, so there is exactly one answer to
"how is data at rest sealed here".

WHAT IS ON DISK AND WHAT IS NOT
---------------------------------
Advocates and their derived credentials; sessions by token FINGERPRINT. The
password is never written, the token is never written, and a stolen store is
therefore not a set of live logins.

FAILURES ARE RECORDED HERE, NOT RETURNED
------------------------------------------
`authenticate` returns `None` for an unknown advocate and for a wrong
password, and writes WHICH to the audit line. The distinction is exactly what
the caller must not learn and exactly what an operator needs.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from nm.adapters.store.file_store import _Cipher
from nm.domain.advocate import (
    AdvocateIdentity,
    Credential,
    Enrolment,
    Session,
    dummy,
    open_session,
    token_fingerprint,
)
from nm.domain.traceability import implements
from nm.ports.directory import AlreadyEnrolled  # noqa: F401


@implements("A1")
class FileDirectory:
    def __init__(self, root: str | Path, key: str | None = None) -> None:
        self._root = Path(root)
        self._advocates = self._root / "advocates"
        self._sessions = self._root / "sessions"
        self._audit = self._root / "auth.log"
        self._advocates.mkdir(parents=True, exist_ok=True)
        self._sessions.mkdir(parents=True, exist_ok=True)
        import os
        self._cipher = _Cipher(
            key if key is not None else os.environ.get("NM_MATTER_KEY", ""))

    # ------------------------------------------------------------ advocates ---

    def _advocate_path(self, advocate_id: str) -> Path:
        return self._advocates / f"{advocate_id}.nm"

    def enrol(self, enrolment: Enrolment) -> None:
        path = self._advocate_path(enrolment.identity.id)
        if path.exists():
            raise AlreadyEnrolled(
                f"{enrolment.identity.id} is already enrolled. Overwriting "
                f"would replace a credential without anyone deciding to.")
        blob = {
            "identity": enrolment.identity.as_dict(),
            "credential": {
                "algorithm": enrolment.credential.algorithm,
                "salt": enrolment.credential.salt,
                "hash": enrolment.credential.hash,
                "n": enrolment.credential.n,
                "r": enrolment.credential.r,
                "p": enrolment.credential.p,
            },
            "created_at": enrolment.created_at.isoformat(),
        }
        path.write_bytes(self._cipher.encrypt(
            json.dumps(blob, indent=2).encode("utf8")))

    def _read(self, advocate_id: str) -> dict | None:
        path = self._advocate_path(advocate_id)
        if not path.exists():
            return None
        try:
            return json.loads(self._cipher.decrypt(path.read_bytes()).decode("utf8"))
        except Exception as exc:  # noqa: BLE001
            # A RECORD THAT WILL NOT OPEN IS NOT AN ABSENT ONE, and the
            # difference is only visible to the operator. The caller still
            # gets the single failure A1 requires.
            self._note(advocate_id, f"record unreadable: {type(exc).__name__}")
            return None

    def identity(self, advocate_id: str) -> AdvocateIdentity | None:
        doc = self._read(advocate_id)
        return AdvocateIdentity(**doc["identity"]) if doc else None

    def authenticate(self, advocate_id: str,
                     password: str) -> AdvocateIdentity | None:
        doc = self._read(advocate_id)
        if doc is None:
            # THE COST IS PAID ANYWAY. Returning here without deriving would
            # make an unknown advocate answer in microseconds and a wrong
            # password in tens of milliseconds — the same oracle A1's second
            # NEVER forbids, wearing a stopwatch instead of a message.
            dummy().verify(password)
            self._note(advocate_id, "no such advocate")
            return None

        credential = Credential(**doc["credential"])
        if not credential.verify(password):
            self._note(advocate_id, "wrong password")
            return None
        self._note(advocate_id, "authenticated")
        return AdvocateIdentity(**doc["identity"])

    # ------------------------------------------------------------- sessions ---

    def _session_path(self, fingerprint: str) -> Path:
        return self._sessions / f"{fingerprint}.nm"

    def open_session(self, advocate_id: str, device: str,
                     now: datetime) -> str:
        token, session = open_session(advocate_id, device, now)
        self._write_session(session)
        return token

    def _write_session(self, session: Session) -> None:
        self._session_path(session.token_fingerprint).write_bytes(
            self._cipher.encrypt(json.dumps({
                "token_fingerprint": session.token_fingerprint,
                "advocate_id": session.advocate_id,
                "device": session.device,
                "issued_at": session.issued_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "ended_because": session.ended_because,
            }, indent=2).encode("utf8")))

    def _read_session(self, fingerprint: str) -> Session | None:
        path = self._session_path(fingerprint)
        if not path.exists():
            return None
        try:
            d = json.loads(self._cipher.decrypt(path.read_bytes()).decode("utf8"))
        except Exception:  # noqa: BLE001 -- an unopenable session is not a session
            return None
        return Session(
            token_fingerprint=d["token_fingerprint"],
            advocate_id=d["advocate_id"],
            device=d["device"],
            issued_at=datetime.fromisoformat(d["issued_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
            ended_because=d.get("ended_because"),
        )

    def session(self, token: str, device: str,
                now: datetime) -> Session | None:
        if not (token or "").strip():
            return None
        session = self._read_session(token_fingerprint(token))
        if session is None:
            return None

        if not session.live_at(now):
            self._note(session.advocate_id,
                       f"session refused: {session.why_not(now)}")
            return None

        # A SESSION DOES NOT TRAVEL. A1's first NEVER is that a matter list is
        # not restored on a shared or borrowed device without
        # re-authentication — and a token that works from anywhere IS that
        # restoration, however short its life.
        if session.device != (device or "unknown-device"):
            self._note(session.advocate_id,
                       "session refused: presented from a different device")
            return None
        return session

    def close_session(self, token: str, why: str) -> None:
        fingerprint = token_fingerprint(token or "")
        session = self._read_session(fingerprint)
        if session is None:
            return
        # ENDED, NOT DELETED. A closed session that vanished would be
        # indistinguishable from one that never existed, and an operator
        # reading the audit could not tell a sign-out from a forged token.
        from dataclasses import replace
        self._write_session(replace(session, ended_because=why))

    # ---------------------------------------------------------------- audit ---

    def _note(self, advocate_id: str, what: str) -> None:
        """WHY IT FAILED, where the operator can read it and the caller cannot.

        Appended in plaintext deliberately: this is an operational log about
        access attempts, not client material, and an audit nobody can read
        without the key is an audit nobody reads.
        """
        try:
            with self._audit.open("a", encoding="utf8") as fh:
                fh.write(f"{datetime.now().isoformat()}\t{advocate_id}\t{what}\n")
        except OSError:
            # Never fail a login because the log is unwritable. The record is
            # worth having and it is not worth locking an advocate out for.
            pass
