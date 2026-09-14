"""HELD AND ERASED AS DECISIONS, NOT AS SIDE EFFECTS. BK-85-AC4, BK-88-AC1. P33.

    from nm.domain.retention import RetentionRequest, RetentionState, request

WHAT THIS IS FOR
------------------
An advocate, or the client whose material it is, asks for something to be held
or erased. The answer they get is acted on and cannot be taken back, so the two
ways of getting it wrong are both severe:

* saying ERASED while a transcript, an extracted page, a processor copy or a
  restorable backup of the same recording is still readable;
* erasing material a hold required to be kept.

Both are sentences somebody repeats to a court. This module makes each of them
a state that has to be reached rather than a boolean that can be asserted.

IT IS NOT A SECOND RETENTION VOCABULARY
-----------------------------------------
`nm.domain.media.Retention` already owns *how long an original is kept* --
`MATTER_LIFE`, `FIXED_PERIOD`, `DELETE_AFTER_DERIVATION`, `NOT_DECIDED` -- and
`nm.edge.uploads` already refuses original bytes under an undecided one. That is
the POLICY on one asset. This is the LIFECYCLE of one request against many
assets, and it reads that policy rather than restating it. Two owners for one
notion is the §4 defect; two notions is not, and the distinction is the reason
this module exists beside `media.py` instead of inside it.

ARCHIVING, WITHDRAWING ACCESS AND ERASING ARE THREE THINGS
-------------------------------------------------------------
`RequestedAction` keeps them apart -- `RESTRICT_ACCESS`, `REVIEW_RETENTION`,
`ERASE`. Collapsing them is how "we deleted it" comes to mean "we hid it". A
restriction that reports itself as an erasure is a false statement about
material that still exists, and the material is usually still discoverable.

WHY COMPLETION IS COUNTED AND NOT DECLARED
---------------------------------------------
`complete_for_declared_scope` is the only state that means the declared scope is
actually gone, and `completion_problems` refuses it while a single asset is
unresolved or a single reason to retain still stands. The counts are carried on
the request -- `expected_asset_count` against `resolved_asset_count` -- so the
claim is arithmetic rather than assertion. The contract states the same rule
from the other end: *incomplete processor/backup inventory cannot return
complete_for_declared_scope.*

    A receipt is not an erasure. `request()` can only ever produce
    REVIEW_REQUESTED, which is the contract's "receipt never means erased"
    made unrepresentable rather than merely forbidden.

THE TRANSITION TABLE IS DATA
------------------------------
`_ALLOWED` is the whole rule. A new state is an edit to one mapping, and
`refuse_transition` reports WHICH move was refused rather than a boolean, for
the reason `Mandate.expansions_over` names its expansions: a caller that is told
only "no" cannot tell the advocate what happened.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from nm.domain.text import blank, refuses_blank_text


class RetentionState(str, Enum):
    """Where one request has got to. The vocabulary is the served contract's.

    NOT a progress bar: `UNDER_HOLD` and `DECLINED` are ordinary destinations,
    and `BACKUP_EXPIRY_PENDING` is the honest state for material removed from
    every active system while a backup generation still holds it.
    """

    REVIEW_REQUESTED = "review_requested"
    UNDER_HOLD = "under_hold"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    ERASED_FROM_ACTIVE_SYSTEMS = "erased_from_active_systems"
    BACKUP_EXPIRY_PENDING = "backup_expiry_pending"
    COMPLETE_FOR_DECLARED_SCOPE = "complete_for_declared_scope"
    DECLINED = "declined"

    @classmethod
    def not_established(cls) -> "RetentionState":
        """THE ESCAPE, DECLARED, as `media.Retention` declares its own.

        A request that has been received and not yet assessed is
        REVIEW_REQUESTED. There is deliberately no `UNKNOWN`: a request always
        has a state from the moment it exists, and inventing one would create a
        way for a live request to read as nothing in particular.
        """
        return cls.REVIEW_REQUESTED

    @property
    def is_terminal(self) -> bool:
        return self in (RetentionState.COMPLETE_FOR_DECLARED_SCOPE,
                        RetentionState.DECLINED)


class RetainedReason(str, Enum):
    """Why something is still held. Named so the advocate is told which."""

    LEGAL_HOLD = "legal_hold"
    APPROVED_RETENTION = "approved_retention"
    PROCESSOR_PENDING = "processor_pending"
    BACKUP_EXPIRY = "backup_expiry"
    REVIEW_PENDING = "review_pending"


class RequestedAction(str, Enum):
    """THREE DIFFERENT ASKS. See the module docstring: they are not degrees."""

    RESTRICT_ACCESS = "restrict_access"
    REVIEW_RETENTION = "review_retention"
    ERASE = "erase"


class RequestScope(str, Enum):
    SELECTED_ASSETS = "selected_assets"
    MATTER_LIFECYCLE_REVIEW = "matter_lifecycle_review"


#: WHICH MOVES EXIST. Everything absent from this mapping is refused by name.
#:
#: Read the shape rather than the rows: a hold can interrupt from any live
#: state, review and approval precede work, and the two ways out of active
#: erasure are "a backup still holds it" and "the declared scope is gone".
#: Nothing leads out of a terminal state -- a completed erasure that could be
#: moved back to APPROVED would let a later write undo the tombstone.
_ALLOWED: dict[RetentionState, frozenset[RetentionState]] = {
    RetentionState.REVIEW_REQUESTED: frozenset({
        RetentionState.UNDER_HOLD, RetentionState.APPROVED,
        RetentionState.DECLINED}),
    RetentionState.UNDER_HOLD: frozenset({
        RetentionState.REVIEW_REQUESTED, RetentionState.DECLINED}),
    RetentionState.APPROVED: frozenset({
        RetentionState.IN_PROGRESS, RetentionState.UNDER_HOLD,
        RetentionState.DECLINED}),
    RetentionState.IN_PROGRESS: frozenset({
        RetentionState.ERASED_FROM_ACTIVE_SYSTEMS, RetentionState.UNDER_HOLD}),
    RetentionState.ERASED_FROM_ACTIVE_SYSTEMS: frozenset({
        RetentionState.BACKUP_EXPIRY_PENDING,
        RetentionState.COMPLETE_FOR_DECLARED_SCOPE}),
    RetentionState.BACKUP_EXPIRY_PENDING: frozenset({
        RetentionState.COMPLETE_FOR_DECLARED_SCOPE}),
    RetentionState.COMPLETE_FOR_DECLARED_SCOPE: frozenset(),
    RetentionState.DECLINED: frozenset(),
}


@refuses_blank_text()
@dataclass(frozen=True)
class AssetRef:
    """One asset at one version. The version is not decoration.

    Erasure is agreed against what the inventory said at the time. An asset
    that has moved since is a different object, and resolving it silently is
    how a newer copy survives an erasure everybody believes completed.
    """

    id: str
    version: int


@refuses_blank_text("released_by", "released_at")
@dataclass(frozen=True)
class Hold:
    """A reason material must be kept, and who is accountable for it.

    `released_by` and `released_at` are EXEMPT from the blank rule because
    their emptiness is this type's live state: a hold that has not been
    released carries neither, and requiring them would make an active hold
    unrepresentable.
    """

    hold_id: str
    reason: str
    placed_by: str
    placed_at: str
    released_by: str = ""
    released_at: str = ""

    @property
    def is_active(self) -> bool:
        return blank(self.released_at)


@refuses_blank_text()
@dataclass(frozen=True)
class Tombstone:
    """WHAT WAS ERASED, kept after the thing itself is gone.

    A tombstone is not a copy and carries no content -- only the identity, when
    it went and under which request. It exists so a restore can be asked *was
    this erased?* and get an answer, because a backup does not know that the
    live system deleted something after the backup was taken.
    """

    asset_id: str
    asset_version: int
    erased_at: str
    request_id: str


@refuses_blank_text("resolved_at")
@dataclass(frozen=True)
class Copy:
    """One place a copy is known to live, and whether it is resolved.

    `resolved_at` empty means outstanding. A copy nobody has confirmed is
    outstanding, never absent: this is CLAUDE.md §9 at the one place where
    reading an unconfirmed processor as "nothing there" produces a false
    completion.
    """

    location: str
    kind: str = "derivative"
    resolved_at: str = ""

    @property
    def is_resolved(self) -> bool:
        return not blank(self.resolved_at)


@refuses_blank_text("declined_because")
@dataclass(frozen=True)
class RetentionRequest:
    """One asked-for change to what is kept, and everything decided about it."""

    request_id: str
    matter_id: str
    requested_by: str
    requested_at: str
    scope: RequestScope
    requested_action: RequestedAction
    purpose: str
    authority_id: str
    authority_version: int
    assets: tuple[AssetRef, ...] = ()
    copies: tuple[Copy, ...] = ()
    holds: tuple[Hold, ...] = ()
    tombstones: tuple[Tombstone, ...] = ()
    state: RetentionState = RetentionState.REVIEW_REQUESTED
    declined_because: str = ""
    next_review_at: str = ""
    version: int = 1

    @property
    def active_holds(self) -> tuple[Hold, ...]:
        return tuple(h for h in self.holds if h.is_active)

    @property
    def expected_asset_count(self) -> int:
        return len(self.assets)

    @property
    def resolved_asset_count(self) -> int:
        """Resolved COPIES, counted against the assets they belong to.

        An asset is resolved when every copy naming it is resolved; an asset
        with no copy recorded is NOT resolved, because an empty inventory is
        the absence of a search rather than the absence of copies.
        """
        by_asset: dict[str, list[Copy]] = {}
        for copy in self.copies:
            by_asset.setdefault(copy.location.split("#", 1)[0], []).append(copy)
        resolved = 0
        for asset in self.assets:
            found = by_asset.get(asset.id) or []
            if found and all(c.is_resolved for c in found):
                resolved += 1
        return resolved

    @property
    def retained_reason_codes(self) -> tuple[RetainedReason, ...]:
        """Every reason something is still kept, in the contract's vocabulary.

        Derived, never stored: a stored list is a second copy of a fact the
        request already carries, and it would go stale exactly when a hold is
        released.
        """
        out: list[RetainedReason] = []
        if self.active_holds:
            out.append(RetainedReason.LEGAL_HOLD)
        if self.state in (RetentionState.REVIEW_REQUESTED,
                          RetentionState.UNDER_HOLD):
            out.append(RetainedReason.REVIEW_PENDING)
        if any(c.kind == "processor" and not c.is_resolved for c in self.copies):
            out.append(RetainedReason.PROCESSOR_PENDING)
        if any(c.kind == "backup" and not c.is_resolved for c in self.copies):
            out.append(RetainedReason.BACKUP_EXPIRY)
        if self.requested_action is RequestedAction.RESTRICT_ACCESS:
            out.append(RetainedReason.APPROVED_RETENTION)
        return tuple(dict.fromkeys(out))

    def completion_problems(self) -> tuple[str, ...]:
        """Every reason this request may NOT claim the scope is gone.

        Empty means it may. The population is returned rather than a boolean
        so the served answer can say which copy is outstanding -- an advocate
        told "not complete" and not told why cannot chase the processor.
        """
        problems: list[str] = []
        if self.requested_action is not RequestedAction.ERASE:
            problems.append(
                f"the request asked to {self.requested_action.value}, not to "
                f"erase; restricting access is not deletion")
        for hold in self.active_holds:
            problems.append(f"hold {hold.hold_id!r} is active: {hold.reason}")
        outstanding = [c for c in self.copies if not c.is_resolved]
        for copy in outstanding:
            problems.append(f"{copy.kind} copy at {copy.location!r} is unresolved")
        if self.expected_asset_count and not self.copies:
            problems.append(
                f"{self.expected_asset_count} asset(s) in scope and no copy "
                f"inventory: an empty inventory is an unrun search, not proof "
                f"that no copy exists")
        missing = self.expected_asset_count - self.resolved_asset_count
        if missing > 0:
            problems.append(
                f"{missing} of {self.expected_asset_count} asset(s) in the "
                f"declared scope are not resolved")
        return tuple(problems)


def refuse_transition(request: RetentionRequest,
                      target: RetentionState) -> str:
    """Why this move is refused, or "" when it is allowed. ONE OWNER.

    Both ends call this -- the domain when a request is advanced, and the
    served path before it writes -- for the reason P47's mandate check is used
    at admission and acceptance: a rule enforced at one end only is enforced
    until somebody adds a second caller.
    """
    if target is request.state:
        return (f"the request is already {target.value}; a repeated transition "
                f"is not a state change and must not bump the version")
    if request.state.is_terminal:
        return (f"the request is {request.state.value}, which is final; a "
                f"completed erasure that could be moved back would let a "
                f"later write undo its tombstones")
    allowed = _ALLOWED.get(request.state, frozenset())
    if target not in allowed:
        permitted = ", ".join(sorted(s.value for s in allowed)) or "nothing"
        return (f"{request.state.value} -> {target.value} is not a lifecycle "
                f"transition; from {request.state.value} the request may only "
                f"become {permitted}")
    if target is RetentionState.COMPLETE_FOR_DECLARED_SCOPE:
        problems = request.completion_problems()
        if problems:
            return ("the declared scope is not gone: " + "; ".join(problems))
    if (request.active_holds
            and target in (RetentionState.APPROVED, RetentionState.IN_PROGRESS,
                           RetentionState.ERASED_FROM_ACTIVE_SYSTEMS)):
        held = ", ".join(repr(h.hold_id) for h in request.active_holds)
        return (f"hold(s) {held} are active; material under a hold is not "
                f"erased, and the request stays visible rather than failing "
                f"quietly")
    return ""


def request(*, request_id: str, matter_id: str, requested_by: str,
            requested_at: str, scope: RequestScope,
            requested_action: RequestedAction, purpose: str,
            authority_id: str, authority_version: int,
            assets: tuple[AssetRef, ...] = (),
            copies: tuple[Copy, ...] = (),
            holds: tuple[Hold, ...] = (),
            next_review_at: str = "") -> RetentionRequest:
    """Receive a request. IT CAN ONLY EVER BE REVIEW_REQUESTED.

    The state is not a parameter, which is the contract's *receipt never means
    erased* expressed as something a caller cannot get wrong. A request that
    arrives while a hold is active is still received -- and reads UNDER_HOLD on
    its first assessment rather than being rejected, because the person asking
    is entitled to know the material is being kept and why.
    """
    if scope is RequestScope.SELECTED_ASSETS and not assets:
        raise ValueError(
            "a selected-assets request names no asset. An empty selection is "
            "not a scope, and treating it as 'everything' or as 'nothing' are "
            "both answers nobody asked for.")
    return RetentionRequest(
        request_id=request_id, matter_id=matter_id, requested_by=requested_by,
        requested_at=requested_at, scope=scope,
        requested_action=requested_action, purpose=purpose,
        authority_id=authority_id, authority_version=authority_version,
        assets=assets, copies=copies, holds=holds,
        state=RetentionState.REVIEW_REQUESTED, next_review_at=next_review_at)


def advance(current: RetentionRequest,
            target: RetentionState) -> RetentionRequest:
    """Move a request, or raise with the reason. The version bumps here.

    `commit` does not bump for the caller anywhere else in this product, and a
    lifecycle that silently kept its version would let a stale second tab
    overwrite a completed erasure.
    """
    refused = refuse_transition(current, target)
    if refused:
        raise ValueError(refused)
    return replace(current, state=target, version=current.version + 1)


def erased_ids(requests: tuple[RetentionRequest, ...]) -> frozenset[str]:
    """Every asset id any tombstone names, across every request.

    THE RESTORE GUARD READS THIS. A backup does not know what was deleted after
    it was taken, so restoring one re-exposes material that was erased in the
    meantime unless somebody replays the tombstones over it. Drawn from the
    whole population rather than one request, because the restore does not know
    which request erased what.
    """
    return frozenset(
        t.asset_id for r in requests for t in r.tombstones)
