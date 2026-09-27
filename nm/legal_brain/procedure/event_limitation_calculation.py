"""Calendar arithmetic over independently reviewed attributed event bindings.

The v1 confirmed-Fact calculation path is unchanged. This v2 path never creates
a confirmed fact, chooses legal inputs, registers a deadline or invokes a model.
"""
from __future__ import annotations

from dataclasses import asdict, replace

from nm.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
)
from nm.legal_brain.procedure import limitation
from nm.legal_brain.procedure.reviewed_limitation_selection import (
    LimitationInputsV2,
    _wire,
    resolve_limitation_inputs,
)
from nm.shared.json_values import same_json_value
from nm.work_the_file.matter_contracts import Side


def compute_event_limitation(*, store, matter, thread, selected, context, args, as_of,
                             source_generation, current_source_version, source_current, version):
    inputs = {"matter_id": matter.id, "matter_version": matter.version, **args}
    receipts = [{"kind": "recorded_file", "matter_id": matter.id,
                 "matter_version": matter.version}]

    def unavailable(reason):
        return ToolEnvelope("compute_limitation", version, ToolKind.COMPUTATION,
            ToolOutcome.FAILED, Availability.UNAVAILABLE, Assessment.NOT_ASSESSED,
            {"inputs": inputs,
             "method": "reviewed event selection + nm.legal_brain.procedure.limitation",
             "input_receipts": receipts}, {}, reason)

    if (not callable(current_source_version) or current_source_version() != source_generation
            or not callable(source_current)):
        return unavailable("The exact current primary-source generation cannot be checked.")
    if type(selected) is not LimitationInputsV2:
        return unavailable("The event selection does not have its declared v2 input owner.")
    # A typed object is not itself a reviewed result. Reconstruct the actual
    # independent dispatch and complete current subject at calculation time.
    current = resolve_limitation_inputs(matter, thread, context,
        source_generation=source_generation, source_current=source_current,
        parent_turn_id=selected.parent_turn_id)
    if current is None or not same_json_value(_wire(asdict(current)), _wire(asdict(selected))):
        return unavailable(
            "The selected events lack their exact current sealed independent review.")
    if selected.premises.unestablished():
        return unavailable("A recorded applicable-law, accrual or jurisdiction premise is unknown.")
    # Use the existing period reader. Its first-match behavior is not an
    # authority to choose among multiple period clauses inside a supplied span.
    try:
        period = limitation.unique_period_in(selected.article.text)
    except ValueError:
        return unavailable("The selected clause cannot satisfy the existing period contract.")
    if period is None:
        return unavailable("The exact selected Article clause has no unambiguous readable period.")
    factors = []
    for row in selected.factors:
        restart = row.observation.on if row.effect == "restart" else None
        if restart is not None and (restart < selected.accrual.on or any(
                other.on is not None and restart < other.on for other in selected.alternatives)):
            return unavailable(
                "One restart operation precedes a proposed trigger; its alternative effect "
                "needs a separate reviewed binding, not copied arithmetic.")
        # The author selects endpoints and a reviewed counting convention, not
        # a day total. This is arithmetic, not a remembered extending provision.
        days = ((row.end.on - row.observation.on).days
                + (1 if row.effect == "exclude_inclusive_days" else 0)) if row.end else 0
        factors.append(limitation.Factor(row.kind, row.observation.source_fact, row.clause.text,
                                        restarts_from=restart, adds_days=days))
    inferred = selected.premises.inferred()
    because = ("The selected date is an attributed EventObservation, not a confirmed dated "
               "finding. This source-based arithmetic is conditional, not an established "
               "legal deadline.")
    if inferred:
        because += " Recorded inferred premises: " + ", ".join(row.value for row in inferred) + "."
    considered = {row.fact.id: row.reason for row in selected.decisions
                  if row.state is limitation.Applied.NO_EFFECT}
    alternatives = []
    try:
        for observation in selected.alternatives:
            expiry = (limitation.expiry_from(observation.on, period, tuple(factors))
                      if observation.on is not None else None)
            alternatives.append({"accrual": observation.source_fact,
                "observation_id": observation.identity,
                "accrual_on": observation.on.isoformat() if observation.on is not None else None,
                "date_expression": observation.date_expression,
                "expires_on": expiry.isoformat() if expiry is not None else None,
                "conditional": True, "assessment": "not_assessed" if expiry is None
                else "conditional_arithmetic"})
        position = limitation.compute(
            for_side=Side.MOVING if thread.posture.side is Side.DEFENDING else thread.posture.side,
            article=selected.article.choice.source.finding.ref,
            accrual=selected.accrual.source_fact, accrual_on=selected.accrual.on,
            accrual_reason=selected.reason, chronology=tuple(row.id for row in selected.chronology),
            period=period, factors=tuple(factors), considered=considered,
            premises=selected.premises.as_rows(), premise_digest=selected.premises.digest(),
            conditional_because=because, alternatives=tuple(alternatives))
    except (ValueError, OverflowError):
        return unavailable("The reviewed event arithmetic exceeds the supported calendar contract.")
    position = replace(position, covered=tuple(limitation.Entry(row.fact.id, row.state, row.reason)
                                               for row in selected.decisions))
    outstanding = tuple(row.fact for row in position.covered
                        if row.applied is limitation.Applied.NOT_ASSESSED)
    reason = because + ((" Unassessed chronology entries: " + ", ".join(outstanding) + ".")
                        if outstanding else "")
    unassessed_events = tuple(row.observation.identity for row in selected.event_decisions
                             if row.state is limitation.Applied.NOT_ASSESSED)
    if unassessed_events:
        reason += " Unassessed source events: " + ", ".join(unassessed_events) + "."
    clauses = (selected.article, *selected.premise_clauses,
               *(row.clause for row in selected.factors),
               *(row.clause for row in selected.decisions if row.clause),
               *(row.clause for row in selected.event_decisions if row.clause))
    receipts.extend([{"kind": "independent_selection_review",
                      "parent_turn_id": selected.parent_turn_id,
                      "turn_id": f"{selected.parent_turn_id}:verify:{selected.package_id}",
                      "package_identity": selected.package_identity},
                     {"kind": "recorded_premises", "premises": selected.premises.as_rows(),
                      "origin": selected.premise_origin,
                      "digest": selected.premises.digest()},
                     {"kind": "captured_primary_clauses", "clauses": [
                         {**row.choice.as_dict(), "start": row.start, "end": row.end,
                          "text": row.text} for row in clauses]},
                     {"kind": "recorded_observations",
                      "selected": selected.accrual.as_dict(),
                      "observations": [row.as_dict() for row in selected.observations]},
                     {"kind": "recorded_facts", "snapshot": selected.snapshot_id,
                      "facts": [asdict(row) for row in selected.chronology]}])
    # Recheck the actual source-current owner after arithmetic, not only its
    # global generation. Withdrawal/current authority can move independently.
    if (store.load(matter.id) != matter or current_source_version() != source_generation
            or any(source_current(row.choice.source.finding, source_generation) is not True
                   for row in clauses)):
        raise ToolRefused("The file or actual legal source moved during event calculation.")
    return ToolEnvelope("compute_limitation", version, ToolKind.COMPUTATION,
        ToolOutcome.RESULTS, Availability.PARTIAL, Assessment.NOT_ASSESSED,
        {"inputs": inputs,
         "method": ("nm.legal_brain.procedure.limitation.unique_period_in"
                    " + compute + days_remaining"),
         "input_receipts": receipts},
        {"position": asdict(position), "accrual_on": selected.accrual.on.isoformat(),
         "accrual_observation_id": selected.accrual.identity,
         "observations": [row.as_dict() for row in selected.observations],
         "event_coverage": [{"observation_id": row.observation.identity,
             "state": row.state.value, "reason": row.reason}
             for row in selected.event_decisions],
         "as_of": as_of.isoformat(), "days_remaining": position.days_remaining(as_of),
         "expired": position.expired(as_of), "arithmetic_verified": True,
         "selection_independently_reviewed": True, "factual_truth_established": False,
         "premise_origin": selected.premise_origin,
         "legal_applicability_established": False, "deadline_registered": False}, reason)
