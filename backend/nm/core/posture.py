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
from copy import deepcopy
from dataclasses import dataclass

from nm.domain.matter import Basis, Role
from nm.domain.quotable import Quotable
from nm.domain.text import (
    clean,
    refuses_blank_text,
    snippet,
    speaks_of_the_representation,
)

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
                           "said who filed, or expressly stated that no proceeding "
                           "applies or has begun. 'inferred' if you worked it out "
                           "from the account plus who they act for. "
                           "'not_stated' if role is 'not_stated' — there is "
                           "then no basis to describe.",
        },
        "client_described_as": {
            "type": "string",
            "description": "The advocate's own word for the client where they "
                           "gave one without a procedural role. Empty string if none.",
        },
        "opponent": {
            "type": "string",
            "description": "Who the client is AGAINST, in the advocate's own "
                           "words. Only "
                           "where they said it. Empty string if they did not.",
        },
        "opponent_correction_quote": {
            "type": "string",
            "description": "Exact CURRENT words expressly correcting the recorded opponent "
                           "for this dispute. Include both the rejected name and replacement. "
                           "Empty unless the advocate corrects it; a different name alone "
                           "is not a correction.",
        },
        "quoted": {
            "type": "string",
            "description": "The EXACT words stating WHOM the advocate acts for. "
                           "Must appear verbatim. Empty string if nothing was "
                           "stated.",
        },
        # WHOM WE ACT FOR AND WHICH SIDE OF WHICH PROCEEDING ARE TWO FACTS, and
        # an advocate usually states them in two sentences. See `interpret`.
        "role_quote": {
            "type": "string",
            "description": "The EXACT words stating the client's procedural "
                           "role or position on THIS dispute -- who filed, the "
                           "procedural term used, or what the client seeks or "
                           "resists. Often a DIFFERENT sentence from `quoted`. "
                           "Must appear verbatim in THIS dispute's own words. "
                           "Empty string if the role is not stated.",
        },
    },
    "additionalProperties": False,
    # Every property, because strict mode compiles the grammar from `required`
    # and a property left out of it cannot be emitted at all.
    "required": ["states_client", "role", "role_basis",
                 "client_described_as", "opponent", "quoted", "role_quote",
                 "opponent_correction_quote"],
}

SYSTEM = (
    "You extract, from an Indian advocate's message, ONLY what they have "
    "STATED about whom they act for. You never infer a side from the facts "
    "described.\n\n"
    "A description of events alone does not identify the represented party. "
    "Use the advocate's actual representation instruction, not familiar party "
    "vocabulary or an assumed aggrieved side.\n\n"
    "Once the advocate has said WHO they act for, you may work out that "
    "client's procedural role from an unambiguous proceeding. Do not assign a "
    "filed role to advisory work or an uninstituted proceeding. "
    "Use prospective_claimant or prospective_respondent when the advocate "
    "expressly identifies their client's intention to seek or resist relief "
    "on THIS unfiled dispute. These are substantive positions, not claims "
    "that proceedings exist; they require stated support in the quotation. "
    "Do not infer them merely from being aggrieved. "
    "Use not_applicable for expressly non-contentious work, not_yet_instituted "
    "for an expressly unfiled proceeding whose intended position is not stated, "
    "and unsupported_role for a stated "
    "role outside the supported vocabulary. These do not establish a litigating side. "
    "BEING UNFILED AND HAVING A POSITION ARE TWO DIFFERENT FACTS, and a matter "
    "can have both. Where the advocate has BOTH said nothing is filed AND "
    "stated what their client seeks or resists on this dispute, answer with "
    "the prospective role: it is the one that says which side they are on, and "
    "that nothing is filed is already recorded on the file from intake. "
    "not_yet_instituted is for the unfiled dispute where no position is "
    "stated -- it is the absence of an answer, not a second way of giving one. "
    "Mark an inferred role_basis 'inferred'. Use 'stated' only where they "
    "named a procedural term, said who filed, stated their prospective claim or "
    "defence, or expressly stated no proceeding "
    "applies or has begun.\n\n"
    "Where the role genuinely cannot be told even knowing the client, return "
    "role 'not_stated' and put their own word for the client in "
    "client_described_as.\n\n"
    "`opponent` is who the client is AGAINST, in the advocate's own words, "
    "and ONLY where they said it. Do not work it out from the events. Empty string if they did "
    "not name one.\n\n"
    "WHOM YOU ACT FOR AND THE CLIENT'S ROLE ARE TWO FACTS, and they are "
    "often stated in two different sentences. Put the sentence saying whom the "
    "advocate acts for in `quoted`, and the sentence stating the role on THIS "
    "dispute -- who filed, the procedural term, what the client seeks or "
    "resists -- in `role_quote`. Do not choose a role because it is the only "
    "one the representation sentence alone supports: read the dispute's own "
    "words for the role.\n\n"
    "A PROCEEDING THE ADVOCATE SAYS WAS FILED IS INSTITUTED. Where they say "
    "they filed, instituted or are appearing in a proceeding -- or give its "
    "case number, forum or stage -- give the filed role that forum uses "
    "(plaintiff, petitioner, applicant, complainant, appellant, or the "
    "answering role where the other side filed). Never not_yet_instituted.\n\n"
    "`quoted` and `role_quote` must be the exact words from the message, "
    "copied character for character."
)

