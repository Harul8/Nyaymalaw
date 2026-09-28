"""The note under a reply: what this message changed on the board. LB-90, F-C-04.

Owner, 28 September 2026: "for every message, we need to also extract updates /
changes to be done to the matter board."

WHAT THE SAVED FILE GAINED, NEVER WHAT A READ CLAIMED
-----------------------------------------------------
Every applied line is computed from the file before the message and the file
about to be saved -- the same bytes the board is read from -- so the note can
never report a change the board does not show. Lines about what NM noticed and
did NOT apply (a withdrawal, a party removed or moved) are proposals: they
change nothing until the advocate confirms, and a target that cannot be
matched EXACTLY to one entry or one party is said to be unmatched rather than
guessed (CLAUDE.md §5: matching may rank, never identify).
"""
from __future__ import annotations

from nm.advise.answer_contracts import BoardChange
from nm.shared.text_contracts import snippet
from nm.work_the_file.matter_contracts import Matter

#: More dated entries than this are summarised as a count on one line.
DATED_LINES = 6

_SIDE = {"client": "our side", "adverse": "the other side", "related": "related parties"}
_KEPT_AS = {"hypothetical": "a hypothetical", "question": "a question",
            "others_allegation": "the other side's allegation"}


def _label(thread) -> str:
    return snippet(thread.label, 60) or "this dispute"


def _quoted(text: str, cap: int = 70) -> str:
    return f"“{snippet(text, cap)}”"


def applied(before: Matter, after: Matter) -> tuple[BoardChange, ...]:
    """What the file gained between the two versions. Pure."""
    out: list[BoardChange] = []
    old_threads = {t.id: t for t in before.threads}
    old_facts = {f.id: f for f in before.facts}
    facts = {f.id: f for f in after.facts}

    for thread in after.threads:
        if thread.id not in old_threads:
            out.append(BoardChange("dispute_opened", f"Dispute opened: {_label(thread)}."))

    # CORRECTIONS: an entry this message superseded, and what replaced it.
    replacements: set[str] = set()
    for fact in after.facts:
        was = old_facts.get(fact.id)
        if was is None or was.superseded_by is not None or fact.superseded_by is None:
            continue
        new = facts.get(fact.superseded_by)
        if new is None:
            continue
        replacements.add(new.id)
        where = next((t for t in after.threads if new.id in t.chronology), None)
        old_date = f" ({was.date.isoformat()})" if was.date else ""
        new_date = f" ({new.date.isoformat()})" if new.date else ""
        out.append(BoardChange(
            "corrected",
            (f"Corrected{' on ' + _label(where) if where else ''}: {_quoted(was.statement)}"
             f"{old_date} is replaced by {_quoted(new.statement)}{new_date}."),
            target=new.id, was=was.statement,
            was_date=was.date.isoformat() if was.date else ""))

    dated: list[BoardChange] = []
    for thread in after.threads:
        earlier = old_threads.get(thread.id)
        seen = set(earlier.chronology) if earlier is not None else set()
        new_ids = [i for i in thread.chronology if i not in seen and i in facts
                   and i not in old_facts and i not in replacements]
        undated = [i for i in new_ids if facts[i].date is None]
        for ident in new_ids:
            fact = facts[ident]
            if fact.date is not None:
                dated.append(BoardChange(
                    "dated_event",
                    f"{_label(thread)}: {_quoted(fact.statement, 60)} dated "
                    f"{fact.date.isoformat()}."))
        if undated:
            out.append(BoardChange(
                "statements_added",
                f"{_label(thread)}: {len(undated)} of your statement"
                f"{'s' if len(undated) != 1 else ''} added."))
        if earlier is not None:
            answered = [k for k, v in thread.requirement_outcomes.items()
                        if earlier.requirement_outcomes.get(k) != v]
            if answered:
                out.append(BoardChange(
                    "question_answered",
                    f"{_label(thread)}: {len(answered)} checklist item"
                    f"{'s' if len(answered) != 1 else ''} answered from your message."))
        was = earlier.posture if earlier is not None else None
        now = thread.posture
        if now.resolved and (was is None or not was.resolved or was.role != now.role):
            inferred = getattr(now.basis, "value", "") == "inferred"
            out.append(BoardChange(
                "side_recorded",
                f"{_label(thread)}: our client recorded as "
                f"{now.role.value.replace('_', ' ')}"
                f"{' (worked out from your words; say if wrong)' if inferred else ''}."))
        if now.opponent and (was is None or was.opponent != now.opponent):
            out.append(BoardChange(
                "side_recorded", f"{_label(thread)}: the other side recorded as "
                                 f"{snippet(now.opponent, 60)}."))
    if len(dated) > DATED_LINES:
        dated = [*dated[:DATED_LINES], BoardChange(
            "dated_event", f"and {len(dated) - DATED_LINES} more dated entries.")]
    out.extend(dated)

    parties_before = {str(n).casefold() for n in (before.intake_parties or {})}
    for name, side in (after.intake_parties or {}).items():
        if str(name).casefold() not in parties_before:
            out.append(BoardChange(
                "party_added", f"Party added: {snippet(name, 60)} ({_SIDE.get(side, side)})."))
    return tuple(out)


