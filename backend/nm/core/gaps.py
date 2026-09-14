"""The gap queue, and the question policy. PRD §5.1–5.3.

A SENIOR DOES NOT RUN A SCRIPT
--------------------------------
*They ask the question that matters most next.* So this is not a state machine
advancing through phases; it is a PRIORITY QUEUE OVER GAPS, recomputed every
turn across the whole file. The order varies by matter, and a fixed order is
wrong on the matters that matter.

Ranked: blocking gates, then deadline urgency, then information value, then
consequence. A blocking gate short-circuits — an unresolved posture makes
everything below it worthless however interesting, which is a correctness
mechanism before it is a cost one.

THE MANUFACTURED QUESTION, REMOVED BY CONSTRUCTION
----------------------------------------------------
§5.2 states the mechanism and it is worth quoting because it is the whole
design: *there is no obligation to ask something in order to advance, because
there is nothing to advance. This removes the manufactured question BY
CONSTRUCTION RATHER THAN BY PROHIBITION.*

So a `Question` cannot be built without the `Gap` it fills, and a `Gap` cannot
be built without the action it blocks. E-090 — *every question traces to a gap
and to the action that gap blocks* — is then not a check that runs, it is a
sentence that cannot be written. A question that blocks nothing has nowhere to
come from.

THE ADVOCATE NAVIGATES; THE QUEUE IS ADVICE, NOT A RAIL
---------------------------------------------------------
§5.3: *if the advocate asks about another thread, NM answers on that thread in
that turn. It does not finish anything first and does not ask to come back.*

`follows` is the mechanism, and the eval is pointed: *a build that passes its
stages by railroading the advocate through them has failed.* The queue's own
preference is returned alongside, because the ordering survives as STATE even
when it is not driving — the deferred threads keep their deadlines on the
board.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.matter import ThreadId
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements


class GapKind(str, Enum):
    """Why this gap outranks that one. THE RANKING IS THE VOCABULARY.

    Declared as an ordered concept rather than computed from a score, because
    a score would need weights nobody measured and would rank a posture below
    a deadline on some matter, silently.
    """

    BLOCKING_GATE = "blocking_gate"
    """An unresolved posture makes everything below it worthless."""

    DEADLINE = "deadline"
    """Time is running on something."""

    INFORMATION_VALUE = "information_value"
    """The one question that unblocks the most."""

    CONSEQUENCE = "consequence"
    """What it costs if it stays open."""


#: THE ORDER, and it is the PRD's, in the PRD's words.
RANK: tuple[GapKind, ...] = (
    GapKind.BLOCKING_GATE, GapKind.DEADLINE,
    GapKind.INFORMATION_VALUE, GapKind.CONSEQUENCE,
)


@refuses_blank_text()
@dataclass(frozen=True)
class Gap:
    """Something missing, AND THE ACTION IT BLOCKS.

    `blocks` is required by the type. A gap that blocks nothing is not a gap,
    it is a curiosity, and the whole of §5.2's design is that there is nothing
    to ask about it with.
    """

    what: str
    blocks: str
    thread: ThreadId
    kind: GapKind
    """NO DEFAULT. The kind IS the rank, so a default is a rank nobody chose.

    `INFORMATION_VALUE` was the default for about an hour, and it sorts THIRD:
    an unclassified blocking gate would have queued below every deadline, which
    is precisely the burial this queue exists to prevent. Sorting the
    unclassified FIRST is no better -- then everything nobody thought about
    screams. So there is no unclassified state: whoever writes the gap says
    what makes it urgent."""

    @property
    def priority(self) -> int:
        return RANK.index(self.kind)


@refuses_blank_text()
@dataclass(frozen=True)
class Question:
    """A question, and the gap it exists to fill.

    THERE IS NO CONSTRUCTOR THAT OMITS THE GAP. E-090's counterexample -- *a
    question asked to keep the conversation moving* -- is unwritable rather
    than caught: there is nowhere for such a question to get a `Gap` from.
    """

    text: str
    gap: Gap

    @property
    def blocks(self) -> str:
        return self.gap.blocks


@implements("A3")
def rank(gaps: tuple[Gap, ...]) -> tuple[Gap, ...]:
    """Highest-value next action across the WHOLE FILE.

    Across the file and not within a thread, because five disputes on one file
    is the normal case: the most urgent thing is not reliably on the thread the
    advocate happens to be discussing.

    Stable within a kind, so the order the gaps arrived in survives where the
    ranking has nothing to say. An arbitrary tiebreak would look like a
    judgement nobody made.
    """
    return tuple(sorted(gaps, key=lambda g: g.priority))


@implements("A3")
def batched(gaps: tuple[Gap, ...], thread: ThreadId) -> tuple[Gap, ...]:
    """§5.2. ONE BATCHED ASK PER THREAD, never an interrogation across all.

    *Serial single questions make the advocate do the scheduling.* Batching by
    thread is what lets them answer a dispute in one go instead of ping-ponging
    across five.
    """
    return tuple(g for g in rank(gaps) if g.thread == thread)


@implements("A3")
def leads(gaps: tuple[Gap, ...]) -> Gap | None:
    """The single highest-value next action, or `None` where there is none.

    `None` IS AN ANSWER AND IT IS THE POINT. Nothing is owed when nothing is
    blocked -- §5.2 again -- and a queue that always yields something is the
    manufactured question with a data structure behind it.
    """
    ordered = rank(gaps)
    return ordered[0] if ordered else None


@implements("A3")
def follows(gaps: tuple[Gap, ...], asked_about: ThreadId,
            ) -> tuple[ThreadId, Gap | None]:
    """§5.3. THE ADVOCATE NAVIGATES.

    Returns the thread to answer on -- always the one they asked about -- and
    the queue's own preference, which is carried rather than obeyed.

    *It does not finish anything first and does not ask to come back.* The eval
    is pointed about the failure: a build that passes its stages by railroading
    the advocate through them has failed. So there is no branch here in which
    the queue wins; the second value exists so the answer can SAY what it would
    otherwise have raised, which is a note and not a redirection.
    """
    return asked_about, leads(gaps)


@implements("A3")
def still_missing(gaps: tuple[Gap, ...]) -> tuple[str, ...]:
    """§5.2's closing line: *"still missing, and why it matters"*.

    It closes every consultation, and it is what stops an assessment reading as
    more settled than it is. A RECORDED GAP IS A FIRST-CLASS OUTPUT -- after
    one re-ask NM accepts what was given and records the gap rather than
    pushing, so this is where the unanswered ones surface instead of
    disappearing into another question.
    """
    return tuple(f"{g.what} — needed for: {g.blocks}" for g in rank(gaps))
