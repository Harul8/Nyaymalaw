"""The decisions that act on a retention request, and the restore guard. P33.

    from nm.core import retention as rt

`nm.domain.retention` holds the STATE and the transition rule; this holds the
decisions and the persistence shape, on the same split `nm.core.delegation`
keeps over `nm.domain.delegation` and for the same reason: an agent, a model or
a client may construct a request, and none of them may decide whether it is
approved, whether a hold releases, or whether the declared scope is gone.

THE RESTORE GUARD IS THE HALF NOBODY EXPECTS
-----------------------------------------------
Erasing from the active systems is the easy half. The hard half is that a
backup taken BEFORE the erasure does not know the erasure happened, so restoring
it silently re-exposes exactly the material somebody was told was gone -- and
the restore looks like a successful recovery while it does it. `refuse_restore`
replays the tombstones over whatever a restore proposes to bring back and names
every asset that must not return. It reads the tombstones of the WHOLE matter,
not of one request, because a restore does not know which request erased what.
"""
from __future__ import annotations

from dataclasses import replace

from nm.domain.retention import (
    AssetRef,
    Copy,
    Hold,
    RequestedAction,
    RequestScope,
    RetentionRequest,
    RetentionState,
    Tombstone,
    advance,
    erased_ids,
    refuse_transition,
)
from nm.domain.text import clean


def _enum(kind, value, fallback):
    try:
        return kind(value)
    except (ValueError, KeyError):
        return fallback


def as_dict(request: RetentionRequest) -> dict:
    """The stored shape. Derived counts are NOT stored.

    `expected_asset_count`, `resolved_asset_count` and `retained_reason_codes`
    are computed from the assets, copies and holds every time they are asked
    for. Storing them would put a second copy of the same fact on disk, and the
    copy would be wrong from the moment a hold is released.
    """
    return {
        "schema": 1,
        "request_id": request.request_id,
        "matter_id": request.matter_id,
        "requested_by": request.requested_by,
        "requested_at": request.requested_at,
        "scope": request.scope.value,
        "requested_action": request.requested_action.value,
        "purpose": request.purpose,
        "authority_id": request.authority_id,
        "authority_version": request.authority_version,
        "assets": [{"id": a.id, "version": a.version} for a in request.assets],
        "copies": [{"location": c.location, "kind": c.kind,
                    "resolved_at": c.resolved_at} for c in request.copies],
        "holds": [{"hold_id": h.hold_id, "reason": h.reason,
                   "placed_by": h.placed_by, "placed_at": h.placed_at,
                   "released_by": h.released_by,
                   "released_at": h.released_at} for h in request.holds],
        "tombstones": [{"asset_id": t.asset_id, "asset_version": t.asset_version,
                        "erased_at": t.erased_at,
                        "request_id": t.request_id} for t in request.tombstones],
        "state": request.state.value,
        "declined_because": request.declined_because,
        "next_review_at": request.next_review_at,
        "version": request.version,
    }


def from_dict(value: dict) -> RetentionRequest:
    """Read one back. An unreadable state reads as REVIEW_REQUESTED.

    NOT as a completed erasure: an unrecognised value must fall to the state
    that claims least, because the alternative is a corrupt row reporting that
    material is gone.
    """
    return RetentionRequest(
        request_id=clean(str(value.get("request_id") or "?")),
        matter_id=clean(str(value.get("matter_id") or "?")),
        requested_by=str(value.get("requested_by") or "?"),
        requested_at=str(value.get("requested_at") or "?"),
        scope=_enum(RequestScope, value.get("scope"),
                    RequestScope.SELECTED_ASSETS),
        requested_action=_enum(RequestedAction, value.get("requested_action"),
                               RequestedAction.REVIEW_RETENTION),
        purpose=str(value.get("purpose") or "?"),
        authority_id=str(value.get("authority_id") or "?"),
        authority_version=int(value.get("authority_version") or 1),
        assets=tuple(AssetRef(id=str(a.get("id") or "?"),
                              version=int(a.get("version") or 1))
                     for a in (value.get("assets") or ()) if isinstance(a, dict)),
        copies=tuple(Copy(location=str(c.get("location") or "?"),
                          kind=str(c.get("kind") or "derivative"),
                          resolved_at=str(c.get("resolved_at") or ""))
                     for c in (value.get("copies") or ()) if isinstance(c, dict)),
        holds=tuple(Hold(hold_id=str(h.get("hold_id") or "?"),
                         reason=str(h.get("reason") or "?"),
                         placed_by=str(h.get("placed_by") or "?"),
                         placed_at=str(h.get("placed_at") or "?"),
                         released_by=str(h.get("released_by") or ""),
                         released_at=str(h.get("released_at") or ""))
                    for h in (value.get("holds") or ()) if isinstance(h, dict)),
        tombstones=tuple(Tombstone(asset_id=str(t.get("asset_id") or "?"),
                                   asset_version=int(t.get("asset_version") or 1),
                                   erased_at=str(t.get("erased_at") or "?"),
                                   request_id=str(t.get("request_id") or "?"))
                         for t in (value.get("tombstones") or ())
                         if isinstance(t, dict)),
        state=_enum(RetentionState, value.get("state"),
                    RetentionState.REVIEW_REQUESTED),
        declined_because=str(value.get("declined_because") or ""),
        next_review_at=str(value.get("next_review_at") or ""),
        version=int(value.get("version") or 1))


