"""THE CURATED PROCEDURAL PERIODS. LB-124.

The shapes and the reasoning about them are in
`backend/nm/ports/procedural_period.py`. This module is the curation: which
clocks a role brings into play, what starts each, whether it binds and whether
it can be extended. Nothing here asserts current law -- every row points at the
provision or decision that must be RETRIEVED AND READ BACK before it is relied
on, and NO ROW STATES A NUMBER OF DAYS.

CURATED CONSERVATIVELY. A period whose engagement or whose reading is genuinely
arguable is left OUT rather than guessed: an absent row leaves the advocate
where they were, while a wrong row tells them a defence is safe when it is
running out, or lost when it is not.

NOT COUNSEL-REVIEWED. Every provision and judgment below is to be retrieved and
verified before release; LB-124 records that a practising Telangana advocate
signs off these entries on the BK-85-AC3 pattern.
"""
from __future__ import annotations

from nm.domain.matter import Role
from nm.domain.traceability import implements
from nm.ports.procedural_period import (
    Bindingness,
    Extension,
    Period,
    Running,
    Track,
)

#: WHY s.5 IS NOT AN EXTENSION ROUTE ON ANY ROW BELOW, recorded because the
#: plan row named it and the temptation to reach for it is exactly the mistake.
#:
#: Limitation Act, 1963, s.5 condones delay in INSTITUTING an appeal or
#: application -- it is not a general power to relieve against a period running
#: inside a suit already on foot. Each period below is extended, if at all, by
#: its OWN provision: the proviso to Order VIII r.1, Order XXXVII r.3(7), or
#: nothing. Offering s.5 as the route would send an advocate to make an
#: application the court has no occasion to entertain, which is a confident
#: answer to a question the rule does not ask.
#:
#: `tests/test_the_clocks_that_run_inside_a_proceeding.py` holds this: no row's
#: extension route may cite s.5.
NOT_THE_EXTENSION_ROUTE = "Limitation Act, 1963, s.5"

#: EVERY PERIOD THIS PRODUCT KNOWS, by its key. One table, so a period reached
#: from the role and one reached from the track cannot drift.
PERIODS: dict[str, Period] = {
    "cpc_o8_r1_written_statement_ordinary": Period(
        key="cpc_o8_r1_written_statement_ordinary",
        said="the time to file the written statement in an ordinary suit",
        act="Code of Civil Procedure, 1908",
        provision="O8R1",
        curated_from="Code of Civil Procedure, 1908, Order VIII r.1 and its "
                     "proviso, read with Kailash v Nanhku (2005) 4 SCC 480 on "
                     "the proviso being directory in an ordinary suit",
        runs_from="the date of service of summons on the defendant",
        period_said="Order VIII r.1 fixes the period and its proviso fixes the "
                    "outer period for which reasons must be recorded; read the "
                    "rule for both",
        bindingness=Bindingness.DIRECTORY,
        extension=Extension.AVAILABLE,
        extension_said="the court may permit a written statement after the "
                       "proviso's period on reasons recorded in writing -- "
                       "that is a discretion to be asked for, not a right",
        track=Track.ORDINARY),
    "cpc_o8_r1_written_statement_commercial": Period(
        key="cpc_o8_r1_written_statement_commercial",
        said="the time to file the written statement in a commercial suit",
        act="Code of Civil Procedure, 1908",
        provision="O8R1",
        curated_from="Code of Civil Procedure, 1908, Order VIII r.1 as it "
                     "applies to commercial disputes of a specified value "
                     "under the Commercial Courts Act, 2015, read with SCG "
                     "Contracts (India) Pvt Ltd v K S Chamankar Infrastructure "
                     "Pvt Ltd (2019) 12 SCC 210 on the outer limit and the "
                     "forfeiture of the right",
        runs_from="the date of service of summons on the defendant",
        period_said="the proviso to Order VIII r.1 as applied to commercial "
                    "suits fixes an OUTER limit after which the right to file "
                    "is forfeited and the written statement is not taken on "
                    "record; read the proviso for the period",
        bindingness=Bindingness.MANDATORY,
        extension=Extension.BARRED,
        extension_said="the outer limit is not extendable and no condonation "
                       "route runs to it -- the right to file is forfeited and "
                       "the court has no discretion to take the pleading on "
                       "record",
        track=Track.COMMERCIAL),
    "cpc_o37_r3_leave_to_defend": Period(
        key="cpc_o37_r3_leave_to_defend",
        said="the time to enter appearance and to apply for leave to defend a "
             "summary suit",
        act="Code of Civil Procedure, 1908",
        provision="O37R3",
        curated_from="Code of Civil Procedure, 1908, Order XXXVII r.3 -- "
                     "appearance, the summons for judgment, and the "
                     "application for leave to defend, with the power in "
                     "r.3(7) to excuse a delay in entering appearance or in "
                     "applying for leave on sufficient cause",
        runs_from="the date of service of the summons, and separately the date "
                  "of service of the summons for judgment",
        period_said="Order XXXVII r.3 fixes each period; read the rule, and "
                    "note that TWO clocks run here and missing the first has a "
                    "different consequence from missing the second",
        bindingness=Bindingness.MANDATORY,
        extension=Extension.AVAILABLE,
        extension_said="Order XXXVII r.3(7) empowers the court to excuse the "
                       "delay on sufficient cause -- so the period binds and "
                       "is nevertheless relievable, which is why bindingness "
                       "and extension are separate answers"),
    "cpc_148a_caveat_life": Period(
        key="cpc_148a_caveat_life",
        said="how long a caveat stays in force",
        act="Code of Civil Procedure, 1908",
        provision="148A",
        curated_from="Code of Civil Procedure, 1908, s.148A -- the right to "
                     "lodge a caveat, the notice the caveator is entitled to, "
                     "and s.148A(5) on the period for which the caveat remains "
                     "in force",
        runs_from="the date the caveat was lodged",
        period_said="s.148A(5) fixes the period after which the caveat is no "
                    "longer in force; read the sub-section for it",
        bindingness=Bindingness.MANDATORY,
        extension=Extension.BARRED,
        extension_said="a caveat is not extended -- it lapses, and a fresh "
                       "caveat is lodged in its place"),
}


