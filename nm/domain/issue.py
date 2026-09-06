"""Issue facets and disposition. D9.

THE MEASURED COUNTEREXAMPLE
----------------------------
Classification in the previous build discarded **20.1% of all issue labels ever
spotted — 641 of 3,192** — led by limitation (122), bail (86) and forum or
jurisdiction (58). The three things an advocate can least afford to lose were
the three most often lost.

Nothing was wrong with the labels. They were spotted correctly, and then a
filter that decided what was "relevant enough" dropped them, silently, with no
count and no trace. The advocate saw a shorter list and had no way to know it
was shorter.

So THERE IS NO DELETE PATH. Not "deleting is discouraged" — there is no
function here that removes an issue. An issue that will not be run is an issue
with `disposition: parked` and a reason, and it appears on the
"considered, not pursued" line. Deleting is silent; a disposition is visible.

`accounted_for` is the invariant, and it is the same shape as
`Limitation.accounts_for_every_entry`: it returns what was LOST, so a
conservation failure names the issues rather than reporting a number that
dropped.

EFFECT IS DERIVED FROM POSTURE AND IS NEVER STORED
----------------------------------------------------
D9's second NEVER: *never build "this obstructs us" into the vocabulary. A
limitation point is not "a bar" — ours obstructs us, theirs disposes of their
claim without our touching the merits.*

A stored effect cannot detect its own reversal. The advocate corrects the
posture on turn 4, every issue's effect flips, and a field written on turn 2
still says `opposes` — which is the same failure `Deadline.status` is a method
for, and the same one `Posture.side` is a property for. So `effect` is computed
from the posture each time it is asked for, and the projection records the
posture VERSION it was computed against, so a stale reading is detectable
rather than invisible.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from nm.domain.matter import Posture, Side, ThreadId, new_id
from nm.domain.text import blank, refuses_blank_text
from nm.domain.traceability import implements


class IssueKind(str, Enum):
    """What sort of issue. NOT a priority, and not a visibility rule.

    D9: *disposition, not kind, governs visibility*, and *never give a
    threshold or procedural issue a thinner pipeline than a substantive one.*
    A threshold issue disposes of a claim without reaching the merits, so
    ranking it below one is exactly backwards.
    """

    THRESHOLD = "threshold"
    SUBSTANTIVE = "substantive"
    PROCEDURAL = "procedural"
    NOT_ESTABLISHED = "not_established"


class Effect(str, Enum):
    """Whose case this issue helps. DERIVED, never stored -- see the module docstring."""

    SUPPORTS = "supports"
    OPPOSES = "opposes"
    NEUTRAL = "neutral"
    NOT_ASSESSED = "not_assessed"


class DispositionState(str, Enum):
    """What is being done about it. THE COMPLETE SET, and there is no fifth
    member meaning "gone"."""

    RUN = "run"
    PARKED = "parked"
    BLOCKED = "blocked"
    CLOSED = "closed"


@dataclass(frozen=True)
class Disposition:
    """A state AND the reason for it.

    `parked` and `closed` REQUIRE a reason and `blocked` requires what it
    needs, because those are the three that stop work. A stopped issue with no
    reason is indistinguishable from a deleted one at the point it matters --
    when the advocate asks why they are not running it.
    """

    state: DispositionState
    reason: str = ""
    needs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state in (DispositionState.PARKED, DispositionState.CLOSED) \
                and blank(self.reason):
            raise ValueError(
                f"an issue {self.state.value} with no reason is a deletion with "
                f"extra steps. D9 has no delete path: what will not be run is "
                f"parked WITH ITS REASON and appears on the "
                f"'considered, not pursued' line.")
        if self.state is DispositionState.BLOCKED and not self.needs:
            raise ValueError(
                "a BLOCKED issue must name what it needs. 'Blocked' with no "
                "needs tells the advocate something is stuck and nothing about "
                "how to unstick it.")

    @property
    def visible(self) -> bool:
        """D9: *disposition, not kind, governs visibility.*

        Everything is visible. `parked` is visible on its own line rather than
        in the working set, which is a different thing from hidden -- and the
        distinction is the whole feature.
        """
        return True


@refuses_blank_text("statement")
@dataclass(frozen=True)
class Issue:
    """One issue on one thread. PRODUCES per D9.

    `effect` is NOT a field. See `effect_for`.
    """

    thread: ThreadId
    statement: str
    id: str = field(default_factory=lambda: new_id("iss"))
    kind: IssueKind = IssueKind.NOT_ESTABLISHED
    runs_against: Side = Side.UNKNOWN
    """WHOSE case this issue runs against, as a fact about the issue.

    This is the half that does not change when the posture does. A limitation
    point runs against whoever is asserting the claim; whether that helps or
    hurts OUR client is then a question about which side we are on, and the two
    are combined by `effect_for` rather than baked together at spotting time.

    Baking them together is the defect D9 names: an issue labelled "a bar"
    carries an opinion about whose problem it is, and that opinion is wrong for
    half the advocates who will read it."""
    proof: str = ""
    disposition: Disposition = field(
        default_factory=lambda: Disposition(DispositionState.RUN))
    serves_theory: str = ""
    provisions: tuple[str, ...] = ()
    authorities: tuple[str, ...] = ()
    deadline: str | None = None

    @implements("D9")
    def effect_for(self, posture: Posture) -> tuple[Effect, int]:
        """The effect, AND the posture version it was computed against.

        Returns both because a caller that records one without the other has
        recorded a value it cannot later tell is stale. The version is
        `effect_basis` in the PRODUCES contract.

        THE SAME ISSUE ON OPPOSITE POSTURES YIELDS OPPOSITE EFFECT (E-061),
        and that falls out of the arithmetic rather than being asserted: the
        issue knows whose claim it runs against, the posture knows which side
        we are, and neither knows the answer alone.
        """
        if self.runs_against is Side.UNKNOWN or not posture.resolved:
            # NOT ASSESSED, and it is a value. `neutral` here would be a
            # finding that the issue helps nobody, which nobody established.
            return Effect.NOT_ASSESSED, posture.version
        if self.runs_against is posture.side:
            return Effect.OPPOSES, posture.version
        return Effect.SUPPORTS, posture.version


@implements("D9")
def classify(spotted: tuple[Issue, ...],
             dispositions: dict[str, Disposition] | None = None,
             ) -> tuple[Issue, ...]:
    """Apply dispositions. RETURNS EVERY ISSUE IT WAS GIVEN.

    There is no predicate here and no filter, and that is the feature. The
    measured defect was a classifier that decided what was relevant enough and
    dropped 641 of 3,192 labels; anything shaped like a filter would reproduce
    it however carefully the predicate were written.

    An issue with no disposition supplied keeps the one it has. An issue the
    caller wants stopped gets `parked` WITH A REASON, which the `Disposition`
    constructor requires.
    """
    given = dispositions or {}
    return tuple(replace(i, disposition=given[i.id]) if i.id in given else i
                 for i in spotted)


@implements("D9")
def accounted_for(spotted: tuple[Issue, ...],
                  classified: tuple[Issue, ...]) -> tuple[str, ...]:
    """E-060'S INVARIANT. The issues that went in and did not come out.

    Returns the LOST ONES rather than a count, for the same reason
    `Limitation.accounts_for_every_entry` does: a number that dropped tells the
    reader something is wrong and nothing about what. The measured failure lost
    limitation, bail and forum -- and which three were lost is the entire
    difference between a rounding error and an advocate missing a deadline.
    """
    out = {i.id for i in classified}
    return tuple(i.statement[:80] for i in spotted if i.id not in out)


@implements("D9")
def considered_not_pursued(issues: tuple[Issue, ...]) -> tuple[str, ...]:
    """D9: *surface parked issues as the "considered, not pursued" line, one
    line with its reason.*

    This is what makes a disposition different from a deletion in the only
    place it counts -- what the advocate actually reads.
    """
    return tuple(
        f"{i.statement[:90]} — not pursued: {i.disposition.reason}"
        for i in issues if i.disposition.state is DispositionState.PARKED)


def facet(enum_type, value, *, default=None):
    """An out-of-vocabulary facet value is BLANKED AND RE-DERIVED (D9).

    ONE OWNER, and the docstring of the NEVER clause says why: *whichever path
    supplied it.* Two call sites each doing their own `try: Enum(v)` is two
    chances to differ, and the measured defect -- `tracks {'civil': 2,
    'revenue': 1}` passing unvalidated and emptying the charge map -- entered
    through the path nobody had guarded.

    `default` is the enum's own NOT_ESTABLISHED-style member, passed by the
    caller because only the caller knows which member that is.
    """
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().lower())
    except (ValueError, AttributeError):
        return default


@implements("D9")
def merge(standing: tuple[Issue, ...], spotted: tuple[Issue, ...],
          ) -> tuple[Issue, ...]:
    """The issues on the thread after this turn. THE LIST IS NOT REPLACED.

    THE MEASURED DEFECT. GS-15, 6 September 2026: the issue count went 1, 1,
    1, 0, 2 across five turns. On turn 4 the thread had NO ISSUES AT ALL,
    having had one for the three turns before it. Nothing disposed of it --
    the read simply did not mention it, and the list was whatever the read
    returned.

    `DispositionState` already says this must not happen: *"THE COMPLETE SET,
    and there is no fifth member meaning 'gone'"*, and `Disposition` refuses
    PARKED or CLOSED without a reason because *"a stopped issue with no reason
    is indistinguishable from a deleted one at the point it matters -- when
    the advocate asks why they are not running it."*

    The type forbade the delete path and the ARCHITECTURE deleted every issue
    on every turn by rebuilding the list. A rule the data model enforces and
    the pipeline routes around is not enforced.

    IDENTITY IS THE STATEMENT, folded. An `Issue` gets a fresh id from every
    read, so ids cannot match across turns; two issues asking the court the
    same question are the same issue, which is also what a person would say.
    The standing one WINS on a match -- it carries a disposition that a fresh
    read knows nothing about, and overwriting it would be the deletion again
    wearing an update's clothes.
    """
    out = list(standing)
    seen = {_fold(i.statement) for i in standing}
    for issue in spotted:
        key = _fold(issue.statement)
        if key and key not in seen:
            seen.add(key)
            out.append(issue)
    return tuple(out)


def _fold(text: str) -> str:
    return " ".join((text or "").lower().split())


@implements("D9")
def from_stored(values) -> tuple[Issue, ...]:
    """Issues read back off a thread, whatever shape the store returned.

    `Thread.issues` is untyped for the same reason `Thread.theory` is: this
    module imports `nm.domain.matter`, so `matter` cannot name `Issue` without
    a cycle. The generic decoder therefore hands back plain dicts, and the
    NEXT turn would merge dicts against Issues and match nothing -- every
    issue would look new, every turn, which is the defect this exists to fix
    arriving through its own repair.

    A row that cannot be rebuilt is DROPPED AND THE REST KEPT. Losing one
    issue to a record written before a rule existed is bad; losing the whole
    list to it is worse.
    """
    if not values:
        return ()
    out: list[Issue] = []
    for v in values:
        if isinstance(v, Issue):
            out.append(v)
            continue
        if not isinstance(v, dict) or not str(v.get("statement") or "").strip():
            continue
        try:
            out.append(Issue(
                thread=ThreadId(str(v.get("thread") or "")),
                statement=str(v["statement"]),
                kind=IssueKind(v.get("kind") or IssueKind.NOT_ESTABLISHED),
                runs_against=Side(v.get("runs_against") or Side.UNKNOWN),
                proof=str(v.get("proof") or ""),
            ))
        except (ValueError, TypeError):
            continue
    return tuple(out)
