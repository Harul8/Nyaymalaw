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
from dataclasses import dataclass, replace
from enum import Enum

from nm.shared.spoken_contracts import dispute
from nm.shared.text_contracts import refuses_blank_text, snippet
from nm.shared.traceability_contracts import implements
from nm.work_the_file.matter_contracts import Fact, Matter, Thread

from .dispute import source_units

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


@dataclass(frozen=True)
class SourceAllocation:
    """One labelled source-unit occurrence, before it becomes a charted fact.

    The words alone cannot identify the source: the same sentence may occur on
    this turn and in an earlier account still awaiting placement.
    """

    unit_id: str
    text: str
    origin_turn: str


@refuses_blank_text("question", "reason")
@dataclass(frozen=True)
class BindResult:
    state: BindState
    thread: Thread | None
    created: bool
    reason: str
    proposal: MergeProposal | None = None
    question: str = ""
    counted: bool = False
    looks_like: int = 0
    """HOW MANY DISPUTES THE MESSAGE APPEARED TO DESCRIBE.

    A reported count alone creates nothing. Only validated source-span
    allocations create separate working disputes; the count is diagnostic."""
    """Did anything actually COUNT the disputes in this message?

    False means the read did not run, and the single thread below is a
    fallback rather than a finding. Without this, one thread from a failed
    read is indistinguishable from one thread from a message that really
    described one dispute."""

    others: tuple[Thread, ...] = ()
    """Other working disputes inventoried by this turn, not yet advised on."""
    allocations: tuple[tuple[str, tuple[str, ...]], ...] = ()
    """Current-message spans scoped to dispute IDs, never a copied mixed brief."""
    source_allocations: tuple[tuple[str, tuple[SourceAllocation, ...]], ...] = ()
    """The same allocation by source occurrence, with the turn that actually
    supplied each unit. String allocations remain for existing consumers."""
    links: tuple[tuple[str, str, str], ...] = ()
    """Disputes of this message that are LINKED -- (dispute, other, how): the
    same opponent, the same events. Shown to the advocate; never a merge."""
    doubts: tuple[str, ...] = ()
    """Where a second reading separated the message differently. Said and
    asked, never resolved silently."""

    @property
    def blocks(self) -> bool:
        return self.state is not BindState.BOUND


def _source_index(message: str, accounts: tuple[tuple[str, str], ...]
                  ) -> dict[str, SourceAllocation] | None:
    """Bind prompt unit IDs to the original accounts, without matching text."""
    if not accounts or any(not turn or not isinstance(words, str) or not words.strip()
                           for turn, words in accounts):
        return None
    if "\n".join(words for _, words in accounts) != message:
        return None
    index = {}
    for turn, words in accounts:
        for text in source_units(words).values():
            unit_id = f"S{len(index) + 1}"
            index[unit_id] = SourceAllocation(unit_id, text, turn)
    if [row.text for row in index.values()] != list(source_units(message).values()):
        return None
    return index


