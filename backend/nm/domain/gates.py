"""THE GATE MATRIX. One table, and it is the only one.

WHY THIS FILE EXISTS
--------------------
An external review found that §7.1 said the product "fails closed only on
grounding" while nine separate conditions elsewhere in the specification
blocked something. Both statements were written in good faith and they cannot
both be true, so a reader had no way to know what actually happens when a gate
fires -- and neither did the code, which decided it at each call site.

THE RESOLUTION IS NOT A LONGER SENTENCE. IT IS A RESPONSE CLASS AND A SCOPE,
AND EVERY GATE CARRIES BOTH.

    WITHHOLD   its scope produces NOTHING. No degraded result, no caveat.
    BLOCK      its scope is refused and THE BLOCK IS THE ANSWER: a question
               goes back, the turn succeeds, the file records the block.
    DISCLOSE   its scope proceeds carrying the stated limit. Used where the
               honest answer is "here is what I could not establish", and
               never to soften a WITHHOLD.

Response says what happens; SCOPE says to what -- the turn, a thread, one
directive step, or one evidence need. WITHHOLD on a NEED fails that need and
leaves the turn standing; WITHHOLD on a TURN emits nothing at all.

So §7.1's claim becomes precise and, as written before, it was wrong in one
direction and right in the other:

    THE TURN IS WITHHELD BY EXACTLY THREE GATES -- G-GROUND, G-ATTRIB and
    G-QUOTE, the grounding family -- PLUS G-STALE, which is not a quality gate
    at all but a concurrency re-derive.

Everything else blocks a step or discloses a limit, and which one it does is
read from this table rather than decided where the condition is detected.

THE SECOND COPY IS WHAT MAKES THIS DANGEROUS, SO THERE ISN'T ONE
----------------------------------------------------------------
This registry is the source. `assurance/gate/export_spec.py` dumps it to
`assurance/specification/gates.yaml` and `assurance/specification/prd/gates.json`; the PRD renders
its matrix from
that JSON. `speccheck` refuses a gate id in the document that is not here, and
`trace` refuses a gate declared here that no code path consults. A gate cannot
be documented and unbuilt, or built and undocumented.

Every state vocabulary below has THREE members wherever the condition can fail
to be evaluated at all -- `not_assessed` is a state, never a null. That is
defect shape S8, the single most repeated defect in the previous build: a
screen that could not run returned the shape of a clean result.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Response(str, Enum):
    """What the advocate experiences when the gate fires. Exactly three."""

    WITHHOLD = "withhold"    # nothing is emitted; the turn is refused
    BLOCK = "block"          # the block IS the answer; a question goes back
    DISCLOSE = "disclose"    # the turn proceeds, carrying the stated limit

    @property
    def fails_closed(self) -> bool:
        """`fail closed` is a property of the gate, not a global policy."""
        return self is Response.WITHHOLD


class Scope(str, Enum):
    """What is refused -- NOT how loudly."""

    TURN = "turn"            # the whole turn
    THREAD = "thread"        # every derivation on one thread
    STEP = "step"            # one directive step
    NEED = "need"            # one evidence need; the turn survives it


class Persistence(str, Enum):
    TURN = "turn"            # re-evaluated from scratch next turn
    STICKY = "sticky"        # recorded on the matter and survives restart


class Recovery(str, Enum):
    """WHO can clear it. `system` means it clears itself when the condition
    goes away; the others require a named actor, and a gate whose recovery is
    `human` may never be cleared by a model."""

    SYSTEM = "system"
    ADVOCATE = "advocate"
    HUMAN = "human"          # a named person, recorded, outside the model
    NONE = "none"            # a defect: it is fixed, not released


@dataclass(frozen=True)
class Gate:
    id: str
    condition: str
    states: tuple[str, ...]
    response: Response
    scope: Scope
    persistence: Persistence
    recovery: Recovery
    visible: str              # what the advocate is told, in one line
    feature: str              # the PRD feature that owns it
    built: bool               # whether a code path consults it TODAY

    def __post_init__(self) -> None:
        if len(self.states) < 2:
            raise ValueError(f"{self.id}: a gate with fewer than two states is not a gate")
        if self.recovery in (Recovery.ADVOCATE, Recovery.HUMAN) and len(self.states) < 3:
            # A gate an actor must clear can always fail to be evaluated, so it
            # needs a THIRD state naming that case -- `not_assessed`, `not_run`,
            # `unrecorded`, `unresolved`, `ambiguous`, `not_measured`. Without
            # it, a screen that could not run is indistinguishable from one that
            # passed, which is defect shape S8 and the most repeated defect in
            # the previous build.
            raise ValueError(
                f"{self.id}: a gate cleared by {self.recovery.value} needs a third "
                f"state for the could-not-evaluate case; it has {list(self.states)}")


# ---------------------------------------------------------------------------
# THE MATRIX. Ordered by phase: ADMIT-A, ADMIT-B, DERIVE, EMIT.
# ---------------------------------------------------------------------------

GATES: tuple[Gate, ...] = (
    # ---- ADMIT-A: above the screen boundary -------------------------------
    Gate(
        id="G-EMERGENCY",
        condition="Danger, liberty or an irreversible step is disclosed on the "
                  "names-and-danger reading.",
        states=("live", "cleared", "resolved", "not_assessed"),
        response=Response.BLOCK,
        scope=Scope.TURN,
        persistence=Persistence.STICKY,
        recovery=Recovery.ADVOCATE,
        visible="The protective step, its owner and its time, and nothing else. "
                "Merits are refused on this turn.",
        feature="B2",
        # BK-34: the producer landed 8 September 2026
        built=True,
    ),
    Gate(
        id="G-CONFLICT",
        condition="A party, counterparty or related entity matches the registry, "
                  "or the registry could not be read in full.",
        states=("clear", "matched", "incomplete", "not_run"),
        response=Response.BLOCK,
        scope=Scope.TURN,
        persistence=Persistence.STICKY,
        recovery=Recovery.HUMAN,
        visible="This matter cannot be taken further until the conflict position "
                "is settled by a person.",
        feature="B3",
        # BK-34: the producer landed 8 September 2026
        built=True,
    ),
    Gate(
        id="G-COMPETENCE",
        condition="The matter's jurisdiction or practice area is outside declared "
                  "coverage, or coverage could not be established.",
        states=("covered", "gap", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.THREAD,
        persistence=Persistence.STICKY,
        recovery=Recovery.HUMAN,
        visible="What is outside coverage is named, with what would be needed to "
                "close it. Work continues on what is inside.",
        feature="B4",
        # BK-34: the producer landed 8 September 2026
        built=True,
    ),
    Gate(
        id="G-SCOPE",
        condition="A step falls outside recorded engagement scope, or scope is "
                  "unrecorded.",
        states=("in_scope", "out_of_scope", "accepted", "unrecorded"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.STICKY,
        recovery=Recovery.ADVOCATE,
        visible="This step is outside recorded scope. It is not done silently, "
                "and advice given without scope is not reliance-ready.",
        feature="B5",
        # BK-34: the producer landed 8 September 2026
        built=True,
    ),
    Gate(
        id="G-CAPACITY",
        condition="Capacity to instruct is doubted on a decision that would become "
                  "authority.",
        states=("held", "doubted", "not_assessed"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.STICKY,
        recovery=Recovery.HUMAN,
        visible="The decision is not recorded as authority while capacity is open.",
        feature="B6",
        # BK-34: the producer landed 8 September 2026
        built=True,
    ),
    Gate(
        id="G-UNSCREENED",
        condition="Substance was admitted on a matter whose screens are not built "
                  "or did not run.",
        states=("screened", "unscreened", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="This matter was not screened. The output says so rather than "
                "reading as though it had passed.",
        feature="B3",
        built=True,
    ),

    # ---- ADMIT-B / DERIVE: the frame --------------------------------------
    Gate(
        id="G-POSTURE",
        condition="The thread's role is `unknown`, or a stated posture is "
                  "contradicted by a later statement.",
        states=("resolved", "unresolved", "conflicted"),
        response=Response.BLOCK,
        # STEP, NOT THREAD -- and the engine used to implement it as the
        # whole TURN, which is narrower still than what the matrix said.
        # What is refused is the DIRECTIVE STEP: the gate's own reason is
        # that the same provision helps one side and hurts the other WHEN A
        # STEP IS RECOMMENDED, and the text of a statute is the same bytes
        # for either side. Refusing to read it back applied the gate to a
        # case it was not written for, and an advocate asking a bare
        # question of law got "whose side are we on?" instead of an answer.
        scope=Scope.STEP,
        persistence=Persistence.STICKY,
        recovery=Recovery.ADVOCATE,
        visible="Whose side are we on. I will still read back what a provision "
                "says — that is the same on either side — but no directive step "
                "and no authority set is computed until it is settled, because "
                "the same provision helps one side and hurts the other.",
        feature="C3",
        built=True,
    ),
    Gate(
        id="G-LIMITATION",
        condition="Merits work is done on a thread whose limitation has not "
                  "been computed.",
        states=("computed", "not_applicable", "not_computed"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="Nothing side-dependent is recommended until the period is "
                "computed, and the reason is named.",
        feature="D1",
        # UNBUILT, DELIBERATELY, and the reason is in
        # `test_unbuilt_gates_are_declared_unbuilt`: the STATE is computed and
        # rendered, but nothing can yet tell whether the step being
        # recommended is merits work that DEPENDS on limitation. "Obtain the
        # sale deed" does not; "file the suit" does. Firing on the whole set
        # applies a gate to cases it was not written for -- G-POSTURE's
        # recorded defect.
        #
        # I built it and had to back it out: it suppressed the action on every
        # uncomputed thread, which broke slice 4's tested contract that *the
        # action says which* window could not be established.
        built=False,
    ),
    Gate(
        id="G-PREMISE",
        condition="A limitation is about to be computed: are the applicable "
                  "law, the accrual rule and the forum each ESTABLISHED, or "
                  "did the product infer one?",
        states=("established", "conditional", "unestablished"),
        response=Response.DISCLOSE,
        scope=Scope.STEP,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="BK-65-AC2: correct arithmetic cannot establish which "
                "provision governs, what starts the period, or which forum "
                "binds. Where a premise is INFERRED the date is shown "
                "CONDITIONAL with its alternatives and is never entered as a "
                "deadline; where one is UNESTABLISHED nothing is computed. A "
                "premise the advocate STATES outranks the inference and is "
                "recorded with who stated it and when.",
        feature="D1",
        built=True,
    ),
    Gate(
        id="G-THREAD",
        condition="An account cannot be bound to exactly one thread, or two "
                  "threads look like one without a decisive identifier.",
        states=("bound", "ambiguous", "unbindable"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="A merge is PROPOSED and never performed. A wrong split is "
                "visible; a wrong merge inverts the advice invisibly.",
        feature="C4",
        built=True,
    ),
    Gate(
        id="G-DATE",
        condition="An evidence need carries no governing date.",
        states=("dated", "undated"),
        response=Response.WITHHOLD,
        scope=Scope.NEED,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="The query is rejected rather than defaulted to today. Retrieval "
                "against the wrong version of an Act is not a near miss.",
        feature="D3",
        built=True,
    ),

    # ---- DERIVE: the grounding family. THE ONLY GATES THAT WITHHOLD -------
    Gate(
        id="G-GROUND",
        condition="A proposition in the answer is not supported by the span of a "
                  "retrieved primary source.",
        states=("supported", "unsupported"),
        response=Response.WITHHOLD,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.NONE,
        visible="Nothing is emitted. The advocate is told the turn was withheld "
                "and why -- never given the answer with a caveat.",
        feature="P1",
        built=True,
    ),
    Gate(
        id="G-DUTY",
        condition="The advocate instructs this product to DO something an "
                  "advocate must refuse -- make a false document, suppress "
                  "evidence, mislead the court, or shape what a witness says.",
        states=("clear", "refused", "not_assessed"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="The instruction is refused, the duty is NAMED, and what the "
                "law actually provides for what they were trying to achieve "
                "is retrieved and read back. A refusal with no route is a "
                "wall: an advocate asking this usually has a real problem, "
                "and there is a lawful answer to it.",
        feature="B2",
        built=True,
    ),
    Gate(
        id="G-SPLIT",
        condition="One message describes more than one dispute, so a thread "
                  "is opened for each and only one of them is advised on.",
        states=("split", "single", "not_assessed"),
        # `not_assessed` IS NOT A COURTESY MEMBER. The count comes from a
        # model read, and a read that does not run leaves the binder
        # falling back to one thread -- which is indistinguishable from
        # `single` unless this says otherwise. The advocate is then
        # advised on one dispute with no indication that nobody counted.
        response=Response.DISCLOSE,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="The other disputes are named and marked NOT ASSESSED. Silence "
                "here reads as an answer about them: a brief opening `first "
                "... second ... third` produced one thread with one posture "
                "and one limitation across all three, and the advocate was "
                "told every deadline on the file had passed while a trespass "
                "five days old sat in it.",
        feature="B1",
        built=True,
    ),
    Gate(
        id="G-ATTRIB",
        condition="A proposition is attributed to a judgment from a paragraph that "
                  "is not ratio, reasoning or order.",
        states=("attributable", "not_attributable"),
        response=Response.WITHHOLD,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.NONE,
        visible="Nothing is emitted. Counsel's losing submission is 14.8% of the "
                "case corpus and reads exactly like a holding.",
        feature="P2",
        built=True,
    ),
    Gate(
        id="G-QUOTE",
        condition="A quoted string in the answer does not appear verbatim in a "
                  "retrieved span.",
        states=("verbatim", "not_verbatim"),
        response=Response.WITHHOLD,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.NONE,
        visible="Nothing is emitted. A paraphrase inside quotation marks is a "
                "fabricated quotation whether or not it is accurate.",
        feature="P1",
        built=True,
    ),
    Gate(
        id="G-INFORCE",
        condition="Retrieved text was not in force on the matter's governing "
                  "date.",
        states=("in_force", "not_in_force"),
        response=Response.WITHHOLD,
        scope=Scope.NEED,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="The superseded text is not served. The 2024 codes make this "
                "load-bearing: the CrPC answer to a 2025 question is wrong in a "
                "way that reads exactly like right.",
        feature="H2",
        built=True,
    ),
    Gate(
        id="G-BINDING",
        condition="Binding status for an authority cannot be computed from its "
                  "court and date against the matter's jurisdiction.",
        states=("binding", "persuasive", "not_assessed"),
        response=Response.WITHHOLD,
        scope=Scope.NEED,
        persistence=Persistence.TURN,
        recovery=Recovery.HUMAN,
        visible="The authority may be quoted with its status disclosed. It may "
                "not carry a proposition alone.",
        feature="P2",
        built=True,
    ),

    # ---- DERIVE: coverage -------------------------------------------------
    Gate(
        id="G-HELDNOTFOUND",
        condition="The manifest declares the provision as intended coverage and "
                  "retrieval did not return it.",
        states=("retrieved", "held_not_found"),
        response=Response.DISCLOSE,
        scope=Scope.NEED,
        persistence=Persistence.TURN,
        recovery=Recovery.NONE,
        visible="A RETRIEVAL DEFECT, escalated. It is never shown to the advocate "
                "as though the corpus did not hold it.",
        feature="H8",
        built=True,
    ),
    Gate(
        id="G-CORRECTION",
        condition="Something the advocate just said REPLACES an entry already "
                  "on the file, rather than adding to it.",
        states=("superseded", "none", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.THREAD,
        persistence=Persistence.STICKY,
        recovery=Recovery.SYSTEM,
        visible="NOTHING IS DELETED. The replaced entry stays on the file and "
                "leaves the CHART, which is where the arithmetic reads — an "
                "advocate needs to see what they said as well as what replaced "
                "it, and §5.4 needs the prior value to still exist so a change "
                "can be reported with what it was before.",
        feature="A3",
        built=True,
    ),
    Gate(
        id="G-CONSERVE",
        condition="Something derived on an earlier turn is NOT derived on this "
                  "one — not withdrawn, not superseded, simply absent.",
        states=("complete", "lost", "not_assessed"),
        response=Response.BLOCK,
        scope=Scope.THREAD,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="A SILENTLY THINNER ANSWER IS THE FAILURE THIS EXISTS TO "
                "REFUSE. Nearly everything the product derives is re-read from "
                "scratch every turn, so a read that found three issues on turn "
                "2 and nothing on turn 9 does not fail — it succeeds, quietly, "
                "with less. `cascade.changes` cannot see it: that walks the "
                "values computed NOW and a value that vanished produces "
                "nothing from it. So the population here is what was derived "
                "BEFORE, and what is missing is named with its prior value.",
        feature="A3",
        built=True,
    ),
    Gate(
        id="G-CASCADE",
        condition="A value derived on an earlier turn has MOVED, because a "
                  "fact it rested on was corrected.",
        states=("moved", "unchanged", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.THREAD,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="§5.4: a corrected fact re-derives its dependents and reports "
                "each changed value WITH ITS PRIOR — a number the advocate "
                "cannot reconcile against what they remember reads as though "
                "they misread it the first time. And where earlier advice "
                "rested on it, that is said in terms: an advocate who filed on "
                "Tuesday against a date that moved on Thursday needs telling, "
                "and showing them a corrected number is not telling them.",
        feature="A3",
        built=True,
    ),
    Gate(
        id="G-CURRENCY",
        condition="A recorded conclusion rests on an input that has since "
                  "moved -- a corrected or withdrawn fact, a republished "
                  "provision, or another conclusion that itself moved -- and "
                  "has not yet been recomputed.",
        states=("current", "stale", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.STEP,
        # ON THE MATTER, because a currency held in a process is a currency
        # a restart converts to `current`. The ledger persists with the file,
        # and the cover reads it before any turn runs.
        persistence=Persistence.STICKY,
        recovery=Recovery.SYSTEM,
        visible="BK-65-AC1: changing a material predicate invalidates every "
                "dependent conclusion and NO unrelated one, keeping the prior "
                "state and the reason. G-CASCADE announces what MOVED between "
                "two turns; this is what is STILL NOT CURRENT -- between the "
                "correction and the recomputation, after a restart, and two "
                "hops away where a deadline rests on a limitation that rests "
                "on a date. A stale value is shown labelled stale, never "
                "counted as the nearest live deadline, and a node whose "
                "inputs nobody recorded is not_assessed rather than current.",
        feature="A3",
        built=True,
    ),
    Gate(
        id="G-GAP",
        condition="Something is missing that BLOCKS a named action, ranked "
                  "across the whole file: blocking gates, then deadline "
                  "urgency, then information value, then consequence.",
        states=("open", "none", "not_assessed"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="§5.2: there is NO OBLIGATION to ask something in order to "
                "advance, because there is nothing to advance — the "
                "manufactured question is removed by construction rather than "
                "by prohibition. A `Gap` cannot be built without the action it "
                "blocks, and a `Question` cannot be built without its gap, so "
                "a question that blocks nothing has nowhere to come from.",
        feature="A3",
        built=True,
    ),
    Gate(
        id="G-SALVAGE",
        condition="A claim is about to be reported as failing: which of the "
                  "seven coordinates was moved, and which were not.",
        states=("varied", "unvaried", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.THREAD,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="D8: almost every `you lose` is the failure of ONE coordinate, "
                "not of the case. A report that varied two and concluded the "
                "claim is dead has not done the work — and the two it DID vary "
                "make it look as though it had, which is why the ones nobody "
                "moved are named.",
        feature="D8",
        built=True,
    ),
    Gate(
        id="G-EXPOSURE",
        condition="The cross-file pass over every pair of threads: a position "
                  "on one dispute that damages another.",
        states=("found", "none_found", "not_run"),
        response=Response.DISCLOSE,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="EXACTLY ONCE ON EVERY FILE, empty or not. E-082's "
                "counterexample is *emitted twice, or silently omitted*, and "
                "the two fail in opposite directions: twice is noise the "
                "advocate learns to skip, and omitted reads as `nothing "
                "found` when nobody looked. `not_run` is a state for that "
                "reason — an absent pass and an empty one are opposite facts.",
        feature="D7",
        built=True,
    ),
    Gate(
        id="G-ADVERSE",
        condition="An adverse fact on the thread is neither explained nor "
                  "expressly conceded by the theory — or no theory has been "
                  "formed, in which case every adverse fact is unaccounted.",
        states=("accounted", "unaccounted", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.THREAD,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="E-080's counterexample, made visible: a theory that works only "
                "if three documents are forgotten READS PERFECTLY, because the "
                "three are simply not mentioned. Absence is invisible, so the "
                "unaccounted facts are listed by name rather than counted — "
                "which one it is decides what is pleaded.",
        feature="D6",
        built=True,
    ),
    Gate(
        id="G-PRESERVE",
        condition="An inventoried item is held by someone with an interest in "
                  "it not surviving, and no preservation step is on the file.",
        # THE THIRD STATE IS `not_assessed`, and the constructor refused
        # this row without it. An inventory that could not be read is not
        # an inventory with nothing at risk in it -- and this gate blocks
        # a step, so the difference decides whether the advocate proceeds.
        states=("preserved", "unpreserved", "not_assessed"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.STICKY,
        recovery=Recovery.ADVOCATE,
        visible="C7's counterexample, refused: the original agreement is with "
                "the opponent's brother, the item is inventoried, the holder "
                "is recorded, and nothing was ever asked of anyone — so the "
                "file reads as WORKED and the document is gone by the time it "
                "is needed. It blocks a step rather than noting a risk, "
                "because a note has been read and a block has been answered.",
        feature="C7",
        built=True,
    ),
    Gate(
        id="G-PROOF",
        condition="The claim has not been decomposed into what must be proved: "
                  "no element table is wired, the cause is not one this "
                  "product curates elements for, or the read could not run.",
        # THREE STATES, AND THE THIRD IS THE WHOLE ROW. "Every element has a
        # position" and "nobody worked out the positions" are what defect
        # shape S1 is about, and a conclusion with no proof section reads as
        # the first while being the second. An advocate who cannot tell them
        # apart cannot tell whether to go looking for the material.
        states=("assessed", "gaps_open", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        # SYSTEM, and it is the honest one. Two of the three ways this fires
        # -- no element table wired, no curated elements for this cause -- are
        # gaps in the PRODUCT, and neither the advocate nor a named person can
        # clear them by doing anything. It goes away when the table covers the
        # cause, which is work here and not an action there.
        recovery=Recovery.SYSTEM,
        visible="D5's counterexample, and it ran for a whole slice: "
                "`backend/nm/domain/proof.py` refused an OBTAINABLE position with "
                "nothing named that would obtain it, refused an ABSENT one "
                "with no dead end, and drew `uncovered` from the ELEMENTS so "
                "the coverage gate could not certify itself \u2014 and "
                "nothing ever built a `ProofPosition`, so none of it ran on a "
                "served turn. It DISCLOSES rather than blocks because a "
                "missing element list is a gap in this product, and stopping "
                "the advocate over our own gap teaches them to work around "
                "the gate.",
        feature="D5",
        built=True,
    ),
    Gate(
        id="G-CONSISTENT",
        condition="The recommended step contradicts a fact this same answer "
                  "computed — the limitation position, the deadline register, "
                  "the side we act for, or what has not been weighed.",
        # THREE STATES PLUS THE REPAIR, and `not_verified` is the one that
        # matters. A consistency check that could not run must not be
        # indistinguishable from one that found nothing: those are opposite
        # facts about the same step, and the second is the whole of S1.
        #
        # `repaired` is a fourth because it is a different fact again — the
        # step served was NOT the step written, and an advocate reading the
        # trace should be able to see that the sentence was rewritten once
        # rather than assume it came out right the first time.
        states=("consistent", "contradicted", "repaired", "not_verified"),
        response=Response.BLOCK,
        scope=Scope.STEP,
        persistence=Persistence.TURN,
        # SYSTEM: it clears when the step stops contradicting the figures.
        # There is nothing for the advocate to do about it — the conflict is
        # between two things this product produced.
        recovery=Recovery.SYSTEM,
        visible="B-074, TWICE. The ACTION read `file the recovery suit, "
                "ensuring it is within the limitation period` while the "
                "GROUND directly below it read `that period has run` — 174 "
                "days ago. It was fixed by telling the model what had been "
                "worked out, at length and correctly, and it recurred on "
                "`6e29cf0`: `Confirm the date of service and file within the "
                "window`, beside an annotation saying every deadline had "
                "passed.\n\n"
                "A PROMPT IS NOT A GUARD, which is why this row exists and "
                "why it is not a phrase list. The answer space is built from "
                "the turn's own typed facts, so the guard is exact "
                "membership rather than matching on words — the rule "
                "CLAUDE.md §5 states about Acts, applied to the one place a "
                "sentence is checked against a number.\n\n"
                "It BLOCKS the step and not the turn: the advocate gets the "
                "computed position and a question, which is the half that "
                "was verified.",
        feature="D3",
        built=True,
    ),
    Gate(
        id="G-REMEDY",
        condition="The relief that would serve the objective is unavailable, "
                  "hollow, late or unenforceable, or its cost exceeds what it "
                  "can recover -- read against the objective with the merits "
                  "held constant.",
        # THREE STATES, AND THE THIRD CARRIES THE WORK. `no_useful_relief`
        # covers both an established defeat and an inferred, unconfirmed
        # shortfall; the disclosure names which. `not_assessed` is a value:
        # a file nobody read for relief is not one with serviceable relief.
        states=("serveable", "no_useful_relief", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.THREAD,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="BK-70. A LEGALLY ARGUABLE CLAIM CAN BE WORTH NOTHING: the "
                "debtor holds no attachable assets, the only order the forum "
                "can give arrives too late, the decree is sound and there is no "
                "route to execute it, the suit costs more than it can recover. "
                "The enforceability basis is DISCLOSED at the point of the "
                "recommendation, so the advice rests on it rather than on the "
                "merits alone -- and where relief is defeated the step may not "
                "pursue it as though it will deliver, which is G-CONSISTENT "
                "reading the relief claim this gate discloses. PROPORTIONALITY "
                "IS STATED ALONGSIDE a legally available route, never used to "
                "withhold it (E3's NEVER).",
        feature="E2",
        built=True,
    ),
    Gate(
        id="G-NOTASSESSED",
        condition="The store that would answer this need could not be consulted "
                  "at all — absent, unopenable, or never built.",
        states=("assessed", "not_assessed"),
        response=Response.DISCLOSE,
        scope=Scope.NEED,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="NOT LOOKED AT, said in those words. Both neighbours here make a "
                "claim about a search that RAN — G-NOTHELD that the corpus does "
                "not hold it, G-HELDNOTFOUND that retrieval failed on something "
                "it does — and a search that never happened borrowing either of "
                "them tells the advocate something untrue.",
        feature="M4",
        built=True,
    ),
    Gate(
        id="G-NOTHELD",
        condition="The manifest does not declare the provision, and it was not "
                  "retrieved.",
        states=("held", "not_held"),
        response=Response.DISCLOSE,
        scope=Scope.NEED,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="What is missing is NAMED. A vague disclaimer is silence in more "
                "words.",
        feature="M4",
        built=True,
    ),
    Gate(
        id="G-COVERAGE",
        condition="A release-gate coverage minimum for the matter's court, period "
                  "or practice area is not met.",
        states=("met", "unmet", "not_measured"),
        response=Response.DISCLOSE,
        scope=Scope.THREAD,
        persistence=Persistence.TURN,
        recovery=Recovery.HUMAN,
        visible="The corpus holds no output of the binding court for this period. "
                "The advocate is told before relying on the answer, not after.",
        feature="H1",
        built=True,
    ),

    # ---- infrastructure ---------------------------------------------------
    Gate(
        id="G-READ",
        condition="A DECISIVE read answered with nothing. Its output is a date, "
                  "an amount, or which law is read, so an empty answer is "
                  "indistinguishable from 'that thing is not present' and the "
                  "arithmetic proceeds from the wrong value.",
        states=("answered", "empty", "not_run"),
        response=Response.DISCLOSE,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.ADVOCATE,
        visible="The turn says WHICH decisive read came back empty, so an "
                "advocate who can see the answer was computed without it can "
                "supply the missing thing in a sentence.",
        feature="7.4.1",
        built=True,
    ),
    Gate(
        id="G-MODEL",
        condition="A model tier is unreachable, over budget, or returns unusable "
                  "output after retries.",
        states=("available", "degraded", "unavailable"),
        response=Response.DISCLOSE,
        scope=Scope.NEED,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="The NEED fails, not the turn. The gap is visible and nothing is "
                "recorded as advice.",
        feature="7.4.4",
        built=True,
    ),
    Gate(
        id="G-STALE",
        condition="The matter moved underneath the turn between load and commit.",
        states=("current", "stale"),
        response=Response.WITHHOLD,
        scope=Scope.TURN,
        persistence=Persistence.TURN,
        recovery=Recovery.SYSTEM,
        visible="The turn is refused and re-derived. It is never merged over the "
                "newer state.",
        feature="I1",
        built=True,
    ),
)

BY_ID: dict[str, Gate] = {g.id: g for g in GATES}


def gate(gate_id: str) -> Gate:
    """Resolve a gate id, or fail loudly.

    A typo'd gate id must not silently become a free-text label -- that is how
    a gating condition becomes a log line nobody reads.
    """
    try:
        return BY_ID[gate_id]
    except KeyError:
        raise KeyError(
            f"{gate_id!r} is not a gate. The matrix is closed: add it to "
            f"backend/nm/domain/gates.py, or use metrics.violate() for a rule that is "
            f"not a gate.") from None


def withholding() -> tuple[Gate, ...]:
    """The gates that fail closed. There are four, and they are the answer to
    "what does §7.1 actually mean"."""
    return tuple(g for g in GATES if g.response.fails_closed)


def as_rows() -> list[dict]:
    """The matrix, for export. The PRD renders from THIS -- never from prose."""
    return [
        {
            "id": g.id,
            "condition": g.condition,
            "states": list(g.states),
            "response": g.response.value,
            "scope": g.scope.value,
            "persistence": g.persistence.value,
            "recovery": g.recovery.value,
            "visible": g.visible,
            "feature": g.feature,
            "built": g.built,
        }
        for g in GATES
    ]
