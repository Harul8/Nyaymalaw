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
#: applies, however busy it is. Twelve hours: long enough for a working day,
#: short enough that a borrowed laptop is not a standing grant.
SESSION_HOURS = 12

#: How long a session survives with NOTHING HAPPENING. Implementation Plan F-A-12,
#: the product owner's rule: thirty minutes in which the page was not touched at
#: all -- no typing, no pointer, no switching back to the tab -- and the advocate
#: is signed out. Any activity starts the thirty minutes again. The page reports
#: activity to the server, so the server enforces the same rule on its own and a
#: closed laptop is not a live session waiting for the next person to open it.
SESSION_IDLE_MINUTES = 30
INVITATION_HOURS = 48

#: The privacy notice on the register card. Implementation Plan F-A-09. The page
#: carries the same value on the notice element and sends it back with the
#: consent, so the record says which words were shown. CHANGE IT WHEN THE WORDS
#: CHANGE: a consent is to a notice, and a new notice is not the one agreed to.
PRIVACY_NOTICE_VERSION = "2026-09-21"

#: How long an emailed password-reset link stays usable. Thirty minutes: long
#: enough for the mail to arrive and be opened, short enough that a link left
#: sitting in a mailbox is not a standing way into the account.
#: Implementation Plan F-A-03.
PASSWORD_RESET_MINUTES = 30

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
# ONE COUNTER: WHICH CREDENTIAL THIS ACCOUNT HAS. F-A-03.
#
# `credential_generation` moves whenever the password hash changes. An emailed
# reset link records the generation it was issued against, so a password
# change by ANY route -- another reset link, or whatever changes a password
# next -- makes every link issued before it unusable rather than merely old.
# Comparing the credential material itself would answer the same question by
# carrying hashes to the edge, and the rule this file keeps is that credential
# material does not travel.
#
# THERE WAS A SECOND COUNTER, for replacing recovery-code sets. The product
# owner removed recovery codes from the whole application on 15 September 2026
# (Implementation Plan F-A-04). An account record that still carries `recovery_generation` or
# recovery-code digests has them removed at its next sign-in, and nothing reads
# them before then.
#
# ABSENT READS AS 0, AND 0 IS A VALUE RATHER THAN AN UNKNOWN. An account
# enrolled before this model existed carries no counter. Zero is honest for a
# comparison whose only question is DID IT MOVE: the account's first credential
# change writes 1, and a link issued against 0 is correctly refused after it.

@dataclass(frozen=True)
class AccountSecurity:
    """Which credential this account currently has."""

    credential_generation: int = 0

    @classmethod
    def read(cls, doc: dict | None) -> AccountSecurity:
        value = (doc or {}).get("credential_generation")
        return cls(credential_generation=(
            value if isinstance(value, int) and value >= 0 else 0))

    def as_dict(self) -> dict:
        return {"credential_generation": self.credential_generation}

    def with_new_credential(self) -> AccountSecurity:
        return AccountSecurity(self.credential_generation + 1)


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


# ------------------------------------------------------- password reset ---
#
# Implementation Plan F-A-03 and F-A-04, 15 September 2026, as the product owner
# described phase A: there are no
# recovery codes anywhere in the product, and a forgotten password is replaced
# through a link sent to the account's email address.
#
# THE LINK IS A BEARER SECRET WITH THREE LIMITS, and each one closes a way a
# link could outlive the moment it was meant for:
#
#   expiry        PASSWORD_RESET_MINUTES after it was issued
#   single use    `consumed_at` is written BEFORE the credential changes, so a
#                 failure between the two leaves a spent link, never a live one
#   generation    issued against one `credential_generation`; a password change
#                 by any route retires every link issued before it
#
# Only the token's FINGERPRINT is stored, exactly as with sessions and
# invitations, so a stolen store is not a set of working reset links.
#
# THE REFUSAL SAYS NOTHING TO THE CALLER. `why_not` returns a sentence for the
# operator log; the adapter turns it into an unsuccessful `PasswordResetResult`,
# exactly as `Session.why_not` becomes a bare `None` from `session()`.

