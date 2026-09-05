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

from nm.domain.matter import AskedQuestion, Certainty, FactBasis, Matter, Role, Thread
from nm.domain.text import refuses_blank_text

#: How much of the account a prompt is given. Enough to carry a matter's worth
#: of instruction, bounded so a long file cannot crowd out the current message.
ACCOUNT_BUDGET = 3000

#: Room kept for the lines this product appends to the account: what was left
#: out, and whether any basis was assessed.
#:
#: BOTH ARE RESERVED, because both are appended AFTER the fitting loop and a
#: note that is not reserved for is a note that breaks the budget. That is not
#: hypothetical -- the left-out note did it once, and the basis note did it
#: again the day it was added (3065 characters against a 3000 budget). The
#: reserve is the mechanism; adding an unreserved note is the way past it.
_NOTE_RESERVE = 110 + 100

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
    words: str = ""
    """The advocate's own sentences, and NOTHING this product composed.

    Separate from `account` on purpose -- see `advocate_words`, which is the
    guard input for every verbatim check and must never widen when the
    account does.
    """
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

        AND AGAIN, ON 5 SEPTEMBER 2026, WHICH IS WHY THIS IS NO LONGER THE
        ACCOUNT. This returned `self.account`, which was safe only while the
        account held nothing but the advocate's sentences. Three changes in
        one day put our own words in it -- a document name, a basis marker,
        and a note reading "How the client KNOWS any of this has not been
        assessed". `_FIRST_PERSON` matches `client`, so
        `speaks_of_the_representation` became true on EVERY matter and a
        COMPLAINANT posture was settled out of "a cheque was dishonoured on 3
        March".

        It is now built from the facts' statements alone, apart from the
        account, so the two cannot drift back together.
        """
        return self.words

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
            # THE HEADING NAMES A SOURCE, so it must be true of every line
            # under it. It said "WHAT THE ADVOCATE HAS ALREADY TOLD ME" while
            # document-sourced facts sat beneath it unmarked -- a heading that
            # is wrong about provenance is worse than none, because a reader
            # who trusts it stops looking.
            blocks.append("WHAT IS ON THIS MATTER — the advocate's own words "
                          "unless a source is named:\n" + self.account)
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
            + (f" Against: {p.opponent}." if p.opponent else "")
            # THE ADVOCATE'S OWN WORD FOR THEIR CLIENT, kept once the role is
            # known rather than dropped. B-094: it was rendered only on the
            # `role is UNKNOWN` branch, so the moment the role settled, "the
            # workman" or "the wife" left the file note for good. It is not a
            # role and never was -- it is who the client IS, it costs a dozen
            # characters ONCE per thread rather than per fact, and a product
            # that stops using the advocate's own word for their client is
            # one they have to keep re-introducing.
            + (f" Our client is {p.client_described_as}."
               if p.client_described_as else ""))

    # THE POSTURE IS CONTESTED, AND THE MODEL WAS NEVER TOLD.
    #
    # B-096, found by the enumerator in test_what_the_model_is_told. The board
    # rendered `loud` and `conflict` from `posture.conflicts` and the ACCOUNT
    # said nothing, so the advocate saw a warning while every derivation on
    # the same turn reasoned as though the side were settled -- and the side
    # is the one thing in this product that reverses the advice rather than
    # weakening it.
    #
    # Stated as an instruction, not as a field. A model told `conflicts: 1`
    # has a number; a model told which two roles are in dispute and that it
    # must not pick one has something it can act on.
    elif p.client_described_as:
        # NOT the same as knowing the posture, and the distinction is the whole
        # of C3: naming the client does not say which side they are on. Recorded
        # so the blocking question can NARROW instead of repeating.
        out.append(
            f"On {thread.label!r}: the client is the {p.client_described_as}. "
            f"Their procedural role is NOT yet settled.")
    for c in p.conflicts:
        out.append(
            f"On {thread.label!r}: THE SIDE IS IN DISPUTE. The file records "
            f"our client as the {c.on_record.value}; this turn reads as the "
            f"{c.now_suggested.value}. Do not choose between them — say what "
            f"holds either way, and ask.")
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

    account, left_out, words = _account(
        on_thread, thread, about, load_bearing)

    return MatterSummary(
        matter_id=matter.id,
        title=matter.title,
        threads=tuple(threads),
        established=tuple(dict.fromkeys(established)),
        account=account,
        words=words,
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


def _source(f) -> str:
    """WHERE THIS CAME FROM, where it is not the advocate's own word.

    Measured on the bytes, 5 September 2026: the file note was BYTE-IDENTICAL
    for a fact the advocate stated and the same fact read off page 3 of a sale
    deed -- under a heading that says "WHAT THE ADVOCATE HAS ALREADY TOLD ME".
    A document's content was handed to every extraction and every derivation
    labelled as the advocate's claim.

    Those are opposite things. A claim is what the client says happened; a
    document is what will be put to a court, and the whole of the product's
    grounding posture rests on the difference. The model could not see it.

    NOT REACHING AN ADVOCATE YET -- `nm.core.intake` is unwired, so no
    document facts exist. Fixed now precisely because of that: once intake
    lands, this failure is silent, and the first person to notice would be
    someone relying on a "documented" fact that was never in a document.

    An advocate statement carries no prefix. Adding one would put four words
    on every line of every account to say the ordinary thing, and the budget
    those words come out of is measured in facts that then do not fit.
    """
    prov = getattr(f, "provenance", None)
    if prov is None or getattr(prov, "kind", "") != "document":
        return ""
    where = prov.document or "a document"
    page = f" p.{prov.page}" if prov.page else ""
    return f"{where}{page}: "


def _marks(f) -> str:
    """WHAT THE FILE KNOWS ABOUT THIS FACT beyond the words of it.

    B-094. Measured on 5 September 2026: of 29 scalars on the persisted
    record, SEVEN reached the model. Six of the rest were held and never told,
    and this renders the two that change the advice.

    BASIS, because its own docstring says why -- "the difference decides what
    has to be proved and by whom". "He never paid me" resting on direct
    knowledge and the same sentence resting on belief are different cases, and
    a model given only the sentence cannot tell them apart. `basis_source`
    travels with it for the reason a page number travels with a document: it
    is what makes the claim checkable rather than merely asserted.

    CERTAINTY, AND IT IS NOT WHAT `_source` ALREADY RENDERS. `_source` says
    the product read this off a document it holds; `documented` says the
    ADVOCATE says a document evidences it. For a limitation those are
    different facts -- a date on a registered deed and a date the client
    remembers are not the same date, and the arithmetic is identical either
    way while the risk is not.

    WHAT IS DELIBERATELY WITHHELD is declared in
    tests/test_what_the_model_is_told.py rather than decided here, because a
    field left out silently and a field left out on purpose look identical
    from inside this function.

    ONLY THE NON-DEFAULT VALUE IS MARKED, the same rule as `_source`. Marking
    the ordinary case spends a measured budget saying the ordinary thing.
    """
    marks: list[str] = []
    if f.certainty is Certainty.DOCUMENTED:
        marks.append("advocate says documented")
    if f.basis is not FactBasis.NOT_ASSESSED:
        basis = f.basis.value.replace("_", " ")
        if (f.basis_source or "").strip():
            basis += f" - {f.basis_source.strip()}"
        marks.append(basis)
    return f" ({'; '.join(marks)})" if marks else ""


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
        return f"{stamp}{_source(f)}{f.statement.strip()}{_marks(f)}"

    kept = [line(f) for f in pinned]
    #: The FACTS behind the rendered lines. `kept` holds strings that carry
    #: this product's own words; the guard input is built from these.
    shown: list = list(pinned)
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
        shown.append(f)
        used += len(text) + 1

    left_out = len(facts) - len(kept)
    account = "\n".join(kept)

    # THE THIRD STATE, SAID ONCE AND NOT FIFTEEN TIMES.
    #
    # `not_assessed` is the honest answer when no basis read has run, and a
    # third state that is invisible is the S8 shape -- the model reads every
    # unmarked line as ordinary rather than as ungraded. Marking each fact
    # would spend roughly 240 characters of a 3000-character budget repeating
    # one sentence, and those characters are paid for in facts that then do
    # not fit. So it is stated once, about the file.
    if kept and not any(f.basis is not FactBasis.NOT_ASSESSED for f in facts):
        account += ("\n[How the client KNOWS any of this has not been "
                    "assessed. Nothing above is marked for basis.]")
    if left_out > 0:
        account += (f"\n[{left_out} earlier statement(s) are on the file and "
                    f"not repeated here. Every dated event is above.]")

    # THE GUARD INPUT, BUILT APART AND FROM THE STATEMENTS ALONE.
    #
    # `advocate_words` used to return the account, which was safe only while
    # the account was nothing but what the advocate wrote. It stopped being
    # that: `_source` prefixes a document name (B-093), `_marks` appends a
    # basis (B-094), and the two notes above are whole sentences this product
    # composed.
    #
    # THE COST OF GETTING THIS WRONG HAS NOW BEEN PAID TWICE. The first time,
    # the posture extractor read "we act for the party moving" out of OUR OWN
    # blocking question and the verbatim guard confirmed the span -- because
    # it was there, in our text. The second time was this very change: the
    # note above reads "How the client KNOWS any of this has not been
    # assessed", `_FIRST_PERSON` matches the word `client`, and
    # `speaks_of_the_representation` became TRUE ON EVERY MATTER. A posture of
    # COMPLAINANT was then settled out of "a cheque was dishonoured on 3
    # March" -- C3 exactly, the reinstatement defect, reached by widening an
    # input rather than by a bad inference.
    #
    # Rewording the note would have fixed this note. Building the two strings
    # apart fixes the next one.
    words = "\n".join(f.statement.strip() for f in shown)
    return account, max(left_out, 0), words


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
