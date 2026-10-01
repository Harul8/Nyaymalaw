"""The compute_limitation model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.Archives.legal_brain.procedure import limitation
from nm.Archives.legal_brain.procedure.calculation_tools import (
    _CONTROLS,
    LimitationInputs,
    _current_fact,
    _source_on_file,
    calculation_snapshot,
)
from nm.Archives.legal_brain.reason import premise
from nm.shared.model_port import ToolDefinition
from nm.work_the_file.matter_contracts import Side


def build_tool(
    *,
    file_of,
    store,
    tool_version,
    resolve,
    source_version,
    current_source_version,
    source_current,
    event_selections,
) -> RegisteredTool:
    def compute(args, context):
        matter = file_of(context)
        thread = next((row for row in matter.threads if row.id == args["thread_id"]), None)
        try:
            as_of = date.fromisoformat(args["as_of"])
        except ValueError as exc:
            raise ToolRefused("The comparison date must be an ISO calendar date.") from exc
        if as_of.isoformat() != args["as_of"]:
            raise ToolRefused("The comparison date must be a canonical ISO calendar date.")
        inputs = {"matter_id": matter.id, "matter_version": matter.version, **args}
        receipts = [
            {"kind": "recorded_file", "matter_id": matter.id, "matter_version": matter.version}
        ]

        def unavailable(reason, position=None):
            # Unavailable envelopes carry no purported calculation data. The
            # native missing/exception state remains in its input receipt.
            if position is not None:
                receipts.append({"kind": "existing_position", "position": asdict(position)})
            return ToolEnvelope(
                "compute_limitation",
                tool_version,
                ToolKind.COMPUTATION,
                ToolOutcome.FAILED,
                Availability.UNAVAILABLE,
                Assessment.NOT_ASSESSED,
                {
                    "inputs": inputs,
                    "method": "nm.Archives.legal_brain.procedure.limitation.compute",
                    "input_receipts": receipts,
                },
                {},
                reason,
            )

        if thread is None:
            return unavailable("The exact requested dispute is not on this file.")
        if thread.posture.side is Side.UNKNOWN:
            return unavailable("The dispute's recorded side is not established.")
        if resolve is None:
            return unavailable("No reviewed Article/accrual/factor binding owner is configured.")
        selected = resolve(matter, thread, context)
        if selected is None:
            return unavailable("Reviewed limitation input bindings have not been established.")
        if event_selections:
            from nm.Archives.legal_brain.procedure.event_limitation_calculation import (
                compute_event_limitation,
            )
            from nm.Archives.legal_brain.procedure.reviewed_limitation_selection import LimitationInputsV2

            if isinstance(selected, LimitationInputsV2):
                return compute_event_limitation(
                    store=store,
                    matter=matter,
                    thread=thread,
                    selected=selected,
                    context=context,
                    args=args,
                    as_of=as_of,
                    source_generation=source_version,
                    current_source_version=current_source_version,
                    source_current=source_current,
                    version=tool_version,
                )
        if not isinstance(selected, LimitationInputs):
            raise ValueError("The limitation resolver returned an undeclared input contract")
        if calculation_snapshot(matter, thread) != selected.snapshot_id:
            return unavailable("The reviewed calculation inputs belong to a changed file snapshot.")
        if current_source_version is None:
            return unavailable("The current source generation cannot be checked.")
        if current_source_version() != source_version:
            return unavailable(
                "The source generation changed; re-read the calculation's legal inputs."
            )
        recorded = premise.Premises.from_stored(thread.premises)
        if recorded != selected.premises or selected.premises.unestablished():
            return unavailable(
                "The current recorded applicable law, accrual or jurisdiction is missing."
            )
        receipts.append(
            {
                "kind": "recorded_premises",
                "digest": selected.premises.digest(),
                "premises": selected.premises.as_rows(),
            }
        )
        if selected.prior_position is not None:
            prior = selected.prior_position
            if prior.premise_digest != selected.premises.digest():
                return unavailable(
                    "The existing exception state belongs to different legal premises."
                )
            if prior.state is limitation.LimitationState.NOT_COMPUTED:
                return unavailable(prior.why_not_computed, prior)
            if store.load(matter.id) != matter or current_source_version() != source_version:
                raise ToolRefused(
                    "The file or source moved during calculation; reacquire the inputs."
                )
            return ToolEnvelope(
                "compute_limitation",
                tool_version,
                ToolKind.COMPUTATION,
                ToolOutcome.RESULTS,
                Availability.PARTIAL,
                Assessment.NOT_ASSESSED,
                {
                    "inputs": inputs,
                    "method": "existing limitation.not_applicable position",
                    "input_receipts": receipts,
                },
                {
                    "position": asdict(prior),
                    "days_remaining": None,
                    "expired": None,
                    "arithmetic_verified": False,
                    "legal_applicability_established": False,
                },
                "The existing owner reports no applicable period; "
                "no new legal assessment was made.",
            )
        if selected.article is None:
            return unavailable("No exact primary-source receipt establishes the selected Article.")
        source_receipt = _source_on_file(matter, selected.article, source_version)
        if source_receipt is None:
            return unavailable(
                "The selected Article is not an available current captured primary read."
            )
        finding = selected.article.finding
        if finding.governing_date is None:
            return unavailable("The retrieved Article's governing date is not established.")
        law = selected.premises.of(premise.Kind.APPLICABLE_LAW)
        if law.statement != finding.ref or law.source not in (
            finding.locator,
            f"{finding.store}:{finding.locator}",
        ):
            return unavailable(
                "The current applicable-law premise does not bind this exact Article."
            )
        receipts.append(source_receipt)
        current = {fact.id: fact for fact in matter.facts}
        if (
            not _current_fact(selected.accrual, current, thread.chronology)
            or type(selected.accrual.date) is not date
        ):
            return unavailable("The selected accrual is not an exact current confirmed dated fact.")
        accrual_rule = selected.premises.of(premise.Kind.ACCRUAL_RULE)
        if accrual_rule.source not in (selected.accrual.id, f"fact:{selected.accrual.id}"):
            return unavailable("The recorded accrual premise does not identify this exact fact.")
        if len(set(thread.chronology)) != len(thread.chronology) or any(
            ident not in current for ident in thread.chronology
        ):
            return unavailable(
                "The chronology contains duplicate or missing recorded fact identities."
            )
        live = tuple(ident for ident in thread.chronology if not current[ident].superseded_by)
        try:
            period = limitation.period_in(finding.span)
        except ValueError:
            return unavailable("The retrieved period cannot satisfy the existing period contract.")
        if period is None:
            return unavailable(
                "The captured Article does not state a period the existing owner can read."
            )
        factors = []
        for reviewed in selected.factors:
            factor = reviewed.factor
            fact = current.get(factor.fact)
            receipt = _source_on_file(matter, reviewed.source, source_version)
            if (
                not _current_fact(fact, current, thread.chronology)
                or receipt is None
                or factor.finding != reviewed.source.finding.span
                or factor.kind is limitation.FactorKind.NOT_ASSESSED
                or type(factor.adds_days) is not int
                or factor.adds_days < 0
                or factor.restarts_from is not None
                and factor.restarts_from != fact.date
            ):
                return unavailable(
                    "A clock-moving factor lacks its current fact and exact legal read."
                )
            if factor in factors:
                return unavailable("The same clock-moving factor was supplied more than once.")
            factors.append(factor)
            receipts.append(receipt)
        considered = {}
        for entry in selected.considered:
            if (
                entry.fact not in live
                or entry.applied is not limitation.Applied.NO_EFFECT
                or entry.fact in considered
                or any(row.fact == entry.fact for row in factors)
            ):
                return unavailable(
                    "A considered entry lacks a unique noncontradictory reviewed no-effect state."
                )
            considered[entry.fact] = entry.reason
        conditional = selected.premises.inferred()
        because = (
            (
                "The recorded "
                + ", ".join(kind.value for kind in conditional)
                + " premise is inferred; this is not an established legal deadline."
            )
            if conditional
            else ""
        )
        alternatives = []
        for fact in selected.alternatives:
            if not _current_fact(fact, current, thread.chronology) or type(fact.date) is not date:
                return unavailable(
                    "A competing accrual has no exact current confirmed calendar date."
                )
            try:
                alternate_on = limitation.expiry_from(fact.date, period, tuple(factors))
            except (ValueError, OverflowError):
                return unavailable("The alternative expiry exceeds the supported calendar range.")
            alternatives.append(
                {
                    "accrual": fact.id,
                    "accrual_on": fact.date.isoformat(),
                    "expires_on": alternate_on.isoformat(),
                }
            )
        try:
            position = limitation.compute(
                for_side=(
                    Side.MOVING if thread.posture.side is Side.DEFENDING else thread.posture.side
                ),
                article=finding.ref,
                accrual=selected.accrual.id,
                accrual_on=selected.accrual.date,
                accrual_reason=selected.accrual.statement,
                chronology=live,
                period=period,
                factors=tuple(factors),
                considered=considered,
                premises=selected.premises.as_rows(),
                premise_digest=selected.premises.digest(),
                conditional_because=because,
                alternatives=tuple(alternatives),
            )
        except (ValueError, OverflowError):
            return unavailable(
                "The expiry exceeds the existing supported calendar/period contract."
            )
        facts = tuple(current[ident] for ident in live)
        receipts.append(
            {
                "kind": "recorded_facts",
                "facts": [asdict(fact) for fact in facts],
                "snapshot": selected.snapshot_id,
            }
        )
        if store.load(matter.id) != matter or current_source_version() != source_version:
            raise ToolRefused("The file or source moved during calculation; reacquire the inputs.")
        reason = because if conditional else ""
        outstanding = tuple(
            row.fact for row in position.covered if row.applied is limitation.Applied.NOT_ASSESSED
        )
        if outstanding:
            reason = (reason + " " if reason else "") + (
                "These chronology entries have not been examined against the clock: "
                + ", ".join(outstanding)
            )
        return ToolEnvelope(
            "compute_limitation",
            tool_version,
            ToolKind.COMPUTATION,
            ToolOutcome.RESULTS,
            Availability.PARTIAL if reason else Availability.AVAILABLE,
            Assessment.NOT_ASSESSED if reason else Assessment.SUPPORTED,
            {
                "inputs": inputs,
                "method": ("nm.Archives.legal_brain.procedure.limitation.period_in"
                           " + compute + days_remaining"),
                "input_receipts": receipts,
            },
            {
                "position": asdict(position),
                "accrual_on": selected.accrual.date.isoformat(),
                "as_of": as_of.isoformat(),
                "days_remaining": position.days_remaining(as_of),
                "expired": position.expired(as_of),
                "arithmetic_verified": True,
                "legal_applicability_established": False,
            },
            reason,
        )

    return RegisteredTool(
        ToolDefinition(
            "compute_limitation",
            "Compute the claimant's clock only from already-reviewed "
            "current file/source inputs. Never choose an Article or accrual from model "
            "memory; unknown, conditional and unexamined entries stay visible.",
            object_schema(
                {
                    "thread_id": {"type": "string", "minLength": 1},
                    "as_of": {"type": "string", "minLength": 1},
                }
            ),
        ),
        ToolKind.COMPUTATION,
        tool_version,
        True,
        _CONTROLS
        + (
            ("test_reviewed_event_calculation_never_confirms_or_registers_its_date",)
            if event_selections
            else ()
        ),
        compute,
    )