def rows(matter) -> tuple[RetentionRequest, ...]:
    return tuple(from_dict(r) for r in (getattr(matter, "retention", ()) or ())
                 if isinstance(r, dict))


def put(existing: tuple[RetentionRequest, ...],
        request: RetentionRequest) -> tuple[RetentionRequest, ...]:
    others = tuple(r for r in existing if r.request_id != request.request_id)
    return others + (request,)


def find(existing: tuple[RetentionRequest, ...],
         request_id: str) -> RetentionRequest | None:
    for row in existing:
        if row.request_id == request_id:
            return row
    return None


def place_hold(request: RetentionRequest, hold: Hold) -> RetentionRequest:
    """Add a hold and move the request under it where the lifecycle allows.

    A hold placed on a request already erasing does NOT rewind the erasure --
    `_ALLOWED` permits IN_PROGRESS -> UNDER_HOLD so the remaining work stops,
    and it does not permit anything to leave
    ERASED_FROM_ACTIVE_SYSTEMS backwards. What is already gone is gone, and
    saying otherwise would be the tombstone contradicting itself.
    """
    held = replace(request, holds=request.holds + (hold,),
                   version=request.version + 1)
    if not refuse_transition(held, RetentionState.UNDER_HOLD):
        return advance(held, RetentionState.UNDER_HOLD)
    return held


def release_hold(request: RetentionRequest, hold_id: str, *,
                 by: str, at: str) -> RetentionRequest:
    """Release one hold BY NAME. Releasing does not resume the work.

    The request returns to REVIEW_REQUESTED rather than to whatever it was
    doing, because the reason it was held may have changed what should happen.
    Resuming automatically is how a hold placed for one purpose silently
    authorises the erasure it interrupted.
    """
    if not any(h.hold_id == hold_id for h in request.holds):
        raise ValueError(
            f"no hold {hold_id!r} on request {request.request_id!r}; releasing "
            f"a hold nobody placed would report material as free to erase")
    released = replace(
        request,
        holds=tuple(replace(h, released_by=by, released_at=at)
                    if h.hold_id == hold_id and h.is_active else h
                    for h in request.holds),
        version=request.version + 1)
    if (released.state is RetentionState.UNDER_HOLD
            and not released.active_holds):
        return advance(released, RetentionState.REVIEW_REQUESTED)
    return released


def resolve_copy(request: RetentionRequest, location: str, *,
                 at: str) -> RetentionRequest:
    """Mark one known copy actually dealt with. One location, named.

    There is deliberately no `resolve_all`: the completion count exists to make
    somebody account for each copy, and a bulk resolver would be a single call
    that produces a completion claim over material nobody looked at.
    """
    if not any(c.location == location for c in request.copies):
        raise ValueError(
            f"no copy at {location!r} is inventoried on request "
            f"{request.request_id!r}; resolving an unlisted location would "
            f"raise the resolved count without resolving anything")
    return replace(
        request,
        copies=tuple(replace(c, resolved_at=at) if c.location == location else c
                     for c in request.copies),
        version=request.version + 1)


def erase_from_active_systems(request: RetentionRequest, *,
                              at: str) -> RetentionRequest:
    """Move to ERASED_FROM_ACTIVE_SYSTEMS and write a tombstone per asset.

    THE TOMBSTONES ARE WRITTEN HERE AND NOWHERE ELSE. A tombstone that could be
    written separately from the erasure is a tombstone that can be missing when
    the restore asks, which is the same defect as not having erased at all --
    the material comes back and nothing objects.
    """
    moved = advance(request, RetentionState.ERASED_FROM_ACTIVE_SYSTEMS)
    fresh = tuple(
        Tombstone(asset_id=a.id, asset_version=a.version, erased_at=at,
                  request_id=request.request_id)
        for a in request.assets
        if not any(t.asset_id == a.id for t in request.tombstones))
    return replace(moved, tombstones=moved.tombstones + fresh)


def refuse_restore(requests: tuple[RetentionRequest, ...],
                   proposed: tuple[str, ...]) -> tuple[str, ...]:
    """Every proposed asset that a tombstone forbids bringing back.

    Empty means the restore may proceed. THE POPULATION IS THE WHOLE MATTER'S
    TOMBSTONES, because a backup predates the erasure and the restore has no
    idea which request erased what -- asking one request would answer only for
    the assets that request happened to name.
    """
    forbidden = erased_ids(requests)
    return tuple(asset for asset in proposed if asset in forbidden)


def projection(request: RetentionRequest) -> dict:
    """The served `Retention` object, exactly as `commands.json` declares it.

    `complete_for_declared_scope` can only appear here because the request
    actually reached it, and it can only reach it through `refuse_transition`,
    which counts. There is no path from this function to that word.
    """
    return {
        "request_id": request.request_id,
        "matter_id": request.matter_id,
        "version": request.version,
        "state": request.state.value,
        "retained_reason_codes": [r.value for r in request.retained_reason_codes],
        "expected_asset_count": request.expected_asset_count,
        "resolved_asset_count": request.resolved_asset_count,
        "next_review_at": request.next_review_at,
    }
