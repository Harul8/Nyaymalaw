"""Durable, conservative spending reservations for an explicitly bounded evaluation.

No prompts, credentials or response text are recorded. An interrupted/failed
attempt keeps its whole reservation, including after a process restart.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from nm.ports.model import ConfigurationError, ProviderUnavailable

# Owner-approved model only. Official model page checked 22 September 2026:
# 128,000 input-context ceiling, 16,384 output ceiling, $0.15/$0.60 per million.
# $0.03 exceeds even the conservative sum of those separate maximum charges.
MODEL = "gpt-4o-mini-2024-07-18"
RESERVATION_MICRO_USD = 30_000


class CallBudget:
    def __init__(self, path: Path, maximum_usd: str, *, model: str = MODEL,
                 price_per_million: tuple[str, str] = ("0.15", "0.60"),
                 reservation_micro_usd: int = RESERVATION_MICRO_USD):
        """A bounded evaluation, pinned to ONE owner-approved model.

        THE DEFAULT IS THE PIN, and every server path relies on it: nothing
        that passes no model can spend on anything but GPT-4o mini. A
        different model is authorised only by EXPLICITLY naming it together
        with its price and a per-call reservation that bounds its worst case
        -- the three facts that make the ledger conservative. Added 23
        September 2026 for one owner-approved measurement of G-CONSISTENT on
        gpt-5.1 (PRD 7.4.1), which the pin correctly refused.

        The price must be the provider's published price, checked when it is
        passed; the reservation must cover the largest charge one call can
        make at the output ceiling the caller sets. An estimate that can
        under-count is not a reservation.
        """
        self.model = model
        self.price_in, self.price_out = (Decimal(x) for x in price_per_million)
        self.reservation = int(reservation_micro_usd)
        if self.reservation <= 0:
            raise ConfigurationError("A per-call reservation must be positive.")
        amount = Decimal(maximum_usd)
        if not amount.is_finite() or amount <= 0 or amount > 25:
            raise ConfigurationError("Evaluation budget must be positive and at most USD25.")
        self.path = Path(path)
        self.maximum = int(amount * 1_000_000)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS budget ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton=1), maximum INTEGER NOT NULL)"
            )
            db.execute("INSERT OR IGNORE INTO budget VALUES (1, ?)", (self.maximum,))
            if (
                db.execute("SELECT maximum FROM budget WHERE singleton=1").fetchone()[0]
                != self.maximum
            ):
                raise ConfigurationError("Existing evaluation budget cannot be reset or enlarged.")
            db.execute(
                "CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, at TEXT NOT NULL, "
                "charge INTEGER NOT NULL, state TEXT NOT NULL, model TEXT NOT NULL, "
                "response_id TEXT, tokens_in INTEGER, tokens_out INTEGER)"
            )

    @contextmanager
    def _connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            yield db

    def reserve(self, model: str) -> str:
        if model != self.model:
            raise ConfigurationError(
                f"This evaluation authorises only the pinned {self.model} model."
            )
        token = str(uuid.uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(charge),0) FROM attempts").fetchone()[0]
            if spent + self.reservation > self.maximum:
                raise ProviderUnavailable(
                    "The approved evaluation budget cannot fund another bounded request."
                )
            db.execute(
                "INSERT INTO attempts (id,at,charge,state,model) VALUES (?,?,?,?,?)",
                (
                    token,
                    datetime.now(timezone.utc).isoformat(),
                    self.reservation,
                    "reserved_or_unknown",
                    model,
                ),
            )
        return token

    def settle(self, token: str, response) -> None:
        usage = getattr(response, "usage", None)
        incoming = getattr(usage, "prompt_tokens", None)
        outgoing = getattr(usage, "completion_tokens", None)
        if any(type(x) is not int or x < 0 for x in (incoming, outgoing)):
            return  # Unknown usage retains the full reservation; never pretend zero.
        cost = int(
            (
                Decimal(incoming) * self.price_in + Decimal(outgoing) * self.price_out
            ).to_integral_value(rounding=ROUND_CEILING)
        )
        if cost > self.reservation:
            raise ProviderUnavailable(
                "Provider usage exceeded the evaluation model's reserved bound."
            )
        with self._connect() as db:
            changed = db.execute(
                "UPDATE attempts SET charge=?,state='measured',response_id=?,"
                "tokens_in=?,tokens_out=? "
                "WHERE id=? AND state='reserved_or_unknown'",
                (cost, str(getattr(response, "id", "")), incoming, outgoing, token),
            )
            if changed.rowcount != 1:
                raise ProviderUnavailable("Evaluation reservation was absent or already settled.")
