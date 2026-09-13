"""PREPARATION THAT DOES NOT PUT WORDS IN A WITNESS'S MOUTH. BK-57-AC2. P31.

    from nm.domain.witness import WitnessPlan, ExpertInstruction, refuse_scripting

WHAT THIS IS FOR
------------------
Two of Appendix E's records had no implementation: `WitnessPlan` and
`ExpertInstruction`. They are the dangerous half of hearing preparation,
because both are produced by writing text about a person who has not spoken
yet, and the failure mode is not an error -- it is a plausible paragraph.

    A WITNESS PLAN that supplies the answer has contaminated the recollection
    it was meant to record, and no later step recovers it.

    AN EXPERT INSTRUCTION that supplies the conclusion has bought an opinion
    rather than obtained one, and it will be put to the expert in exactly
    those terms.

So neither type has a field an answer or a conclusion could be written into.
`topics` are SUBJECTS TO ASK ABOUT; `purpose` is THE QUESTION PUT. And because
prose reaches these fields from a model, `refuse_scripting` and
`refuse_leading` are backstops over the text -- not the mechanism, which is the
absence of the field, exactly as `nm/core/proof.py` argues for its own tripwire.

CONTACT IS LOGGED BECAUSE THE ALLEGATION IS UNFALSIFIABLE OTHERWISE
--------------------------------------------------------------------
Appendix E already requires `contact_log` and gives the reason: *F5 forbids
coaching and requires independent recollection to be preserved. The log is what
makes that auditable rather than asserted -- and it is the record that protects
the advocate if it is alleged.* `unlogged_contact` is the check that a plan
which claims a prior statement was taken can say who took it and who was there.

WHAT THIS MODULE DOES NOT OWN
-------------------------------
Who may concede, and on whose authority, is `nm/domain/authority.py`
(`permits`, `Act.CONCEDE`) over `nm/domain/commission.py`'s instructing/deciding
split. A second copy of that here would be the defect CLAUDE.md §4 asks about,
so the negotiation boundary is DERIVED in `nm/core/hearing.py` and no
concession type is declared in this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.text import blank, refuses_blank_text, snippet


class Availability(str, Enum):
    """Appendix E's enum, exactly. A MATERIAL WITNESS WHO CANNOT ATTEND
    CHANGES THE PROOF SEQUENCE, and finding out late is the whole problem."""

    CONFIRMED = "confirmed"
    EXPECTED = "expected"
    DOUBTFUL = "doubtful"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Availability":
        return cls.NOT_ASSESSED


class Methodology(str, Enum):
    """Appendix E's enum for an expert's method.

    `UNTESTED` and `NOT_ASSESSED` are different positions and the contract says
    so: one is a finding about the method, the other is that nobody looked.
    """

    TESTED = "tested"
    UNTESTED = "untested"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Methodology":
        return cls.NOT_ASSESSED


#: Appendix E's `WitnessPlan` required fields. The test asserts this against
#: `spec/schemas.yaml` rather than trusting it as a copy.
WITNESS_FIELDS: tuple[str, ...] = (
    "thread", "witness", "necessity", "materiality", "availability",
    "credibility", "interest", "prior_statements", "contradictions",
    "proof_sequence", "summons", "interpreter", "safety", "logistics_owner",
    "contact_log",
)

#: Appendix E's `ExpertInstruction` required fields, same rule.
EXPERT_FIELDS: tuple[str, ...] = (
    "thread", "expert", "discipline", "purpose", "material_supplied",
    "material_withheld", "assumptions", "instruction_balanced",
    "independence_statement", "methodology_tested", "limitations", "conflicts",
    "report",
)

#: PHRASES THAT SUPPLY AN ANSWER RATHER THAN ASK FOR ONE.
#:
#: Deliberately broad in the direction that costs a false positive: an advocate
#: told "this line reads as scripting, rephrase it" loses a minute, and a miss
#: puts a contaminated recollection in front of a court.
_SCRIPTING: tuple[str, ...] = (
    "you will say", "you should say", "you must say", "say that",
    "tell them that", "tell the court that", "your answer is",
    "answer that", "confirm that you", "agree that you", "state that you",
    "remember that you", "recall that you", "you remember",
    "do not mention", "don't mention", "avoid mentioning", "leave out the",
)

#: PHRASES THAT SUPPLY A CONCLUSION TO AN EXPERT.
#:
#: The contract's own words: *an expert asked a leading question produces a
#: leading answer.* Withholding material is covered by the record's
#: `material_withheld` field; this covers the question itself.
_LEADING: tuple[str, ...] = (
    "confirm that", "confirm our", "support our", "support the case",
    "establish that", "demonstrate that", "show that the", "conclude that",
    "opine that", "we need you to find", "we require a finding",
    "favourable opinion", "favorable opinion",
)


def refuse_scripting(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Every preparation line that supplies an answer. BK-57-AC2.

    The line between preparing a witness and coaching one is not a matter of
    degree -- it is whether the words came from the witness.
    """
    return _named(lines, _SCRIPTING,
                  "supplies the answer", "preparation asks a witness what they "
                  "recall; it does not tell them")