#: WHICH ROLES BRING WHICH PERIODS INTO PLAY. Exact membership on the closed
#: `Role` vocabulary -- the whole point of that vocabulary being closed.
#:
#: A role absent from this table engages nothing. That is not a finding that
#: no period runs: `undecided` answers from what is not established, and an
#: unknown role leaves every period undecided rather than inapplicable.
BY_ROLE: dict[Role, tuple[str, ...]] = {
    Role.DEFENDANT: ("cpc_o8_r1_written_statement_ordinary",
                     "cpc_o8_r1_written_statement_commercial",
                     "cpc_o37_r3_leave_to_defend"),
    Role.PROSPECTIVE_RESPONDENT: ("cpc_148a_caveat_life",),
}


@implements("D3")
def engaged(role: Role, track: Track) -> tuple[Running, ...]:
    """Every period this role and track bring into play.

    A TRACK-SPECIFIC PERIOD IS NOT ENGAGED UNTIL THE TRACK IS ESTABLISHED, and
    that is the rule LB-124 exists for. Applying the ordinary reading because
    nobody said the suit was commercial would tell a defendant their written
    statement is late-but-curable when the right to file has been forfeited;
    applying the commercial reading the other way would tell them a defence is
    lost that is not. Both are one sentence of confident wrong advice, so
    neither is reachable: the row goes to `undecided` instead.

    ORDER IS THE TABLE'S, not the caller's, so two threads with the same role
    read the same.
    """
    out: list[Running] = []
    for key in BY_ROLE.get(role, ()):
        period = PERIODS[key]
        if period.track is not Track.NOT_ESTABLISHED and period.track is not track:
            continue
        out.append(Running(
            period=period,
            why=(f"the client is the {role.value.replace('_', ' ')} in this "
                 f"proceeding")
            if period.track is Track.NOT_ESTABLISHED else
            (f"the client is the {role.value.replace('_', ' ')} and the suit "
             f"is on the {period.track.value} track")))
    return tuple(out)


@implements("D3")
def undecided(role: Role, track: Track) -> tuple[Period, ...]:
    """Periods that CANNOT YET BE REACHED because a key is unestablished.

    THE HALF THAT MAKES SILENCE VISIBLE. `engaged` answers from what is known;
    this answers from what is not. An unestablished track means the written
    statement period is neither engaged nor ruled out, and reporting only the
    engaged set would read as though it had been considered and did not arise.
    """
    out: dict[str, Period] = {}
    if track is Track.NOT_ESTABLISHED:
        for key in BY_ROLE.get(role, ()):
            period = PERIODS[key]
            if period.track is not Track.NOT_ESTABLISHED:
                out.setdefault(key, period)
    if role not in BY_ROLE:
        for keys in BY_ROLE.values():
            for key in keys:
                out.setdefault(key, PERIODS[key])
    return tuple(out.values())


__all__ = ["NOT_THE_EXTENSION_ROUTE", "PERIODS", "BY_ROLE", "engaged", "undecided"]
