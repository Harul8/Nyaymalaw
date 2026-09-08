"""Is this instruction one an advocate must REFUSE? GS-05, gate G-DUTY.

WHAT WENT WRONG, MEASURED ON A SERVED TURN
--------------------------------------------
    draft me a backdated acknowledgment so the limitation restarts

The product opened a matter and asked *"Whose side are we on in this matter —
do we act for the party moving, or the party answering?"* A request to
manufacture false evidence was processed as an ordinary brief needing a
posture. Nothing in the codebase refused anything.

WHY IT IS READ AND NOT MATCHED
--------------------------------
A phrase list would need `backdated`, `antedated`, `pre-dated`, `dated back`,
`show it as signed earlier`, `put last year's date on it` -- and the seventh
phrasing is always outside it. This project has paid for that list three
times: ten posture phrases without `we act for the workman` (B-031), the Act
keywords that missed *"is the claim still in time"* (B-065), and the route
lists B-124 removed. The mechanism is a read against a CLOSED VOCABULARY OF
GROUNDS, which is the shape `cause.py` and `dispute.py` already use.

THE GROUNDS ARE CLOSED AND THE PHRASINGS ARE NOT. That is the whole design: a
model can recognise that *"put last year's date on it"* is backdating without
anybody having written that sentence down, and it may only answer with a
ground this product has curated.

WHICH DIRECTION IT FAILS
--------------------------
Toward ANSWERING, deliberately, and this is the opposite of most reads here.
A refusal wrongly issued accuses an advocate of professional misconduct for
asking an ordinary question, which is both offensive and useless. So
`cannot_tell` and every failure land on `CLEAR`, and the turn proceeds.

That is safe only because the refusal is not the sole protection: nothing this
product emits is grounded except in retrieved text, no document is drafted
with a date the advocate did not supply, and G-QUOTE refuses a span nobody
wrote. This gate exists so the advocate is TOLD, not to be the last line.

AND A REFUSAL WITHOUT A ROUTE IS A WALL
-----------------------------------------
GS-05's counterexample is explicit: *refuse without an alternative*. An
advocate asking this usually has a real problem -- a period they believe has
run -- and there is a lawful answer to it. The refusal carries what actually
restarts limitation, retrieved and read back, not composed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nm.domain.quotable import Quotable
from nm.domain.text import refuses_blank_text


class Ground(str, Enum):
    """WHY an instruction must be refused. CLOSED, and curated.

    Each is a thing an advocate may not do and a client may reasonably ask
    for without knowing that. None of them is about the merits.
    """

    #: A document made to say it was created or signed at a time it was not.
    FALSE_DOCUMENT = "false_document"
    #: Destroying, hiding or withholding what must be produced.
    SUPPRESS_EVIDENCE = "suppress_evidence"
    #: Telling the court something known to be untrue, or letting it stand.
    MISLEAD_COURT = "mislead_court"
    #: Shaping what a witness will say, or paying for it.
    INTERFERE_WITNESS = "interfere_witness"
    #: Nothing here requires refusal. A FINDING: the read ran and found
    #: nothing refusable.
    CLEAR = "clear"
    #: NOBODY LOOKED. The read did not run, or its answer was refused by a
    #: guard.
    #:
    #: NOT THE SAME AS `CLEAR`, though both let the turn proceed. `CLEAR`
    #: says an instruction was examined and is proper; this says it was
    #: not examined. `UNREAD` used to be `CLEAR`, which made a read that
    #: never ran indistinguishable from one that cleared the advocate --
    #: S1, and the same conflation the Gate constructor refused in
    #: G-SPLIT an hour earlier.
    NOT_ASSESSED = "not_assessed"


#: What the advocate is told, per ground. The duty first, then the route.
#:
#: NAMED, NOT GESTURED AT. "I can't help with that" tells an advocate nothing
#: and reads as squeamishness. The duty has a name and they know it better
#: than this product does; saying it is what makes the refusal legible as a
#: professional position rather than a filter.
DUTY: dict[Ground, str] = {
    Ground.FALSE_DOCUMENT:
        "A document dated to a day it was not made is a false document. I "
        "will not draft one, and an advocate who tenders one is exposed "
        "whatever the client instructed.",
    Ground.SUPPRESS_EVIDENCE:
        "Material that is discoverable has to be produced. I will not help "
        "withhold or destroy it.",
    Ground.MISLEAD_COURT:
        "The duty to the court comes before the client's instructions. I "
        "will not put something before a court that we know to be untrue.",
    Ground.INTERFERE_WITNESS:
        "What a witness says has to be theirs. I will not help shape it.",
}

DUTY_SCHEMA: dict = {
    "x-nm-read": "duty",
    "type": "object",
    "properties": {
        "ground": {
            "type": "string",
            "enum": [g.value for g in Ground],
            "description": (
                "`clear` unless the advocate is asking you to DO one of the "
                "other things. `false_document` covers backdating, "
                "antedating, or dating anything to a day it was not made. "
                "Asking what the law says about backdating is NOT this — "
                "answering a question about a rule is never a refusal."),
        },
        "quoted": {
            "type": "string",
            "description": (
                "The advocate's EXACT words asking for it, copied verbatim. "
                "Empty when the ground is `clear`."),
        },
        "why": {
            "type": "string",
            "description": "One clause. Shown to the advocate.",
        },
        # THE LAWFUL COUNTERPART, NAMED SO IT CAN BE RETRIEVED.
        #
        # NOT asserted from this answer. The product looks the provision up
        # and reads back what the corpus holds; if it is not held, the
        # advocate is told that rather than given the model's recollection of
        # it. That is B-104's shape -- name a provision, retrieve it, and let
        # the retrieval be the claim.
        #
        # An advocate asking to backdate an acknowledgment has a real problem
        # underneath it, and section 18 is the answer to that problem. A
        # refusal that stopped at "no" would leave them with the problem and
        # a reason to ask someone less careful.
        "lawful_section": {
            "type": "string",
            "description": (
                "The Act and section governing the LAWFUL way to achieve what "
                "they are trying to achieve, as 'Limitation Act, 1963 s.18'. "
                "Empty if you do not know one. Do not guess a number."),
        },
    },
    "required": ["ground", "quoted", "why", "lawful_section"],
    "additionalProperties": False,
}

SYSTEM = (
    "An Indian advocate has instructed you. Decide ONE thing: are they asking "
    "you to DO something an advocate must refuse?\n\n"
    "Answer `clear` for anything else, and `clear` is the ordinary answer. "
    "Advocates ask hard, adversarial and unflattering questions all day and "
    "none of that is refusable. Wrongly refusing accuses a colleague of "
    "misconduct for doing their job.\n\n"
    "THE DISTINCTION THAT MATTERS: doing it, versus asking about it. 'What is "
    "the effect of a backdated acknowledgment?' is a question of law and is "
    "CLEAR. 'Draft me a backdated acknowledgment' is an instruction to make a "
    "false document. 'What did the other side gain by backdating theirs?' is "
    "CLEAR. Only an instruction to YOU, to DO it, is refusable.\n\n"
    "Quote their exact words when you refuse. If you cannot quote it, it did "
    "not happen."
)


@refuses_blank_text("quoted", "why")
@dataclass(frozen=True)
class Refusal:
    """One ground, or CLEAR. `refused` is set when a guard rejected the read."""

    ground: Ground = Ground.CLEAR
    quoted: str = ""
    why: str = ""
    refused: str | None = None
    lawful_section: str = ""
    """A PROVISION TO LOOK UP, and never a provision to quote.

    Nothing here reaches the advocate. The turn retrieves it and reads back
    what the corpus holds, so the claim is the retrieval's and not the
    model's. Empty is ordinary."""

    @property
    def must_refuse(self) -> bool:
        """Only a GROUND refuses. `CLEAR` and `NOT_ASSESSED` both let the
        turn run, and they are still different facts -- the gate reports
        which."""
        return self.ground not in (Ground.CLEAR, Ground.NOT_ASSESSED)

    @property
    def duty(self) -> str:
        return DUTY.get(self.ground, "")


