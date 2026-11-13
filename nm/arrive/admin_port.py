"""The Admin area's three narrow ports (plan AN.46, piece 46b; owner decisions D116-D119 and D126, 7 Nov 2026).

WHY THESE ARE NOT METHODS OF THE DIRECTORY PORT. `DirectoryPort` has no listing on purpose (A1: a failed sign-in must
disclose nothing about what exists, and the cheapest way to keep that true is to give the sign-in edge no way to ask). The
Admin area is the one caller that may ask who exists, so it asks through ports of its own, which only the Admin routes are
given. The sign-in edge's port is unchanged.

WHAT EACH PORT CAN RETURN IS THE LIST OF WHAT AN ADMIN MAY SEE (D119). A result type names its fields; there is no way to
return a whole account record, a session token, a conversation, a matter or a file through one of them. A reader that
cannot open a source says so (`readable=False`, a count of unreadable records, `unavailable`) and never reports it as empty.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol, Sequence


class AdminUnavailable(RuntimeError):
    """A source the Admin area reads could not be opened. The view says so; it never shows an empty list instead."""


# ------------------------------------------------------------------ the directory ---

@dataclass(frozen=True)
class SessionLine:
    """One sign-in of an account. No token, no fingerprint, no address: where from is the client's own label."""
    client_label: str
    issued_at: datetime
    expires_at: datetime
    last_active_at: datetime | None
    live: bool


@dataclass(frozen=True)
class AdminAccount:
    """What an admin may see of one account (D119). `readable=False`: the record would not open, and every other
    field is then unknown (None / empty), not "none"."""
    id: str
    readable: bool
    name: str = ""
    enrolment: str = ""
    firm_id: str = ""
    created_at: datetime | None = None
    #: AI data sharing as the advocate last set it; None when the permission record would not open.
    ai_sharing: bool | None = None
    ai_notice_version: str | None = None
    last_sign_in: datetime | None = None
    last_active: datetime | None = None
    sessions: tuple[SessionLine, ...] = ()
    #: Set by an Admin (D121); an account the directory does not yet record this for is not suspended.
    suspended: bool = False
    #: "advocate" (the default) or "admin", as an admin last set it on the account (owner, 7 Nov 2026). The server's settings may name
    #: an admin as well; the view joins the two.
    user_type: str = "advocate"


@dataclass(frozen=True)
class WaitingRegistration:
    """An email that registered and has not yet confirmed it: there is no account yet."""
    email: str
    name: str
    requested_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True)
class DirectoryListing:
    accounts: tuple[AdminAccount, ...]
    waiting: tuple[WaitingRegistration, ...]
    #: Session files that would not open: the sessions shown may be incomplete when this is not 0.
    unreadable_sessions: int = 0
    #: False when the waiting registrations could not be read (the list is then unknown, not empty).
    waiting_readable: bool = True


class AdminDirectoryPort(Protocol):
    def listing(self, now: datetime) -> DirectoryListing:
        """Every account in one pass, with its sessions. Reads only; it writes nothing, not even the migration a
        sign-in does to an older sealed record. Raises AdminUnavailable when the directory cannot be listed."""
        ...


class AdminChangeRefused(Exception):
    """A change the Admin area was asked to make was refused for a reason an admin should be told in plain words (nothing was changed).
    `status` is the HTTP status the edge answers with."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class AdminAccountsPort(Protocol):
    """What an admin may change about an account itself (D116, D121). The allowance is changed through the usage port's own grant, and
    nothing else about an account - its password, its approval, its matters - is reachable from here."""

    def set_suspended(self, account_id: str, suspended: bool, now: datetime) -> bool:
        """Suspend or reinstate. True when the account's state changed, False when it was already so. Raises AdminChangeRefused for an
        account that does not exist, one whose record cannot be read, or one being changed just now; AdminUnavailable on storage."""
        ...

    def set_user_type(self, account_id: str, user_type: str) -> bool:
        """Set the account's user type to "advocate" or "admin". True when it changed, False when it was already so. Raises
        AdminChangeRefused for an account that does not exist, cannot be read or is being changed just now."""
        ...

    def end_sessions(self, account_id: str, why: str, keep_fingerprint: str = "") -> int:
        """End every live session of the account except the one whose fingerprint is given. Returns how many were ended."""
        ...


# ------------------------------------------------------------------------- usage ---

@dataclass(frozen=True)
class Balance:
    """An account's allowance in millionths of a dollar. `left_percent` is the same figure the advocate is shown."""
    granted: int
    spent: int
    left_percent: int


@dataclass(frozen=True)
class Consumption:
    """The calls of one group (a day, a model, an operation, an outcome or an account) between two times."""
    group: tuple[str, ...]
    calls: int
    micro_usd: int
    #: Calls whose cost was not established: the cost above leaves them out and the view says so.
    cost_not_established: int
    tokens_in: int
    tokens_out: int
    cached_tokens: int
    cache_write_tokens: int
    audio_seconds: float


#: The groupings a view may ask for. "account" is a digest of the account, never an address; the view joins it.
GROUPINGS = ("day", "model", "operation", "outcome", "account", "day,model", "account,day")


