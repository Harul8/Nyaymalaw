"""Actual source-span selections, independently reviewed before conditional math.

The complete current scoped inventory and every coverage judgment enter the
independent package. An author cannot omit a recorded payment or competing
source from that review by choosing a smaller supporting-source subset.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from nm.legal_brain.orchestrate.loop import _budget_from
from nm.legal_brain.orchestrate.loop_contracts import LoopOutcome, StepKind, StopReason, digest
from nm.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.legal_brain.procedure.interest_calculation_contracts import (
    InterestInputs,
    InterestNotAssessed,
    InterestPayment,
    MonetaryObservation,
    decimal_literal,
)
from nm.legal_brain.procedure.reviewed_limitation_selection import _describe
from nm.legal_brain.reason.matter_support import MatterDocumentSpan, captured_documents
from nm.legal_brain.reason.working_record import WorkingRecordOwner
from nm.legal_brain.reason.working_record_contracts import ReferenceKind
from nm.legal_brain.verify.brain_assessment import saved_package_reviews
from nm.legal_brain.verify.brain_finalization import neutral
from nm.legal_brain.verify.brain_release import ReviewRefused, ReviewService
from nm.legal_brain.verify.verifier import EvidencePackage, EvidenceSpan
from nm.shared.model_port import require_schema
from nm.work_the_file.date_resolution import resolve
from nm.work_the_file.event_observation_contracts import EventObservation

VERSION = "source-owned-interest-selection-v1"
READ = "read_interest_inventory"
PROPOSE = "propose_interest_selection"
COMPUTE = "compute_interest"
_TEXT = {"type": "string", "minLength": 1}
_CLAUSE = object_schema(
    {
        "reference_id": _TEXT,
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1},
    }
)
_NULL_CLAUSE = {**_CLAUSE, "type": ["object", "null"]}
_MONEY = object_schema(
    {
        "id": _TEXT,
        "purpose": {"type": "string", "enum": ["principal", "annual_rate", "payment"]},
        "literal": _CLAUSE,
        "currency": _NULL_CLAUSE,
    }
)
_PAYMENT = object_schema({"observation_id": _TEXT, "event_id": _TEXT, "allocation": _CLAUSE})
INTEREST_SELECTION_SCHEMA = object_schema(
    {
        "id": _TEXT,
        "thread_id": _TEXT,
        "inventory_identity": _TEXT,
        "observations": {"type": "array", "minItems": 2, "maxItems": 102, "items": _MONEY},
        "principal_id": _TEXT,
        "rate_id": _TEXT,
        "start_event_id": _TEXT,
        "end_event_id": _TEXT,
        "mode": _CLAUSE,
        "day_count": _CLAUSE,
        "year_basis": _CLAUSE,
        "rate_period": _CLAUSE,
        "rounding_digits": _CLAUSE,
        "rounding_mode": _CLAUSE,
        "rounding_stage": _CLAUSE,
        "cadence": _NULL_CLAUSE,
        "payments": {"type": "array", "maxItems": 100, "items": _PAYMENT},
        "coverage": {
            "type": "array",
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
class InterestBinding:
    candidate: dict
    inventory: dict
    inputs: InterestInputs
    package: EvidencePackage


@dataclass(frozen=True)
class InterestSelectionReview:
    bindings: tuple[InterestBinding, ...]
    review: object | None

    @property
    def unresolved(self):
        released = self.review.result.released if self.review is not None else ()
        return tuple(row for row in self.bindings if row.package not in released)


class InterestSelectionOwner:
    def __init__(self, *, source_owner: WorkingRecordOwner):
        if not isinstance(source_owner, WorkingRecordOwner):
            raise ValueError("Interest requires the actual typed working-source owner")
        self.source_owner = source_owner

    def inventory(self, record, matter, thread_id):
        working = self.source_owner.build(record, matter)
        thread = next((row for row in matter.threads if row.id == thread_id), None)
        if thread is None or thread_id not in {row["id"] for row in working.payload["threads"]}:
            raise ReviewRefused("The interest dispute is outside the complete admitted file scope")
        references = [
            row
            for row in working.payload["references"]
            if row["reference"]["kind"]
            in {ReferenceKind.FACT.value, ReferenceKind.DOCUMENT.value, ReferenceKind.SOURCE.value}
            and (not row["thread_ids"] or thread_id in row["thread_ids"])
        ]
        events = []
        for raw in thread.event_observations:
            event = EventObservation.restore(raw)
            fact = matter.fact(event.source_fact)
            if (
                fact is None
                or fact.id not in thread.chronology
                or fact.version != event.source_version
                or fact.statement != event.account
                or fact.superseded_by
                or fact.conflicts_with
                or fact.confirmed is False
                or event.on is not None
                and resolve(event.date_expression, event.reference) != event.on
            ):
                raise ReviewRefused(
                    "Interest date observations lost their exact current attributed source"
                )
            events.append(event.as_dict())
        if len({row["identity"] for row in events}) != len(events):
            raise ReviewRefused("Interest event population is ambiguous")
        value = {
            "thread_id": thread_id,
            "file_snapshot": working.payload["file_snapshot"],
            "original_instruction": working.payload["original_instruction"],
            "thread": neutral(asdict(thread)),
            "references": references,
            "events": events,
            "factual_truth_established": False,
            "selection_reviewed": False,
        }
        value["identity"] = digest(value)
        return value

    def bind(self, record, matter, candidate):
        require_schema(candidate, INTEREST_SELECTION_SCHEMA)
        inventory = self.inventory(record, matter, candidate["thread_id"])
        if candidate["inventory_identity"] != inventory["identity"]:
            raise ReviewRefused("Interest selections belong to a changed exact scoped inventory")
        references = {row["reference"]["id"]: row for row in inventory["references"]}
        coverage = candidate["coverage"]
        if len(coverage) != len(references) or {row["reference_id"] for row in coverage} != set(
            references
        ):
            raise ReviewRefused(
                "Interest review must cover every actual current source/fact/document"
            )
        if len({row["reference_id"] for row in coverage}) != len(coverage):
            raise ReviewRefused("Repeated source coverage cannot hide another payment or rule")
        selected_refs = set()

        def clause(raw):
            row = references.get(raw["reference_id"])
            start, end = raw["start"], raw["end"]
            if (
                row is None
                or type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(row["text"])
            ):
                raise ReviewRefused("An interest term needs exact current scoped source words")
            selected_refs.add(raw["reference_id"])
            return row["text"][start:end], row

        def convention(raw, accepted):
            text, _row = clause(raw)
            value = accepted.get(text.strip().casefold())
            if value is None:
                raise InterestNotAssessed(
                    "The exact source states no supported explicit convention: " + text
                )
            return value

        observations = {}
        for raw in candidate["observations"]:
            if raw["id"] in observations:
                raise ReviewRefused("Interest observations have unique owned identities")
            text, row = clause(raw["literal"])
            if raw["purpose"] != "annual_rate" and row["reference"]["kind"] not in (
                ReferenceKind.FACT.value,
                ReferenceKind.DOCUMENT.value,
            ):
                raise ReviewRefused(
                    "Principal and payments require actual case words, not public law"
                )
            currency = clause(raw["currency"])[0] if raw["currency"] is not None else None
            amount = decimal_literal(text, percentage=raw["purpose"] == "annual_rate")
            observations[raw["id"]] = MonetaryObservation(
                raw["id"], raw["purpose"], row["reference"]["identity"], text, str(amount), currency
            )
        principal, rate = (
            observations.get(candidate["principal_id"]),
            observations.get(candidate["rate_id"]),
        )
        if principal is None or rate is None:
            raise ReviewRefused("Interest cannot invent a selected principal or rate observation")
        if (
            sum(row.purpose == "principal" for row in observations.values()) != 1
            or sum(row.purpose == "annual_rate" for row in observations.values()) != 1
        ):
            raise InterestNotAssessed(
                "Competing principals/rates need independently distinct calculations"
            )
        events = {row["identity"]: row for row in inventory["events"]}

        def dated(ident):
            row = events.get(ident)
            if row is None or row["on"] is None:
                raise ReviewRefused("An interest endpoint needs one exact current resolved event")
            return EventObservation.restore(
                {key: row[key] for key in EventObservation.__dataclass_fields__}
            )

        start, end = dated(candidate["start_event_id"]), dated(candidate["end_event_id"])
        mode = convention(
            candidate["mode"], {"simple interest": "simple", "compound interest": "compound"}
        )
        convention(candidate["day_count"], {"actual days": "actual"})
        year_basis = convention(candidate["year_basis"], {"365": 365, "360": 360})
        rate_convention = convention(
            candidate["rate_period"],
            {"per annum": "annual_simple", "per year": "annual_simple"}
            if mode == "simple"
            else {"nominal per annum": "nominal_annual", "nominal annual rate": "nominal_annual"},
        )
        rounding_digits = convention(
            candidate["rounding_digits"], {str(number): number for number in range(9)}
        )
        rounding_mode = convention(
            candidate["rounding_mode"],
            {"half-up": "half_up", "half-even": "half_even", "round down": "down"},
        )
        rounding_stage = convention(
            candidate["rounding_stage"], {"at end": "at_end", "per period": "per_period"}
        )
        cadence = (
            convention(candidate["cadence"], {"monthly": 1, "quarterly": 3, "annually": 12})
            if candidate["cadence"] is not None
            else None
        )
        payments = []
        for row in candidate["payments"]:
            money = observations.get(row["observation_id"])
            if money is None:
                raise ReviewRefused("A payment needs its recorded monetary observation")
            event = dated(row["event_id"])
            allocation = convention(
                row["allocation"],
                {"principal only": "principal_only", "interest first": "interest_first"},
            )
            payments.append(
                InterestPayment(
                    money, event.on, event.identity, allocation, digest(row["allocation"])
                )
            )
        if {row.observation.id for row in payments} != {
            row.id for row in observations.values() if row.purpose == "payment"
        }:
            raise ReviewRefused("Every recorded payment observation needs its dated allocation")
        if any(
            row["state"] != "selected" for row in coverage if row["reference_id"] in selected_refs
        ):
            raise ReviewRefused("Selected monetary/rule sources cannot be declared excluded")
        assumptions = tuple(
            "Current source "
            + row["reference_id"]
            + ": "
            + row["state"]
            + ". Reason: "
            + row["reason"]
            for row in coverage
        )
        inputs = InterestInputs(
            principal,
            rate,
            start.on,
            end.on,
            start.identity,
            end.identity,
            mode,
            year_basis,
            rounding_digits,
            rounding_mode,
            rounding_stage,
            rate_convention,
            cadence,
            tuple(payments),
            assumptions + (candidate["reason"],),
            digest(candidate),
        )
        findings, _windows = self.source_owner._sources(record)
        documents = {
            "document:" + digest(neutral(asdict(row))): row for row in captured_documents(record)
        }
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
                raise ReviewRefused("Raw law windows cannot become an assessed interest rule")
        subject = {
            "trust": "source-attributed conditional mathematical selections, not entitlement",
            "entire_current_scoped_inventory": inventory,
            "candidate": candidate,
            "derived_inputs": neutral(asdict(inputs)),
            "conditional": True,
            "instruction": "Independently assess every monetary reading, currency, dated period, "
            "day count, rounding, rate period, compounding and allocation. Inspect the full "
            "inventory for omitted known payments and competing rates/rules. An author coverage "
            "label is not your relevance finding. Missing/contested bases remain unassessed.",
        }
        claim = _describe(subject)
        if len(claim) > 256000:
            raise ReviewRefused("The entire interest review population exceeds its private ceiling")
        package = EvidencePackage(
            "interest_" + digest({"turn": record.identity.turn_id, "id": candidate["id"]}),
            claim,
            tuple(spans),
            premises=tuple(facts),
            documents=tuple(docs),
        )
        return InterestBinding(candidate, inventory, inputs, package)

    def candidates(self, outcome, matter):
        calls, candidates = {}, {}
        for event in outcome.record.events:
            if event.kind is StepKind.TOOL_STARTED and event.payload["call"]["name"] == PROPOSE:
                call = event.payload["call"]
                calls[call["call_id"]] = call
            elif event.kind is StepKind.TOOL_RETURNED and event.payload.get("call_id") in calls:
                call = calls.pop(event.payload["call_id"])
                raw = event.payload["receipt"]
                if (
                    raw["tool"] != PROPOSE
                    or raw["version"] != VERSION
                    or raw["kind"] != "control"
                    or raw["assessment"] != "not_assessed"
                    or raw["outcome"] != "results"
                    or raw["availability"] != "available"
                    or raw["effect"] != "continue"
                    or raw["receipt"]
                    != {
                        "operation": PROPOSE,
                        "turn_id": outcome.record.identity.turn_id,
                        "matter_id": matter.id,
                        "selection_identity": digest(call["arguments"]),
                    }
                ):
                    raise ReviewRefused("The interest selection lost its actual exact tool receipt")
                binding = self.bind(outcome.record, matter, call["arguments"])
                expected = {
                    "candidate": call["arguments"],
                    "observations": [
                        neutral(asdict(row))
                        for row in (
                            binding.inputs.principal,
                            binding.inputs.rate,
                            *(payment.observation for payment in binding.inputs.payments),
                        )
                    ],
                    "selection_reviewed": False,
                    "released": False,
                }
                if raw["data"] != expected:
                    raise ReviewRefused(
                        "Recorded monetary observations differ from their exact source readings"
                    )
                ident = call["arguments"]["id"]
                if ident in candidates and candidates[ident].candidate != binding.candidate:
                    raise ReviewRefused(
                        "Interest selection identity has ambiguous candidate versions"
                    )
                candidates[ident] = binding
        return tuple(candidates.values())

    def packages(self, outcome, matter):
        return tuple(row.package for row in self.candidates(outcome, matter))


class InterestSelectionReviewService:
    def __init__(self, *, reviewer: ReviewService, owner: InterestSelectionOwner):
        if not isinstance(reviewer, ReviewService) or not isinstance(owner, InterestSelectionOwner):
            raise ValueError("Interest uses the actual shared independent-review owner")
        self.reviewer, self.owner = reviewer, owner

    def review(self, outcome, *, budget=None, cancelled=lambda: False, max_model_calls=None):
        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        bindings = self.owner.candidates(outcome, matter)
        packages = tuple(row.package for row in bindings)
        if not packages:
            return InterestSelectionReview((), None)
        review = self.reviewer.review_packages(
            outcome,
            packages,
            current_owner=self._current,
            current_sources=self._sources,
            cancelled=cancelled,
            max_model_calls=max_model_calls,
            **({"budget": budget} if budget is not None else {}),
        )
        return InterestSelectionReview(bindings, review)

    def recorded(self, outcome):
        matter = self.reviewer.store.load(outcome.record.identity.matter_id)
        bindings = self.owner.candidates(outcome, matter)
        packages = tuple(row.package for row in bindings)
        matter = self.reviewer._current(outcome, packages=packages, current_owner=self._current)
        review = (
            saved_package_reviews(outcome, packages, matter, self.reviewer.log)
            if packages
            else None
        )
        return InterestSelectionReview(bindings, review)

    def _current(self, outcome, matter, proposed):
        if self.owner.packages(outcome, matter) != proposed:
            raise ReviewRefused(
                "The full current interest selection subjects changed before review"
            )

    def _sources(self, outcome, matter, proposed):
        self._current(outcome, matter, proposed)
        return tuple(dict.fromkeys(span.finding for package in proposed for span in package.spans))

    def resolve(self, matter, context, selection_id):
        matching = []
        for parent in matter.loop_records:
            if (
                not parent.terminal
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
            except (ReviewRefused, InterestNotAssessed, TypeError, ValueError, KeyError):
                continue
        return matching[0] if len(matching) == 1 else None


def interest_tools(
    store, *, owner: InterestSelectionOwner, reviews: InterestSelectionReviewService | None
):
    """Three actual doors; composition replaces only its old unavailable compute door."""
    if reviews is not None and reviews.owner is not owner:
        raise ValueError(
            "Interest reading, writing and computation have one owned selection contract"
        )

    def current(context):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
        ):
            raise ToolRefused("Interest tools require the exact current owned file")
        records = [row for row in matter.loop_records if row.identity == context.identity]
        if len(records) != 1 or records[0].terminal:
            raise ToolRefused("Interest tools need one actual current open parent")
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
            "Private source-attributed inputs; no entitlement, truth or release certified.",
        )

    controls = ("test_interest_needs_actual_saved_selection_review_and_current_source_population",)
    from nm.legal_brain.procedure.tool_compute_interest import build_tool as compute_interest_tool
    from nm.legal_brain.procedure.tool_propose_interest_selection import (
        build_tool as propose_interest_selection_tool,
    )
    from nm.legal_brain.procedure.tool_read_interest_inventory import (
        build_tool as read_interest_inventory_tool,
    )

    return (
        read_interest_inventory_tool(
            current=current, envelope=envelope, owner=owner, controls=controls
        ),
        propose_interest_selection_tool(
            current=current, envelope=envelope, owner=owner, controls=controls
        ),
        compute_interest_tool(
            current=current, owner=owner, reviews=reviews, store=store, controls=controls
        ),
    )
