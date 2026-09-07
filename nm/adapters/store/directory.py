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
    canonical_id,
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
        self._attempts = self._root / "attempts.log"
        self._advocates.mkdir(parents=True, exist_ok=True)
        self._sessions.mkdir(parents=True, exist_ok=True)
        import os
        self._cipher = _Cipher(
            key if key is not None else os.environ.get("NM_MATTER_KEY", ""))

    # ------------------------------------------------------------ advocates ---

    def _advocate_path(self, advocate_id: str) -> Path:
        """FOLDED HERE, once, for every door.

        `enrol`, `identity`, `authenticate` and the failed-attempt note all
        reach the store through this, so a capital an advocate types at
        sign-in is not a different advocate -- and cannot be, rather than
        being one that four call sites each remember not to make.

        `AdvocateIdentity` refuses a non-canonical id, so nothing can be
        enrolled under a second spelling either. Two mechanisms, one rule:
        the type refuses bad data going in, this folds queries coming from
        outside, and neither is sufficient alone.
        """
        return self._advocates / f"{canonical_id(advocate_id)}.nm"

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

    #: Why a sign-in failed, in the caller's vocabulary. THREE STATES.
    #:
    # `unreadable` is the one that is neither a wrong email nor a wrong
    # password: a record encrypted under a key the server no longer has.
    # It happened on 7 September 2026 -- an account enrolled under one
    # `NM_MATTER_KEY` and read under another -- and the advocate was told
    # their credentials were wrong. No amount of retyping fixes that.
    UNKNOWN = "unknown"
    WRONG_PASSWORD = "wrong_password"
    UNREADABLE = "unreadable"

    def _read(self, advocate_id: str) -> dict | None:
        path = self._advocate_path(advocate_id)
        self._last_failure = self.UNKNOWN
        if not path.exists():
            return None
        try:
            doc = json.loads(
                self._cipher.decrypt(path.read_bytes()).decode("utf8"))
            self._last_failure = None
            return doc
        except Exception as exc:  # noqa: BLE001
            # A RECORD THAT WILL NOT OPEN IS NOT AN ABSENT ONE. It was
            # visible only to the operator until the advocate was told
            # their credentials were wrong on a record that existed and
            # was correct.
            self._last_failure = self.UNREADABLE
            self._note(advocate_id, f"record unreadable: {type(exc).__name__}")
            return None

    def identity(self, advocate_id: str) -> AdvocateIdentity | None:
        doc = self._read(advocate_id)
        return AdvocateIdentity(**doc["identity"]) if doc else None

    # ------------------------------------------------- rate limiting ---
    #
    # BK-20/BK-18. The product had none, and the password validator said
    # so in a message the ADVOCATE reads -- *this is the only thing
    # standing between one advocate's client file and another's, and the
    # product has no rate limit yet*. Naming which of three things failed
    # at sign-in made that gap worth more, so the two landed together.

    def failures_since(self, advocate_id: str, source: str,
                       since: datetime) -> tuple[tuple, tuple] | None:
        """(this address's failures, this source's failures), or None.

        NONE MEANS THE LIMITER COULD NOT RUN -- not that there were no
        failures. The caller opens the door and reports it, because
        refusing every sign-in would be a self-inflicted outage; what it
        must not do is treat unreadable as clean, which is S1.
        """
        if not self._attempts.exists():
            return ((), ())
        try:
            raw = self._attempts.read_text(encoding="utf8",
                                           errors="replace")
        except OSError:
            return None

        wanted = canonical_id(advocate_id)
        mine: list = []
        here: list = []
        for line in raw.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            stamp, who, where = parts
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if when < since:
                continue
            if who == wanted:
                mine.append(when)
            if where == source:
                here.append(when)
        return (tuple(mine), tuple(here))

    def note_failure(self, advocate_id: str, source: str,
                     now: datetime) -> None:
        """One line per failed attempt. Never raises: a limiter that can
        break a sign-in is worse than one that misses a count.

        NO CLIENT MATERIAL. A timestamp, a folded id and a source -- the
        same shape the auth log beside it has held since slice 1.
        """
        try:
            with self._attempts.open("a", encoding="utf8") as fh:
                fh.write(f"{now.isoformat()}\t{canonical_id(advocate_id)}"
                         f"\t{source}\n")
        except OSError:
            pass

    def limiter_available(self) -> bool:
        """Whether the attempt log can be written. Reported at /api/health
        so a limiter that is not running is visible BEFORE an incident.
        """
        try:
            self._attempts.touch(exist_ok=True)
            return True
        except OSError:
            return False

    def why_last_sign_in_failed(self) -> str | None:
        """`unknown`, `wrong_password`, `unreadable`, or None.

        Read immediately after `authenticate` returns None. A field rather
        than a second return value because every other caller of
        `authenticate` wants the identity and nothing else, and widening
        the signature would make them all handle a reason they discard.
        """
        return getattr(self, "_last_failure", None)

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
            self._last_failure = self.WRONG_PASSWORD
            self._note(advocate_id, "wrong password")
            return None
        self._last_failure = None
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
