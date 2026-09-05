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
from nm.domain.text import refuses_blank_text

#: The permitted answers, from the product's own type. Offered to the model so
#: it selects rather than invents -- an out-of-vocabulary role is blanked and
#: re-derived, exactly as PRD D9 requires of every facet value.
ROLE_VALUES = tuple(r.value for r in Role if r is not Role.UNKNOWN)

POSTURE_SCHEMA: dict = {
    "x-nm-read": "posture",
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
            # THREE STATES, and the third is not decoration.
            #
            # `role` may be `not_stated`, which is the ordinary case, and
            # this field then has nothing to describe. With only two members
            # a model reporting that ordinary case had NO legal value to
            # return and sent "" -- which failed validation, which failed
            # open to "nothing was stated", which is indistinguishable from
            # the advocate having said nothing. Defect shape S1, in a schema.
            "enum": ["stated", "inferred", "not_stated"],
            "description": "'stated' if the advocate used a procedural term or "
                           "said who filed. 'inferred' if you worked it out "
                           "from the account plus who they act for. "
                           "'not_stated' if role is 'not_stated' — there is "
                           "then no basis to describe.",
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
    "additionalProperties": False,
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

#: A descriptor that names nobody. GRAMMAR, not vocabulary: these are the
#: ways English refers to one's own client WITHOUT identifying them, and
#: the set is closed in a way a list of party descriptors is not.
#:
#: Recording one is worse than recording nothing. The narrowed blocking
#: question became "You act for the our client. Did they file...?", and a
#: descriptor is write-once on the posture, so the junk one also blocked
#: the real one when it arrived on the next turn.
_NAMES_NOBODY = re.compile(
    r"^(?:the\s+|a\s+|an\s+)?(?:my|our|his|her|their|its)?\s*"
    r"(?:client|party|side|matter|case|them|him|her|us)$", re.I)

_WORDS = re.compile(r"[a-z0-9]+")


def speaks_of_the_representation(text: str) -> bool:
    """Has the advocate spoken in the FIRST PERSON about their own side?

    The same closed grammatical set guard 2 uses, asked of the account
    rather than of one span. It is what separates an advocate stating their
    position -- `we act for`, `we want to file`, `our client`, `on behalf`
    -- from a description of events.

    C3's counterexample contains none of it: *the landlord has issued a
    quit notice to the tenant* names two parties and speaks of neither in
    the first person, so nothing here fires and the reinstatement defect
    stays impossible.
    """
    return bool(_FIRST_PERSON.search(text or ""))


def names_nobody(descriptor: str) -> bool:
    """True when the descriptor identifies no one.

    `the workman`, `the payee`, `the second respondent` identify someone
    and narrow the next question usefully. `our client`, `the party`,
    `him` do not -- they are how a speaker refers to a person already in
    mind, and this product does not have them in mind.
    """
    return bool(_NAMES_NOBODY.match((descriptor or "").strip()))


def _fold(text: str) -> str:
    return " ".join(_WORDS.findall((text or "").lower()))


# ===================================================== the role, asked ======
#
# A SECOND, FOCUSED QUESTION -- and only on the turns that need it.
#
# Measured on five scenarios: the extraction above returns `states_client:
# true`, a good descriptor, and `role: not_stated` every single time. In one
# schema with five fields, `not_stated` is an always-available answer that is
# never wrong, so it is what comes back -- and the posture gate then blocks
# every later turn while the advocate answers the same question over and over.
#
# Asked on its own, the SAME model on the SAME tier got all five right and
# returned `cannot_tell` on a control that genuinely could not be told. The
# defect was the shape of the ask.
#
# THIS DOES NOT RELAX C3. It runs ONLY once the advocate has said who they
# act for; the client is given, not guessed. What is worked out is the
# procedural label for a client already identified, it is marked INFERRED,
# and the advocate can correct it in a word. Inferring the CLIENT from the
# facts is the thing C3 forbids and it is not what happens here.
ROLE_SCHEMA: dict = {
    "x-nm-read": "role",
    "type": "object",
    "properties": {
        "role": {"type": "string", "enum": [*ROLE_VALUES, "cannot_tell"]},
        "why": {"type": "string",
                "description": "One clause. Shown to the advocate so they "
                               "can correct it."},
    },
    "required": ["role", "why"],
    "additionalProperties": False,
}

ROLE_SYSTEM = (
    "An Indian advocate has told you WHO they act for. Your only job is to "
    "say which PROCEDURAL ROLE that client occupies in the proceeding "
    "described.\n\n"
    "You are not deciding whose side they are on — they have told you. You "
    "are naming the forum-correct label for the position that client is "
    "already in.\n\n"
    "Work it out from the account. A payee whose cheque bounced and who has "
    "issued the statutory notice is the complainant. A wife bringing a "
    "maintenance claim is the petitioner. A tenant resisting an eviction the "
    "landlord filed is the respondent or defendant. A workman challenging a "
    "dismissal before a Labour Court is the petitioner; his employer "
    "answering it is the respondent.\n\n"
    "ANSWER ONLY FROM THIS LIST: " + ", ".join(ROLE_VALUES) + ". These are "
    "the positions this product knows how to reason about, and a role "
    "outside them is one it could not use. Where the closest fit is "
    "imperfect, choose the closest fit rather than inventing a word.\n\n"
    "Answer 'cannot_tell' ONLY where the account does not say what "
    "proceeding exists or who moved it. If it describes a proceeding and "
    "says who the client is, the role follows and you must give it."
)


def build_role_prompt(described: str, account: str):
    """Ask the one question the five-field schema kept answering 'not_stated'.

    `described` is often empty, and that is an ordinary case rather than a
    missing input: an advocate who says "we want to file a title suit" has
    told you their side moves without giving their client a label, and the
    labels they do give are frequently "my client", which names nobody.
    The account carries it either way.
    """
    from nm.ports.model import Prompt

    who = (f"The client is: {described}" if (described or "").strip()
           else "The advocate has not given their client a separate label. "
                "Read from the account which party is theirs — they speak "
                "of it in the first person.")
    return Prompt(
        system=ROLE_SYSTEM,
        user=(f"{who}\n\n"
              f"The account so far:\n{account.strip()[:2500]}\n\n"
              f"Which procedural role does the client occupy?"))


def interpret_role(data: dict) -> tuple["Role | None", str]:
    """The role and the reason, or (None, why not).

    OUT OF VOCABULARY IS BLANKED, never coerced to something near it. The
    enum is in the schema AND the vocabulary is named in the prompt, and
    this is the third guard because the first two are both advisory on at
    least one provider — `strict` is off, and a returned value outside the
    enum reached the core once already.
    """
    if not isinstance(data, dict):
        return None, "the role read returned nothing usable"
    raw = (data.get("role") or "cannot_tell").strip().lower()
    if raw == "cannot_tell":
        return None, (data.get("why") or "the account does not say what "
                                        "proceeding exists or who moved it")
    try:
        return Role(raw), (data.get("why") or "").strip()
    except ValueError:
        return None, (f"the model answered {raw!r}, which is not a role this "
                      f"product knows")


@refuses_blank_text("quoted")
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
    if described and names_nobody(described):
        # NAMES NOBODY, so it is not recorded. See `_NAMES_NOBODY`.
        described = None
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
