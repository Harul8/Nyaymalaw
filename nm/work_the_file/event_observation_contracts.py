"""A source-bound event reading is not an admitted or confirmed dated fact."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from nm.Archives.legal_brain.orchestrate.loop_contracts import digest


@dataclass(frozen=True)
class EventObservation:
    source_fact: str
    source_version: int
    account: str
    event_quote: str
    date_expression: str
    reference: date
    on: date | None = None

    def __post_init__(self):
        if (not isinstance(self.source_fact, str) or not self.source_fact.strip()
                or type(self.source_version) is not int or self.source_version < 1
                or not isinstance(self.account, str) or not self.account.strip()
                or not isinstance(self.event_quote, str) or not self.event_quote.strip()
                or self.event_quote not in self.account
                or not isinstance(self.date_expression, str)
                or self.date_expression and self.date_expression not in self.event_quote
                or type(self.reference) is not date
                or self.on is not None and type(self.on) is not date):
            raise ValueError("An event reading retains its exact complete attributed source.")
        if self.on is not None and not self.date_expression.strip():
            raise ValueError("A dated event reading has its stated source expression.")

    @property
    def identity(self):
        return digest({**asdict(self), "reference": self.reference.isoformat(),
                       "on": self.on.isoformat() if self.on else None})

    @property
    def observation_key(self):
        """Same source observation is not new because it was reread tomorrow."""
        return (self.source_fact, self.source_version, self.event_quote,
                self.date_expression, self.on)

    def as_dict(self):
        return {**asdict(self), "reference": self.reference.isoformat(),
                "on": self.on.isoformat() if self.on else None,
                "state": "resolved" if self.on else "undated",
                "association_assessment": "not_assessed", "confirmed": False,
                "factual_truth_established": False, "identity": self.identity}

    @classmethod
    def restore(cls, raw):
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            raise ValueError("An event reading is an exact record, not an empty date.")
        allowed = {"source_fact", "source_version", "account", "event_quote",
                   "date_expression", "reference", "on"}
        if not set(raw) <= allowed or not allowed <= set(raw):
            raise ValueError("An event reading has its complete closed source contract.")
        data = dict(raw)
        for key in ("reference", "on"):
            value = data[key]
            if value is not None and type(value) is not date:
                if not isinstance(value, str):
                    raise ValueError("An event reading date uses the calendar contract.")
                converted = date.fromisoformat(value)
                if converted.isoformat() != value:
                    raise ValueError("An event reading date uses canonical ISO characters.")
                value = converted
            data[key] = value
        return cls(**data)


def event_context(thread, facts):
    """Derived currency per observation, never one clock for the whole account."""
    current = {row.id: row for row in facts}
    entries, unreadable = [], 0
    for raw in thread.event_observations:
        try:
            row = EventObservation.restore(raw)
        except (TypeError, ValueError):
            unreadable += 1
            continue
        source = current.get(row.source_fact)
        held = (source is not None and source.id in thread.chronology
                and source.version == row.source_version and source.statement == row.account
                and source.superseded_by is None and not source.conflicts_with)
        entries.append({**row.as_dict(), "currency": "current" if held else "stale",
                        "may_start_a_legal_clock": False})
    return {"entries": entries, "unreadable_observations": unreadable,
            "complete_chronology_assessment": "not_assessed"}
