"""Bounded specialist delegation: the task, the result, and the mandate. P47.

    from nm.domain.delegation import Mandate, Task, Result, Role, ResultStatus

BK-92-AC1 and BK-92-AC2. This module holds the TYPES; `nm.core.delegation` holds
the admission boundary and the one acceptance path that act on them. The split
is the layer rule every PRODUCES contract already keeps -- domain holds the
state, core holds the decisions -- and it is load-bearing here, because the
whole point of the packet is that AGENTS DO NOT DECIDE ADMISSION OR ACCEPTANCE.
The application owns those (autonomy.json `control_boundary.application_owned`),
so the decision code cannot sit on a type an agent constructs.

THE MANDATE IS THE CONTROL, AND IT ONLY EVER SHRINKS
------------------------------------------------------
A child task carries a `Mandate`, and a child's mandate must be a SUBSET of its
parent's -- fewer tools, the same or fewer processors, the same matter, the
same mandate version. `Mandate.expansions_over` reports every way one mandate
exceeds another, by name, so admission refuses the specific expansion rather
than a boolean. A source instruction or a model proposal that would add a tool,
a processor, a matter or a version is exactly such an expansion, and the same
method refuses it at acceptance -- one mechanism, both ends.

    Correct work under the wrong authority is the defect this refuses. A
    child that quietly reaches one more processor than its parent was granted
    has exceeded the mandate however good its findings are.

THREE-PLUS STATES ON THE RESULT, AND THE ESCAPE IS NAMED
----------------------------------------------------------
A result is COMPLETED, PARTIAL, FAILED, CANCELLED, UNAVAILABLE or
NOT_ESTABLISHED. FAILED and PARTIAL are not COMPLETED, and acceptance keeps them
visibly incomplete -- `specialist_failure: visible_incomplete_not_clean`. A
result nobody produced is NOT_ESTABLISHED, which is the §9 third state at the
one place collapsing it would report an unrun specialist as a clean one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from nm.domain.text import refuses_blank_text


class Role(str, Enum):
    """The registered roles. autonomy.json `roles`. LEAD is not optional; the
    two specialists are, and ordinary work uses NEITHER."""

    LEAD = "lead"
    RESEARCH = "research"
    DRAFT_DOCUMENT = "draft_document"


class ResultStatus(str, Enum):
    """What became of a delegated attempt. More than two, and the escape is a
    value: an unrun specialist is NOT_ESTABLISHED, never a quiet COMPLETED."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"
    NOT_ESTABLISHED = "not_established"

    @classmethod
    def not_established(cls) -> "ResultStatus":
        return cls.NOT_ESTABLISHED

    def is_clean(self) -> bool:
        """Only COMPLETED is a clean, whole result. Everything else leaves work
        visibly owed -- the rule `specialist_failure` states."""
        return self is ResultStatus.COMPLETED


#: The budget dimensions a task reserves against, from autonomy.json
#: `initial_profile.budget_dimensions`. Named here so a new dimension is a
#: change to this tuple and not an unlisted default that reserves nothing.
BUDGET_DIMENSIONS = (
    "elapsed_time", "tokens_and_cost", "retrieval_calls", "tool_calls",
    "retries", "concurrency", "delegation_depth",
)


@refuses_blank_text()
@dataclass(frozen=True)
class Mandate:
    """The authority a task carries. A child's is a SUBSET of its parent's.

    `mandate_version` is the version of the authored commission this mandate
    rests on; a result carrying a different version is stale, exactly as a
    correction typed against a moved matter is (P18). Tools and processors are
    frozensets so subset arithmetic is the check, not prose comparison.
    """

    matter_id: str
    mandate_version: int
    tools: frozenset[str] = frozenset()
    processors: frozenset[str] = frozenset()
    max_depth: int = 1
    max_concurrent: int = 2

    def expansions_over(self, ceiling: "Mandate") -> tuple[str, ...]:
        """Every way THIS mandate exceeds `ceiling`, by name. Empty means this
        is a subset -- admissible. The population is what THIS asks for that the
        ceiling does not grant, which is the only direction that can refuse an
        expansion; asked the other way it would confirm the ceiling covers
        itself and never fail (S11)."""
        out: list[str] = []
        if self.matter_id != ceiling.matter_id:
            out.append(f"matter {self.matter_id!r} is not the parent's "
                       f"{ceiling.matter_id!r}")
        if self.mandate_version != ceiling.mandate_version:
            out.append(f"mandate version {self.mandate_version} is not the "
                       f"parent's {ceiling.mandate_version}")
        extra_tools = self.tools - ceiling.tools
        if extra_tools:
            out.append(f"tools {sorted(extra_tools)} are not in the parent's "
                       f"grant")
        extra_proc = self.processors - ceiling.processors
        if extra_proc:
            out.append(f"processors {sorted(extra_proc)} are not in the "
                       f"parent's grant")
        if self.max_depth > ceiling.max_depth:
            out.append(f"depth cap {self.max_depth} exceeds {ceiling.max_depth}")
        if self.max_concurrent > ceiling.max_concurrent:
            out.append(f"concurrency cap {self.max_concurrent} exceeds "
                       f"{ceiling.max_concurrent}")
        return tuple(out)

    def intersect(self, ceiling: "Mandate") -> "Mandate":
        """The largest mandate that is within BOTH. Admission narrows a request
        to this, so a child can never operate on more than it was granted even
        if its request asked for more."""
        return Mandate(
            matter_id=self.matter_id,
            mandate_version=self.mandate_version,
            tools=self.tools & ceiling.tools,
            processors=self.processors & ceiling.processors,
            max_depth=min(self.max_depth, ceiling.max_depth),
            max_concurrent=min(self.max_concurrent, ceiling.max_concurrent))