def kept_apart(statements) -> tuple[BoardChange, ...]:
    """Parts of the message recorded as the advocate's words and NOT as facts."""
    return tuple(BoardChange(
        "kept_apart",
        f"Kept as {_KEPT_AS[s.taken_as]}, not as a fact: {_quoted(s.quoted)}.")
        for s in statements if s.taken_as in _KEPT_AS)


def proposed(after: Matter, removals, *, new_fact_ids=frozenset()) -> tuple[BoardChange, ...]:
    """Removals and moves NM noticed and did not apply. EXACT matching only."""
    out: list[BoardChange] = []
    parties = {str(n).casefold(): str(n) for n in (after.intake_parties or {})}
    for removal in removals:
        target = removal.target.strip()
        if removal.kind == "withdraw_entry":
            # BOARD ENTRIES ONLY: an entry read out of an account carries the
            # span it was read from. The account itself is the advocate's words,
            # kept whole (C1), and is never offered for withdrawal -- it would
            # contain every sentence and match everything.
            live = [f for f in after.facts if f.superseded_by is None
                    and f.provenance.span and f.id not in new_fact_ids
                    and (target in f.statement or f.statement in target)]
            if len(live) == 1:
                out.append(BoardChange(
                    "proposed_withdrawal",
                    f"You asked to withdraw {_quoted(live[0].statement)}. It stays on the "
                    f"file until you confirm.", target=live[0].id))
            else:
                out.append(BoardChange(
                    "unmatched_request",
                    f"You asked to withdraw {_quoted(target)}, but I could not tell which "
                    f"entry that is, so nothing was withdrawn. Correct it from the case file."))
            continue
        name = parties.get(target.casefold())
        if name is None:
            out.append(BoardChange(
                "unmatched_request",
                f"{snippet(target, 60)} is not among the parties on this matter, so nothing "
                f"was changed. Use the edit button on the matter board."))
        elif removal.kind == "remove_party":
            out.append(BoardChange(
                "proposed_party_removal",
                f"Remove {snippet(name, 60)} from the parties? Nothing changes until you "
                f"confirm; the history keeps the change.", target=name))
        elif removal.side in _SIDE and after.intake_parties.get(name) != removal.side:
            out.append(BoardChange(
                "proposed_party_move",
                f"Move {snippet(name, 60)} to {_SIDE[removal.side]}? Nothing changes until "
                f"you confirm; the history keeps the change.", target=name,
                value=removal.side))
    return tuple(out)


def held(title: str) -> BoardChange:
    """The one line on a message kept off a file it may not belong to."""
    return BoardChange(
        "held_other_matter",
        f"Nothing from this message was added to {snippet(title, 60) or 'this matter'}.")
