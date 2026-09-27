"""Closed conversational producers for private legal and product proposals.

These are not advocate instructions, settled law, factual confirmation, advice
acceptance or action authority. Existing primary-read and observation owners
bind support. The immutable loop transaction preserves every prior projection;
the only withdrawal here makes an exact inferred premise unestablished.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import date

from nm.advise.decision_contracts import DecidedBy, Decision, _question, from_stored, merge
from nm.legal_brain import premise
from nm.legal_brain.brain_release import ReviewRefused
from nm.legal_brain.evidence_port import Finding
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.reviewed_limitation_selection import _owned_population, _sources
from nm.legal_brain.source_writes import _parent
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    PreparedToolResult,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
    object_schema,
)
from nm.shared.clock_contracts import today as forum_today
from nm.shared.json_values import same_json_value
from nm.shared.model_port import SchemaViolation, require_schema
from nm.work_the_file import dependency
from nm.work_the_file.file_mutation_contracts import FileMutation, neutral
from nm.work_the_file.original_instruction import InstructionRefused, read_original_instruction

VERSION = "private-source-bound-file-proposals-v1"
SourceCurrent = Callable[[Finding, str], bool]
READ = "read_private_file_inputs"
PREMISE = "propose_legal_premise"
DECISION = "propose_product_decision"
WITHDRAW = "withdraw_private_premise"
_TEXT = {"type": "string", "minLength": 1}
_ID = {"type": "string", "minLength": 1}
_HASH = {"type": "string", "minLength": 64}
_NULL_HASH = {**_HASH, "type": ["string", "null"]}
_CLAUSE = object_schema(
    {
        "source_id": _HASH,
        "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 1},
    }
)
_SUPPORT = {
    "source_clauses": {"type": "array", "minItems": 1, "maxItems": 20, "items": _CLAUSE},
    "observation_ids": {"type": "array", "minItems": 1, "maxItems": 20, "items": _HASH},
    "alternatives": {"type": "array", "maxItems": 20, "items": _TEXT},
    "replaces_identity": _NULL_HASH,
}
SCHEMAS = {
    READ: object_schema({"thread_id": _ID}),
    PREMISE: object_schema(
        {
            "thread_id": _ID,
            "kind": {"type": "string", "enum": [row.value for row in premise.Kind]},
            "statement": _TEXT,
            "reason": _TEXT,
            **_SUPPORT,
        }
    ),
    DECISION: object_schema({"thread_id": _ID, "what": _TEXT, "because": _TEXT, **_SUPPORT}),
    WITHDRAW: object_schema(
        {
            "thread_id": _ID,
            "kind": {"type": "string", "enum": [row.value for row in premise.Kind]},
            "target_identity": _HASH,
            "correction_quote": _TEXT,
        }
    ),
}
_CONTROLS = (
    "test_real_loop_records_private_candidates_without_promoting_their_origin",
    "test_private_producers_reject_changed_sources_scope_or_projection",
)


def _fingerprint(value):
    return digest(neutral(asdict(value)))


def _checked_arguments(operation, args):
    # maxLength is outside this model port's executable schema intersection.
    # Enforce bounded exact text here, also on constructor replay.
    require_schema(args, SCHEMAS[operation])
    if (
        not args["thread_id"].strip()
        or len(args["thread_id"]) > 100
        or any(
            not value.strip() or len(value) > 16000
            for key, value in args.items()
            if key in {"statement", "reason", "what", "because", "correction_quote"}
        )
        or any(not value.strip() or len(value) > 16000 for value in args.get("alternatives", []))
    ):
        raise ToolRefused("Private proposal words and identities must remain bounded and nonblank.")


def _decisions(thread):
    rows = from_stored(thread.decisions)
    if (
        not same_json_value(
            neutral([asdict(row) for row in rows]),
            neutral(
                [asdict(row) if isinstance(row, Decision) else row for row in thread.decisions]
            ),
        )
        or len({_question(row.what) for row in rows}) != len(rows)
        or any(row.thread and row.thread != thread.id for row in rows)
    ):
        raise ToolRefused("The complete standing decision population is unreadable or ambiguous.")
    return rows


def _scope(parent, thread_id):
    start = parent.events[0].payload
    if start.get("scope_identity") == digest({"requested_issue_ids": []}):
        return
    selected = start.get("context", {}).get("brief", {}).get("selected_issue_ids")
    if not isinstance(selected, list) or thread_id not in selected:
        raise ToolRefused(
            "The proposal cannot transfer work outside its original admitted disputes."
        )


def _support(matter, thread, args, *, source_generation, source_current):
    _, observations, owned = _owned_population(matter, thread)
    choices = {row.id: row for row in _sources(matter, source_generation, source_current)}
    observed = {row.identity: row for row in observations}
    clauses, events = [], []
    for raw in args["source_clauses"]:
        choice = choices.get(raw["source_id"])
        start, end = raw["start"], raw["end"]
        if (
            choice is None
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(choice.source.finding.span)
            or not choice.source.finding.span[start:end].strip()
        ):
            raise ToolRefused("A private proposal needs an exact current recorded primary clause.")
        value = {
            "source": choice.as_dict(),
            "start": start,
            "end": end,
            "quote": choice.source.finding.span[start:end],
        }
        if value in clauses:
            raise ToolRefused("Repeated primary clauses add no support.")
        clauses.append(value)
    for ident in args["observation_ids"]:
        if ident not in observed or ident in {row["identity"] for row in events}:
            raise ToolRefused("A proposal needs unique exact current observations on this dispute.")
        events.append(observed[ident].as_dict())
    if len(set(args["alternatives"])) != len(args["alternatives"]) or any(
        not value.strip() for value in args["alternatives"]
    ):
        raise ToolRefused("Alternatives must be distinct nonblank private candidates.")
    return owned, {
        "source_generation": source_generation,
        "source_clauses": clauses,
        "observations": events,
    }


def _derive(matter, *, operation, turn_id, reference, args, source_generation, source_current):
    _checked_arguments(operation, args)
    parent = _parent(matter, turn_id, matter.advocate_id)
    call = parent.events[-1].payload["call"]
    if call["name"] != operation or not same_json_value(call["arguments"], args):
        raise ToolRefused("A private mutation differs from its actual reserved tool invocation.")
    original = read_original_instruction(parent)
    if original.state != "recorded":
        raise ToolRefused(
            "A private mutation needs its complete authenticated supplied instruction."
        )
    thread = matter.thread(args["thread_id"])
    if thread is None:
        raise ToolRefused("The exact owned dispute is unavailable.")
    _scope(parent, thread.id)
    if type(reference) is not date:
        raise ToolRefused("A private mutation uses the trusted current calendar reference.")
    detail = {
        "thread_id": thread.id,
        "operation": operation,
        "instruction_identity": original.text_identity,
        "instruction_provenance": original.provenance,
        "source_generation": source_generation,
        "semantic_assessment": "not_assessed",
        "legal_truth_established": False,
        "factual_truth_established": False,
        "advocate_instruction_established": False,
        "authorises_action": False,
        "released": False,
        "client_ready": False,
    }
    if operation == WITHDRAW:
        _, _, owned = _owned_population(matter, thread)
        old = owned.of(premise.Kind(args["kind"]))
        quote = args["correction_quote"]
        if (
            old is None
            or old.basis is not premise.Basis.INFERRED
            or old.reviewed_by
            or old.reviewed_at
            or args["kind"] in thread.premises_stated
            or _fingerprint(old) != args["target_identity"]
            or not quote.strip()
            or quote not in original.text
        ):
            raise ToolRefused(
                "Withdraw only the exact current private inferred premise using supplied words."
            )
        tombstone = replace(
            old,
            basis=premise.Basis.UNESTABLISHED,
            inferred_from="This product's private candidate was withdrawn; supplied support "
            "(not an established advocate instruction): " + quote,
            reviewed_by="",
            reviewed_at="",
        )
        changed = replace(
            thread,
            premises=tuple(
                tombstone.as_dict() if row.kind is old.kind else row.as_dict()
                for row in owned.items
            ),
        )
        detail.update(
            previous=old.as_dict(),
            current=tombstone.as_dict(),
            previous_identity=_fingerprint(old),
            current_identity=_fingerprint(tombstone),
            correction_quote=quote,
            original_account=original.text,
            tombstone=True,
            source_clauses=[],
            observations=[],
        )
    else:
        owned, support = _support(
            matter, thread, args, source_generation=source_generation, source_current=source_current
        )
        detail.update(support)
        if operation == PREMISE:
            kind = premise.Kind(args["kind"])
            old = owned.of(kind)
            if (
                kind.value in thread.premises_stated
                or old is not None
                and (
                    old.basis not in (premise.Basis.INFERRED, premise.Basis.UNESTABLISHED)
                    or old.reviewed_by
                    or old.reviewed_at
                )
                or args["replaces_identity"] != (_fingerprint(old) if old else None)
            ):
                raise ToolRefused(
                    "A private premise cannot overwrite advocate or attributed legal positions."
                )
            source = ";".join(
                f"primary:{row['source']['id']}:{row['start']}:{row['end']}"
                for row in support["source_clauses"]
            )
            source += ";" + ";".join(
                "observation:" + row["identity"] for row in support["observations"]
            )
            new = premise.Premise(
                kind,
                args["statement"],
                premise.Basis.INFERRED,
                source=source,
                inferred_from=args["reason"],
                alternatives=tuple(args["alternatives"]),
            )
            rows = tuple(new if row.kind is kind else row for row in owned.items)
            if old is None:
                rows = (*rows, new)
            changed = replace(thread, premises=tuple(row.as_dict() for row in rows))
            detail.update(
                previous=old.as_dict() if old else None,
                current=new.as_dict(),
                previous_identity=_fingerprint(old) if old else None,
                current_identity=_fingerprint(new),
                inferred_only=True,
            )
        else:
            standing = _decisions(thread)
            matching = [row for row in standing if _question(row.what) == _question(args["what"])]
            old = matching[0] if matching else None
            if (
                old is not None
                and old.by is not DecidedBy.PRODUCT
                or args["replaces_identity"] != (_fingerprint(old) if old else None)
            ):
                raise ToolRefused(
                    "A product proposal cannot override an advocate or unknown-origin decision."
                )
            new = Decision(
                args["what"],
                args["because"],
                turn_id,
                thread.id,
                DecidedBy.PRODUCT,
                tuple(args["alternatives"]),
            )
            changed = replace(thread, decisions=merge(standing, (new,)))
            detail.update(
                previous=neutral(asdict(old)) if old else None,
                current=neutral(asdict(new)),
                previous_identity=_fingerprint(old) if old else None,
                current_identity=_fingerprint(new),
                product_proposal_only=True,
            )
    changed = replace(
        changed, assessed=tuple(value for value in thread.assessed if value != "review_current")
    )
    if neutral(asdict(changed)) == neutral(asdict(thread)):
        raise ToolRefused(
            "This exact private candidate is already recorded; no duplicate was prepared."
        )
    after = matter.with_thread(changed)
    ledger, _, _ = dependency.sync_inputs(
        dependency.Ledger.from_stored(matter.dependencies), matter
    )
    ledger, affected, _ = dependency.sync_inputs(
        ledger,
        after,
        reason="The exact source-bound private file position changed.",
        at=reference.isoformat(),
        by=matter.advocate_id,
    )
    after = replace(
        after,
        version=matter.version,
        dependencies=ledger.as_dict(),
        threads=tuple(after.thread(row.id) for row in matter.threads),
    )
    detail["stale_nodes"] = list(affected)
    return after, detail


@dataclass(frozen=True)
class PrivateFileMutation(FileMutation):
    operation: str
    turn_id: str
    reference: date
    proposed: dict
    source_generation: str
    source_current: SourceCurrent

    def __post_init__(self):
        object.__setattr__(self, "proposed", deepcopy(self.proposed))
        if (
            self.operation not in (PREMISE, DECISION, WITHDRAW)
            or not isinstance(self.source_generation, str)
            or not self.source_generation.strip()
            or not callable(self.source_current)
        ):
            raise ValueError(
                "Private mutations use their closed trusted operation and source owner."
            )
        super().__post_init__()

    def _validate_projection(self):
        expected, _ = _derive(
            self.before,
            operation=self.operation,
            turn_id=self.turn_id,
            reference=self.reference,
            args=self.proposed,
            source_generation=self.source_generation,
            source_current=self.source_current,
        )
        if not same_json_value(neutral(asdict(expected)), neutral(asdict(self.after))):
            raise ValueError(
                "The private projection differs from its actual source and typed owners."
            )
        super()._validate_projection()

    def _thread_projection(self, before, after, facts):
        if before.id == self.proposed["thread_id"]:
            after = replace(after, premises=before.premises, decisions=before.decisions)
        super()._thread_projection(before, after, facts)

    def _digest(self):
        return digest(
            {
                "base": super()._digest(),
                "operation": self.operation,
                "turn": self.turn_id,
                "reference": self.reference.isoformat(),
                "proposed": self.proposed,
                "source_generation": self.source_generation,
            }
        )


def private_file_tools(
    store, *, source_generation: str, source_current: SourceCurrent, today=forum_today
) -> tuple[RegisteredTool, ...]:
    """No provider call, new allowance, automatic learning or human approval field."""
    if (
        not isinstance(source_generation, str)
        or not source_generation.strip()
        or not callable(source_current)
        or not callable(today)
    ):
        raise ValueError("Private file tools need the actual source generation and clock owners.")

    def current(args, context):
        matter = store.load(context.identity.matter_id)
        if (
            matter is None
            or matter.advocate_id != context.identity.advocate_id
            or matter.version != context.current_version
            or context.issue_ids
            and args["thread_id"] not in context.issue_ids
        ):
            raise ToolRefused("The private tool needs the exact current owned admitted dispute.")
        parent = _parent(matter, context.identity.turn_id, context.identity.advocate_id)
        original = read_original_instruction(parent)
        if (
            parent.identity != context.identity
            or original.state != "recorded"
            or original.text != context.original_message
        ):
            raise ToolRefused(
                "The actual supplied instruction changed or lacks authenticated provenance."
            )
        thread = matter.thread(args["thread_id"])
        if thread is None:
            raise ToolRefused("No such exact dispute is on this file.")
        _scope(parent, thread.id)
        return matter, thread

    def run(name, args, context):
        try:
            _checked_arguments(name, args)
            matter, thread = current(args, context)
            if name == READ:
                _, observations, owned = _owned_population(matter, thread)
                data = {
                    "thread_id": thread.id,
                    "source_generation": source_generation,
                    "sources": [
                        row.as_dict() for row in _sources(matter, source_generation, source_current)
                    ],
                    "observations": [row.as_dict() for row in observations],
                    "premises": [
                        {"identity": _fingerprint(row), "value": row.as_dict()}
                        for row in owned.items
                    ],
                    "decisions": [
                        {"identity": _fingerprint(row), "value": neutral(asdict(row))}
                        for row in _decisions(thread)
                    ],
                    "legal_truth_established": False,
                    "factual_truth_established": False,
                    "authorises_action": False,
                    "released": False,
                    "client_ready": False,
                }
                return ToolEnvelope(
                    name,
                    VERSION,
                    ToolKind.MATTER,
                    ToolOutcome.RESULTS,
                    Availability.AVAILABLE,
                    Assessment.NOT_ASSESSED,
                    {
                        "matter_id": matter.id,
                        "matter_version": matter.version,
                        "snapshot": digest(data),
                        "source_generation": source_generation,
                    },
                    data,
                    "Exact source/file identities only; legal meaning and private choices "
                    "remain unassessed.",
                )
            reference = today()
            after, data = _derive(
                matter,
                operation=name,
                turn_id=context.identity.turn_id,
                reference=reference,
                args=args,
                source_generation=source_generation,
                source_current=source_current,
            )
            mutation = PrivateFileMutation(
                matter,
                after,
                matter.advocate_id,
                name,
                context.identity.turn_id,
                reference,
                args,
                source_generation,
                source_current,
            )
            envelope = ToolEnvelope(
                name,
                VERSION,
                ToolKind.MATTER,
                ToolOutcome.RESULTS,
                Availability.AVAILABLE,
                Assessment.NOT_ASSESSED,
                {
                    "matter_id": matter.id,
                    "matter_version": matter.version,
                    "snapshot": mutation.identity,
                    "source_generation": source_generation,
                },
                data,
                "Private product proposal only; not settled law, advocate acceptance "
                "or action authority.",
            )
            return PreparedToolResult(envelope, mutation)
        except (
            ReviewRefused,
            InstructionRefused,
            SchemaViolation,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ToolRefused(
                "The private proposal lacks its exact current source/typed owner."
            ) from exc

    from nm.work_the_file.tool_propose_legal_premise import build_tool as propose_legal_premise
    from nm.work_the_file.tool_propose_product_decision import (
        build_tool as propose_product_decision,
    )
    from nm.work_the_file.tool_read_private_file_inputs import (
        build_tool as read_private_file_inputs,
    )
    from nm.work_the_file.tool_withdraw_private_premise import (
        build_tool as withdraw_private_premise,
    )

    return (
        read_private_file_inputs(run=run),
        propose_legal_premise(run=run),
        propose_product_decision(run=run),
        withdraw_private_premise(run=run),
    )
