"""THE CURATED SUCCESSIONS. LB-120.

The shapes and the reasoning about them are in `backend/nm/ports/governing_law.py`.
This module is the curation: which statute replaced which, when it commenced,
and the saving provision that decides a matter straddling that date.

NOTHING HERE ASSERTS CURRENT LAW. Every row points at text that must be
RETRIEVED AND READ BACK. In particular the saving provisions named below decide
the hard cases and are NOT paraphrased here -- an advocate reads them, and this
product's job is to say which one to read and why.

NOT COUNSEL-REVIEWED. LB-120 records that a practising advocate signs off these
entries before release, on the BK-85-AC3 pattern.
"""
from __future__ import annotations

from datetime import date

from nm.domain.traceability import implements
from nm.ports.governing_law import Governing, Limb, Pending, Succession

#: THE 1 JULY 2024 SUCCESSION, one row per limb because the limbs are decided
#: by different facts and a single row would force one answer for all three.
#:
#: CURATED CONSERVATIVELY. A succession whose engagement is arguable is left
#: out rather than guessed: an absent row leaves the question unanswered, which
#: is a worse answer and an honest one, while a wrong row picks the governing
#: law by assumption and every citation under it reads correct.
SUCCESSIONS: tuple[Succession, ...] = (
    Succession(
        limb=Limb.SUBSTANTIVE,
        replaced="Indian Penal Code, 1860",
        replacing="Bharatiya Nyaya Sanhita, 2023",
        commenced_on=date(2024, 7, 1),
        saving="Bharatiya Nyaya Sanhita, 2023, s.358 (repeal and savings)",
        curated_from="Bharatiya Nyaya Sanhita, 2023, s.358, read with the "
                     "commencement notification and Constitution Article "
                     "20(1) -- no person is convicted of an offence except "
                     "under the law in force at the time of the act"),
    Succession(
        limb=Limb.PROCEDURAL,
        replaced="Code of Criminal Procedure, 1973",
        replacing="Bharatiya Nagarik Suraksha Sanhita, 2023",
        commenced_on=date(2024, 7, 1),
        saving="Bharatiya Nagarik Suraksha Sanhita, 2023, s.531 (repeal and "
               "savings)",
        curated_from="Bharatiya Nagarik Suraksha Sanhita, 2023, s.531, read "
                     "with the commencement notification -- the saving "
                     "provision governs appeals, applications, trials, "
                     "inquiries and investigations pending at commencement"),
    Succession(
        limb=Limb.EVIDENTIARY,
        replaced="Indian Evidence Act, 1872",
        replacing="Bharatiya Sakshya Adhiniyam, 2023",
        commenced_on=date(2024, 7, 1),
        saving="Bharatiya Sakshya Adhiniyam, 2023, s.170 (repeal and savings)",
        curated_from="Bharatiya Sakshya Adhiniyam, 2023, s.170, read with the "
                     "commencement notification. MEASURED 25 September 2026: "
                     "the Bharatiya Sakshya Adhiniyam is NOT among the "
                     "principal Acts measured in docs/BASELINE.md section 2.1, "
                     "so its text must be measured in raw_data/ before this "
                     "row is relied on"),
)


@implements("D4")
def governing(limb: Limb, on: date | None, pending: Pending) -> Governing:
    """Which Act governs this limb, or an honest account of what is missing.

    THE DATE ALONE DECIDES THE SUBSTANTIVE LIMB, because what conduct was an
    offence is fixed when it happened. Conduct before commencement is governed
    by the replaced Act however long afterwards it is charged, and the saving
    provision is named so the advocate reads it rather than this sentence.

    THE PROCEDURAL AND EVIDENTIARY LIMBS NEED MORE THAN THE DATE. A proceeding
    already under way at commencement is the case the saving provision exists
    for, so where that is unknown NO ACT IS NAMED -- the alternative is picking
    the governing procedure by assumption, which is the defect this whole
    module refuses.
    """
    row = next((s for s in SUCCESSIONS if s.limb is limb), None)
    if row is None:
        return Governing(limb=limb,
                         because="no succession this product holds affects "
                                 "this limb; that is what the curated table "
                                 "says, not a search of every statute")
    if on is None:
        return Governing(
            limb=limb,
            because=(f"the date that decides this is not established, so "
                     f"neither {row.replaced} nor {row.replacing} is named. "
                     f"Give me the date and I will read the saving provision "
                     f"against it"),
            read_the_saving=row.saving)
    if on < row.commenced_on:
        return Governing(
            limb=limb, act=row.replaced,
            because=(f"{on.isoformat()} is before {row.replacing} commenced on "
                     f"{row.commenced_on.isoformat()}"),
            read_the_saving=row.saving)
    if limb is Limb.SUBSTANTIVE:
        return Governing(
            limb=limb, act=row.replacing,
            because=(f"{on.isoformat()} is on or after {row.replacing} "
                     f"commenced on {row.commenced_on.isoformat()}"),
            read_the_saving=row.saving)
    if pending is Pending.YES:
        return Governing(
            limb=limb, act=row.replaced,
            because=(f"the proceeding was already under way when "
                     f"{row.replacing} commenced on "
                     f"{row.commenced_on.isoformat()}"),
            read_the_saving=row.saving)
    if pending is Pending.NO:
        return Governing(
            limb=limb, act=row.replacing,
            because=(f"nothing was under way when {row.replacing} commenced "
                     f"on {row.commenced_on.isoformat()}"),
            read_the_saving=row.saving)
    return Governing(
        limb=limb,
        because=(f"whether a proceeding was already under way when "
                 f"{row.replacing} commenced on "
                 f"{row.commenced_on.isoformat()} is not established, and that "
                 f"is what the saving provision turns on. Tell me and I will "
                 f"name the Act"),
        read_the_saving=row.saving)


def successions() -> tuple[Succession, ...]:
    return SUCCESSIONS


__all__ = ["SUCCESSIONS", "governing", "successions"]
