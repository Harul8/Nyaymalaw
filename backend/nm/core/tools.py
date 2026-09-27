"""Declared tools over existing owners. A receipt is not an approval to advise.

Every invocation is scoped by its trusted context, not by model-supplied actor
or matter IDs. Checks surround the actual handler, including terminal proposals.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nm.domain.file_mutation import FileMutation

from nm.domain.authority import Act
from nm.domain.budget import Budget
from nm.domain.loop import LoopIdentity, digest
from nm.ports.evidence import Coverage, EvidenceNeed, EvidencePort
from nm.ports.model import ToolCall, ToolDefinition, require_schema
from nm.ports.store import StorePort


class ToolKind(str, Enum):
    SOURCE = "source"
    MATTER = "matter"
    COMPUTATION = "computation"
    CONTROL = "control"


class Availability(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class Assessment(str, Enum):
    SUPPORTED = "supported"
    BLOCKED = "blocked"
    NOT_ASSESSED = "not_assessed"


class ToolOutcome(str, Enum):
    RESULTS = "results"
    NO_RESULTS = "no_results"
    FAILED = "failed"


class Effect(str, Enum):
    CONTINUE = "continue"
    QUESTION = "question_proposal"
    ANSWER = "answer_proposal"
    CONVERSATION = "conversation_proposal"


class OfferRole(str, Enum):
    OPTIONAL = "optional"
    INITIAL = "initial"
    SCHEMA_LOADER = "schema_loader"


@dataclass(frozen=True)
class ToolEnvelope:
    tool: str
    version: str
    kind: ToolKind
    outcome: ToolOutcome
    availability: Availability
    assessment: Assessment
    receipt: dict
    data: dict
    reason: str = ""
    effect: Effect = Effect.CONTINUE

    def __post_init__(self) -> None:
        if not self.tool.strip() or not self.version.strip():
            raise ValueError("a tool result records its named implementation version")
        for value, cls in ((self.kind, ToolKind), (self.outcome, ToolOutcome),
                           (self.availability, Availability),
                           (self.assessment, Assessment), (self.effect, Effect)):
            if not isinstance(value, cls):
                raise ValueError("unknown tool receipt state")
        required = {
            ToolKind.SOURCE: {"index", "locators", "source_version"},
            ToolKind.MATTER: {"matter_id", "matter_version", "snapshot"},
            ToolKind.COMPUTATION: {"inputs", "method", "input_receipts"},
            ToolKind.CONTROL: {"operation", "turn_id"},
        }[self.kind]
        if not required <= self.receipt.keys():
            raise ValueError("the tool receipt is incomplete for its own kind")
        if self.kind is ToolKind.SOURCE:
            if not self.receipt["index"] or not isinstance(self.receipt["locators"], list):
                raise ValueError("source reads name an index even when they find nothing")
            if self.outcome is ToolOutcome.RESULTS and (
                    not self.receipt["locators"] or not self.receipt["source_version"]):
                raise ValueError("source results carry exact locators and source identity")
        if (self.availability is not Availability.AVAILABLE
                or self.assessment is not Assessment.SUPPORTED
                or self.outcome is ToolOutcome.FAILED) and not self.reason.strip():
            raise ValueError("incomplete, unchecked and failed results explain their limit")
        if self.outcome is ToolOutcome.NO_RESULTS and self.data:
            raise ValueError("no-results may not carry purported findings")
        if self.availability is Availability.UNAVAILABLE and (
                self.assessment is Assessment.SUPPORTED or self.data):
            raise ValueError("an unavailable read cannot assert a supported result")
        self.wire()  # Non-serializable/non-finite payloads are programming defects.

    def wire(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True,
                          allow_nan=False, default=_wire_value)

    @property
    def fingerprint(self) -> str:
        return digest(json.loads(self.wire()))


def _wire_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, frozenset):
        return sorted(value)
    raise TypeError(f"unsupported tool value: {type(value).__name__}")


@dataclass(frozen=True)
class ToolContext:
    identity: LoopIdentity
    observed_version: int | None = None
    original_message: str = ""
    delegation: DelegationGrant | None = None
    cancelled: Callable[[], bool] = lambda: False
    issue_ids: tuple[str, ...] = ()
    """Identity comes from authenticated admission, never tool arguments."""

    @property
    def current_version(self):
        return (self.identity.matter_version if self.observed_version is None
                else self.observed_version)


@dataclass(frozen=True)
class Boundary:
    allowed: bool
    reason: str

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool or not self.reason.strip():
            raise ValueError("tool boundaries are explicit judgments with reasons")


class ToolRefused(Exception):
    def __init__(self, message: str, *, delegated: DelegatedToolResult | None = None):
        super().__init__(message)
        self.delegated = delegated


@dataclass(frozen=True)
class PreparedToolResult:
    envelope: ToolEnvelope
    mutation: FileMutation
    """A checked proposal; only the journal's atomic commit may apply it."""