def _allocated_sources(described, index: dict[str, SourceAllocation]
                       ) -> tuple[SourceAllocation, ...] | None:
    """Resolve occurrence IDs; permit legacy text only when it is unique."""
    ids = tuple(getattr(described, "allocation_unit_ids", ()) or ())
    if ids:
        if len(ids) != len(set(ids)) or any(unit_id not in index for unit_id in ids):
            return None
        sources = tuple(index[unit_id] for unit_id in ids)
        if {source.text for source in sources} != set(described.spans):
            return None
        return sources
    sources = []
    for span in described.spans:
        matches = [row for row in index.values() if row.text == span]
        if len(matches) != 1:
            return None
        sources.append(matches[0])
    return tuple(sources)


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
         opens_new_dispute: bool | None = None, described: tuple = (),
         source_accounts: tuple[tuple[str, str], ...] | None = None) -> BindResult:
    """Bind an account to exactly one thread, or refuse and ask.

    `thread_hint` is the advocate saying which thread they mean. It outranks
    everything else, because the only source better than a registry number is
    the person holding the file.
    """
    disclosed = identifiers_in(message)
    source_index = (_source_index(message, source_accounts)
                    if source_accounts is not None else None)
    if source_accounts is not None and source_index is None:
        return BindResult(BindState.UNBINDABLE, None, False,
                          "source accounts do not match the message being bound",
                          question="I could not reliably place the source accounts. "
                                   "Which dispute should I work on?")

    # Successful source-bound inventory: keep each working dispute visible.
    # The model proposes organisation, not factual truth or legal completion.
    # Validate again at this boundary so a caller cannot bypass interpret().
    if described:
        if any(not d.quoted or any(s not in message for s in d.spans)
               or (d.thread_id and matter.thread(d.thread_id) is None)
               for d in described):
            return BindResult(BindState.UNBINDABLE, None, False,
                              "dispute allocation is not source-bound",
                              question=("I could not reliably place these instructions. "
                                        "Which dispute should I work on?"))
        if (matter.threads and any(not d.thread_id for d in described)
                and opens_new_dispute is not True):
            # Legacy single-dispute reads may continue the sole record, but
            # cannot spawn duplicates from a clarification.
            if len(matter.threads) == 1 and opens_new_dispute is False and len(described) == 1:
                described = (replace(described[0], thread_id=matter.threads[0].id),)
            else:
                proposed = "; ".join(d.label for d in described if not d.thread_id)
                return BindResult(BindState.AMBIGUOUS, None, False,
                                  "existing and new disputes were not distinguished",
                                  question=(f"Should I add these as separate disputes: {proposed}? "
                                            "Or do they belong to an existing dispute? "
                                            "I have kept your instructions; those additions "
                                            "have not been recorded as separate disputes yet."))
        made, allocations, source_allocations, order = {}, {}, {}, []
        for d in described:
            sources = _allocated_sources(d, source_index) if source_index is not None else ()
            if sources is None:
                return BindResult(BindState.UNBINDABLE, None, False,
                                  "dispute allocation does not identify its source occurrence",
                                  question="I could not reliably place these instructions "
                                           "on their original turns. Which dispute "
                                           "should I work on?")
            thread = (matter.thread(d.thread_id) if d.thread_id
                      else Thread.create(label=_dispute_label(d)))
            opponent = getattr(d, "opponent", "")
            if not d.thread_id and opponent and not thread.posture.opponent:
                # THE OPPONENT THE ADVOCATE NAMED FOR THIS DISPUTE, recorded when
                # the dispute is opened. Only on a new record: an existing
                # dispute's opponent changes by express correction, never here.
                thread = replace(thread, posture=replace(thread.posture, opponent=opponent))
            thread = _with_identifiers(thread, identifiers_in("\n".join(d.spans)))
            made[thread.id] = thread
            order.append(thread.id)
            allocations[thread.id] = tuple(dict.fromkeys(
                (*allocations.get(thread.id, ()), *d.spans)))
            if source_index is not None:
                source_allocations[thread.id] = tuple(dict.fromkeys(
                    (*source_allocations.get(thread.id, ()), *sources)))
        links = tuple((order[i], order[j], how) for i, d in enumerate(described)
                      for j, how in getattr(d, "related", ()) if j < len(order))
        if thread_hint and thread_hint not in made:
            target = matter.thread(thread_hint)
            if target is None:
                return BindResult(BindState.UNBINDABLE, None, False,
                                  "selected dispute is not on this matter",
                                  question=("That dispute is not on this matter. "
                                            "Please select it again."))
            made[target.id], allocations[target.id] = target, ()
            if source_index is not None:
                source_allocations[target.id] = ()
        active = made[thread_hint] if thread_hint else next(iter(made.values()))
        return BindResult(BindState.BOUND, active, matter.thread(active.id) is None,
                          "instructions allocated to source-bound working disputes",
                          looks_like=len(made),
                          others=tuple(t for t in made.values() if t.id != active.id),
                          allocations=tuple(allocations.items()),
                          source_allocations=tuple(source_allocations.items()), links=links)

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

    # 4. Nothing on the file yet -- ONE THREAD PER DISPUTE DESCRIBED.
    #
    # This returned exactly one thread however many disputes the message
    # carried, and the engine did not even run the read, on the reasoning
    # that with no thread yet there is nothing to confuse it with. There
    # is: the disputes inside the message, with each other. A brief
    # opening `first ... second ... third ...` is how a file is handed
    # over, and it produced one thread with one posture across all three.
    if not matter.threads:
        made = _per_dispute(message, described, disclosed)
        return BindResult(
            BindState.BOUND, made[0], True,
            ("the first thread on this matter" if len(made) == 1 else
             f"this message appears to describe {len(described)} disputes; "
             f"it is on one thread until you say otherwise"),
            looks_like=len(described))

    # 5. ONE OPEN THREAD AND NOTHING DECISIVE. Not automatically a
    #    continuation -- that was the defect. `opens_new_dispute` is read
    #    by the engine and passed in; this module stays pure.
    if len(matter.threads) == 1:
        if opens_new_dispute is True:
            # STATED, not silent. `created=True` puts it on the board where
            # the advocate can see the split and say if it is wrong -- and
            # a wrong split is the recoverable direction.
            # THE SAME COUNT APPLIES HERE. A later message can open two
            # disputes as easily as the first one can, and splitting only
            # the first would leave the second welded to it -- the very
            # merge this branch exists to avoid.
            made = _per_dispute(message, described, disclosed)
            return BindResult(
                BindState.BOUND, made[0], True,
                ("this describes a different dispute from the one on the "
                 "file, so it opens its own thread rather than inheriting "
                 "that thread's posture and limitation" if len(made) == 1
                 else f"this appears to describe {len(described)} disputes, "
                      f"none of them the one on the file; it opens one "
                      f"thread until you say otherwise"),
                looks_like=len(described))
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
                f"Does this belong to {dispute(matter.threads[0].label)}, or is it "
                f"a separate dispute? I will not assume it is the same one: "
                f"attaching it to the wrong thread puts the wrong posture "
                f"and the wrong limitation on it, and every citation would "
                f"still be correct."))

    # 6. Several threads and nothing decisive. THE QUESTION IS THE ANSWER.
    labels = "; ".join(dispute(t.label) for t in matter.threads[:5])
    return BindResult(
        BindState.AMBIGUOUS, None, False,
        f"{len(matter.threads)} open threads and no number of record in the message",
        question=(
            f"I have not reliably placed this update. Does it concern {labels}? "
            "You can also select the dispute on the board. Your instructions are saved."))



