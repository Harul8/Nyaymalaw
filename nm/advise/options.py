"""Storing and serving a comparison and its decisions. BK-96-AC1, BK-55-AC3. P27.

`nm.advise.options_contracts` and `nm.advise.advice_decision_contracts` hold the state and the
rules; this holds the persistence shape and the served projections, on the
split every packet here keeps.

WHY THE PROJECTION CARRIES `problems`
---------------------------------------
A comparison with an unsupported view, an unexplained loser or a figure
recorded as established with nothing behind it is not shown as a tidy table
with a gap. It is served WITH its problems, because the reader is the person
who would otherwise repeat the number to a client.
"""
from __future__ import annotations

from nm.advise.advice_decision_contracts import AdviceDecision, Disposition, authorises
from nm.advise.options_contracts import Comparison
from nm.shared.text_contracts import clean


def _enum(kind, value, fallback):
    try:
        return kind(value)
    except (ValueError, KeyError):
        return fallback


def comparison_projection(comparison: Comparison) -> dict:
    """What the advocate is served. THE PROBLEMS TRAVEL WITH IT.

    Every figure is rendered through `Figure.render`, so an unknown reads as
    *not established* rather than as an empty cell -- an empty cell in a table
    of numbers reads as zero to the person scanning it.
    """
    return {
        "supported": comparison.supported.value if comparison.supported else None,
        "because": comparison.because,
        "no_view_because": comparison.no_view_because,
        "problems": list(comparison.problems()),
        "options": [{
            "route": o.route.value, "summary": o.summary,
            "objective_fit": o.objective_fit or "not established",
            "useful_recovery": o.useful_recovery.render(),
            "cost": o.cost.render(), "time": o.time.render(),
            "disruption": o.disruption.render(),
            "enforceability": o.enforceability.render(),
            "proportionate": ("not assessed" if o.proportionate is None
                              else bool(o.proportionate)),
            "adverse": list(o.adverse),
            "why_it_loses": o.why_it_loses,
            "unknowns": o.unknown_count(),
        } for o in comparison.options],
    }


def decision_as_dict(decision: AdviceDecision) -> dict:
    return {
        "schema": 1,
        "decision_id": decision.decision_id,
        "disposition": decision.disposition.value,
        "decided_by": decision.decided_by,
        "decided_at": decision.decided_at,
        "advice_version": decision.advice_version,
        "scope": decision.scope,
        "owner": decision.owner,
        "review_trigger": decision.review_trigger,
        "narrowed_to": decision.narrowed_to,
        "because": decision.because,
        "superseded_by": decision.superseded_by,
    }


def decision_from_dict(value: dict) -> AdviceDecision:
    """An unreadable disposition reads as NOT_DECIDED.

    The direction matters here more than anywhere: a corrupt row must not read
    as ACCEPT, because an acceptance nobody gave is the one value that changes
    what the product believes it was told to do.
    """
    return AdviceDecision(
        decision_id=clean(str(value.get("decision_id") or "?")),
        disposition=_enum(Disposition, value.get("disposition"),
                          Disposition.NOT_DECIDED),
        decided_by=str(value.get("decided_by") or ""),
        decided_at=str(value.get("decided_at") or ""),
        advice_version=str(value.get("advice_version") or ""),
        scope=str(value.get("scope") or ""),
        owner=str(value.get("owner") or ""),
        review_trigger=str(value.get("review_trigger") or ""),
        narrowed_to=str(value.get("narrowed_to") or ""),
        because=str(value.get("because") or ""),
        superseded_by=str(value.get("superseded_by") or ""))


def decision_projection(decision: AdviceDecision) -> dict:
    """The served decision, WITH the sentence that says what it does not do.

    `authorises` is called here rather than left to the caller, so that every
    served decision carries the statement that it is not action authority. A
    consumer that had to ask separately is a consumer that will not.
    """
    permitted, why = authorises(decision)
    return {
        "decision_id": decision.decision_id,
        "disposition": decision.disposition.value,
        "decided_by": decision.decided_by,
        "decided_at": decision.decided_at,
        "advice_version": decision.advice_version,
        "scope": decision.scope,
        "owner": decision.owner,
        "review_trigger": decision.review_trigger,
        "narrowed_to": decision.narrowed_to,
        "because": decision.because,
        "current": decision.is_current,
        "superseded_by": decision.superseded_by,
        "absent": list(decision.absent()),
        "authorises_action": permitted,
        "authority_note": why,
    }
