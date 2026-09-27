"""A tool door onto reviewed limitation inputs and the existing arithmetic owner.

The model supplies a dispute ID and comparison date, never an Article, accrual,
period, formula or exception. A trusted application owner must already have
bound those inputs to the current recorded file. Missing bindings are explicit
non-assessments, not a choice of the earliest date or a remembered legal rule.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date

from nm.core import limitation, premise
from nm.core.brain_context import assemble_brief
from nm.core.tool_sources import findings_from_envelope, source_envelopes_from_event
from nm.core.tools import (
    Assessment,
    Availability,
    RegisteredTool,
    ToolContext,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.domain.loop import StepKind
from nm.domain.matter import Fact, Matter, Side, Thread
from nm.domain.text import refuses_blank_text
from nm.ports.evidence import Finding
from nm.ports.model import ToolDefinition
from nm.ports.store import StorePort

VERSION = "reviewed-calculation-wrappers-v1"
_CONTROLS = ("test_compute_limitation_uses_current_fact_and_exact_saved_primary_source",
             "test_missing_or_changed_limitation_inputs_never_produce_a_supported_date")


@refuses_blank_text()
@dataclass(frozen=True)
class CalculationSource:
    """Exact primary source event, not a model-authored locator or text span."""
    turn_id: str
    call_id: str
    event_fingerprint: str
    finding: Finding

    def __post_init__(self):
        if not isinstance(self.finding, Finding):
            raise ValueError("A calculation source needs the captured typed primary finding")


@dataclass(frozen=True)
class ReviewedFactor:
    factor: limitation.Factor
    source: CalculationSource

    def __post_init__(self):
        if (not isinstance(self.factor, limitation.Factor)
                or not isinstance(self.source, CalculationSource)):
            raise ValueError("A factor needs its existing typed owner and exact source receipt")


@refuses_blank_text()
@dataclass(frozen=True)
class LimitationInputs:
    """Trusted, already-reviewed selections; never exposed as model arguments.

    The source and all facts are checked again at dispatch. Confirmed assertions
    retain their actual certainty/basis/provenance; confirmation does not turn
    a client's account into an objectively established factual finding.
    """
    snapshot_id: str
    premises: premise.Premises
    article: CalculationSource | None = None
    accrual: Fact | None = None
    factors: tuple[ReviewedFactor, ...] = ()
    considered: tuple[limitation.Entry, ...] = ()
    alternatives: tuple[Fact, ...] = ()
    prior_position: limitation.Limitation | None = None

    def __post_init__(self):
        if not isinstance(self.premises, premise.Premises):
            raise ValueError("A calculation needs the existing three-premise owner")
        if self.article is not None and not isinstance(self.article, CalculationSource):
            raise ValueError("A selected Article needs an exact captured source contract")
        if self.accrual is not None and not isinstance(self.accrual, Fact):
            raise ValueError("A selected accrual needs the current typed recorded fact")
        if (self.prior_position is not None
                and not isinstance(self.prior_position, limitation.Limitation)):
            raise ValueError("A prior exception needs the existing limitation owner type")
        if self.prior_position is not None and self.prior_position.state not in (
            limitation.LimitationState.NOT_APPLICABLE, limitation.LimitationState.NOT_COMPUTED
        ):
            raise ValueError(
                "A saved computed date must be recomputed, not copied as a tool result")
        for population, kind in ((self.factors, ReviewedFactor),
                                 (self.considered, limitation.Entry), (self.alternatives, Fact)):
            if not isinstance(population, tuple) or any(not isinstance(row, kind)
                                                       for row in population):
                raise ValueError("Calculation inputs need their complete typed owner population")


def calculation_snapshot(matter: Matter, thread: Thread) -> str:
    return assemble_brief(matter, (thread.id,), advocate_id=matter.advocate_id).snapshot_id


def _source_on_file(matter, source, source_version):
    found = []
    for record in matter.loop_records:
        if record.identity.turn_id != source.turn_id:
            continue
        if (record.identity.matter_id != matter.id
                or record.identity.advocate_id != matter.advocate_id):
            return None
        for event in record.events:
            if (event.kind is StepKind.TOOL_RETURNED
                    and event.fingerprint == source.event_fingerprint
                    and event.payload.get("call_id") == source.call_id):
                for envelope in source_envelopes_from_event(event):
                    if (envelope.availability is Availability.UNAVAILABLE
                            or envelope.outcome is not ToolOutcome.RESULTS
                            or envelope.receipt.get("source_version") != source_version):
                        continue
                    rows = envelope.receipt.get("primary_reads", [])
                    primary = tuple(Finding.from_record(raw) for row in rows
                                    for raw in row["findings"])
                    captured = findings_from_envelope(envelope)
                    if source.finding not in primary or source.finding not in captured:
                        continue
                    if source.finding.supports is False or source.finding.source_blocking_reason:
                        return None
                    found.append({"kind": "captured_primary_source", "turn_id": source.turn_id,
                                  "call_id": source.call_id, "event": event.fingerprint,
                                  "source_version": source_version,
                                  "original_reader": envelope.tool,
                                  "finding": source.finding.as_record()})
    return found[0] if len(found) == 1 else None


def _current_fact(fact, current, chronology):
    return (fact is not None and current.get(fact.id) == fact and fact.id in chronology
            and fact.confirmed is True and not fact.conflicts_with and not fact.superseded_by)


def calculation_tools(store: StorePort, *, source_version: str,
                      current_source_version: Callable[[], str] | None = None,
                      resolve: Callable[[Matter, Thread, ToolContext], LimitationInputs | None]
                      | None = None) -> tuple[RegisteredTool, ...]:
    """Attach to the shared registry; its pre/post permission checks still run.

    The resolver does not perform a model call: it reads already-reviewed saved
    input bindings. Without that owner, this tool is available to name what is
    missing, but cannot claim it computed a legal position. Generic calendar
    arithmetic and the unavailable fee rule already belong to tool_catalogue;
    this module neither registers duplicates nor invents an interest rule.
    """
    if not isinstance(source_version, str) or not source_version.strip():
        raise ValueError("A calculation wrapper needs the exact current source generation")

    def file_of(context):
        matter = store.load(context.identity.matter_id)
        if matter is None or matter.advocate_id != context.identity.advocate_id:
            raise ToolRefused("The calculation file is not available to this actor.")
        if matter.version != context.current_version:
            raise ToolRefused("The recorded file moved; reacquire its current calculation inputs.")
        return matter

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
        receipts = [{"kind": "recorded_file", "matter_id": matter.id,
                     "matter_version": matter.version}]

        def unavailable(reason, position=None):
            # Unavailable envelopes carry no purported calculation data. The
            # native missing/exception state remains in its input receipt.
            if position is not None:
                receipts.append({"kind": "existing_position", "position": asdict(position)})
            return ToolEnvelope("compute_limitation", VERSION, ToolKind.COMPUTATION,
                ToolOutcome.FAILED, Availability.UNAVAILABLE, Assessment.NOT_ASSESSED,
                {"inputs": inputs, "method": "nm.core.limitation.compute",
                 "input_receipts": receipts}, {}, reason)

        if thread is None:
            return unavailable("The exact requested dispute is not on this file.")
        if thread.posture.side is Side.UNKNOWN:
            return unavailable("The dispute's recorded side is not established.")
        if resolve is None:
            return unavailable("No reviewed Article/accrual/factor binding owner is configured.")
        selected = resolve(matter, thread, context)
        if selected is None:
            return unavailable("Reviewed limitation input bindings have not been established.")
        if not isinstance(selected, LimitationInputs):
            raise ValueError("The limitation resolver returned an undeclared input contract")
        if calculation_snapshot(matter, thread) != selected.snapshot_id:
            return unavailable("The reviewed calculation inputs belong to a changed file snapshot.")
        if current_source_version is None:
            return unavailable("The current source generation cannot be checked.")
        if current_source_version() != source_version:
            return unavailable(
                "The source generation changed; re-read the calculation's legal inputs.")
        recorded = premise.Premises.from_stored(thread.premises)
        if recorded != selected.premises or selected.premises.unestablished():
            return unavailable(
                "The current recorded applicable law, accrual or jurisdiction is missing.")
        receipts.append({"kind": "recorded_premises", "digest": selected.premises.digest(),
                         "premises": selected.premises.as_rows()})
        if selected.prior_position is not None:
            prior = selected.prior_position
            if prior.premise_digest != selected.premises.digest():
                return unavailable(
                    "The existing exception state belongs to different legal premises.")
            if prior.state is limitation.LimitationState.NOT_COMPUTED:
                return unavailable(prior.why_not_computed, prior)
            if store.load(matter.id) != matter or current_source_version() != source_version:
                raise ToolRefused(
                    "The file or source moved during calculation; reacquire the inputs.")
            return ToolEnvelope("compute_limitation", VERSION, ToolKind.COMPUTATION,
                ToolOutcome.RESULTS, Availability.PARTIAL, Assessment.NOT_ASSESSED,
                {"inputs": inputs, "method": "existing limitation.not_applicable position",
                 "input_receipts": receipts},
                {"position": asdict(prior), "days_remaining": None, "expired": None,
                 "arithmetic_verified": False, "legal_applicability_established": False},
                "The existing owner reports no applicable period; "
                "no new legal assessment was made.")
        if selected.article is None:
            return unavailable("No exact primary-source receipt establishes the selected Article.")
        source_receipt = _source_on_file(matter, selected.article, source_version)
        if source_receipt is None:
            return unavailable(
                "The selected Article is not an available current captured primary read.")
        finding = selected.article.finding
        if finding.governing_date is None:
            return unavailable("The retrieved Article's governing date is not established.")
        law = selected.premises.of(premise.Kind.APPLICABLE_LAW)
        if (law.statement != finding.ref or law.source not in (
                finding.locator, f"{finding.store}:{finding.locator}")):
            return unavailable(
                "The current applicable-law premise does not bind this exact Article.")
        receipts.append(source_receipt)
        current = {fact.id: fact for fact in matter.facts}
        if (not _current_fact(selected.accrual, current, thread.chronology)
                or type(selected.accrual.date) is not date):
            return unavailable("The selected accrual is not an exact current confirmed dated fact.")
        accrual_rule = selected.premises.of(premise.Kind.ACCRUAL_RULE)
        if accrual_rule.source not in (selected.accrual.id, f"fact:{selected.accrual.id}"):
            return unavailable("The recorded accrual premise does not identify this exact fact.")
        if len(set(thread.chronology)) != len(thread.chronology) or any(
                ident not in current for ident in thread.chronology):
            return unavailable(
                "The chronology contains duplicate or missing recorded fact identities.")
        live = tuple(ident for ident in thread.chronology if not current[ident].superseded_by)
        try:
            period = limitation.period_in(finding.span)
        except ValueError:
            return unavailable("The retrieved period cannot satisfy the existing period contract.")
        if period is None:
            return unavailable(
                "The captured Article does not state a period the existing owner can read.")
        factors = []
        for reviewed in selected.factors:
            factor = reviewed.factor
            fact = current.get(factor.fact)
            receipt = _source_on_file(matter, reviewed.source, source_version)
            if (not _current_fact(fact, current, thread.chronology) or receipt is None
                    or factor.finding != reviewed.source.finding.span
                    or factor.kind is limitation.FactorKind.NOT_ASSESSED
                    or type(factor.adds_days) is not int or factor.adds_days < 0
                    or factor.restarts_from is not None and factor.restarts_from != fact.date):
                return unavailable(
                    "A clock-moving factor lacks its current fact and exact legal read.")
            if factor in factors:
                return unavailable("The same clock-moving factor was supplied more than once.")
            factors.append(factor)
            receipts.append(receipt)
        considered = {}
        for entry in selected.considered:
            if (entry.fact not in live or entry.applied is not limitation.Applied.NO_EFFECT
                    or entry.fact in considered or any(row.fact == entry.fact for row in factors)):
                return unavailable(
                    "A considered entry lacks a unique noncontradictory reviewed no-effect state.")
            considered[entry.fact] = entry.reason
        conditional = selected.premises.inferred()
        because = (("The recorded " + ", ".join(kind.value for kind in conditional)
                    + " premise is inferred; this is not an established legal deadline.")
                   if conditional else "")
        alternatives = []
        for fact in selected.alternatives:
            if (not _current_fact(fact, current, thread.chronology)
                    or type(fact.date) is not date):
                return unavailable(
                    "A competing accrual has no exact current confirmed calendar date.")
            try:
                alternate_on = limitation.expiry_from(fact.date, period, tuple(factors))
            except (ValueError, OverflowError):
                return unavailable("The alternative expiry exceeds the supported calendar range.")
            alternatives.append({"accrual": fact.id, "accrual_on": fact.date.isoformat(),
                                 "expires_on": alternate_on.isoformat()})
        try:
            position = limitation.compute(
                for_side=(Side.MOVING if thread.posture.side is Side.DEFENDING
                          else thread.posture.side),
                article=finding.ref, accrual=selected.accrual.id, accrual_on=selected.accrual.date,
                accrual_reason=selected.accrual.statement, chronology=live, period=period,
                factors=tuple(factors), considered=considered,
                premises=selected.premises.as_rows(), premise_digest=selected.premises.digest(),
                conditional_because=because, alternatives=tuple(alternatives))
        except (ValueError, OverflowError):
            return unavailable(
                "The expiry exceeds the existing supported calendar/period contract.")
        facts = tuple(current[ident] for ident in live)
        receipts.append({"kind": "recorded_facts", "facts": [asdict(fact) for fact in facts],
                         "snapshot": selected.snapshot_id})
        if store.load(matter.id) != matter or current_source_version() != source_version:
            raise ToolRefused("The file or source moved during calculation; reacquire the inputs.")
        reason = (because if conditional else "")
        outstanding = tuple(row.fact for row in position.covered
                            if row.applied is limitation.Applied.NOT_ASSESSED)
        if outstanding:
            reason = (reason + " " if reason else "") + (
                "These chronology entries have not been examined against the clock: "
                + ", ".join(outstanding))
        return ToolEnvelope("compute_limitation", VERSION, ToolKind.COMPUTATION,
            ToolOutcome.RESULTS, Availability.PARTIAL if reason else Availability.AVAILABLE,
            Assessment.NOT_ASSESSED if reason else Assessment.SUPPORTED,
            {"inputs": inputs, "method": "nm.core.limitation.period_in + compute + days_remaining",
             "input_receipts": receipts},
            {"position": asdict(position), "accrual_on": selected.accrual.date.isoformat(),
             "as_of": as_of.isoformat(), "days_remaining": position.days_remaining(as_of),
             "expired": position.expired(as_of), "arithmetic_verified": True,
             "legal_applicability_established": False}, reason)

    def interest(_args, context):
        matter = file_of(context)
        return ToolEnvelope("compute_interest", VERSION, ToolKind.COMPUTATION,
            ToolOutcome.FAILED, Availability.UNAVAILABLE, Assessment.NOT_ASSESSED,
            {"inputs": {}, "method": "No reviewed interest-rule/calculation owner is configured",
             "input_receipts": [{"kind": "recorded_file", "matter_id": matter.id,
                                  "matter_version": matter.version}]}, {},
            "No reviewed contractual/statutory interest rule and calculation owner is configured. "
            "No rate, principal, compounding convention or payment allocation is assumed.")

    return (RegisteredTool(
        ToolDefinition("compute_limitation",
                       "Compute the claimant's clock only from already-reviewed "
                       "current file/source inputs. Never choose an Article or accrual from model "
                       "memory; unknown, conditional and unexamined entries stay visible.",
                       object_schema({"thread_id": {"type": "string", "minLength": 1},
                                      "as_of": {"type": "string", "minLength": 1}})),
        ToolKind.COMPUTATION, VERSION, True, _CONTROLS, compute),
        RegisteredTool(ToolDefinition("compute_interest",
                       "Report the unavailable reviewed interest rule; never estimate interest.",
                       object_schema({})), ToolKind.COMPUTATION, VERSION, True,
                       ("test_interest_absence_never_becomes_estimated_arithmetic",), interest))