#: A descriptor that names nobody. GRAMMAR, not vocabulary: these are the
#: ways English refers to a person WITHOUT identifying them -- by their
#: relation to the speaker -- and the set is closed in a way a list of party
#: descriptors is not.
#:
#: Recording one is worse than recording nothing. The narrowed blocking
#: question became "You act for the our client. Did they file...?", and a
#: descriptor is write-once on the posture, so the junk one also blocked
#: the real one when it arrived on the next turn.
#:
#: THE SECOND CLAUSE IS THE MIRROR, and it is the same rule rather than a
#: second guard. `our client` identifies the near side only by its relation
#: to the speaker; `the opposite party`, `the other side` identify the far
#: side the same way. Recording one as the OPPONENT says "we are against the
#: side we are against" and makes the record report that the other side is
#: known. Where `opposite party` is the advocate's PROCEDURAL role -- it is
#: one, in consumer and execution practice -- it arrives as `role` and never
#: through here.
_NAMES_NOBODY = re.compile(
    r"^(?:the\s+|a\s+|an\s+)?(?:"
    r"(?:my|our|his|her|their|its)?\s*"
    r"(?:client|party|side|matter|case|them|him|her|us)"
    r"|(?:opposite|opposing|other|another|adverse|rival)\s+"
    r"(?:party|parties|side|counsel)"
    r")$", re.I)



#: `speaks_of_the_representation` IS IMPORTED, NOT DEFINED HERE.
#:
#: `nm.domain.summary` has to ask the same question -- is this statement about
#: the representation, and therefore about the FILE rather than about one
#: dispute -- and `domain` may import only `domain`. Defining it twice is the
#: second copy CLAUDE.md §4 asks about, and the failure it guards is exactly
#: the one a drifting copy reintroduces. It stays re-exported from this module
#: so `posture.speaks_of_the_representation` keeps working for its callers.


