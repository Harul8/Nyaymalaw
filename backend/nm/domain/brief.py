"""BK-37 — THE COUNSEL BRIEF. Stable sections, in the order counsel reads.

WHAT AN ANSWER LOOKED LIKE BEFORE THIS
----------------------------------------
J-6, measured: one single-dispute brief produced **31 elements** in a flat
sequence. The leading ACTION was the advocate's own question returned to them.
Underneath it, in no order anyone chose: nine "they will say" paragraphs, five
not-assessed disclosures, the threshold list, the screens list, the evidence
bound notice, the proof positions, and the trace line.

Nothing in it was wrong. Every element was true, sourced and necessary to
somebody. What was missing was an ORDER, and without one the reader has to
hold the whole answer in their head to find the two lines they act on.

WHY SECTIONS AND NOT A BETTER SORT
------------------------------------
A sort needs a rank per element and a rank is a judgement about importance —
which is exactly the judgement this product must not make silently. Nine
adverse paragraphs are not less important than the limitation position; they
answer a DIFFERENT QUESTION, and a reader looking for one is not looking for
the other.

So the elements are not ranked. They are FILED, by the question each answers:

    POSITION   where this stands
    BECAUSE    the controlling reason
    RISK       the decisive risk and the adverse case
    WINDOW     limitation and deadlines
    NEXT       the step, its owner and its by-when
    NEEDED     what is missing, and what would close it
    AUTHORITY  what any of it rests on
    AUDIT      how the answer was made

THE ASSIGNMENT IS PURE AND HAS ONE OWNER
------------------------------------------
It reads only fields the `Element` already carries. No model, no clock, no
store — so it runs in the class-A cadence, and the browser groups rather than
deciding. A renderer that decided sections for itself would be a second
opinion about what an element IS, which is the S9 shape in the place where it
is hardest to see: two correct components and the disagreement only visible on
a screen nobody diffed.

AUDIT IS A SECTION AND NOT A DELETION
---------------------------------------
J-7's finding is that gate ids, rule ids, token counts and the trace line are
engineering vocabulary on an advocate's screen. The answer is NOT to stop
recording them — every one is what makes a claim checkable, and this whole
product is an argument for keeping them. It is that they answer *how was this
made*, which is a question an advocate asks occasionally and counsel reading
for the position never asks at all.

So they are filed, under a heading, behind a control. Present, checkable, and
not in the way.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.answer import Element, ElementKind, Signal


class Section(str, Enum):
    """The questions an answer is filed under. ORDER IS THE ORDER READ."""

    POSITION = "position"
    BECAUSE = "because"
    RISK = "risk"
    WINDOW = "window"
    NEXT = "next"
    NEEDED = "needed"
    AUTHORITY = "authority"
    AUDIT = "audit"


#: What each section is called on screen, and the question it answers. The
#: heading is the QUESTION rather than a noun, because a reader scanning for
#: "what do I do" finds it faster than one scanning for "Action".
HEADINGS: dict[Section, tuple[str, str]] = {
    Section.POSITION:  ("Where this stands", "the position on this thread"),
    Section.BECAUSE:   ("Why", "what the position rests on"),
    Section.RISK:      ("What cuts against us", "the decisive risk"),
    Section.WINDOW:    ("Time", "limitation and deadlines"),
    Section.NEXT:      ("Next step", "with its owner and by-when"),
    Section.NEEDED:    ("What I still need", "and what it would settle"),
    Section.AUTHORITY: ("What it rests on", "provisions and authority"),
    Section.AUDIT:     ("How this answer was made", "gates, reads and cost"),
}

#: The order they are READ IN, which is not the order they were derived in.
#: Counsel opens an advice looking for the position and the step; the working
#: is what they turn to when they disagree with it.
ORDER: tuple[Section, ...] = (
    Section.POSITION, Section.WINDOW, Section.RISK, Section.NEXT,
    Section.NEEDED, Section.BECAUSE, Section.AUTHORITY, Section.AUDIT,
)


def section_of(element: Element) -> Section:
    """Which question this element answers. PURE, and the only owner.

    THE ORDER OF THE TESTS IS THE DESIGN. A loud signal outranks the kind it
    arrived on -- an expired limitation is a FINDING and belongs under Time,
    not under the position it destroys -- and `Signal.is_loud` is already the
    product's one statement of what may never be softened.
    """
    if element.signal is Signal.LIMITATION_BAR:
        return Section.WINDOW
    if element.signal.is_loud:
        return Section.RISK
    if element.kind is ElementKind.ACTION:
        return Section.NEXT
    if element.kind is ElementKind.QUESTION:
        return Section.NEEDED
    if element.kind is ElementKind.FINDING:
        return Section.POSITION
    # GROUNDS split three ways, and the split is by what they carry rather
    # than by what they say. A ground with refs is authority; a ground marked
    # as a disclosure is something that could not be established, which is
    # material the advocate can supply; the rest is reasoning.
    if element.refs:
        return Section.AUTHORITY
    if element.disclosure:
        return Section.NEEDED
    return Section.BECAUSE


@dataclass(frozen=True)
class Line:
    """One line of the brief, with the count of times it was said."""

    element: Element
    said: int = 1
    """How many elements collapsed into this one.

    BK-37: *deduplicate repeated gaps and show their count without hiding a
    new or critical one.* The count is kept rather than dropped because "I
    could not assess this" said once and said nine times are different facts
    about the file -- and an advocate reading the shorter answer must not
    believe the product looked less hard than it did.
    """


def _key(element: Element) -> tuple:
    """What makes two lines the same line.

    THE TEXT AND THE KIND, and deliberately not the thread: the same gap on
    three threads is three facts and collapsing them would hide two files.
    """
    return (element.kind, element.thread, " ".join(element.text.split()))


def lines_for(elements, section: Section) -> tuple[Line, ...]:
    """The lines of one section, deduplicated, IN ARRIVAL ORDER.

    NOTHING LOUD IS EVER COLLAPSED, and that is not a special case here --
    `Element` already refuses a loud signal marked collapsible, and this
    keeps loud lines separate for the same reason: a repeated adverse finding
    is not noise, it is the same problem on two threads.
    """
    out: list[Line] = []
    seen: dict[tuple, int] = {}
    for element in elements:
        if section_of(element) is not section:
            continue
        if element.signal.is_loud:
            out.append(Line(element))
            continue
        key = _key(element)
        if key in seen:
            at = seen[key]
            out[at] = Line(out[at].element, out[at].said + 1)
            continue
        seen[key] = len(out)
        out.append(Line(element))
    return tuple(out)


def sections(elements) -> tuple[tuple[Section, tuple[Line, ...]], ...]:
    """The whole brief, in reading order, EMPTY SECTIONS DROPPED.

    A heading with nothing under it tells the advocate a question was asked
    and answered with silence, which is the one reading this product refuses
    everywhere else. A section that has nothing in it was not asked.
    """
    out = []
    for section in ORDER:
        lines = lines_for(elements, section)
        if lines:
            out.append((section, lines))
    return tuple(out)


#: Sections an advocate sees by default. AUDIT is the only one behind a
#: control, and it is behind one because it answers a question they are not
#: asking -- not because it is unimportant, and never because it is hidden.
ADVOCATE_SECTIONS: frozenset[Section] = frozenset(
    s for s in Section if s is not Section.AUDIT)
