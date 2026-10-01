"""Source-backed checklist records and their one shared read projection."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum

from nm.shared.text_contracts import refuses_blank_text


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
    context_identity: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, n), str)
               for n in ("need", "why", "span", "source", "locator", "source_identity",
                         "context_identity")):
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
    source_identity: str = ""
    requires_review: bool = False
    context_identity: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(getattr(self, n), str)
               for n in ("basis", "at", "fact", "due", "source_identity", "context_identity")):
            raise ValueError("an answer has typed provenance")
        if type(self.requires_review) is not bool:
            raise ValueError("A proposed classification records its independent review requirement")
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
                "fact": self.fact, "due": self.due, "source_identity": self.source_identity,
                "requires_review": self.requires_review,
                "context_identity": self.context_identity}

    @classmethod
    def restore(cls, row) -> "Outcome | None":
        """An unreadable outcome is dropped, never rendered as held."""
        if not isinstance(row, dict):
            return None
        try:
            return cls(State(row.get("state")), row.get("basis", ""),
                       row.get("at", ""), row.get("fact", ""), row.get("due", ""),
                       row.get("source_identity", ""), row.get("requires_review", False),
                       row.get("context_identity", ""))
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


def classification_identity(requirement, outcome, fact) -> str:
    """Exact relevance subject; changes of status, denial or generation matter."""
    value = {"requirement": asdict(requirement), "outcome": outcome.stored(), "fact": asdict(fact)}
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     default=lambda item: item.isoformat()).encode("utf8")
    return hashlib.sha256(raw).hexdigest()


def applicability_subject(thread, facts=()) -> dict:
    """Only the current dispute material that can change a law's application.

    Exclude appended answer facts, question history and model-derived
    assessment sections: those change during ordinary conversation and must
    not invalidate the very legal need the advocate is answering. A genuine
    recorded correction has an explicit supersession link and is included,
    along with its replacement. A new fact without a correction link may
    inform later analysis, but does not itself claim to reverse the legal
    applicability previously read. Each thread has its own subject.
    """
    recorded = asdict(thread)
    scoped = {row.id: row for row in facts if row.id in thread.chronology}
    corrected = {row.id for row in scoped.values() if row.superseded_by is not None}
    corrected.update(row.superseded_by for row in scoped.values()
                     if row.superseded_by in scoped)
    return {
        "label": thread.label,
        "identifiers": recorded["identifiers"],
        "parties": recorded["parties"],
        "posture": recorded["posture"],
        "objective": recorded["objective"],
        "premises_stated": recorded["premises_stated"],
        "corrections": [asdict(scoped[ident]) for ident in thread.chronology
                        if ident in corrected and ident in scoped],
    }


def applicability_identity(thread, facts=()) -> str:
    """Version the legal-need reading against its actual dispute context."""
    raw = json.dumps(applicability_subject(thread, facts), sort_keys=True,
                     ensure_ascii=False, allow_nan=False,
                     default=lambda value: value.isoformat()).encode("utf8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ClassificationProof:
    """A trusted reader's independently verified exact subject, never a written tick.

    No model-facing schema accepts this type. The core reader constructs it only
    after checking the sealed independent-verifier record and exact current subject.
    """
    subject_identity: str
    record_reference: str

    def __post_init__(self):
        if (not isinstance(self.subject_identity, str) or len(self.subject_identity) != 64
                or any(char not in "0123456789abcdef" for char in self.subject_identity)
                or not isinstance(self.record_reference, str) or not self.record_reference.strip()):
            raise ValueError(
                "An independent classification proof needs an exact subject and receipt")


@dataclass(frozen=True)
class Item:
    """One row of the checklist, as the board and the conversation both read it."""

    requirement: Requirement
    state: State
    outcome: Outcome | None = None
    independently_reviewed: bool = False
    applicability_current: bool = True

    @property
    def outstanding(self) -> bool:
        """An answerable grey need, never an old clause pending legal review."""
        return self.applicability_current and self.state is State.OUTSTANDING

    def rendered(self) -> dict:
        r = self.requirement
        return {"key": key(r), "need": r.need, "why": r.why, "force": r.force.value,
                "source": r.source, "locator": r.locator, "span": r.span,
                "state": self.state.value,
                "applicability_state": ("current" if self.applicability_current
                                        else "review_required"),
                "proposed_state": self.outcome.state.value if self.outcome else "",
                "review_state": ("applicability_review_required"
                    if not self.applicability_current else
                    "independently_reviewed" if self.independently_reviewed
                    else "not_assessed" if self.outcome and self.outcome.requires_review
                    else "legacy_structural" if self.outcome else "not_assessed"),
                "basis": self.outcome.basis if self.outcome else "",
                "at": self.outcome.at if self.outcome else "",
                "fact": self.outcome.fact if self.outcome else "",
                "due": self.outcome.due if self.outcome else ""}


def restored(thread) -> tuple[Requirement, ...]:
    """Both in-memory types and saved JSON records use the same validation."""
    return tuple(r for value in getattr(thread, "requirements", ()) or ()
                 if (r := Requirement.restore(value)) is not None)


def checklist(thread, facts=(), *, classifications=()) -> tuple[Item, ...]:
    """The rows for one dispute, each with the state the record supports."""
    outcomes = getattr(thread, "requirement_outcomes", None) or {}
    rows = []
    scoped = {f.id: f for f in facts if f.id in thread.chronology
              and f.superseded_by is None}
    reads = getattr(thread, "requirement_reads", {}) or {}
    context = applicability_identity(thread, facts)
    if (not isinstance(classifications, tuple)
            or any(not isinstance(row, ClassificationProof) for row in classifications)):
        raise ValueError("Checklist classifications need typed independent receipt proofs")
    certified = {row.subject_identity for row in classifications}
    for requirement in restored(thread):
        # Old persisted source-backed rows have no applicability fingerprint.
        # They must not inherit a current legal verdict merely because their
        # passage identity is unchanged. Source-less legacy structural rows
        # cannot claim freshness, but retain their old projection vocabulary.
        source_bound = bool(requirement.source_identity or reads.get(requirement.locator))
        applicability_current = (requirement.context_identity == context
                                 if requirement.context_identity else not source_bound)
        recorded = Outcome.restore(outcomes.get(key(requirement)))
        fact = scoped.get(recorded.fact) if recorded else None
        if (recorded and (fact is None or recorded.basis not in fact.statement
                          or fact.provenance.kind != "advocate_statement")):
            recorded = None
        current_source = reads.get(requirement.locator)
        if (requirement.source_identity and current_source
                and current_source != requirement.source_identity):
            recorded = None
        if (recorded and current_source
                and recorded.source_identity != current_source):
            # Re-reading the same exact clause can change its applicability
            # context. Preserve the old answer, but do not lend it the new
            # source generation. Absence of a read is not a currency verdict.
            recorded = None
        if (recorded and requirement.context_identity
                and recorded.context_identity != requirement.context_identity):
            # A current need does not re-certify an old answer merely because
            # its passage was found again after the dispute changed.
            recorded = None
        reviewed = (applicability_current and recorded is not None and
                    (not recorded.requires_review
            or classification_identity(requirement, recorded, fact) in certified))
        rows.append(Item(requirement,
                         recorded.state if reviewed else State.OUTSTANDING, recorded,
                         bool(reviewed and recorded.requires_review),
                         applicability_current))
    return tuple(rows)


def projection_identity(thread, facts=()) -> str:
    """All current recorded subject data; never a persisted completion flag."""
    raw = json.dumps({"thread": asdict(thread), "facts": [asdict(row) for row in facts]},
        ensure_ascii=False, sort_keys=True, allow_nan=False,
        default=lambda value: value.isoformat()).encode("utf8")
    return hashlib.sha256(raw).hexdigest()


def facts_identity(facts=()) -> str:
    """Bind the whole factual population even before any dispute exists."""
    raw = json.dumps([asdict(row) for row in facts], ensure_ascii=False,
                     sort_keys=True, allow_nan=False,
                     default=lambda value: value.isoformat()).encode("utf8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ChecklistProjection:
    """One request-local derivation, not another stored or model-authored verdict."""
    rows: tuple[Item, ...]
    expected_population: int
    subject_identity: str

    def __post_init__(self):
        if (not isinstance(self.rows, tuple) or any(not isinstance(row, Item) for row in self.rows)
                or type(self.expected_population) is not int or self.expected_population < 0
                or not isinstance(self.subject_identity, str) or len(self.subject_identity) != 64
                or any(char not in "0123456789abcdef" for char in self.subject_identity)):
            raise ValueError(
                "A checklist projection needs typed rows and its exact recorded subject")

    def require_current(self, thread, facts=()):
        if self.subject_identity != projection_identity(thread, facts):
            raise ValueError(
                "The request-local checklist subject changed; rebuild its actual checks")

    @property
    def complete_population(self):
        return (bool(self.rows) and len(self.rows) == self.expected_population
                and len({key(row.requirement) for row in self.rows}) == len(self.rows)
                and all(row.applicability_current for row in self.rows))

    @property
    def nothing_to_ask(self):
        return self.complete_population and not any(row.outstanding for row in self.rows)

    @property
    def settled(self):
        return self.complete_population and not any(
            row.outstanding or row.state is State.PROMISED for row in self.rows)

    def summary(self):
        return {"state": "established" if self.rows else "not_established",
                "held": sum(row.state is State.HELD for row in self.rows),
                "outstanding": sum(row.outstanding for row in self.rows),
                "promised": sum(row.state is State.PROMISED for row in self.rows),
                "unavailable": sum(row.state is State.UNAVAILABLE for row in self.rows),
                "applicability_review_required": sum(not row.applicability_current
                                                      for row in self.rows),
                "total": len(self.rows)}

    def due_items(self, today: date, *, resumed=False):
        """A due promise stays promised; time supplies no factual conclusion."""
        if type(today) is not date or type(resumed) is not bool:
            raise ValueError("Information follow-up uses a trusted date and explicit resume state")
        result = []
        for item in self.rows:
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


def project(thread, facts=(), *, classifications=()) -> ChecklistProjection:
    return ChecklistProjection(checklist(thread, facts, classifications=classifications),
                               len(getattr(thread, "requirements", ()) or ()),
                               projection_identity(thread, facts))


def nothing_to_ask(thread, facts=(), *, classifications=()) -> bool:
    """No grey left: every requirement has had its answer from the advocate.

    THIS IS WHAT STOPS NM ASKING (F-C-13). A requirement the client cannot
    produce, recorded with its reason, is a finished question even though the
    thing itself will never arrive.
    """
    return project(thread, facts, classifications=classifications).nothing_to_ask


def settled(thread, facts=(), *, classifications=()) -> bool:
    """Nothing left to ask AND nothing left to wait for.

    A PROMISE IS NOT AN ARRIVAL, and the first version of this function said it
    was: a dispute waiting on a document the advocate undertook to send on
    Friday reported complete on Tuesday. Asking is finished when nothing is
    grey; the dispute is finished when nothing is grey and nothing is promised.
    False when there is no checklist at all -- nothing retrieved is not the
    same as nothing needed.
    """
    return project(thread, facts, classifications=classifications).settled


def summary(thread, facts=(), *, classifications=()) -> dict:
    return project(thread, facts, classifications=classifications).summary()


def due_items(thread, facts, today: date, *, resumed=False, classifications=()) -> tuple[Item, ...]:
    """A due promise stays promised, never becomes held or unavailable by time."""
    return project(thread, facts, classifications=classifications).due_items(today, resumed=resumed)
