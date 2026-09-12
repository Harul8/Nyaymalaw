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
from enum import Enum, nonmember
from typing import Literal

from nm.domain.intake import ReadQuality
from nm.domain.spoken import Spoken
from nm.domain.text import fold, refuses_blank_text
from nm.domain.traceability import implements
from nm.domain.turn_receipt import TurnReceipt

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


@refuses_blank_text()
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


class CauseOfAction(str, Enum):
    """THE CLOSED VOCABULARY. Everything else is `NOT_ESTABLISHED`.

    Closed on purpose. An open set of causes would have to be matched
    approximately, and approximate matching is what decides the wrong Article —
    the failure this whole module exists to remove.
    """

    GOODS_SOLD_PRICE = "goods_sold_price"
    MONEY_LENT = "money_lent"
    BREACH_OF_CONTRACT = "breach_of_contract"
    SPECIFIC_PERFORMANCE = "specific_performance"
    POSSESSION_ON_TITLE = "possession_on_title"
    POSSESSION_ON_PREVIOUS_POSSESSION = "possession_on_previous_possession"
    DECLARATION = "declaration"
    CHEQUE_DISHONOUR = "cheque_dishonour"

    NOT_ESTABLISHED = "not_established"
    """Nobody worked out what the cause is. NOT "no cause arises".

    It is a value rather than an absence because the two send the product in
    opposite directions: an unresolved cause falls through to search, and a
    cause genuinely outside the graph is a coverage gap to report.
    """


#: WHAT EACH CAUSE IS, in the terms that distinguish it from its
#: neighbours. Read by the cause reader's schema.
#:
#: THE VOCABULARY WITHOUT DEFINITIONS WAS THE DEFECT. The schema offered
#: eight bare identifiers, and a brief about unpaid invoices that used the
#: word `debt` was read as `money_lent` -- so the proof section worked the
#: elements of a loan on a suit for the price of goods. Every other closed
#: vocabulary in this product describes its values; the one that decides
#: which Article is looked up did not.
#:
#: HERE AND NOT IN `nm/core/cause.py`, because `nm/knowledge/resolution.py`
#: states the same legal ground in `Edge.curated_from` and `core` may not
#: import `knowledge`. A copy beside the reader would be two homes for one
#: fact; `domain` imports nothing and both layers may read it.
CAUSE_MEANS: dict[CauseOfAction, str] = {
    CauseOfAction.GOODS_SOLD_PRICE:
        "the PRICE of goods sold and delivered, unpaid. A seller suing a "
        "buyer on invoices. This is a debt, and it is NOT money lent -- "
        "nothing was advanced, goods were supplied and the price is owed.",
    CauseOfAction.MONEY_LENT:
        "money ADVANCED as a loan and not repaid. Something was handed "
        "over to be given back. If the sum is the price of goods or "
        "services already supplied, it is not this.",
    CauseOfAction.BREACH_OF_CONTRACT:
        "compensation for a contract broken, where the claim is damages "
        "rather than a fixed price or the performance itself.",
    CauseOfAction.SPECIFIC_PERFORMANCE:
        "the contract PERFORMED -- typically a sale deed executed -- "
        "rather than damages for its breach.",
    CauseOfAction.POSSESSION_ON_TITLE:
        "possession of immovable property claimed ON TITLE: we own it and "
        "somebody else holds it.",
    CauseOfAction.POSSESSION_ON_PREVIOUS_POSSESSION:
        "possession claimed on PREVIOUS POSSESSION and not on title -- we "
        "were in possession and were put out, whoever owns it.",
    CauseOfAction.DECLARATION:
        "a declaration of a right or status, where no consequential "
        "relief is the substance of the claim.",
    CauseOfAction.CHEQUE_DISHONOUR:
        "a cheque returned unpaid, and the statutory route that follows "
        "it. Not the underlying debt -- the dishonour itself.",
}

class Weight(str, Enum):
    """C1 requires unfavourable facts to be explored as hard as favourable ones.

    Without a field, nothing can check that they were -- and D6's adverse-fact
    accounting has nothing to compare its theory against.
    """

    FAVOURABLE = "favourable"
    UNFAVOURABLE = "unfavourable"
    NEUTRAL = "neutral"
    NOT_ASSESSED = "not_assessed"


