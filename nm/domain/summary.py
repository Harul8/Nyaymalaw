"""The matter's memory: what is established, what was asked, what is open.

WHY THIS EXISTS
---------------
An advocate briefs a matter once. They say who the client is, what happened,
when, and under what number — and they expect the file to hold it. A product
that asks again has not merely been inefficient; it has told them their
instructions were not recorded, and they stop volunteering detail.

That failure was measured, not imagined. Six golden scenarios run end to end
found the product asking *"whose side are we on?"* on consecutive turns of
GS-08 after the advocate had answered it, because the posture read saw only the
latest message and six persisted fields were being dropped on every restart.
Both were fixed. Neither fix stopped the general case, which is that EVERY
prompt in this product was built from `turn.message` alone.

A PROJECTION, NOT A SECOND STORE
--------------------------------
`MatterSummary` holds NOTHING the matter does not already hold, and it is
rebuilt from the matter on every turn. That is the same rule the two boards
follow and for the same reason: a summary that can disagree with the file is
worse than no summary, because the advocate cannot tell which one is stale.

The one piece of genuinely new state — `AskedQuestion` — therefore lives on the
`Matter` itself, in `nm.domain.matter`, and is persisted with it.

WHAT IT IS FOR
--------------
`as_context()` is the block handed to every model call the turn makes: the
posture read, the retrieval, the recommendation. Before this, each of them was
shown the latest message and nothing else, so the product could only ever know
what had been said in the last thirty seconds.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.domain.matter import AskedQuestion, Matter, Role, Thread
from nm.domain.text import refuses_blank_text

#: How much of the account a prompt is given. Enough to carry a matter's worth
#: of instruction, bounded so a long file cannot crowd out the current message.
ACCOUNT_BUDGET = 3000

#: Room kept for the line that says what was left out.
_NOTE_RESERVE = 110

#: What THIS type carries of the Appendix E `CaseSummary` contract.
#:
#: `CaseSummary` is the G3 HANDOVER summary -- complete enough that another
#: advocate can take the file over from it alone. Sixteen sections, and most
#: of them are issues, theory, proof, deadlines and decisions, which are
#: slices 4 to 9. What exists after S3 is the conversational subset.
#:
#: Naming what is carried, rather than what is missing, is deliberate: a
#: list of gaps has to be maintained as slices land and will silently stop
#: being true. This one only shrinks the blockers when a section is
#: genuinely added here.
CARRIES = frozenset({"matter", "threads", "posture", "chronology"})

#: The full contract, from Appendix E. `tests/test_produces_contracts.py`
#: asserts this equals `spec/schemas.yaml`, so the two cannot drift -- the
#: same arrangement as the gate matrix, where the code is the source and
#: the spec is the export.
CASE_SUMMARY_SECTIONS = (
    "matter", "engagement", "screens", "threads", "posture",
    "chronology", "issues", "theory", "proof", "authorities",
    "deadlines", "decisions", "reservations", "gaps",
    "handover_complete", "handover_blockers",
)


@refuses_blank_text("account")
@dataclass(frozen=True)
class MatterSummary:
    """What the file holds, as one readable thing. Rebuilt, never stored."""

    matter_id: str
    title: str
    threads: tuple[dict, ...] = ()
    established: tuple[str, ...] = ()
    account: str = ""
    left_out: int = 0
    """How many facts did not fit the budget. NOT a flag: a reader who is told
    something was trimmed learns that a boundary exists, and a reader told
    `left_out=7` learns how much of the file they are not looking at."""
    open_questions: tuple[AskedQuestion, ...] = ()
    answered: tuple[AskedQuestion, ...] = ()
    facts_recorded: int = 0
    turns: int = 0

    @property
    def handover_blockers(self) -> tuple[str, ...]:
        """What stops this standing alone as a handover. NEVER an empty list.

        Appendix E requires the claim to be COMPUTED rather than assumed,
        and this is why: a receiving advocate reading a summary with no
        proof positions cannot tell whether there are none or whether the
        section was never built. Those are opposite situations and the
        second one is the dangerous one.
        """
        derived = {"handover_complete", "handover_blockers"}
        return tuple(s for s in CASE_SUMMARY_SECTIONS
                     if s not in CARRIES and s not in derived)

    @property
    def handover_complete(self) -> bool:
        """Derived, never asserted. False while any section is unbuilt."""
        return not self.handover_blockers

    @property
    def advocate_words(self) -> str:
        """ONLY what the advocate wrote. Never a line this product composed.

        `as_context()` is the PROMPT and rightly carries our own questions --
        a model that cannot see what is already outstanding will ask it
        again. This is the GUARD INPUT, and the two must never be the same
        string.

        They were, for about ten minutes. The posture extractor read "we act
        for the party moving" out of our own blocking question, the verbatim
        guard confirmed the span was present -- because it was, in OUR text --
        and the product settled a posture nobody had stated. C3 was defeated
        by widening an input, not by a bad inference.
        """
        return self.account

    @property
    def empty(self) -> bool:
        return not (self.established or self.account or self.asked_anything)

    @property
    def asked_anything(self) -> bool:
        return bool(self.open_questions or self.answered)

    def as_context(self) -> str:
        """The file, written for a model prompt.

        This is what stops the product re-asking. It is given to every
        extraction and every derivation, so nothing already established has to
        be said twice by the person who already said it.
        """
        blocks: list[str] = []
        if self.account:
            blocks.append("WHAT THE ADVOCATE HAS ALREADY TOLD ME ON THIS "
                          "MATTER:\n" + self.account)
        if self.established:
            blocks.append("ALREADY ESTABLISHED — do not ask for any of this "
                          "again:\n"
                          + "\n".join(f"  - {e}" for e in self.established))
        if self.answered:
            blocks.append(
                "ALREADY ASKED AND ANSWERED — these are settled:\n"
                + "\n".join(f"  - {q.text[:160]}" for q in self.answered))
        if self.open_questions:
            lines = []
            for q in self.open_questions:
                seen = (f" (asked {q.times_asked} times already, still not "
                        f"answered)" if q.ignored else "")
                lines.append(f"  - {q.text[:160]}{seen}")
            blocks.append("ASKED AND STILL OPEN:\n" + "\n".join(lines))
        return "\n\n".join(blocks)

    def as_dict(self) -> dict:
        return {
            "state": "ok",
            "matter_id": self.matter_id,
            "title": self.title,
            "threads": list(self.threads),
            "established": list(self.established),
            "open_questions": [
                {"gate": q.gate, "text": q.text, "asked_on": q.asked_on,
                 "thread": q.thread, "times_asked": q.times_asked,
                 "ignored": q.ignored}
                for q in self.open_questions],
            "answered": [
                {"gate": q.gate, "text": q.text, "asked_on": q.asked_on,
                 "thread": q.thread, "answered_by": q.answered_by}
                for q in self.answered],
            "facts_recorded": self.facts_recorded,
            "turns": self.turns,
            # THE PART OF THE CONTRACT THIS DOES NOT YET CARRY, named.
            # `CaseSummary` is the G3 handover summary and most of it is
            # slices 4 to 9. Shipping the conversational subset under that
            # name with the rest merely absent is defect shape S1: the
            # receiving advocate cannot tell an empty section from an
            # unbuilt one.
            "contract": "CaseSummary (Appendix E), partial",
            "handover_complete": self.handover_complete,
            "handover_blockers": list(self.handover_blockers),
            # The same discipline the boards carry: a projection states what
            # bounds it, so it cannot quietly start scaling on the wrong axis.
            "bounded_by": "thread_count + fact_count",
        }


def _established_on(thread: Thread) -> list[str]:
    """What this thread has SETTLED — never what it has merely been told.

    A line here means "you do not need to ask this". Anything provisional
    belongs in the account, where the model can weigh it, rather than here,
    where it reads as decided.
    """
    out: list[str] = []
    p = thread.posture
    if p.role is not Role.UNKNOWN:
        out.append(
            f"On {thread.label!r}: we act for the {p.role.value} — the "
            f"{p.side.value} party ({p.basis.value})."
            + (f" Against: {p.opponent}." if p.opponent else ""))
    elif p.client_described_as:
        # NOT the same as knowing the posture, and the distinction is the whole
        # of C3: naming the client does not say which side they are on. Recorded
        # so the blocking question can NARROW instead of repeating.
        out.append(
            f"On {thread.label!r}: the client is the {p.client_described_as}. "
            f"Their procedural role is NOT yet settled.")
    for kind, value in sorted(thread.identifiers.items()):
        out.append(f"On {thread.label!r}: {kind.replace('_', ' ')} is {value}.")
    if thread.deferred_reason:
        out.append(f"On {thread.label!r}: deferred — {thread.deferred_reason}.")
    return out


def build(matter: Matter, thread_id: str | None = None,
          about: str = "", load_bearing: frozenset[str] = frozenset(),
          ) -> MatterSummary:
    """Rebuild the summary from the matter. Nothing is stored twice.

    `thread_id` narrows the ACCOUNT to one dispute while leaving what is
    established across the whole matter. A matter's threads are separate
    disputes — that is what a thread is — so feeding one thread's narrative
    into another's derivation is the wrong-merge defect arriving by way of a
    prompt instead of by way of a binding.
    """
    established: list[str] = []
    threads: list[dict] = []

    for t in matter.threads:
        threads.append({
            "thread_id": t.id,
            "thread": t.label,
            "our_client_is": t.posture.role.value,
            "side": t.posture.side.value,
            "client_described_as": t.posture.client_described_as,
            "identifiers": dict(t.identifiers),
            "facts": len(t.chronology),
        })
        established.extend(_established_on(t))

    thread = matter.thread(thread_id) if thread_id else None
    in_scope = set(thread.chronology) if thread is not None else None

    on_thread = [f for f in matter.facts
                 if in_scope is None or f.id in in_scope]
    for f in on_thread:
        if f.date:
            established.append(f"{f.date.isoformat()}: {f.statement.strip()[:120]}")

    account, left_out = _account(on_thread, thread, about, load_bearing)

    return MatterSummary(
        matter_id=matter.id,
        title=matter.title,
        threads=tuple(threads),
        established=tuple(dict.fromkeys(established)),
        account=account,
        left_out=left_out,
        open_questions=tuple(q for q in matter.asked if q.open),
        answered=tuple(q for q in matter.asked if not q.open),
        facts_recorded=len(matter.facts),
        turns=len(matter.turns_applied),
    )


def unbuildable(reason: str) -> dict:
    """A summary that could not be built is an EXPLICIT FAILURE.

    Never an empty one. An empty summary tells the advocate the file holds
    nothing, and the product would then re-ask everything it had ever been
    told — defect shape S1, with the whole conversation as the blast radius.
    """
    return {"state": "unbuildable", "reason": reason, "established": [],
            "open_questions": [], "answered": []}


def _account(facts: list, thread, about: str,
             load_bearing: frozenset[str]) -> tuple[str, int]:
    """The account, SELECTED to fit. Returns it and how much did not.

    PINNED FIRST, and this is the half that makes truncation safe:

      * every DATED fact, because the chronology is what the arithmetic reads
        and a date dropped from the account is a date the next read cannot see;
      * the fact the POSTURE rests on, because losing it re-opens a question
        the advocate has already answered;
      * every fact a LIVE DERIVATION named in `from_facts` — the product knows
        which facts it actually used, so it can refuse to forget those.

    Then the rest, ranked against what this turn is about. Ranking is fuzzy
    and identifies nothing: the worst case is a less useful sentence carried
    instead of a more useful one, and both are still on the file.
    """
    pinned, rest = [], []
    source = getattr(getattr(thread, "posture", None), "source_fact", None)

    # THE LATEST STATEMENT IS PINNED, and it is not pinned for being recent.
    # It is what this turn is ABOUT: dropping it is the failure that looks
    # most like the product ignoring the advocate, and selection by relevance
    # would have dropped it on a matter with nothing to rank against.
    latest = facts[-1].id if facts else None

    for f in facts:
        if (f.date is not None or f.id in load_bearing
                or f.id == source or f.id == latest):
            pinned.append(f)
        else:
            rest.append(f)

    def line(f) -> str:
        stamp = f"[{f.date.isoformat()}] " if f.date else ""
        return f"{stamp}{f.statement.strip()}"

    kept = [line(f) for f in pinned]
    # THE NOTE COUNTS AGAINST THE BUDGET, because it is sent to the model like
    # everything else. Appending it after the check made the account exceed
    # the budget by exactly the length of the sentence explaining that it had
    # been kept within the budget.
    used = sum(len(x) + 1 for x in kept) + _NOTE_RESERVE

    # THE PINNED SET ALONE CAN EXCEED THE BUDGET on a long matter, and it is
    # still carried. Dropping a dated fact to respect a character count would
    # trade a number the advocate acts on for a number nobody chose.
    for f in _ranked(rest, about):
        text = line(f)
        if used + len(text) + 1 > ACCOUNT_BUDGET and kept:
            break
        kept.append(text)
        used += len(text) + 1

    left_out = len(facts) - len(kept)
    account = "\n".join(kept)
    if left_out > 0:
        account += (f"\n[{left_out} earlier statement(s) are on the file and "
                    f"not repeated here. Every dated event is above.]")
    return account, max(left_out, 0)


def _ranked(facts: list, about: str) -> list:
    """Undated facts, most relevant to THIS turn first.

    Overlap on content words. It is a weak signal and it is the right KIND of
    signal: it decides what to carry, never what is true, and everything it
    ranks down is still on the file and still retrievable next turn.

    With nothing to rank against, the order is the order they arrived — which
    is the honest default, not a judgement nobody made.
    """
    words = {w for w in _words(about) if len(w) > 3}
    if not words:
        return facts
    return sorted(facts,
                  key=lambda f: -len(words & set(_words(f.statement))))


def _words(text: str) -> set[str]:
    import re
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))