@dataclass(frozen=True)
class DelegationPolicy:
    """Trusted per-child ceilings, never a model-authored new allowance."""

    max_steps: int
    max_tokens: int
    max_cost_usd: float
    max_ms: int

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in (
                self.max_steps, self.max_tokens, self.max_ms)):
            raise ValueError("delegated work has positive bounded steps, tokens and time")
        if (type(self.max_cost_usd) not in (int, float)
                or not math.isfinite(self.max_cost_usd) or self.max_cost_usd <= 0):
            raise ValueError("delegated work has a positive finite cost ceiling")


@dataclass(frozen=True)
class DelegationGrant:
    """A reservation against the parent's exact current ledger."""

    budget: Budget
    policy: DelegationPolicy

    def as_dict(self):
        return {"budget": self.budget.as_dict(), "policy": asdict(self.policy)}


@dataclass(frozen=True)
class DelegatedToolResult:
    envelope: ToolEnvelope
    budget: Budget
    steps_used: int
    transcript: tuple[dict, ...]
    """Private child work; parent journals it, and only parent may write."""

    def __post_init__(self):
        if (not isinstance(self.envelope, ToolEnvelope) or not isinstance(self.budget, Budget)
                or type(self.steps_used) is not int or self.steps_used < 0
                or not isinstance(self.transcript, tuple)
                or any(not isinstance(row, dict) for row in self.transcript)):
            raise ValueError("delegated work returns typed spend, steps and its private transcript")
        json.dumps(self.transcript, allow_nan=False)


Handler = Callable[[dict, ToolContext], ToolEnvelope | PreparedToolResult | DelegatedToolResult]
Before = Callable[[str, dict, ToolContext], Boundary]
After = Callable[[ToolEnvelope, ToolContext], Boundary]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    kind: ToolKind
    version: str
    parallel_safe: bool
    tests: tuple[str, ...]
    handler: Handler
    required_act: Act = Act.READ
    delegation: DelegationPolicy | None = None
    offer_role: OfferRole = OfferRole.OPTIONAL

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.tests:
            raise ValueError("every tool has a version and declared rejecting controls")
        if type(self.parallel_safe) is not bool or not isinstance(self.kind, ToolKind):
            raise ValueError("tool safety and kind are explicit declarations")
        if not isinstance(self.required_act, Act):
            raise ValueError("each tool declares its actual operation authority")
        if not isinstance(self.offer_role, OfferRole):
            raise ValueError("tool offering is explicit trusted registry metadata")
        if self.offer_role is OfferRole.SCHEMA_LOADER and (
                self.kind is not ToolKind.CONTROL or self.required_act is not Act.READ
                or self.delegation is not None):
            raise ValueError("a schema loader is local read-only control metadata")
        if self.delegation is not None and (
                not isinstance(self.delegation, DelegationPolicy) or self.parallel_safe
                or self.required_act is not Act.READ):
            raise ValueError("a delegated tool is sequential read-only work with a trusted ceiling")


