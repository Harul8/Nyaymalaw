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
attacker cannot. `issue_password_reset` follows the same rule: the edge learns
whether there is a link to send, and the person who asked learns nothing.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from nm.domain.advocate import (
    AdvocateIdentity,
    Consent,
    Credential,
    Enrolment,
    PasswordResetResult,
    Session,
)
from nm.domain.attempts import Verdict
from nm.domain.external_ai import ModelPermission
from nm.domain.professional_access import ProfessionalApproval


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
    """A credential change or sign-in currently owns this account."""


class RegistrationUnavailable(RuntimeError):
    """Public signup cannot establish durable bounded admission; refuse it."""


class SessionsUnavailable(RuntimeError):
    """The complete session inventory could not be established."""


class AuthenticationUnavailable(RuntimeError):
    """Authentication controls could not be durably read or written."""


class DirectoryPort(Protocol):
    def model_permission(self, advocate_id: str) -> ModelPermission | None:
        """Current sealed permission; damaged state raises, absence grants nothing."""
        ...

    def record_model_permission(self, permission: ModelPermission, *,
                                expected_version: int) -> ModelPermission:
        """Authenticated account's versioned acceptance/withdrawal, never a roster grant."""
        ...

    def begin_pending_registration(self, enrolment: Enrolment, now: datetime) -> dict:
        """Hold a bounded inactive signup and return the internal mail challenge."""
        ...

    def resend_registration(self, email: str, now: datetime) -> str | None:
        """An eligible challenge or no mail, without resetting its guess budget."""
        ...

    def cancel_pending_registration(self, email: str, flow: str, now: datetime) -> bool:
        """Invalidate only the unconfirmed registration owned by this browser's flow."""
        ...

    def confirm_registration(self, email: str, code: str, flow: str,
                             credential: Credential | None, now: datetime) -> AdvocateIdentity:
        """Activate once after mailbox proof, refusing takeover/replay/expiry."""
        ...

    def device_draft_key(self, advocate_id: str, device: str) -> dict:
        """Return a sealed-at-rest draft key for this authenticated account/device.

        The edge validates the current session first. The key is not a login
        credential and must never be persisted by the browser.
        """
        ...

    def admit_registration(self, email: str, source: str, now: datetime) -> Verdict:
        """Atomically count an admitted public attempt before deriving secrets.

        Successful creations count too. Counters survive worker/restart and
        are resource bounded; unreadable/unwritable state raises
        RegistrationUnavailable, never permission. Refused retries do not
        extend the window. The email is the validated canonical account ID.
        """
        ...

    def issue_invitation(self, identity: AdvocateIdentity, issued_by: str,
                         now: datetime) -> str:
        """Return the invitation once; retain only its fingerprint."""
        ...

    def accept_invitation(self, token: str, credential: Credential,
                          now: datetime, consent: Consent | None = None,
                          ) -> AdvocateIdentity:
        """Consume one invitation and enrol the identity it carries.

        `consent`, when given, is recorded with the account (F-A-09).
        """
        ...

    def enrol(self, enrolment: Enrolment) -> None:
        """Record an advocate. Refuses, never overwrites, an existing one."""
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
            *, client_label: str = '', source: str = '',
            ) -> tuple[AdvocateIdentity, str] | None:
        """Authenticate and mint a session under the account mutation lock."""
        ...

    def issue_password_reset(self, email: str, now: datetime) -> str | None:
        """A reset token ONCE for an account this email names, or `None`. F-A-03.

        `None` covers an unknown address, an unreadable account and an account
        with no email to send to, and the edge must answer the person who asked
        identically in every case. Only the token's fingerprint is stored; the
        link it becomes is bound to the account's current credential generation
        and expires.
        """
        ...

    def reset_password(self, token: str, credential: Credential,
                       now: datetime) -> PasswordResetResult:
        """Spend one reset link, replace the credential and end every session.

        The link is marked used BEFORE the credential changes. Unknown, used,
        expired and superseded links are one unsuccessful result; the adapter
        records which. Raises `AccountBusy` when another change owns the account.
        """
        ...

    def open_session(self, advocate_id: str, device: str,
                     now: datetime, *, client_label: str = '', source: str = '') -> str:
        """Returns the token, once. It is never retrievable afterwards."""
        ...

    def session(self, token: str, device: str,
                now: datetime) -> Session | None:
        """The live session this token names, or `None`.

        `None` covers unknown, expired, ended, IDLE and WRONG DEVICE alike —
        A1's first NEVER is that a matter list is not restored on a borrowed
        device without re-authentication, and a session that travels between
        devices is exactly that restoration.

        A read does not extend authority. Only explicitly reported user
        activity renews the idle clock; polling and retries do not.
        """
        ...

    def close_session(self, token: str, why: str) -> str:
        ...

    def sessions_for(self, advocate_id: str) -> tuple[Session, ...]:
        """Own issued sessions, or SessionsUnavailable; never an incomplete success."""
        ...

    def close_selected_session(self, advocate_id: str, reference: str, why: str,
                               *, except_token: str) -> str:
        """Close only an owned non-current session; unknown/foreign references agree."""
        ...

    def touch_session(self, token: str, device: str, now: datetime) -> Session | None:
        """Renew a still-live session following explicit user activity."""
        ...

    def identity(self, advocate_id: str) -> AdvocateIdentity | None:
        """For rendering who is signed in. Requires a live session upstream."""
        ...

    def professional_approval(self, advocate_id: str) -> dict | None:
        """Current operator-reviewed record; absence/unreadable never grants approval."""
        ...

    def record_professional_approval(self, approval: "ProfessionalApproval", *,
                                     expected_version: int, now: datetime) -> dict:
        """Operator-only attributed update, under the shared account mutation lock."""
        ...
