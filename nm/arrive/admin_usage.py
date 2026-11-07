"""Usage as the Admin area reads it: balances and consumption, content-free, changing nothing (plan AN.46, piece 46e; D119).

READ-ONLY, ON PURPOSE. `FileUsage.standing` gives an account its trial the first time it is read, which is right for an advocate
who is about to use the product and wrong for an admin looking at a list: reading a person's balance must never be what starts it.
This opens the same file read-only, and an account with no record is simply absent from the balances ("not started").

WHAT COMES BACK. Balances by account digest (the SHA-256 of the canonical id, as the store names accounts; the Admin views join the
digest to an address from the directory, so no address is read from here), and calls grouped by day, model, operation, outcome or
account, in numbers: how many, what they cost, tokens in and out, cache reads and writes, audio seconds. A call whose cost the
provider did not establish is counted apart and never priced. There is no prompt, answer or file in this store to return.

A DAY IS AN INDIAN DAY. The users are in India (owner, 26 Oct 2026), so a day runs from midnight Indian time and the daily figures
read as the advocates lived the day; the times asked for stay absolute.

A MISSING FILE IS AN EMPTY STORE (nothing has been used yet; the store is made at its first use). A file that is there and is not
the usage store, or will not open, is `AdminUnavailable`: the view says so, and never shows it as no usage.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from nm.arrive.admin_port import GROUPINGS, AdminUnavailable, Balance, Consumption
from nm.arrive.store_usage import FileUsage
from nm.arrive.usage_port import percent_left
from nm.shared.sqlite_creation import why

_log = logging.getLogger("nm.admin")

#: Indian Standard Time, UTC+5:30, in minutes: the shift that makes SQLite's date() an Indian day.
DAY_SHIFT_MINUTES = 330
_DAY = f"date(at, '+{DAY_SHIFT_MINUTES} minutes')"
#: The whitelist of groupings: nothing a caller sends is ever put into a statement.
_GROUP_SQL = {
    "day": (_DAY,),
    "model": ("model",),
    "operation": ("operation",),
    "outcome": ("outcome",),
    "account": ("account",),
    "day,model": (_DAY, "model"),
    "account,day": ("account", _DAY),
}
assert set(_GROUP_SQL) == set(GROUPINGS)


def _instant(value: datetime) -> str:
    """The text the store writes times in, so that text order is time order."""
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("a period is asked for in times that have their zone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


class AdminUsage:
    """The usage sidecar of one installation, read for the Admin area. See the module's note."""

    def __init__(self, path):
        self.path = Path(path).resolve()

    def _read(self, sql: str, params: tuple = ()) -> list[tuple]:
        if not self.path.exists():
            return []
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
                FileUsage._schema(db)  # the store's own rule for a file it made
                return db.execute(sql, params).fetchall()
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The usage store could not be read for the admin area (%s).", why(exc))
            raise AdminUnavailable("usage") from None

    def balances(self) -> Mapping[str, Balance]:
        granted = dict(self._read("SELECT account, SUM(micro_usd) FROM grants GROUP BY account"))
        spent = dict(self._read("SELECT account, COALESCE(SUM(micro_usd),0) FROM calls GROUP BY account"))
        return {account: Balance(granted.get(account, 0), spent.get(account, 0),
                                 percent_left(granted.get(account, 0), spent.get(account, 0)))
                for account in sorted(set(granted) | set(spent))}

    def consumption(self, since: datetime, until: datetime, grouping: str) -> Sequence[Consumption]:
        if grouping not in _GROUP_SQL:
            raise ValueError("usage can be grouped by day, model, operation, outcome or account")
        keys = ", ".join(_GROUP_SQL[grouping])
        rows = self._read(
            f"SELECT {keys}, COUNT(*), COALESCE(SUM(micro_usd),0), COALESCE(SUM(micro_usd IS NULL),0), "
            "COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0), COALESCE(SUM(cached_tokens),0), "
            "COALESCE(SUM(cache_write_tokens),0), COALESCE(SUM(audio_seconds),0) "
            f"FROM calls WHERE at >= ? AND at < ? GROUP BY {keys} ORDER BY {keys}", (_instant(since), _instant(until)))
        width = len(_GROUP_SQL[grouping])
        return tuple(Consumption(tuple(str(part) for part in row[:width]), *row[width:width + 7], float(row[width + 7]))
                     for row in rows)

    def granted_since(self, since: datetime, until: datetime) -> int:
        rows = self._read("SELECT COALESCE(SUM(micro_usd),0) FROM grants WHERE at >= ? AND at < ?",
                          (_instant(since), _instant(until)))
        return rows[0][0] if rows else 0