@dataclass(frozen=True)
class PasswordReset:
    """One issued reset link. Holds a fingerprint of its token, never the token."""

    token_fingerprint: str
    advocate_id: str
    credential_generation: int
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("token_fingerprint", "advocate_id"):
            if blank(getattr(self, name)):
                raise ValueError(f"a password reset with no {name} cannot be checked")
        if self.expires_at <= self.issued_at:
            raise ValueError("a reset link that expires when it is issued is not a link")

    def why_not(self, *, security: AccountSecurity, now: datetime) -> str | None:
        """The REASON it cannot be used, for the operator log -- never for the caller."""
        if self.consumed_at is not None:
            return f"already used at {self.consumed_at.isoformat()}"
        if now >= self.expires_at:
            return f"expired at {self.expires_at.isoformat()}"
        if self.credential_generation != security.credential_generation:
            return (f"the password changed after this link was issued (generation "
                    f"{self.credential_generation} -> {security.credential_generation})")
        return None

    def as_dict(self) -> dict:
        return {
            "token_fingerprint": self.token_fingerprint,
            "advocate_id": self.advocate_id,
            "credential_generation": self.credential_generation,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PasswordReset:
        consumed = data.get("consumed_at")
        return cls(
            token_fingerprint=data["token_fingerprint"],
            advocate_id=data["advocate_id"],
            credential_generation=AccountSecurity.read(data).credential_generation,
            issued_at=datetime.fromisoformat(data["issued_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            consumed_at=datetime.fromisoformat(consumed) if consumed else None,
        )


def new_password_reset(advocate_id: str, security: AccountSecurity, now: datetime,
                       minutes: int = PASSWORD_RESET_MINUTES,
                       ) -> tuple[str, PasswordReset]:
    """Returns the token ONCE, and a record that cannot reproduce it."""
    if minutes <= 0:
        raise ValueError("a reset link lifetime must be positive")
    token = new_token()
    return token, PasswordReset(
        token_fingerprint=token_fingerprint(token),
        advocate_id=canonical_id(advocate_id),
        credential_generation=security.credential_generation,
        issued_at=now,
        expires_at=now + timedelta(minutes=minutes),
    )


@dataclass(frozen=True)
class PasswordResetResult:
    """Whether a reset link changed the password, and how many sessions it ended."""

    success: bool
    sessions_ended: int = 0


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
    #: The last time this session was used, or `None` when it has not been used
    #: since it was issued. F-A-12: the idle limit runs from here.
    last_active_at: datetime | None = None
    client_label: str = ''
    source: str = ''

    def __post_init__(self) -> None:
        for name in ("token_fingerprint", "advocate_id", "device"):
            if blank(getattr(self, name)):
                raise ValueError(f"a session with no {name} cannot be checked")
        if self.expires_at <= self.issued_at:
            raise ValueError(
                "a session that expires when it is issued is not a session")

    @property
    def idle_expires_at(self) -> datetime:
        """When it stops working if nothing uses it again."""
        return ((self.last_active_at or self.issued_at)
                + timedelta(minutes=SESSION_IDLE_MINUTES))

    @property
    def reference(self) -> str:
        """Public management handle, distinct from the authentication fingerprint."""
        return token_fingerprint(f"session-control:{self.token_fingerprint}")

    def live_at(self, now: datetime) -> bool:
        return self.why_not(now) is None

    def why_not(self, now: datetime) -> str | None:
        """The REASON it cannot be used, for the log — never for the caller.

        A1's second NEVER: the response to a failed or expired credential must
        be identical. This exists so the reason is recorded where an operator
        can see it, and the edge returns the same words either way.

        ONE OWNER FOR "IS IT LIVE". `live_at` asks this, so a fourth way for a
        session to end cannot be added to one of the two and not the other.
        """
        if self.ended_because:
            return self.ended_because
        if now >= self.expires_at:
            return f"expired at {self.expires_at.isoformat()}"
        if now >= self.idle_expires_at:
            return (f"no activity for {SESSION_IDLE_MINUTES} minutes; idle since "
                    f"{(self.last_active_at or self.issued_at).isoformat()}")
        return None


def open_session(advocate_id: str, device: str, now: datetime,
                 hours: int = SESSION_HOURS, *, client_label: str = '',
                 source: str = '') -> tuple[str, Session]:
    """Returns the token ONCE, and a session that cannot reproduce it."""
    token = new_token()
    return token, Session(
        token_fingerprint=token_fingerprint(token),
        advocate_id=advocate_id,
        device=device or "unknown-device",
        issued_at=now,
        expires_at=now + timedelta(hours=hours),
        client_label=client_label,
        source=source,
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


#: The one refusal for a registration without full consent. F-A-09.
CONSENT_REQUIRED = (
    "Registration needs your agreement to the privacy notice and your "
    "confirmation that you are 18 or older. Nothing was saved.")
#: The notice changed after the page was loaded, so what was agreed to is not
#: what is in force.
CONSENT_TO_AN_OLD_NOTICE = (
    "The privacy notice has changed since this page was opened. Reload the "
    "page, read the notice and register again. Nothing was saved.")


@dataclass(frozen=True)
class Consent:
    """What an advocate agreed to, and when. Implementation Plan F-A-09.

    DPDP Act 2023 s.6(10) puts the burden of proving consent on the one who
    collected it, so the record names the exact notice version shown and the
    age confirmation, not merely that a box was ticked somewhere.
    """

    notice_version: str
    given_at: datetime
    adult_confirmed: bool
    external_ai_notice_version: str | None = None

    def __post_init__(self) -> None:
        if blank(self.notice_version):
            raise ValueError("a consent that names no notice proves nothing")
        if not self.adult_confirmed:
            raise ValueError("a consent without the 18-or-older confirmation is not one")

    def as_dict(self) -> dict:
        return {"notice_version": self.notice_version,
                "given_at": self.given_at.isoformat(),
                "adult_confirmed": self.adult_confirmed,
                "external_ai_notice_version": self.external_ai_notice_version}


def registration_consent(notice_version: str | None, agreed: bool, adult: bool,
                         now: datetime, *, external_ai: bool = False,
                         external_ai_notice_version: str | None = None) -> Consent:
    """The consent a registration carries, or `ValueError` naming what is missing.

    `is True`, not truthiness: a JSON `"false"` string or a `1` is not somebody
    ticking a box.
    """
    if agreed is not True or adult is not True:
        raise ValueError(CONSENT_REQUIRED)
    if (notice_version or "").strip() != PRIVACY_NOTICE_VERSION:
        raise ValueError(CONSENT_TO_AN_OLD_NOTICE)
    from nm.domain.external_ai import NOTICE_VERSION
    if type(external_ai) is not bool:
        raise ValueError("OpenAI processing permission must be an explicit choice")
    if external_ai and external_ai_notice_version != NOTICE_VERSION:
        raise ValueError("The OpenAI processing notice changed; read the current notice")
    if not external_ai and external_ai_notice_version is not None:
        raise ValueError("An unaccepted OpenAI notice cannot record permission")
    return Consent(notice_version=PRIVACY_NOTICE_VERSION, given_at=now,
                   adult_confirmed=True,
                   external_ai_notice_version=NOTICE_VERSION if external_ai else None)


@dataclass(frozen=True)
class Enrolment:
    """An advocate and their credential, as one record on the way to the store."""

    identity: AdvocateIdentity
    credential: Credential
    created_at: datetime = field(default_factory=utcnow)
    #: The privacy consent given at registration. `None` for an account made
    #: without the register card -- an operator enrolment or an invitation --
    #: which is recorded as having no consent rather than as having one.
    consent: Consent | None = None
    mailbox_confirmed_at: datetime | None = None
    activation_id: str | None = None
