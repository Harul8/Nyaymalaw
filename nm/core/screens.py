"""The front-door screens. B2 to B6.

WHAT THEY HAVE IN COMMON, AND WHY THEY ARE ONE MODULE
-------------------------------------------------------
Every one of them answers a question that gates substance, and every one of
them fails the same way: BY NOT RUNNING AND LOOKING LIKE IT PASSED. B2's
counterexample is *a matter where the urgency step threw an exception and the
answer reads "nothing urgent on this file"*; B3's is *a registry read that
failed on three of forty firms and returned "no conflicts found"*.

That is one defect with five faces, so it gets one type. `Screen` carries four
states, not two, and `INCOMPLETE` is the one that does the work — it is the
state a partial read produces, and it can never become `CLEAR` by being asked
again politely.

A CLEARANCE IS BOUND TO WHAT WAS SCREENED
-------------------------------------------
B3: *a clearance is bound to the party set that was screened.* A conflict check
that cleared two parties says nothing about the third who arrives on turn six,
and a clearance that floats free of its subject is worse than none — it is a
recorded assurance nobody gave.

So `Screen.covers` holds the party set, and `stale_for` answers whether the
clearance still applies. Same shape as `effect_basis` carrying a posture
version: the answer travels with the thing it was an answer about.

A RELEASE RECORDS, IT DOES NOT DELETE
---------------------------------------
B4's counterexample: *a competence limit found at turn 2, released by a partner
at turn 3, and ABSENT FROM THE FILE AT TURN 4.* The release is a decision
somebody made and it belongs on the record beside the limit it lifted. Deleting
the limit leaves a file that never had a problem, which is a different file.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from enum import Enum

from nm.domain.capacity import Capacity as Capacity
from nm.domain.capacity import CapacityPosition
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements


class ScreenKind(str, Enum):
    EMERGENCY = "emergency"
    CONFLICT = "conflict"
    COMPETENCE = "competence"
    SCOPE = "scope"
    CAPACITY = "capacity"


class ScreenState(str, Enum):
    """FOUR STATES, and the middle two are the ones that earn their keep."""

    CLEAR = "clear"
    """Ran in full, and there is nothing."""

    BLOCKED = "blocked"
    """Ran in full, and there is something. A finding, not a failure."""

    INCOMPLETE = "incomplete"
    """Ran in PART. B3: *a registry that was unreadable in part produces an
    incomplete screen, and an incomplete screen NEVER CLEARS.*

    Distinct from NOT_ASSESSED because the fix differs: an incomplete screen
    needs a re-run of the part that failed, and an unassessed one needs running
    at all."""

    NOT_ASSESSED = "not_assessed"
    """Did not run. Never renders as cleared (E-016, E-063c)."""

    UNAVAILABLE = "unavailable"
    """COULD NOT RUN -- the source it screens against could not be reached.

    P14. Distinct from NOT_ASSESSED because the FIX DIFFERS, which is the only
    reason any of these four are separate values: an unassessed screen needs
    somebody to run it, and an unavailable one needs the registry back before
    anybody can. Telling an advocate to run a screen whose source is down
    sends them at the wrong problem.

    Distinct from INCOMPLETE because that one READ SOMETHING. A partial answer
    can sometimes be acted on; nothing cannot.

    AND IT NEVER CLEARS, which is the property all three non-CLEAR states
    share and the one this whole enum exists for.
    """


@refuses_blank_text()
@dataclass(frozen=True)
class Release:
    """A limit lifted by a named human, ON THE RECORD.

    B4: *a release RECORDS rather than deletes.* The release sits beside the
    finding it lifted, because a file with the finding removed is a file that
    never had a problem, and that is a different file from one where somebody
    decided the problem was acceptable.
    """

    by: str
    because: str
    at: datetime = field(default_factory=datetime.now)


@refuses_blank_text("detail", "not_assessed_because")
@dataclass(frozen=True)
class Screen:
    """One screen, its state, and what it was a screen OF."""

    kind: ScreenKind
    state: ScreenState = ScreenState.NOT_ASSESSED
    detail: str = ""
    covers: frozenset[str] = frozenset()
    """The party set this answer is ABOUT. See the module docstring."""
    unread: tuple[str, ...] = ()
    """What could not be read. Non-empty forces INCOMPLETE."""
    released: Release | None = None
    not_assessed_because: str = ""

    def __post_init__(self) -> None:
        if self.unread and self.state is not ScreenState.INCOMPLETE:
            raise ValueError(
                f"the {self.kind.value} screen could not read "
                f"{len(self.unread)} source(s) and is not INCOMPLETE. A "
                f"registry unreadable in part produces an incomplete screen, "
                f"and an incomplete screen never clears — "
                f"{sorted(self.unread)}")
        if self.state is ScreenState.INCOMPLETE and not self.unread:
            raise ValueError(
                f"the {self.kind.value} screen is INCOMPLETE and does not say "
                f"what it could not read. Without that it cannot be re-run "
                f"against the part that failed.")
        if self.state is ScreenState.BLOCKED and blank(self.detail):
            raise ValueError(
                f"the {self.kind.value} screen blocks and says nothing. A "
                f"block the advocate cannot see the reason for is one they "
                f"cannot answer.")
        if self.state is ScreenState.NOT_ASSESSED \
                and blank(self.not_assessed_because):
            raise ValueError(
                f"the {self.kind.value} screen did not run and does not say "
                f"why. NOT_ASSESSED and CLEAR are opposite facts and this is "
                f"the field that keeps them apart.")
        if self.released is not None and self.state is ScreenState.CLEAR:
            raise ValueError(
                f"the {self.kind.value} screen is CLEAR and carries a release. "
                f"A release lifts a finding; a screen with nothing to lift did "
                f"not need one, and recording it there hides whether anything "
                f"was ever found.")

    @property
    def clears(self) -> bool:
        """The ONLY question the rest of the product may ask.

        `state is CLEAR` written at a call site is a second copy of this rule,
        and the copy is where INCOMPLETE gets treated as good enough.
        """
        return self.state is ScreenState.CLEAR

    @implements("B3")
    def stale_for(self, parties: frozenset[str]) -> bool:
        """Does this answer still apply to THIS party set?

        A conflict check that cleared two parties says nothing about the third
        who arrives on turn six. A clearance floating free of its subject is
        worse than none: it is a recorded assurance nobody gave.
        """
        return not parties <= self.covers

    @implements("B3")
    def uncovered(self, parties: frozenset[str]) -> tuple[str, ...]:
        """WHICH names this answer never saw.

        `stale_for` says THAT a clearance no longer applies; this says WHICH
        parties it never covered. Both live here rather than at the call site,
        because a caller computing `parties - covers` for itself is a second
        copy of the rule -- and the copy is where a normalisation drifts and
        the staleness check silently stops matching.

        A disclosure that cannot name the party is one the advocate cannot
        act on: "the check may not cover everyone" is a worry, and "it did not
        cover the guarantor you just named" is a next step.
        """
        return tuple(sorted(parties - self.covers))


#: SCREEN KIND -> ITS GATE, and how a screen state reads in that gate's own
#: vocabulary. BK-34.
#:
#: WRITTEN DOWN RATHER THAN INFERRED, because the vocabularies genuinely
#: differ: a conflict that found something is `matched`, a scope that found
#: something is `out_of_scope`, and a capacity that found something is
#: `doubted`. They are not synonyms and flattening them to one word would
#: lose exactly what each gate exists to say.
#:
#: `metrics.fire` REFUSES AN OUT-OF-VOCABULARY STATE, so a mapping that drifts
#: from `nm/domain/gates.py` fails at the call rather than quietly recording a
#: state the matrix does not define.
GATE_FOR: dict[ScreenKind, tuple[str, dict[ScreenState, str]]] = {
    # `UNAVAILABLE` MAPS ONTO AN EXISTING GATE STATE RATHER THAN A NEW ONE.
    # `nm/domain/gates.py` declares each gate's states and is not P14's to
    # widen; G-CONFLICT's own condition already covers "the registry could not
    # be read", so `incomplete` is the honest gate answer. The distinction
    # between "nobody ran it" and "it could not run" is carried where it is
    # acted on -- the screen's own state and detail -- and mapping it here
    # EXPLICITLY rather than letting it fall through `table.get`'s default is
    # the point: a new enum member silently defaulting is how a state nobody
    # mapped starts reading as one somebody did.
    ScreenKind.EMERGENCY: ("G-EMERGENCY", {
        ScreenState.CLEAR: "resolved",
        ScreenState.BLOCKED: "live",
        ScreenState.INCOMPLETE: "not_assessed",
        ScreenState.NOT_ASSESSED: "not_assessed",
        ScreenState.UNAVAILABLE: "not_assessed",
    }),
    ScreenKind.CONFLICT: ("G-CONFLICT", {
        ScreenState.CLEAR: "clear",
        ScreenState.BLOCKED: "matched",
        ScreenState.INCOMPLETE: "incomplete",
        ScreenState.NOT_ASSESSED: "not_run",
        ScreenState.UNAVAILABLE: "incomplete",
    }),
    ScreenKind.COMPETENCE: ("G-COMPETENCE", {
        ScreenState.CLEAR: "covered",
        ScreenState.BLOCKED: "gap",
        ScreenState.INCOMPLETE: "not_assessed",
        ScreenState.NOT_ASSESSED: "not_assessed",
        ScreenState.UNAVAILABLE: "not_assessed",
    }),
    ScreenKind.SCOPE: ("G-SCOPE", {
        ScreenState.CLEAR: "in_scope",
        ScreenState.BLOCKED: "unrecorded",
        ScreenState.INCOMPLETE: "unrecorded",
        ScreenState.NOT_ASSESSED: "unrecorded",
        ScreenState.UNAVAILABLE: "unrecorded",
    }),
    ScreenKind.CAPACITY: ("G-CAPACITY", {
        ScreenState.CLEAR: "held",
        ScreenState.BLOCKED: "not_assessed",
        ScreenState.INCOMPLETE: "not_assessed",
        ScreenState.NOT_ASSESSED: "not_assessed",
        ScreenState.UNAVAILABLE: "not_assessed",
    }),
}


def gate_for(screen: Screen) -> tuple[str, str]:
    """The gate this screen fires, and the state it fires with.

    A COMPETENCE SCREEN THAT FOUND A COVERAGE GAP IS `CLEAR` AND FIRES `gap`,
    and the pair is not a contradiction: the screen ran and does not block --
    `G-COMPETENCE` is `Response.DISCLOSE` -- while the gate is what carries
    the finding to the advocate. The screen state answers *did this stop the
    turn*; the gate state answers *what did it find*.
    """
    gate_id, table = GATE_FOR.get(screen.kind, ("", {}))
    if not gate_id:
        return "", ""
    if screen.kind is ScreenKind.COMPETENCE:
        # Its finding lives in the detail, because the state is always CLEAR.
        if screen.detail.startswith("NOT MEASURED"):
            return gate_id, "not_assessed"
        if screen.detail.startswith("COVERAGE GAP"):
            return gate_id, "gap"
        return gate_id, "covered"
    return gate_id, table.get(screen.state, "not_assessed")


def from_stored(values) -> tuple[Screen, ...]:
    """Reconstruct the deliberately untyped persisted screen projection.

    Matter cannot depend on this core type. Its store therefore returns dicts;
    readers use this owner rather than misreporting every restored set unreadable.
    Malformed records raise, because dropping one would invent a clean screen.
    """
    if not isinstance(values, (tuple, list)):
        raise ValueError("the stored screen population is not a sequence")
    restored: list[Screen] = []
    for value in values:
        if isinstance(value, Screen):
            screen = value
        else:
            if not isinstance(value, dict) or set(value) != {f.name for f in fields(Screen)}:
                raise ValueError("a stored screen has missing or unknown fields")
            if any(not isinstance(value[key], str)
                   for key in ("kind", "state", "detail", "not_assessed_because")):
                raise ValueError("a stored screen has invalid text or state")
            for key in ("covers", "unread"):
                if (not isinstance(value[key], (list, tuple, frozenset))
                        or any(not isinstance(x, str) or blank(x) for x in value[key])):
                    raise ValueError("a stored screen has invalid coverage or unread entries")
            release = value["released"]
            if release is not None:
                if (not isinstance(release, dict)
                        or set(release) != {f.name for f in fields(Release)}
                        or any(not isinstance(release[key], str) or blank(release[key])
                               for key in ("by", "because", "at"))):
                    raise ValueError("a stored screen release lacks valid attribution")
                release = Release(by=release["by"], because=release["because"],
                                  at=datetime.fromisoformat(release["at"]))
            screen = Screen(
                kind=ScreenKind(value["kind"]), state=ScreenState(value["state"]),
                detail=value["detail"], covers=frozenset(value["covers"]),
                unread=tuple(value["unread"]), released=release,
                not_assessed_because=value["not_assessed_because"])
        if any(prior.kind is screen.kind for prior in restored):
            raise ValueError("the stored screen population repeats a kind")
        restored.append(screen)
    return tuple(restored)


@implements("B3")
def unscreened(screens: tuple[Screen, ...]) -> tuple[str, ...]:
    """Every screen that does NOT clear, with why. THE POPULATION IS THE KINDS.

    Built from `ScreenKind` rather than from what was run, so a screen nobody
    ran appears as a named row instead of not appearing — the arrangement D1's
    threshold map already uses, and for the identical reason: an advocate
    reading four rows believes the fifth was checked.
    """
    by_kind = {s.kind: s for s in from_stored(screens)}
    out: list[str] = []
    for kind in ScreenKind:
        s = by_kind.get(kind)
        if s is None:
            out.append(f"{kind.value}: never run on this matter")
        elif not s.clears:
            reason = s.detail or s.not_assessed_because or "; ".join(s.unread)
            out.append(f"{kind.value}: {s.state.value} — {reason}")
    return tuple(out)


@implements("B3")
def may_admit_substance(screens: tuple[Screen, ...],
                        emergency: bool = False) -> tuple[bool, str]:
    """B3: *no substantive fact is persisted to a matter whose screen is not
    `clear` or expressly emergency-excepted.*

    Returns the answer AND the reason, because a refusal the caller cannot
    explain is one the advocate cannot act on.

    THE EMERGENCY EXCEPTION IS EXPRESS AND NARROW. Liberty does not wait for a
    registry, and a product that let it would be wrong in the way that matters
    most — but the exception is recorded as an exception, so the file never
    reads as though the screens had passed.
    """
    # RESTORED BY P14. This read `blocking = ()` in the foundation handoff --
    # a debugging stub that made `unscreened` uncallable and turned the whole
    # admission gate into a constant `True`. Every screen cleared, including
    # the ones nobody had run. P14 owns this module and the ordinary-admission
    # criterion it serves (BK-34-AC3), so restoring the call IS the packet's
    # work rather than an unrelated fix carried alongside it.
    blocking = unscreened(screens)
    if not blocking:
        return True, "every screen clears"
    if emergency:
        return True, ("admitted under the EMERGENCY EXCEPTION with screens "
                      "outstanding: " + "; ".join(blocking))
    return False, "; ".join(blocking)


# ------------------------------------------------------------ B5 and B6 ---


def scope_screen(record, actor: str, now: datetime) -> Screen:
    """Acknowledge an attributed instruction, not professional scope authority.

    Older intake recorded an ISO date; newer intake records the server instant.
    Neither a malformed record nor a future assertion may count as answered.
    The complete Commission/work compatibility decision is a separate boundary.
    """
    valid = (isinstance(record, dict) and set(record) == {"by", "answer", "at"}
             and all(isinstance(record[key], str) and not blank(record[key])
                     for key in ("by", "answer", "at"))
             and record["by"] == actor and not blank(actor))
    if valid:
        try:
            raw = record["at"]
            if len(raw) == 10:
                recorded = date.fromisoformat(raw)
                valid = recorded.isoformat() == raw and recorded <= now.date()
            else:
                recorded = datetime.fromisoformat(raw)
                valid = (recorded.tzinfo is not None and now.tzinfo is not None
                         and recorded <= now)
        except (ValueError, TypeError, AttributeError):
            valid = False
    if valid:
        return Screen(
            kind=ScreenKind.SCOPE, state=ScreenState.CLEAR,
            detail=(f"instruction statement recorded by {record['by']} on "
                    f"{record['at']}: {record['answer']}"))
    return Screen(
        kind=ScreenKind.SCOPE, state=ScreenState.NOT_ASSESSED,
        not_assessed_because=(
            "the engagement instruction is missing or its recorded source cannot "
            "be verified; state the work you are instructed to do"))


def capacity_screen(record, now: datetime) -> Screen:
    """The real admission decision uses the typed position, never prose truthiness."""
    position = CapacityPosition.from_stored(record)
    if position.authorises_at(now):
        return Screen(kind=ScreenKind.CAPACITY, state=ScreenState.CLEAR,
                      detail=position.said())
    if position.state is Capacity.IN_DOUBT:
        return Screen(kind=ScreenKind.CAPACITY, state=ScreenState.BLOCKED,
                      detail=position.said())
    return Screen(kind=ScreenKind.CAPACITY, state=ScreenState.NOT_ASSESSED,
                  not_assessed_because=(position.said() +
                      " No current capacity clearance is established."))


@refuses_blank_text("scope", "decision_owner", "authority")
@dataclass(frozen=True)
class Engagement:
    """B5. Who instructs, on what authority, within what scope, deciding what."""

    identity: str = ""
    authority: str = ""
    scope: str = ""
    decision_owner: str = ""
    capacity: Capacity = Capacity.NOT_ASSESSED

    @property
    @implements("B5")
    def reliance_ready(self) -> bool:
        """B5: *false while ANY of identity, authority, scope or decision
        ownership is unset. AN EMPTY SCOPE AUTHORISES NOTHING.*

        The counterexample is a file with a blank scope where every recommended
        step rendered as in-scope — the empty string read as "no limits" when
        it means "nobody said".

        B6 joins here rather than in a second property: an instruction whose
        capacity is IN_DOUBT cannot make advice reliance-ready, and two
        properties would let a caller ask the easier one.
        """
        if self.capacity is not Capacity.NOT_IN_DOUBT:
            return False
        return not any(blank(v) for v in
                       (self.identity, self.authority, self.scope,
                        self.decision_owner))

    @implements("B5")
    def missing(self) -> tuple[str, ...]:
        """What is unset, named. `reliance_ready` alone tells the advocate they
        cannot rely on the advice and not what would change that."""
        out = [name for name, value in (
            ("identity", self.identity), ("authority", self.authority),
            ("scope", self.scope), ("decision owner", self.decision_owner))
            if blank(value)]
        if self.capacity is Capacity.NOT_ASSESSED:
            out.append("capacity to instruct — not assessed")
        elif self.capacity is Capacity.IN_DOUBT:
            out.append("capacity to instruct — in doubt on the record")
        return tuple(out)
