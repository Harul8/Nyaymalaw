"""Available relief, its enforceability and its proportion. BK-70. E2/E3.

WHY MERITS ARE NOT THE ANSWER, AND WHY THIS IS A SEPARATE FILE
--------------------------------------------------------------
A claim can be legally unanswerable and still worth nothing to the client. The
debtor has no assets; the only order the forum can give arrives after it would
have mattered; the decree is sound and there is no route to execute it; the
suit costs more than it can recover. CLAUDE.md records the shape this product
exists to refuse -- a right answer to a question nobody asked -- and a
recommendation to litigate a hollow claim is exactly that, wearing diligence.

The recommendation feature (E2) already listed `enforceability` among the
things to compare, and nothing computed it, so it was compared from the account
like everything else the model was told to weigh. That is the same defect
`premise` exists for one door down: a value that decides the advice, believed
without being established.

    Correct merits cannot establish that the relief is worth pursuing.

So relief becomes a FIRST-CLASS FILE OBJECT with the discipline every other
computed fact here carries: three states, an attributed basis, and a claim the
served next step is checked against (`nm.core.consistency`).

THE FIVE COORDINATES, AND WHY PROPORTIONALITY IS NOT ONE OF THE FOUR
---------------------------------------------------------------------
Relief is read on five things, and they do NOT fail the same way:

    AVAILABILITY    the forum can grant this remedy on these facts, or cannot
    VALUE           what it wins is substantial, or it is hollow
    TIMING          it arrives in time to serve the objective, or too late
    ENFORCEABILITY  there is a route to realise it, or there is not
    PROPORTIONALITY the cost is worth the recovery, or it is not

The FIRST FOUR decide whether a relief DELIVERS the objective. Proportionality
does not, and that is not an oversight -- E3's NEVER is explicit: *never let
proportionality become a reason to withhold a legally available route; it is
stated alongside the route, not instead of it.* A disproportionate route is
still a route. The advocate is told, plainly and at the point of the
recommendation, that the cost exceeds the recovery -- and left to decide. So
`delivers` reads the four; proportionality is disclosed beside the step and,
where a step presents a costly route as plainly worthwhile, the step must SAY
the cost exceeds the recovery. It is never silently removed.

THE FACTS ARE ATTRIBUTED, NOT GUESSED
---------------------------------------
"The debtor has no assets" is a fact about the world that decides the answer,
and a model that guesses it advises on a fiction. Each relief carries a `Basis`
-- STATED by the advocate, ATTRIBUTED to something re-readable, or INFERRED and
therefore not sufficient to conclude on. An adverse coordinate believed only by
INFERENCE does not silently defeat the relief; it is a QUESTION, exactly as an
inferred premise is a question and not a computed date (P22). The relief is
then CONTINGENT: the step may proceed but must carry the reservation.

THREE STATES, ALWAYS
--------------------
Every coordinate has a NOT_ASSESSED member and it is a value, not a blank. A
relief nobody assessed for enforceability is not enforceable and is not
unenforceable -- it is unassessed, and the recommendation says which. The same
rule the limitation map and the threshold map already keep, for the same
reason: absence is invisible and a row is not.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from nm.core.premise import SUFFICIENT, Basis
from nm.domain.spoken import named
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements
from nm.ports.interim_relief import InterimRelief


class Availability(str, Enum):
    """Can the forum grant this remedy on these facts."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_assessed(cls) -> "Availability":
        return cls.NOT_ASSESSED


class Value(str, Enum):
    """What the remedy actually wins for the client."""

    SUBSTANTIAL = "substantial"
    HOLLOW = "hollow"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_assessed(cls) -> "Value":
        return cls.NOT_ASSESSED


class Timing(str, Enum):
    """Does the remedy arrive in time to serve the objective."""

    TIMELY = "timely"
    LATE = "late"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_assessed(cls) -> "Timing":
        return cls.NOT_ASSESSED


