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

from nm.Archives.legal_brain.retrieve.source_excerpt_contracts import SourceExcerpt
from nm.shared.text_contracts import blank, refuses_blank_text
from nm.work_the_file.matter_contracts import ThreadId


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


@refuses_blank_text()
@dataclass(frozen=True)
class Element:
    kind: ElementKind
    text: str
    thread: ThreadId | None = None
    by_when: date | None = None
    no_deadline_reason: str | None = None
    refs: tuple[str, ...] = ()
    source: SourceExcerpt | None = None
    signal: Signal = Signal.NONE
    collapsible: bool = False
    gate: str | None = None
    """The gate that caused this element, where one did.

    Set at the point the element is created, never reconstructed later.
    The first version of the ask ledger recovered it by splitting
    `Answer.blocked_reason` on a colon, which is a second copy of the gate
    id living in a format string -- and a question that was not gated had
    to be given an invented id, which `assurance/gate/trace.py` rejected because an
    id that looks like a gate and is not in the matrix is exactly the
    inflation T8 exists to catch.

    `None` means no gate caused this. That is a real state: a question can
    be a one-off ("I could not reach the model, resend") rather than a
    standing condition, and the two are closed differently."""
    disclosure: bool = False

    feature: str = ""
    """WHICH FEATURE EMITTED THIS, by its spec id (`D5`, `C7`, `D9`).

    A consumer that has to read the TEXT to tell an issue finding from an
    inventory row breaks every time the product's English improves -- and
    a product whose tests break when its English improves does not improve
    its English. That is not hypothetical: the issues suite filtered on the
    words "runs against", said so in its own docstring, and predicted this
    field in the same sentence.

    EMPTY IS HONEST. Most elements have no feature worth naming and "" says
    exactly that; it is not a default standing in for one. The three that
    a consumer needs to tell apart set it.
    """
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
        if self.source is not None and (not isinstance(self.source, SourceExcerpt)
                                        or self.source.locator not in self.refs):
            raise ValueError("a source excerpt must bind to this element's exact reference")
        if blank(self.text):
            raise ValueError("an Element must say something")
        if self.kind is ElementKind.ACTION and blank(self.by_when) \
                and blank(self.no_deadline_reason):
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
    EXPLANATION = "explanation"
    ASSESSMENT = "assessment"


class Route(str, Enum):
    MATTER = "matter"
    NON_MATTER = "non_matter"


#: WHAT A LINE OF THE BOARD NOTE REPORTS. The first group is what the saved
#: file actually gained; the second is what NM noticed and did NOT apply, which
#: waits for the advocate (LB-90, owner, 28 September 2026).
APPLIED_KINDS = frozenset({
    "dispute_opened", "statements_added", "dated_event", "corrected",
    "question_answered", "party_added", "side_recorded", "kept_apart"})
PROPOSED_KINDS = frozenset({
    "proposed_withdrawal", "proposed_party_removal", "proposed_party_move",
    "unmatched_request", "held_other_matter"})


@refuses_blank_text("kind", "text")
@dataclass(frozen=True)
class BoardChange:
    """ONE LINE OF THE BOARD NOTE UNDER A REPLY. Not advice, and not a claim a
    model made: an applied line is computed from the file before and after the
    turn, and a proposed line changed nothing until the advocate acts on it.

    `target` is the entry or party a button acts on; `value` the side a party
    moves to; `was` / `was_date` the words and date a correction replaced, so
    Undo can put them back through the ordinary correction owner.
    """

    kind: str
    text: str
    target: str = ""
    value: str = ""
    was: str = ""
    was_date: str = ""

    def __post_init__(self) -> None:
        if self.kind not in APPLIED_KINDS | PROPOSED_KINDS:
            raise ValueError(f"unknown board change kind {self.kind!r}")


