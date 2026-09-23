"""G-CONSISTENT — the step must not contradict what the same answer computed.

THE DEFECT, AND WHY TELLING THE MODEL DID NOT FIX IT
------------------------------------------------------
Measured on a served turn, 31 August 2026 (B-074): the ACTION read *"file the
recovery suit, ensuring it is within the limitation period"* while the GROUND
directly below it read *"that period has run"* — 174 days ago. On the next
turn the step told the advocate to *"calculate the limitation period and
determine if the claim is still within time"*, which is the calculation the
product had just done and printed underneath.

Nothing was wrong with either component. The limitation was computed correctly
and the step was composed correctly GIVEN WHAT IT WAS TOLD. The fix applied
then was to TELL THE MODEL what had been worked out — the `ALREADY WORKED OUT`
block in `_recommend`, which is long, specific and correct.

IT RECURRED ANYWAY, and BK-35 recorded the recurrence on `6e29cf0`: the action
said *"Confirm the date of service and file within the window"* while its own
deadline annotation said every deadline had passed. The prompt expressly
forbade that output.

    A PROMPT IS NOT A GUARD. It is an instruction that is usually followed,
    and "usually" is the whole problem: the turns where it is not followed are
    exactly the turns nobody is watching.

So the check is here, after the sentence exists, comparing it against the
TYPED FACTS rather than against the instruction that was supposed to produce
it. That is the same move `backend/nm/core/accrual.py` makes and for the same reason.

WHY THERE IS NO PHRASE LIST, AND CANNOT BE
--------------------------------------------
The obvious implementation is a list of forbidden phrases — *within the
limitation period*, *calculate whether*, *file in time*. It was rejected on
the standing decision that a scenario-specific list can never be complete, and
the measurement behind that decision is in CLAUDE.md §5: matching on words
picked the wrong Act three times in one hour.

Instead the ANSWER SPACE IS BUILT FROM THE TURN'S OWN TYPED FACTS. `claims_for`
renders each computed fact as one sentence with a stable id, and the read is
asked which of THOSE the step contradicts. The vocabulary is therefore closed,
generated per turn, and the guard is exact membership — the same single `in`
the accrual read uses, and for the same reason: an id that is not on the list
names nothing, and no reading of the prose would make it name something.

A new typed fact means a new claim builder, not a new phrase. And nothing has
to anticipate how a sentence might go wrong, which is what a phrase list is
really trying and failing to do.

THREE STATES, AND THE THIRD IS SERVED DIFFERENTLY
---------------------------------------------------
`consistent`, `contradicted`, and `not_verified` for the case where the read
could not run. The third does NOT block: the step is served exactly as it was
before this module existed, carrying a disclosure that it was not checked. A
check that cannot run must not silently become a check that passed (defect
shape S1) — and it must not become a refusal either, because that would make
an unavailable model delete the advice on a turn where nothing is wrong.

WHICH DIRECTION IT FAILS
--------------------------
Toward SERVING THE TYPED POSITION. Where the step cannot be made consistent,
the advocate gets the computed facts and a question, not a sentence that
disagrees with the figures printed beside it. The typed facts are the part
that was verified; the sentence is the part that was generated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nm.core import deadlines, limitation
from nm.domain.text import fold, refuses_blank_text, snippet


@refuses_blank_text()
@dataclass(frozen=True)
class Claim:
    """One typed fact the step is not allowed to contradict.

    NEITHER FIELD MAY BE BLANK, and that is not tidiness. A claim with an
    empty `id` can never be named by the read, and one with an empty
    `sentence` is offered to it carrying nothing — either way the fact is on
    the list and cannot be matched against, so the step passes a check that
    silently had one fewer subject than it says it does.

    A SENTENCE AND A STABLE ID. The sentence is what the read is shown, so it
    has to say the fact in the words an advocate would; the id is what the
    read answers with, so it has to be exact and closed. Splitting them is
    what lets the guard be a membership test rather than a comparison of
    prose against prose.
    """

    id: str
    sentence: str


@refuses_blank_text("why")
@dataclass(frozen=True)
class Verdict:
    """Whether the step contradicts a computed fact, and which.

    `ran` IS NOT `contradicted is False`. A read that could not run has found
    nothing, and so has a read that ran and found nothing — the same value
    for opposite facts is the defect this repository has recorded in four
    separate controls, so the two are kept apart at the type.
    """

    claim_id: str = ""
    quoted: str = ""
    why: str = ""
    ran: bool = True
    refused: str | None = None

    @property
    def contradicted(self) -> bool:
        return bool(self.claim_id)

    @property
    def state(self) -> str:
        """The gate state, so no call site decides it from the fields."""
        if not self.ran:
            return "not_verified"
        return "contradicted" if self.contradicted else "consistent"


#: What a read that could not run leaves behind. NOT a clean verdict.
UNVERIFIED = Verdict(ran=False, why="the consistency read did not run")

#: The OTHER way a step goes unverified: nothing was computed to check it
#: against. Same state, different fact, and the difference is the whole reason
#: `ran` exists -- an advocate reading the trace can tell a broken check from
#: a turn that had nothing to check.
NOTHING_TO_CHECK = Verdict(
    ran=False, why="nothing was computed on this turn for the step to contradict")


CONSISTENCY_SCHEMA: dict = {
    "x-nm-read": "consistency",
    "type": "object",
    "properties": {
        "claim_id": {
            "type": "string",
            "description": (
                "The id of the ONE computed fact the step contradicts, copied "
                "exactly from the list. EMPTY if the step contradicts none of "
                "them, which is the ordinary answer."),
        },
        "quoted": {
            "type": "string",
            "description": (
                "The words OF THE STEP that carry the contradiction, copied "
                "exactly from it. Empty when there is no contradiction."),
        },
        "why": {
            "type": "string",
            "description": (
                "One clause saying what the step asserts and what the computed "
                "fact says instead. Shown to the advocate."),
        },
    },
    "required": ["claim_id", "quoted", "why"],
    "additionalProperties": False,
}

SYSTEM = (
    "Below is a proposed answer or next step written for an Indian advocate, and the "
    "facts this same answer has already COMPUTED and will print beside it.\n\n"
    "Say whether the step CONTRADICTS one of those computed facts.\n\n"
    "A CONTRADICTION IS THE STEP ASSERTING, ASSUMING OR DIRECTING SOMETHING "
    "THE COMPUTED FACT RULES OUT. Check the direction of the act, identity, "
    "time and conditional premises against the recorded computation. A request "
    "to recheck a computation for a stated material reason is not a contradiction.\n\n"
    "An instruction to investigate an unresolved question is not an assertion "
    "that it has already been resolved. Preserve the distinction between a "
    "proposed examination, a conditional hypothesis and an established result.\n\n"
    "Explaining a rule or its trigger is not asserting that its factual premises "
    "have been satisfied. Unknown is not false: a missing computed date does not "
    "contradict an explanation of which event would be needed to compute it. "
    "Identify incompatible assertions about the SAME subject and status; mere "
    "mention of limitation, a date, a weakness or an opponent is not contradiction.\n\n"
    "Accurately describing an opponent's contention, testing an adverse fact, or "
    "acknowledging weakness in our client's case is not advising the opponent. "
    "Independent assessment must be able to do all three. A side contradiction "
    "requires actually misidentifying whom we represent or directing the wrong "
    "party's action, not merely discussing material that may hurt our client.\n\n"
    "IT IS NOT A CONTRADICTION FOR THE STEP TO BE ABOUT SOMETHING ELSE. Most "
    "steps do not assert the truth or effect of a computed fact. Such a step does not "
    "contradict it, and answering with an empty `claim_id` is the ordinary "
    "and expected answer.\n\n"
    "NOR IS IT A CONTRADICTION FOR THE STEP TO BE INCOMPLETE, cautious, or "
    "differently worded. You are not judging whether it is the best step. "
    "Only whether it says something the computed facts say is false.\n\n"
    "QUOTE THE WORDS OF THE STEP that carry it, exactly. If you cannot quote "
    "them from the step, there is no contradiction to report."
)


def claims_for(position, register, side: str, today: date,
               chronology: tuple = (), relief_position=None) -> tuple[Claim, ...]:
    """The computed facts of this turn, as sentences with ids. ONE OWNER.

    THE POPULATION IS THE TYPED FACTS, and this is the only place that turns
    one into a claim. A second builder somewhere else would be a second answer
    to *what did this turn compute*, which is S9 — and it is the specific
    version of S9 that produced the defect: `_recommend`'s prose is informed
    by `position` while its by-when annotation comes from `register`, two
    computations of the same subject that were never reconciled.

    ONLY WHAT WAS ACTUALLY ESTABLISHED BECOMES A CLAIM, and `not computed` is
    itself established: a step that tells the advocate to file within a window
    nothing computed is contradicting a real fact about this turn, and that is
    exactly the case BK-35 recorded.

    RELIEF IS THE NEWEST SUCH FACT (BK-70). A step that recommends pursuing a
    remedy the file has established is unavailable, hollow, late or
    unenforceable -- with the merits unchanged -- contradicts a computed fact
    exactly as one that files within a window that has run does. It comes in as
    a `ReliefPosition` and becomes a claim here, in the ONE owner, rather than
    as a second consistency check beside this one. The reservation the step is
    allowed to make is written into the sentence, so acknowledging the
    shortfall is not a contradiction while pursuing it silently is.
    """
    out: list[Claim] = []

    if position is not None:
        state = position.state
        if state is limitation.LimitationState.COMPUTED:
            gone = position.expired(today)
            when = position.expires_on.isoformat()
            out.append(Claim(
                "limitation",
                (f"The limitation period on {position.article} has been "
                 f"COMPUTED and expired on {when}, which has already passed."
                 if gone else
                 f"The limitation period on {position.article} has been "
                 f"COMPUTED and expires on {when}, which is still open.")))
            # THE THREAD'S OWN ENTRIES, not an empty tuple. Passing ()
            # would make this claim never appear and the check would
            # silently cover one fact fewer than it says it does --
            # which is S11: a check that cannot fail.
            missed = position.accounts_for_every_entry(chronology)
            if missed:
                out.append(Claim(
                    "unweighed",
                    f"{len(missed)} thing(s) on this file have NOT been "
                    f"weighed against that period. Whether any of them "
                    f"restarts, extends or fails to restart it is NOT "
                    f"computed."))
        elif state is limitation.LimitationState.NOT_APPLICABLE:
            out.append(Claim(
                "limitation",
                "No limitation period runs against this party on this thread, "
                "because they have brought no claim. This is a finding, not a "
                "gap."))
        else:
            out.append(Claim(
                "limitation",
                f"NO limitation period has been computed on this thread: "
                f"{position.why_not_computed}. Whether a window is open or "
                "closed is NOT ESTABLISHED. This does not prevent explaining a "
                "retrieved rule or investigating its missing premises."))

    if register is None:
        out.append(Claim(
            "register",
            "NO deadline register was computed on this turn. Nothing is known "
            "about what is due or when."))
    else:
        live = deadlines.upcoming(register, today)
        gone = deadlines.passed(register, today)
        if live:
            out.append(Claim(
                "register",
                f"The nearest deadline still open is {live[0].on.isoformat()} "
                f"— {live[0].action}."))
        elif gone:
            out.append(Claim(
                "register",
                f"EVERY deadline on this thread has PASSED. The nearest was "
                f"{gone[0].on.isoformat()}. There is no open window."))
        else:
            out.append(Claim(
                "register",
                "The register holds no deadline with an established date on "
                "this thread, so no by-when can be stated."))

    if side:
        out.append(Claim(
            "side",
            f"The represented party is the {side} party. This records client identity, "
            "not the strength of that party's case. A weak claim, an adverse admission, "
            "a possible concession or an unfavourable assessment can all be compatible "
            "with representing that party. Only a changed represented identity or "
            "directing an act for the other party contradicts this identity."))

    # RELIEF (BK-70). Built by its own owner and wrapped here so `consistency`
    # need not import `relief` at module load (the pair would import each
    # other). Each pair is (id, sentence) and becomes a Claim, so the relief
    # facts sit in exactly the same closed vocabulary the read is asked about.
    if relief_position is not None:
        from nm.core import relief as _relief
        for cid, sentence in _relief.consistency_claims(relief_position):
            out.append(Claim(cid, sentence))

    return tuple(out)


def build_prompt(step: str, claims: tuple[Claim, ...], file_note: str = ""):
    """The step, the computed facts it must not contradict, and the file.

    THE FILE IS CARRIED, and E-036 is why: no prompt in this product is built
    from the latest message alone. That rule is stated over ALL prompts rather
    than the ones that existed when it was written, precisely so a read added
    in a later slice fails it the day it is written — and this one did.

    It is also right on the merits rather than merely required. B-074's second
    instance was a step telling the advocate to *calculate the limitation
    period* they had already been given, which is a step contradicting what
    the FILE holds and not only what the figures say. A read shown the
    computed facts alone cannot see that.

    THE FILE IS CONTEXT AND NOT THE SUBJECT, which the prompt says out loud.
    Judging the step against the brief rather than against the computed facts
    would widen this into a quality review of the advice — a different job,
    with no typed answer to check it against.
    """
    from nm.ports.model import Prompt

    rows = "\n".join(f"  {c.id}\t{c.sentence}" for c in claims)
    file_block = (
        f"\n\nTHE FILE SO FAR, as context only — you are not judging the step "
        f"against it, and a step that is merely incomplete about the file is "
        f"NOT a contradiction:\n{file_note}" if file_note.strip() else "")
    return Prompt(
        system=SYSTEM,
        user=(f"THE COMPUTED FACTS:\n{rows or '  (none)'}{file_block}\n\n"
              f"THE STEP:\n{step}\n\n"
              f"Which computed fact does the step contradict, if any?"))


def repair_prompt(step: str, claim: Claim, why: str, file_note: str = ""):
    """ONE rewrite, told exactly what was wrong. Not a second guess.

    THE REPAIR IS NARROW ON PURPOSE. It is handed the contradiction that was
    found and asked for the same step without it — not asked to write a better
    step, which would put the whole recommendation back in the hands of the
    thing that just got it wrong. If the rewrite still contradicts, the step
    is not served; there is no third attempt, because a second failure is
    evidence about the step rather than about the wording.
    """
    from nm.ports.model import Prompt

    return Prompt(
        system=(
            "Rewrite one next step for an Indian advocate so that it no longer "
            "contradicts a fact that has already been computed.\n\n"
            "KEEP THE STEP. Same action and subject, stated concisely with "
            "all material qualifications retained. You are removing a "
            "contradiction, not inventing a different course or legal premise.\n\n"
            "If no supported repair of this step is possible from the supplied "
            "record, return an empty answer so the step can be withheld.\n\n"
            "Name NO section, article or rule number."),
        user=(f"THE COMPUTED FACT:\n{claim.sentence}\n\n"
              # THE FILE, for the same reason the verification carries it
              # (E-036): a rewrite built from one sentence re-asks what the
              # advocate already said. It is what makes the rewrite specific
              # rather than a hedged version of the same step.
              + (f"THE FILE SO FAR:\n{file_note}\n\n"
                 if file_note.strip() else "")
              + f"THE STEP AS WRITTEN:\n{step}\n\n"
              f"WHAT IS WRONG WITH IT:\n{why}\n\n"
              f"The corrected step:"))


def interpret(data: dict, step: str, offered: frozenset[str]) -> Verdict:
    """The read's answer, checked against the claims actually offered.

    TWO GUARDS, AND BOTH FAIL TOWARD `CONSISTENT`.

    The first is exact membership on the claim id — the answer space is this
    turn's own claims, a closed set built a few lines earlier, so an id that
    is not in it names nothing (CLAUDE.md §5's easiest case: an exact key
    exists, so nothing is ranked).

    The second is that the quoted words must be IN THE STEP. A contradiction
    nobody can point at is not one the advocate could check, and it is the
    shape a model produces when it is asked a yes/no question and would
    rather say yes.

    BOTH FAILING TOWARD `consistent` IS THE DELIBERATE DIRECTION, and it is
    the opposite of the accrual read's. There, refusing costs a date and buys
    safety. Here, refusing DELETES THE ADVICE — so a guard that failed toward
    blocking would let a confused read silence a correct step, and the
    advocate would have no way to tell that from a step that was never
    written. The refusal is recorded either way, so a read that keeps failing
    its own guards is visible rather than merely tolerated.
    """
    if not isinstance(data, dict):
        return Verdict(why="the consistency read returned nothing usable",
                       refused="the consistency read returned nothing usable")

    claim_id = (data.get("claim_id") or "").strip()
    quoted = (data.get("quoted") or "").strip()
    why = snippet(data.get("why"), 240)

    if not claim_id:
        return Verdict(why=why or "the step contradicts none of the computed facts")

    if claim_id not in offered:
        return Verdict(
            why=why or "the read named a fact that was not offered",
            refused=(f"the consistency read named {claim_id!r}, which is not "
                     f"one of the computed facts it was shown"))

    # AN EMPTY QUOTATION POINTS AT NOTHING. It used to pass the check below,
    # because the empty string is inside every step: measured 23 September
    # 2026, two live verdicts named `limitation`, quoted nothing, and withheld
    # the step -- one whose own reason read "the step does not assert anything
    # about a limitation period". The rule above is that a contradiction
    # nobody can point at is not one; this is the case it did not reach.
    if not fold(quoted):
        return Verdict(
            why=why or "the read named a fact but pointed at nothing in the step",
            refused=(f"the consistency read named {claim_id!r} and quoted nothing "
                     f"from the step"))

    held = fold(step)
    if not held or fold(quoted) not in held:
        return Verdict(
            why=why or "the read could not point at the contradiction",
            refused=(f"the consistency read quoted {snippet(quoted, 60)!r}, which is "
                     f"not in the step it was shown"))

    return Verdict(claim_id=claim_id, quoted=quoted,
                   why=why or "the step contradicts a computed fact")
