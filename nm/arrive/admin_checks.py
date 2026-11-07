"""The facts the Admin diagnostics are made of: counts, sizes and short names read from this installation (plan AN.46, piece 46i; D119).

CONTENT-FREE, READ-ONLY, EACH ON ITS OWN. Every method here reads one source and returns numbers and short fixed names. The sign-in log
is counted by kind - never by who - and a problem is a kind and a count, never a message. A source that cannot be read returns None for
that method (or raises AdminUnavailable), so the one check says it could not be made and the other checks stand (D128). Nothing here
opens a conversation, a file of an advocate's, an account record or a key.

THE LAW'S FILES ARE CHECKED BY SIZE, NOT BY HASH. The held-law lineage records name the vector index, the passage store and the word
index with the size each had when it was recorded; this compares sizes (a stat, not a four-gigabyte read) and says so. A matching size
is not the proof that a full hash is; the figure is "present and the size recorded", and the page says exactly that.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping

from nm.arrive.admin_port import AdminUnavailable

_log = logging.getLogger("nm.admin")
#: How much of the end of the sign-in log is read: recent behaviour only.
_LOG_TAIL_BYTES = 2_000_000
_ATTEMPT_STATES = ("running", "retryable", "unconfirmed", "terminal", "finished")
#: The kinds a sign-in log line is counted as, by what it starts with. Nothing after the kind is kept.
_AUTH_KINDS = (
    ("signed_in", "authenticated"), ("wrong_password", "wrong password"), ("unknown_account", "no such advocate"),
    ("session_ended_idle", "session refused: no activity"), ("session_ended_signed_out", "session refused: signed out"),
    ("record_unreadable", "record unreadable"), ("recovery_refused", "recovery refused"),
    ("reset_refused", "password reset refused"), ("activity_not_recorded", "session activity not recorded"))
_LAW = (("acts", "bare_acts.lineage.json"), ("judgments", "judgments.lineage.json"))


class AdminChecks:
    """The checks' sources for one installation. See the module's note."""

    def __init__(self, *, storage: Path, root: Path, settings: Mapping[str, str], corpus_dir: Path | None = None):
        self.storage, self.root, self.settings = Path(storage), Path(root), settings
        chosen = Path(corpus_dir or settings.get("NM_CORPUS_DIR") or self.root / "legal_database" / "vector_store")
        self.corpus = chosen if chosen.is_absolute() else self.root / chosen

    # -------------------------------------------------------------- turns in progress ---

    def turn_attempts(self) -> Mapping[str, int] | None:
        """How many requests are in each state. None where the file would not open; zeros where it has not been made."""
        path = self.storage / "turn-attempts.sqlite"
        if not path.exists():
            return {state: 0 for state in _ATTEMPT_STATES}
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
                found = dict(db.execute("SELECT state, COUNT(*) FROM turn_attempts GROUP BY state").fetchall())
        except (OSError, sqlite3.Error):
            return None
        return {state: int(found.get(state, 0)) for state in _ATTEMPT_STATES}

    # ------------------------------------------------------------- sign-in security ---

    def sign_ins(self, since: datetime) -> Mapping[str, int] | None:
        """Sign-in log lines since a local time, counted by kind. None where the log would not read; zeros where it has none."""
        path = self.storage / "auth.log"
        counts = {name: 0 for name, _ in _AUTH_KINDS} | {"other": 0}
        if not path.exists():
            return counts
        try:
            with path.open("rb") as handle:
                size = handle.seek(0, os.SEEK_END)
                handle.seek(max(0, size - _LOG_TAIL_BYTES))
                text = handle.read().decode("utf8", "replace")
        except OSError:
            return None
        for line in text.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            try:
                when = datetime.fromisoformat(parts[0])
            except ValueError:
                continue
            if when < since:
                continue
            what = parts[2].strip().lower()
            counts[next((name for name, start in _AUTH_KINDS if what.startswith(start)), "other")] += 1
        return counts

    # --------------------------------------------------------------------- the disk ---

    def disk(self) -> Mapping[str, Mapping[str, int]] | None:
        """Free and total bytes of the disk the accounts and their records are kept on and of the one the law is kept on."""
        found = {}
        try:
            for name, where in (("records", self.storage), ("law", self.corpus)):
                usage = shutil.disk_usage(where)
                found[name] = {"free": usage.free, "total": usage.total}
        except OSError:
            return None
        return found

    # ------------------------------------------------------------------ the law held ---

    def law(self) -> tuple[Mapping, ...]:
        """The two held-law stores as their lineage records name them: passages, vectors, when recorded, the verified sample, and
        whether the files named are present at the size recorded. A record that would not read is reported as such."""
        found = []
        for name, file in _LAW:
            entry: dict = {"collection": name, "readable": False}
            try:
                record = json.loads((self.root / ".nm" / "retrieval" / file).read_text(encoding="utf8"))
                files = (("vector_index", record["vector_index"]["path"], record["vector_index"].get("bytes")),
                         ("passage_store", record["passage_store"]["path"], None))
                present = all((self.corpus / path).exists() for _, path, _ in files)
                sizes = all(expected is None or (self.corpus / path).stat().st_size == expected
                            for _, path, expected in files if (self.corpus / path).exists())
                verified = record.get("verified") or {}
                entry.update(readable=True, passages=int(record["passages"]), vectors=int(record["vector_index"]["vectors"]),
                             model=str(record.get("model", "")), recorded_at=str(record.get("recorded_at", "")),
                             sampled=int(verified.get("sampled", 0)), same_vector=int(verified.get("same_vector", 0)),
                             files_present=present, sizes_as_recorded=present and sizes,
                             bm25_present=(self.corpus / record["bm25"]["path"]).is_dir())
            except (OSError, ValueError, KeyError, TypeError):
                pass
            found.append(entry)
        return tuple(found)

    # ------------------------------------------------------------- the document scanner ---

    def scanner(self) -> Mapping[str, object]:
        """Whether the malware scanner the settings name is there, and how old its definitions are (an advocate's file is read only after
        this clears it, so a scanner that is missing holds every upload)."""
        scan, definitions = self.settings.get("NM_CLAMSCAN"), self.settings.get("NM_CLAMAV_DATABASE")
        if not scan or not definitions:
            return {"configured": False, "present": False, "definitions_age_days": None}
        newest = None
        try:
            stamps = [p.stat().st_mtime for p in Path(definitions).iterdir() if p.suffix.lower() in (".cvd", ".cld")]
            newest = max(stamps) if stamps else None
        except OSError:
            newest = None
        age = None if newest is None else round((datetime.now().timestamp() - newest) / 86400, 1)
        return {"configured": True, "present": Path(scan).exists(), "definitions_age_days": age}

    # --------------------------------------------------------------------- the outbox ---

    def outbox(self) -> Mapping[str, object]:
        """How many messages wait in the local outbox, and whether any mail leaves this computer at all."""
        provider, delivery = self.settings.get("NM_MAIL_PROVIDER", "local-outbox"), self.settings.get("NM_MAIL_DELIVERY", "disabled")
        try:
            waiting = sum(1 for p in (self.storage / "outbox").iterdir() if p.is_file()) if (self.storage / "outbox").is_dir() else 0
        except OSError:
            raise AdminUnavailable("outbox") from None
        return {"provider": provider, "delivery": delivery, "queued": waiting,
                "reaches_a_mailbox": provider != "local-outbox" and delivery == "enabled"}
