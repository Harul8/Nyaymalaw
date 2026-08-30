"""Thread binding. Slice 3 -- never answer a question whose frame is unsettled.

THE ASYMMETRY THAT DECIDES EVERY RULE IN THIS FILE
---------------------------------------------------
A wrong SPLIT duplicates work and is visible: the advocate sees two rows where
they expected one, says so, and it is corrected in a turn.

A wrong MERGE attaches one thread's posture, chronology and limitation to facts
they do not govern. Every citation stays correct. The board looks tidier. And
the advice inverts silently, which is the failure mode this whole product
exists to refuse.

So the rules are deliberately unbalanced:

    a DECISIVE IDENTIFIER binds        -- a case number, an FIR number, a cheque
    an EXPLICIT REFERENCE binds        -- the advocate named the thread
    A NEW DISPUTE OPENS A THREAD       -- read, quoted, and stated so it can
                                          be corrected
    ANYTHING ELSE ASKS                 -- and the question is the answer

THE THIRD RULE USED TO READ *a SINGLE OPEN THREAD continues -- there is
nothing to be wrong about*, and there was. Rule 3 creates a thread only
when the message carries a number of record, so with one thread on the
file and no case number, a SECOND DISPUTE was welded onto the first --
and a matter could not hold two threads unless the advocate typed a
number. Three disputes driven through it produced one thread carrying
`role=accused`, which would have advised the client's own recovery suit as
though he were defending it. The golden set calls multi-thread files the
NORMAL case.

LABEL SIMILARITY NEVER BINDS. "The Kukatpally property", "the land matter" and
"O.S. 442/2023" can be one thread or three, and nothing in those strings tells
you which. Two disputes between the same two parties are the ordinary case in
practice, not the edge case -- a landlord suing on arrears and on possession is
two threads with two limitation positions and two postures.

MERGES ARE PROPOSED AND NEVER PERFORMED. A merge is a decision with no undo
that the advocate has the facts to make and the product does not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from nm.domain.matter import Fact, Matter, Thread
from nm.domain.text import refuses_blank_text
from nm.domain.traceability import implements

# Decisive identifiers as they are actually written in Indian practice. Each
# pattern captures a NUMBER OF RECORD -- something a registry assigned, which
# is what makes it decisive. Descriptions never appear here.
_IDENTIFIERS: tuple[tuple[str, re.Pattern], ...] = (
    ("case_number", re.compile(
        r"\b((?:O\.?S|C\.?C|S\.?C|C\.?R\.?P|W\.?P|W\.?A|A\.?S|E\.?P|E\.?A|I\.?A"
        r"|Crl\.?\s?[MPA]\.?P?|Crl\.?A|M\.?A\.?C\.?M\.?A|F\.?C\.?O\.?P|O\.?P"
        r"|R\.?S\.?A|S\.?A|C\.?M\.?A)\.?\s*(?:No\.?\s*)?(\d+)\s*(?:/|of)\s*(\d{4}))\b",
        re.I)),
    ("fir", re.compile(
        r"\b(?:F\.?I\.?R\.?|Cr(?:ime)?\.?)\s*(?:No\.?\s*)?(\d+\s*(?:/|of)\s*\d{4})\b",
        re.I)),
    ("cheque", re.compile(
        r"\bcheque\s*(?:no\.?|number)\s*([A-Z]?\d{5,})\b", re.I)),
    ("survey", re.compile(
        r"\b(?:Sy|Survey)\.?\s*No\.?\s*([\d/\-]+)\b", re.I)),
    ("document", re.compile(
        r"\b(?:document|doc)\.?\s*no\.?\s*(\d+\s*(?:/|of)\s*\d{4})\b", re.I)),
)


class BindState(str, Enum):
    """Three states. `AMBIGUOUS` is the one that earns its keep."""

    BOUND = "bound"
    AMBIGUOUS = "ambiguous"      # more than one candidate, nothing decisive
    UNBINDABLE = "unbindable"    # nothing to bind to and nothing to create from


@refuses_blank_text()
@dataclass(frozen=True)
class MergeProposal:
    """A proposal, and it is never applied by anything in this codebase."""

    left: str
    right: str
    on: str
    question: str


@refuses_blank_text("question", "reason")
@dataclass(frozen=True)
class BindResult:
    state: BindState
    thread: Thread | None
    created: bool
    reason: str
    proposal: MergeProposal | None = None
    question: str = ""

    @property
    def blocks(self) -> bool:
        return self.state is not BindState.BOUND


def identifiers_in(text: str) -> dict[str, str]:
    """Every number of record disclosed in a message.

    Normalised on read: `O.S.442/2023`, `OS 442 of 2023` and `O. S. No. 442/2023`
    are one identifier, because an identifier that only matches its own spelling
    is not an identifier.
    """
    found: dict[str, str] = {}
    for kind, pattern in _IDENTIFIERS:
        m = pattern.search(text or "")
        if not m:
            continue
        raw = m.group(1)
        # Fold every spelling onto one value. `No.`, the dots and the spaces
        # are noise; "of" and "/" are the same separator. `O.S. 442/2023`,
        # `OS 442 of 2023` and `O.S.No.442/2023` must produce ONE identifier,
        # or the second mention of a case opens a second thread.
        value = re.sub(r"\s+", "", raw)
        value = re.sub(r"(?i)\bno\.?", "", value)
        value = value.replace(".", "").replace("of", "/").upper()
        found[kind] = value
    return found


@implements("C4")
def bind(matter: Matter, message: str, fact: Fact,
         thread_hint: str | None = None,
         opens_new_dispute: bool | None = None) -> BindResult:
    """Bind an account to exactly one thread, or refuse and ask.

    `thread_hint` is the advocate saying which thread they mean. It outranks
    everything else, because the only source better than a registry number is
    the person holding the file.
    """
    disclosed = identifiers_in(message)

    # 1. The advocate named the thread.
    if thread_hint:
        target = matter.thread(thread_hint)
        if target is None:
            return BindResult(
                BindState.UNBINDABLE, None, False,
                f"thread {thread_hint!r} is not on this matter",
                question=("That thread is not on this file. Which of the open "
                          "threads did you mean?"))
        return BindResult(BindState.BOUND, _with_identifiers(target, disclosed),
                          False, "bound to the thread the advocate named")

    # 2. A decisive identifier matches an existing thread.
    matches = [t for t in matter.threads
               if any(t.identifiers.get(k) == v for k, v in disclosed.items())]
    if len(matches) == 1:
        key = next(k for k, v in disclosed.items() if matches[0].identifiers.get(k) == v)
        return BindResult(BindState.BOUND, _with_identifiers(matches[0], disclosed),
                          False, f"decisive identifier {key}={disclosed[key]}")
    if len(matches) > 1:
        # Two threads carrying the same number of record is an ingestion or
        # data defect, not a merge invitation. It is PROPOSED, never applied.
        return BindResult(
            BindState.AMBIGUOUS, None, False,
            f"{len(matches)} threads carry the same identifier",
            proposal=MergeProposal(
                left=matches[0].id, right=matches[1].id,
                on=", ".join(f"{k}={v}" for k, v in disclosed.items()),
                question=("Two threads on this file carry the same number of "
                          "record. Are they one dispute? I will not merge them "
                          "myself — a wrong merge inverts the advice invisibly.")),
            question=("Two threads on this file carry the same number of record. "
                      "Are they one dispute?"))

    # 3. A NEW decisive identifier: a new thread, stated as such.
    if disclosed and matter.threads:
        return BindResult(
            BindState.BOUND,
            _with_identifiers(Thread.create(label=_label(message)), disclosed),
            True,
            f"a number of record not on any existing thread "
            f"({', '.join(f'{k}={v}' for k, v in disclosed.items())}): opening a "
            f"new thread rather than attaching it to an existing one")

    # 4. Nothing on the file yet.
    if not matter.threads:
        return BindResult(
            BindState.BOUND,
            _with_identifiers(Thread.create(label=_label(message)), disclosed),
            True, "the first thread on this matter")

    # 5. ONE OPEN THREAD AND NOTHING DECISIVE. Not automatically a
    #    continuation -- that was the defect. `opens_new_dispute` is read
    #    by the engine and passed in; this module stays pure.
    if len(matter.threads) == 1:
        if opens_new_dispute is True:
            # STATED, not silent. `created=True` puts it on the board where
            # the advocate can see the split and say if it is wrong -- and
            # a wrong split is the recoverable direction.
            return BindResult(
                BindState.BOUND,
                _with_identifiers(Thread.create(label=_label(message)),
                                  disclosed),
                True,
                "this describes a different dispute from the one on the "
                "file, so it opens its own thread rather than inheriting "
                "that thread's posture and limitation")
        if opens_new_dispute is False:
            return BindResult(BindState.BOUND, matter.threads[0], False,
                              "the only thread on this matter, continued")
        # NOT ASSESSED. The read did not run or could not tell, and the
        # asymmetry forbids defaulting to the merge: ask, exactly as rule 6
        # does when several threads are open.
        return BindResult(
            BindState.AMBIGUOUS, None, False,
            "one open thread, no number of record, and it could not be "
            "told whether this continues it",
            question=(
                f"Does this belong to {matter.threads[0].label!r}, or is it "
                f"a separate dispute? I will not assume it is the same one: "
                f"attaching it to the wrong thread puts the wrong posture "
                f"and the wrong limitation on it, and every citation would "
                f"still be correct."))

    # 6. Several threads and nothing decisive. THE QUESTION IS THE ANSWER.
    labels = "; ".join(f"{t.label!r}" for t in matter.threads[:5])
    return BindResult(
        BindState.AMBIGUOUS, None, False,
        f"{len(matter.threads)} open threads and no number of record in the message",
        question=(
            f"Which thread does this belong to — {labels}? I will not guess from "
            f"the wording: two disputes between the same parties are the ordinary "
            f"case, and attaching facts to the wrong one puts the wrong posture "
            f"and the wrong limitation on them."))


def _with_identifiers(thread: Thread, disclosed: dict[str, str]) -> Thread:
    """Identifiers accumulate; they are never overwritten.

    A second FIR number on a thread that already has one is new information
    about the dispute, not a correction of the first -- and silently replacing
    it would lose the link to everything filed under the old number.
    """
    if not disclosed:
        return thread
    merged = dict(thread.identifiers)
    for k, v in disclosed.items():
        merged.setdefault(k, v)
    if merged == thread.identifiers:
        return thread
    return Thread(
        id=thread.id, label=thread.label, aliases=thread.aliases,
        identifiers=merged, posture=thread.posture, chronology=thread.chronology,
        deferred_reason=thread.deferred_reason)


def _label(message: str) -> str:
    """A display name. It is NEVER an identity.

    `Thread.create` generates the id independently, so a label collision costs
    nothing and a label change loses nothing.
    """
    first = (message or "").strip().split("\n")[0]
    ids = identifiers_in(message)
    if ids:
        return f"{next(iter(ids.values()))} — {first[:36]}".strip()
    return first[:48] or "Thread"
