"""What a change reaches, and what it must leave alone. BK-65-AC1. P18.

    from nm.core.dependency import Ledger, Rest, InputKind, Currency

WHY THIS IS NOT `nm/core/cascade.py`, AND WHY IT IS NOT A SECOND COPY OF IT
-----------------------------------------------------------------------------
`cascade` answers *what MOVED between this turn and the last*, by comparing two
snapshots of derived values. It is an ANNOUNCEMENT mechanism: it fires once, on
the turn after a correction, and its output is prose the advocate reads.

It cannot answer the question BK-65-AC1 asks, and the gap is not a missing
feature -- it is the shape of the comparison. Three things follow from it:

  * A snapshot pair says a value moved. It cannot say WHY, because nothing in
    it records what the value rested on beyond a flat list of fact ids.
  * A value derived from ANOTHER derived value is invisible. `from_facts` is
    facts, so a deadline computed from a limitation computed from a premise
    has one edge where it needs two, and a premise that moves reaches nothing.
  * A comparison is a moment. The turn after a correction announces it and the
    turn after THAT announces nothing -- so a conclusion nobody has recomputed
    goes on being served as current, indefinitely, and a restart loses even
    the announcement.

So this module owns a different noun. `cascade` owns MOVEMENT; this owns
CURRENCY -- whether a recorded conclusion is still about the file as it now
stands. They meet at exactly one place: `from_derived` builds ledger nodes out
of the same `cascade.Derived` rows the turn already produces, so there is one
statement in the product of what a derived value rests on, and it is
`Derived.from_facts` plus the premises and authorities named where the value is
computed. Nothing here re-derives a dependency and nothing here guesses one.

WHAT IT IS FOR, IN ONE SENTENCE
---------------------------------
    Changing a material predicate invalidates every dependent conclusion and
    NO UNRELATED CONCLUSION, while preserving the prior state and the reason.

Both halves are load-bearing and they fail in opposite directions. A closure
that is too small serves stale advice as current. A closure that is too large
throws away the independent analysis an advocate has already relied on, which
trains them to ignore invalidation -- and then the one that mattered arrives in
a place they have learned to skip. That is §5.4's bound arriving one level
down, and it is why `closure` walks edges rather than invalidating a matter.

UNKNOWN DEPENDENCY INFORMATION CANNOT CERTIFY CURRENCY
--------------------------------------------------------
This is defect shape S1 aimed at the mechanism whose whole job is to catch S1.
A node with no recorded inputs has not been shown to be unaffected -- nobody
looked. A node that declares `InputKind.UNKNOWN` has been shown to rest on
something nothing tracks. Both are `Currency.NOT_ESTABLISHED`, which is not
`CURRENT`, and `presentable` refuses it the same way it refuses `STALE`.

The temptation is to treat "no edges touched it" as "it is fine". That reads an
absence of information as a clean result, which is the single most repeated
defect in this project.

REWORK IS BOUNDED, AND EXHAUSTION LEAVES IT STALE
---------------------------------------------------
A stale node is queued for recomputation with an attempt limit. When the limit
is reached the node does NOT become current and does not disappear: it becomes
`STALE` with an exhausted rework record naming how many attempts were made.
An unbounded retry is a queue that never drains; a retry that gives up quietly
is a stale conclusion wearing a fresh timestamp.

THE PRIOR STATE IS KEPT, AND SO IS THE REASON
-----------------------------------------------
`Revision` holds what the value was, what it became, which input versions moved
and the reason in words. EVAL-010 asks for exactly this -- the advocate sees
the old and the corrected date and who changed it -- and a history of values
with no reason is a diff, not an explanation.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import Enum

from nm.domain.text import clean, refuses_blank_text
from nm.domain.traceability import implements

#: How many times a stale node may be queued for recomputation before the
#: queue stops offering it. AUTHORED HERE, ONCE, so the runner and the report
#: cannot disagree about what "bounded" means.
#:
#: Three, and the number is not the point -- the bound is. What matters is
#: that exhaustion is a recorded state and not a silent drop.
REWORK_LIMIT = 3


class InputKind(str, Enum):
    """WHAT a derived value rests on. The four kinds fail differently.

    They are separated because the CORRECTION for each is different and
    arrives from a different place, which is the same argument
    `nm.core.premise.Kind` makes about the three legal premises.

        FACT       the advocate corrects it, or a document supersedes it.
        PREMISE    a legal position; corrected by review or retrieval.
        AUTHORITY  a corpus source version; moved by publication or
                   withdrawal, which `nm.knowledge.manifest` owns.
        DERIVED    another node. THIS IS WHAT MAKES THE CLOSURE TRANSITIVE,
                   and it is the edge `cascade.Derived.from_facts` cannot
                   express at all.
    """

    FACT = "fact"
    PREMISE = "premise"
    AUTHORITY = "authority"
    DERIVED = "derived"

    UNKNOWN = "unknown"
    """A dependency that exists and is not identified.

    NOT A PLACEHOLDER FOR "none". It is the honest record of a computation
    that rested on something the product cannot name, and its whole effect is
    that the node holding it can never be certified current."""

    @classmethod
    def not_established(cls) -> "InputKind":
        return cls.UNKNOWN


class Currency(str, Enum):
    """Whether a recorded conclusion is still about the file as it stands.

    FOUR STATES, and the two that get conflated are `STALE` and
    `NOT_ESTABLISHED`. The first is a finding -- something it rested on moved,
    and it must be recomputed. The second is a gap -- nobody knows what it
    rests on, so nobody can say whether it moved. They call for opposite next
    moves and only one of them is fixed by recomputing.
    """

    CURRENT = "current"
    STALE = "stale"
    REWORKING = "reworking"
    """Recomputation has been queued or started. STILL NOT CURRENT -- a value
    being recomputed is a value nobody should act on, and the window between
    'we noticed' and 'we finished' is exactly where stale advice is served."""

    NOT_ESTABLISHED = "not_established"

    @classmethod
    def not_established(cls) -> "Currency":
        return cls.NOT_ESTABLISHED

    @property
    def usable(self) -> bool:
        """Only CURRENT. Written as one property so no call site decides."""
        return self is Currency.CURRENT


@refuses_blank_text()
@dataclass(frozen=True)
class Rest:
    """One typed, versioned edge: what a node rested on, as it then stood.

    `version` IS THE WHOLE POINT OF RECORDING THIS. A node that names its
    inputs but not their versions can say what it depended on and never
    whether that dependency has since moved -- which is the difference
    between an audit trail and a control.
    """

    kind: InputKind
    id: str
    version: int = 0

    def as_dict(self) -> dict:
        return {"kind": self.kind.value, "id": self.id, "version": self.version}

    @staticmethod
    def from_stored(row: object) -> "Rest | None":
        if not isinstance(row, dict) or not clean(str(row.get("id") or "")):
            return None
        try:
            kind = InputKind(str(row.get("kind") or ""))
        except ValueError:
            # AN UNREADABLE KIND IS UNKNOWN, NOT DROPPED. Dropping the edge
            # would make the node look like it rested on less than it did,
            # and a smaller dependency set is a node that stays current
            # through a change that reached it.
            kind = InputKind.UNKNOWN
        try:
            version = int(row.get("version") or 0)
        except (TypeError, ValueError):
            version = 0
        return Rest(kind=kind, id=clean(str(row["id"])), version=version)


@refuses_blank_text()
@dataclass(frozen=True)
class Tracked:
    """One input the ledger is watching, and the version it is now on.

    THE VERSION IS ASSIGNED BY OBSERVED CHANGE, not supplied by the caller.
    A caller that numbers its own versions is a caller that can forget to,
    and the forgotten increment is invisible -- the node goes on matching an
    input that has moved underneath it.
    """

    kind: InputKind
    id: str
    version: int = 1
    digest: str = ""
    """What the input's material content hashed to at this version. The
    comparison that decides whether the version moves."""
    reason: str = ""
    """Why this version exists, in words an advocate reads."""
    withdrawn: bool = False
    """This input has been withdrawn rather than corrected. Kept apart from a
    correction because the answer differs: a corrected input yields a new
    value, and a withdrawn one yields none at all."""

    def as_dict(self) -> dict:
        return {"kind": self.kind.value, "id": self.id, "version": self.version,
                "digest": self.digest, "reason": self.reason,
                "withdrawn": self.withdrawn}


@refuses_blank_text()
@dataclass(frozen=True)
class Node:
    """One derived conclusion or computation, and what it rested on.

    `name` IS THE KEY AND `shown` IS THE SENTENCE, for the reason
    `cascade.Derived` separates them: the key carries a thread id so two
    threads' limitations are different values, and an advocate cannot read a
    database key (B-103).
    """

    name: str
    value: str
    rests_on: tuple[Rest, ...] = ()
    shown: str = ""
    currency: Currency = Currency.CURRENT
    stale_because: str = ""
    """Which input moved, and how. Empty while CURRENT."""
    computed_at: str = ""
    reason: str = ""
    """Why this value is what it is. Carried into `Revision` when it moves."""
    rework_attempts: int = 0
    rework_exhausted: bool = False

    def __post_init__(self) -> None:
        # A NODE THAT NAMES NOTHING CANNOT BE CERTIFIED CURRENT, and this is
        # answered by the type rather than left to the caller -- the caller
        # who gets it wrong is the one who records a conclusion in a hurry
        # and leaves its inputs for later.
        unknown = (not self.rests_on
                   or any(r.kind is InputKind.UNKNOWN for r in self.rests_on))
        if unknown and self.currency is Currency.CURRENT:
            object.__setattr__(self, "currency", Currency.NOT_ESTABLISHED)
            object.__setattr__(self, "stale_because", self.stale_because or (
                "nothing records what this rests on, so nobody can say "
                "whether it still holds"
                if not self.rests_on else
                "this rests on something the product cannot name, so a change "
                "to it would not be noticed"))

    @property
    def label(self) -> str:
        return self.shown or self.name

    def as_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "shown": self.shown,
                "rests_on": [r.as_dict() for r in self.rests_on],
                "currency": self.currency.value,
                "stale_because": self.stale_because,
                "computed_at": self.computed_at, "reason": self.reason,
                "rework_attempts": self.rework_attempts,
                "rework_exhausted": self.rework_exhausted,
                # DERIVED AND SERVED, so no reader re-implements the rule.
                "usable": self.currency.usable}


@refuses_blank_text()
@dataclass(frozen=True)
class Revision:
    """The prior state of one node, and why it stopped being current.

    BK-65-AC1's second clause. `was` is required for the reason
    `cascade.Change.was` is: a value that changed with no record of what it
    used to be is one the advocate cannot reconcile against what they
    remember, and the honest reading is that they misread it.
    """

    name: str
    was: str
    now: str = ""
    """Empty where the node has not been recomputed yet -- which is the
    ordinary state immediately after an invalidation, and is different from
    a recomputation that produced the same value."""
    reason: str = ""
    at: str = ""
    moved: tuple[Rest, ...] = ()
    """The exact input versions that moved. EVAL-010 reads `source_versions`
    off this: the advocate is shown that the record went from version 1 to
    version 2 rather than merely that something changed."""
    was_on: tuple[Rest, ...] = ()
    """The versions the node HAD been computed from, kept because `moved`
    alone loses them. Recomputing re-stamps the node with the new versions, so
    without this the file would say the conclusion rests on version 2 and hold
    no record that version 1 was ever relied on -- which is the half of
    EVAL-010 that lets an advocate see both."""

    def as_dict(self) -> dict:
        return {"name": self.name, "was": self.was, "now": self.now,
                "reason": self.reason, "at": self.at,
                "moved": [r.as_dict() for r in self.moved],
                "was_on": [r.as_dict() for r in self.was_on]}


@dataclass(frozen=True)
class Ledger:
    """Every tracked input, every derived node, and every prior state.

    PERSISTED ON THE MATTER, because a currency that lives in a process is a
    currency a restart silently converts to `current`. EVAL-010 restarts
    between the correction and the read for exactly that reason.
    """

    tracked: tuple[Tracked, ...] = ()
    nodes: tuple[Node, ...] = ()
    history: tuple[Revision, ...] = ()

    # ------------------------------------------------------------- reads ---

    def input_of(self, kind: InputKind, id_: str) -> Tracked | None:
        for row in self.tracked:
            if row.kind is kind and row.id == id_:
                return row
        return None

    def node(self, name: str) -> Node | None:
        for row in self.nodes:
            if row.name == name:
                return row
        return None

    def stale(self) -> tuple[Node, ...]:
        """Everything that is not usable. NOT ONLY `STALE`.

        A caller asking "what must I not serve" is asking about
        `NOT_ESTABLISHED` and `REWORKING` too, and a method named for one
        state that answered for one state would have three call sites each
        remembering to check the other two.
        """
        return tuple(n for n in self.nodes if not n.currency.usable)

    def current(self) -> tuple[Node, ...]:
        return tuple(n for n in self.nodes if n.currency.usable)

    def revisions_of(self, name: str) -> tuple[Revision, ...]:
        return tuple(r for r in self.history if r.name == name)

    def source_versions(self, name: str) -> tuple[int, ...]:
        """Every input version this node has been computed from, in order.

        EVAL-010's `history.source_versions` -- `{1, 2}` after one
        correction, which is the record that the advocate can see both.
        """
        node = self.node(name)
        seen = {r.version for r in (node.rests_on if node is not None else ())}
        for revision in self.revisions_of(name):
            seen.update(r.version for r in revision.moved)
            seen.update(r.version for r in revision.was_on)
        return tuple(sorted(seen))

    def as_dict(self) -> dict:
        return {"schema": 1,
                "tracked": [t.as_dict() for t in self.tracked],
                "nodes": [n.as_dict() for n in self.nodes],
                "history": [r.as_dict() for r in self.history]}

    @staticmethod
    def from_stored(value: object) -> "Ledger":
        """Rebuild from what was persisted. AN UNREADABLE LEDGER IS EMPTY.

        Empty is the safe direction here and it is worth saying why, because
        elsewhere in this product an empty result read as success is the
        defect. A node absent from the ledger has no recorded currency, and
        `presentable` refuses an unrecorded node rather than passing it --
        so losing the ledger withholds conclusions rather than certifying
        them.
        """
        if not isinstance(value, dict):
            return Ledger()
        tracked: list[Tracked] = []
        for row in value.get("tracked") or ():
            if not isinstance(row, dict) or not clean(str(row.get("id") or "")):
                continue
            try:
                kind = InputKind(str(row.get("kind") or ""))
            except ValueError:
                kind = InputKind.UNKNOWN
            tracked.append(Tracked(
                kind=kind, id=clean(str(row["id"])),
                version=int(row.get("version") or 1),
                digest=str(row.get("digest") or ""),
                reason=str(row.get("reason") or ""),
                withdrawn=bool(row.get("withdrawn"))))
        nodes: list[Node] = []
        for row in value.get("nodes") or ():
            if not isinstance(row, dict) or not clean(str(row.get("name") or "")):
                continue
            rests = tuple(r for r in (Rest.from_stored(x)
                                      for x in (row.get("rests_on") or ()))
                          if r is not None)
            try:
                currency = Currency(str(row.get("currency") or ""))
            except ValueError:
                currency = Currency.NOT_ESTABLISHED
            nodes.append(Node(
                name=clean(str(row["name"])), value=str(row.get("value") or ""),
                rests_on=rests, shown=str(row.get("shown") or ""),
                currency=currency,
                stale_because=str(row.get("stale_because") or ""),
                computed_at=str(row.get("computed_at") or ""),
                reason=str(row.get("reason") or ""),
                rework_attempts=int(row.get("rework_attempts") or 0),
                rework_exhausted=bool(row.get("rework_exhausted"))))
        history: list[Revision] = []
        for row in value.get("history") or ():
            if not isinstance(row, dict) or not clean(str(row.get("name") or "")):
                continue
            history.append(Revision(
                name=clean(str(row["name"])), was=str(row.get("was") or ""),
                now=str(row.get("now") or ""),
                reason=str(row.get("reason") or ""),
                at=str(row.get("at") or ""),
                moved=tuple(r for r in (Rest.from_stored(x)
                                        for x in (row.get("moved") or ()))
                            if r is not None),
                was_on=tuple(r for r in (Rest.from_stored(x)
                                         for x in (row.get("was_on") or ()))
                             if r is not None)))
        return Ledger(tuple(tracked), tuple(nodes), tuple(history))


# ------------------------------------------------------------- digesting ---


def digest_of(*parts: object) -> str:
    """The material content of one input, as a short stable hash.

    WHAT IS HASHED IS WHAT THE CALLER DECLARES MATERIAL. A fact's statement
    and date are material; the turn it arrived on is not, and hashing it
    would make every restatement look like a correction -- which is the
    cascade firing on every turn, the noise §5.4's bound exists to prevent.
    """
    material = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(material.encode("utf8")).hexdigest()[:16]


# ------------------------------------------------------------- observing ---


@implements("A3")
def observe(ledger: Ledger, kind: InputKind, id_: str, digest: str, *,
            reason: str = "", withdrawn: bool = False) -> tuple[Ledger, bool]:
    """Record where one input now stands. Returns the ledger and WHETHER IT MOVED.

    THE BOOLEAN IS THE POINT. A caller that has to compare digests itself is a
    caller that can compare them differently from the next one, and the two
    disagreeing is a change that reaches half the closure.

    A FIRST OBSERVATION IS NOT A MOVE. Version 1 of an input is the input
    arriving, and treating it as a change would invalidate every node computed
    on the same turn it was recorded -- announcing a correction on a file where
    nothing has been corrected.
    """
    existing = ledger.input_of(kind, id_)
    if existing is None:
        row = Tracked(kind=kind, id=id_, version=1, digest=digest,
                      reason=reason or "first recorded", withdrawn=withdrawn)
        return replace(ledger, tracked=(*ledger.tracked, row)), False
    if existing.digest == digest and existing.withdrawn == withdrawn:
        return ledger, False
    row = Tracked(kind=kind, id=id_, version=existing.version + 1,
                  digest=digest,
                  reason=reason or ("withdrawn" if withdrawn else "corrected"),
                  withdrawn=withdrawn)
    tracked = tuple(row if (t.kind is kind and t.id == id_) else t
                    for t in ledger.tracked)
    return replace(ledger, tracked=tracked), True


def _version_of(ledger: Ledger, rest: Rest) -> int:
    """The version the ledger currently holds for one edge's target.

    A DERIVED EDGE HAS NO `Tracked` ROW, because a node is not an input the
    advocate corrects -- it is a value the product computed. Its version is
    therefore how many times it has been revised, which is the only monotonic
    count that exists for it and is exactly what a dependent needs in order to
    notice that its own input moved.
    """
    if rest.kind is InputKind.DERIVED:
        return len(ledger.revisions_of(rest.id)) + 1
    tracked = ledger.input_of(rest.kind, rest.id)
    return tracked.version if tracked is not None else 0


@implements("A3")
def record(ledger: Ledger, node: Node) -> Ledger:
    """Record a computed node against the input versions the ledger now holds.

    THE VERSIONS ARE STAMPED HERE, FROM THE LEDGER, and not taken from the
    caller. A caller supplying its own version numbers is a caller that can
    supply a stale one, and a node stamped with a version older than the input
    it actually used is a node that reads as affected when it is not -- or, in
    the other direction, one that reads as current when it is not.
    """
    stamped = tuple(replace(rest, version=_version_of(ledger, rest))
                    for rest in node.rests_on)
    fresh = replace(node, rests_on=stamped)
    if ledger.node(node.name) is None:
        return replace(ledger, nodes=(*ledger.nodes, fresh))
    return replace(ledger, nodes=tuple(
        fresh if n.name == node.name else n for n in ledger.nodes))


# --------------------------------------------------------------- closure ---


@implements("A3")
def closure(ledger: Ledger, moved: tuple[Rest, ...]) -> tuple[str, ...]:
    """Every node a change reaches, TRANSITIVELY, and no other.

    THE POPULATION IS THE NODES, asked which of them touch a moved input --
    the same direction `cascade.dependents` takes, and for the same reason:
    asked the other way it would confirm that the inputs it knew about were
    known about, which cannot fail.

    CYCLES TERMINATE. A derived value that rests on itself, directly or round
    a ring, is a defect in whatever recorded it -- and a closure that hung on
    one would take the whole product down rather than reporting the ring. The
    frontier is a set and a node is added once, so a ring is walked once.
    """
    hit = {(r.kind, r.id) for r in moved}
    reached: set[str] = set()
    frontier = True
    while frontier:
        frontier = False
        for node in ledger.nodes:
            if node.name in reached:
                continue
            for rest in node.rests_on:
                if (rest.kind, rest.id) in hit:
                    reached.add(node.name)
                    # A NODE THAT IS REACHED BECOMES A MOVED INPUT ITSELF.
                    # This is the transitive edge, and it is the one
                    # `cascade` has no way to express.
                    hit.add((InputKind.DERIVED, node.name))
                    frontier = True
                    break
    return tuple(sorted(reached))


@implements("A3")
def invalidate(ledger: Ledger, moved: tuple[Rest, ...], *, reason: str,
               at: str = "") -> tuple[Ledger, tuple[str, ...]]:
    """Mark exactly the affected closure stale, keeping the prior state.

    NODES OUTSIDE THE CLOSURE ARE NOT TOUCHED -- not re-stamped, not
    re-timestamped, not re-reasoned. That is the second half of BK-65-AC1 and
    it is easy to lose by rebuilding the whole tuple with a fresh timestamp,
    which looks harmless and makes every independent conclusion report that
    something happened to it.
    """
    affected = closure(ledger, moved)
    if not affected:
        return ledger, ()
    hit = set(affected)
    revisions = list(ledger.history)
    nodes: list[Node] = []
    for node in ledger.nodes:
        if node.name not in hit:
            nodes.append(node)
            continue
        why = _why(moved, node, reason)
        revisions.append(Revision(
            name=node.name, was=node.value, now="", reason=why, at=at,
            moved=tuple(moved), was_on=node.rests_on))
        nodes.append(replace(
            node, currency=Currency.STALE, stale_because=why,
            # THE ATTEMPT COUNT RESETS ON A NEW INVALIDATION. A node that
            # exhausted its rework against yesterday's correction has not
            # exhausted it against today's, and carrying the count forward
            # would leave a node permanently unreworkable after one bad day.
            rework_attempts=0, rework_exhausted=False))
    return replace(ledger, nodes=tuple(nodes),
                   history=tuple(revisions)), affected


def _why(moved: tuple[Rest, ...], node: Node, reason: str) -> str:
    """The sentence the advocate reads, naming what moved and how far.

    DIRECT AND INDIRECT ARE SAID DIFFERENTLY. "The date you corrected" and
    "something the date you corrected fed into" are different facts, and an
    advocate reading the second as the first goes looking for a correction
    they did not make.
    """
    direct = [r for r in moved
              if any(x.kind is r.kind and x.id == r.id for x in node.rests_on)]
    if direct:
        what = ", ".join(f"{r.kind.value} {r.id} (now version {r.version})"
                         for r in direct)
        return f"{what} moved — {reason}" if reason else f"{what} moved"
    what = ", ".join(f"{r.kind.value} {r.id}" for r in moved)
    return (f"this rests on something that {what} fed into"
            + (f" — {reason}" if reason else ""))


@implements("A3")
def recomputed(ledger: Ledger, name: str, value: str, *,
               at: str = "", reason: str = "") -> Ledger:
    """A stale node has been recomputed. Close its revision with the new value.

    THE REVISION IS CLOSED RATHER THAN A SECOND ONE OPENED. One correction is
    one entry in the history with a `was` and a `now`; two entries would make
    a single change read as two, which is the same defect as one dispute
    recorded twice.
    """
    node = ledger.node(name)
    if node is None:
        return ledger
    history = list(ledger.history)
    for index in range(len(history) - 1, -1, -1):
        if history[index].name == name and not history[index].now:
            history[index] = replace(history[index], now=value)
            break
    nodes = tuple(
        replace(n, value=value, currency=Currency.CURRENT, stale_because="",
                computed_at=at or n.computed_at, reason=reason or n.reason,
                rework_attempts=0, rework_exhausted=False)
        if n.name == name else n
        for n in ledger.nodes)
    return replace(ledger, nodes=nodes, history=tuple(history))


# ---------------------------------------------------------------- rework ---


@implements("A3")
def due(ledger: Ledger) -> tuple[Node, ...]:
    """Stale nodes still within their rework bound, nearest to the change first.

    `REWORKING` IS NOT OFFERED AGAIN. A node already claimed by a runner is
    one another runner must not pick up, and the state is on the node rather
    than in the runner's memory so a restart cannot lose it.
    """
    return tuple(n for n in ledger.nodes
                 if n.currency is Currency.STALE and not n.rework_exhausted
                 and n.rework_attempts < REWORK_LIMIT)


@implements("A3")
def claim(ledger: Ledger, name: str) -> Ledger:
    """Take a node for recomputation. One more attempt against the bound."""
    node = ledger.node(name)
    if node is None or node.currency is not Currency.STALE:
        return ledger
    return replace(ledger, nodes=tuple(
        replace(n, currency=Currency.REWORKING,
                rework_attempts=n.rework_attempts + 1)
        if n.name == name else n for n in ledger.nodes))


@implements("A3")
def rework_failed(ledger: Ledger, name: str, why: str) -> Ledger:
    """A recomputation did not produce a value. BACK TO STALE, NEVER CURRENT.

    AT THE BOUND IT IS EXHAUSTED AND STILL STALE. A queue that gives up and
    marks the node current is worse than no queue: it converts a known-stale
    conclusion into a certified one, at the moment nobody is watching.
    """
    node = ledger.node(name)
    if node is None:
        return ledger
    exhausted = node.rework_attempts >= REWORK_LIMIT
    because = (f"{node.stale_because}; recomputation failed {node.rework_attempts} "
               f"time(s) — {why}" if not exhausted else
               f"{node.stale_because}; recomputation was attempted "
               f"{node.rework_attempts} time(s) and stopped at the bound of "
               f"{REWORK_LIMIT} — {why}. This value is still stale and no "
               f"further attempt is scheduled.")
    return replace(ledger, nodes=tuple(
        replace(n, currency=Currency.STALE, stale_because=because,
                rework_exhausted=exhausted)
        if n.name == name else n for n in ledger.nodes))


# ----------------------------------------------------------- enforcement ---


@implements("A3")
def presentable(ledger: Ledger, name: str) -> tuple[bool, str]:
    """May this conclusion be shown as current, and if not, why not.

    AN UNRECORDED NODE IS REFUSED. That is the direction this whole module
    must fail in: a name the ledger has never heard of has no established
    currency, and answering "yes, it is fine" for it would make the control
    silent for exactly the conclusions nobody remembered to record.
    """
    node = ledger.node(name)
    if node is None:
        return False, (f"{name} has no dependency record, so whether it is "
                       f"still current has not been established")
    if node.currency.usable:
        return True, ""
    return False, node.stale_because or (
        f"{node.label} is {node.currency.value} and must not be shown as "
        f"current")


@implements("A3")
def withheld(ledger: Ledger, names: tuple[str, ...]) -> tuple[str, ...]:
    """The reasons, for every name that may not be served. Empty is the pass.

    NAMED, NOT COUNTED, for the reason every other list in this product is:
    a number tells the advocate something is wrong and not what.
    """
    out: list[str] = []
    for name in names:
        allowed, why = presentable(ledger, name)
        if not allowed:
            out.append(why)
    return tuple(out)


@implements("A3")
def released(ledger: Ledger) -> tuple[bool, tuple[str, ...]]:
    """Whether the file may be released, and everything blocking it.

    RELEASE IS A SEPARATE QUESTION FROM A READ, and it is stricter: a read may
    show a stale value LABELLED stale, because hiding it tells the advocate
    there was never a conclusion. A release asserts the file is current, and
    one stale node makes that assertion false.
    """
    blocking = tuple(f"{n.label}: {n.stale_because}" for n in ledger.stale())
    return (not blocking), blocking


# ------------------------------------------------ the one bridge to cascade ---


@implements("A3")
def from_derived(row, *, premises: tuple[str, ...] = (),
                 authorities: tuple[str, ...] = (),
                 unknown: bool = False, reason: str = "",
                 at: str = "") -> Node:
    """Build a ledger node from the `cascade.Derived` row the turn already made.

    THE ONE PLACE THE TWO MECHANISMS MEET. `cascade.Derived.from_facts` stays
    the single statement of which facts a value rests on -- this reads it
    rather than restating it -- and the premise and authority edges are named
    by the code that computed the value, where they are known.

    `unknown` IS AN HONEST DECLARATION AND NOT A DEFAULT. A caller that knows
    its value rested on something it cannot name says so, and the node it
    produces can never be certified current. What is refused is the silent
    version of that: a computation with unrecorded inputs looking exactly like
    one with none.
    """
    rests = [Rest(kind=InputKind.FACT, id=str(f))
             for f in getattr(row, "from_facts", ()) or ()]
    rests.extend(Rest(kind=InputKind.PREMISE, id=p) for p in premises)
    rests.extend(Rest(kind=InputKind.AUTHORITY, id=a) for a in authorities)
    if unknown:
        rests.append(Rest(kind=InputKind.UNKNOWN, id="undeclared"))
    return Node(name=getattr(row, "name", ""), value=getattr(row, "value", ""),
                shown=getattr(row, "shown", "") or "",
                rests_on=tuple(rests), computed_at=at, reason=reason)


@implements("A3")
def report(ledger: Ledger) -> tuple[str, ...]:
    """What the advocate reads about currency. ONE LINE where nothing is stale.

    §5.4's bound, applied to this mechanism as well: a product that printed a
    currency section every turn would train the advocate to skip it.
    """
    bad = ledger.stale()
    if not bad:
        return ("Every recorded conclusion on this file is current against the "
                "inputs it was computed from.",)
    lines = []
    for node in bad:
        line = f"{node.label}: {node.currency.value} — {node.stale_because}"
        if node.rework_exhausted:
            line += " No further recomputation is scheduled."
        lines.append(line)
    return tuple(lines)
