"""A tool door onto reviewed limitation inputs and the existing arithmetic owner.

The model supplies a dispute ID and comparison date, never an Article, accrual,
period, formula or exception. A trusted application owner must already have
bound those inputs to the current recorded file. Missing bindings are explicit
non-assessments, not a choice of the earliest date or a remembered legal rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nm.legal_brain import limitation, premise
from nm.legal_brain.brain_context import assemble_brief
from nm.legal_brain.evidence_port import Finding
from nm.legal_brain.loop_contracts import StepKind
from nm.legal_brain.tool_sources import findings_from_envelope, source_envelopes_from_event
from nm.legal_brain.tools import (
    Availability,
    RegisteredTool,
    ToolContext,
    ToolOutcome,
    ToolRefused,
)
from nm.shared.store_port import StorePort
from nm.shared.text_contracts import refuses_blank_text
from nm.work_the_file.matter_contracts import Fact, Matter, Thread

if TYPE_CHECKING:
    from nm.legal_brain.reviewed_limitation_selection import LimitationInputsV2

VERSION = "reviewed-calculation-wrappers-v1"
EVENT_VERSION = "reviewed-event-calculation-wrappers-v2"
_CONTROLS = (
    "test_compute_limitation_uses_current_fact_and_exact_saved_primary_source",
    "test_missing_or_changed_limitation_inputs_never_produce_a_supported_date",
)


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
        if not isinstance(self.factor, limitation.Factor) or not isinstance(
            self.source, CalculationSource
        ):
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
        if self.prior_position is not None and not isinstance(
            self.prior_position, limitation.Limitation
        ):
            raise ValueError("A prior exception needs the existing limitation owner type")
        if self.prior_position is not None and self.prior_position.state not in (
            limitation.LimitationState.NOT_APPLICABLE,
            limitation.LimitationState.NOT_COMPUTED,
        ):
            raise ValueError(
                "A saved computed date must be recomputed, not copied as a tool result"
            )
        for population, kind in (
            (self.factors, ReviewedFactor),
            (self.considered, limitation.Entry),
            (self.alternatives, Fact),
        ):
            if not isinstance(population, tuple) or any(
                not isinstance(row, kind) for row in population
            ):
                raise ValueError("Calculation inputs need their complete typed owner population")


def calculation_snapshot(matter: Matter, thread: Thread) -> str:
    return assemble_brief(matter, (thread.id,), advocate_id=matter.advocate_id).snapshot_id


def _source_on_file(matter, source, source_version):
    found = []
    for record in matter.loop_records:
        if record.identity.turn_id != source.turn_id:
            continue
        if (
            record.identity.matter_id != matter.id
            or record.identity.advocate_id != matter.advocate_id
        ):
            return None
        for event in record.events:
            if (
                event.kind is StepKind.TOOL_RETURNED
                and event.fingerprint == source.event_fingerprint
                and event.payload.get("call_id") == source.call_id
            ):
                for envelope in source_envelopes_from_event(event):
                    if (
                        envelope.availability is Availability.UNAVAILABLE
                        or envelope.outcome is not ToolOutcome.RESULTS
                        or envelope.receipt.get("source_version") != source_version
                    ):
                        continue
                    rows = envelope.receipt.get("primary_reads", [])
                    primary = tuple(
                        Finding.from_record(raw) for row in rows for raw in row["findings"]
                    )
                    captured = findings_from_envelope(envelope)
                    if source.finding not in primary or source.finding not in captured:
                        continue
                    if source.finding.supports is False or source.finding.source_blocking_reason:
                        return None
                    found.append(
                        {
                            "kind": "captured_primary_source",
                            "turn_id": source.turn_id,
                            "call_id": source.call_id,
                            "event": event.fingerprint,
                            "source_version": source_version,
                            "original_reader": envelope.tool,
                            "finding": source.finding.as_record(),
                        }
                    )
    return found[0] if len(found) == 1 else None


def _current_fact(fact, current, chronology):
    return (
        fact is not None
        and current.get(fact.id) == fact
        and fact.id in chronology
        and fact.confirmed is True
        and not fact.conflicts_with
        and not fact.superseded_by
    )


def calculation_tools(
    store: StorePort,
    *,
    source_version: str,
    current_source_version: Callable[[], str] | None = None,
    resolve: Callable[[Matter, Thread, ToolContext], LimitationInputs | LimitationInputsV2 | None]
    | None = None,
    source_current: Callable[[Finding, str], bool] | None = None,
    event_selections: bool = False,
) -> tuple[RegisteredTool, ...]:
    """Attach to the shared registry; its pre/post permission checks still run.

    The resolver does not perform a model call: it reads already-reviewed saved
    input bindings. Without that owner, this tool is available to name what is
    missing, but cannot claim it computed a legal position. Generic calendar
    arithmetic and the unavailable fee rule already belong to tool_catalogue;
    this module neither registers duplicates nor invents an interest rule.
    """
    if not isinstance(source_version, str) or not source_version.strip():
        raise ValueError("A calculation wrapper needs the exact current source generation")
    if type(event_selections) is not bool:
        raise ValueError("The reviewed event calculation contract is explicitly enabled")
    tool_version = EVENT_VERSION if event_selections else VERSION

    def file_of(context):
        matter = store.load(context.identity.matter_id)
        if matter is None or matter.advocate_id != context.identity.advocate_id:
            raise ToolRefused("The calculation file is not available to this actor.")
        if matter.version != context.current_version:
            raise ToolRefused("The recorded file moved; reacquire its current calculation inputs.")
        return matter

    from nm.legal_brain.tool_compute_interest import (
        build_unavailable_tool as compute_interest_unavailable_tool,
    )
    from nm.legal_brain.tool_compute_limitation import build_tool as compute_limitation_tool

    return (
        compute_limitation_tool(
            file_of=file_of,
            store=store,
            tool_version=tool_version,
            resolve=resolve,
            source_version=source_version,
            current_source_version=current_source_version,
            source_current=source_current,
            event_selections=event_selections,
        ),
        compute_interest_unavailable_tool(file_of=file_of, tool_version=tool_version),
    )