@refuses_blank_text("objective", "source_snapshot", "idempotency_key",
                    "result_contract_version")
@dataclass(frozen=True)
class Task:
    """One delegated task. autonomy.json `task_fields`.

    Carries its mandate, the source snapshot it was framed against, the epochs
    that fence a stale permission or a cancellation, and the idempotency key its
    caller chose before dispatch -- the same discipline `Operation` keeps, for
    the same reason: a retry that never saw the key cannot be told from new work.
    """

    task_id: str
    parent_task_id: str
    role: Role
    objective: str
    mandate: Mandate
    source_snapshot: str
    idempotency_key: str
    result_contract_version: str
    acceptance_conditions: tuple[str, ...] = ()
    known_gaps: tuple[str, ...] = ()
    requested_budget: dict = field(default_factory=dict)
    deadline: str = ""
    permission_epoch: int = 0
    cancellation_epoch: int = 0
    depth: int = 0
    actor_scope: str = ""

    @property
    def is_root(self) -> bool:
        return self.parent_task_id in ("", "root")


@refuses_blank_text("claim", "source_locator")
@dataclass(frozen=True)
class Finding:
    """A candidate claim a specialist returns. It is PROPOSED, never accepted
    truth: it names what it rests on and stays a candidate until the one
    acceptance path takes it. `subject` is what two findings can disagree ABOUT,
    so a conflict is set arithmetic rather than prose comparison."""

    claim: str
    source_locator: str
    source_version: str = ""
    subject: str = ""
    status: str = "candidate"


@dataclass(frozen=True)
class MandateDelta:
    """A change a specialist PROPOSES to the mandate. It is refused if it would
    expand authority -- no source text or model proposal grants a tool, a
    processor or a matter. Modelled as data so the refusal is deterministic."""

    add_tools: frozenset[str] = frozenset()
    add_processors: frozenset[str] = frozenset()
    change_matter: str = ""

    def expands(self) -> bool:
        return bool(self.add_tools or self.add_processors or self.change_matter)


#: `producer_identity` and `attempt_id` are EXEMPT because their emptiness is a
#: state this type must be able to express: a result carrying neither is exactly
#: how an unauthenticated or forged one presents, `forged_against` reads that,
#: and `accept` refuses it. Making them non-blank at construction would remove
#: the state rather than add a guard -- the forged case would become
#: unrepresentable and the control unprovable. `task_id` and `source_snapshot`
#: stay required: a result that names no task and no snapshot is not a result.
@refuses_blank_text("producer_identity", "attempt_id")
@dataclass(frozen=True)
class Result:
    """What a delegated attempt returned. autonomy.json `result_fields`.

    `producer_identity` and `attempt_id` are what authenticate the result:
    acceptance refuses one whose task id does not match the task it claims, or
    that names no producer -- a forged result cannot be told from a real one
    without them. `budget_used` is a receipt reconciled against the shared
    ledger, never a fresh count.
    """

    task_id: str
    attempt_id: str
    mandate_version: int
    source_snapshot: str
    status: ResultStatus
    producer_identity: str
    permission_epoch: int = 0
    cancellation_epoch: int = 0
    findings: tuple[Finding, ...] = ()
    contrary_material: tuple[Finding, ...] = ()
    open_gaps: tuple[str, ...] = ()
    proposed_deltas: tuple[MandateDelta, ...] = ()
    stop_reason: str = ""
    budget_used: dict = field(default_factory=dict)

    @property
    def forged_against(self) -> str:
        """Non-empty when the result cannot be authenticated at all -- no
        producer or no attempt id. The task-id match is checked at acceptance,
        where the task is in hand."""
        if not self.producer_identity.strip():
            return "the result names no producer identity"
        if not self.attempt_id.strip():
            return "the result carries no attempt id"
        return ""
