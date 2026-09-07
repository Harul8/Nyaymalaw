"""Does this message continue the dispute on the file, or open another one?

WHY THIS EXISTS
---------------
`nm/core/threading.py` could only ever create a second thread when the advocate
supplied a NUMBER OF RECORD. With one thread on the file and no case number in
the message, rule 5 bound to it and called that a continuation — *"there is
nothing to be wrong about"*.

There is. Measured, on a matter driven three turns:

    a cheque complaint filed against him   -> he is the ACCUSED
    a Labour Court claim by a fitter       -> he is the RESPONDENT EMPLOYER
    his own recovery suit for 11 lakhs     -> he is the PLAINTIFF

One thread. `role=accused, side=defending`. The product would advise his own
recovery suit as though he were defending it — which is the measured original
defect, arriving through the binder instead of through the posture reader.

And it was unreachable any other way: since only an identifier could open a
second thread, a matter could not hold two disputes unless the advocate typed a
case number. The golden set calls multi-thread files *the normal case*.

THE ASYMMETRY DECIDES THE DEFAULT, and `threading.py` states it at the top of
its own docstring: a wrong SPLIT duplicates work, is visible, and is corrected
in a turn. A wrong MERGE attaches one thread's posture, chronology and
limitation to facts they do not govern, every citation stays correct, the board
looks tidier, and the advice inverts silently.

So this never guesses toward merging. Three answers, and the third is not a
failure state:

    CONTINUES    bind, as before
    OPENS        a new thread, stated so the advocate can correct it
    CANNOT TELL  ASK — which is what rule 6 already does when several threads
                 are open and nothing is decisive. The question is the answer.

WHAT KEEPS IT HONEST
--------------------
The same two guards the posture read uses, for the same reason. The model must
QUOTE the words that make this a different dispute, and the span is checked
against what the ADVOCATE wrote — never against the prompt, which carries this
product's own questions and would otherwise let it quote itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.quotable import Quotable
from nm.domain.text import refuses_blank_text


class Dispute(str, Enum):
    """THREE STATES. The third is what makes the other two safe to act on."""

    CONTINUES = "continues"
    OPENS = "opens"
    CANNOT_TELL = "cannot_tell"


DISPUTE_SCHEMA: dict = {
    "x-nm-read": "dispute",
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": [d.value for d in Dispute],
            "description": "'continues' if this message adds to the dispute "
                           "already on the file. 'opens' if it describes a "
                           "DIFFERENT dispute — a different proceeding, a "
                           "different opponent, or a different subject matter. "
                           "'cannot_tell' if it genuinely could be either.",
        },
        "quoted": {
            "type": "string",
            "description": "For 'opens', the EXACT words from the message that "
                           "show this is a different dispute. Must appear "
                           "verbatim. Empty for the other answers.",
        },
        "why": {
            "type": "string",
            "description": "One clause. Shown to the advocate so they can "
                           "correct it.",
        },
        # HOW MANY, NOT WHETHER. `verdict` answers a question that only
        # exists once the file holds something: does this add to THAT
        # dispute. On the first turn there is no THAT, so the read was
        # never made -- and one thread was created however many disputes
        # the advocate had just described.
        #
        # A brief that opens `first ... second ... third ...` is the
        # ordinary way a file is handed over, not an edge case.
        "disputes": {
            "type": "array",
            "description": "EVERY distinct dispute this message describes, "
                           "in the order they appear. A different "
                           "proceeding, a different opponent or a different "
                           "subject matter is a different dispute. One item "
                           "is the ordinary answer. Return an EMPTY array "
                           "if the message adds detail to something already "
                           "on the file rather than describing a dispute of "
                           "its own.",
            "items": {
                "type": "object",
                "properties": {
                    "quoted": {
                        "type": "string",
                        "description": "The EXACT words from the message "
                                       "that describe THIS dispute. Must "
                                       "appear verbatim.",
                    },
                    "label": {
                        "type": "string",
                        "description": "A few words naming it, as an "
                                       "advocate would on a file cover.",
                    },
                },
                "required": ["quoted", "label"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "quoted", "why", "disputes"],
    # STRICT MODE REQUIRES IT. Without `additionalProperties: false` on
    # every object the provider cannot compile the grammar, and the
    # schema silently degrades to a hint.
    "additionalProperties": False,
}

SYSTEM = (
    "An Indian advocate is briefing a matter. You are told what is already on "
    "the file and what they have just said. Decide ONE thing: does the new "
    "message add to the dispute already on the file, or does it describe a "
    "DIFFERENT dispute?\n\n"
    "A different dispute means a different proceeding, a different opponent, "
    "or a different subject matter. One client commonly has several at once — "
    "a cheque case against him, a labour claim by an employee, a tenancy he is "
    "defending, and a recovery suit he has filed himself are FOUR disputes, "
    "not one matter with four facts.\n\n"
    "Adding detail to what is already there — a date, a name, a document, an "
    "answer to a question — CONTINUES. So does asking what to do about it.\n\n"
    "Answer 'cannot_tell' where it genuinely could be either. That is a real "
    "answer and it is better than a wrong one: the advocate will be asked, and "
    "they know.\n\n"
    "SECOND, AND IT IS A DIFFERENT QUESTION: list every distinct dispute "
    "THIS MESSAGE ITSELF describes, whatever you answered above. Do not "
    "compare it to the file for this part -- there may not be a file yet. "
    "Read the message on its own.\n\n"
    "An advocate handing over a file commonly describes several disputes "
    "at once, and marks them off: first this, second that, third the "
    "other. Each has its own opponent, its own dates and its own posture, "
    "and each must be listed separately. A message describing three "
    "disputes gets THREE entries.\n\n"
    "Quote the advocate's OWN WORDS for each -- copy the span out of the "
    "message exactly. A paraphrase is discarded.\n\n"
    "Return an empty list ONLY where the message describes no dispute of "
    "its own: a date, a name, a document, or an answer to a question."
)


@refuses_blank_text("quoted", "label")
@dataclass(frozen=True)
class Described:
    """One dispute a message describes, in the advocate's own words."""

    quoted: str
    label: str