class Enforceability(str, Enum):
    """Is there a route to realise the remedy once granted."""

    ENFORCEABLE = "enforceable"
    UNENFORCEABLE = "unenforceable"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_assessed(cls) -> "Enforceability":
        return cls.NOT_ASSESSED


class Proportionality(str, Enum):
    """Cost against recovery. NEVER a veto on a legally available route (E3)."""

    PROPORTIONATE = "proportionate"
    DISPROPORTIONATE = "disproportionate"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_assessed(cls) -> "Proportionality":
        return cls.NOT_ASSESSED


class ReliefState(str, Enum):
    """The objective's overall relief position. FOUR STATES, and the fourth is
    the escape §9 requires.

    `SERVEABLE`   at least one relief delivers the objective.
    `DEFEATED`    reliefs were assessed and none delivers, and the shortfall is
                  ESTABLISHED (stated or attributed) -- the merits may hold and
                  the useful relief is unavailable, hollow, late or
                  unenforceable. This is the state BK-70 exists to make visible.
    `CONTINGENT`  no relief delivers, but the shortfall is only INFERRED -- a
                  question, not a defeat. The step may proceed under an express
                  reservation, exactly as an inferred premise makes a
                  computation CONDITIONAL rather than blocking it (P22).
    `NOT_ASSESSED` nothing has been assessed. NOT the same as DEFEATED: one is
                  "we looked and there is nothing worth pursuing", the other is
                  "nobody looked", and an advocate acts on them differently.
    """

    SERVEABLE = "serveable"
    DEFEATED = "defeated"
    CONTINGENT = "contingent"
    NOT_ASSESSED = "not_assessed"

    @classmethod
    def not_assessed(cls) -> "ReliefState":
        return cls.NOT_ASSESSED


#: The four coordinates that decide whether a relief DELIVERS. Proportionality
#: is deliberately not here -- see the module docstring and E3's NEVER.
_DELIVERS = {
    "availability": Availability.AVAILABLE,
    "value": Value.SUBSTANTIAL,
    "timing": Timing.TIMELY,
    "enforceability": Enforceability.ENFORCEABLE,
}

#: How each adverse coordinate reads in a sentence to the advocate.
_ADVERSE_WORD = {
    "availability": "not available from the forum on these facts",
    "value": "hollow -- what it wins is not substantial",
    "timing": "too late to serve the objective",
    "enforceability": "unenforceable -- there is no route to realise it",
}


@refuses_blank_text("source")
@dataclass(frozen=True)
class Objective:
    """WHAT THE CLIENT ACTUALLY WANTS, against which relief is measured.

    Not the cause of action and not the theory: the practical end. "Recover the
    price of the goods." "Keep possession of the shop." "Stop the construction
    before the slab is poured." A relief is useful only against an objective,
    and the same decree can serve one objective and be useless for another --
    a money decree is relief for a debt and no relief at all where the client
    needed the building stopped this week.

    ATTRIBUTED like a premise. An objective the advocate STATED is the strong
    case; one the product INFERRED from the brief is a question, and the answer
    says which so the advocate can correct it in a few words.
    """

    statement: str
    basis: Basis = Basis.UNESTABLISHED
    source: str = ""
    """WHAT CAN BE RE-READ. The advocate's own words, or a brief locator.
    Required for ATTRIBUTED -- a source nobody can open is decoration."""
    inferred_from: str = ""

    def as_dict(self) -> dict:
        return {"statement": self.statement, "basis": self.basis.value,
                "source": self.source, "inferred_from": self.inferred_from}

    @staticmethod
    def from_stored(row: object) -> "Objective | None":
        if not isinstance(row, dict) or blank(row.get("statement")):
            return None
        try:
            basis = Basis(str(row.get("basis") or Basis.UNESTABLISHED.value))
        except ValueError:
            basis = Basis.UNESTABLISHED
        return Objective(statement=str(row["statement"]), basis=basis,
                         source=str(row.get("source") or ""),
                         inferred_from=str(row.get("inferred_from") or ""))


