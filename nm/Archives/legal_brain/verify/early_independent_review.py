"""A real independent read inside one open parent, never a second journal writer.

The trusted producer owns exact candidate/source binding. This transport does
not invent a producer, promote a fact or supply calculator authority. Only the
actual LoopRunner can seal its delegated transcript into the parent receipt.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, fields, replace

from nm.Archives.legal_brain.orchestrate.loop import _budget_from, _checked_child_budget
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopRecord, StepKind
from nm.Archives.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    DelegatedToolResult,
    DelegationGrant,
    DelegationPolicy,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    object_schema,
)
from nm.Archives.legal_brain.retrieve.evidence_port import Finding
from nm.Archives.legal_brain.retrieve.tool_sources import tool_envelope_from_record
from nm.Archives.legal_brain.verify.brain_release import ReviewRefused, _decode_verdict, _json, _review_spend
from nm.Archives.legal_brain.verify.verifier import (
    EvidencePackage,
    IndependentVerifier,
    VerificationRecord,
    _unassessed,
    interpret_completed_verification,
    verification_prompt,
)
from nm.open_matter.matter_documents_port import MatterDocumentQuote
from nm.shared.budget_contracts import Completion, Exhausted, Spend
from nm.shared.json_values import same_json_value
from nm.shared.model_port import (
    ModelResult,
    Tier,
    Usage,
    estimate_tokens,
    require_schema,
)

TOOL = "check_candidate_independently"
VERSION = "early-independent-package-v1"
SCHEMA = object_schema({"candidate_id": {"type": "string", "minLength": 1}})


@dataclass(frozen=True)
class EarlyReviewSubject:
    package: EvidencePackage
    retrieved: tuple[Finding, ...]
    documents: tuple[MatterDocumentQuote, ...] = ()

    def __post_init__(self):
        if (
            not isinstance(self.package, EvidencePackage)
            or type(self.retrieved) is not tuple
            or any(not isinstance(row, Finding) for row in self.retrieved)
            or type(self.documents) is not tuple
            or any(not isinstance(row, MatterDocumentQuote) for row in self.documents)
        ):
            raise ValueError("An early check requires the existing exact package/source contracts")

    def wire(self):
        return json.loads(
            _json(
                {
                    "package_identity": self.package.identity,
                    "package": self.package.payload(),
                    "retrieved": [row.as_record() for row in self.retrieved],
                    "documents": [asdict(row) for row in self.documents],
                }
            )
        )


@dataclass(frozen=True)
class EarlyReviewRead:
    subject: EarlyReviewSubject | None
    verification: VerificationRecord | None
    spend: Spend
    model_steps: int
    reason: str

    @property
    def checked(self):
        return self.verification is not None and self.verification.releasable

    @property
    def client_ready(self):
        return False


def _result(raw):
    if not isinstance(raw, dict) or set(raw) != {row.name for row in fields(ModelResult)}:
        raise ReviewRefused("An early response lacks its exact model result contract")
    values = dict(raw)
    values.update(
        usage=Usage(**raw["usage"]),
        tier=Tier(raw["tier"]),
        completion=Completion(raw["completion"]),
        downgraded_from=Tier(raw["downgraded_from"])
        if raw["downgraded_from"] is not None
        else None,
    )
    return ModelResult(**values)


class EarlyIndependentReviewService:
    def __init__(
        self,
        *,
        store,
        log,
        verifier,
        subject_owner,
        source_current,
        session_current,
        current_tools_version,
        current_principles_version,
        cost_ceiling,
        monotonic=time.monotonic,
    ):
        if (
            not isinstance(verifier, IndependentVerifier)
            or verifier.tier is not Tier.JUDGE
            or any(
                not callable(row)
                for row in (
                    subject_owner,
                    source_current,
                    session_current,
                    current_tools_version,
                    current_principles_version,
                    cost_ceiling,
                    monotonic,
                )
            )
        ):
            raise ValueError("Early review needs actual independent and current trusted owners")
        self.store, self.log, self.verifier = store, log, verifier
        self.subject_owner, self.source_current = subject_owner, source_current
        self.session_current, self.current_tools_version = session_current, current_tools_version
        self.current_principles_version, self.cost_ceiling = (
            current_principles_version,
            cost_ceiling,
        )
        self.monotonic = monotonic

    def tools(self, policy: DelegationPolicy):
        from nm.Archives.legal_brain.verify.tool_check_candidate_independently import build_tool

        return (build_tool(service=self, policy=policy),)

    def _subject(self, parent, candidate_id, *, expected_version=None):
        matter = self.store.load(parent.identity.matter_id)
        if (
            not self.session_current()
            or matter is None
            or matter.advocate_id != parent.identity.advocate_id
            or expected_version is not None
            and matter.version != expected_version
            or self.current_tools_version() != parent.identity.tools_version
            or self.current_principles_version() != parent.identity.principles_version
        ):
            raise ReviewRefused("The early subject lost its current actor, source or principles")
        subject = self.subject_owner(parent, matter, candidate_id)
        if not isinstance(subject, EarlyReviewSubject) or self.source_current(subject) is not True:
            raise ReviewRefused("The exact early candidate/source owner is unavailable or stale")
        return subject

    @staticmethod
    def _authors(parent):
        authors = {
            (row.payload.get("provider"), row.payload.get("model"))
            for row in parent.events
            if row.kind is StepKind.MODEL_STARTED
        }
        if not authors or any(
            not all(type(value) is str and value.strip() for value in row) for row in authors
        ):
            raise ReviewRefused("The early candidate lacks its actual author dispatch identity")
        return authors

    def run(self, arguments, context):
        started, grant = self.monotonic(), context.delegation
        if not isinstance(grant, DelegationGrant):
            raise ReviewRefused("Early review has no actual parent delegation reservation")
        parent = self.log.read(context.identity)
        if (
            parent is None
            or parent.terminal
            or not parent.events
            or parent.events[-1].kind is not StepKind.TOOL_STARTED
            or parent.events[-1].payload["call"]["name"] != TOOL
            or not same_json_value(parent.events[-1].payload["call"]["arguments"], arguments)
            or not same_json_value(parent.events[-1].payload["delegation"], grant.as_dict())
        ):
            raise ReviewRefused("Early review requires its exact actual open tool dispatch")
        trace, subject, record, reserved, steps = [], None, None, None, 0
        judge = (self.verifier.model.provider, self.verifier.model.resolved_model(Tier.JUDGE))
        reason = "not_assessed"
        try:
            subject = self._subject(
                parent, arguments["candidate_id"], expected_version=context.current_version
            )
            trace.append(
                {
                    "kind": "review_subject",
                    "parent": parent.events[-1].fingerprint,
                    "candidate_id": arguments["candidate_id"],
                    "subject": subject.wire(),
                }
            )
            authors = self._authors(parent)
            if judge in authors:
                raise ReviewRefused("The author cannot independently check its own candidate")

            def current():
                if (
                    context.cancelled()
                    or grant.budget.cancelled_at
                    or self.log.read(context.identity) != parent
                    or judge
                    != (
                        self.verifier.model.provider,
                        self.verifier.model.resolved_model(Tier.JUDGE),
                    )
                    or self._subject(
                        parent, arguments["candidate_id"], expected_version=context.current_version
                    ).wire()
                    != subject.wire()
                ):
                    raise ReviewRefused("The exact current early-check admission changed")

            def before(prompt, tier, maximum):
                nonlocal reserved, steps
                current()
                incoming = estimate_tokens((prompt.system or "") + prompt.user)
                price = self.cost_ceiling(incoming, maximum, tier)
                elapsed = max(0, int((self.monotonic() - started) * 1000))
                if (
                    type(price) not in (int, float)
                    or not math.isfinite(price)
                    or price < 0
                    or tier is not Tier.JUDGE
                    or grant.policy.max_steps < 1
                    or incoming + maximum > grant.policy.max_tokens
                    or incoming + maximum > grant.budget.max_tokens - grant.budget.spend.tokens
                    or price > grant.policy.max_cost_usd
                    or price > grant.budget.max_cost_usd - grant.budget.spend.cost_usd
                    or elapsed >= grant.policy.max_ms
                    or grant.budget.spend.elapsed_ms + elapsed >= grant.budget.max_ms
                ):
                    raise ReviewRefused("The existing parent reservation cannot fund early review")
                reserved, steps = Spend(tokens=incoming + maximum, cost_usd=price), 1
                trace.append(
                    {
                        "kind": "model_started",
                        "prompt": asdict(prompt),
                        "provider": judge[0],
                        "model": judge[1],
                        "tier": tier.value,
                        "max_tokens": maximum,
                        "reserved_tokens": reserved.tokens,
                        "reserved_cost_usd": price,
                    }
                )

            def after(result):
                trace.append({"kind": "model_returned", "result": asdict(result)})

            def failed(error):
                trace.append(
                    {
                        "kind": "model_failed",
                        "reason": type(error).__name__,
                        "usage": asdict(error.usage) if error.usage else None,
                        "retries": error.retries,
                    }
                )

            author = next(iter(authors))
            record = self.verifier.verify(
                subject.package,
                author_provider=author[0],
                author_model=author[1],
                retrieved=subject.retrieved,
                retrieved_documents=subject.documents,
                before_dispatch=before,
                after_dispatch=after,
                on_error=failed,
            )
            current()
            reason = record.reason
        except ReviewRefused as exc:
            reason = str(exc)
            if subject is not None:
                record = _unassessed(
                    subject.package,
                    reason,
                    tier=Tier.JUDGE,
                    provider=judge[0],
                    model=judge[1],
                    usage=record.usage if record else None,
                    retries=record.retries if record else 0,
                )
        spend = (
            Spend(
                tokens=record.usage.tokens_in + record.usage.tokens_out,
                cost_usd=record.usage.cost_usd,
                retries=record.retries,
            )
            if record is not None and record.usage is not None
            else reserved or Spend()
        )
        spend = replace(
            spend, children=1, elapsed_ms=max(0, int((self.monotonic() - started) * 1000))
        )
        charged = grant.budget.spend_on(spend)
        if (
            context.cancelled()
            or charged.exhausted() not in (Exhausted.NONE, Exhausted.CHILDREN)
            or charged.spend.children > charged.max_children
            or spend.elapsed_ms > grant.policy.max_ms
            or reserved is not None
            and (spend.tokens > reserved.tokens or spend.cost_usd > reserved.cost_usd)
        ):
            reason = "Early review exceeded or lost its existing admitted resource boundary"
            if subject is not None:
                record = _unassessed(
                    subject.package,
                    reason,
                    tier=Tier.JUDGE,
                    provider=judge[0],
                    model=judge[1],
                    usage=record.usage if record else None,
                    retries=record.retries if record else 0,
                )
        if record is None or not record.releasable:
            spend = replace(spend, failed_children=1)
            charged = grant.budget.spend_on(spend)
        trace.append(
            {
                "kind": "review_completed",
                "verification": asdict(record) if record else None,
                "spend": asdict(spend),
                "reason": reason,
                "released": False,
            }
        )
        envelope = ToolEnvelope(
            TOOL,
            VERSION,
            ToolKind.CONTROL,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "operation": TOOL,
                "turn_id": parent.identity.turn_id,
                "candidate_id": arguments["candidate_id"],
            },
            {
                "verification": asdict(record) if record else None,
                "reason": reason,
                "released": False,
                "client_ready": False,
            },
            "Private exact-package check only; no fact, arithmetic authority or release created.",
        )
        return DelegatedToolResult(envelope, charged, steps, tuple(json.loads(_json(trace))))

    def recorded(self, parent, call_id):
        """Read actual sealed tool dispatch/result; a saved PASS is not its evidence."""
        if not isinstance(parent, LoopRecord) or self.log.read(parent.identity) != parent:
            raise ReviewRefused("The early check lacks its exact sealed parent record")
        starts = [
            (index, row)
            for index, row in enumerate(parent.events)
            if row.kind is StepKind.TOOL_STARTED and row.payload["call"]["call_id"] == call_id
        ]
        returns = [
            row
            for row in parent.events
            if row.kind is StepKind.TOOL_RETURNED and row.payload.get("call_id") == call_id
        ]
        if not starts and not returns:
            return None
        if len(starts) != 1 or len(returns) != 1:
            raise ReviewRefused("The early check's external outcome is missing or ambiguous")
        index, start = starts[0]
        end, call = returns[0].payload, start.payload["call"]
        require_schema(call["arguments"], SCHEMA)
        if call["name"] != TOOL or returns[0].sequence <= start.sequence:
            raise ReviewRefused("The actual early response has no matching preceding invocation")
        prefix = LoopRecord(parent.identity, parent.events[: index + 1])
        raw, trace = end["receipt"], end.get("child_transcript")
        if (
            raw["tool"] != TOOL
            or raw["version"] != VERSION
            or raw["kind"] != ToolKind.CONTROL.value
            or raw["assessment"] != Assessment.NOT_ASSESSED.value
            or raw["receipt"]
            != {
                "operation": TOOL,
                "turn_id": parent.identity.turn_id,
                "candidate_id": call["arguments"]["candidate_id"],
            }
            or end.get("child_released") is not False
            or not isinstance(trace, (list, tuple))
            or not trace
            or trace[-1].get("kind") != "review_completed"
        ):
            raise ReviewRefused("The early check lacks its actual owned sealed child transcript")
        finish = trace[-1]
        if any(
            row.get("kind")
            not in {
                "review_subject",
                "model_started",
                "model_returned",
                "model_failed",
                "review_completed",
            }
            for row in trace
        ):
            raise ReviewRefused("The private check contains an unowned or recursive operation")
        if (
            not same_json_value(
                raw["data"],
                {
                    "verification": finish["verification"],
                    "reason": finish["reason"],
                    "released": False,
                    "client_ready": False,
                },
            )
            or finish.get("released") is not False
        ):
            raise ReviewRefused("The early tool words differ from the actual private child result")
        spend = _review_spend(finish["spend"])
        dispatched = [row for row in trace if row.get("kind") == "model_started"]
        returned = [row for row in trace if row.get("kind") == "model_returned"]
        if (
            len(dispatched) > 1
            or len(returned) > 1
            or type(end.get("child_steps")) is not int
            or end["child_steps"] != len(dispatched)
            or any(
                type(row["max_tokens"]) is not int
                or row["max_tokens"] <= 0
                or type(row["reserved_tokens"]) is not int
                or row["reserved_tokens"] <= 0
                or type(row["reserved_cost_usd"]) not in (int, float)
                or not math.isfinite(row["reserved_cost_usd"])
                or row["reserved_cost_usd"] < 0
                for row in dispatched
            )
        ):
            raise ReviewRefused("The early check has an unknown attempted-dispatch population")
        initial = _budget_from(start.payload["delegation"]["budget"])
        _review_spend(start.payload["budget"]["spend"])
        _review_spend(start.payload["delegation"]["budget"]["spend"])
        # The child inherits the actual whole-task checkpoint; neither a
        # paired START/RETURN rewrite nor a saved PASS can manufacture a grant.
        admitted = parent.events[0].payload["budget"]
        previous = next(
            row.payload["budget"]
            for row in reversed(parent.events[:index])
            if "budget" in row.payload
        )
        if (
            not same_json_value(start.payload["budget"], initial.as_dict())
            or not same_json_value(start.payload["delegation"]["budget"], initial.as_dict())
            or any(
                not same_json_value(start.payload["budget"][key], admitted[key])
                for key in ("max_ms", "max_tokens", "max_cost_usd", "max_children", "max_retries")
            )
            or any(
                initial.as_dict()["spend"][key] < value for key, value in previous["spend"].items()
            )
            or previous["cancelled_at"]
            and start.payload["budget"]["cancelled_at"] != previous["cancelled_at"]
        ):
            raise ReviewRefused("The early child reset its actual whole-task grant or checkpoint")
        policy = DelegationPolicy(**start.payload["delegation"]["policy"])
        envelope = tool_envelope_from_record(raw)
        if (
            envelope.effect.value != "continue"
            or envelope.outcome is not ToolOutcome.RESULTS
            or envelope.availability is not Availability.AVAILABLE
        ):
            raise ReviewRefused("An early read cannot acquire execution or publication authority")
        charged = initial.spend_on(spend)
        _checked_child_budget(
            DelegationGrant(initial, policy),
            DelegatedToolResult(envelope, charged, end["child_steps"], tuple(trace)),
        )
        recorded_budget = _budget_from(end["budget"])
        expected = replace(
            recorded_budget,
            spend=replace(recorded_budget.spend, elapsed_ms=charged.spend.elapsed_ms),
        )
        if (
            not same_json_value(expected.as_dict(), charged.as_dict())
            or recorded_budget.spend.elapsed_ms < charged.spend.elapsed_ms
        ):
            raise ReviewRefused(
                "The actual parent did not retain its complete early child spending"
            )
        if finish["verification"] is None:
            if dispatched or returned or spend.tokens or spend.cost_usd:
                raise ReviewRefused("An unbound early refusal cannot conceal paid model work")
            return EarlyReviewRead(None, None, spend, 0, finish["reason"])
        subject = self._subject(prefix, call["arguments"]["candidate_id"])
        subjects = [row for row in trace if row.get("kind") == "review_subject"]
        if len(subjects) != 1 or not same_json_value(
            subjects[0],
            {
                "kind": "review_subject",
                "parent": start.fingerprint,
                "candidate_id": call["arguments"]["candidate_id"],
                "subject": subject.wire(),
            },
        ):
            raise ReviewRefused(
                "The early verifier did not read this exact currently bound subject"
            )
        record = _decode_verdict(finish["verification"])
        if (
            record.package_id != subject.package.id
            or record.package_identity != subject.package.identity
        ):
            raise ReviewRefused("The early verdict refers to a different actual candidate")
        failures = [row for row in trace if row.get("kind") == "model_failed"]
        if len(failures) > 1:
            raise ReviewRefused("The early check has ambiguous actual provider failures")
        if returned:
            usage, retries = (
                Usage(**returned[0]["result"]["usage"]),
                returned[0]["result"]["retries"],
            )
        elif failures and failures[0]["usage"] is not None:
            usage, retries = Usage(**failures[0]["usage"]), failures[0]["retries"]
        else:
            usage, retries = None, failures[0]["retries"] if failures else 0
        expected_tokens = (
            usage.tokens_in + usage.tokens_out
            if usage
            else dispatched[0]["reserved_tokens"]
            if dispatched
            else 0
        )
        expected_cost = (
            usage.cost_usd if usage else dispatched[0]["reserved_cost_usd"] if dispatched else 0
        )
        if (
            spend.tokens != expected_tokens
            or spend.cost_usd != expected_cost
            or type(retries) is not int
            or spend.retries != retries
            or record.usage is not None
            and record.usage != usage
        ):
            raise ReviewRefused("The early check refunded or changed actual paid provider usage")
        if record.releasable:
            if len(dispatched) != 1 or len(returned) != 1:
                raise ReviewRefused("A positive early check needs its actual dispatch and response")
            dispatch, result = dispatched[0], _result(returned[0]["result"])
            judge = (self.verifier.model.provider, self.verifier.model.resolved_model(Tier.JUDGE))
            if (
                judge in self._authors(prefix)
                or (result.provider, result.model) != judge
                or (dispatch["provider"], dispatch["model"]) != judge
                or dispatch["tier"] != Tier.JUDGE.value
                or result.tier is not Tier.JUDGE
                or dispatch["max_tokens"] != self.verifier.max_tokens
                or dispatch["reserved_tokens"]
                != estimate_tokens(
                    (verification_prompt(subject.package).system or "")
                    + verification_prompt(subject.package).user
                )
                + self.verifier.max_tokens
                or dispatch["reserved_tokens"] > policy.max_tokens
                or dispatch["reserved_cost_usd"] > policy.max_cost_usd
                or not same_json_value(
                    dispatch["prompt"], asdict(verification_prompt(subject.package))
                )
                or record != interpret_completed_verification(subject.package, result)
                or spend.tokens != result.usage.tokens_in + result.usage.tokens_out
                or spend.cost_usd != result.usage.cost_usd
                or spend.retries != result.retries
                or spend.failed_children
                or spend.tokens > dispatch["reserved_tokens"]
                or spend.cost_usd > dispatch["reserved_cost_usd"]
                or spend.elapsed_ms > policy.max_ms
                or charged.exhausted() not in (Exhausted.NONE, Exhausted.CHILDREN)
            ):
                raise ReviewRefused(
                    "The early positive differs from its actual independent response"
                )
        return EarlyReviewRead(subject, record, spend, len(dispatched), finish["reason"])
