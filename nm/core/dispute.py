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

import re
from dataclasses import dataclass
from enum import Enum

from nm.domain.text import refuses_blank_text

_WORDS = re.compile(r"[a-z0-9]+")


def _fold(text: str) -> str:
    return " ".join(_WORDS.findall((text or "").lower()))


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
    },
    "required": ["verdict", "quoted", "why"],
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
    "they know."
)


@refuses_blank_text("quoted", "why")
@dataclass(frozen=True)
class DisputeRead:
    verdict: Dispute
    quoted: str = ""
    why: str = ""
    refused: str | None = None

    @property
    def opens(self) -> bool:
        return self.verdict is Dispute.OPENS

    @property
    def continues(self) -> bool:
        return self.verdict is Dispute.CONTINUES


UNREAD = DisputeRead(Dispute.CANNOT_TELL, why="the dispute read did not run")


def build_prompt(message: str, on_file: str):
    """What is on the file, and what was just said."""
    from nm.ports.model import Prompt

    return Prompt(
        system=SYSTEM,
        user=(f"Already on the file:\n{on_file.strip()[:2000]}\n\n"
              f"The advocate has just said:\n{message.strip()[:1200]}\n\n"
              f"Does this continue that dispute, or open a different one?"))


def interpret(message: str, data: dict) -> DisputeRead:
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

    if verdict is not Dispute.OPENS:
        return DisputeRead(verdict, quoted, why)

    # OPENING A THREAD IS THE ANSWER THAT CREATES SOMETHING, so it carries the
    # evidence. `continues` and `cannot_tell` both leave the file as it was.
    if not quoted:
        return DisputeRead(Dispute.CANNOT_TELL, why=why,
                           refused="the model said this opens a new dispute and "
                                   "quoted nothing to support it")
    if _fold(quoted) not in _fold(message):
        # The span must be the ADVOCATE'S words. Checked against the message
        # rather than the prompt: the prompt carries the file, and a span
        # lifted from there would let an old dispute open a new thread.
        return DisputeRead(Dispute.CANNOT_TELL, quoted, why,
                           refused=f"the quoted span is not in what the advocate "
                                   f"just wrote: {quoted[:60]!r}")
    return DisputeRead(Dispute.OPENS, quoted, why)