class ToolRegistry:
    def __init__(self, tools: tuple[RegisteredTool, ...], *, before: Before, after: After,
                 version_context: dict[str, str] | None = None):
        self._tools = {tool.definition.name: replace(
            tool, definition=deepcopy(tool.definition)) for tool in tools}
        if not tools or len(self._tools) != len(tools):
            raise ValueError("a tool registry is nonempty and each name has one owner")
        self._before = before
        self._after = after
        self._versions = dict(version_context or {})
        if any(not key.strip() or not value.strip() for key, value in self._versions.items()):
            raise ValueError("tool environment versions are explicit, never blank fallbacks")

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(deepcopy(row.definition) for row in self._tools.values())

    @property
    def version(self) -> str:
        return digest({"environment": self._versions, "tools": [{"name": row.definition.name,
                        "description": row.definition.description,
                        "parameters": row.definition.parameters, "version": row.version,
                        "kind": row.kind.value, "parallel_safe": row.parallel_safe,
                        "required_act": row.required_act.value,
                        "offer_role": row.offer_role.value,
                        "delegation": asdict(row.delegation) if row.delegation else None,
                        "tests": row.tests} for row in self._tools.values()]})

    def invoke(self, call: ToolCall, context: ToolContext
               ) -> ToolEnvelope | PreparedToolResult | DelegatedToolResult:
        admitted_version = self.version
        if call.name not in self._tools:
            raise ToolRefused("the requested tool is not registered")
        row = self._tools[call.name]
        require_schema(call.arguments, row.definition.parameters)
        boundary = self._before(call.name, call.arguments, context)
        if not boundary.allowed:
            raise ToolRefused(boundary.reason)
        if self.version != admitted_version:
            raise ToolRefused("the tool contract changed during its permission check")
        result = row.handler(call.arguments, context)
        receipt = (result.envelope if isinstance(result, (PreparedToolResult, DelegatedToolResult))
                   else result)
        if (not isinstance(receipt, ToolEnvelope) or receipt.tool != call.name
                or receipt.kind != row.kind or receipt.version != row.version):
            raise ValueError("a handler returned a receipt for a different tool contract")
        if isinstance(result, PreparedToolResult):
            from nm.domain.file_mutation import FileMutation

            if (not isinstance(result.mutation, FileMutation) or row.parallel_safe
                    or row.required_act is not Act.RECORD
                    or receipt.kind is not ToolKind.MATTER
                    or result.mutation.advocate_id != context.identity.advocate_id
                    or result.mutation.before.id != context.identity.matter_id
                    or result.mutation.before.version != context.current_version):
                raise ValueError("a write proposal is not bound to this checked transaction")
        if isinstance(result, DelegatedToolResult) != (row.delegation is not None):
            raise ValueError("delegated spend must cross its registered parent accounting seam")
        if isinstance(result, DelegatedToolResult) and (
                context.delegation is None or receipt.effect is not Effect.CONTINUE):
            raise ValueError("a child cannot publish or execute without a parent reservation")
        boundary = self._after(receipt, context)
        if not boundary.allowed:
            raise ToolRefused(boundary.reason, delegated=(
                result if isinstance(result, DelegatedToolResult) else None))
        if self.version != admitted_version:
            raise ToolRefused("the tool contract changed while its result was checked",
                              delegated=(result if isinstance(result, DelegatedToolResult)
                                         else None))
        return result

    def authority_for(self, name: str) -> Act:
        if name not in self._tools:
            raise ToolRefused("the requested tool is not registered")
        return self._tools[name].required_act

    def offer_state(self):
        from nm.core.tool_offers import ToolOfferState

        inventory = tuple(sorted(self.definitions, key=lambda row: row.name))
        loaders = tuple(sorted(row.definition.name for row in self._tools.values()
                               if row.offer_role is OfferRole.SCHEMA_LOADER))
        initial = tuple(sorted(row.definition.name for row in self._tools.values()
                               if row.offer_role is not OfferRole.OPTIONAL or not loaders))
        return ToolOfferState(inventory, self.version, initial, loaders)

    def delegation_for(self, name: str) -> DelegationPolicy | None:
        if name not in self._tools:
            raise ToolRefused("the requested tool is not registered")
        return self._tools[name].delegation

    def reading_tools(self) -> tuple[RegisteredTool, ...]:
        """A capability is inherited by contract, not by its optimistic name."""
        return tuple(row for row in self._tools.values()
                     if row.required_act is Act.READ and row.parallel_safe
                     and row.delegation is None and row.kind in (
                         ToolKind.SOURCE, ToolKind.MATTER, ToolKind.COMPUTATION))

    def extend(self, tools: tuple[RegisteredTool, ...], *, versions: dict[str, str] | None = None):
        """Add capabilities without changing their before/after authority owner."""
        additions = dict(versions or {})
        if set(additions) & self._versions.keys():
            raise ValueError("a registry environment version has exactly one owner")
        return ToolRegistry((*self._tools.values(), *tools), before=self._before,
                            after=self._after, version_context={**self._versions, **additions})


def object_schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


_STRING = {"type": "string"}
_SOURCE_WINDOW = object_schema({"locator": _STRING, "quote": _STRING})
_STRING_LIST = {"type": "array", "items": _STRING}
CLAIM_SHAPE = object_schema({
    "id": _STRING, "text": _STRING,
    "sources": {"type": "array", "items": _SOURCE_WINDOW},
    "premise_ids": _STRING_LIST,
    "contrary": {"type": "array", "items": _SOURCE_WINDOW},
    "depends_on": _STRING_LIST,
})
ANSWER_PROPOSAL_SHAPE = object_schema({"claims": {"type": "array", "items": CLAIM_SHAPE}})


