"""A1 — the directory: who exists, and whether this session is theirs.

DELIBERATELY NARROW, AND THE OMISSIONS ARE THE DESIGN
------------------------------------------------------
There is no `list_advocates`, no `find_by_name`, and no method that answers
"does this advocate exist". A1's second NEVER is that a failed credential must
disclose nothing about what exists, and the cheapest way to keep that true is
to give the edge no way to ask.

`authenticate` returns an identity or `None` and never says which of the two
reasons applied, because the caller must not be able to tell either. The
reason is recorded by the ADAPTER, where an operator can read it and an
attacker cannot.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from nm.domain.advocate import (
    AdvocateIdentity,
    Credential,
    Enrolment,
    RecoveryResult,
    Session,
)


class AlreadyEnrolled(RuntimeError):
    """An id that is already enrolled. DECLARED BY THE PORT, not the adapter.

    It lived on `FileDirectory` and the register route had to import the
    adapter to catch it -- which layercheck refused, correctly: the edge must
    not know which adapter is live, and an exception is part of a contract as
    much as a return type is. The model port declares `ModelError` and its
    kin for the same reason, so the retry and degrade policies hold whichever
    adapter is serving.
    """


class InvitationRefused(RuntimeError):
    """Unknown, expired, replayed or unreadable invitation.

    One exception deliberately covers every cause. The adapter records the
    precise reason; the caller must not turn an invitation token into an
    oracle for roster or workspace data.
    """


class AccountBusy(RuntimeError):
    """A credential or recovery mutation currently owns this account."""


class ProofRefused(RuntimeError):
    """A fresh-authentication proof cannot authorise this replacement.

    ONE EXCEPTION FOR EVERY CAUSE, on the same rule as `InvitationRefused`.
    Expired, already spent, issued to another session, issued for another
    advocate, and superseded by a credential or recovery change are five
    different facts, and the caller learns none of them: a refusal that says
    WHICH would tell a holder of a stolen session whether the account's
    password has changed since they took it.

    DECLARED HERE RATHER THAN IN THE DOMAIN because an exception is part of a
    contract as much as a return type is, and the edge must be able to catch it
    without knowing which adapter is live. `ReauthenticationProof.why_not`
    returns the reason as a sentence for the operator log; turning that
    sentence into this exception is the adapter's job, exactly as `Session.
    why_not` becomes a bare `None` from `session()`.
    """


class DirectoryPort(Protocol):
    def issue_invitation(self, identity: AdvocateIdentity, issued_by: str,
                         now: datetime) -> str:
        """Return the invitation once; retain only its fingerprint."""
        ...

    def accept_invitation(self, token: str, credential: Credential,
                          now: datetime) -> tuple[AdvocateIdentity, tuple[str, ...]]:
        """Consume one invitation; return identity and recovery codes once."""
        ...

    def enrol(self, enrolment: Enrolment) -> tuple[str, ...]:
        """Record an advocate and return their initial recovery codes once."""
        ...

    def authenticate(self, advocate_id: str, password: str,
                     ) -> AdvocateIdentity | None:
        """The identity, or `None`. NEVER which of the two failures it was.

        Implementations must run the key derivation even when the advocate is
        unknown: an identical message returned in 0.2ms for a stranger and
        80ms for a wrong password discloses which accounts exist.
        """
        ...

    def authenticate_and_open_session(
            self, advocate_id: str, password: str, device: str, now: datetime,
            ) -> tuple[AdvocateIdentity, str, tuple[str, ...]] | None:
        """Authenticate and mint a session under the account mutation lock."""
        ...

    def ensure_recovery_codes(self, advocate_id: str,
                              now: datetime) -> tuple[str, ...]:
        """Provision a legacy advocate once, after valid authentication."""
        ...

    def recover(self, advocate_id: str, code: str, credential: Credential,
                now: datetime) -> RecoveryResult:
        """Consume one recovery code, change credential and end sessions."""
        ...

    def account_security(self, advocate_id: str) -> int | None:
        """The current recovery generation, or `None` when it cannot be read.

        A counter and not a secret: it says how many times this advocate's own
        recovery set has been replaced and nothing about the codes. A client
        needs it so `rotate_recovery_codes` can compare against what the
        advocate was actually shown rather than against the request's own echo.
        """
        ...

    def reauthenticate(self, advocate_id: str, password: str,
                       session_token: str, device: str,
                       now: datetime, *, source: str = "reauthenticate") -> str | None:
        """Prove the current password again, INSIDE this session. BK-31-AC20.

        Returns the proof token ONCE, or `None` — and `None` covers a wrong
        password, a session that is not live, a session belonging to somebody
        else and a session presented from another device alike. A signed-in
        advocate must not be able to use this to discover which.

        The proof it mints is spendable once, expires in five minutes, is bound
        to this session's fingerprint and carries both generation counters, so
        anything that moves the credential or the recovery set underneath it
        makes it unusable rather than merely old.

        The HTTP caller supplies its observed connection source for failed
        attempt accounting; it is never a client-claimed forwarded address.
        """
        ...

    def rotate_recovery_codes(self, advocate_id: str, proof_token: str,
                              session_token: str, device: str,
                              expected_recovery_generation: int,
                              now: datetime, *,
                              source: str = "rotate-recovery-codes") -> tuple[str, ...]:
        """Replace the whole recovery set atomically. The new codes, once.

        THE EXPECTED GENERATION IS THE RECOVERY ONE, NOT THE SESSION'S. A
        rotation is a compare-and-set against the set being replaced; the
        session version says nothing about whether that set moved. Raises
        `ProofRefused` on any refusal and `AccountBusy` when another credential
        or recovery mutation holds the account.

        A LOST RESPONSE IS NOT RECOVERABLE, and that is the design. The codes
        exist in the successful return value and nowhere else; an advocate who
        loses it authenticates again and replaces the set again. There is no
        read-back, because a read-back is a second place the plaintext lives.
        """
        ...

    def open_session(self, advocate_id: str, device: str,
                     now: datetime) -> str:
        """Returns the token, once. It is never retrievable afterwards."""
        ...

    def session(self, token: str, device: str,
                now: datetime) -> Session | None:
        """The live session this token names, or `None`.

        `None` covers unknown, expired, ended and WRONG DEVICE alike — A1's
        first NEVER is that a matter list is not restored on a borrowed device
        without re-authentication, and a session that travels between devices
        is exactly that restoration.
        """
        ...

    def close_session(self, token: str, why: str) -> None:
        ...

    def identity(self, advocate_id: str) -> AdvocateIdentity | None:
        """For rendering who is signed in. Requires a live session upstream."""
        ...
