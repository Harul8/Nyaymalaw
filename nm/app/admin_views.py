"""What the Admin pages are told: the users, one user, the usage and the overview (plan AN.46, piece 46f; D118-D119).

BUILT FROM NAMED FIELDS, NEVER FROM A FULLER RECORD (D119). Every payload below is assembled field by field from the three Admin ports
(`nm/arrive/admin_port.py`), whose result types cannot carry a conversation, a file, a token or an address. Nothing here removes
content from something that had it, so nothing can be left in by mistake. `content_free` then walks a finished payload and refuses
one that has a key an advocate's work or a secret would sit under; the tests run every view through it, and the routes do too.

THE LEVEL IS THE ROSTER'S (D117-D118): Advocate, Admin, or Admin (view only). Professional approval, a suspension, an unreadable record
and an email still waiting to be confirmed are facts beside the level, never levels.

AN ACCOUNT WITH NO ALLOWANCE RECORD HAS NOT STARTED; it is not shown as having none left. Money is whole millionths of a US dollar, as
the store keeps it; the page does the formatting. The answers a day and the time an answer takes need the turn record (D120) and say so.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from nm.arrive.admin_access import Roster
from nm.arrive.admin_port import (AdminAccount, AdminDirectoryPort, AdminUsagePort, Balance, Consumption)
from nm.arrive.advocate_contracts import canonical_id

#: The days an admin may ask the usage pages about.
PERIODS = (7, 30, 90)
#: An Indian day (see nm/arrive/admin_usage.py): the days on the charts are the days the advocates lived.
INDIA = timezone(timedelta(hours=5, minutes=30))
LEVEL_LABELS = {"admin": "Admin", "view-only": "Admin (view only)", "advocate": "Advocate"}
#: An allowance this low is called low, as the advocate's own notices start to (P53).
LOW_PERCENT = 10
#: An approval ending within this many days is called ending.
APPROVAL_ENDING_DAYS = 30
TOP_ACCOUNTS = 10
#: A key under which an advocate's work or a secret would sit. A payload with one of these anywhere is refused.
FORBIDDEN_KEYS = frozenset({
    "message", "messages", "matter", "matter_id", "matters", "chat", "chat_id", "conversation", "board", "document",
    "documents", "file", "files", "answer_text", "brief", "research", "preferences", "memory", "draft", "password",
    "credential", "token", "secret", "cookie", "salt", "hash", "text", "body", "content"})


def digest(account_id: str) -> str:
    """The name the usage store gives an account: the SHA-256 of its canonical id."""
    return hashlib.sha256(canonical_id(account_id).encode("utf8")).hexdigest()


def content_free(payload: Any) -> Any:
    """The payload itself, when no key anywhere in it is one an advocate's work or a secret would sit under; else ValueError."""
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            bad = FORBIDDEN_KEYS & {str(key).lower() for key in item}
            if bad:
                raise ValueError(f"an Admin payload may not carry {sorted(bad)}")
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return payload


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _level(roster: Roster, account_id: str) -> str:
    level = roster.level_of(account_id)
    return level.value if level is not None else "advocate"


def _allowance(balance: Balance | None) -> dict:
    if balance is None:
        return {"started": False, "granted": None, "spent": None, "left_percent": None}
    return {"started": True, "granted": balance.granted, "spent": balance.spent, "left_percent": balance.left_percent}


def _row(account: AdminAccount, roster: Roster, balances: Mapping[str, Balance], now: datetime) -> dict:
    status = "unreadable" if not account.readable else "suspended" if account.suspended else "active"
    return {
        "id": account.id, "name": account.name, "enrolment": account.enrolment, "firm_id": account.firm_id,
        "level": _level(roster, account.id), "level_label": LEVEL_LABELS[_level(roster, account.id)], "status": status,
        "created_at": _iso(account.created_at), "last_sign_in": _iso(account.last_sign_in),
        "last_active": _iso(account.last_active), "live_sessions": sum(1 for s in account.sessions if s.live),
        "professional": {"state": account.professional_state, "valid_until": _iso(account.professional_valid_until)},
        "ai_sharing": account.ai_sharing,
        "allowance": _allowance(balances.get(digest(account.id))) if account.readable else _allowance(None)}


