"""What cause of action is this? PRD §4.2, control H3.

THE QUESTION THIS ANSWERS, AND WHY A MODEL ASKS IT
----------------------------------------------------
`nm/Archives/legal_brain/retrieve/resolution_sources.py` turns a cause of action into the Article that
governs it, exactly, by lookup. That graph is useless until something can say
which cause the advocate is describing, and the advocate never says it in those
words. They say *"the goods were supplied against invoices dated 14 March 2023
and nothing was paid"*.

Two ways to bridge that, and this project has already measured both.

A PHRASE LIST WAS TRIED AND IT FAILED. Ten exact phrases meant "we act for the
workman", and an advocate whose wording was missing was asked the same question
forever. Lengthening the list is not a repair — the eleventh phrasing is always
outside it. The Act keyword list is the same mechanism and it failed the same
way on 31 August 2026: the Limitation Act is held in full, its keywords are
`limitation`, `time-barred`, `acknowledgment`, and *"is the claim still in
time"* matched none of them (B-065).

A MODEL READ WITH GUARDS WAS TRIED AND IT WORKED. That is what replaced the
posture phrase list, and this module is deliberately built to the same shape,
importing that module's own verbatim guard rather than carrying a second copy
of it.

WHAT THE GUARDS REFUSE
-----------------------
1. A cause outside the CLOSED vocabulary is blanked, never accepted. An
   out-of-vocabulary value that gets through becomes a routing decision nobody
   curated (B-042, B-055).
2. A span the advocate did not write settles nothing. The model is shown this
   product's own questions along with the advocate's words, and a guard that
   checked the span against everything the model saw once let the extractor
   quote us back to ourselves. SINCE 30 SEPTEMBER 2026 (LB-76 change 2) the read
   points at the advocate's sentences by NUMBER instead of retyping them: on the
   Farah Begum brief it named the right cause for all three disputes and every
   one was refused, because the retyped quote joined non-adjacent sentences and
   once garbled the rupee sign. A number cannot drift, and a number that is not
   one of the advocate's sentences is refused all the same.
3. A cause is always INFERRED and always disclosed. Nobody states a cause of
   action; it is worked out, and a worked-out routing decision the advocate
   cannot see is one they cannot correct.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from nm.Archives.legal_brain.common.quotable_contracts import Quotable
from nm.shared.text_contracts import snippet
from nm.shared.traceability_contracts import implements
from nm.work_the_file.matter_contracts import CAUSE_MEANS, CauseOfAction

CAUSE_VALUES = tuple(c.value for c in CauseOfAction
                     if c is not CauseOfAction.NOT_ESTABLISHED)

#: The vocabulary as the model sees it. COMPOSED FROM `CAUSE_MEANS`, so a
#: cause added to the enum without a definition renders as `no definition
#: recorded` here -- visible, rather than silently becoming a bare
#: identifier again.
_VOCABULARY = (
    "Which cause of action is this? The values mean:" + chr(10)
    + chr(10).join(
        f"  {c.value} - {CAUSE_MEANS.get(c, 'no definition recorded')}"
        for c in CauseOfAction
        if c is not CauseOfAction.NOT_ESTABLISHED)
    + chr(10) + chr(10)
    + "cannot_tell if what they wrote does not plainly support one."
)

CAUSE_SCHEMA: dict = {
    "x-nm-read": "cause",
    "type": "object",
    "properties": {
        # `cannot_tell` IS A REQUIRED MEMBER, not a courtesy. A schema whose
        # every value is a decisive answer forces the model to pick one, and
        # whichever it picks the product routes on a cause nobody established.
        # THE VALUES ARE DEFINED, not merely listed. Eight bare
        # identifiers made `money_lent` a reasonable reading of a brief
        # about unpaid invoices that used the word `debt`, and the proof
        # section then worked the elements of a loan.
        "cause": {
            "type": "string",
            "enum": [*CAUSE_VALUES, "cannot_tell"],
            "description": _VOCABULARY,
        },

        "sentences": {"type": "array", "items": {"type": "string"}},
        "why": {
            "type": "string",
            "description": "One clause, shown to the advocate so they can "
                           "correct the routing.",
        },
    },
    "required": ["cause", "sentences", "why"],
    "additionalProperties": False,
}

SYSTEM = (
    "You read what an Indian advocate has written and name the CAUSE OF "
    "ACTION from a closed list. You are not advising and you are not deciding "
    "the merits — you are deciding which limitation Article should be looked "
    "up.\n\n"
    "THEY MAY DESCRIBE FACTS, OR THEY MAY NAME THE CAUSE OUTRIGHT, and both "
    "are answerable. Facts may support a cause, while a legal enquiry may "
    "explicitly name one without narrating facts. Do "
    "not answer `cannot_tell` merely because nobody has told you a story — "
    "answer it because you cannot tell WHICH cause is meant.\n\n"
    "Answer `cannot_tell` unless what they wrote plainly supports one. A "
    "wrong cause sends an exact lookup into the wrong Article, which is "
    "worse than no lookup at all: the advocate gets a confident date "
    "computed from a period that does not govern their suit. "
    "This vocabulary is incomplete. Do not select a broad neighbouring cause "
    "merely because the precise relief is absent. A contract in the history "
    "does not make every claim a claim for compensation for breach. Match "
    "the relief actually sought, and use cannot_tell when that is unresolved.\n\n"
    "`sentences` are the numbers of the advocate's own sentences that show this "
    "cause. Point at their words by number; never at the questions put to them."
)


@dataclass(frozen=True)
class ReadCause:
    """What was read, and what was refused. THREE STATES.

    `cause` is `NOT_ESTABLISHED` whenever nothing was established, and
    `refused` says why when a guard rejected something the model returned.
    Those are different: the first is an ordinary silence, the second is a
    model output this product declined, and only the second is worth telling
    the advocate about.
    """

    cause: CauseOfAction = CauseOfAction.NOT_ESTABLISHED
    quoted: str = ""
    why: str = ""
    refused: str | None = None

    @property
    def resolved(self) -> bool:
        return self.cause is not CauseOfAction.NOT_ESTABLISHED


UNREAD = ReadCause()


def schema_for(quotable: Quotable) -> dict:
    """The contract, with the advocate's sentence numbers closed."""
    schema = deepcopy(CAUSE_SCHEMA)
    schema["properties"]["sentences"] = quotable.sentence_field(
        "The numbers of the advocate's OWN sentences that show this cause. Empty if "
        "none do.")
    return schema


