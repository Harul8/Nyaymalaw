"""Durable, conservative spending reservations for an explicitly bounded evaluation.

No prompts, credentials or response text are recorded. An interrupted/failed
attempt keeps its whole reservation, including after a process restart.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path

from nm.ports.model import ConfigurationError, ProviderUnavailable, Usage

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
        if not isinstance(model, str) or not model.strip():
            raise ConfigurationError("An evaluation needs an explicit model identity.")
        self.model = model
        try:
            self.price_in, self.price_out = (Decimal(x) for x in price_per_million)
            amount = Decimal(maximum_usd)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ConfigurationError("Evaluation prices and budget must be numeric.") from exc
        if any(not price.is_finite() or price < 0 for price in (self.price_in, self.price_out)):
            raise ConfigurationError("Evaluation prices must be finite and nonnegative.")
        self.reservation = reservation_micro_usd
        if type(self.reservation) is not int or self.reservation <= 0:
            raise ConfigurationError("A per-call reservation must be positive.")
        if not amount.is_finite() or amount <= 0 or amount > 25:
            raise ConfigurationError("Evaluation budget must be positive and at most USD25.")
        self.path = Path(path)
        self.maximum = int(amount * 1_000_000)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
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
            # Old unknown attempts stay charged; absence of their price terms
            # cannot be retrospectively treated as authority to release money.
            columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
            for name, kind in (("price_in", "TEXT"), ("price_out", "TEXT"),
                               ("reservation", "INTEGER")):
                if name not in columns:
                    db.execute(f"ALTER TABLE attempts ADD COLUMN {name} {kind}")

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
            if db.execute("SELECT 1 FROM attempts WHERE state='measured_over_bound'").fetchone():
                raise ProviderUnavailable(
                    "A measured request exceeded its bound; approval needs review.")
            spent = db.execute("SELECT COALESCE(SUM(charge),0) FROM attempts").fetchone()[0]
            if spent + self.reservation > self.maximum:
                raise ProviderUnavailable(
                    "The approved evaluation budget cannot fund another bounded request."
                )
            db.execute(
                "INSERT INTO attempts (id,at,charge,state,model,price_in,price_out,reservation) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    token,
                    datetime.now(timezone.utc).isoformat(),
                    self.reservation,
                    "reserved_or_unknown",
                    model,
                    str(self.price_in),
                    str(self.price_out),
                    self.reservation,
                ),
            )
        return token

    def status(self) -> dict:
        """Content-free measured and unknown spending across the shared ledger.

        An unknown outcome stays charged; zero measured usage is not reported
        as zero total consumption. Reading cannot refund or reset any attempt.
        """
        with self._connect() as db:
            rows = db.execute("SELECT model,state,COUNT(*),SUM(charge) FROM attempts "
                              "GROUP BY model,state ORDER BY model,state").fetchall()
        measured = sum(charge for _, state, _, charge in rows if state.startswith("measured"))
        unknown = sum(charge for _, state, _, charge in rows if not state.startswith("measured"))
        return {"maximum_usd": self.maximum / 1_000_000,
                "charged_usd": (measured + unknown) / 1_000_000,
                "measured_usd": measured / 1_000_000,
                "reserved_or_unknown_usd": unknown / 1_000_000,
                "attempts": sum(count for _, _, count, _ in rows),
                "models": [{"model": model, "state": state, "attempts": count,
                            "charged_usd": charge / 1_000_000}
                           for model, state, count, charge in rows]}

    def settle(self, token: str, response) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            held = db.execute("SELECT model,price_in,price_out,reservation,state FROM attempts "
                              "WHERE id=?", (token,)).fetchone()
            if held is None or held[4] != "reserved_or_unknown":
                raise ProviderUnavailable("Evaluation reservation was absent or already settled.")
            if held[:4] != (self.model, str(self.price_in), str(self.price_out), self.reservation):
                raise ConfigurationError(
                    "A reservation can be settled only under its captured model/prices.")
            returned_model = getattr(response, "model", None)
            if returned_model is not None and returned_model != held[0]:
                raise ConfigurationError("Provider response changed the reserved model identity.")
            usage = getattr(response, "usage", None)
            incoming = getattr(usage, "prompt_tokens", None)
            outgoing = getattr(usage, "completion_tokens", None)
            if any(type(x) is not int or x < 0 for x in (incoming, outgoing)):
                return  # Unknown usage retains the whole reservation.
            cost = int((Decimal(incoming) * self.price_in + Decimal(outgoing) * self.price_out
                        ).to_integral_value(rounding=ROUND_CEILING))
            state = "measured_over_bound" if cost > held[3] else "measured"
            changed = db.execute(
                "UPDATE attempts SET charge=?,state=?,response_id=?,"
                "tokens_in=?,tokens_out=? "
                "WHERE id=? AND state='reserved_or_unknown'",
                (cost, state, str(getattr(response, "id", "")), incoming, outgoing, token),
            )
            if changed.rowcount != 1:
                raise ProviderUnavailable("Evaluation reservation was absent or already settled.")
        if state == "measured_over_bound":
            # Commit measured spending before refusing. Rolling back here would
            # leave the smaller reservation as a false statement of actual cost.
            raise ProviderUnavailable(
                "Provider usage exceeded the evaluation model's reserved bound.",
                usage=Usage(incoming, outgoing, cost / 1_000_000))
