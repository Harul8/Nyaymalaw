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
This registry is the source. `tools/export_spec.py` dumps it to
`spec/gates.yaml` and `spec/prd/gates.json`; the PRD renders its matrix from
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
        built=False,
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
        built=False,
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
        built=False,
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
        built=False,
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
        built=False,
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
        states=("computed", "not_computed", "not_assessed"),
        response=Response.BLOCK,
        # THE SECOND BLOCKING GATE OF PHASE D, and the PRD names it beside
        # G-POSTURE: "no merits work is done on a thread whose posture is
        # unresolved, or whose limitation has not been computed."
        #
        # DECLARED AND NOT BUILT, DELIBERATELY. What is missing is not the
        # limitation computation -- D2 computes it, and a thread with no
        # computed position already renders a BLOCKED row on the threshold
        # map with the reason. What is missing is the OTHER HALF of the
        # condition: whether the step being recommended depends on
        # limitation at all. "Obtain the sale deed from the sub-registrar"
        # does not; "file the suit" does, and nothing in slice 4 can tell
        # them apart. That classification arrives with D5, which resolves a
        # cause into elements and so knows which steps are merits work.
        #
        # Firing it without that half would repeat the exact defect
        # G-POSTURE's own comment records: a gate applied to a case it was
        # not written for, refusing an advocate the answer to a bare
        # question of law. Leaving the row out entirely would be worse --
        # the matrix would say nothing evaluates a condition the PRD calls
        # blocking, and the advocate would have no way to know.
        scope=Scope.STEP,
        persistence=Persistence.STICKY,
        recovery=Recovery.ADVOCATE,
        visible="Whether limitation has been computed on this thread. Until "
                "it is, the threshold map carries it as BLOCKED with the "
                "reason, and no step is presented as though the window were "
                "known.",
        feature="D1",
        built=False,
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
            f"nm/domain/gates.py, or use metrics.violate() for a rule that is "
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