def _days(since: datetime, until: datetime) -> list[str]:
    day, last, found = since.astimezone(INDIA).date(), (until - timedelta(seconds=1)).astimezone(INDIA).date(), []
    while day <= last:
        found.append(day.isoformat())
        day += timedelta(days=1)
    return found


def _period(now: datetime, days: int) -> tuple[datetime, datetime]:
    if days not in PERIODS:
        raise ValueError(f"the usage pages cover {PERIODS} days")
    today = now.astimezone(INDIA).replace(hour=0, minute=0, second=0, microsecond=0)
    return (today - timedelta(days=days - 1)).astimezone(timezone.utc), (today + timedelta(days=1)).astimezone(timezone.utc)


def _totals(rows: tuple[Consumption, ...] | list[Consumption]) -> dict:
    return {"calls": sum(r.calls for r in rows), "micro_usd": sum(r.micro_usd for r in rows),
            "cost_not_established": sum(r.cost_not_established for r in rows),
            "tokens_in": sum(r.tokens_in for r in rows), "tokens_out": sum(r.tokens_out for r in rows),
            "cached_tokens": sum(r.cached_tokens for r in rows), "cache_write_tokens": sum(r.cache_write_tokens for r in rows)}


def _by_day(rows: list[Consumption], days: list[str]) -> list[dict]:
    """One entry for every day of the period, quiet days included, with the cost of each model that day."""
    found: dict[str, dict] = {day: {"day": day, "calls": 0, "micro_usd": 0, "models": {}} for day in days}
    for row in rows:
        day, model = row.group
        if day in found:
            entry = found[day]
            entry["calls"] += row.calls
            entry["micro_usd"] += row.micro_usd
            entry["models"][model] = entry["models"].get(model, 0) + row.micro_usd
    return list(found.values())


# --------------------------------------------------------------------------- the pages ---

def users_view(roster: Roster, directory: AdminDirectoryPort, usage: AdminUsagePort, now: datetime) -> dict:
    listing, balances = directory.listing(now), usage.balances()
    rows = [_row(account, roster, balances, now) for account in listing.accounts]
    readable = [r for r in rows if r["status"] != "unreadable"]
    return content_free({
        "as_of": now.isoformat(),
        "totals": {"accounts": len(rows), "admins": sum(1 for r in rows if r["level"] != "advocate"),
                   "advocates": sum(1 for r in rows if r["level"] == "advocate"),
                   "suspended": sum(1 for r in rows if r["status"] == "suspended"),
                   "unreadable": len(rows) - len(readable), "waiting": len(listing.waiting),
                   "ai_sharing_on": sum(1 for r in readable if r["ai_sharing"]),
                   "approved": sum(1 for r in readable if r["professional"]["state"] == "approved")},
        "accounts": rows,
        "waiting": [{"email": w.email, "name": w.name, "requested_at": _iso(w.requested_at),
                     "expires_at": _iso(w.expires_at)} for w in listing.waiting],
        "waiting_readable": listing.waiting_readable, "unreadable_sessions": listing.unreadable_sessions})


def user_view(account_id: str, roster: Roster, directory: AdminDirectoryPort, usage: AdminUsagePort,
              now: datetime, days: int = 30) -> dict | None:
    """One account's page, or None when there is no such account (the route answers 404, as for any address)."""
    wanted = canonical_id(account_id)
    listing = directory.listing(now)
    account = next((a for a in listing.accounts if a.id == wanted), None)
    if account is None:
        return None
    balances = usage.balances()
    since, until = _period(now, days)
    mine = digest(account.id)
    by_day = [r for r in usage.consumption(since, until, "account,day") if r.group[0] == mine]
    mine_in_total = [r for r in usage.consumption(since, until, "account") if r.group[0] == mine]
    return content_free({
        **_row(account, roster, balances, now),
        "sessions": [{"client_label": s.client_label, "issued_at": _iso(s.issued_at), "expires_at": _iso(s.expires_at),
                      "last_active_at": _iso(s.last_active_at), "live": s.live} for s in account.sessions],
        "ai_notice_version": account.ai_notice_version, "unreadable_sessions": listing.unreadable_sessions,
        "usage": {"period": {"since": since.isoformat(), "until": until.isoformat(), "days": days},
                  "totals": _totals(mine_in_total),
                  "by_day": [{"day": day, "calls": next((r.calls for r in by_day if r.group[1] == day), 0),
                              "micro_usd": next((r.micro_usd for r in by_day if r.group[1] == day), 0)}
                             for day in _days(since, until)]}})


