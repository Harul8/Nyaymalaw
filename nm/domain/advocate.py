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

from nm.domain.text import blank, clean, refuses_blank_text

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


def canonical_id(value: str | None) -> str:
    """THE ONE FORM AN ADVOCATE ID TAKES. Stripped, and lower-cased.

    WHY LOWER-CASING IS NOT COSMETIC HERE. The id is the email on a
    self-service registration, and `FileDirectory` names the record file after
    it. So `R.Kumar@X.com` and `r.kumar@x.com` are one advocate on Windows,
    where the filesystem folds case for you, and TWO on Linux, where it does
    not -- an advocate who registers with a capital signs in on the developer's
    machine and cannot sign in on the server.

    The register route already lower-cased the email. That was one door
    deciding the canonical form while the sign-in door, the identity lookup
    and the failed-attempt note all took the string as typed: the same rule
    with four owners, three of which did not know it existed.

    ENFORCED BY THE TYPE rather than applied by each caller, because applying
    it is what four callers were already supposed to be doing. The constructor
    refuses a non-canonical id, so a second form cannot be enrolled at all --
    and `FileDirectory` folds what comes off the wire, so a capital an
    advocate types is not a different advocate.
    """
    return clean(value).lower()


@refuses_blank_text("enrolment", "practice", "firm_id")
@dataclass(frozen=True)
class AdvocateIdentity:
    """A1's PRODUCES contract. Referenced by every later record.

    THREE FIELDS BECAME OPTIONAL ON 6 SEPTEMBER 2026, on the advocate's
    instruction, so self-service registration asks for a name, an email and a
    password and nothing else. `id`, `name` and `email` remain non-blank: an
    advocate with no id has no file, and one with no email cannot sign in.

    WHAT A BLANK `firm_id` COSTS, recorded here because it will be paid later.
    B3's conflicts registry is SCOPED BY THE FIRM: it is what detects the
    product advising both sides of one dispute. An advocate with no firm is in
    a registry of one, and a screen run against a registry of one finds
    nothing — which is not the same as there being nothing to find.

    THE SCREEN IS NOT BUILT YET (`nm.core.screens` is declared UNWIRED), so
    this weakens no live control today. When it is built, a blank firm must
    make the conflicts screen report NOT_ASSESSED and never CLEAR. That is the
    three-state rule this whole build turns on, and it is written down now
    rather than discovered by whoever wires the screen.
    """

    id: str
    name: str
    enrolment: str = ""
    practice: str = ""
    firm_id: str = ""
    email: str = ""
    """How to reach them. OPTIONAL, and that is not an oversight.

    Added for self-service registration, where the email is what an advocate
    types to sign in. Every advocate enrolled by `tools/enrol.py` before this
    field existed has none, and requiring it would have made those records
    unreadable -- a field added to a persisted type is a field every OLD
    record lacks, which is the migration this build has not needed until now.

    IT IS ALSO THE ID, on a self-service registration, and the alternative was
    considered and rejected. A generated id would be stable when an email
    changes -- which is the textbook answer -- but this product's ids are
    already human-chosen strings (`adv_scenarios`, `adv_demo`, whatever
    `tools/enrol.py --id` was given), and an advocate cannot sign in with an
    identifier nobody showed them.

    So the id is the normalised email and the trade is stated rather than
    hidden: if an advocate changes email, their id does not follow, and the
    file store keys every matter on the id. That is a migration whichever
    design is chosen, and it is a smaller problem than a login handle the
    advocate never sees.
    """

    def __post_init__(self) -> None:
        if self.id != canonical_id(self.id):
            raise ValueError(
                f"advocate id {self.id!r} is not in canonical form "
                f"({canonical_id(self.id)!r}). Two spellings of one id are two "
                f"advocates with two files on a case-sensitive filesystem and "
                f"one advocate on a case-insensitive one, which is a defect "
                f"that only appears in production. Use `canonical_id`.")

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "enrolment": self.enrolment,
                "practice": self.practice, "firm_id": self.firm_id,
                "email": self.email}


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

    THE RULE IS ENFORCED HERE AND NOT AT THE EDGE, because the edge is not the
    only caller — an enrolment tool, a migration, a registration form and
    every test fixture reach this, and a rule that lives at one door is a rule
    with a back one.

    EIGHT CHARACTERS WITH FOUR CLASSES, from 6 September 2026 on the
    advocate's instruction. The trade is worth recording rather than
    pretending it is free: a twelve-character passphrase carries more entropy
    than an eight-character complex password, and complexity rules are what
    produce `Password1!`. Eight-plus-classes is the common standard and it is
    the advocate's product.

    WHAT DOES NOT CHANGE is that this is the only thing standing between one
    advocate's client file and another's, and the product still has no rate
    limit. The classes are checked as CHARACTER CATEGORIES rather than against
    a list of permitted symbols: a list would refuse a keyboard this product
    has never seen.
    """
    pw = password or ""
    if len(pw) < 8:
        raise ValueError(
            "a password under 8 characters is refused. This is the only thing "
            "standing between one advocate's client file and another's, and "
            "the product has no rate limit yet.")
    missing = [name for name, ok in (
        ("an upper-case letter", any(c.isupper() for c in pw)),
        ("a lower-case letter", any(c.islower() for c in pw)),
        ("a numeral", any(c.isdigit() for c in pw)),
        ("a special character", any(not c.isalnum() for c in pw)),
    ) if not ok]
    if missing:
        # NAMED, NOT COUNTED. "Does not meet complexity requirements" makes
        # the advocate guess which one; the list is the difference between a
        # rule and an obstacle.
        raise ValueError(
            "a password must contain " + ", ".join(missing[:-1])
            + (" and " if len(missing) > 1 else "") + missing[-1] + ".")
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