@refuses_blank_text("source", "inferred_from", "reason")
@dataclass(frozen=True)
class Relief:
    """One remedy for one objective, read on the five coordinates.

    `basis` is HOW THE ADVERSE COORDINATES CAME TO BE BELIEVED, the same
    vocabulary a premise uses. It is what separates a relief that is DEFEATED
    (its shortfall is STATED or ATTRIBUTED) from one that is CONTINGENT (the
    shortfall is only INFERRED, so it is a question and not a conclusion). A
    relief with no adverse coordinate needs no basis -- there is nothing to
    have established.
    """

    remedy: str
    """What is asked for, in the words a pleading would use."""
    objective: str
    """The objective this serves -- the `statement` of an `Objective`."""
    forum: str = ""
    availability: Availability = Availability.NOT_ASSESSED
    value: Value = Value.NOT_ASSESSED
    timing: Timing = Timing.NOT_ASSESSED
    enforceability: Enforceability = Enforceability.NOT_ASSESSED
    proportionality: Proportionality = Proportionality.NOT_ASSESSED
    prerequisites: tuple[str, ...] = ()
    interim: InterimRelief = InterimRelief.NOT_STATED
    """The INTERIM order sought while this remedy is pursued, if any. LB-123.

    IT IS NOT A SIXTH COORDINATE and it is deliberately not read by
    `delivers`. Whether an interim injunction will be granted is decided on
    its own test (`nm.knowledge.interim_relief`), not on whether the FINAL
    relief is available, valuable, timely and enforceable -- and the reverse
    is equally false. Folding it into the five would make each answer the
    other's question, which is the defect LB-123 exists to refuse.
    """
    basis: Basis = Basis.UNESTABLISHED
    source: str = ""
    """Required for ATTRIBUTED -- what says the debtor has no assets, that the
    window has run, that no execution route exists."""
    inferred_from: str = ""
    reason: str = ""
    """One clause the advocate reads: why the adverse coordinate is adverse, or
    why the enforceability holds. This is the enforceability basis BK-70-AC1
    requires the recommendation to explain."""

    @property
    def delivers(self) -> bool:
        """All four load-bearing coordinates favourable. Proportionality is not
        read here -- a disproportionate route still delivers, and E3 forbids
        treating cost as a bar."""
        return all(getattr(self, name) is good
                   for name, good in _DELIVERS.items())

    @property
    def shortfalls(self) -> tuple[str, ...]:
        """The load-bearing coordinates that are ADVERSE (not merely
        unassessed). Named, never counted -- which one it is decides whether
        the answer is 'pivot' or 'confirm the route is enforceable'."""
        adverse = {
            "availability": Availability.UNAVAILABLE,
            "value": Value.HOLLOW,
            "timing": Timing.LATE,
            "enforceability": Enforceability.UNENFORCEABLE,
        }
        return tuple(name for name, bad in adverse.items()
                     if getattr(self, name) is bad)

    @property
    def established(self) -> bool:
        """Is the adverse finding one a computation may rest on. STATED or
        ATTRIBUTED is; INFERRED is a question, and UNESTABLISHED is nothing."""
        return self.basis in SUFFICIENT

    def as_dict(self) -> dict:
        return {
            "remedy": self.remedy, "objective": self.objective,
            "forum": self.forum,
            "availability": self.availability.value,
            "value": self.value.value, "timing": self.timing.value,
            "enforceability": self.enforceability.value,
            "proportionality": self.proportionality.value,
            "prerequisites": list(self.prerequisites),
            "interim": self.interim.value,
            "basis": self.basis.value, "source": self.source,
            "inferred_from": self.inferred_from, "reason": self.reason,
        }

    @staticmethod
    def from_stored(row: object) -> "Relief | None":
        if not isinstance(row, dict) or blank(row.get("remedy")) \
                or blank(row.get("objective")):
            return None

        def _enum(cls, key, default):
            try:
                return cls(str(row.get(key) or default.value))
            except ValueError:
                return default

        try:
            basis = Basis(str(row.get("basis") or Basis.UNESTABLISHED.value))
        except ValueError:
            basis = Basis.UNESTABLISHED
        pre = row.get("prerequisites")
        return Relief(
            remedy=str(row["remedy"]), objective=str(row["objective"]),
            forum=str(row.get("forum") or ""),
            availability=_enum(Availability, "availability",
                               Availability.NOT_ASSESSED),
            value=_enum(Value, "value", Value.NOT_ASSESSED),
            timing=_enum(Timing, "timing", Timing.NOT_ASSESSED),
            enforceability=_enum(Enforceability, "enforceability",
                                 Enforceability.NOT_ASSESSED),
            proportionality=_enum(Proportionality, "proportionality",
                                  Proportionality.NOT_ASSESSED),
            prerequisites=tuple(str(p) for p in pre) if isinstance(pre, list)
            else (),
            interim=_enum(InterimRelief, "interim", InterimRelief.NOT_STATED),
            basis=basis, source=str(row.get("source") or ""),
            inferred_from=str(row.get("inferred_from") or ""),
            reason=str(row.get("reason") or ""),
        )