@refuses_blank_text()
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
    read_quality: ReadQuality = ReadQuality.UNREAD
    """Extraction quality, independent of legal certainty and confirmation."""
    version: int = 1
    """Version of this proposition; old records load as their first version."""

    def __post_init__(self) -> None:
        if not isinstance(self.read_quality, ReadQuality):
            raise ValueError("a fact's extraction quality must be a ReadQuality")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("a proposition version must be a positive integer")
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


class Side(Spoken, str, Enum):
    MOVING = "moving"
    DEFENDING = "defending"
    UNKNOWN = "unknown"

    SAID = nonmember({
        "moving": "the party who has to move",
        "defending": "the party defending",
        "unknown": "a side that is not yet settled",
    })




Side.complete()
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


@refuses_blank_text()
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
    #: BK-34. WHO IS IN THIS THREAD, name -> `client` | `adverse` | `related`.
    #:
    #: THE CONFLICT SCREEN'S INPUT, and the reason it is a field rather than a
    #: derivation: the screen has to check THIS matter against every OTHER
    #: matter, and the others are files on disk that nobody is going to re-read
    #: a brief for. What is not persisted cannot be screened against.
    #:
    #: EMPTY IS `NOBODY IS NAMED YET`, which is the ordinary state of a first
    #: turn and produces a NOT_ASSESSED screen naming what it wants. It must
    #: never produce a screen that cleared against the empty set.
    #:
    #: `Posture.opponent` is NOT this. That field is filled by the posture
    #: read, whose question is which SIDE we act for, and asked for a name as a
    #: by-product it produced `invoices` -- rendered to an advocate as
    #: *AGAINST: invoices*. A conflict check built on that has examined
    #: nothing and says it is clear.
    parties: dict[str, str] = field(default_factory=dict)
    posture: Posture = field(default_factory=Posture)
    chronology: tuple[FactId, ...] = ()
    deferred_reason: str | None = None
    # `tuple[object, ...]` AND NOT A BARE `tuple`. The store's decoder
    # dispatches on `get_origin`, which is None for a bare tuple, so the
    # field came back a LIST and the round-trip guard failed it within the
    # minute -- "a field written faithfully and dropped on read fails
    # nothing until an advocate notices the product forgot what they told
    # it". The element type stays `object` for the cycle reason below.
    assessed: tuple[str, ...] = ()
    """WHICH SECTIONS HAVE BEEN COMPUTED ON THIS THREAD, by name.

    Every section below persists as an empty tuple until something writes
    it, so empty carries two opposite meanings: the section was built and
    found nothing, or nothing ever built it. On a turn that is a small
    ambiguity. IN A HANDOVER IT IS THE DANGEROUS ONE -- a receiving
    advocate reading an empty proof section cannot tell that the work is
    silently missing, which is the counterexample `handover_blockers`
    already exists for, arriving one level down.

    ONE FIELD RATHER THAN FOUR FLAGS. `issues_assessed`,
    `theory_assessed` and the rest would be four copies of one rule, and
    the fifth section would arrive without its copy. The population comes
    from the KEYS of the derive phase's `concluded` dict -- the thing that
    already knows exactly what this turn worked out -- so a section added
    there is recorded here with nothing to remember.

    A TUPLE, NOT A FROZENSET: the store encodes with `asdict` and decodes
    from the class's own field list, and both already carry
    `tuple[str, ...]`. Order is not meaningful; duplicates are removed on
    write.
    """

    authorities: tuple[object, ...] = ()
    """THE PROVISIONS AND CASES THIS THREAD'S ANSWER RESTED ON.

    Appendix E wants binding status, validity window, paragraph kind and
    treatment -- all of which a `Finding` carries and all of which were
    discarded at the end of every turn.

    Replaced whole on each deriving turn, like `deadlines`: what the
    LAST answer relied on is the useful fact, and accumulating every
    finding ever retrieved would hand a receiving advocate a pile rather
    than a position.
    """

    deadlines: tuple[object, ...] = ()
    """THE DEADLINE REGISTER, as the last turn that could compute it left
    it. Phase 3.

    `nm/core/deadlines.py` runs on every turn and nothing kept the result,
    so a receiving advocate got no deadlines section on a file whose
    limitation had been computed for four turns.

    RECOMPUTED AND OVERWRITTEN, never merged. This is a derivation and not
    a reading: a persisted derivation that can disagree with the
    computation behind it is the three-stores defect, and the only reason
    it does not arise here is that every deriving turn replaces it whole.
    Assessment provenance is the existing `"deadlines" in Thread.assessed`
    marker, written only when the register phase produces a result. The empty
    default alone means not assessed. Legacy dated rows remain visible without
    manufacturing this marker. A turn unable to compute a register preserves
    any previously recorded register and assessment; it does not reassess it.

    Untyped for the cycle reason `issues` and `proof` carry --
    `nm.core.deadlines` imports this module.
    """

    gaps: tuple[object, ...] = ()
    """THE GAP QUEUE as it stood at the end of the last deriving turn.
    Phase 3, and the same shape as `deadlines`.

    An EMPTY queue is a real answer -- nothing is missing -- and is
    written as one. That is the whole reason it goes through `concluded`
    rather than being inferred from emptiness at read time: empty and
    never-computed are opposite facts, and `Thread.assessed` is what tells
    them apart.
    """

    issues: tuple[object, ...] = ()
    """THE ISSUES ON THIS THREAD. Persisted, and MERGED rather than replaced.

    Phase 1, the same shape as `theory`. Measured on GS-15: the issue count
    went 1, 1, 1, 0, 2 across five turns and the thread had NO issues on turn
    4 having had one for three turns. `DispositionState` already says there is
    no member meaning "gone" and `Disposition` refuses a stop with no reason --
    the type forbade the delete path and the pipeline deleted every issue on
    every turn by rebuilding the list.

    UNTYPED for the same reason as `theory`: `nm.domain.issue` imports this
    module, so naming `Issue` here is a cycle. `nm.domain.issue.from_stored`
    reads it back.
    """
    decisions: tuple[object, ...] = ()
    """WHAT HAS BEEN SETTLED ON THIS THREAD, and by whom.

    The product routes a cause to an Act, settles a posture and takes a
    theory on every turn, discloses each as a sentence, and keeps none of
    them. GS-15 made the same routing decision five times from scratch
    with nothing checking the answer was the same.

    An advocate does not re-decide a settled question every time they are
    asked something. Recorded, a decision can be held stable, shown to
    have moved, and OVERRULED BY THE ADVOCATE -- which is what naming the
    alternatives is for.

    Untyped for the cycle reason above; `nm.domain.decision.from_stored`
    reads it back.
    """
    thresholds_told: tuple[object, ...] = ()
    """WHICH THRESHOLD GAPS THE ADVOCATE HAS ALREADY BEEN GIVEN IN FULL.

    Measured on GS-14: the same forty-word line, naming the same nine
    thresholds, on all four turns. An advocate who reads that four times
    learns to skip it -- and what they then skip is the list of what
    nobody has checked.

    THIS IS HISTORY AND NOT A DERIVATION, which is why it is stored. The
    blocked set is derivable from the thread on any turn; what the
    advocate was last TOLD is not, and re-deriving it would mean telling
    them again every turn, which is the defect.

    IT MAY NOT MAKE THE GAP SILENT. The full list is replaced by a short
    clause, never by nothing: the third state has to be visible in the
    output and not only in the type.
    """
    evidence: tuple[object, ...] = ()
    """WHAT THE FILE HAS AND WHO HOLDS IT. C7.

    MEASURED, driven, 6 September 2026:

        turn 1  2 items  ['the original agreement', 'the invoices']
        turn 2  2 items
        turn 3  1 item   the read did not mention the agreement
        turn 4  0 items
        turn 5  2 items  it mentioned them again

    Nothing happened to the evidence. An item the read did not mention was
    simply gone, and came back when a later read happened to describe it.

    AND `Preservation` IS NOT A DERIVATION AT ALL. It records that a step was
    TAKEN, with an owner and a date -- history, not something re-derivable
    from an account that will never mention it again. Losing it means
    G-PRESERVE blocks a step and asks a question the advocate has already
    answered, which is the one thing the question machinery is built not to
    do.

    Untyped for the cycle reason `issues`, `decisions` and `proof` carry;
    `nm.core.evidence_item.from_stored` reads it back.
    """
    proof: tuple[object, ...] = ()
    """WHAT THIS THREAD CAN ESTABLISH, element by element. D5.

    Persisted for the reason the theory and the issues are, and MEASURED the
    same way -- driven, because a live read cannot be made to forget on
    demand:

        turn 1  held          ('we hold the original',)
        turn 2  held          ('we hold the original',)
        turn 3  NOT_ASSESSED  ()          <- the read did not mention it
        turn 4  held          ('we hold the original',)

    The material never moved. An advocate told on turn 2 that an element is
    established, and on turn 3 that nobody worked it out, is watching the
    product lose its place.

    A POSITION IS NOT A FUNCTION OF THE FILE ALONE, which is why storing it is
    right where storing an `effect` would be wrong. `effect` is derived from
    the posture, so re-deriving keeps it true. A position is what a READ
    concluded from the file, and re-deriving it every turn does not refresh it
    -- it discards it whenever the read has an off turn.

    The staleness that argument has to answer is real and is handled where it
    belongs: `still_supported` checks a HELD position's material against the
    FILE, so a position resting on a corrected fact falls whatever the read
    says. See `nm.domain.proof.merge` for the asymmetry.

    `tuple[object, ...]` and not `tuple[ProofPosition, ...]`: the store's
    decoder needs `get_origin` to see a parameterised tuple, and a bare
    `tuple` gave back a list. The type is untyped for the same cycle reason as
    `issues` and `decisions`; `nm.domain.proof.from_stored` reads it back.
    """
    theory: "object | None" = None
    """THE CASE THEORY THIS THREAD IS RUNNING ON. Persisted, and REVISED.

    Phase 1 of the analysis carrying across turns. Measured on GS-15, 6
    September 2026: five turns produced FIVE DIFFERENT THEORIES while the
    advocate supplied a date, corrected it, and mentioned non-registration.
    The issue count went 1, 1, 1, 0, 2 — the thread had no issues at all on
    turn 4 having had one for three turns. Nothing the advocate said asked for
    any of that; the theory was simply rebuilt from the account every turn.

    An advocate who reconsidered their whole theory each time you gave them a
    date would not be trusted with the matter. NM remembered what the advocate
    SAID and forgot what it had CONCLUDED, and this is the first of the twelve
    handover sections that fixes.

    TYPED `object` AND NOT `Theory`, DELIBERATELY. `nm.core.theory` imports
    from here, so naming the type would be a cycle — and the layer rule is
    that domain holds the state while core holds the reading of it. The store
    round-trips it structurally either way.
    """

    @staticmethod
    def create(label: str, **kw) -> "Thread":
        return Thread(id=new_id("thr"), label=label, **kw)

    @staticmethod
    @implements("C4")
    def _implements_c4() -> str:
        """Thread identity (feature C4) is a property of THIS TYPE.

        The id is generated once and never derived from the label, and
        aliases are never keys. Those two are properties of THIS TYPE and
        the constructor enforces them.

        THE MERGE RULE IS NOT HERE, and this docstring used to say it was:
        it named a `decisive_identifier_matches` method as the enforcement,
        and that method had no callers at all. `nm/core/threading.bind()`
        does the matching, and it has to -- it distinguishes one match from
        many, and PROPOSES a merge rather than performing one, neither of
        which a boolean on a single thread can express.

        A second copy of "do these share a decisive identifier" is the
        arrangement that produced the O.S. 442/2023 defect, where one copy
        was hardened and the other was not. So the unused method was
        deleted rather than given a caller.
        """
        return "C4"

    def renamed(self, label: str) -> "Thread":
        """A rename loses nothing: the label is a display name and an alias."""
        aliases = self.aliases if self.label in self.aliases else self.aliases + (self.label,)
        return replace(self, label=label, aliases=aliases)



