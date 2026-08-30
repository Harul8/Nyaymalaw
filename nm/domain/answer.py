"""The Answer type. PRD §6.2.

THE STRUCTURAL MOVE THIS FILE EXISTS FOR
----------------------------------------
The previous build tried to make the product decisive by telling it to be
decisive in a prompt. That never holds: a model over-applies a behavioural
instruction, because over-applying looks like compliance.

So decisiveness is not instructed here. It is made STRUCTURAL. An answer element
is one of exactly four kinds, and none of them can hold a survey or a recital of
the brief. There is no ElementKind for "background", so background cannot be
represented -- and a rule that cannot be violated does not need enforcing.

    You do not instruct a stance. You make the alternative unrepresentable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from nm.domain.matter import ThreadId


class ElementKind(str, Enum):
    """The four permitted kinds. There is deliberately no fifth."""

    ACTION = "action"        # do X, by when
    FINDING = "finding"      # a finding that CHANGES an action
    QUESTION = "question"    # a question that BLOCKS an action
    GROUND = "ground"        # the citation, proof position, or opposing argument


class Signal(str, Enum):
    """Loud-signal classes. These may never be collapsed or placed below the
    fold -- otherwise "concise" becomes the mechanism that suppresses exactly
    the signals we fought to raise."""

    NONE = "none"
    LIMITATION_BAR = "limitation_bar"
    UNRESOLVED_POSTURE = "unresolved_posture"
    ADVERSE_TREATMENT = "adverse_treatment"
    CONTRADICTION = "contradiction"
    CROSS_THREAD_EXPOSURE = "cross_thread_exposure"
    EMERGENCY = "emergency"

    @property
    def is_loud(self) -> bool:
        return self is not Signal.NONE


@dataclass(frozen=True)
class Element:
    kind: ElementKind
    text: str
    thread: ThreadId | None = None
    by_when: date | None = None
    no_deadline_reason: str | None = None
    refs: tuple[str, ...] = ()
    signal: Signal = Signal.NONE
    collapsible: bool = False
    gate: str | None = None
    """The gate that caused this element, where one did.

    Set at the point the element is created, never reconstructed later.
    The first version of the ask ledger recovered it by splitting
    `Answer.blocked_reason` on a colon, which is a second copy of the gate
    id living in a format string -- and a question that was not gated had
    to be given an invented id, which `tools/trace.py` rejected because an
    id that looks like a gate and is not in the matrix is exactly the
    inflation T8 exists to catch.

    `None` means no gate caused this. That is a real state: a question can
    be a one-off ("I could not reach the model, resend") rather than a
    standing condition, and the two are closed differently."""
    disclosure: bool = False
    """True when this element REPORTS WHAT COULD NOT BE ESTABLISHED rather than
    asserting anything about the law -- a corpus gap, a retrieval defect, a
    source retrieved and then dropped.

    The grounding gate reads this. A disclosure names the provision it could
    not produce, and naming it must not be mistaken for citing it; without the
    distinction, the product is withheld precisely for being honest.

    ONLY THE ENGINE SETS IT, on text it composed itself from a retrieval
    result. Model output always lands in an asserting element, so nothing the
    model writes can opt out of the gate."""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("an Element must say something")
        if self.kind is ElementKind.ACTION and not (self.by_when or self.no_deadline_reason):
            # An action without a date is incomplete. Where genuinely no
            # deadline applies, that is STATED rather than left blank.
            raise ValueError(
                "an ACTION needs by_when, or an express no_deadline_reason "
                "(PRD D3/L11)")
        if self.signal.is_loud and self.collapsible:
            raise ValueError(
                f"a {self.signal.value} signal cannot be collapsible (PRD §6.2 S5)")


class Mode(str, Enum):
    SHORT_QUESTION = "short_question"
    FULL_BRIEF = "full_brief"


class Route(str, Enum):
    MATTER = "matter"
    NON_MATTER = "non_matter"


@dataclass(frozen=True)
class Answer:
    route: Route
    mode: Mode
    mode_statement: str
    elements: tuple[Element, ...] = ()
    blocked: bool = False
    blocked_reason: str | None = None

    def __post_init__(self) -> None:
        if self.route is Route.NON_MATTER:
            return
        if not self.elements:
            raise ValueError("a matter-route answer must contain at least one element")
        first = self.elements[0]
        if first.kind not in (ElementKind.ACTION, ElementKind.QUESTION):
            # If the recommendation is not at the top, the analysis was written
            # toward a verdict and not toward a step.
            raise ValueError(
                "the first content element must be an ACTION or a blocking "
                "QUESTION, never background (PRD §6.2 S3). Got "
                f"{first.kind.value!r}.")
        if not any(e.kind in (ElementKind.ACTION, ElementKind.QUESTION)
                   for e in self.elements):
            raise ValueError(
                "every turn contains a recommendation or a blocking question "
                "(PRD D2). An answer with neither has failed.")

    @property
    def loud_signals(self) -> tuple[Element, ...]:
        return tuple(e for e in self.elements if e.signal.is_loud)

    def render_text(self) -> str:
        """The bytes that leave the process. Nothing else is emitted."""
        return "\n\n".join(e.text for e in self.elements)
