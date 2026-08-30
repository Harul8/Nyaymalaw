"""Reading the posture the advocate STATED — by model, not by word list.

WHY THERE IS NO LIST HERE
--------------------------
There was one. Ten exact phrases, and `we act for the workman` was not among
them — so an advocate who answered the blocking question in any other words was
asked it again, and rephrasing was precisely what had failed. Every multi-turn
conversation died on that loop.

The reflex fix is a longer list. I wrote one: forty party descriptors, fifteen
forum roles. It is the same defect at a larger size. A list of the ways a
practising advocate can say who they act for is not a list anyone finishes —
"we're for the second respondent", "instructed by the bank", "appearing on
behalf of the corporate debtor", "our side is the caveator". Every gap is a
conversation that traps the person using it.

So the model reads it. That is what a model is for and what a regex is not.

WHAT KEEPS THAT SAFE — AND C3 IS NOT NEGOTIABLE
------------------------------------------------
C3 says posture is taken from what the advocate STATED and is NEVER inferred
from familiar vocabulary. *"The landlord has issued a quit notice"* names a
landlord and says nothing about which side the client is on; the measured
defect there told an employer he could claim reinstatement from himself, with
every citation correct and the whole analysis on the wrong side.

Handing the decision to a model does not relax that rule. It changes how it is
enforced, and two guards do the work:

  1. THE SPAN MUST BE VERBATIM. The model returns the exact words it read the
     posture from, and they are checked against the message. It cannot settle a
     posture out of nothing, and the advocate can see what was relied on.

  2. THE SPAN MUST SPEAK OF THE REPRESENTATION, NOT THE EVENTS. An advocate
     stating their client says *we*, *our client*, *I appear*. An account of
     events does not. That test is on GRAMMAR — a closed set of English
     pronouns, complete in a way a list of party descriptors can never be —
     rather than on which nouns appear.

The role vocabulary is the `Role` enum: the product's own closed type, offered
to the model as the permitted answers. That is not a phrase list. It is the set
of procedural positions this product knows how to reason about, and a posture
outside it is one the product could not use anyway.

WHERE THE MODEL IS STILL NOT TRUSTED
-------------------------------------
A party descriptor is not a role. `we act for the wife` says who the client is
and NOT whether she filed — the old list mapped it to PETITIONER, which was an
inference about who moved dressed as a reading of what was said. The model is
asked for those separately, and a descriptor alone narrows the question rather
than settling it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from nm.domain.matter import Basis, Role

#: The permitted answers, from the product's own type. Offered to the model so
#: it selects rather than invents -- an out-of-vocabulary role is blanked and
#: re-derived, exactly as PRD D9 requires of every facet value.
ROLE_VALUES = tuple(r.value for r in Role if r is not Role.UNKNOWN)

POSTURE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "states_client": {
            "type": "boolean",
            "description": "True ONLY if the advocate states who they act for. "
                           "False if the message merely describes events.",
        },
        "role": {
            "type": "string",
            "enum": [*ROLE_VALUES, "not_stated"],
            "description": "The client's PROCEDURAL role. Give it where the "
                           "advocate named one, said who filed, or where the "
                           "account makes it clear. 'not_stated' if the role "
                           "genuinely cannot be told.",
        },
        "role_basis": {
            "type": "string",
            "enum": ["stated", "inferred"],
            "description": "'stated' if the advocate used a procedural term or "
                           "said who filed. 'inferred' if you worked it out "
                           "from the account plus who they act for.",
        },
        "client_described_as": {
            "type": "string",
            "description": "The advocate's own word for the client where they "
                           "gave one without a procedural role -- 'the "
                           "workman', 'the wife'. Empty string if none.",
        },
        "quoted": {
            "type": "string",
            "description": "The EXACT words from the message that state this. "
                           "Must appear verbatim. Empty string if nothing was "
                           "stated.",
        },
    },
    "required": ["states_client", "role", "role_basis",
                 "client_described_as", "quoted"],
}

SYSTEM = (
    "You extract, from an Indian advocate's message, ONLY what they have "
    "STATED about whom they act for. You never infer a side from the facts "
    "described.\n\n"
    "A message that describes events — 'the landlord issued a quit notice', "
    "'a fitter was dismissed' — states NOTHING about which side the advocate "
    "is on. Return states_client false for those.\n\n"
    "A message where the advocate says who they act for, or who filed, DOES "
    "state it: 'we act for the workman', 'we filed the claim', 'this was "
    "filed against our client', 'appearing for the second respondent'.\n\n"
    "Once the advocate has said WHO they act for, you may work out that "
    "client's procedural role from the account — a wife bringing a maintenance "
    "claim is the applicant; a workman challenging a dismissal is the "
    "claimant. Mark that role_basis 'inferred'. Use 'stated' only where they "
    "named a procedural term or said who filed.\n\n"
    "Where the role genuinely cannot be told even knowing the client, return "
    "role 'not_stated' and put their own word for the client in "
    "client_described_as.\n\n"
    "`quoted` must be the exact words from the message, copied character for "
    "character."
)

#: Grammar, not vocabulary. An advocate stating their client speaks in the
#: first person about the representation; an account of events does not. This
#: set is CLOSED and complete in a way a list of party descriptors can never be.
_FIRST_PERSON = re.compile(
    r"\b(?:we|we're|us|our|ours|my|mine|i|client'?s?|behalf)\b", re.I)

_WORDS = re.compile(r"[a-z0-9]+")


def _fold(text: str) -> str:
    return " ".join(_WORDS.findall((text or "").lower()))


@dataclass(frozen=True)
class StatedPosture:
    role: Role
    basis: Basis
    client_described_as: str | None
    quoted: str
    refused: str | None = None

    @property
    def settles_role(self) -> bool:
        return self.role is not Role.UNKNOWN


UNSTATED = StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, None, "")


def build_prompt(message: str, account: str = ""):
    """The message, AND what the advocate has already said on this thread.

    Reading only the latest message throws the conversation away. "We act for
    the wife" says nothing about her procedural role on its own; read against
    "talaq was pronounced, there is a maintenance claim" from the turn before,
    it is plain. An advocate builds context across turns and expects it held —
    being asked to restate the file every turn is the same failure as being
    asked the same question twice.
    """
    from nm.ports.model import Prompt

    user = f"Message:\n{message.strip()[:1500]}"
    if account.strip():
        user = (f"What the advocate has already said on this matter:\n"
                f"{account.strip()[:2500]}\n\n" + user)
    return Prompt(system=SYSTEM, user=user)


def interpret(message: str, data: dict,
              advocate_words: str = "") -> StatedPosture:
    """Turn the model's answer into a posture, or REFUSE it.

    Refusal is not an error path. It is the ordinary outcome whenever the model
    reports something the message does not support, and it leaves posture
    exactly where it was — unresolved, and blocking.
    """
    if not isinstance(data, dict) or not data.get("states_client"):
        return UNSTATED

    quoted = (data.get("quoted") or "").strip()
    if not quoted:
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, None, "",
                             refused="the model reported a stated posture and "
                                     "quoted nothing to support it")

    # GUARD 1 -- the span must be the advocate's ACTUAL WORDS.
    #
    # `advocate_words` is what they said on earlier turns, and it is a
    # SEPARATE parameter from the prompt for a reason. The prompt carries
    # this product's own outstanding questions, and one of those questions
    # is literally "do we act for the party moving, or the party
    # answering?" -- so checking the span against everything the model was
    # SHOWN let the extractor quote us back to ourselves and settle a
    # posture nobody had stated. Every other guard passed.
    said = f"{message}\n{advocate_words}" if advocate_words else message
    if _fold(quoted) not in _fold(said):
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, None, quoted,
                             refused=f"the quoted span is in nothing the "
                                     f"advocate wrote: {quoted[:60]!r}")

    # GUARD 2 -- the span must speak of the REPRESENTATION, not the events.
    if not _FIRST_PERSON.search(quoted):
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, None, quoted,
                             refused=f"the quoted span describes events rather "
                                     f"than stating whom the advocate acts for: "
                                     f"{quoted[:60]!r}")

    described = (data.get("client_described_as") or "").strip().lower() or None
    if described:
        described = re.sub(r"^(?:the|a|an)\s+", "", described)[:40] or None

    raw_role = (data.get("role") or "not_stated").strip().lower()
    if raw_role == "not_stated":
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, described, quoted)
    try:
        role = Role(raw_role)
    except ValueError:
        # OUT OF VOCABULARY IS BLANKED, never accepted (PRD D9).
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, described, quoted,
                             refused=f"the model returned role {raw_role!r}, "
                                     f"which is not a role this product knows")

    # STATED vs INFERRED, and the difference is disclosed rather than hidden.
    #
    # Once the advocate has SAID who they act for, the reinstatement defect is
    # already impossible -- that defect was assuming the client's identity from
    # the facts, and the identity is now given. What remains open is the
    # procedural role, and working that out from the account is ordinary
    # reading, not the guess C3 forbids. It is marked `inferred` so the
    # advocate sees it and can correct it in a word.
    basis = (Basis.STATED if (data.get("role_basis") or "").strip().lower()
             == "stated" else Basis.INFERRED)
    return StatedPosture(role, basis, described, quoted)