@refuses_blank_text("quoted", "why")
@dataclass(frozen=True)
class DisputeRead:
    verdict: Dispute
    quoted: str = ""
    why: str = ""
    refused: str | None = None
    described: tuple[Described, ...] = ()
    """EVERY dispute this message describes, each carrying the words it was
    read from.

    EMPTY IS NOT THE SAME AS ZERO DISPUTES. It is what a read that did not
    run leaves behind, and also what an ordinary continuing message
    produces. The caller separates them by asking whether the read RAN --
    never by the length of this tuple. S1: an absent input must not read
    as a finding."""

    @property
    def opens(self) -> bool:
        return self.verdict is Dispute.OPENS

    @property
    def continues(self) -> bool:
        return self.verdict is Dispute.CONTINUES


UNREAD = DisputeRead(Dispute.CANNOT_TELL, why="the dispute read did not run")


def build_prompt(quotable: Quotable):
    """What is on the file, and what was just said.

    THE FILE IS CONTEXT AND THE MESSAGE IS THE EVIDENCE (B-108). Opening a
    thread is the answer that creates something, so it carries a quotation --
    and a span lifted out of the file would let an old dispute open a new
    thread. The guard has always said so; the prompt now does too.
    """
    from nm.ports.model import Prompt

    # BOTH QUESTIONS ARE ASKED, and the closing line is the last thing the
    # model reads. It used to close on the binary one alone -- "does this
    # continue that dispute, or open a different one?" -- and against the
    # brief that found BK-27 the model answered exactly that and returned
    # an EMPTY list of disputes. The schema and the system text both
    # described the second question; nothing at the point of asking did.
    return Prompt(
        system=SYSTEM,
        user=(f"{quotable.block()}\n\n"
              f"1. Does this continue the dispute already on the file, or "
              f"open a different one? (If there is no file yet, answer "
              f"cannot_tell.)\n"
              f"2. How many distinct disputes does this message itself "
              f"describe? List each one with the advocate's own words."))


def interpret(quotable: Quotable, data: dict) -> DisputeRead:
    """Turn the model's answer into a verdict, or REFUSE it.

    A refusal lands on CANNOT_TELL, never on CONTINUES. Falling back to
    "continues" would make every failed read a silent merge, which is the
    defect this module exists to close.
    """
    if not isinstance(data, dict):
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused="the dispute read returned nothing usable")

    raw = (data.get("verdict") or "").strip().lower()
    try:
        verdict = Dispute(raw)
    except ValueError:
        return DisputeRead(Dispute.CANNOT_TELL,
                           refused=f"the model answered {raw!r}, which is not "
                                   f"an answer to this question")

    why = (data.get("why") or "").strip()
    quoted = (data.get("quoted") or "").strip()

    # THE COUNT IS READ ON EVERY VERDICT, because the two answers are
    # about different things: `verdict` is this message against the FILE,
    # `described` is this message against ITSELF. A brief that opens three
    # disputes on an empty matter has no verdict worth having and three
    # threads to create.
    described = _described(quotable, data)

    if verdict is not Dispute.OPENS:
        return DisputeRead(verdict, quoted, why, described=described)

    # OPENING A THREAD IS THE ANSWER THAT CREATES SOMETHING, so it carries the
    # evidence. `continues` and `cannot_tell` both leave the file as it was.
    if not quotable.accepts(quoted):
        # The span must be the ADVOCATE'S words. The file is CONTEXT on this
        # read and not quotable, because a span lifted from there would let an
        # old dispute open a new thread.
        return DisputeRead(Dispute.CANNOT_TELL, quoted, why,
                           refused=(f"the model said this opens a new dispute "
                                    f"and {quotable.refusal(quoted)}"))
    return DisputeRead(Dispute.OPENS, quoted, why, described=described)


def _described(quotable: Quotable, data: dict) -> tuple[Described, ...]:
    """The disputes the message describes, each checked against the
    advocate's own words.

    THE SAME GUARD AS THE SINGULAR ANSWER, applied per item and for the
    same reason: a span the advocate did not write settles nothing, and a
    span lifted out of the file would let an old dispute open a new
    thread. An item that fails the guard is DROPPED rather than kept with
    a warning -- a thread is created from these, and a thread created
    from words nobody wrote is worse than one not created.
    """
    rows = data.get("disputes")
    if not isinstance(rows, list):
        return ()
    out: list[Described] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        span = (row.get("quoted") or "").strip()
        label = (row.get("label") or "").strip()
        if not span or not label or not quotable.accepts(span):
            continue
        out.append(Described(span, label))
    return tuple(out)