def names_nobody(descriptor: str) -> bool:
    """True when the descriptor identifies no one.

    `the workman`, `the payee`, `the second respondent` identify someone
    and narrow the next question usefully. `our client`, `the party`,
    `him` do not -- they are how a speaker refers to a person already in
    mind, and this product does not have them in mind.
    """
    return bool(_NAMES_NOBODY.match((descriptor or "").strip()))


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
    "Use the stated proceeding and represented party. Non-contentious work is "
    "not_applicable; an expressly uninstituted proceeding is not_yet_instituted. "
    "Use unsupported_role for a known role outside the supported vocabulary. "
    "These states grant no litigating side or permission.\n\n"
    "ANSWER ONLY FROM THIS LIST: " + ", ".join(ROLE_VALUES) + ". These are "
    "the positions this product knows how to reason about, and a role "
    "outside them must not be approximated.\n\n"
    "Answer cannot_tell whenever the supplied record does not establish a "
    "supported role or one of the explicit non-litigation states. Do not guess."
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
                "Use only an explicit representation instruction in the account. "
                "First-person language alone does not identify the represented party; "
                "return cannot_tell when representation is not established.")
    return Prompt(
        system=ROLE_SYSTEM,
        user=(f"{who}\n\n"
              f"The account so far:\n{account.strip()}\n\n"
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
        role = Role(raw)
        if role in (Role.PROSPECTIVE_CLAIMANT, Role.PROSPECTIVE_RESPONDENT):
            return None, "a prospective position requires the source-bound stated-posture read"
        return role, (data.get("why") or "").strip()
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
    opponent: str | None = None
    """Who the client is against, as the advocate said it.

    A NAME, recorded and shown back. Nothing is ever looked up with it, so
    CLAUDE.md 5 does not reach here: it neither identifies an Act nor routes
    a retrieval. Keyword-only in position so every existing construction of
    this type is unchanged -- there are eight, and a positional insertion
    would have silently shifted `refused` into it.
    """
    opponent_correction_quote: str = ""

    @property
    def settles_role(self) -> bool:
        return self.role is not Role.UNKNOWN


UNSTATED = StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, None, "")


def schema_for(quotable: Quotable) -> dict:
    """Correction quotes select actual current sentences, never a paraphrase."""
    from nm.core.dispute import source_units

    schema = deepcopy(POSTURE_SCHEMA)
    schema['properties']['opponent_correction_quote']['enum'] = [
        '', *source_units(quotable.turn).values()]
    return schema


def build_prompt(quotable: Quotable):
    """The message, AND what the advocate has already said on this thread.

    Reading only the latest message throws the conversation away. "We act for
    the wife" says nothing about her procedural role on its own; read against
    "talaq was pronounced, there is a maintenance claim" from the turn before,
    it is plain. An advocate builds context across turns and expects it held —
    being asked to restate the file every turn is the same failure as being
    asked the same question twice.

    AND THE FILE IS SHOWN AS CONTEXT, NOT AS QUOTABLE TEXT (B-108). This read
    has the sharpest version of the trap: the prompt carries this product's
    own outstanding questions, one of which is literally "do we act for the
    party moving, or the party answering?" -- so a span quoted from the
    rendering could settle a posture nobody stated. The guard already refused
    that; now the prompt says so.
    """
    from nm.ports.model import Prompt

    return Prompt(system=SYSTEM, user=quotable.block())


def interpret(quotable: Quotable, data: dict) -> StatedPosture:
    """Turn the model's answer into a posture, or REFUSE it.

    Refusal is not an error path. It is the ordinary outcome whenever the model
    reports something the message does not support, and it leaves posture
    exactly where it was — unresolved, and blocking.
    """
    if not isinstance(data, dict) or not data.get("states_client"):
        return UNSTATED

    quoted = (data.get("quoted") or "").strip()

    # GUARD 1 -- the span must be the advocate's ACTUAL WORDS.
    #
    # The prompt carries this product's own outstanding questions, and one of
    # those questions is literally "do we act for the party moving, or the
    # party answering?" -- so accepting a span from everything the model was
    # SHOWN let the extractor quote us back to ourselves and settle a posture
    # nobody had stated. Every other guard passed.
    #
    # THE SAME `quotable` THE PROMPT WAS BUILT FROM (B-108), so the section
    # the model was told to copy from is the section this accepts.
    if not quotable.accepts(quoted):
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, None, quoted,
                             refused=(f"the model reported a stated posture "
                                      f"and {quotable.refusal(quoted)}"))

    # GUARD 2 -- the span must speak of the REPRESENTATION, not the events.
    if not speaks_of_the_representation(quoted):
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, None, quoted,
                             refused=f"the quoted span describes events rather "
                                     f"than stating whom the advocate acts for: "
                                     f"{snippet(quoted, 60)!r}")

    # THE ADVOCATE'S OWN WORD FOR THEIR CLIENT, IN THEIR OWN CASE.
    #
    # THE MEASURED DEFECT, 23 September 2026, on a live matter. The advocate
    # wrote "I act for Sattaru Ramulu" and the blocking question came back:
    #
    #     You act for sattaru ramulu. Are they the one seeking something here?
    #
    # `.strip().lower()` was doing two jobs at once. Lowercasing is right for
    # ASKING QUESTIONS OF the value -- `names_nobody` and the leading-article
    # strip both want a case-insensitive probe -- and wrong for the value that
    # is STORED AND SHOWN, because this is the advocate's own word for their
    # client and it is put back in front of them in a sentence.
    #
    # THE GENERAL RULE: a normalisation for MATCHING is never the value kept
    # for DISPLAY. This repository already draws that line for text -- `fold`
    # answers "are these the same" and never replaces the sentence it folded --
    # and this was the one place a fold was being stored.
    #
    # Swept, 23 September 2026: thirteen other `.strip().lower()` calls in
    # `core/` and `domain/` were read, and every one lowers an ENUM
    # DISCRIMINATOR (`cause`, `verdict`, `role`, `role_basis`, `ground`,
    # `side`) or a COMPARISON KEY (`conflict`, `parties`, `intake`). Those are
    # correct and stay. This was the only value that was lowered and then
    # rendered.
    described = clean(data.get("client_described_as")) or None
    if described and names_nobody(described.lower()):
        # NAMES NOBODY, so it is not recorded. See `_NAMES_NOBODY`.
        described = None
    if described:
        # The article is stripped case-insensitively and what remains keeps
        # the advocate's capitalisation -- "the Landlord" gives "Landlord",
        # and "Sattaru Ramulu" is untouched.
        described = re.sub(r"^(?:the|a|an)\s+", "", described,
                           flags=re.IGNORECASE)[:40].strip() or None

    # NAMES NOBODY applies here too, and it is the same mechanism rather than
    # a second one: "the opposite party" is a grammatical placeholder, not a
    # name, and recording it would make the record say the opponent is known.
    against = (data.get("opponent") or "").strip()[:60] or None
    if against and names_nobody(against):
        against = None

    raw_role = (data.get("role") or "not_stated").strip().lower()
    if raw_role == "not_stated":
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, described, quoted,
                             opponent=against)
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

    # THE ROLE'S OWN QUOTATION, AND IT IS HELD TO THIS DISPUTE'S WORDS.
    #
    # THE MEASURED DEFECT, 23 September 2026, live matter 2. The advocate
    # wrote "We act for Sunitha Reddy, the landlord..." and, three sentences
    # later, "We filed RC 88/2025 before the Rent Controller and he has filed
    # his written statement." The posture read returned `not_yet_instituted`
    # on the eviction thread -- quoting the FIRST sentence, which says whom we
    # act for and nothing about any proceeding. The fallback role read, on the
    # same turn, answered `applicant` "in the RC 88/2025 proceeding", and could
    # not be used because it carries no quotation. The matter blocked on
    # G-POSTURE with the side written out in plain words.
    #
    # ONE FIELD WAS CARRYING TWO FACTS, the shape 1.5 of the dated review
    # found for filing-versus-side, one field over. With a single `quoted`
    # the answer could be source-bound for the representation OR for the
    # role, and the model chose the representation.
    #
    # `role_quote` IS ACCEPTED ONLY FROM THIS TURN'S WORDS, which on a scoped
    # turn are THIS dispute's allocation -- the rule `opponent_correction_quote`
    # already applies. `quoted` may come from representation lines carried in
    # from other disputes, because whom we act for is shared; the ROLE may
    # not, because a role quoted out of another dispute is 1.1's contamination
    # (a lease dispute read as `respondent` out of the cheque case) arriving
    # through the new field. A role quote that is not this dispute's words
    # therefore leaves the role INFERRED rather than stated -- and a
    # prospective role, which must be stated, is then refused as it always was.
    #
    # An EMPTY role_quote keeps the old behaviour: many advocates name the role
    # inside the representation sentence ("we act for the plaintiff"), and
    # `quoted` already carries it.
    role_quote = (data.get("role_quote") or "").strip()
    if role_quote and not Quotable(turn=quotable.turn).accepts(role_quote):
        basis = Basis.INFERRED
    if (role in (Role.PROSPECTIVE_CLAIMANT, Role.PROSPECTIVE_RESPONDENT)
            and basis is not Basis.STATED):
        return StatedPosture(Role.UNKNOWN, Basis.UNKNOWN, described, quoted,
                             refused="a prospective position was inferred rather than stated")
    correction = data.get("opponent_correction_quote") or ""
    if correction and (not isinstance(correction, str)
                       or not Quotable(turn=quotable.turn).accepts(correction)
                       or not against or against.casefold() not in correction.casefold()):
        correction = ""
    return StatedPosture(role, basis, described, quoted, opponent=against,
                         opponent_correction_quote=correction)
