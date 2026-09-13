"""The adaptive lead's typed state: claims, steps and the plan. P46.

    from nm.domain.lead import Claim, EpistemicStatus, Action, StepProposal, Plan

BK-91-AC1 and BK-91-AC2, autonomy.json AUTO-01/AUTO-02. This module holds the
TYPES the lead reasons over; `nm.core.lead` holds the runtime that chooses and
revises steps. The split is the layer rule, and here it also draws the line the
control boundary draws: the agent proposes over `dynamic_actions`, but admission
and acceptance are the application's (P47), so the decision code cannot sit on a
type the agent constructs.

EPISTEMIC STATUS IS THE WHOLE OF AC2
--------------------------------------
A material claim is one of six things, and they are NOT interchangeable:

    ALLEGATION   a party asserts it. The source exists; the claim is contested
                 by its own nature.
    EXTRACTED    text is present at a locator. A quote is not its meaning.
    DISPUTED     two sources or parties disagree on the same subject.
    SUPPORTED    ASSESSED to be borne out by a current source. This is the only
                 status a conclusion may rest on, and it is reachable only
                 through an assessment against a current version -- never from a
                 source merely existing, being quoted, or carrying a locator.
    INFERENCE    the product reasoned it. A hypothesis, autonomy.json
                 `model_knowledge: investigation_hypothesis_not_evidence`.
    UNKNOWN      nobody has established it. §9's third state.

    Source existence, an exact quote and a valid locator do not establish
    semantic support -- `semantic_support: assessed_not_proved_by_schema_or
    _citation_presence`. So `classify` can produce ALLEGATION or EXTRACTED but
    never SUPPORTED, and `nm.core.lead.assess_support` is the only way up.

VERSION-LINKED, SO A CHANGE INVALIDATES
-----------------------------------------
Every claim carries the source id, version and locator it rests on. When a
source, instruction or permission changes, the claims resting on the old version
are no longer current, and `is_current` reports it -- the same currency
discipline P18 keeps for conclusions, one layer up at the claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.text import refuses_blank_text


class EpistemicStatus(str, Enum):
    """What is known about a claim, and how. SUPPORTED is earned, never given."""

    ALLEGATION = "allegation"
    EXTRACTED = "extracted"
    DISPUTED = "disputed"
    SUPPORTED = "supported"
    INFERENCE = "inference"
    UNKNOWN = "unknown"

    @classmethod
    def not_established(cls) -> "EpistemicStatus":
        return cls.UNKNOWN

    def is_material_conclusion(self) -> bool:
        """A status a piece of ADVICE may rest on. Only SUPPORTED qualifies; an
        allegation, an extract, a dispute, a hypothesis or an unknown may be
        reported but may not be relied on as established."""
        return self is EpistemicStatus.SUPPORTED


class Action(str, Enum):
    """The permitted next moves. autonomy.json `control_boundary.dynamic_actions`.
    The lead PROPOSES one; the application admits it. There is deliberately no
    'analyse the standard litigation checklist' action -- a fixed cognitive
    sequence is exactly what AUTO-01 forbids."""

    READ = "read"
    RETRIEVE = "retrieve"
    COMPARE_HYPOTHESES = "compare_hypotheses"
    ASK = "ask"
    DELEGATE = "delegate"
    ASSESS = "assess"
    CHALLENGE = "challenge"
    DRAFT = "draft"
    REVISE = "revise"
    STOP = "stop"


@refuses_blank_text("statement", "source_id")
@dataclass(frozen=True)
class Claim:
    """One material claim, with its provenance and epistemic status.

    `subject` is what two claims can disagree ABOUT, so a dispute is set
    arithmetic. `source_version` is the version of the source this claim rests
    on; a SUPPORTED claim MUST name one, because support is against a specific
    version and a later version may not bear it out.
    """

    id: str
    statement: str
    status: EpistemicStatus
    source_id: str
    source_version: int = 0
    locator: str = ""
    subject: str = ""
    asserted_by: str = ""
    """WHICH PARTY asserts this claim. Adversity is relative to the side we act
    for, so the same claim is ours on one posture and the opponent's on the
    other -- which is why changing the represented side yields a reasoned
    different assessment (EVAL-031), and why this is provenance, not a verdict."""

    def __post_init__(self) -> None:
        if self.status is EpistemicStatus.SUPPORTED and self.source_version <= 0:
            raise ValueError(
                "a SUPPORTED claim must rest on a specific source version; "
                "support is assessed against a version, not against existence")

    def is_current(self, snapshot: dict) -> bool:
        """Whether this claim rests on the CURRENT version of its source.
        `snapshot` maps source id -> current version. A source not in the
        snapshot is treated as moved-or-gone, so a claim on it is not current --
        the safe direction, because absence of a version is not proof of
        currency."""
        return self.source_version == snapshot.get(self.source_id)


@refuses_blank_text("objective", "rationale")
@dataclass(frozen=True)
class StepProposal:
    """One proposed next action, versioned by the snapshot it was framed on.

    `rationale` is a CONCISE professional reason, never persisted chain-of-thought
    (autonomy.json `audit: restricted_concise_rationale_no_raw_chain_of_thought`).
    `open_predicates` are what remains unresolved after this step -- so a plan
    can never read as finished while it names an open predicate.
    """

    action: Action
    objective: str
    snapshot_version: int
    rationale: str
    evidence_refs: tuple[str, ...] = ()
    open_predicates: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    """The lead's state at one snapshot: what is claimed, what is still open,
    and whether it may be reported complete. A frozen plan cannot claim
    completion once a premise it rested on has moved -- `completed` is derived
    by `nm.core.lead.readiness`, never set by the agent."""

    snapshot_version: int
    claims: tuple[Claim, ...] = ()
    open_needs: tuple[str, ...] = ()
    completed: bool = False
    escalation: str = ""

    def conclusions(self) -> tuple[Claim, ...]:
        """The claims a piece of advice would rest on -- the SUPPORTED ones."""
        return tuple(c for c in self.claims
                     if c.status.is_material_conclusion())