def usage_view(roster: Roster, directory: AdminDirectoryPort, usage: AdminUsagePort, now: datetime, days: int = 30) -> dict:
    since, until = _period(now, days)
    by_day_model = list(usage.consumption(since, until, "day,model"))
    by_account = list(usage.consumption(since, until, "account"))
    listing, balances = directory.listing(now), usage.balances()
    names = {digest(a.id): a for a in listing.accounts}
    top = sorted(by_account, key=lambda r: (-r.micro_usd, r.group))[:TOP_ACCOUNTS]
    started = sum(1 for a in listing.accounts if digest(a.id) in balances)
    return content_free({
        "period": {"since": since.isoformat(), "until": until.isoformat(), "days": days},
        "tiles": {**_totals(by_account), "active_accounts": len(by_account),
                  "granted": usage.granted_since(since, until)},
        "models": sorted({r.group[1] for r in by_day_model}),
        "by_day": _by_day(by_day_model, _days(since, until)),
        "by_operation": [{"operation": r.group[0], "calls": r.calls, "micro_usd": r.micro_usd}
                         for r in usage.consumption(since, until, "operation")],
        "by_outcome": [{"outcome": r.group[0], "calls": r.calls} for r in usage.consumption(since, until, "outcome")],
        "top_accounts": [{"id": names[r.group[0]].id if r.group[0] in names else None,
                          "name": names[r.group[0]].name if r.group[0] in names else "",
                          "calls": r.calls, "micro_usd": r.micro_usd} for r in top],
        "funnel": {"waiting": len(listing.waiting), "accounts": len(listing.accounts),
                   "ai_sharing_on": sum(1 for a in listing.accounts if a.ai_sharing),
                   "started_allowance": started, "used_in_period": len(by_account)},
        "answers": {"available": False, "needs": "the turn record"}})


def overview_view(roster: Roster, directory: AdminDirectoryPort, usage: AdminUsagePort, now: datetime) -> dict:
    page = users_view(roster, directory, usage, now)
    week = usage_view(roster, directory, usage, now, 7)
    rows = page["accounts"]
    ending = now + timedelta(days=APPROVAL_ENDING_DAYS)
    attention = [
        {"kind": "allowance_low", "count": sum(1 for r in rows if r["allowance"]["started"]
                                               and r["allowance"]["left_percent"] <= LOW_PERCENT)},
        {"kind": "approval_ending", "count": sum(1 for r in rows if r["professional"]["state"] == "approved"
                                                 and datetime.fromisoformat(r["professional"]["valid_until"]) <= ending)},
        {"kind": "records_unreadable", "count": page["totals"]["unreadable"]},
        {"kind": "sessions_unreadable", "count": page["unreadable_sessions"]},
        {"kind": "registrations_unreadable", "count": 0 if page["waiting_readable"] else 1}]
    return content_free({
        "as_of": now.isoformat(), "accounts": page["totals"],
        "live_sessions": sum(r["live_sessions"] for r in rows),
        "signed_in_last_7_days": sum(1 for r in rows if r["last_sign_in"]
                                     and datetime.fromisoformat(r["last_sign_in"]) >= now - timedelta(days=7)),
        "week": {"tiles": week["tiles"], "by_day": week["by_day"], "models": week["models"]},
        "needs_attention": [item for item in attention if item["count"]],
        "answers": week["answers"]})