@dataclass(frozen=True)
class ReliefPosition:
    """The relief position for one objective, as this turn computed it.

    THE POPULATION IS THE RELIEFS THAT WERE READ, and `assess` is the only
    place a relief becomes a verdict -- a second reading somewhere else would
    be a second answer to 'is this claim worth pursuing', which is the
    three-stores defect on the most consequential question the file asks.
    """

    objective: Objective | None
    reliefs: tuple[Relief, ...]
    state: ReliefState
    useful: tuple[str, ...] = ()
    """Remedies (by their text) that DELIVER the objective."""
    defeated: tuple[tuple[str, str, str], ...] = ()
    """(remedy, coordinate, why) for each relief that fails a load-bearing
    coordinate on an ESTABLISHED basis. The reason the recommendation changes."""
    contingent: tuple[tuple[str, str, str], ...] = ()
    """(remedy, coordinate, why) where the shortfall is only INFERRED -- a
    question, not a defeat. The step proceeds under a reservation."""
    disproportionate: tuple[tuple[str, str], ...] = ()
    """(remedy, why) for reliefs whose cost exceeds recovery. STATED ALONGSIDE
    the route, never a reason to withhold it (E3)."""

    @property
    def digest(self) -> str:
        """A stable identity for the position, so the answer, the cover and the
        register can be checked to rest on ONE version (the move P22 makes for
        premises and P18 for currency)."""
        parts = [self.state.value,
                 (self.objective.statement if self.objective else "")]
        for r in self.reliefs:
            parts.append(f"{r.remedy}|{r.availability.value}|{r.value.value}|"
                         f"{r.timing.value}|{r.enforceability.value}|"
                         f"{r.proportionality.value}|{r.basis.value}")
        return hashlib.sha256("".join(parts).encode("utf8")).hexdigest()

    def as_rows(self) -> tuple[dict, ...]:
        return tuple(r.as_dict() for r in self.reliefs)


