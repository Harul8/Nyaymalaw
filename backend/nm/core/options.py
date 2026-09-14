"""Storing and serving a comparison and its decisions. BK-96-AC1, BK-55-AC3. P27.

`nm.domain.options` and `nm.domain.advice_decision` hold the state and the
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

from nm.domain.advice_decision import AdviceDecision, Disposition, authorises
from nm.domain.options import Certainty, Comparison, Figure, Option, Route
from nm.domain.text import clean


def _enum(kind, value, fallback):
    try:
        return kind(value)
    except (ValueError, KeyError):
        return fallback


def figure_as_dict(figure: Figure) -> dict:
    return {"text": figure.text, "certainty": figure.certainty.value,
            "basis": figure.basis}


def figure_from_dict(value: dict) -> Figure:
    """An unreadable certainty reads as UNKNOWN.

    NOT as established: a corrupt row must fall to the value that claims
    least, or a damaged record starts asserting measured figures.
    """
    return Figure(text=str(value.get("text") or ""),
                  certainty=_enum(Certainty, value.get("certainty"),
                                  Certainty.UNKNOWN),
                  basis=str(value.get("basis") or ""))


def option_as_dict(option: Option) -> dict:
    return {
        "route": option.route.value, "summary": option.summary,
        "objective_fit": option.objective_fit,
        "useful_recovery": figure_as_dict(option.useful_recovery),
        "cost": figure_as_dict(option.cost),
        "time": figure_as_dict(option.time),
        "disruption": figure_as_dict(option.disruption),
        "enforceability": figure_as_dict(option.enforceability),
        "proportionate": option.proportionate,
        "adverse": list(option.adverse),
        "why_it_loses": option.why_it_loses,
    }


def option_from_dict(value: dict) -> Option:
    blank_figure = {"text": "", "certainty": "unknown", "basis": ""}
    return Option(
        route=_enum(Route, value.get("route"), Route.NOT_ASSESSED),
        summary=str(value.get("summary") or "?"),
        objective_fit=str(value.get("objective_fit") or ""),
        useful_recovery=figure_from_dict(value.get("useful_recovery") or blank_figure),
        cost=figure_from_dict(value.get("cost") or blank_figure),
        time=figure_from_dict(value.get("time") or blank_figure),
        disruption=figure_from_dict(value.get("disruption") or blank_figure),
        enforceability=figure_from_dict(value.get("enforceability") or blank_figure),
        proportionate=value.get("proportionate"),
        adverse=tuple(str(a) for a in (value.get("adverse") or ())),
        why_it_loses=str(value.get("why_it_loses") or ""))


def comparison_as_dict(comparison: Comparison) -> dict:
    return {
        "schema": 1,
        "options": [option_as_dict(o) for o in comparison.options],
        "supported": (comparison.supported.value
                      if comparison.supported else None),
        "because": comparison.because,
        "no_view_because": comparison.no_view_because,
    }


def comparison_from_dict(value: dict) -> Comparison:
    supported = value.get("supported")
    return Comparison(
        options=tuple(option_from_dict(o) for o in (value.get("options") or ())
                      if isinstance(o, dict)),
        supported=(_enum(Route, supported, Route.NOT_ASSESSED)
                   if supported else None),
        because=str(value.get("because") or ""),
        no_view_because=str(value.get("no_view_because") or ""))


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


def decision_rows(matter) -> tuple[AdviceDecision, ...]:
    return tuple(decision_from_dict(d)
                 for d in (getattr(matter, "advice_decisions", ()) or ())
                 if isinstance(d, dict))


def put_decision(existing: tuple[AdviceDecision, ...],
                 decision: AdviceDecision) -> tuple[AdviceDecision, ...]:
    others = tuple(d for d in existing if d.decision_id != decision.decision_id)
    return others + (decision,)


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