def refuse_leading(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Every instruction line that supplies the conclusion. BK-57-AC2.

    Same mechanism as `refuse_scripting`, over the expert's question rather
    than the witness's topics -- one shape, two populations, which is the
    arrangement CLAUDE.md's sweep rule asks for.
    """
    return _named(lines, _LEADING,
                  "supplies the conclusion", "an instruction states the "
                  "question; the expert states the answer")


def _named(lines: tuple[str, ...], shapes: tuple[str, ...], what: str,
           because: str) -> tuple[str, ...]:
    out: list[str] = []
    for line in lines:
        lowered = (line or "").lower()
        hit = next((s for s in shapes if s in lowered), "")
        if hit:
            out.append(f"{snippet(line, 60)!r} {what} ({hit!r}); {because}")
    return tuple(out)


@refuses_blank_text()
@dataclass(frozen=True)
class WitnessPlan:
    """Appendix E's record, implemented. One witness, and what protects their
    independence.

    EVERY FIELD BUT THE TWO IDENTIFIERS CARRIES A DEFAULT, and that is the same
    argument P30's `ActionProposal` makes: a plan under construction has to be
    REPRESENTABLE, or a caller obtains one by inventing a necessity. `problems`
    reports what is missing; the constructor does not force a sentence.
    """

    thread: str
    witness: str
    necessity: str = ""
    materiality: tuple[str, ...] = ()
    availability: Availability = Availability.NOT_ASSESSED
    credibility: dict = field(default_factory=dict)
    interest: str = ""
    prior_statements: tuple[dict, ...] = ()
    contradictions: tuple[dict, ...] = ()
    proof_sequence: int = 0
    summons: dict = field(default_factory=dict)
    interpreter: dict | None = None
    safety: str = ""
    logistics_owner: str = ""
    contact_log: tuple[dict, ...] = ()
    topics: tuple[str, ...] = ()
    """WHAT TO ASK ABOUT. Subjects, never answers -- there is no field on this
    record in which testimony could be written, which is the mechanism.
    `refuse_scripting` reads these as a backstop over model prose."""

    def problems(self) -> tuple[str, ...]:
        """Why this plan is not fit to work from. NAMED, never a flag."""
        out: list[str] = []
        if blank(self.necessity):
            out.append("nothing records why this witness is necessary, so "
                       "nobody can weigh calling them against the risk")
        if not self.materiality:
            out.append("this witness is linked to no fact in issue; a witness "
                       "carrying no pleaded fact is a risk with no upside")
        if self.availability is Availability.NOT_ASSESSED:
            out.append("nobody has established whether this witness can "
                       "attend")
        if blank(self.logistics_owner):
            out.append("no named owner is recorded for getting this witness to "
                       "the hearing; unowned logistics fail on the day")
        if self.summons.get("needed") and not self.summons.get("filed_at"):
            out.append("a summons is recorded as needed and not as filed")
        out.extend(refuse_scripting(self.topics))
        out.extend(self.unlogged_contact())
        return tuple(out)

    def unlogged_contact(self) -> tuple[str, ...]:
        """Prior statements this plan cannot say were properly taken.

        Appendix E's reason for `contact_log`: the log is what makes the
        no-coaching rule auditable rather than asserted. A prior statement with
        no contact recording who took it and who was present is the shape an
        allegation lands on.
        """
        if not self.prior_statements:
            return ()
        taken = [c for c in self.contact_log
                 if not blank(str(c.get("by", ""))) and "present" in c]
        if taken:
            return ()
        return (
            f"{len(self.prior_statements)} prior statement(s) are recorded and "
            f"no contact entry says who took one or who was present; the "
            f"contact log is what makes independent recollection auditable "
            f"rather than asserted",)

    @property
    def contaminated(self) -> bool:
        """Whether anything in this plan supplies testimony. ANY hit is one."""
        return bool(refuse_scripting(self.topics))


@refuses_blank_text()
@dataclass(frozen=True)
class ExpertInstruction:
    """Appendix E's record, implemented. An expert instructed independently.

    `instruction_balanced` is NOT a claim this type will make on its own:
    `problems` refuses an instruction marked balanced whose purpose reads as
    leading, because a boolean somebody set is not evidence about the sentence
    beside it.
    """

    thread: str
    expert: str
    discipline: str = ""
    purpose: str = ""
    material_supplied: tuple[str, ...] = ()
    material_withheld: tuple[dict, ...] = ()
    assumptions: tuple[str, ...] = ()
    instruction_balanced: bool = False
    independence_statement: str = ""
    methodology_tested: Methodology = Methodology.NOT_ASSESSED
    limitations: tuple[str, ...] = ()
    conflicts: dict = field(default_factory=dict)
    report: dict | None = None
    """`None` until received. Appendix E's own word for it."""

    def problems(self) -> tuple[str, ...]:
        out: list[str] = []
        if blank(self.discipline):
            out.append("no discipline is recorded, so nothing bounds what this "
                       "expert may speak to")
        if blank(self.purpose):
            out.append("no question is recorded; an expert with no question "
                       "answers the one they infer")
        if not self.material_supplied:
            out.append("no material is recorded as supplied")
        if not self.assumptions:
            out.append("no assumptions are stated; an unstated assumption is "
                       "an opinion resting on air")
        if blank(self.independence_statement):
            out.append("independence is not recorded, and it is recorded "
                       "rather than implied")
        if "assessed_by" not in self.conflicts:
            out.append("nobody is recorded as having assessed conflicts; an "
                       "expert conflict surfaces in cross-examination if it "
                       "does not surface here")
        leading = refuse_leading((self.purpose,) + self.assumptions)
        if leading and self.instruction_balanced:
            out.append("this instruction is marked balanced and reads as "
                       "leading, which is a claim contradicted by its own text")
        out.extend(leading)
        return tuple(out)

    def unsupported_by_report(self) -> tuple[str, ...]:
        """Conclusions asserted with no report behind them.

        `report` is `None` until received, and a preparation pack that carries
        an expert's conclusion before the report exists has invented one.
        """
        if self.report is None:
            return ("no report has been received, so this expert supports no "
                    "conclusion yet",)
        if not self.report.get("conclusions"):
            return ("a report is recorded as received and lists no "
                    "conclusions",)
        return ()
