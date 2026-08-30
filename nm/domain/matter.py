"""The matter domain. Pure -- no I/O, no model, no clock of its own.

Purity is not tidiness here. It is what buys the class-A test cadence: the most
load-bearing invariants in this product (posture derivation, disposition
accounting, the limitation coverage check) are pure logic, and they can only run
every commit in seconds if nothing in this module reaches for a database.

WHAT THE TYPES MAKE IMPOSSIBLE
------------------------------
  * a Fact without provenance            -- Provenance is non-optional
  * posture defaulting to "we are aggrieved" -- UNKNOWN is a value, not a null
  * `side` drifting from `role`          -- side is derived, never stored
  * a thread id derived from its label   -- the id is generated once
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum
from typing import Literal

from nm.domain.traceability import implements

# --------------------------------------------------------------------- ids ---
MatterId = str
ThreadId = str
FactId = str
TurnId = str


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ------------------------------------------------------------------- facts ---


class Certainty(str, Enum):
    DOCUMENTED = "documented"
    ASSERTED = "asserted"


@dataclass(frozen=True)
class Provenance:
    """Where a fact came from. Non-optional by construction.

    A fact whose source cannot be named cannot be walked back, and an advocate
    who cannot audit the chain has to take the answer on trust -- which is the
    one thing this product must never ask of them.
    """

    kind: Literal["advocate_statement", "document", "derived"]
    turn: TurnId
    document: str | None = None
    page: int | None = None
    span: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "document" and (self.document is None or self.page is None):
            raise ValueError(
                "a document-sourced fact needs its document and page. A fact "
                "without provenance is not usable (PRD C6)."
            )


class FactBasis(str, Enum):
    """How the client KNOWS the thing they just told you. PRD C1.

    Labelling this is not bookkeeping. "He never paid me" resting on direct
    knowledge and the same sentence resting on belief are different cases, and
    the difference decides what has to be proved and by whom.
    """

    DIRECT_KNOWLEDGE = "direct_knowledge"
    DOCUMENT = "document"
    HEARSAY = "hearsay"
    INFERENCE = "inference"
    BELIEF = "belief"
    NOT_ASSESSED = "not_assessed"


class Weight(str, Enum):
    """C1 requires unfavourable facts to be explored as hard as favourable ones.

    Without a field, nothing can check that they were -- and D6's adverse-fact
    accounting has nothing to compare its theory against.
    """

    FAVOURABLE = "favourable"
    UNFAVOURABLE = "unfavourable"
    NEUTRAL = "neutral"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class Fact:
    """PRD C1. THE FULL CONTRACT IS APPENDIX E, and this type is checked
    against it by tests/test_produces_contracts.py."""

    id: FactId
    statement: str
    provenance: Provenance
    certainty: Certainty = Certainty.ASSERTED
    date: date | None = None            # None means UNDATED, never estimated
    material: bool = True
    # `None` is NOT ASSESSED. Two states would make an unconfirmed fact
    # indistinguishable from a rejected one.
    confirmed: bool | None = None
    confirmed_at: str | None = None
    conflicts_with: tuple[FactId, ...] = ()
    superseded_by: FactId | None = None
    # The quotation, IF ONE WAS RECORDED. C1 forbids recording a paraphrase as
    # a quotation, and that rule is unenforceable unless the claimed exact
    # words are a separate field that can be checked back against the account.
    exact_words: str | None = None
    basis: FactBasis = FactBasis.NOT_ASSESSED
    basis_source: str | None = None
    weight: Weight = Weight.NOT_ASSESSED

    def __post_init__(self) -> None:
        needs_source = (FactBasis.DOCUMENT, FactBasis.HEARSAY, FactBasis.INFERENCE)
        if self.basis in needs_source and not (self.basis_source or "").strip():
            # C1: never record a source for a basis that points nowhere.
            raise ValueError(
                f"a fact whose basis is {self.basis.value!r} must name where "
                f"that basis points. A basis with no source cannot be walked "
                f"back, and an advocate who cannot audit the chain has to take "
                f"it on trust.")
        quoted = (self.exact_words or "").strip()
        if quoted and quoted not in self.statement:
            # C1: never record a paraphrase as a quotation. Claimed exact words
            # must be findable in the account they claim to come from.
            raise ValueError(
                "recorded `exact_words` are not present in the statement they "
                "claim to quote. A paraphrase recorded as a quotation is the "
                "one an advocate reads out in court.")

    @staticmethod
    def create(statement: str, provenance: Provenance, **kw) -> "Fact":
        return Fact(id=new_id("fact"), statement=statement, provenance=provenance, **kw)


# ----------------------------------------------------------------- posture ---


class Role(str, Enum):
    """Forum-correct names. UNKNOWN is a first-class value."""

    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    COMPLAINANT = "complainant"
    ACCUSED = "accused"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    OPPOSITE_PARTY = "opposite_party"
    APPELLANT = "appellant"
    APPLICANT = "applicant"
    DECREE_HOLDER = "decree_holder"
    JUDGMENT_DEBTOR = "judgment_debtor"
    UNKNOWN = "unknown"


class Side(str, Enum):
    MOVING = "moving"
    DEFENDING = "defending"
    UNKNOWN = "unknown"


# Whoever must FILE to get what they want is the mover. This mapping is the
# whole of the test, written once so no call site re-derives it differently.
_SIDE_OF: dict[Role, Side] = {
    Role.PLAINTIFF: Side.MOVING,
    Role.COMPLAINANT: Side.MOVING,
    Role.PETITIONER: Side.MOVING,
    Role.APPELLANT: Side.MOVING,
    Role.APPLICANT: Side.MOVING,
    Role.DECREE_HOLDER: Side.MOVING,
    Role.DEFENDANT: Side.DEFENDING,
    Role.ACCUSED: Side.DEFENDING,
    Role.RESPONDENT: Side.DEFENDING,
    Role.OPPOSITE_PARTY: Side.DEFENDING,
    Role.JUDGMENT_DEBTOR: Side.DEFENDING,
    Role.UNKNOWN: Side.UNKNOWN,
}


class Basis(str, Enum):
    STATED = "stated"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PostureConflict:
    on_record: Role
    now_suggested: Role
    applied: bool = False


@dataclass(frozen=True)
class Posture:
    """`side` is DERIVED from `role`. It is never stored independently.

    Storing it would let the two drift, and a thread whose stored side no longer
    matches its role gives advice to the wrong party while every citation in it
    remains correct -- the measured original defect.
    """

    role: Role = Role.UNKNOWN
    basis: Basis = Basis.UNKNOWN
    opponent: str | None = None
    client_described_as: str | None = None
    """The advocate's own word for their client -- "the workman", "the wife".

    NOT a role. A descriptor identifies who the client IS; it says nothing
    about whether they filed or are answering, and the old mapping from
    descriptor to role (`wife` -> PETITIONER, `tenant` -> RESPONDENT) was an
    inference about who moved, dressed as a reading of what was said.

    Carried so the blocking question can NARROW rather than repeat itself at
    an advocate who has already answered it once."""
    source_fact: FactId | None = None
    version: int = 0
    conflicts: tuple[PostureConflict, ...] = ()

    @property
    def side(self) -> Side:
        return _SIDE_OF[self.role]

    @property
    def resolved(self) -> bool:
        return self.role is not Role.UNKNOWN and self.basis is not Basis.UNKNOWN

    def enrich(self, role: Role, basis: Basis, source_fact: FactId | None = None) -> "Posture":
        """Monotonic enrichment. A STATED posture is never silently flipped.

        Gaps fill freely and `inferred` upgrades to `stated` freely. A
        contradiction surfaces as a conflict for the advocate to settle,
        because a turn-5 reversal is worse than a turn-1 error: by then the
        advocate has acted on it.
        """
        if self.role is Role.UNKNOWN or self.basis is Basis.UNKNOWN:
            return replace(self, role=role, basis=basis, source_fact=source_fact,
                           version=self.version + 1)
        if role is self.role:
            better = self.basis is Basis.INFERRED and basis is Basis.STATED
            return replace(self, basis=basis, version=self.version + 1) if better else self
        return replace(
            self,
            conflicts=self.conflicts + (PostureConflict(on_record=self.role, now_suggested=role),),
            version=self.version + 1,
        )


# ---------------------------------------------------------------- threads ---


@dataclass(frozen=True)
class Thread:
    """A dispute inside a matter.

    The id is generated once and NEVER derived from the label. A sale deed says
    "the Kukatpally property", the advocate's note says "the land matter", the
    plaint says "O.S. 442/2023" -- nothing in a label tells you these are one
    thread, or that two similar labels are two matters.
    """

    id: ThreadId
    label: str
    aliases: tuple[str, ...] = ()
    identifiers: dict[str, str] = field(default_factory=dict)
    posture: Posture = field(default_factory=Posture)
    chronology: tuple[FactId, ...] = ()
    deferred_reason: str | None = None

    @staticmethod
    def create(label: str, **kw) -> "Thread":
        return Thread(id=new_id("thr"), label=label, **kw)

    @staticmethod
    @implements("C4")
    def _implements_c4() -> str:
        """Thread identity (feature C4) is a property of THIS TYPE.

        The id is generated once and never derived from the label, aliases are
        never keys, and merging requires a decisive identifier. Those rules are
        enforced by the constructor and by `decisive_identifier_matches`, so
        the feature is declared here rather than on a function that happens to
        call it.
        """
        return "C4"

    def renamed(self, label: str) -> "Thread":
        """A rename loses nothing: the label is a display name and an alias."""
        aliases = self.aliases if self.label in self.aliases else self.aliases + (self.label,)
        return replace(self, label=label, aliases=aliases)

    def decisive_identifier_matches(self, other: "Thread") -> bool:
        """Ranked identity: a decisive identifier settles it; label similarity
        NEVER does. The failure is asymmetric -- a wrong split duplicates work
        and is visible; a wrong merge attaches the wrong posture and limitation
        to facts they do not govern, and inverts the advice invisibly."""
        return any(
            k in other.identifiers and other.identifiers[k] == v
            for k, v in self.identifiers.items()
        )


# ----------------------------------------------------- what we have asked ---


@dataclass(frozen=True)
class AskedQuestion:
    """A question this product PUT to the advocate, and whether it came back.

    THE ONLY NEW STATE THE MATTER MEMORY NEEDS, and it has to be state rather
    than a derivation. Facts record what came back; nothing records what was
    asked -- and "we never asked" and "we asked and were ignored" are different
    situations calling for different next moves.

    `answered_by` is the TURN that resolved it, not a boolean, so the file can
    show when an outstanding question was finally met.
    """

    gate: str
    text: str
    asked_on: TurnId
    thread: ThreadId | None = None
    answered_by: TurnId | None = None
    times_asked: int = 1

    @property
    def open(self) -> bool:
        return self.answered_by is None

    @property
    def ignored(self) -> bool:
        """Asked more than once and still unanswered.

        Not a failure of the advocate. It usually means the question was the
        wrong one, or that they do not have the answer yet -- and asking it a
        third time in the same words is the product failing to listen.
        """
        return self.open and self.times_asked > 1


# ----------------------------------------------------------------- matter ---


@dataclass(frozen=True)
class Matter:
    id: MatterId
    advocate_id: str
    title: str
    threads: tuple[Thread, ...] = ()
    facts: tuple[Fact, ...] = ()
    turns_applied: tuple[TurnId, ...] = ()
    asked: tuple[AskedQuestion, ...] = ()
    """Every question put to the advocate, and whether it came back.

    Persisted, because the alternative is asking again. An advocate who is
    asked something they answered two turns ago has been told their
    instructions were not recorded, and they stop volunteering detail."""
    version: int = 0

    @staticmethod
    def create(advocate_id: str, title: str) -> "Matter":
        if not (advocate_id or "").strip():
            # AN ANONYMOUS SESSION MAY NOT OPEN A FILE (A1).
            #
            # Tenet 4 requires the file to know who may instruct and tenet
            # 20 requires a decision to record who decided; an anonymous
            # session satisfies neither. Refusing later, at the point of
            # advice, would already have put client material on a record
            # nothing can attribute.
            #
            # The wire had `min_length=1`, which counts CHARACTERS: "   "
            # is three of them and no identity, and it opened a matter.
            raise ValueError(
                "a matter cannot be opened without a named advocate. An "
                "identifier made of whitespace is not an identifier, and a "
                "file nothing can attribute cannot record who instructed "
                "it or who decided.")
        return Matter(id=new_id("mat"), advocate_id=advocate_id.strip(),
                      title=title)

    def thread(self, thread_id: ThreadId) -> Thread | None:
        return next((t for t in self.threads if t.id == thread_id), None)

    def fact(self, fact_id: FactId) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def with_thread(self, thread: Thread) -> "Matter":
        others = tuple(t for t in self.threads if t.id != thread.id)
        return replace(self, threads=others + (thread,), version=self.version + 1)

    def with_fact(self, fact: Fact) -> "Matter":
        return replace(self, facts=self.facts + (fact,), version=self.version + 1)

    def has_applied(self, turn_id: TurnId) -> bool:
        return turn_id in self.turns_applied

    def applied(self, turn_id: TurnId) -> "Matter":
        return replace(self, turns_applied=self.turns_applied + (turn_id,),
                       version=self.version + 1)

    # ------------------------------------------------------ the ask ledger ---
    def open_question(self, gate: str,
                      thread: ThreadId | None = None) -> AskedQuestion | None:
        return next((q for q in self.asked
                     if q.gate == gate and q.open and q.thread == thread), None)

    def asking(self, gate: str, text: str, turn: TurnId,
               thread: ThreadId | None = None) -> "Matter":
        """Note that a question was PUT.

        The same gate asked again BUMPS the count rather than adding a row. The
        file should show that a thing was asked three times -- which is a fact
        about the conversation worth acting on -- not carry three near-identical
        rows nobody reads.
        """
        standing = self.open_question(gate, thread)
        if standing is not None:
            i = self.asked.index(standing)
            bumped = replace(standing, times_asked=standing.times_asked + 1,
                             asked_on=turn, text=text)
            return replace(self, asked=self.asked[:i] + (bumped,) + self.asked[i + 1:])
        return replace(self, asked=self.asked + (
            AskedQuestion(gate=gate, text=text, asked_on=turn, thread=thread),))

    def answered(self, gates: frozenset[str], turn: TurnId) -> "Matter":
        """Close every open question whose gate did NOT fire this turn.

        THE GENERAL RULE, and it is deliberately not a list of special cases: a
        gate stops firing exactly when the condition it names has cleared, and
        the condition clearing is what "the advocate answered" means. Closing
        them one by one at each call site is how a question survives its own
        answer and gets asked again.
        """
        if not self.asked:
            return self
        out = tuple(q if (not q.open or q.gate in gates)
                    else replace(q, answered_by=turn)
                    for q in self.asked)
        return self if out == self.asked else replace(self, asked=out)
