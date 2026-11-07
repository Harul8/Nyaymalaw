"""The turn record as the Admin area reads it: how many answers a day, how each turn ended, how long answers took (plan AN.46, piece
46r; owner decision D120, 7 Nov 2026), changing nothing.

READ-ONLY AND CONTENT-FREE. The file holds one line per finished turn - when, how long, how it ended, the model and effort chosen, the
number of calls, the cost and the number of documents - and names the account only by a digest (nm/arrive/store_turn_events.py). This
opens it read-only, with the store's own rule for a file it made, and returns counts by Indian day, the outcome totals and the middle and
slow ends of the time an answer took. Nothing here returns a digest, an account, a model or an effort: the Admin pages show how the
service is used, not who used it in what words.

A RECORD THAT HAS NOT BEGUN IS EMPTY, NOT BROKEN. The file is made when the first turn after the record was applied ends, so a missing
file reads as no turns (and `first_at` None says the record has not started). A file that is there and is not the store, or will not
open, is `AdminUnavailable`: the view says so and never shows it as no answers.

The days before `first_at` were not recorded; a view says the record began then, and never counts them as quiet days.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from nm.arrive.admin_port import AdminUnavailable, TurnDay, TurnsSummary
from nm.arrive.admin_usage import DAY_SHIFT_MINUTES
from nm.arrive.store_turn_events import FileTurnEvents
from nm.arrive.turn_event_port import OUTCOMES
from nm.shared.sqlite_creation import why

_log = logging.getLogger("nm.admin")
_DAY = f"date(ended_at, '+{DAY_SHIFT_MINUTES} minutes')"


def _instant(value: datetime) -> str:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("a period is asked for in times that have their zone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _rank(sorted_seconds: list[int], share: float) -> int | None:
    """The nearest-rank percentile: the smallest time that `share` of the answers took no longer than."""
    if not sorted_seconds:
        return None
    index = max(0, -(-int(share * 100) * len(sorted_seconds) // 100) - 1)
    return sorted_seconds[min(index, len(sorted_seconds) - 1)]


class AdminTurns:
    """The turn record of one installation, read for the Admin area. See the module's note."""

    def __init__(self, path):
        self.path = Path(path).resolve()

    def _read(self, sql: str, params: tuple = ()) -> list[tuple]:
        if not self.path.exists():
            return []
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
                FileTurnEvents._schema(db)  # the store's own rule for a file it made
                return db.execute(sql, params).fetchall()
        except (OSError, sqlite3.Error, ValueError) as exc:
            _log.warning("The turn record could not be read for the admin area (%s).", why(exc))
            raise AdminUnavailable("turn record") from None

    def summary(self, since: datetime, until: datetime) -> TurnsSummary:
        window = (_instant(since), _instant(until))
        counted = self._read(f"SELECT {_DAY}, outcome, COUNT(*) FROM turns WHERE ended_at >= ? AND ended_at < ? "
                             f"GROUP BY {_DAY}, outcome", window)
        per_day: dict[str, dict[str, int]] = {}
        for day, outcome, count in counted:
            per_day.setdefault(day, {name: 0 for name in OUTCOMES})[outcome] = count
        seconds = sorted(row[0] for row in self._read(
            "SELECT seconds FROM turns WHERE outcome='answered' AND ended_at >= ? AND ended_at < ?", window))
        first = self._read("SELECT MIN(ended_at) FROM turns")
        return TurnsSummary(
            by_day=tuple(TurnDay(day, **counts) for day, counts in sorted(per_day.items())),
            answered_seconds_middle=_rank(seconds, 0.5), answered_seconds_slow=_rank(seconds, 0.9),
            first_at=datetime.fromisoformat(first[0][0]) if first and first[0][0] else None)
