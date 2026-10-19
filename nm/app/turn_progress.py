"""What a turn in progress is doing, for the advocate who sent it (owner decision, 14 Oct 2026).

A turn now takes minutes. The turn reports each stage here; the advocate's browser
reads it while waiting and after a reload. Only stage names, counts and times are
kept, never message, legal or model content, and each advocate reads only their own
turns. Entries are memory only and lapse KEEP_SECONDS after the turn ends; a reader
that finds none is told the progress is unknown, never that the turn failed.

From 19 Oct 2026 (owner decisions P26 and P27) a turn also says how many times its answer
has shown more, and which conversation it belongs to: what it shows is saved, sealed,
with that conversation, which the browser reads (never from here).
"""
from __future__ import annotations

import re
import threading
import time

KEEP_SECONDS = 900
STAGES = {
    "understanding": "Reading your message",
    "understanding_matter": "Working out the disputes and the legal questions",
    "checking_understanding": "Checking that understanding against the conversation",
    "revising_understanding": "Correcting the understanding",
    "writing_search_terms": "Writing search terms for each legal question",
    "searching": "Searching the statutes and judgments",
    "choosing_provisions": "Choosing the provisions and judgments that answer each question",
    "writing": "Writing the answer",
    "checking_authorities": "Checking the cited sources",
    "reviewing": "Reviewing the answer independently",
    "revising": "Revising the answer after review",
    # Answering dispute by dispute (owner decisions P26 and P27, 19 Oct 2026).
    "checking_across": "Checking the sections against each other",
    "writing_overview": "Writing the overview",
    "saving": "Saving the answer",
}
#: Counts a stage may report; anything else is dropped.
DETAIL = ("done", "total", "round")
#: A conversation's identity as the browser names it; anything else is dropped.
_CHAT = re.compile(r"[A-Za-z0-9_-]{1,120}\Z")


class TurnProgress:
    def __init__(self, *, clock=time.monotonic, keep_seconds=KEEP_SECONDS):
        self._clock, self._keep = clock, keep_seconds
        self._rows: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def _prune(self, now):
        for key in [k for k, row in self._rows.items() if row["ended"] is not None and now - row["ended"] > self._keep]:
            del self._rows[key]

    def report(self, advocate_id, turn_id, stage, detail=None):
        if stage not in STAGES or not isinstance(advocate_id, str) or not isinstance(turn_id, str):
            return
        counts = {k: v for k, v in (detail or {}).items() if k in DETAIL and type(v) is int and v >= 0}
        now = self._clock()
        with self._lock:
            self._prune(now)
            row = self._rows.get((advocate_id, turn_id))
            if row is None or row["ended"] is not None:
                row = self._rows[(advocate_id, turn_id)] = {"started": now, "ended": None, "state": "working",
                                                            "steps": []}
            if not row["steps"] or row["steps"][-1]["stage"] != stage:
                row["steps"].append({"stage": stage, "at": now})
            row["detail"] = counts

    def shown(self, advocate_id, turn_id, count, chat_id):
        """The turn's answer has shown more (P26): how many times so far, and the conversation
        whose saved record holds what it shows. Never the content itself."""
        if (type(count) is not int or count < 1 or not isinstance(chat_id, str) or not _CHAT.match(chat_id)
                or not isinstance(advocate_id, str) or not isinstance(turn_id, str)):
            return
        with self._lock:
            row = self._rows.get((advocate_id, turn_id))
            if row is not None and row["ended"] is None:
                row["shown"], row["chat_id"] = max(count, row.get("shown", 0)), chat_id

    def end(self, advocate_id, turn_id, state):
        """state is "finished" (an answer was saved or replayed) or "stopped"."""
        with self._lock:
            row = self._rows.get((advocate_id, turn_id))
            if row is not None and row["ended"] is None:
                row["ended"], row["state"] = self._clock(), state if state in ("finished", "stopped") else "stopped"

    def read(self, advocate_id, turn_id):
        now = self._clock()
        with self._lock:
            self._prune(now)
            row = self._rows.get((advocate_id, turn_id))
            if row is None:
                return {"state": "unknown"}
            steps, until = row["steps"], row["ended"] if row["ended"] is not None else now
            current = steps[-1] if steps else None
            return {"state": row["state"],
                    "stage": current["stage"] if current else None,
                    "label": STAGES[current["stage"]] if current else None,
                    "detail": dict(row.get("detail") or {}),
                    "shown": row.get("shown", 0), "chat_id": row.get("chat_id"),
                    "elapsed_seconds": int(until - row["started"]),
                    "steps": [{"label": STAGES[step["stage"]],
                               "seconds": int((steps[i + 1]["at"] if i + 1 < len(steps) else until) - step["at"])}
                              for i, step in enumerate(steps)]}
