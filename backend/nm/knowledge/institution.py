"""THE CURATED PRE-INSTITUTION CONDITIONS. LB-121.

The shapes and the reasoning about them are in `backend/nm/ports/institution.py`.
This module is the curation: which statutes require something before a
proceeding is instituted, and what each requires. Nothing here asserts
current law -- every row points at the provision that must be RETRIEVED AND
READ BACK before it is relied on.
"""
from __future__ import annotations

from nm.domain.matter import CauseOfAction
from nm.domain.traceability import implements
from nm.ports.institution import Against, Condition, Engagement

#: EVERY CONDITION THIS PRODUCT KNOWS, by its key. One table, so a condition
#: reached from the cause and one reached from the opponent cannot drift.
#:
#: CURATED CONSERVATIVELY. A condition whose engagement is genuinely arguable
#: is left OUT rather than guessed: an absent row leaves the threshold reading
#: NOT ASSESSED, which is a worse answer and an honest one, while a wrong row
#: is a confident answer that stops an advocate filing.
#:
#: NOT COUNSEL-REVIEWED. Every provision below is to be retrieved and verified
#: before release; LB-121 records that a practising Telangana advocate signs
#: off these entries on the BK-85-AC3 pattern.
CONDITIONS: dict[str, Condition] = {
    "ni_138_demand_notice": Condition(
        key="ni_138_demand_notice",
        said="the written demand for payment after the cheque was returned",
        act="Negotiable Instruments Act, 1881",
        provision="138",
        curated_from="Negotiable Instruments Act, 1881, s.138 provisos (a) to "
                     "(c) -- presentation within validity, a written demand "
                     "made within the statutory period of the information of "
                     "return, and the drawer's failure to pay within the "
                     "statutory window",
        satisfied_when="the file shows when the bank returned the cheque, when "
                       "the written demand was made, and how it was sent",
        period_said="the proviso fixes the window for the demand from the "
                    "information of return, and a further window for payment "
                    "before the cause of action arises -- read the section for "
                    "both, and do not compute either from memory"),
    "ni_142_complaint_window": Condition(
        key="ni_142_complaint_window",
        said="the window for making the complaint once the cause of action "
             "arose",
        act="Negotiable Instruments Act, 1881",
        provision="142",
        curated_from="Negotiable Instruments Act, 1881, s.142(1)(b) -- the "
                     "complaint is made within the period fixed there from the "
                     "date on which the cause of action arises under the "
                     "proviso (c) to s.138",
        satisfied_when="the file shows the date the payment window closed, so "
                       "the complaint window can be run from it",
        period_said="s.142(1)(b) fixes the period and the section provides for "
                    "a complaint made after it on sufficient cause shown; read "
                    "both rather than assuming either"),
    "cpc_80_government_notice": Condition(
        key="cpc_80_government_notice",
        said="the notice to the Government or public officer before suing",
        act="Code of Civil Procedure, 1908",
        provision="80",
        curated_from="Code of Civil Procedure, 1908, s.80 -- notice before "
                     "instituting a suit against the Government or a public "
                     "officer in respect of an act purporting to be done in "
                     "official capacity, with the leave route in s.80(2) for "
                     "urgent or immediate relief",
        satisfied_when="the file shows the notice served, on whom, when, and "
                       "what it stated -- or that leave under s.80(2) is "
                       "sought instead",
        period_said="s.80 fixes the waiting period after the notice before the "
                    "suit may be instituted; read the section for it"),
    "tpa_106_lease_notice": Condition(
        key="tpa_106_lease_notice",
        said="the notice terminating the lease",
        act="Transfer of Property Act, 1882",
        provision="106",
        curated_from="Transfer of Property Act, 1882, s.106 -- the notice "
                     "determining a lease, whose length depends on the purpose "
                     "of the lease, and the manner of its service",
        satisfied_when="the file shows the purpose of the lease, and the "
                       "notice given, its length, and how it was served",
        period_said="s.106 fixes different notice lengths by the purpose of "
                    "the lease; the purpose is established from the file "
                    "before the length is read"),
}


#: WHICH CAUSES ENGAGE WHICH CONDITIONS. Exact membership on a closed
#: vocabulary -- the whole point of `CauseOfAction` being closed.
#:
#: A cause absent from this table engages nothing THROUGH THE CAUSE. That is
#: not a finding that nothing is required: `assess` says so in terms, and the
#: opponent-driven conditions below are reached separately.
BY_CAUSE: dict[CauseOfAction, tuple[str, ...]] = {
    CauseOfAction.CHEQUE_DISHONOUR: ("ni_138_demand_notice",
                                     "ni_142_complaint_window"),
    CauseOfAction.POSSESSION_FROM_TENANT: ("tpa_106_lease_notice",),
}

#: WHICH OPPONENTS ENGAGE WHICH CONDITIONS, whatever the cause. Kept apart
#: from `BY_CAUSE` because the question is different: s.80 turns on who is
#: being sued, not on what for, and folding it into the cause table would make
#: it invisible for every cause nobody listed it under.
BY_OPPONENT: dict[Against, tuple[str, ...]] = {
    Against.GOVERNMENT: ("cpc_80_government_notice",),
}


@implements("D1")
def engaged(cause: CauseOfAction, against: Against = Against.UNKNOWN,
            ) -> tuple[Engagement, ...]:
    """Every pre-institution condition this cause and opponent bring into play.

    ORDER IS THE TABLE'S, not the caller's, so two threads with the same cause
    read the same. Duplicates cannot arise: one condition is engaged once
    however many routes reach it.
    """
    seen: dict[str, Engagement] = {}
    for key in BY_CAUSE.get(cause, ()):
        seen.setdefault(key, Engagement(
            condition=CONDITIONS[key],
            why=f"the cause reads as {cause.value.replace('_', ' ')}"))
    for key in BY_OPPONENT.get(against, ()):
        seen.setdefault(key, Engagement(
            condition=CONDITIONS[key],
            why="the proceeding would be against the Government or a public "
                "officer"))
    return tuple(seen.values())


@implements("D1")
def undecided(cause: CauseOfAction, against: Against) -> tuple[Condition, ...]:
    """Conditions that CANNOT YET BE REACHED because a key is unestablished.

    THE HALF THAT MAKES SILENCE VISIBLE. `engaged` answers from what is known;
    this answers from what is not. An unestablished opponent means s.80 is
    neither engaged nor ruled out, and reporting only the engaged set would
    read as though it had been considered and did not arise.

    A cause nobody has established engages nothing through the cause, and every
    cause-driven condition is undecided for the same reason.
    """
    out: dict[str, Condition] = {}
    if cause is CauseOfAction.NOT_ESTABLISHED:
        for keys in BY_CAUSE.values():
            for key in keys:
                out.setdefault(key, CONDITIONS[key])
    if against is Against.UNKNOWN:
        for keys in BY_OPPONENT.values():
            for key in keys:
                out.setdefault(key, CONDITIONS[key])
    return tuple(out.values())


__all__ = ["Against", "Condition", "Engagement", "CONDITIONS", "BY_CAUSE",
           "BY_OPPONENT", "engaged", "undecided"]