@implements("E2")
def assess(objective: Objective | None,
           reliefs: tuple[Relief, ...]) -> ReliefPosition:
    """Read the reliefs and say whether the objective can be served.

    THE FOUR COORDINATES DECIDE, PROPORTIONALITY IS DISCLOSED. A relief
    delivers when it is available, substantial, timely and enforceable; a
    disproportionate one still delivers and is listed for the finding beside
    the recommendation. This is E3's NEVER made structural -- there is no
    branch in which proportionality removes a relief from `useful`.

    AN INFERRED SHORTFALL IS A QUESTION, NOT A DEFEAT. A relief whose only
    adverse coordinate rests on INFERENCE is `contingent`, so the answer asks
    rather than concludes -- the same control P22 puts on an inferred premise.
    """
    useful: list[str] = []
    defeated: list[tuple[str, str, str]] = []
    contingent: list[tuple[str, str, str]] = []
    disproportionate: list[tuple[str, str]] = []

    for r in reliefs:
        if r.proportionality is Proportionality.DISPROPORTIONATE:
            disproportionate.append(
                (r.remedy, r.reason or "the cost of this route exceeds what it "
                                       "can recover"))
        if r.delivers:
            useful.append(r.remedy)
            continue
        shorts = r.shortfalls
        if not shorts:
            # No adverse coordinate, but not all four are favourable either:
            # something is NOT_ASSESSED. It does not deliver and it is not
            # defeated -- it is a gap, and the state below records it.
            continue
        for name in shorts:
            why = r.reason or _ADVERSE_WORD[name]
            row = (r.remedy, name, why)
            (defeated if r.established else contingent).append(row)

    if useful:
        state = ReliefState.SERVEABLE
    elif defeated:
        # An ESTABLISHED shortfall defeats: the useful relief is genuinely not
        # there, and the recommendation cannot pursue it as though it were.
        state = ReliefState.DEFEATED
    elif contingent:
        # Only an INFERRED shortfall: a question, not a defeat. The step
        # proceeds under a reservation -- the same control P22 puts on an
        # inferred premise, which computes CONDITIONAL rather than blocking.
        state = ReliefState.CONTINGENT
    elif disproportionate:
        # Every relief delivers (else it would be in useful/defeated/
        # contingent), so a bare disproportionate list means a costed but
        # available route -- SERVEABLE, with the cost stated alongside.
        state = ReliefState.SERVEABLE
    else:
        state = ReliefState.NOT_ASSESSED

    return ReliefPosition(
        objective=objective, reliefs=tuple(reliefs), state=state,
        useful=tuple(useful), defeated=tuple(defeated),
        contingent=tuple(contingent),
        disproportionate=tuple(disproportionate))


def consistency_claims(position: ReliefPosition | None,
                       ) -> tuple[tuple[str, str], ...]:
    """Relief as (id, sentence) facts the served step must not contradict.

    ONE OWNER FEEDS `nm.core.consistency.claims_for`. Relief lives in `core`
    and `consistency` lives in `core`; this returns raw pairs rather than
    `Claim` objects so `consistency` need not be imported here, which would be
    the cycle. The wording carries the RESERVATION the step is allowed to make
    -- a step that pursues a defeated relief AND says the shortfall is
    unresolved is not contradicting the fact, it is acknowledging it, which is
    exactly the escape BK-70-AC1's negative control names.
    """
    if position is None:
        return ()
    out: list[tuple[str, str]] = []
    obj = position.objective.statement if position.objective else "the objective"

    if position.state is ReliefState.DEFEATED and position.defeated:
        remedy, _coord, why = position.defeated[0]
        out.append((
            "relief",
            f"The relief that would serve {named(obj)} ({remedy}) is {why}. A step "
            f"that pursues it as though it will deliver contradicts this; "
            f"pursuing it needs an explicit reservation that it may not."))
    elif position.state is ReliefState.CONTINGENT and position.contingent:
        remedy, _coord, why = position.contingent[0]
        out.append((
            "relief",
            f"Whether the relief that would serve {named(obj)} ({remedy}) delivers "
            f"is NOT established -- {why}. A step that pursues it as though it "
            f"certainly will deliver contradicts this; it needs an express "
            f"reservation, or the shortfall confirmed first."))
    for remedy, why in position.disproportionate:
        out.append((
            "proportionality",
            f"The route {named(remedy)} {why}. A step recommending it as plainly "
            f"worthwhile, without stating that the cost exceeds the recovery, "
            f"contradicts this."))
    return tuple(out)