class AdminUsagePort(Protocol):
    def balances(self) -> Mapping[str, Balance]:
        """Every account that has a record, by account digest. An account with no record has not started: it is
        absent here, and reading never gives it the trial a first use gives. Raises AdminUnavailable."""
        ...

    def consumption(self, since: datetime, until: datetime, grouping: str) -> Sequence[Consumption]:
        """Calls from `since` up to `until`, grouped as `grouping` (one of GROUPINGS), in group order."""
        ...

    def granted_since(self, since: datetime, until: datetime) -> int:
        """Allowance given in the period, trials and operators' grants, in millionths of a dollar."""
        ...


# --------------------------------------------------------------------- the turn record ---

@dataclass(frozen=True)
class TurnDay:
    """How many turns ended on one Indian day, by how they ended (D120). No account, model or word of a turn."""
    day: str
    answered: int = 0
    stopped: int = 0
    refused: int = 0
    failed: int = 0


@dataclass(frozen=True)
class TurnsSummary:
    """The turn record over a period. Days with no turn are absent (the view fills them); the middle and slow ends are the time, in
    seconds, that half and nine in ten of the answers took. `first_at` is when the record began: nothing before it was recorded."""
    by_day: tuple[TurnDay, ...]
    answered_seconds_middle: int | None
    answered_seconds_slow: int | None
    first_at: datetime | None


class AdminTurnsPort(Protocol):
    def summary(self, since: datetime, until: datetime) -> TurnsSummary:
        """Turns that ended from `since` up to `until`. A record that has not begun is empty (first_at None). Raises
        AdminUnavailable when the record is there and cannot be read."""
        ...


# ------------------------------------------------------------------------ diagnostics ---

#: Plan AN.53 (53e, D220): the file in the store where each line the outgoing-data log could not take is counted - one time a
#: line, nothing else.
UNWRITTEN_LOG_LINES = "outgoing-log-unwritten.log"


class AdminChecksPort(Protocol):
    """The sources the diagnostics are made of: counts, sizes and short names, nothing an advocate wrote (D119). A method whose source
    cannot be read returns None (or raises AdminUnavailable), and only that check says so (D128)."""

    def turn_attempts(self) -> Mapping[str, int] | None:
        ...

    def sign_ins(self, since: datetime) -> Mapping[str, int] | None:
        ...

    def disk(self) -> Mapping[str, Mapping[str, int]] | None:
        ...

    def law(self) -> Sequence[Mapping]:
        ...

    def scanner(self) -> Mapping[str, object]:
        ...

    def outbox(self) -> Mapping[str, object]:
        ...

    def limiter_log(self) -> Mapping[str, int] | None:
        """How many lines of the sign-in limiter's log are skipped as unreadable (plan AN.53, 53c4). None where it cannot be opened."""
        ...

    def outgoing_log(self, since: datetime) -> Mapping[str, int] | None:
        """How many lines the outgoing-data log could not take since `since` (plan AN.53, 53e). None where that cannot be read."""
        ...


# ------------------------------------------------------------------------ the library ---

class AdminStagingPort(Protocol):
    """Acts staged for the library by an admin (D122, D125): copied into a folder of their own, read by the free reading job, approved,
    and then appended by the owner's own job with the server stopped. Nothing here reaches the library."""

    def batches(self) -> list[dict]:
        ...

    def stage(self, jurisdiction: str, files: list[tuple[str, str]], now: datetime) -> dict:
        """Raises AdminChangeRefused for a name, a size or a count that is not allowed; AdminUnavailable when it cannot be kept."""
        ...

    def approve(self, batch_id: str, actor: str, now: datetime) -> dict:
        ...

    def discard(self, batch_id: str) -> bool:
        ...


class AdminLibraryPort(Protocol):
    def library(self) -> Mapping[str, object]:
        """What the held law holds, described and not opened: each store's lineage facts, the Acts catalogue's counts, the earlier
        copies kept beside a store, candidate stores built beside the live ones, and free disk (D122)."""
        ...


# ------------------------------------------------------------------ the audit record ---

@dataclass(frozen=True)
class AuditEntry:
    """One thing an admin did (D126). `reason` is what the admin typed, at most 200 characters; nothing of an
    advocate's work can be put here, since an entry names an account or a batch and no more."""
    at: datetime
    actor: str
    action: str
    target: str
    reason: str
    outcome: str
    #: Set by the store: this entry's position and the fingerprint that includes the one before it.
    id: int = 0
    fingerprint: str = ""


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    entries: int
    #: The first entry that does not follow from the one before it, or None when the whole chain does.
    first_bad_id: int | None = None
    #: The newest fingerprint, which anyone who wrote it down earlier can compare.
    newest: str = ""


class AdminRecordPort(Protocol):
    def append(self, entry: AuditEntry) -> AuditEntry:
        """Add one entry at the end and return it with its position and fingerprint. There is no other write: nothing
        changes or removes an entry. Raises AdminUnavailable, and then the change the entry records is not made."""
        ...

    def entries(self, *, limit: int = 100, before_id: int | None = None) -> tuple[AuditEntry, ...]:
        """Newest first, at most `limit` (capped), those before `before_id` when it is given."""
        ...

    def verify(self) -> ChainCheck:
        ...

    def confirm_password(self, session: str, now: datetime) -> datetime:
        """Remember that this session's holder just gave their password, until the returned time. The password was
        checked by the caller through the directory's own `authenticate`; it is not passed here and never stored."""
        ...

    def password_confirmed(self, session: str, now: datetime) -> bool:
        ...