# ----------------------------------------------------- what we have asked ---


@refuses_blank_text()
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


@refuses_blank_text()
@dataclass(frozen=True)
class Matter:
    id: MatterId
    advocate_id: str
    title: str
    threads: tuple[Thread, ...] = ()
    facts: tuple[Fact, ...] = ()
    engagement: "object | None" = None
    """WHO THE CLIENT IS AND WHAT THIS FILE COVERS. Tenet 4.

    `None` until the product has read a client description or opened a
    dispute -- a real state, and the one a handover most needs told apart
    from an engagement that was recorded and is thin.

    Untyped for the cycle reason: `nm.domain.engagement` is pure, but the
    field follows the convention its neighbours set so a reader is not
    invited to wonder which persisted fields are typed and why.
    """

    commission: "object | None" = None
    """WHAT THIS ADVOCATE WAS INSTRUCTED TO DO, versioned. BK-62-AC1.

    `None` until somebody records one, which is a real state and NOT the same
    as a commission whose fields are blank: the first says nobody has been
    instructed, the second says an instruction was taken and says nothing.
    `nm/domain/commission.py` owns the type; this follows `engagement`'s
    convention of holding it untyped so a reader is not invited to wonder
    which persisted fields are typed and why.

    SUPERSEDED VERSIONS ARE NOT HERE. This is the current one; the history
    lives in `commission_history` because an advice given under version 1 was
    correct work under version 1, and losing version 1 makes it look wrong.
    """

    commission_history: tuple[object, ...] = ()
    """Every superseded commission, oldest first. Evidence, not clutter."""

    emergencies: tuple[object, ...] = ()
    """EVERY EMERGENCY DECLARED ON THIS FILE, oldest first. BK-78-AC2.

    A tuple and not a single field because an emergency re-declared after
    expiry is a SECOND moment of danger and a second fact. Keeping only the
    latest would make a file that was urgent twice look like a file that was
    urgent once, and the first declaration is the evidence for how the file
    was handled at the time.

    Expiry never removes one. What lapses is the permission, not the history.
    """

    urgency_records: tuple[object, ...] = ()
    """Manual per-danger UrgencyRegister rows; permission expiry never resolves them."""
    urgency_operations: tuple[object, ...] = ()
    """Immutable keyed acceptance of urgency recording and explicit resolution."""

    authority_refusals: tuple[object, ...] = ()
    """UNAUTHORISED ATTEMPTS, KEPT. BK-63-AC1 requires that a refused
    operation is refused AND RECORDED, and a refusal that exists only as an
    HTTP status is one nobody can review. Each holds who attempted what and
    why it was refused; none holds any client material."""

    authority_bindings: tuple[object, ...] = ()
    """Trusted, expiring matter-authority grants; never authored by commission HTTP."""
    decisions: tuple[object, ...] = ()
    """Attributable internal decision receipts. No record performs an external act."""
    commission_invalidations: tuple[object, ...] = ()
    """Prior scope assessments reopened by changed instructions, with their reason."""
    emergency_triage: tuple[object, ...] = ()
    """Bounded protective handoffs, not legal conclusions or established facts."""
    uploads: dict[str, dict] = field(default_factory=dict)
    """Original receipt records; the same sealed matter CAS owns their publication.

    Chunk objects are immutable, sealed and never legal facts. Quarantine,
    receipt integrity and reading remain separate states.
    """
    intake_request_key: str = ""
    """Idempotency identity for an upload-first empty matter shell."""
    intake_opening_offer: dict[str, object] = field(default_factory=dict)
    """Immutable normalized opening instructions, never derived from later edits."""

    reservations: tuple[object, ...] = ()
    """E5. POSITIONS THIS PRODUCT TOOK THAT THE ADVOCATE WENT AGAINST.

    Matter-scoped rather than thread-scoped because the reservation is
    about a disagreement with the ADVOCATE, and an advocate who overruled
    a reading on one dispute has not thereby overruled it on another --
    but they have made a decision about how this file is run, and a
    receiving advocate needs to see all of them in one place.

    Never restated to the advocate unless a FACT reactivates it. See
    `nm.domain.reservation`: the counterexample E5 names is the same
    objection raised on every turn after they went the other way.
    """

    screens: tuple[object, ...] = ()
    """THE ADMIT-A SCREENS, one entry per `ScreenKind`, matter-scoped.

    Appendix E: *each carries its own state, INCLUDING `not_run`. A2
    forbids showing a not_assessed screen as clear, and that is only
    possible if the summary distinguishes them.*

    MATTER-SCOPED AND NOT THREAD-SCOPED, because `_run_screens` decides
    for the FILE. A conflict is a conflict whichever dispute raised it.

    Carrying these is not slice-10 work. RUNNING the conflict, competence
    and scope checks is B3-B5; carrying five states that say `not_run` is
    what makes their absence visible at all, and until it is carried a
    receiving advocate cannot tell an unscreened file from a clean one.

    Untyped for the cycle reason every other persisted derivation carries:
    `nm.core.screens` imports this module.
    """

    assessed: tuple[str, ...] = ()
    """WHICH MATTER-LEVEL SECTIONS HAVE BEEN COMPUTED, by name.

    `Thread.assessed` one level up, and deliberately the same field with
    the same rule rather than a second mechanism: empty means either
    computed-and-found-nothing or never-computed, and in a handover those
    are opposite facts.
    """

    intake_parties: dict[str, str] = field(default_factory=dict)
    """BK-34. WHO THIS MATTER IS, recorded at intake: name -> side.

    MATTER-LEVEL AND NOT THREAD-LEVEL, and the sequencing is the reason. The
    conflict screen runs in ADMIT-A, before this turn's words have been read
    by anything -- which is the whole point of where the screens sit. Threads
    are bound in ADMIT-B, after. A party set that only existed on a thread
    would arrive one phase too late to screen the brief that named it.

    IT IS WHY INTAKE COMES BEFORE THE BRIEF. Parties cannot be read out of a
    brief that has not been admitted, and admitting the brief to read them is
    exactly what B3 forbids. So the advocate is asked who is involved when
    they open the file, and the screen has something to check before anything
    substantive is persisted.
    """

    intake_answers: dict[str, dict] = field(default_factory=dict)
    """BK-34. What the advocate ANSWERED at intake: screen kind -> {by, answer, at}.

    NOT A RELEASE, AND THE DISTINCTION IS THE DOMAIN'S OWN. `Screen.__post_init__`
    refuses a CLEAR screen carrying a `Release`, because "a release lifts a
    finding; a screen with nothing to lift did not need one" -- and modelling
    a recorded engagement scope as a release ran straight into that guard,
    correctly.

    A screen whose question the advocate has ANSWERED has RUN AND FOUND
    NOTHING. The scope screen asks what work they are instructed to do; told
    that, it clears on its own merits, and the answer is the detail. A
    `Release` remains what it always was -- the lifting of a real finding,
    such as a conflict the advocate accepts -- and nothing here creates one.

    PERSISTED PER MATTER, not per turn and not per session. The advocate
    records the scope once on a file, not every time they open it: an answer
    that evaporated would train them to click past it, which is how a screen
    becomes decoration.

    EMPTY IS `NOBODY HAS ANSWERED`, and it produces a BLOCKED screen carrying
    the question. It must never produce a cleared one.
    """

    emergency_because: str = ""
    """Why this matter was admitted with screens outstanding, if it was.

    THE EXCEPTION IS NARROW AND IT IS ON THE FILE. Liberty does not wait for a
    registry and a product that made it would be wrong in the way that matters
    most -- but an exception nobody can see afterwards is indistinguishable
    from a screen that passed, which is the whole of defect shape S1.
    """

    turns_applied: tuple[TurnId, ...] = ()
    turn_receipts: tuple[TurnReceipt, ...] = ()
    """Approved outputs and exact original-offer identities, atomic with the file.

    An archival transcript is not this receipt: it may hold a withheld draft
    or outlive a failed commit. Legacy absence proves neither release nor an
    exact replay identity.
    """
    asked: tuple[AskedQuestion, ...] = ()
    """Every question put to the advocate, and whether it came back.

    Persisted, because the alternative is asking again. An advocate who is
    asked something they answered two turns ago has been told their
    instructions were not recorded, and they stop volunteering detail."""
    last_activity: str = ""
    """WHEN THIS FILE WAS LAST WORKED, as an ISO date. BK-33.

    THE LIST SORTED ON `version`, WHICH IS NOT A TIME. `last_touched` was
    the version number -- an integer that counts writes -- so a matter
    written to nine times looked more recent than one written to twice
    yesterday, and an advocate scanning for what they touched this morning
    was reading a counter.

    THE FORUM'S DATE, taken from the turn (BK-14) and never from the
    machine, for the same reason every other date in this product is: a
    server keeping UTC is a day behind India from 18:30, and a file worked
    this evening would be listed as yesterday's.

    EMPTY IS `NEVER WORKED`, which is a real state for a matter opened and
    abandoned, and it renders as such rather than as an epoch.
    """

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
        """ADD a fact. Refuses one whose id is already on the file.

        A matter holding two facts with one id is a matter where every lookup
        is ambiguous and the FIRST one wins by accident of order. It happened:
        marking a fact superseded went through here, appended a second copy,
        and `chart` kept the un-superseded one — so the correction was applied
        and had no effect (B-086's fix, defeated by its own write).

        Amending an existing fact is `amending`, which says so.

        THE CONTENT RULE IS `recording`, AND THIS GOES THROUGH IT so that no
        caller reaches the raw append. A caller that needs to know which fact
        ended up on the file calls `recording` directly.
        """
        return self.recording(fact)[0]

    def recording(self, fact: Fact) -> tuple["Matter", Fact]:
        """Put this fact on the file, and say which fact is now there.

        B-107. ONE SENTENCE WAS BECOMING TWO FACTS. `with_fact` refused a
        duplicate ID and nothing refused duplicate CONTENT, and two paths
        create facts from one turn — the account is recorded whole (C1 takes
        it before clarifying anything) and the date read then produces a dated
        fact from the same sentence. Measured on GS-15's second run: 8 facts
        on a 5-turn matter, with "the agreement is dated 15-4-1984" held
        undated AND dated from one turn, and "Corrected: the agreement is
        dated 15-4-2024" held TWICE with the same statement and the same date.

        It cost three ways. The account budget paid for the same words twice,
        the model read a file that looked like it said something twice, and
        the limitation read a chronology with two entries where the advocate
        had described one event.

        WHAT THIS IS NOT. It is not "refuse the duplicate" — the right outcome
        is better than that. A dated reading of a sentence already on the file
        is THE SAME FACT, NOW DATED, so the held one is amended and the
        advocate sees one entry carrying its date instead of two entries
        carrying half the information each.

        THE FOUR CASES, and the third is the one that must not be collapsed:

            held undated, this dated   ── AMEND. One fact, now dated.
            held dated, same date      ── nothing to add.
            held dated, DIFFERENT date ── BOTH KEPT. That is a date conflict,
                                          `chronology.conflicts` surfaces it,
                                          and picking one here would be the
                                          silent resolution C5 forbids.
            neither dated              ── nothing to add.

        SAME TURN ONLY. The match is scoped to facts from this turn, because
        the defect is two extractions of ONE sentence and that is what a turn
        is. An advocate who says the same thing again on turn 4 has said it
        again — recording that once would lose the repetition, and the
        cross-turn case is the conflict path above, which already works.

        A SUPERSEDED FACT IS NOT A CANDIDATE. It has left the chart, and
        amending it would put a date on a record the advocate has withdrawn.

        The statement is compared with `nm.domain.text.fold` — the one fold,
        exact after typography (CLAUDE.md §5: no threshold, no score).
        """
        if any(f.id == fact.id for f in self.facts):
            raise ValueError(
                f"fact {fact.id} is already on this matter. `with_fact` adds; "
                f"use `amending` to replace one, so that a second copy cannot "
                f"be created by a caller who meant to change the first.")

        key = fold(fact.statement)
        held = next(
            (f for f in self.facts
             if f.superseded_by is None
             and f.provenance.turn == fact.provenance.turn
             and fold(f.statement) == key), None) if key else None

        if held is None:
            return (replace(self, facts=self.facts + (fact,),
                            version=self.version + 1), fact)

        if fact.date is not None and held.date is None:
            dated = replace(
                held, date=fact.date,
                provenance=replace(held.provenance,
                                   span=fact.provenance.span or held.provenance.span))
            return (self.amending(dated), dated)

        # Same date, or no new date: nothing is added. A DIFFERENT date is a
        # conflict and both are kept.
        if fact.date is not None and held.date != fact.date:
            return (replace(self, facts=self.facts + (fact,),
                            version=self.version + 1), fact)
        return (self, held)

    def amending(self, fact: Fact) -> "Matter":
        """REPLACE the fact with this id, keeping its position on the file.

        Position is kept because the chart sorts dated facts by date and lists
        undated ones in the order they arrived; re-appending an amended fact
        would move it, and an advocate reading their own chronology would find
        it had rearranged itself.
        """
        if not any(f.id == fact.id for f in self.facts):
            raise ValueError(
                f"fact {fact.id} is not on this matter, so there is nothing "
                f"to amend. `with_fact` is how a new one is added.")
        held = next(f for f in self.facts if f.id == fact.id)
        if fact == held:
            return self
        fact = replace(fact, version=held.version + 1)
        return replace(
            self, facts=tuple(fact if f.id == fact.id else f
                              for f in self.facts),
            version=self.version + 1)

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
