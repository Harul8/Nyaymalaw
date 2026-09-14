"""E5. A position the advocate overruled stays visible and DOES NOT REAPPEAR.

    *Disagree once, clearly, then drop it. Record the reservation and get on
    with the job.*

    *Never relitigate. A point the advocate has overruled does not reappear
    unless a NEW FACT reactivates it -- and then as a current finding with its
    consequence, never as vindication.*

E5's counterexample is *the same objection restated on every turn after the
advocate went the other way*, and that is what this type exists to make
structurally impossible rather than merely discouraged.

WHY A TURN MUST NOT REACTIVATE ONE
------------------------------------
The Class A eval is exact: *a reservation is reactivated only by a Fact, never
by a new turn.* The distinction is the whole feature. Almost everything this
product derives is recomputed from scratch each turn, so a reservation keyed on
"has the objection been re-derived" would reactivate on every single turn --
which is the counterexample, arriving by construction rather than by intent.

So `reactivated_by` holds a `FactId` or nothing, and `reactivate` takes FACTS.
There is no code path that takes a turn id.

AND THE TONE IS PART OF THE CONTRACT
--------------------------------------
*...and then as a current finding with its consequence, never as vindication.*
A reactivated reservation is not "as I said last week". `as_current_finding`
renders the consequence and never the history of having been right, which is
why it is a method here rather than a sentence at the call site: three call
sites would be three tones, and the third one would be smug.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from nm.domain.text import blank


@dataclass(frozen=True)
class Reservation:
    """A position this product took that the advocate went against.

    Appendix E: `Reservation { position, stated_at, overruled_at,
    reactivated_by: FactId|null }`.
    """

    position: str
    """WHAT WAS SAID, in the words it was said in.

    Not a summary of it. A reservation the advocate cannot recognise as the
    thing they overruled is one they cannot judge the reactivation of.
    """

    because: str
    """WHY it was said. E5 requires criticism to be grounded rather than
    asserted, and a reservation carrying no reason reactivates as an opinion
    with a date on it."""

    stated_at: str
    """The turn on which this product took the position."""

    overruled_at: str
    """The turn on which the advocate went the other way. REQUIRED: a
    reservation that was never overruled is just a position, and filing one
    here would let a live disagreement be quietly reclassified as settled."""

    reactivated_by: str | None = None
    """The FACT that brought it back, or None.

    A `FactId`, never a turn id. The type is what enforces the Class A eval:
    there is no constructor path that takes a turn.
    """

    def __post_init__(self) -> None:
        for name in ("position", "because", "stated_at", "overruled_at"):
            if blank(getattr(self, name)):
                raise ValueError(
                    f"a Reservation needs {name}: a position recorded without "
                    f"it cannot be recognised, judged, or dated by the "
                    f"advocate who overruled it")
        if self.reactivated_by is not None and blank(self.reactivated_by):
            raise ValueError(
                "reactivated_by is present and empty. A reservation that was "
                "reactivated by nothing in particular is the relitigation E5 "
                "forbids, wearing the shape of a fact.")

    @property
    def live(self) -> bool:
        """Whether this should be put in front of the advocate again.

        False for an overruled position with no new fact -- which is the
        ordinary case and the whole point.
        """
        return self.reactivated_by is not None

    def as_current_finding(self) -> str:
        """The reactivated reservation, AS A CURRENT FINDING.

        *...never as vindication.* No "as I noted", no "as I said at the time",
        no reference to having been right. The new fact and the consequence,
        which is what an advocate can act on.

        One owner for the tone, because three call sites would be three tones
        and one of them would be smug.
        """
        if not self.live:
            raise ValueError(
                "a reservation that has not been reactivated has no current "
                "finding to state. Rendering one anyway is the restatement "
                "E5's counterexample names.")
        return (f"{self.position} This is live again: {self.reactivated_by} "
                f"changes it. {self.because}")


def record(standing: tuple[Reservation, ...],
           new: Reservation) -> tuple[Reservation, ...]:
    """Add a reservation, ONCE.

    Keyed on the position, so the same disagreement overruled twice is one
    reservation and not two. Two entries would be the restatement E5 forbids,
    arriving in the summary instead of in the answer.
    """
    if any(r.position == new.position for r in standing):
        return standing
    return (*standing, new)


def reactivate(standing: tuple[Reservation, ...],
               fact_ids: frozenset[str],
               touches: dict[str, str]) -> tuple[Reservation, ...]:
    """Reservations after a turn that recorded new FACTS.

    `touches` maps a reservation's position to the fact id that bears on it.
    The caller decides what bears on what -- it has the facts and the
    reasoning; this has the rule.

    ONLY A FACT. There is no parameter here that could carry a turn id, which
    is the Class A eval expressed as a signature rather than as a check: a
    reservation cannot be reactivated by the passage of a turn because there
    is no way to say so.
    """
    out = []
    for r in standing:
        fid = touches.get(r.position)
        if fid is not None and fid in fact_ids and not r.live:
            out.append(replace(r, reactivated_by=fid))
        else:
            out.append(r)
    return tuple(out)


def live(standing: tuple[Reservation, ...]) -> tuple[Reservation, ...]:
    """The ones to put in front of the advocate. Usually none."""
    return tuple(r for r in standing if r.live)


def from_stored(values) -> tuple[Reservation, ...]:
    """Read back what the store holds.

    The same shape as `decision.from_stored` and `proof.from_stored`: the
    field is `tuple[object, ...]` for the import-cycle reason, so it reloads
    as dicts and something has to turn them back into the type.
    """
    out = []
    for v in values or ():
        if isinstance(v, Reservation):
            out.append(v)
            continue
        if not isinstance(v, dict):
            continue
        try:
            out.append(Reservation(
                position=v.get("position", ""),
                because=v.get("because", ""),
                stated_at=v.get("stated_at", ""),
                overruled_at=v.get("overruled_at", ""),
                reactivated_by=v.get("reactivated_by")))
        except ValueError:
            # A stored row that cannot be rebuilt is DROPPED rather than
            # repaired with defaults. A reservation with an invented reason
            # would reactivate as something the product never said.
            continue
    return tuple(out)