def _per_dispute(message: str, described: tuple,
                 disclosed: dict[str, str]) -> list[Thread]:
    """ONE thread, whatever the count says. The count is DISCLOSED.

    This used to return one thread per dispute the read described, and the
    read is not good enough to act on: 3/6, 2/6, 2/6 across six briefs,
    unstable on identical input, and blind to a four-dispute enumeration.

    `threading.py`\'s asymmetry justified splitting on the ground that a
    wrong merge inverts the advice SILENTLY. It is not silent now -- the
    engine states the count and invites the advocate to separate the file
    -- and a wrong split costs more than the docstring assumed: three
    threads, three posture gates, and a cross-file pass arguing across
    fragments of one transaction.

    THE LABEL STILL COMES FROM THE READ where there is one, because a
    thread called after the first dispute is better than one called after
    the opening words of the brief -- which is how a three-dispute file
    came to be filed under `My client is Ravi Kumar, a retired bank
    employee`.
    """
    label = _dispute_label(described[0]) if described else _label(message)
    return [_with_identifiers(Thread.create(label=label), disclosed)]

def _dispute_label(d) -> str:
    """A file-cover name for one dispute.

    The read supplies one; the quoted span is the fallback, because a
    label the model left blank must not produce a blank thread label --
    `Thread.create` would refuse it and the turn would fail on a read
    that was otherwise fine.
    """
    label = (getattr(d, "label", "") or "").strip()
    if label:
        # Room for "<client> v. <opponent> -- <thing fought over>" (LB-109).
        return snippet(label, 120)
    return snippet(getattr(d, "quoted", ""), 80) or "a dispute"

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
    return replace(thread, identifiers=merged)


def _label(message: str) -> str:
    """A display name. It is NEVER an identity.

    `Thread.create` generates the id independently, so a label collision costs
    nothing and a label change loses nothing.
    """
    first = (message or "").strip().split("\n")[0]
    ids = identifiers_in(message)
    if ids:
        return f"{next(iter(ids.values()))} — {snippet(first, 36)}".strip()
    return snippet(first, 48) or "Thread"
