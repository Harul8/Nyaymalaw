"""Current exact source-owned fee inputs, independently checked before math.

The whole scoped source/case population and original authenticated request go
to the existing independent reviewer. No installed table or model approval flag
can supply a tariff, legally operative schedule or valuation/jurisdiction rule.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from nm.Archives.legal_brain.orchestrate.loop import _budget_from
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopOutcome, StepKind, StopReason, digest
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.Archives.legal_brain.procedure.fee_calculation_contracts import (
    FeeBand,
    FeeInputs,
    FeeNotAssessed,
    FeeObservation,
    fee_literal,
)
from nm.Archives.legal_brain.procedure.reviewed_interest_selection import InterestSelectionOwner
from nm.Archives.legal_brain.procedure.reviewed_limitation_selection import _describe
from nm.Archives.legal_brain.reason.matter_support import MatterDocumentSpan, captured_documents
from nm.Archives.legal_brain.reason.working_record import WorkingRecordOwner
from nm.Archives.legal_brain.reason.working_record_contracts import ReferenceKind
from nm.Archives.legal_brain.retrieve.evidence_port import SourceKind
from nm.Archives.legal_brain.verify.brain_assessment import saved_package_reviews
from nm.Archives.legal_brain.verify.brain_finalization import neutral
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.Archives.legal_brain.verify.verifier import EvidencePackage, EvidenceSpan
from nm.shared.model_port import SchemaViolation, require_schema
from nm.work_the_file.event_observation_contracts import EventObservation

VERSION = "source-owned-conditional-fee-selection-v1"
READ, PROPOSE, COMPUTE = "read_fee_inventory", "propose_fee_selection", "court_fee"
_TEXT = {"type": "string", "minLength": 1}
_CLAUSE = object_schema(
    {
        "reference_id": _TEXT,
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1},
    }
)
_NULL_CLAUSE = {**_CLAUSE, "type": ["object", "null"]}
_BASIS = object_schema({"literal": _CLAUSE, "currency": _NULL_CLAUSE})
_LIMIT = object_schema({"mode": _CLAUSE, "amount": _NULL_CLAUSE})
FEE_SELECTION_SCHEMA = object_schema(
    {
        "id": {"type": "string", "minLength": 1},
        "thread_id": _TEXT,
        "inventory_identity": _TEXT,
        "as_of_event_id": _TEXT,
        "schedule": _CLAUSE,
        "schedule_version": _CLAUSE,
        "currency": _CLAUSE,
        "mode": _CLAUSE,
        "basis": {**_BASIS, "type": ["object", "null"]},
        "charge": _NULL_CLAUSE,
        "bands": {
            "type": "array",
            "maxItems": 100,
            "items": object_schema({"lower": _CLAUSE, "upper": _CLAUSE, "charge": _CLAUSE}),
        },
        "boundaries": _NULL_CLAUSE,
        "unit_size": _NULL_CLAUSE,
        "unit_rounding": _NULL_CLAUSE,
        "minimum": _LIMIT,
        "maximum": _LIMIT,
        "rounding_digits": _CLAUSE,
        "rounding_mode": _CLAUSE,
        "rounding_stage": _CLAUSE,
        "coverage": {
            "type": "array",
            "maxItems": 1000,
            "items": object_schema(
                {
                    "reference_id": _TEXT,
                    "state": {"type": "string", "enum": ["selected", "excluded", "not_assessed"]},
                    "reason": _TEXT,
                }
            ),
        },
        "reason": _TEXT,
    }
)


@dataclass(frozen=True)
class FeeBinding:
    candidate: dict
    inventory: dict
    inputs: FeeInputs
    package: EvidencePackage


@dataclass(frozen=True)
class FeeSelectionReview:
    bindings: tuple[FeeBinding, ...]
    review: object | None

    @property
    def unresolved(self):
        released = self.review.result.released if self.review is not None else ()
        return tuple(row for row in self.bindings if row.package not in released)


class FeeSelectionOwner:
    def __init__(self, *, source_owner: WorkingRecordOwner):
        if not isinstance(source_owner, WorkingRecordOwner):
            raise ValueError("Fees require the actual typed complete working-source owner")
        self.source_owner = source_owner
        # Shared owner, not a second chronology/source inventory implementation.
        self._inventory_owner = InterestSelectionOwner(source_owner=source_owner)

    def inventory(self, record, matter, thread_id):
        value = self._inventory_owner.inventory(record, matter, thread_id)
        value.pop("identity")
        value["calculation_kind"] = "conditional_fee"
        value["legal_schedule_verified"] = False
        value["identity"] = digest(value)
        return value

    def bind(self, record, matter, candidate):
        require_schema(candidate, FEE_SELECTION_SCHEMA)

        def bounded(value):
            if type(value) is str:
                return bool(value.strip()) and len(value) <= 16000
            if type(value) is dict:
                return all(bounded(row) for row in value.values())
            if type(value) is list:
                return all(bounded(row) for row in value)
            return True

        if len(candidate["id"]) > 100 or not bounded(candidate):
            raise ReviewRefused("Fee selections retain bounded nonblank identity and source words")
        inventory = self.inventory(record, matter, candidate["thread_id"])
        if candidate["inventory_identity"] != inventory["identity"]:
            raise ReviewRefused("Fee selections belong to a changed exact complete inventory")
        references = {row["reference"]["id"]: row for row in inventory["references"]}
        coverage = candidate["coverage"]
        if len(coverage) != len(references) or {row["reference_id"] for row in coverage} != set(
            references
        ):
            raise ReviewRefused("Fee review covers every actual current source/fact/document")
        if len({row["reference_id"] for row in coverage}) != len(coverage):
            raise ReviewRefused("Duplicate coverage cannot hide competing schedules or values")
        if any(not row["reason"].strip() for row in coverage) or not candidate["reason"].strip():
            raise ReviewRefused("Excluded/competing inputs retain an explicit nonblank reason")
        findings, _windows = self.source_owner._sources(record)
        documents = {
            "document:" + digest(neutral(asdict(row))): row for row in captured_documents(record)
        }
        selected = set()

        def clause(raw):
            row = references.get(raw["reference_id"])
            start, end = raw["start"], raw["end"]
            if (
                row is None
                or type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(row["text"])
            ):
                raise ReviewRefused("A fee term needs exact current scoped source words")
            selected.add(raw["reference_id"])
            return row["text"][start:end], row

        schedule_words, schedule = clause(candidate["schedule"])
        schedule_id = schedule["reference"]["id"]
        schedule_kind = schedule["reference"]["kind"]
        if schedule_kind not in {ReferenceKind.SOURCE.value, ReferenceKind.DOCUMENT.value}:
            raise ReviewRefused(
                "A tariff needs an actual primary source or admitted document, not an assertion"
            )
        events = {row["identity"]: row for row in inventory["events"]}
        event = events.get(candidate["as_of_event_id"])
        if event is None or event["on"] is None:
            raise FeeNotAssessed("Fee arithmetic needs one exact recorded resolved comparison date")
        event = EventObservation.restore(
            {key: event[key] for key in EventObservation.__dataclass_fields__}
        )
        if schedule_kind == ReferenceKind.SOURCE.value:
            found = findings.get(schedule_id)
            if found is None:
                raise FeeNotAssessed("Unassessed raw law cannot become a versioned fee schedule")
            finding = found[0]
            if (
                finding.source_kind is not SourceKind.PROVISION
                or finding.supports is False
                or finding.source_blocking_reason
            ):
                raise FeeNotAssessed(
                    "The exact retrieved primary schedule is unavailable or known blocked"
                )
            if finding.governing_date != event.on:
                raise FeeNotAssessed(
                    "The schedule reader's actual governing date differs from the selected date"
                )
        elif schedule_id not in documents:
            raise ReviewRefused("The fee document is not the actual owned admitted derivative")

        def tariff(raw):
            text, row = clause(raw)
            if row["reference"]["id"] != schedule_id or not (
                candidate["schedule"]["start"]
                <= raw["start"]
                < raw["end"]
                <= candidate["schedule"]["end"]
            ):
                raise ReviewRefused(
                    "One schedule cannot mix literal/convention/version spans from another"
                )
            return text, row

        def convention(raw, choices):
            text, _row = tariff(raw)
            value = choices.get(text.strip().casefold())
            if value is None:
                raise FeeNotAssessed("No supported explicit fee convention is stated: " + text)
            return value

        def number(raw, *, percentage=False):
            text, row = tariff(raw)
            return FeeObservation(
                row["reference"]["identity"],
                text,
                str(fee_literal(text, percentage=percentage)),
                percentage,
            )

        version, _row = tariff(candidate["schedule_version"])
        if not version.strip() or len(version) > 128:
            raise FeeNotAssessed("The actual quoted schedule version is missing or unbounded")
        currency, _row = tariff(candidate["currency"])
        mode = convention(
            candidate["mode"],
            {
                "fixed fee": "fixed",
                "percentage fee": "percentage",
                "per unit fee": "per_unit",
                "flat bands": "flat_bands",
                "marginal percentage bands": "marginal_bands",
            },
        )
        basis = None
        if candidate["basis"] is not None:
            text, row = clause(candidate["basis"]["literal"])
            if row["reference"]["kind"] not in {
                ReferenceKind.FACT.value,
                ReferenceKind.DOCUMENT.value,
            }:
                raise ReviewRefused("Case valuation/quantity cannot be taken from a public tariff")
            basis = FeeObservation(row["reference"]["identity"], text, str(fee_literal(text)))
            if mode == "per_unit":
                if candidate["basis"]["currency"] is not None:
                    raise FeeNotAssessed("A unit quantity cannot masquerade as a currency amount")
            else:
                raw_currency = candidate["basis"]["currency"]
                if (
                    raw_currency is None
                    or raw_currency["reference_id"] != row["reference"]["id"]
                    or clause(raw_currency)[0] != currency
                ):
                    raise FeeNotAssessed(
                        "Case valuation and schedule require the same explicit currency"
                    )
        charge = (
            number(candidate["charge"], percentage=mode == "percentage")
            if candidate["charge"] is not None
            else None
        )
        bands = []
        for row in candidate["bands"]:
            words, _reference = tariff(row["upper"])
            upper = None if words.strip().casefold() == "unbounded" else number(row["upper"])
            bands.append(
                FeeBand(
                    number(row["lower"]),
                    upper,
                    number(row["charge"], percentage=mode == "marginal_bands"),
                )
            )
        if bands:
            if candidate["boundaries"] is None:
                raise FeeNotAssessed("Band endpoint inclusivity cannot be guessed")
            convention(candidate["boundaries"], {"lower inclusive upper exclusive": "explicit"})
        elif candidate["boundaries"] is not None:
            raise FeeNotAssessed("A non-banded fee has no invented band convention")

        def limit(raw, label):
            choice = convention(raw["mode"], {"no " + label: "none", label + " fee": "amount"})
            if (choice == "none") != (raw["amount"] is None):
                raise FeeNotAssessed("A fee limit needs its exact amount or explicit absence")
            return number(raw["amount"]) if raw["amount"] is not None else None

        minimum, maximum = (
            limit(candidate["minimum"], "minimum"),
            limit(candidate["maximum"], "maximum"),
        )
        digits = convention(
            candidate["rounding_digits"], {str(number): number for number in range(9)}
        )
        rounding = convention(
            candidate["rounding_mode"],
            {"half-up": "half_up", "half-even": "half_even", "round down": "down"},
        )
        convention(candidate["rounding_stage"], {"at end": "at_end"})
        unit_size = number(candidate["unit_size"]) if candidate["unit_size"] is not None else None
        unit_rounding = (
            convention(
                candidate["unit_rounding"],
                {"exact units": "exact", "round units up": "up", "round units down": "down"},
            )
            if candidate["unit_rounding"] is not None
            else None
        )
        if any(row["state"] != "selected" for row in coverage if row["reference_id"] in selected):
            raise ReviewRefused(
                "Selected fee/case sources cannot be declared excluded or unassessed"
            )
        assumptions = tuple(
            "Current source "
            + row["reference_id"]
            + ": "
            + row["state"]
            + ". Reason: "
            + row["reason"]
            for row in coverage
        )
        inputs = FeeInputs(
            mode,
            currency,
            basis,
            charge,
            tuple(bands),
            unit_size,
            unit_rounding,
            minimum,
            maximum,
            digits,
            rounding,
            event.on,
            event.identity,
            schedule["reference"]["identity"],
            version,
            schedule_kind,
            assumptions + (candidate["reason"],),
            digest(candidate),
        )
        spans, docs, facts = [], [], []
        for ident, row in references.items():
            if row["reference"]["kind"] == ReferenceKind.FACT.value:
                facts.append(matter.fact(ident.removeprefix("fact:")))
            elif ident in findings:
                finding = findings[ident][0]
                spans.append(EvidenceSpan(ident, finding, 0, len(finding.span)))
            elif ident in documents:
                document = documents[ident]
                docs.append(MatterDocumentSpan(ident, document, 0, len(document.text)))
            else:
                raise FeeNotAssessed("The complete fee population contains unassessed raw law")
        subject = {
            "trust": "source-attributed conditional schedule arithmetic, "
            "never legally payable court fee",
            "entire_current_scoped_inventory": inventory,
            "candidate": candidate,
            "derived_inputs": neutral(asdict(inputs)),
            "quoted_schedule": schedule_words,
            "legal_schedule_verified": False,
            "instruction": "Independently inspect the complete population and original request, "
            "every "
            "literal/currency/version/date, applicability of the arithmetic mode, all tariff rows "
            "and endpoint conventions, minimum/maximum, units and rounding. Inspect for competing "
            "schedules, valuations, omitted rows/exemptions/surcharges and known uncertainty. "
            "Coverage labels and a source version label are not a completeness/current-law "
            "verdict. "
            "Missing or ambiguous schedule/conventions remain unassessed; no statutory payable "
            "fee, valuation rule, jurisdiction, filing authority, factual truth or release "
            "is established.",
        }
        claim = _describe(subject)
        if len(claim) > 256000:
            raise ReviewRefused(
                "The full fee review population exceeds its private bounded ceiling"
            )
        package = EvidencePackage(
            "fee_" + digest({"turn": record.identity.turn_id, "id": candidate["id"]}),
            claim,
            tuple(spans),
            premises=tuple(facts),
            documents=tuple(docs),
        )
        return FeeBinding(candidate, inventory, inputs, package)

    def candidates(self, outcome, matter):
        calls, candidates = {}, {}
        for event in outcome.record.events:
            if event.kind is StepKind.TOOL_STARTED and event.payload["call"]["name"] == PROPOSE:
                call = event.payload["call"]
                calls[call["call_id"]] = call
            elif event.kind is StepKind.TOOL_RETURNED and event.payload.get("call_id") in calls:
                call = calls.pop(event.payload["call_id"])
                raw = event.payload["receipt"]
                if any(
                    raw[key] != value
                    for key, value in {
                        "tool": PROPOSE,
                        "version": VERSION,
                        "kind": "control",
                        "assessment": "not_assessed",
                        "outcome": "results",
                        "availability": "available",
                        "effect": "continue",
                    }.items()
                ) or raw["receipt"] != {
                    "operation": PROPOSE,
                    "turn_id": outcome.record.identity.turn_id,
                    "matter_id": matter.id,
                    "selection_identity": digest(call["arguments"]),
                }:
                    raise ReviewRefused("The fee selection lost its actual exact completed receipt")
                binding = self.bind(outcome.record, matter, call["arguments"])
                if raw["data"] != {
                    "candidate": call["arguments"],
                    "derived_inputs": neutral(asdict(binding.inputs)),
                    "selection_reviewed": False,
                    "released": False,
                }:
                    raise ReviewRefused(
                        "Recorded fee inputs differ from exact current source readings"
                    )
                ident = binding.candidate["id"]
                if ident in candidates and candidates[ident].candidate != binding.candidate:
                    raise ReviewRefused("A fee selection identity has ambiguous versions")
                candidates[ident] = binding
        return tuple(candidates.values())

    def packages(self, outcome, matter):
        return tuple(row.package for row in self.candidates(outcome, matter))


class FeeSelectionReviewService:
    def __init__(self, *, reviewer: ReviewService | None, owner: FeeSelectionOwner):
        if (
            not isinstance(owner, FeeSelectionOwner)
            or reviewer is not None
            and not isinstance(reviewer, ReviewService)
        ):
            raise ValueError("Fee selections use the actual shared independent-review owner")
        self.reviewer, self.owner = reviewer, owner

    def _current(self, outcome, matter, proposed):
        if self.owner.packages(outcome, matter) != proposed:
            raise ReviewRefused("The full exact source-owned fee subject changed")

    def _sources(self, outcome, matter, proposed):
        self._current(outcome, matter, proposed)
        return tuple(dict.fromkeys(span.finding for package in proposed for span in package.spans))

    def review(self, outcome, *, budget=None, cancelled=lambda: False, max_model_calls=None):
        if self.reviewer is None:
            return FeeSelectionReview((), None)
        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        bindings = self.owner.candidates(outcome, matter)
        if not bindings:
            return FeeSelectionReview((), None)
        review = self.reviewer.review_packages(
            outcome,
            tuple(row.package for row in bindings),
            current_owner=self._current,
            current_sources=self._sources,
            cancelled=cancelled,
            max_model_calls=max_model_calls,
            **({"budget": budget} if budget is not None else {}),
        )
        return FeeSelectionReview(bindings, review)

    def recorded(self, outcome):
        if self.reviewer is None:
            return FeeSelectionReview((), None)
        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        bindings = self.owner.candidates(outcome, matter)
        packages = tuple(row.package for row in bindings)
        matter = self.reviewer._current(outcome, packages=packages, current_owner=self._current)
        review = (
            saved_package_reviews(outcome, packages, matter, self.reviewer.log)
            if packages
            else None
        )
        judge = (
            self.reviewer.verifier.model.provider,
            self.reviewer.verifier.model.resolved_model(self.reviewer.verifier.tier),
        )
        if review is not None and any((row.provider, row.model) != judge for row in review.records):
            raise ReviewRefused(
                "Fee selection review belongs to a different current independent judge"
            )
        return FeeSelectionReview(bindings, review)

    def resolve(self, matter, context, selection_id):
        if self.reviewer is None:
            return None
        matching = []
        for parent in matter.loop_records:
            terminal = parent.events[-1].payload if parent.terminal else {}
            if (
                not parent.terminal
                or terminal.get("reason")
                not in {
                    StopReason.PROPOSAL.value,
                    StopReason.QUESTION.value,
                    StopReason.CONVERSATION.value,
                }
                or "budget" not in terminal
                or "proposal" not in terminal
                or parent.identity.advocate_id != context.identity.advocate_id
                or parent.identity.matter_id != context.identity.matter_id
                or parent.identity.mode is not context.identity.mode
                or parent.identity.turn_id == context.identity.turn_id
            ):
                continue
            try:
                raw = parent.events[-1].payload
                outcome = LoopOutcome(
                    StopReason(raw["reason"]), parent, _budget_from(raw["budget"]), raw["proposal"]
                )
                result = self.recorded(outcome)
                for binding in result.bindings:
                    if (
                        binding.candidate["id"] == selection_id
                        and result.review is not None
                        and binding.package in result.review.result.released
                    ):
                        matching.append(binding)
            except (ReviewRefused, FeeNotAssessed, SchemaViolation):
                continue
        return matching[0] if len(matching) == 1 else None


def fee_tools(store, *, owner: FeeSelectionOwner, reviews: FeeSelectionReviewService | None):
    """Three genuine registry doors, replacing only the unavailable court_fee stub."""
    if (
        not isinstance(owner, FeeSelectionOwner)
        or reviews is not None
        and reviews.owner is not owner
    ):
        raise ValueError("All fee doors share one actual current selection owner")

    def current(context):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
        ):
            raise ToolRefused("Fee tools require the exact current owned file")
        records = [row for row in matter.loop_records if row.identity == context.identity]
        if len(records) != 1 or records[0].terminal:
            raise ToolRefused("Fee tools need one actual current open parent")
        return matter, records[0]

    def envelope(name, context, data, *, selection_identity=""):
        receipt = {
            "operation": name,
            "turn_id": context.identity.turn_id,
            "matter_id": context.identity.matter_id,
        }
        if selection_identity:
            receipt["selection_identity"] = selection_identity
        return ToolEnvelope(
            name,
            VERSION,
            ToolKind.CONTROL,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            receipt,
            data,
            "Private conditional fee inputs; no lawful payable fee, valuation, truth or release.",
        )

    controls = ("test_fee_needs_actual_saved_selection_review_and_current_source_population",)
    from nm.Archives.legal_brain.procedure.tool_court_fee import build_tool as court_fee_tool
    from nm.Archives.legal_brain.procedure.tool_propose_fee_selection import (
        build_tool as propose_fee_selection_tool,
    )
    from nm.Archives.legal_brain.procedure.tool_read_fee_inventory import (
        build_tool as read_fee_inventory_tool,
    )

    return (
        read_fee_inventory_tool(current=current, envelope=envelope, owner=owner, controls=controls),
        propose_fee_selection_tool(
            current=current, envelope=envelope, owner=owner, controls=controls
        ),
        court_fee_tool(current=current, owner=owner, reviews=reviews, controls=controls),
    )
