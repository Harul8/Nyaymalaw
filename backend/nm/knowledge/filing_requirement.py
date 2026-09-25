"""WHAT WOULD ANSWER FORUM, VALUATION AND COURT FEE -- and whether it is held.

LB-125. The shapes and the reasoning about them are in
`backend/nm/ports/filing_requirement.py`. This module is the curation: which
instruments answer each requirement, and the MEASUREMENT of whether the corpus
intends to hold them.

THE MEASUREMENT IS MADE HERE AND NOT WRITTEN DOWN ANYWHERE. `readiness` asks
the manifest -- the curated assertion of intended coverage -- at the moment it
is called. A sentence in this file saying the Telangana schedule is not held
would be a claim about the corpus that nothing compares to the corpus, which is
B-141 exactly: a backlog row saying the authority index had never run while it
sat on disk, unnoticed for eight days. The day the Act is ingested, this
answers differently and no line changes.

MEASURED 25 September 2026, for the record and not as the mechanism:
`pipeline/manifest.yaml` carries 22 entries and none of them is a court-fees
and suits valuation Act or a civil courts Act. That measurement is against the
MANIFEST -- intended coverage -- and is not a claim about what
`legal_database/raw_data/` holds, which is measured there and nowhere else.

NOT COUNSEL-REVIEWED. Every title and provision below is to be retrieved and
verified before release; LB-125 records that a practising Telangana advocate
signs off these entries on the BK-85-AC3 pattern.
"""
from __future__ import annotations

from nm.domain.traceability import implements
from nm.ports.filing_requirement import (
    Authority,
    Readiness,
    Requirement,
    SourceState,
)

#: WHAT WOULD ANSWER EACH REQUIREMENT. Titles, exactly as an Act is titled,
#: because they are matched against the manifest by exact title.
#:
#: THE TERRITORIAL ORDER IS THE CODE'S, NOT OURS. CPC ss.15-20 fix the order in
#: which the question is asked, and the Code is held; what is missing is the
#: PECUNIARY tier, which is state law. So `FORUM` is deliberately answered by
#: two instruments of which one is held: a requirement half-answered is not
#: answered, and saying which half is missing is the useful part.
AUTHORITIES: dict[Requirement, tuple[Authority, ...]] = {
    Requirement.FORUM: (
        Authority(
            requirement=Requirement.FORUM,
            act_name="Code of Civil Procedure, 1908",
            what_it_would_answer="where the suit may be instituted -- the "
                                 "order in which subject matter, the place of "
                                 "the cause of action and the defendant's "
                                 "residence or business are asked",
            curated_from="Code of Civil Procedure, 1908, ss.15 to 20 -- suits "
                         "to be instituted in the court of the lowest grade "
                         "competent to try them, and the territorial rules "
                         "that follow"),
        Authority(
            requirement=Requirement.FORUM,
            act_name="Telangana Civil Courts Act, 1972",
            what_it_would_answer="the pecuniary limit of each grade of civil "
                                 "court in this state, which decides which "
                                 "court is the lowest grade competent",
            curated_from="the state enactment constituting the civil courts "
                         "and fixing their pecuniary jurisdiction, as adapted "
                         "for Telangana -- the TITLE AND ITS ADAPTATION ARE "
                         "TO BE VERIFIED before this row is relied on"),
    ),
    Requirement.VALUATION: (
        Authority(
            requirement=Requirement.VALUATION,
            act_name="Telangana Court Fees and Suits Valuation Act, 1956",
            what_it_would_answer="how a suit for this relief is valued, which "
                                 "the pecuniary tier and the fee both read",
            curated_from="the court-fees and suits-valuation enactment as "
                         "adapted for Telangana, whose valuation sections fix "
                         "the value by the relief sought -- the TITLE AND ITS "
                         "ADAPTATION ARE TO BE VERIFIED"),
    ),
    Requirement.COURT_FEES: (
        Authority(
            requirement=Requirement.COURT_FEES,
            act_name="Telangana Court Fees and Suits Valuation Act, 1956",
            what_it_would_answer="the fee payable on the plaint, from the "
                                 "schedule in force",
            curated_from="the schedules to the court-fees and suits-valuation "
                         "enactment as adapted for Telangana, AS AMENDED -- "
                         "the schedule in force on the date of filing is the "
                         "one that governs"),
    ),
}

