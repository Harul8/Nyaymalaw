"""What cause of action is this? PRD §4.2, control H3.

THE QUESTION THIS ANSWERS, AND WHY A MODEL ASKS IT
----------------------------------------------------
`nm/knowledge/resolution.py` turns a cause of action into the Article that
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
   quote us back to ourselves.
3. A cause is always INFERRED and always disclosed. Nobody states a cause of
   action; it is worked out, and a worked-out routing decision the advocate
   cannot see is one they cannot correct.
"""
from __future__ import annotations

from dataclasses import dataclass

from nm.core.posture import _fold
from nm.domain.matter import CauseOfAction
from nm.domain.traceability import implements

CAUSE_VALUES = tuple(c.value for c in CauseOfAction
                     if c is not CauseOfAction.NOT_ESTABLISHED)

CAUSE_SCHEMA: dict = {
    "title": "cause",
    "type": "object",
    "properties": {
        # `cannot_tell` IS A REQUIRED MEMBER, not a courtesy. A schema whose
        # every value is a decisive answer forces the model to pick one, and
        # whichever it picks the product routes on a cause nobody established.
        "cause": {"type": "string", "enum": [*CAUSE_VALUES, "cannot_tell"]},
        "quoted": {
            "type": "string",
            "description": "The advocate's OWN words that show this cause, "
                           "verbatim. Empty if none do.",
        },
        "why": {
            "type": "string",
            "description": "One clause, shown to the advocate so they can "
                           "correct the routing.",
        },
    },
    "required": ["cause", "quoted", "why"],
    "additionalProperties": False,
}

SYSTEM = (
    "You read an Indian advocate's account of a matter and name the CAUSE OF "
    "ACTION from a closed list. You are not advising and you are not deciding "
    "the merits — you are deciding which limitation Article should be looked "
    "up.\n\n"
    "Answer `cannot_tell` unless the account plainly supports one. A wrong "
    "cause sends an exact lookup into the wrong Article, which is worse than "
    "no lookup at all: the advocate gets a confident date computed from a "
    "period that does not govern their suit.\n\n"
    "`quoted` must be the advocate's own words, copied exactly from what they "
    "wrote. Never quote the questions put to them and never paraphrase."
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


def build_prompt(message: str, account: str = ""):
    """This turn, read against the file.

    The cause lives in the ACCOUNT far more often than in the latest message —
    "is the claim still in time" carries no cause at all, and the invoices two
    turns earlier carry it completely. Reading the message alone is what makes
    a product ask an advocate to restate their file every turn.
    """
    from nm.ports.model import Prompt

    user = f"What the advocate has just asked:\n{message.strip()[:1500]}"
    if account.strip():
        user = (f"What the advocate has already said on this matter:\n"
                f"{account.strip()[:2500]}\n\n" + user)
    return Prompt(system=SYSTEM, user=user)


@implements("D4")
def interpret(message: str, data: dict, advocate_words: str = "") -> ReadCause:
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
    quoted = (data.get("quoted") or "").strip()
    why = " ".join((data.get("why") or "").split())[:200]

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

    # GUARD 2 -- the span must be the advocate's ACTUAL WORDS.
    #
    # `advocate_words` is a SEPARATE parameter from the prompt, and that is
    # load-bearing. The prompt carries this product's own outstanding
    # questions; checking against everything the model was SHOWN would let the
    # extractor quote our own question about the goods back at us and settle a
    # cause nobody described. The posture reader was measured failing exactly
    # that way, and this imports its guard rather than restating it.
    if not quoted:
        return ReadCause(why=why,
                         refused=f"a cause of {cause.value!r} was reported "
                                 f"with nothing quoted to support it")
    said = f"{message}\n{advocate_words}" if advocate_words else message
    if _fold(quoted) not in _fold(said):
        return ReadCause(quoted=quoted, why=why,
                         refused=f"the quoted span is in nothing the advocate "
                                 f"wrote: {quoted[:60]!r}")

    return ReadCause(cause=cause, quoted=quoted, why=why)