def build_prompt(quotable: Quotable):
    """This turn, read against the file.

    The cause lives in the ACCOUNT far more often than in the latest message —
    "is the claim still in time" carries no cause at all, and the invoices two
    turns earlier carry it completely. Reading the message alone is what makes
    a product ask an advocate to restate their file every turn.

    THE PROMPT AND THE GUARD ARE ONE VALUE (B-108). This used to take
    `account` -- the rendered file, with `[1984-04-15]` stamps and our own
    notes in it -- while `interpret` checked the span against the advocate's
    sentences alone. A model good enough to use its whole context quoted the
    block it was shown, the guard refused it correctly, and the turn was
    withheld. Nothing had told it the two differed.
    """
    from nm.shared.model_port import Prompt

    return Prompt(system=SYSTEM, user=quotable.block(numbered=True))


@implements("D4")
def interpret(quotable: Quotable, data: dict) -> ReadCause:
    """The model's answer, or a REFUSAL. Never a guess.

    Every refusal lands on `NOT_ESTABLISHED`, which falls through to search.
    That is the asymmetry the whole module is built on: a cause this could not
    read costs a ranked answer carrying its own confidence, and a cause read
    WRONGLY costs an exact lookup into the wrong Article and a limitation date
    the advocate acts on.
    """
    if not isinstance(data, dict):
        return ReadCause(refused="the cause read returned no object")

    raw = (data.get("cause") or "cannot_tell").strip().lower()
    quoted = quotable.cite(data.get("sentences"))
    why = snippet(data.get("why"), 200)

    if raw == "cannot_tell":
        return ReadCause(why=why)

    # GUARD 1 -- OUT OF VOCABULARY IS BLANKED, NEVER ACCEPTED.
    #
    # The closed list is what makes the lookup exact. A value outside it
    # reaches `LIMITATION_ARTICLE.get(...)` as a miss, which is survivable --
    # but it would also be recorded and disclosed as a cause this product
    # identified, which it did not.
    try:
        cause = CauseOfAction(raw)
    except ValueError:
        return ReadCause(quoted=quoted, why=why,
                         refused=f"{raw!r} is not a cause this product routes "
                                 f"on. The vocabulary is closed because the "
                                 f"lookup is exact.")
    if cause is CauseOfAction.NOT_ESTABLISHED:
        # The escape member is not an answer the model may choose.
        return ReadCause(quoted=quoted, why=why)

    # GUARD 2 -- the cause must rest on the advocate's ACTUAL SENTENCES, named by
    # number from the same `quotable` the prompt was built from, so what the
    # model was shown and what this accepts cannot differ.
    if not quoted:
        return ReadCause(why=why, refused=(
            f"a cause of {cause.value!r} was reported without naming any of the "
            f"advocate's own sentences"))

    return ReadCause(cause=cause, quoted=quoted, why=why)