#: THE VERSION OF EACH SCHEDULE, BY ACT TITLE. EMPTY, AND THAT IS THE POINT.
#:
#: A fee computed from a schedule whose version nobody recorded is wrong in a
#: way that reads exactly like right -- the amendment that moved it leaves no
#: trace in the figure. So nothing is computed until a version is recorded
#: here with the instrument that fixed it, and an entry added without one
#: cannot make a fee computable: `readiness` reads THIS table, not the presence
#: of the Act.
#:
#: This is the same argument as `nm.knowledge.artefact` (defect shape S11): the
#: dense index was knowable as unusable ONLY because it shipped an identity.
#: A schedule with no version is that index with no `identity.json`.
SCHEDULE_VERSIONS: dict[str, str] = {}


def _titles(manifest) -> frozenset[str]:
    """Every Act title the manifest intends, exactly as written.

    EXACT, NEVER OVERLAP. CLAUDE.md section 5 measured three wrong Acts in one
    hour from shared words -- `Indian` matched the Evidence Act to an Easements
    question, and the shared year matched it to the Transfer of Property Act.
    A wrong Act here decides the fee.
    """
    return frozenset(e.act_name for e in getattr(manifest, "entries", ()))


@implements("D1")
def readiness(requirement: Requirement, manifest=None) -> Readiness:
    """Whether this requirement can be answered, and what is in the way.

    FOUR ANSWERS AND THREE OF THEM ARE REASONS NOT TO COMPUTE. A missing
    manifest is NOT_MEASURED, never NOT_INTENDED: an installation that cannot
    ask has not learned that the answer is no. A missing Act names the title.
    A held Act with no recorded schedule version is HELD_UNVERSIONED, which is
    not a weaker held -- it is a different thing wrong, and the advocate is
    told which.
    """
    authorities = AUTHORITIES.get(requirement, ())
    if manifest is None:
        return Readiness(
            requirement=requirement, state=SourceState.NOT_MEASURED,
            why="nothing on this installation could be asked which instruments "
                "are held, so whether this can be answered is unknown -- "
                "which is not the same as knowing it cannot",
            missing=tuple(a.act_name for a in authorities))

    held = _titles(manifest)
    absent = tuple(a.act_name for a in authorities if a.act_name not in held)
    if absent:
        return Readiness(
            requirement=requirement, state=SourceState.NOT_INTENDED,
            why=(f"this is read from {len(authorities)} instrument(s) and the "
                 f"corpus does not intend to hold "
                 f"{'; '.join(absent)}. Measured against the manifest's "
                 f"intended coverage, not guessed from a search returning "
                 f"nothing"),
            missing=absent)

    unversioned = tuple(a.act_name for a in authorities
                        if a.act_name not in SCHEDULE_VERSIONS)
    if unversioned:
        return Readiness(
            requirement=requirement, state=SourceState.HELD_UNVERSIONED,
            why=(f"{'; '.join(unversioned)} is held, and no version of its "
                 f"schedule is recorded. A figure from a schedule whose "
                 f"version nobody recorded is wrong in a way that reads "
                 f"exactly like right, so none is computed"),
            missing=unversioned)

    return Readiness(
        requirement=requirement, state=SourceState.HELD_AND_VERSIONED,
        why=("every instrument this requirement is read from is held, at a "
             "recorded version"))


__all__ = ["AUTHORITIES", "SCHEDULE_VERSIONS", "readiness"]
