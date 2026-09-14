"""A1 — WHO IS ACTING. The identity every later record points back to.

WHY THIS TYPE HAD TO EXIST BEFORE ANYTHING ELSE HERE
-----------------------------------------------------
`AdvocateIdentity { id, name, enrolment, practice, firm_id }` was A1's whole
PRODUCES contract and there was no class, no field of it, and no credential
anywhere in `backend/nm/`. `advocate_id` was a non-blank query parameter, and it was
the only thing between one advocate's client file and another's (B-082).

ACCOUNT IDENTITY IS NOT PROFESSIONAL APPROVAL
-----------------------------------------------
Public registration creates an email-named private account. Qualifications,
shared-firm membership and professional authority cannot be self-asserted at
that door. A blank firm stays blank: it is not evidence that an organisation's
conflicts register has been assessed. Approval has its own attributed record.

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
import re
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
INVITATION_HOURS = 48
RECOVERY_CODE_COUNT = 10

#: How long a fresh-authentication proof stays usable. Five minutes: long
#: enough to read a warning and press a button, short enough that a proof left
#: on a walked-away-from screen is not a standing licence to replace the
#: account's last-resort credential.
REAUTHENTICATION_MINUTES = 5

_UNSAFE_FILE_ID = re.compile(r'[<>:"/\\|?*]|[\x00-\x1f]')
_WINDOWS_DEVICE_IDS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)})


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


def registration_email(value: str | None) -> str:
    """Canonical storage-safe email handle, not a claim of mailbox ownership.

    NM accepts ASCII dot-atom mailboxes on a DNS hostname. Case is folded as
    for existing account IDs; plus tags and dots are never provider-normalised.
    Quoted/SMTPUTF8 addresses are not supported by this account namespace.
    """
    refused = "Enter a supported email address, such as name@example.com."
    if not isinstance(value, str) or len(value) > 320:
        raise ValueError(refused)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(refused)
    email = value.strip(" ").lower()
    if len(email) > 254 or email.count("@") != 1 or not email.isascii():
        raise ValueError(refused)
    local, host = email.split("@")
    atom = r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+"
    labels = host.split(".")
    if (not 1 <= len(local) <= 64
            or re.fullmatch(atom + r"(?:\." + atom + r")*", local) is None
            or len(labels) < 2
            or any(not 1 <= len(label) <= 63 or re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is None
                   for label in labels)
            or not advocate_id_is_storage_safe(email)):
        raise ValueError(refused)
    return email


def advocate_id_is_storage_safe(value: str | None) -> bool:
    """Whether an id can name one record without escaping or aliasing it."""
    candidate = canonical_id(value)
    if blank(candidate) or _UNSAFE_FILE_ID.search(candidate):
        return False
    if candidate.endswith((".", " ")):
        return False
    return candidate.split(".", 1)[0].upper() not in _WINDOWS_DEVICE_IDS


@refuses_blank_text("enrolment", "practice", "firm_id")
@dataclass(frozen=True)
class AdvocateIdentity:
    """A1's PRODUCES contract. Referenced by every later record.

    Public registration uses the canonical email as both id and provisional
    display name; enrolment, practice and firm remain empty. The optional
    operator invitation still supplies its bound roster identity. Neither
    route infers professional approval from these descriptive fields.

    WHAT A BLANK `firm_id` COSTS, recorded here because it will be paid later.
    B3's conflicts registry is SCOPED BY THE FIRM: it is what detects the
    product advising both sides of one dispute. An advocate with no firm is in
    a registry of one, and a screen run against a registry of one finds
    nothing — which is not the same as there being nothing to find.

    No default shared firm is invented. The consumer must preserve the scope
    and limits of whichever conflict assessment it actually performed.
    """

    id: str
    name: str
    enrolment: str = ""
    practice: str = ""
    firm_id: str = ""
    email: str = ""
    """How to reach them. OPTIONAL, and that is not an oversight.

    Added for self-service registration, where the email is what an advocate
    types to sign in. Every advocate enrolled by `backend/operations/enrol.py` before this
    field existed has none, and requiring it would have made those records
    unreadable -- a field added to a persisted type is a field every OLD
    record lacks, which is the migration this build has not needed until now.

    IT IS ALSO THE ID, on a self-service registration, and the alternative was
    considered and rejected. A generated id would be stable when an email
    changes -- which is the textbook answer -- but this product's ids are
    already human-chosen strings (`adv_scenarios`, `adv_demo`, whatever
    `backend/operations/enrol.py --id` was given), and an advocate cannot sign in with an
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
        if not advocate_id_is_storage_safe(self.id):
            raise ValueError(
                "advocate id cannot contain a path, control character or "
                "reserved device name. It must name one directory record.")

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

    Authentication and admission limits protect the served doors separately.
    The classes are checked as CHARACTER CATEGORIES rather than against
    a list of permitted symbols: a list would refuse a keyboard this product
    has never seen.
    """
    pw = password or ""
    if len(pw) < 8:
        raise ValueError(
            "a password under 8 characters is refused.")
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


# ------------------------------------------------- the generation model ---
#
# BK-31-AC20. FROZEN BEFORE ANY ROTATION PATH WAS WRITTEN, deliberately.
#
# Replacing a recovery-code set is a compare-and-set on state two other
# operations also move: `recover` changes the credential, and first-login
# provisioning creates a set. Without a counter, "has anything changed under
# me" can only be answered by comparing the material itself -- which means
# reading hashes at the edge to decide a race, and the one rule this file
# exists to keep is that credential material does not travel.
#
# TWO COUNTERS, NOT ONE, AND THAT IS THE WHOLE DESIGN DECISION.
#
#   credential_generation   moves when the password hash changes.
#   recovery_generation     moves when the code SET is replaced wholesale.
#
# Conflating them would make every password change lose a concurrent rotation
# and every rotation lose a concurrent recovery, and the advocate would be told
# "someone else changed this" for an event that did not touch what they were
# changing. Two different questions, two counters -- the same reason
# `backend/nm/domain/identity.py` and `assurance/control_plane/evidence.py` keep two fingerprints.
#
# CONSUMING ONE CODE DOES NOT MOVE `recovery_generation`. The set is the same
# set with one member spent; a rotation racing a recovery is not stale, it is
# replacing exactly the set it meant to. What a recovery DOES move is the
# credential, which is why the reauthentication proof carries both.
#
# ABSENT READS AS 0, AND 0 IS A VALUE RATHER THAN AN UNKNOWN. An account
# enrolled before this model existed carries neither field. Zero is honest for
# a comparison whose only question is DID IT MOVE: such an account's first
# generation-bearing mutation writes 1, and a proof issued before that
# mutation recorded 0 and is correctly refused.

@dataclass(frozen=True)
class AccountSecurity:
    """Which credential and which recovery set this account currently has."""

    credential_generation: int = 0
    recovery_generation: int = 0

    @classmethod
    def read(cls, doc: dict | None) -> AccountSecurity:
        def counter(name: str) -> int:
            value = (doc or {}).get(name)
            return value if isinstance(value, int) and value >= 0 else 0

        return cls(credential_generation=counter("credential_generation"),
                   recovery_generation=counter("recovery_generation"))

    def as_dict(self) -> dict:
        return {"credential_generation": self.credential_generation,
                "recovery_generation": self.recovery_generation}

    def with_new_credential(self) -> AccountSecurity:
        return AccountSecurity(self.credential_generation + 1,
                               self.recovery_generation)

    def with_new_recovery_set(self) -> AccountSecurity:
        return AccountSecurity(self.credential_generation,
                               self.recovery_generation + 1)


def csrf_token(session_token: str) -> str:
    """The value a cookie-authenticated unsafe request must echo in a header.

    DERIVED FROM THE SESSION TOKEN, so it is bound to one session and needs no
    server-side record and no second secret to manage. A token minted for one
    session cannot authorise a request carrying another, and ending a session
    invalidates its CSRF value at the same instant rather than a cache later.

    WHY THIS IS SAFE TO HAND THE BROWSER. The session cookie is `httponly`, so
    page script cannot read it; this derived value goes in a SEPARATE readable
    cookie, which page script on the serving origin can read and echo as a
    header. A cross-site page can neither read another origin's cookies nor set
    a custom header on a form post, so it can produce neither half.

    ONE-WAY, and that matters: `sha256` of the token means a leaked CSRF value
    does not yield the session token it came from. The reverse construction --
    handing out the token and deriving the session from it -- would make the
    readable cookie as good as the httponly one.
    """
    return hashlib.sha256(
        f"nm-csrf:{session_token or ''}".encode("utf8")).hexdigest()


#: THE REFUSAL IS NOT DECLARED HERE. `ProofRefused` lives in
#: `backend/nm/ports/directory.py`, beside `AccountBusy` and `InvitationRefused`,
#: because an exception is part of a contract as much as a return type is and
#: the edge must catch it without knowing which adapter is live. This module
#: answers WHY in a sentence; turning that sentence into a refusal that says
#: nothing is the adapter's job, exactly as `Session.why_not` becomes a bare
#: `None` from `session()`.


@dataclass(frozen=True)
class ReauthenticationProof:
    """Fresh authentication, bound to one session and spendable once.

    Holds a FINGERPRINT of its token and never the token, exactly as `Session`
    and `Invitation` do. The advocate's copy exists only in the response that
    minted it; a lost response is replaced by authenticating again, never by
    reading one back out of the store.
    """

    token_fingerprint: str
    advocate_id: str
    session_fingerprint: str
    security: AccountSecurity
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("token_fingerprint", "advocate_id", "session_fingerprint"):
            if blank(getattr(self, name)):
                raise ValueError(f"a reauthentication proof with no {name} "
                                 f"cannot be checked")
        if self.expires_at <= self.issued_at:
            raise ValueError("a proof that expires when it is issued is not a proof")

    def why_not(self, *, advocate_id: str, session_fingerprint: str,
                security: AccountSecurity, now: datetime) -> str | None:
        """The REASON it cannot be spent, for the log — never for the caller.

        Every clause here is a refusal the packet names: expiry, replay,
        session binding, and the two generations moving underneath. It returns
        a sentence rather than a bool so the operator log can say which, while
        `ProofRefused` says the same nothing to everyone.
        """
        if self.consumed_at is not None:
            return f"already spent at {self.consumed_at.isoformat()}"
        if now >= self.expires_at:
            return f"expired at {self.expires_at.isoformat()}"
        if canonical_id(self.advocate_id) != canonical_id(advocate_id):
            return "issued to a different advocate"
        if not hmac.compare_digest(self.session_fingerprint, session_fingerprint):
            return "issued to a different session"
        if self.security.credential_generation != security.credential_generation:
            return (f"the credential moved from generation "
                    f"{self.security.credential_generation} to "
                    f"{security.credential_generation}")
        if self.security.recovery_generation != security.recovery_generation:
            return (f"the recovery set moved from generation "
                    f"{self.security.recovery_generation} to "
                    f"{security.recovery_generation}")
        return None


def new_reauthentication_proof(
        advocate_id: str, session_fingerprint: str, security: AccountSecurity,
        now: datetime, minutes: int = REAUTHENTICATION_MINUTES,
        ) -> tuple[str, ReauthenticationProof]:
    """Returns the token ONCE, and a proof that cannot reproduce it."""
    token = new_token()
    return token, ReauthenticationProof(
        token_fingerprint=token_fingerprint(token),
        advocate_id=advocate_id,
        session_fingerprint=session_fingerprint,
        security=security,
        issued_at=now,
        expires_at=now + timedelta(minutes=minutes),
    )


# -------------------------------------------------------- recovery codes ---

@dataclass(frozen=True)
class RecoveryCodeRecord:
    """One salted code digest. The usable code is never reconstructable."""

    id: str
    salt: str
    hash: str
    used_at: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "salt", "hash"):
            if blank(getattr(self, name)):
                raise ValueError(f"a recovery-code record with no {name} is unusable")

    def as_dict(self) -> dict:
        return {"id": self.id, "salt": self.salt, "hash": self.hash,
                "used_at": self.used_at}


@dataclass(frozen=True)
class RecoveryResult:
    success: bool
    sessions_ended: int = 0


def _normalise_recovery_code(code: str | None) -> str:
    """Ignore grouping and case; preserve no user-entered representation."""
    return "".join(ch for ch in (code or "") if ch.isalnum()).upper()


def recovery_code_hash(code: str | None, salt: str) -> str:
    """A salted verifier for a high-entropy one-time code."""
    material = f"{salt}:{_normalise_recovery_code(code)}".encode("utf8")
    return hashlib.sha256(material).hexdigest()


def new_recovery_codes(
        count: int = RECOVERY_CODE_COUNT,
        ) -> tuple[tuple[str, ...], tuple[RecoveryCodeRecord, ...]]:
    """Return each advocate-held code once and only salted records thereafter."""
    if count < 8:
        raise ValueError("a recovery set must contain at least eight one-time codes")
    codes: list[str] = []
    records: list[RecoveryCodeRecord] = []
    for _ in range(count):
        raw = secrets.token_hex(10).upper()  # 80 random bits, made typeable
        code = "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))
        salt = secrets.token_hex(16)
        codes.append(code)
        records.append(RecoveryCodeRecord(
            id=secrets.token_hex(8), salt=salt,
            hash=recovery_code_hash(code, salt)))
    return tuple(codes), tuple(records)


def recovery_code_matches(record: RecoveryCodeRecord, code: str | None) -> bool:
    """Constant-time comparison; a used code never matches again."""
    candidate = recovery_code_hash(code, record.salt)
    matches = hmac.compare_digest(record.hash, candidate)
    return matches and record.used_at is None


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
class Invitation:
    """One invitation to one server-owned advocate identity.

    Only the fingerprint is retained. The complete roster identity travels
    inside the sealed invitation, so registration has no second copy a bearer
    can use to choose another advocate, profile or workspace.
    """

    token_fingerprint: str
    identity: AdvocateIdentity
    issued_at: datetime
    expires_at: datetime
    issued_by: str

    def active_at(self, now: datetime) -> bool:
        return bool(self.issued_by.strip()) and self.issued_at <= now < self.expires_at


def new_invitation(identity: AdvocateIdentity, issued_by: str, now: datetime,
                   lifetime: timedelta | None = None) -> tuple[str, Invitation]:
    """Mint a high-entropy invitation and retain only its fingerprint."""
    operator = (issued_by or "").strip()
    if not operator:
        raise ValueError("an invitation must name the operator who issued it")
    if any(mark in operator for mark in ("\r", "\n", "\t")):
        raise ValueError("an invitation issuer must fit on one audit line")
    if (not identity.email or canonical_id(identity.email) != identity.id
            or identity.email.count("@") != 1
            or any(ch.isspace() for ch in identity.email)):
        raise ValueError("an invitation must bind one canonical email identity")
    if lifetime is None:
        lifetime = timedelta(hours=INVITATION_HOURS)
    if lifetime <= timedelta(0):
        raise ValueError("an invitation lifetime must be positive")
    token = new_token()
    return token, Invitation(
        token_fingerprint=token_fingerprint(token), identity=identity,
        issued_at=now, expires_at=now + lifetime, issued_by=operator)


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
