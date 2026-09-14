"""Persisting consequential-action proposals. BK-56-AC4. P30.

`nm.domain.action` holds the states and the rules; this holds the persistence
shape and the served projection, on the split every packet here keeps.

THE PROJECTION ALWAYS CARRIES THE REFUSAL
-------------------------------------------
`refuse_dispatch` is called here rather than left to each caller, so every
served proposal arrives with the sentence saying nothing sent it and nothing
can. A consumer that had to ask separately is a consumer that will not.
"""
from __future__ import annotations

from nm.domain.action import (
    ActionProposal,
    ActionState,
    audit_row,
    refuse_dispatch,
)
from nm.domain.text import clean


def as_dict(a: ActionProposal) -> dict:
    return {
        "schema": 1, "proposal_id": a.proposal_id, "matter_id": a.matter_id,
        "package_id": a.package_id, "actor": a.actor,
        "authority": a.authority, "object": a.object,
        "destination": a.destination, "content_digest": a.content_digest,
        "state": a.state.value, "confirmed_by": a.confirmed_by,
        "confirmed_at": a.confirmed_at, "receipt": a.receipt,
        "outcome_because": a.outcome_because,
        "attempts": [dict(x) for x in a.attempts], "version": a.version}


def from_dict(value: dict) -> ActionProposal:
    """An unreadable state falls to DELIVERY_UNKNOWN.

    NOT to DELIVERED and not to PREPARED. A corrupt row must not claim the
    filing arrived, and must not claim nothing was ever sent -- both are
    assertions nobody can support, and the honest answer is that the outcome
    is not known.
    """
    try:
        state = ActionState(value.get("state"))
    except ValueError:
        state = ActionState.DELIVERY_UNKNOWN
    return ActionProposal(
        proposal_id=clean(str(value.get("proposal_id") or "?")),
        matter_id=clean(str(value.get("matter_id") or "?")),
        package_id=str(value.get("package_id") or "?"),
        actor=str(value.get("actor") or ""),
        authority=str(value.get("authority") or ""),
        object=str(value.get("object") or ""),
        destination=str(value.get("destination") or ""),
        content_digest=str(value.get("content_digest") or ""),
        state=state, confirmed_by=str(value.get("confirmed_by") or ""),
        confirmed_at=str(value.get("confirmed_at") or ""),
        receipt=str(value.get("receipt") or ""),
        outcome_because=str(value.get("outcome_because") or ""),
        attempts=tuple(dict(x) for x in (value.get("attempts") or ())
                       if isinstance(x, dict)),
        version=int(value.get("version") or 1))


def rows(matter) -> tuple[ActionProposal, ...]:
    return tuple(from_dict(r)
                 for r in (getattr(matter, "action_proposals", ()) or ())
                 if isinstance(r, dict))


def put(existing: tuple[ActionProposal, ...],
        a: ActionProposal) -> tuple[ActionProposal, ...]:
    return tuple(x for x in existing if x.proposal_id != a.proposal_id) + (a,)


def projection(a: ActionProposal) -> dict:
    """The served proposal. The audit row carries no protected content."""
    return {
        **audit_row(a),
        "object": a.object,
        "absent": list(a.absent()),
        "settled": a.state.is_settled,
        "claims_arrival": a.state.claims_arrival,
        "outcome_because": a.outcome_because,
        "dispatch_note": refuse_dispatch(a),
    }