def foundation_tools(store: StorePort, evidence: EvidencePort, *, manifest,
                     source_version: str, before: Before, after: After) -> ToolRegistry:
    """Existing file/source owners wrapped for controlled foundation evaluation.

    No tool establishes facts, performs external actions or releases advice.
    The supplied policies remain mandatory even in synthetic mode.
    """
    version = "foundation-v2"

    def matter_read(_args, context):
        matter = store.load(context.identity.matter_id)
        if matter is None or matter.advocate_id != context.identity.advocate_id:
            raise ToolRefused("the matter is not available to this actor")
        if matter.version != context.current_version:
            raise ToolRefused("the recorded file changed before this read")
        data = {"title": matter.title, "facts": [asdict(f) for f in matter.facts],
                "disputes": [asdict(t) for t in matter.threads]}
        normalized = json.loads(json.dumps(data, default=_wire_value, allow_nan=False))
        return ToolEnvelope("read_matter", version, ToolKind.MATTER, ToolOutcome.RESULTS,
                            Availability.AVAILABLE, Assessment.SUPPORTED,
                            {"matter_id": matter.id, "matter_version": matter.version,
                             "snapshot": digest(normalized)}, normalized)

    def identify(args, _context):
        resolution = manifest.identify(args["name"], date.fromisoformat(args["as_of"]))
        data = ({"act": resolution.entry.act_name, "basis": resolution.basis.value}
                if resolution.entry is not None else {})
        return ToolEnvelope("identify_act", version, ToolKind.SOURCE,
                            ToolOutcome.RESULTS if data else ToolOutcome.NO_RESULTS,
                            Availability.AVAILABLE, Assessment.SUPPORTED,
                            {"index": "exact Act manifest", "source_version": source_version,
                             "locators": [resolution.entry.act_name] if data else []}, data)

    def source_result(name, result):
        from nm.core.tool_sources import source_envelope

        if result.coverage is Coverage.NOT_ASSESSED:
            return source_envelope(
                name, version, "; ".join(result.searched_stores) or "evidence port",
                source_version, (), {}, available=False,
                primary_reads=(result,),
                reason=result.missing or "The source read could not be assessed.")
        data = {"coverage": result.coverage.value,
                "assumption": result.assumption, "search_note": result.search_note}
        available = result.coverage is Coverage.ANSWERED
        supported = bool(result.findings) and len(result.usable) == len(result.findings)
        return source_envelope(
            name, version, "; ".join(result.searched_stores) or "evidence port",
            source_version, (), data if result.findings else {}, partial=not available,
            assessed=supported, primary_reads=(result,),
            reason="" if available and supported else
            result.missing or "Retrieved material is incomplete or not yet usable.")

    def provision(args, _context):
        return source_result("read_provision", evidence.read_provision(
            args["act"], args["section"], date.fromisoformat(args["as_of"])))

    def authority(args, _context):
        return source_result("search_authority", evidence.fetch(EvidenceNeed(
            question=args["query"], governing_date=date.fromisoformat(args["as_of"]),
            jurisdiction=args["jurisdiction"], want_authority=True)))

    def terminal(name, args, context):
        return ToolEnvelope(name, version, ToolKind.CONTROL, ToolOutcome.RESULTS,
                            Availability.AVAILABLE, Assessment.NOT_ASSESSED,
                            {"operation": name, "turn_id": context.identity.turn_id}, args,
                            "This is a model proposal; release checks have not run.",
                            Effect.QUESTION if name == "ask_advocate" else Effect.ANSWER)

    rows = (
        ("read_matter", "Read the recorded file, facts and distinct disputes.", {},
         ToolKind.MATTER, matter_read),
        ("identify_act", "Identify an Act exactly; this never ranks a guessed statute.",
         {"name": _STRING, "as_of": _STRING}, ToolKind.SOURCE, identify),
        ("read_provision", "Read a specific provision on the stated governing date.",
         {"act": _STRING, "section": _STRING, "as_of": _STRING}, ToolKind.SOURCE, provision),
        ("search_authority", "Search relevant authority; ranking is not exact identity.",
         {"query": _STRING, "as_of": _STRING, "jurisdiction": _STRING},
         ToolKind.SOURCE, authority),
        ("ask_advocate", "Propose the necessary question; checks still precede delivery.",
         {"question": _STRING}, ToolKind.CONTROL,
         lambda args, ctx: terminal("ask_advocate", args, ctx)),
        ("submit_answer", "Propose exact response paragraphs as evidence packages. Each text "
         "is final wording, with exact retrieved quotes, recorded premise IDs, contrary "
         "material and dependencies. Use empty arrays only when genuinely inapplicable. "
         "No unreferenced answer text is delivered; this does not release advice.",
         ANSWER_PROPOSAL_SHAPE["properties"], ToolKind.CONTROL,
         lambda args, ctx: terminal("submit_answer", args, ctx)),
    )
    from nm.core.conversational_proposal import conversational_tool

    tools = tuple(RegisteredTool(
        ToolDefinition(name, description, object_schema(properties)), kind, version, True,
        ("test_each_foundation_tool_refuses_before_its_handler",), handler,
        offer_role=(OfferRole.INITIAL if name == "read_matter" or kind is ToolKind.CONTROL
                    else OfferRole.OPTIONAL))
        for name, description, properties, kind, handler in rows)
    return ToolRegistry((*tools, conversational_tool()), before=before, after=after,
        version_context={"corpus": source_version})
