"""A1 — WHO IS ACTING. The identity every later record points back to.

WHY THIS TYPE HAD TO EXIST BEFORE ANYTHING ELSE HERE
-----------------------------------------------------
`AdvocateIdentity { id, name, enrolment, practice, firm_id }` was A1's whole
PRODUCES contract and there was no class, no field of it, and no credential
anywhere in `nm/`. `advocate_id` was a non-blank query parameter, and it was
the only thing between one advocate's client file and another's (B-082).

EVERY FIELD IS REQUIRED, AND `firm_id` MOST OF ALL
---------------------------------------------------
Tenet 4 requires the file to know who may instruct and tenet 20 requires a
decision to record who decided; an identity missing either is a file that
cannot answer those. And `firm_id` is what B3's conflicts registry is scoped
by — a blank firm is a conflict screen run against nothing, which is the
absent-input shape aimed at the one control that exists to stop the product
acting against a client it already acts for.

WHAT A CREDENTIAL IS, AND WHAT IT IS NOT
------------------------------------------
`Credential` holds a derived hash and never a password. It cannot be built
from one by accident: the constructor takes a hash, and `enrol()` is the only
way a password becomes one. `verify` is constant-time, and `dummy()` exists so
the key derivation runs even when the advocate does not — an identical error
returned instantly for an unknown advocate and slowly for a wrong password is
still an oracle, in the one place A1 says there must not be one.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from nm.domain.text import blank, refuses_blank_text

#: scrypt parameters. Deliberately named rather than defaulted inside the
#: call, because they are recorded WITH each credential: raising the cost
#: later must not make every existing credential unverifiable.
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
DK_LEN = 32

#: How long a session lives before A1's "re-authenticate after session expiry"
#: applies. Twelve hours: long enough for a working day, short enough that a
#: borrowed laptop is not a standing grant.
SESSION_HOURS = 12


@refuses_blank_text()
@dataclass(frozen=True)
class AdvocateIdentity:
    """A1's PRODUCES contract. Referenced by every later record."""

    id: str
    name: str
    enrolment: str
    practice: str
    firm_id: str

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "enrolment": self.enrolment,
                "practice": self.practice, "firm_id": self.firm_id}


@dataclass(frozen=True)
class Credential:
    """A derived hash and the parameters that produced it. Never a password.

    The parameters travel WITH the hash rather than being read from the module
    at verification time. Raising the cost is then an ordinary change: new
    credentials use the new cost, old ones still verify against the cost they
    were made with, and nobody is locked out by a constant being edited.
    """

    algorithm: str
    salt: str
    hash: str
    n: int = SCRYPT_N
    r: int = SCRYPT_R
    p: int = SCRYPT_P

    def __post_init__(self) -> None:
        if self.algorithm != "scrypt":
            raise ValueError(
                f"unknown credential algorithm {self.algorithm!r}. A "
                f"credential that cannot be verified must not be constructed "
                f"— it would fail closed at login and read as a wrong password.")
        for name in ("salt", "hash"):
            if blank(getattr(self, name)):
                raise ValueError(
                    f"a credential with no {name} verifies nothing. An empty "
                    f"hash compared against a derived one is a login that "
                    f"always fails, which reads to the advocate as a "
                    f"forgotten password rather than as a broken record.")

    def verify(self, password: str) -> bool:
        """Constant-time. `==` on a hash leaks it one byte at a time."""
        return hmac.compare_digest(
            self.hash, _derive(password, self.salt, self.n, self.r, self.p))


def enrol(password: str) -> Credential:
    """THE ONLY WAY A PASSWORD BECOMES A CREDENTIAL.

    A minimum length is enforced here rather than at the edge, because the
    edge is not the only caller — an enrolment tool, a migration and a test
    fixture all reach this, and a rule that lives at one door is a rule with a
    back one.
    """
    if len(password or "") < 12:
        raise ValueError(
            "a password under 12 characters is refused. This is the only "
            "thing standing between one advocate's client file and another's, "
            "and the product has no rate limit yet.")
    salt = secrets.token_hex(16)
    return Credential(algorithm="scrypt", salt=salt,
                      hash=_derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P))


def dummy() -> Credential:
    """A credential nothing can match, for the advocate who does not exist.

    A1: the error must be IDENTICAL whether the advocate has one matter or
    forty. Byte-identical is not enough — a login that returns instantly for
    an unknown advocate and takes 80ms for a wrong password discloses which
    accounts exist, in the one place A1 says nothing may. So the unknown case
    verifies against this and pays the same cost.
    """
    return Credential(algorithm="scrypt", salt="0" * 32,
                      hash=_derive(secrets.token_hex(32), "0" * 32,
                                   SCRYPT_N, SCRYPT_R, SCRYPT_P))


def _derive(password: str, salt: str, n: int, r: int, p: int) -> str:
    return hashlib.scrypt(
        (password or "").encode("utf8"), salt=bytes.fromhex(salt),
        n=n, r=r, p=p, dklen=DK_LEN).hex()


# --------------------------------------------------------------- sessions ---


def new_token() -> str:
    """256 bits from the OS. Never a uuid4 and never a counter."""
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """WHAT IS STORED. The token itself never touches disk.

    A store holding live tokens is a store whose theft is a login. A plain
    SHA-256 is right here and a slow KDF is not: the token is already 256 bits
    of OS randomness, so there is nothing to brute-force, and paying scrypt on
    every request would put a cost on reading a matter list.
    """
    return hashlib.sha256(token.encode("utf8")).hexdigest()


@dataclass(frozen=True)
class Session:
    """An issued session. Holds a fingerprint of the token, never the token."""

    token_fingerprint: str
    advocate_id: str
    device: str
    issued_at: datetime
    expires_at: datetime
    #: Why this session is no longer usable, or `None` while it is. A VALUE,
    #: because "expired" and "signed out" and "still live" are three states and
    #: a boolean can hold two.
    ended_because: str | None = None

    def __post_init__(self) -> None:
        for name in ("token_fingerprint", "advocate_id", "device"):
            if blank(getattr(self, name)):
                raise ValueError(f"a session with no {name} cannot be checked")
        if self.expires_at <= self.issued_at:
            raise ValueError(
                "a session that expires when it is issued is not a session")

    def live_at(self, now: datetime) -> bool:
        return self.ended_because is None and now < self.expires_at

    def why_not(self, now: datetime) -> str | None:
        """The REASON it cannot be used, for the log — never for the caller.

        A1's second NEVER: the response to a failed or expired credential must
        be identical. This exists so the reason is recorded where an operator
        can see it, and the edge returns the same words either way.
        """
        if self.ended_because:
            return self.ended_because
        if now >= self.expires_at:
            return f"expired at {self.expires_at.isoformat()}"
        return None


def open_session(advocate_id: str, device: str, now: datetime,
                 hours: int = SESSION_HOURS) -> tuple[str, Session]:
    """Returns the token ONCE, and a session that cannot reproduce it."""
    token = new_token()
    return token, Session(
        token_fingerprint=token_fingerprint(token),
        advocate_id=advocate_id,
        device=device or "unknown-device",
        issued_at=now,
        expires_at=now + timedelta(hours=hours),
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Enrolment:
    """An advocate and their credential, as one record on the way to the store."""

    identity: AdvocateIdentity
    credential: Credential
    created_at: datetime = field(default_factory=utcnow)