def recommendation_note(position: ReliefPosition | None) -> str:
    """What the recommendation read is TOLD about relief, so the step is
    composed knowing it -- the same `ALREADY WORKED OUT` move `_recommend`
    makes for limitation. Empty when nothing was assessed, because a note that
    says nothing invites a step that assumes everything."""
    if position is None or position.state is ReliefState.NOT_ASSESSED:
        return ""
    obj = position.objective.statement if position.objective else "the objective"
    if position.state is ReliefState.SERVEABLE:
        note = (f"\n\nRELIEF, ALREADY WORKED OUT for {obj}: a remedy that "
                f"delivers is available ({', '.join(position.useful)}). Your "
                f"step may pursue it.")
    elif position.state is ReliefState.CONTINGENT:
        lines = "; ".join(f"{remedy} is {why} (inferred -- not established)"
                          for remedy, _c, why in position.contingent)
        note = (f"\n\nRELIEF, NOT ESTABLISHED for {obj}: no remedy is confirmed "
                f"to deliver it -- {lines}. Do NOT recommend pursuing a remedy "
                f"as though it certainly will deliver; the step is to confirm "
                f"the shortfall or to pursue it under an express reservation.")
    else:
        lines = "; ".join(f"{remedy} is {why}"
                          for remedy, _c, why in position.defeated)
        note = (f"\n\nRELIEF, ALREADY WORKED OUT for {obj}: no remedy on the "
                f"file DELIVERS it -- {lines}. Do NOT recommend pursuing a "
                f"remedy as though it will deliver; the step is to address the "
                f"shortfall or to pursue it under an express reservation.")
    if position.disproportionate:
        costed = "; ".join(f"{remedy} ({why})"
                           for remedy, why in position.disproportionate)
        note += (f" The cost of {costed} exceeds what it can recover; you may "
                 f"still recommend it, but SAY SO -- proportionality is stated "
                 f"alongside the route, never used to withhold it.")
    return note


def disclosure(position: ReliefPosition | None) -> str:
    """The enforceability basis, as one sentence for the served FINDING that
    fires G-REMEDY. THREE STATES, and the third is a value: a file nobody
    assessed for relief is told so, not shown a clean bill."""
    if position is None or position.state is ReliefState.NOT_ASSESSED:
        return ""
    obj = position.objective.statement if position.objective else "the objective"
    if position.state is ReliefState.SERVEABLE:
        head = (f"Relief for {obj}: a remedy that delivers is available "
                f"({', '.join(position.useful)}).")
    elif position.state is ReliefState.CONTINGENT:
        parts = [f"{remedy} — {why}" for remedy, _c, why in position.contingent]
        head = (f"Relief for {obj}: no remedy is CONFIRMED to deliver it "
                f"(the shortfall is inferred, not established). "
                + "; ".join(parts) + ".")
    else:
        parts = [f"{remedy} — {why}" for remedy, _c, why in position.defeated]
        head = (f"Relief for {obj}: no remedy on the file delivers it. "
                + "; ".join(parts) + ".")
    if position.disproportionate:
        costed = "; ".join(f"{remedy} — {why}"
                           for remedy, why in position.disproportionate)
        head += f" Cost against recovery: {costed}."
    return head


def gate_state(position: ReliefPosition | None) -> str:
    """The G-REMEDY state, decided here so no call site reads it off fields."""
    if position is None or position.state is ReliefState.NOT_ASSESSED:
        return "not_assessed"
    return "serveable" if position.state is ReliefState.SERVEABLE \
        else "no_useful_relief"


def reliefs_from_stored(rows: object) -> tuple[Relief, ...]:
    """A thread's persisted reliefs, whatever the store returned. An
    unreadable row is dropped rather than crashing the turn -- the honest
    outcome is to reassess, exactly as `theory.from_stored` does."""
    if not isinstance(rows, (list, tuple)):
        return ()
    out: list[Relief] = []
    for row in rows:
        r = Relief.from_stored(row)
        if r is not None:
            out.append(r)
    return tuple(out)
