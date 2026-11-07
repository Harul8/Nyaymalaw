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
from nm.arrive.admin_port import (AdminAccount, AdminChecksPort, AdminDirectoryPort, AdminLibraryPort, AdminRecordPort,
                                  AdminTurnsPort, AdminUnavailable, AdminUsagePort, Balance, Consumption)
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


def _level(roster: Roster, account: AdminAccount) -> str:
    """The settings' level when they name the account, else admin when the account's own type says so, else advocate."""
    level = roster.level_of(account.id)
    if level is not None:
        return level.value
    return "admin" if account.user_type == "admin" else "advocate"


def _allowance(balance: Balance | None) -> dict:
    if balance is None:
        return {"started": False, "granted": None, "spent": None, "left_percent": None}
    return {"started": True, "granted": balance.granted, "spent": balance.spent, "left_percent": balance.left_percent}


def _row(account: AdminAccount, roster: Roster, balances: Mapping[str, Balance], now: datetime) -> dict:
    status = "unreadable" if not account.readable else "suspended" if account.suspended else "active"
    return {
        "id": account.id, "name": account.name, "enrolment": account.enrolment, "firm_id": account.firm_id,
        "level": _level(roster, account), "level_label": LEVEL_LABELS[_level(roster, account)], "status": status,
        "user_type": "admin" if _level(roster, account) != "advocate" else "advocate",
        "type_locked": roster.level_of(account.id) is not None,
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


def _answers(turns: AdminTurnsPort | None, since: datetime, until: datetime, days: list[str]) -> dict:
    """The turn record's part of the Usage page (D120): answers a day, how turns ended, how long an answer took. A part that cannot be
    read says so and leaves the rest of the page standing (D128); no turn port at all is the old "needs the turn record"."""
    if turns is None:
        return {"available": False, "needs": "the turn record"}
    try:
        summary = turns.summary(since, until)
    except AdminUnavailable:
        return {"available": False, "unreadable": True}
    found = {t.day: t for t in summary.by_day}
    rows = [{"day": day, **({"answered": found[day].answered, "stopped": found[day].stopped, "refused": found[day].refused,
                            "failed": found[day].failed} if day in found else
                           {"answered": 0, "stopped": 0, "refused": 0, "failed": 0})} for day in days]
    return {"available": True, "began": _iso(summary.first_at), "by_day": rows,
            "totals": {name: sum(r[name] for r in rows) for name in ("answered", "stopped", "refused", "failed")},
            "seconds_middle": summary.answered_seconds_middle, "seconds_slow": summary.answered_seconds_slow}


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


def usage_view(roster: Roster, directory: AdminDirectoryPort, usage: AdminUsagePort, now: datetime, days: int = 30,
               turns: AdminTurnsPort | None = None) -> dict:
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
        "answers": _answers(turns, since, until, _days(since, until))})


def overview_view(roster: Roster, directory: AdminDirectoryPort, usage: AdminUsagePort, now: datetime,
                  turns: AdminTurnsPort | None = None) -> dict:
    page = users_view(roster, directory, usage, now)
    week = usage_view(roster, directory, usage, now, 7, turns)
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


def access_view(roster: Roster, directory: AdminDirectoryPort, record: AdminRecordPort, now: datetime, *, limit: int = 100) -> dict:
    """Who is an admin and what they have done (D117, D126): the settings' roster beside what the directory knows of those accounts,
    the audit log newest first, and whether its chain still holds. A log that cannot be read is said to be unreadable; the roster
    still shows."""
    known = {a.id: a for a in directory.listing(now).accounts}
    def line(who: str, level: str, source: str) -> dict:
        return {"id": who, "level": level, "label": LEVEL_LABELS[level], "source": source,
                "name": known[who].name if who in known else "", "has_account": who in known,
                "status": ("unreadable" if not known[who].readable else "suspended" if known[who].suspended else "active")
                if who in known else "no account"}

    admins = [line(who, level.value, "server settings") for who, level in roster.named()]
    admins += [line(a.id, "admin", "set by an admin") for a in sorted(known.values(), key=lambda a: a.id)
               if a.readable and a.user_type == "admin" and roster.level_of(a.id) is None]
    try:
        check, entries = record.verify(), record.entries(limit=limit)
        audit = {"available": True,
                 "chain": {"ok": check.ok, "entries": check.entries, "first_bad_id": check.first_bad_id, "newest": check.newest},
                 "entries": [{"id": e.id, "at": _iso(e.at), "actor": e.actor, "action": e.action, "target": e.target,
                              "reason": e.reason, "outcome": e.outcome, "fingerprint": e.fingerprint} for e in entries]}
    except AdminUnavailable:
        audit = {"available": False}
    return content_free({"as_of": now.isoformat(), "admins": admins, "rejected_entries": roster.rejected, "audit": audit})


# ------------------------------------------------------------------------ diagnostics ---

#: A disk with less free than this is called low.
LOW_DISK_BYTES = 20 * 1024 ** 3
LOW_DISK_SHARE = 0.10
#: The malware scanner's definitions older than this many days are called old.
OLD_DEFINITIONS_DAYS = 3
#: A day with this many wrong sign-ins is called busy.
BUSY_WRONG_SIGN_INS = 20
#: A local outbox with this many unread messages is called filling up.
FULL_OUTBOX = 20
#: The share of model calls that did not end well before the model service is called unwell, once there are enough calls to say.
UNWELL_SHARE = 0.10
ENOUGH_CALLS = 5


def _check(name: str, label: str, state: str, facts: dict) -> dict:
    return {"id": name, "label": label, "state": state, "facts": facts}


def _could_not(name: str, label: str) -> dict:
    return _check(name, label, "unavailable", {})


