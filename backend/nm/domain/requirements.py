"""Source-backed checklist records and their one shared read projection."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.domain.text import refuses_blank_text


class Force(str, Enum):
    """Source-bound interpretation of necessity, not a document-type shortcut."""

    REQUIRED = "required"
    STRENGTHENING = "strengthening"

# `locator` MAY BE EMPTY: it is the passage's own, and `Passage.locator`
# defaults to empty for a passage the store gave no locator.
@refuses_blank_text("locator")
@dataclass(frozen=True)
class Requirement:
    """One thing this dispute needs, and the retrieved words that say so."""

    need: str
    why: str
    span: str
    source: str
    locator: str
    force: Force
    source_identity: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, n), str)
               for n in ("need", "why", "span", "source", "locator", "source_identity")):
            raise ValueError("requirement text must be attributable strings")
        if not self.need.strip() or not self.span.strip():
            raise ValueError("a requirement carries what is needed and the words requiring it")
        if not isinstance(self.force, Force):
            raise ValueError("a requirement's force is where its authority came from")

    @classmethod
    def restore(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return None
        try:
            return cls(**{**value, "force": Force(value.get("force"))})
        except (TypeError, ValueError):
            return None


class State(str, Enum):
    """What the board paints, in the product's own vocabulary.

    NOT COLOURS. Green, amber, red and grey are how the interface draws these;
    the domain says what is true, and a renderer that loses its colours must
    still be able to say it.
    """

    HELD = "held"                  # green: the file carries it, with its source
    PROMISED = "promised"          # amber: the advocate undertook to provide it
    UNAVAILABLE = "unavailable"    # red: the advocate says it cannot be obtained
    OUTSTANDING = "outstanding"    # grey: not yet asked, or asked and unanswered

    @classmethod
    def not_established(cls) -> "State":
        """The third state, declared rather than guessed from a name. An item
        nobody has answered is OUTSTANDING -- never HELD by default and never
        UNAVAILABLE, which is the advocate saying it cannot be had."""
        return cls.OUTSTANDING


@dataclass(frozen=True)
class Outcome:
    """What the advocate said about one requirement, and what it rests on.

    THERE IS NO PATH THAT SETS A TICK. `HELD` carries the fact on the file that
    satisfies it; `PROMISED` and `UNAVAILABLE` carry the advocate's own words.
    An outcome with no basis is refused here rather than rendered as a state
    nobody can account for -- which is the whole of F-B-17's "never a manual
    tick", enforced where it cannot be forgotten.
    """

    state: State
    basis: str
    at: str
    fact: str = ""
    due: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, n), str) for n in ("basis", "at", "fact", "due")):
            raise ValueError("an answer has typed provenance")
        if self.due:
            date.fromisoformat(self.due)
        if not isinstance(self.state, State):
            raise ValueError("an outcome's state comes from the vocabulary")
        if not self.basis.strip() or not self.at.strip():
            raise ValueError("an outcome names what it rests on and when it was given")
        if self.state is State.HELD and not self.fact.strip():
            raise ValueError(
                "held names the fact on the file that satisfies it: a tick with no "
                "fact behind it is the manual tick this product refuses")

    def stored(self) -> dict:
        return {"state": self.state.value, "basis": self.basis, "at": self.at,
                "fact": self.fact, "due": self.due}

    @classmethod
    def restore(cls, row) -> "Outcome | None":
        """An unreadable outcome is dropped, never rendered as held."""
        if not isinstance(row, dict):
            return None
        try:
            return cls(State(row.get("state")), row.get("basis", ""),
                       row.get("at", ""), row.get("fact", ""), row.get("due", ""))
        except (TypeError, ValueError):
            return None


def key(requirement: Requirement) -> str:
    """A requirement's identity: the passage it came from and the words in it.

    NOT THE `need` TEXT. The model words the need afresh on every reading, so
    keying on it would lose the advocate's answer the moment a re-reading said
    "the dishonour memo" where it had said "the bank's memo of dishonour". The
    span is copied verbatim from the passage and the locator names the passage,
    so together they are stable for as long as the passage is.
    """
    return hashlib.sha256(f"{requirement.locator}::{requirement.span}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Item:
    """One row of the checklist, as the board and the conversation both read it."""

    requirement: Requirement
    state: State
    outcome: Outcome | None = None

    @property
    def outstanding(self) -> bool:
        """Grey only. A red with a reason is finished work, not a gap (F-C-13)."""
        return self.state is State.OUTSTANDING

    def rendered(self) -> dict:
        r = self.requirement
        return {"key": key(r), "need": r.need, "why": r.why, "force": r.force.value,
                "source": r.source, "locator": r.locator, "span": r.span,
                "state": self.state.value,
                "basis": self.outcome.basis if self.outcome else "",
                "at": self.outcome.at if self.outcome else "",
                "fact": self.outcome.fact if self.outcome else "",
                "due": self.outcome.due if self.outcome else ""}


def restored(thread) -> tuple[Requirement, ...]:
    """Both in-memory types and saved JSON records use the same validation."""
    return tuple(r for value in getattr(thread, "requirements", ()) or ()
                 if (r := Requirement.restore(value)) is not None)


def checklist(thread, facts=()) -> tuple[Item, ...]:
    """The rows for one dispute, each with the state the record supports."""
    outcomes = getattr(thread, "requirement_outcomes", None) or {}
    rows = []
    scoped = {f.id: f for f in facts if f.id in thread.chronology
              and f.superseded_by is None}
    reads = getattr(thread, "requirement_reads", {}) or {}
    for requirement in restored(thread):
        recorded = Outcome.restore(outcomes.get(key(requirement)))
        fact = scoped.get(recorded.fact) if recorded else None
        if (recorded and (fact is None or recorded.basis not in fact.statement
                          or fact.provenance.kind != "advocate_statement")):
            recorded = None
        current_source = reads.get(requirement.locator)
        if (requirement.source_identity and current_source
                and current_source != requirement.source_identity):
            recorded = None
        rows.append(Item(requirement,
                         recorded.state if recorded else State.OUTSTANDING,
                         recorded))
    return tuple(rows)


def nothing_to_ask(thread, facts=()) -> bool:
    """No grey left: every requirement has had its answer from the advocate.

    THIS IS WHAT STOPS NM ASKING (F-C-13). A requirement the client cannot
    produce, recorded with its reason, is a finished question even though the
    thing itself will never arrive.
    """
    rows = checklist(thread, facts)
    return bool(rows) and not any(row.outstanding for row in rows)


def settled(thread, facts=()) -> bool:
    """Nothing left to ask AND nothing left to wait for.

    A PROMISE IS NOT AN ARRIVAL, and the first version of this function said it
    was: a dispute waiting on a document the advocate undertook to send on
    Friday reported complete on Tuesday. Asking is finished when nothing is
    grey; the dispute is finished when nothing is grey and nothing is promised.
    False when there is no checklist at all -- nothing retrieved is not the
    same as nothing needed.
    """
    rows = checklist(thread, facts)
    return bool(rows) and not any(
        row.outstanding or row.state is State.PROMISED for row in rows)


def summary(thread, facts=()) -> dict:
    rows = checklist(thread, facts)
    return {"state": "established" if rows else "not_established",
            "held": sum(r.state is State.HELD for r in rows),
            "outstanding": sum(r.outstanding for r in rows),
            "promised": sum(r.state is State.PROMISED for r in rows),
            "unavailable": sum(r.state is State.UNAVAILABLE for r in rows),
            "total": len(rows)}


def due_items(thread, facts, today: date, *, resumed=False) -> tuple[Item, ...]:
    """A due promise stays promised, never becomes held or unavailable by time."""
    result = []
    for item in checklist(thread, facts):
        if item.state is not State.PROMISED:
            continue
        due = item.outcome.due
        if not due:
            if resumed:
                result.append(item)
            continue
        try:
            when = date.fromisoformat(due)
        except ValueError:
            if resumed:
                result.append(item)
        else:
            if when <= today:
                result.append(item)
    return tuple(result)
