"""How an admin's change is made (plan AN.46, pieces 46j and 46k; owner decisions D116 and D121, 7 Nov 2026).

ONE PATH FOR EVERY CHANGE, SO NO CHANGE CAN SKIP A STEP (D116). Whatever is being changed, `make_change` does these in this order and
stops at the first that is not met, having changed nothing:

  1. The admin's level permits it. Admin (view only) may look and may not change anything.
  2. The admin gave their password just now, in this session (the check the Admin area keeps for ten minutes). A session that has not
     gets "password_needed", which the page answers by asking for it.
  3. The reason is one line of at most 200 characters.
  4. The audit log takes a first entry, "started". If it cannot be written the change is not made.
  5. The change is made.
  6. The audit log takes a second entry, "done" - or "not made" when the change was refused or failed, so the log never says a change
     happened that did not.

A change names its account by the id the directory knows it by and is refused for an account that is not there, so a typo can never
make a record for someone who does not exist. Nothing here reads or writes a conversation, a matter, a file or a password.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from nm.arrive.admin_access import Action, Level, permits
from nm.arrive.admin_port import AdminChangeRefused, AdminRecordPort, AdminUnavailable, AuditEntry

REASON_LIMIT = 200
#: The words an admin is told when each step refuses.
VIEW_ONLY = "Admin (view only) can look but cannot change anything."
PASSWORD_NEEDED = "Confirm your password to make this change."
RECORD_UNAVAILABLE = "The audit record could not be written, so nothing was changed."


class PasswordNeeded(AdminChangeRefused):
    """The password step has not been done in this session in the last ten minutes."""

    code = "password_needed"

    def __init__(self):
        super().__init__(403, PASSWORD_NEEDED)


def one_line_reason(reason: object) -> str:
    """The reason, trimmed, or a refusal: required, one line, at most 200 characters."""
    if (not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > REASON_LIMIT
            or any(ord(c) < 32 or ord(c) == 127 for c in reason.strip())):
        raise AdminChangeRefused(422, f"Give a reason in one line of at most {REASON_LIMIT} characters.")
    return reason.strip()


def make_change(*, record: AdminRecordPort, level: Level | None, actor: str, session_fingerprint: str, now: datetime,
                action: Action, label: str, target: str, reason: str, do: Callable[[], dict]) -> dict:
    """Make one change through the steps in the module's note. `label` is the short name the audit log gives the change (it may say how
    much, as "allowance add usd 5"); `do` makes it and returns what the page is told, or raises AdminChangeRefused."""
    if not permits(level, action):
        raise AdminChangeRefused(403, VIEW_ONLY)
    try:
        if not record.password_confirmed(session_fingerprint, now):
            raise PasswordNeeded()
    except AdminUnavailable as exc:
        raise AdminChangeRefused(503, RECORD_UNAVAILABLE) from exc
    why = one_line_reason(reason)
    try:
        record.append(AuditEntry(now, actor, label, target, why, "started"))
    except AdminUnavailable as exc:
        raise AdminChangeRefused(503, RECORD_UNAVAILABLE) from exc
    try:
        result = do()
    except AdminChangeRefused:
        _close(record, now, actor, label, target, why, "not made")
        raise
    except (AdminUnavailable, ValueError, OSError) as exc:
        _close(record, now, actor, label, target, why, "not made")
        raise AdminChangeRefused(503, "That could not be done just now. Nothing was changed.") from exc
    audited = _close(record, now, actor, label, target, why, "done")
    return {**result, "audited": audited}


def _close(record: AdminRecordPort, now: datetime, actor: str, label: str, target: str, why: str, outcome: str) -> bool:
    """The second entry. True when written; False when the log could not take it (the first entry stands, and the page says so)."""
    try:
        record.append(AuditEntry(now, actor, label, target, why, outcome))
        return True
    except AdminUnavailable:
        return False