@refuses_blank_text("text")
@dataclass(frozen=True)
class ReplyParagraph:
    """ONE PARAGRAPH OF THE REPLY AS THE ADVOCATE READS IT. LB-76, owner, 28
    September 2026: guiding principles, not templates.

    The answer's `elements` are the CHECKED WORKING FINDINGS of the turn -- what
    was established, asked, recommended and could not be established. The reply
    is those findings told as one colleague tells another, written by one
    composer and then checked again ON THESE WORDS (`grounding.verify_reply`).

    `carries` names the element whose checked wording this paragraph IS,
    verbatim -- a limit, a blocker or a step the reply keeps word for word, or
    one appended because the composed prose did not convey it. `passage` names
    the element whose saved source the paragraph relies on, for its pinpoint
    link. Both are indexes into `Answer.elements`; neither is a certificate --
    the words are checked, not the labels.
    """

    text: str
    passage: int | None = None
    carries: int | None = None
    cites: tuple[tuple[int, int, int], ...] = ()
    """INLINE CITATIONS, several to a paragraph (LB-76 change 5, owner, 30 September
    2026): `(start, end, element)` -- the characters of `text` that name a saved
    passage, each a link opening that element's source at the exact passage. The
    words are the source's own label, written by code from the retrieved item,
    never typed by the model (the previous build's citation tags, reused)."""


@refuses_blank_text("mode_statement")
@dataclass(frozen=True)
class Answer:
    route: Route
    mode: Mode
    mode_statement: str
    elements: tuple[Element, ...] = ()
    blocked: bool = False
    blocked_reason: str | None = None
    board_changes: tuple[BoardChange, ...] = ()
    """What this message changed on the board, and what waits for the
    advocate. Empty on a turn that changed nothing, and on every answer saved
    before the note existed."""
    composed: tuple[ReplyParagraph, ...] = ()
    """THE REPLY, told from the checked `elements` (LB-76). Empty means the
    checked findings are shown as they are: nothing was composed, or the
    composed words failed their checks -- and on every answer saved before
    composition existed."""

    def __post_init__(self) -> None:
        for paragraph in self.composed:
            for index in (paragraph.passage, paragraph.carries):
                if index is not None and not 0 <= index < len(self.elements):
                    raise ValueError("a reply paragraph names an element this answer does not hold")
            if paragraph.passage is not None and self.elements[paragraph.passage].source is None:
                raise ValueError("a reply paragraph's passage must be a saved source")
            if paragraph.carries is not None \
                    and paragraph.text != self.elements[paragraph.carries].text:
                raise ValueError(
                    "a carried paragraph must be its element's checked words, verbatim")
            for start, end, index in paragraph.cites:
                source = (self.elements[index].source
                          if 0 <= index < len(self.elements) else None)
                if source is None or paragraph.text[start:end] != source.label \
                        or not 0 <= start < end <= len(paragraph.text):
                    raise ValueError("a citation must be a saved source's own label, "
                                     "at the place it names")
        if self.route is Route.NON_MATTER:
            return
        if not self.elements:
            raise ValueError("a matter-route answer must contain at least one element")
        # PRD E2, BY PURPOSE (owner, 28 September 2026). A blocked turn leads
        # with its blocker. An unblocked turn leads with its answer, which the
        # type leaves to the work because only a reading can tell an answer from
        # background: no turn computes a next step per message any more (LB-76;
        # owner, 30 September 2026 -- the reply gives what the retrieved law says
        # and requires, then asks for what the file lacks), so there is no
        # recommendation to put first. Purpose governs presentation, not
        # permission, grounding or truth -- and how the reply is WRITTEN is
        # guidance (`register_contracts.REPLY_CRAFT`), not this rule.
        if not self.blocked:
            return
        first = self.elements[0]
        if first.kind not in (ElementKind.ACTION, ElementKind.QUESTION):
            # A stopped turn that does not lead with what stops it has hidden the
            # one thing the advocate must answer before anything moves.
            raise ValueError(
                "a blocked answer's first content element must be an ACTION or a "
                "blocking QUESTION, never background (PRD E2). Got "
                f"{first.kind.value!r}.")

    @property
    def loud_signals(self) -> tuple[Element, ...]:
        return tuple(e for e in self.elements if e.signal.is_loud)

