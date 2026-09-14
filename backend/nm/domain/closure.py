"""CLOSING A MATTER, AND OPENING IT AGAIN. BK-59-AC2, BK-59-AC3. P32.

    from nm.domain.closure import ClosureRecord, Lifecycle, refuse_closure

WHAT THIS IS FOR
------------------
Closing a matter is the point at which everything nobody finished stops being
visible. So the question is not *may we close it* but *what is still owed, and
who owes it after we do*:

    A closure that swallows a live obligation is the most expensive kind of
    tidy. The deadline still exists; only the product's view of it has gone.

`refuse_closure` names every live obligation that is neither resolved nor
explicitly transferred, and `ClosureRecord.blockers` carries them so the answer
travels with the record rather than being recomputed by whoever asks.

ARCHIVE, CLOSE AND DELETE ARE THREE THINGS
--------------------------------------------
BK-59-AC3 says so directly, and P33 already made the same distinction for
material: `RESTRICT_ACCESS`, `REVIEW_RETENTION` and `ERASE` are separate
actions there. `Lifecycle` keeps them separate here for the matter, and
`retention` on the record points at the P33 request that owns the material --
this module does not decide what happens to bytes, and having two owners of
that decision is the §4 defect.

REOPENING RECHECKS RATHER THAN RESUMES
----------------------------------------
A matter reopened after six months is not the matter that was closed. The
permissions may have lapsed, the instruction may have changed, the law may
have moved and the material may have been erased under a retention decision.
`reopen_checks` returns what must be re-established, and it returns them as
work to do rather than as a refusal: refusing to reopen would leave an
advocate unable to act on a live development.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class Lifecycle(str, Enum):
    """Where the MATTER is. Not where its material is -- P33 owns that."""

    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"
    """Closed AND put beyond ordinary view. Still held, still restorable, and
    emphatically not erased -- the conflation BK-59-AC3 refuses."""

    REOPENED = "reopened"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_established(cls) -> "Lifecycle":
        return cls.NOT_ASSESSED

    @property
    def is_live(self) -> bool:
        return self in (Lifecycle.OPEN, Lifecycle.REOPENED)


@refuses_blank_text("until", "owner")
@dataclass(frozen=True)
class Obligation:
    """Something still owed at the moment of closing.

    `owner` is exempt from the blank rule because an unowned obligation must be
    REPRESENTABLE -- that is precisely the state `refuse_closure` exists to
    report. Requiring an owner would make the dangerous case unconstructable
    and the check unprovable.
    """

    what: str
    until: str = ""
    owner: str = ""
    resolved: bool = False
    transferred_to: str = ""

    @property
    def is_live(self) -> bool:
        return not self.resolved and blank(self.transferred_to)


#: Appendix E's `ClosureRecord`, required fields. The test asserts this against
#: `assurance/specification/schemas.yaml` rather than trusting the copy.
CLOSURE_FIELDS: tuple[str, ...] = (
    "matter", "closed_by", "closed_at", "money", "originals", "work_product",
    "continuing_obligations", "retention", "closure_summary_sent_at",
    "lessons", "blockers",
)


@refuses_blank_text("closed_at", "closure_summary_sent_at")
@dataclass(frozen=True)
class ClosureRecord:
    """Appendix E's record, implemented. BK-59-AC2.

    `closed_at` is exempt and empty until the closure actually happens: a
    record that had to carry a date to exist would force a caller to invent
    one, and `blockers` is what says the closure has not happened yet.
    """

    matter: str
    closed_by: str
    closed_at: str = ""
    money: dict = field(default_factory=dict)
    originals: tuple[dict, ...] = ()
    work_product: dict = field(default_factory=dict)
    continuing_obligations: tuple[Obligation, ...] = ()
    retention: str = ""
    """The P33 retention request id that owns what happens to the material.
    A closure that decided retention itself would be a second owner of a
    question P33 already answers."""

    closure_summary_sent_at: str = ""
    lessons: dict = field(default_factory=dict)
    lifecycle: Lifecycle = Lifecycle.OPEN

    @property
    def blockers(self) -> tuple[str, ...]:
        return refuse_closure(self)

    @property
    def complete(self) -> bool:
        return not self.blockers


def refuse_closure(record: ClosureRecord) -> tuple[str, ...]:
    """Every reason this matter may not close. Empty means it may.

    A POPULATION, not a boolean, so the advocate is told WHICH obligation is
    still live. "Cannot close" sends them looking through the file.
    """
    out: list[str] = []
    for obligation in record.continuing_obligations:
        if obligation.is_live:
            out.append(
                f"{obligation.what!r} is still owed and is neither resolved "
                f"nor transferred"
                + (f" (owner: {obligation.owner})" if obligation.owner
                   else " and nobody owns it"))
    if blank(record.retention):
        out.append(
            "no retention decision covers this matter's material; closing "
            "without one leaves the file held on nobody's authority")
    if not record.work_product:
        out.append(
            "the work product has not been exported, so closing would put it "
            "beyond the advocate's reach")
    if blank(record.closed_by):
        out.append("nobody is recorded as closing this matter")
    return tuple(out)


def reopen_checks(record: ClosureRecord, *, months_closed: int = 0,
                  ) -> tuple[str, ...]:
    """What must be re-established before a reopened matter is worked. BK-59-AC3.

    RETURNED AS WORK, NOT AS A REFUSAL. A matter reopens because something
    happened -- an order, a notice, a client calling. Refusing to reopen until
    the checks pass would leave the advocate unable to act on exactly the
    development that made them reopen it; what they need is the list.
    """
    out = [
        "recheck who is permitted to act on this matter; the authority that "
        "existed at closure may have lapsed",
        "confirm the current instruction: the client's objective at closure is "
        "not evidence of their objective now",
        "recheck the legal position for movement since it was last derived",
    ]
    if not blank(record.retention):
        out.append(
            f"confirm what material survives under retention request "
            f"{record.retention}; anything erased under it does not come back")
    if record.lifecycle is Lifecycle.ARCHIVED:
        out.append("this matter was archived, not merely closed; restoring it "
                   "to ordinary view is a separate decision from reopening it")
    if months_closed >= 6:
        out.append(
            f"it has been closed {months_closed} months; treat every derived "
            f"value as stale until reworked rather than assuming it held")
    return tuple(out)