def diagnostics_view(roster: Roster, usage: AdminUsagePort, turns: AdminTurnsPort, checks: AdminChecksPort, now: datetime,
                     serving: Mapping[str, Any], provider: Mapping[str, Any]) -> dict:
    """Is the service well? Each check reads one source and says ok, attention, note or unavailable; a source that cannot be read makes
    only its own check unavailable (D128). Facts are counts, sizes and short names - never an address, a message or a word of anyone's
    work; recent problems are a kind and a count."""
    day_ago = now - timedelta(hours=24)
    found: list[dict] = []

    state = serving.get("code_state")
    found.append(_check("server", "The server and its code", {"current": "ok", "stale": "attention"}.get(state, "unavailable"),
                        {"code_state": state or "not_assessed", "running_code": str(serving.get("serving", ""))[:12],
                         "code_on_disk": str(serving.get("tree", ""))[:12]}))

    try:
        outcomes = {r.group[0]: r.calls for r in usage.consumption(day_ago, now, "outcome")}
        total, bad = sum(outcomes.values()), sum(n for k, n in outcomes.items() if k != "ok")
        found.append(_check("model_service", "The model service (calls in the last 24 hours)",
                            "attention" if total >= ENOUGH_CALLS and bad / total > UNWELL_SHARE else "ok",
                            {"provider": provider.get("provider"), "model": provider.get("model"), "calls": total,
                             "not_ok": bad, "by_outcome": outcomes}))
    except AdminUnavailable:
        found.append(_could_not("model_service", "The model service (calls in the last 24 hours)"))

    attempts = checks.turn_attempts()
    if attempts is None:
        found.append(_could_not("turns_in_progress", "Turns in progress"))
    else:
        found.append(_check("turns_in_progress", "Turns in progress", "attention" if attempts["unconfirmed"] else "ok",
                            {"running": attempts["running"], "stopped_and_waiting": attempts["retryable"],
                             "unconfirmed": attempts["unconfirmed"]}))
    try:
        recent = turns.summary(day_ago, now)
        ended = {name: sum(getattr(d, name) for d in recent.by_day) for name in ("answered", "stopped", "refused", "failed")}
        made = sum(ended.values())
        found.append(_check("recent_turns", "Turns in the last 24 hours",
                            "attention" if made >= ENOUGH_CALLS and ended["failed"] / made > UNWELL_SHARE else "ok",
                            {**ended, "seconds_middle": recent.answered_seconds_middle,
                             "seconds_slow": recent.answered_seconds_slow, "record_began": _iso(recent.first_at)}))
    except AdminUnavailable:
        found.append(_could_not("recent_turns", "Turns in the last 24 hours"))

    for store in checks.law():
        label = f"The held {store['collection']}"
        if not store.get("readable"):
            found.append(_could_not(f"law_{store['collection']}", label))
            continue
        well = (store["files_present"] and store["sizes_as_recorded"] and store["bm25_present"]
                and store["sampled"] == store["same_vector"] and store["passages"] <= store["vectors"])
        found.append(_check(f"law_{store['collection']}", label, "ok" if well else "attention", {
            "passages": store["passages"], "vectors": store["vectors"], "model": store["model"],
            "recorded_at": store["recorded_at"], "sampled": store["sampled"], "same_vector": store["same_vector"],
            "files_present": store["files_present"], "sizes_as_recorded": store["sizes_as_recorded"],
            "word_index_present": store["bm25_present"], "checked_by": "size, not by hash"}))

    scanner = checks.scanner()
    age = scanner["definitions_age_days"]
    found.append(_check("scanner", "The document scanner",
                        "ok" if scanner["configured"] and scanner["present"] and age is not None and age <= OLD_DEFINITIONS_DAYS
                        else "attention", dict(scanner)))

    sign_ins = checks.sign_ins(datetime.now() - timedelta(hours=24))
    if sign_ins is None:
        found.append(_could_not("sign_in_security", "Sign-in security (last 24 hours)"))
    else:
        found.append(_check("sign_in_security", "Sign-in security (last 24 hours)",
                            "attention" if sign_ins["wrong_password"] + sign_ins["unknown_account"] >= BUSY_WRONG_SIGN_INS else "ok",
                            dict(sign_ins)))

    disk = checks.disk()
    if disk is None:
        found.append(_could_not("disk", "Free disk"))
    else:
        low = any(d["free"] < LOW_DISK_BYTES or d["free"] / d["total"] < LOW_DISK_SHARE for d in disk.values() if d["total"])
        found.append(_check("disk", "Free disk", "attention" if low else "ok", {k: dict(v) for k, v in disk.items()}))

    try:
        outbox = checks.outbox()
        found.append(_check("mail", "Account mail", "attention" if outbox["queued"] >= FULL_OUTBOX
                            else "ok" if outbox["reaches_a_mailbox"] else "note", dict(outbox)))
    except AdminUnavailable:
        found.append(_could_not("mail", "Account mail"))

    found.append(_check("admin_setting", "The admin list in the server's settings", "attention" if roster.rejected else "ok",
                        {"admins": len(roster.levels), "entries_ignored": roster.rejected}))
    counts = {name: sum(1 for c in found if c["state"] == name) for name in ("ok", "attention", "note", "unavailable")}
    return content_free({"as_of": now.isoformat(), "summary": counts, "checks": found})


# ---------------------------------------------------------------------------- the library ---

def library_view(library: AdminLibraryPort, now: datetime) -> dict:
    """What the held law holds (D122): counts and descriptions of the stores and what has been set aside or built beside them. The
    law is public, but the view still carries only descriptions - no passage, no judgment's words, no index."""
    return content_free({"as_of": now.isoformat(), **library.library()})