#: What a read that did not run leaves behind. The turn proceeds --
#: `must_refuse` is false -- and the state is honest about why.
UNREAD = Refusal(Ground.NOT_ASSESSED, why="the duty read did not run")


def build_prompt(quotable: Quotable):
    from nm.ports.model import Prompt

    return Prompt(
        system=SYSTEM,
        user=(f"{quotable.block()}\n\n"
              f"Are they instructing you to do something you must refuse?"))


def interpret(quotable: Quotable, data: dict) -> Refusal:
    """The model's answer, or CLEAR.

    EVERY FAILURE PATH LANDS ON CLEAR. A refusal is an accusation, and one
    issued because a read timed out is worse than the request it was meant to
    catch -- it is unanswerable, because there is nothing for the advocate to
    correct.
    """
    if not isinstance(data, dict):
        return Refusal(Ground.NOT_ASSESSED,
                       refused="the duty read returned nothing")

    raw = (data.get("ground") or "").strip().lower()
    try:
        ground = Ground(raw)
    except ValueError:
        return Refusal(Ground.NOT_ASSESSED,
                       refused=f"the model answered {raw!r}, which is not a "
                               f"ground this product refuses on")
    if ground is Ground.CLEAR:
        return Refusal(Ground.CLEAR)

    quoted = (data.get("quoted") or "").strip()
    why = " ".join((data.get("why") or "").split())[:200]

    # THE SPAN IS THE ADVOCATE'S OWN WORDS OR THERE IS NO REFUSAL.
    #
    # The same guard `cause` and `dispute` use, and it earns more here than
    # anywhere else: this answer tells an advocate they asked for something
    # improper, and it must be able to show them where. A refusal quoting the
    # product's own prompt back at them would be unanswerable.
    if not quotable.accepts(quoted):
        return Refusal(Ground.NOT_ASSESSED, refused=(
            f"the model refused on {ground.value!r} and "
            f"{quotable.refusal(quoted)}"))
    if not why:
        why = "the instruction asks for this to be done"
    route = " ".join((data.get("lawful_section") or "").split())[:120]
    return Refusal(ground, quoted, why, lawful_section=route)
