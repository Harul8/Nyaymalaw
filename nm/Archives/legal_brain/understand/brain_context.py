"""Checked-file context generations, never a model summary replacing the file.

The stored transcript is append-only. Budgeting, clearing and compaction operate
on a separately identified working projection. Model prose in a handover is not
trusted: the conservative fallback admits only a cited verbatim file span. A
paraphrase requires the independent semantic verifier, outside this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date
from enum import Enum
from typing import Mapping

from nm.advise.turn_receipt_contracts import fingerprint
from nm.Archives.legal_brain.common.principles_port import PrinciplesSnapshot
from nm.Archives.legal_brain.communicate.register_contracts import PEER
from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopMode
from nm.Archives.legal_brain.orchestrate.tool_offers import OfferRefused, ToolOfferState
from nm.Archives.legal_brain.orchestrate.tools import TERMINAL_CONTRACT, TERMINAL_REASONS
from nm.Archives.legal_brain.reason import requirements
from nm.shared.clock_contracts import today as forum_today
from nm.shared.model_port import (
    ToolCall,
    ToolDefinition,
    ToolMessage,
    estimate_tokens,
    validate_tool_history,
)
from nm.work_the_file.matter_contracts import Matter


class ContextRefused(RuntimeError):
    """A named context failure; never a partial brief that looks complete."""

    def __init__(self, code: str, reason: str):
        self.code = code
        self.reason = reason
        super().__init__(reason)


def require_recorded_source(record, matter: Matter, *, as_of: date | None = None):
    """Reuse the exact checked source, including this loop's atomic writes.

    Journal-only versions may advance. An unrelated correction cannot inherit
    an old proposal, and a loop's own recorded mutation is not a stale input.
    """
    identity = record.identity
    if matter.id != identity.matter_id or matter.advocate_id != identity.advocate_id:
        raise ContextRefused("wrong_scope", "The saved work belongs to another captured file.")
    saved = record.events[0].payload.get("context", {}).get("brief", {})
    if not saved.get("snapshot_id") or "selected_issue_ids" not in saved:
        raise ContextRefused("missing_source", "No checked file context was captured.")
    current = assemble_brief(
        matter, tuple(saved["selected_issue_ids"]), advocate_id=identity.advocate_id,
        display_before_version=_display_anchor(
            saved, matter, admitted_version=identity.matter_version),
        include_admitted_instructions=instruction_history_enabled(saved),
        private_instruction_mode=identity.mode,
        as_of=as_of,
    )
    snapshots = [
        event.payload["checked_snapshot"]
        for event in record.events
        if event.kind.value == "tool_returned" and "mutation_identity" in event.payload
    ]
    expected = snapshots[-1] if snapshots else saved["snapshot_id"]
    if current.snapshot_id != expected:
        raise ContextRefused("stale_context", "The case details changed; re-derive from the file.")
    if _display_anchor(saved, matter, admitted_version=identity.matter_version) is not None:
        old = json.loads(saved["text"])["data"]["displayed_private_questions"]
        now = json.loads(current.text)["data"]["displayed_private_questions"]
        if old != now:
            raise ContextRefused("stale_context", "The previously displayed questions changed.")
        if instruction_history_enabled(saved):
            old = json.loads(saved["text"])["data"]["admitted_private_instructions"]
            now = json.loads(current.text)["data"]["admitted_private_instructions"]
            if old != now:
                raise ContextRefused("stale_context", "The prior admitted instructions changed.")
    return current


def _display_anchor(saved, matter, *, admitted_version=None):
    """Optional private-history projection is pinned, never inferred from latest work."""
    try:
        data = json.loads(saved["text"])["data"]
        anchor = data.get("private_display_history_as_of_version")
        if anchor is None:
            if "displayed_private_questions" in data:
                raise ValueError("unanchored private history")
            return None
        if (type(anchor) is not int or not 1 <= anchor <= matter.version
                or admitted_version is not None and anchor != admitted_version
                or not isinstance(data.get("displayed_private_questions"), list)):
            raise ValueError("changed private history admission")
        return anchor
    except (KeyError, TypeError, ValueError) as exc:
        raise ContextRefused("invalid_recovery", "The displayed-question history is not pinned.") \
            from exc


def instruction_history_enabled(saved):
    """A new projection never changes the identity of an older saved context."""
    try:
        data = json.loads(saved["text"])["data"]
        if "admitted_private_instructions" not in data:
            return False
        if (not isinstance(data["admitted_private_instructions"], list)
                or "private_display_history_as_of_version" not in data
                or data.get("private_instruction_mode") not in {mode.value for mode in LoopMode}):
            raise ValueError("unbound instruction history")
        return True
    except (KeyError, TypeError, ValueError) as exc:
        raise ContextRefused("invalid_recovery", "The original-instruction history is unbound.") \
            from exc


def _instruction_mode(saved):
    if not instruction_history_enabled(saved):
        return LoopMode.SYNTHETIC
    return LoopMode(json.loads(saved["text"])["data"]["private_instruction_mode"])


def _admitted_private_instructions(matter, before_version, selected, mode):
    """Actual earlier lead input only, never private replies, tools or reasoning."""
    from nm.work_the_file.original_instruction import InstructionRefused, prior_instructions

    try:
        admitted = prior_instructions(matter, actor=matter.advocate_id,
                                      mode=mode, before_version=before_version)
    except InstructionRefused as exc:
        raise ContextRefused("invalid_history", "The prior lead input cannot be verified.") from exc
    rows = []
    for row in admitted:
        saved, original, issues = row.record, row.original, row.selected_issue_ids
        outside = bool(issues and selected and not set(issues) & set(selected))
        value = original.as_dict()
        if outside:
            value.pop("text")
        rows.append({"turn_id": saved.identity.turn_id,
            "parent_identity": saved.identity.fingerprint,
            "journal_identity": saved.events[-1].fingerprint,
            "admitted_at": saved.events[0].at, "selected_issue_ids": list(issues),
            "original_instruction": value,
            "detail_state": "outside_selected_issue_scope" if outside else
                "not_recorded" if original.state == "not_recorded" else
                "exact_prior_user_input_not_case_fact_or_current_authorization"})
    return tuple(rows)


class UncertaintyDimension(str, Enum):
    EXTRACTION = "extraction_quality"
    UNDERSTANDING = "faithful_understanding"
    FACTUAL = "factual_status"
    SUPPORT = "legal_support"
    APPLICABILITY = "applicability"
    PRACTICAL = "practical_uncertainty"
    READINESS = "decision_readiness"


class AssessmentState(str, Enum):
    ESTABLISHED = "established"
    NOT_ESTABLISHED = "not_established"
    NOT_ASSESSED = "not_assessed"
    CONDITIONAL = "conditional"


@dataclass(frozen=True)
class IndependentUncertainty:
    issue_id: str
    dimension: UncertaintyDimension
    state: AssessmentState = AssessmentState.NOT_ASSESSED
    basis: str = ""
    sources: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            not isinstance(self.issue_id, str)
            or not self.issue_id.strip()
            or not isinstance(self.dimension, UncertaintyDimension)
            or not isinstance(self.state, AssessmentState)
        ):
            raise ValueError("an uncertainty needs its issue, dimension and explicit state")
        if self.state is not AssessmentState.NOT_ASSESSED and not (
            self.basis.strip() and self.sources
        ):
            raise ValueError("an assessed uncertainty needs a basis and its sources")


@dataclass(frozen=True)
class ContextPolicy:
    max_tokens: int = 100_000
    reserve_tokens: int = 8_000

    def __post_init__(self):
        if (
            type(self.max_tokens) is not int
            or type(self.reserve_tokens) is not int
            or self.reserve_tokens < 1
            or self.max_tokens <= self.reserve_tokens
        ):
            raise ValueError("context needs a positive capacity and a smaller positive reserve")

    def require_fit(self, *texts: str) -> int:
        used = sum(estimate_tokens(text) for text in texts)
        if used + self.reserve_tokens > self.max_tokens:
            raise ContextRefused(
                "context_budget",
                "The checked context cannot fit without losing material; "
                "narrow the working disputes or read detail by its locator.",
            )
        return used


@dataclass(frozen=True)
class SourceSpan:
    source_id: str
    verbatim: str
    kind: str
    version: str

    def __post_init__(self):
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.source_id, self.verbatim, self.kind, self.version)
        ):
            raise ValueError("a source span needs its locator, actual text, kind and version")


@dataclass(frozen=True)
class CheckedBrief:
    matter_id: str
    advocate_id: str
    snapshot_id: str
    selected_issue_ids: tuple[str, ...]
    text: str
    sources: tuple[SourceSpan, ...]
    uncertainties: tuple[IndependentUncertainty, ...]
    source_record_json: str

    def span(self, source_id: str) -> SourceSpan | None:
        return next((source for source in self.sources if source.source_id == source_id), None)


@dataclass(frozen=True)
class HandoverLine:
    text: str
    source_id: str

    def __post_init__(self):
        if any(
            not isinstance(value, str) or not value.strip() for value in (self.text, self.source_id)
        ):
            raise ValueError("a handover line needs actual text and its file source")


def _wire(value):
    """Closed JSON representation, never repr() of an unknown domain object."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _wire(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ContextRefused("unbuildable_file", "A file record has non-text field names.")
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_wire(item) for item in value), key=_json)
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise ContextRefused("unbuildable_file", "A file record cannot be represented faithfully.")


def _json(value) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (ValueError, TypeError) as exc:
        raise ContextRefused(
            "unbuildable_file", "The file contains an invalid JSON value."
        ) from exc


def _data_message(value, *, label: str) -> str:
    """JSON strings cannot close a data boundary or become an extra message.

    This marks trust, it does not claim to solve semantic prompt injection.
    Permissions and the post-tool checks remain the enforcement boundary.
    """
    payload = _json(
        {"material_kind": label, "trust": "untrusted_data_not_instructions", "data": value}
    )
    return payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def assemble_brief(
    matter: Matter,
    selected_issue_ids: tuple[str, ...] = (),
    policy: ContextPolicy | None = None,
    *,
    advocate_id: str,
    uncertainties: tuple[IndependentUncertainty, ...] = (),
    as_of: date | None = None,
    source_current=None,
    display_before_version: int | None = None,
    include_admitted_instructions: bool = False,
    private_instruction_mode: LoopMode = LoopMode.SYNTHETIC,
) -> CheckedBrief:
    """Project the current structured file; selected facts are never paraphrased.

    Other disputes remain on a complete manifest with fact ids, dates, versions,
    conflicts and supersession links, and are read through the file tools. No
    detail silently disappears: every fact explicitly says full text or locator.
    A selected dispute's complete state, negations and original words must fit;
    otherwise this operation stops. The full stored file is not changed.
    """
    policy = policy or ContextPolicy()
    if type(include_admitted_instructions) is not bool or (
            include_admitted_instructions and (
                display_before_version is None
                or not isinstance(private_instruction_mode, LoopMode))):
        raise ContextRefused(
            "wrong_history", "Prior user input needs an explicit admitted version.")
    as_of = forum_today() if as_of is None else as_of
    if type(as_of) is not date:
        raise ContextRefused("invalid_calendar", "The checked checklist has a trusted date.")
    if not advocate_id.strip() or matter.advocate_id != advocate_id:
        raise ContextRefused("wrong_scope", "The file does not belong to this advocate.")
    raw = _wire(matter)
    # The journal describes work on the file; writing it must not invalidate
    # its own input. CAS still compares Matter.version in the runner. Every
    # substantive file field remains in this independently identified source.
    source_record = {key: value for key, value in raw.items() if key not in {"loop_records"}}
    snapshot = fingerprint({key: value for key, value in source_record.items() if key != "version"})
    thread_ids = {thread.id for thread in matter.threads}
    fact_ids = {fact.id for fact in matter.facts}
    if len(thread_ids) != len(matter.threads) or len(fact_ids) != len(matter.facts):
        raise ContextRefused("broken_file", "The file contains ambiguous duplicate identities.")
    if any(not set(thread.chronology) <= fact_ids for thread in matter.threads):
        raise ContextRefused("broken_file", "A dispute refers to a fact missing from the file.")
    if any(
        question.thread is not None and question.thread not in thread_ids
        for question in matter.asked
    ):
        raise ContextRefused("broken_file", "A question refers to a dispute missing from the file.")
    selected = tuple(sorted(set(selected_issue_ids or thread_ids)))
    if not set(selected) <= thread_ids:
        raise ContextRefused("wrong_issue", "A selected dispute is not on this matter.")
    selected_facts = {
        fact_id
        for thread in matter.threads
        if thread.id in selected
        for fact_id in thread.chronology
    }
    # Before a dispute exists, the file's original account is the working set.
    if not matter.threads:
        selected_facts = {fact.id for fact in matter.facts}
    if not selected_facts <= fact_ids:
        raise ContextRefused("broken_file", "A dispute refers to a fact missing from the file.")
    # Both directions of correction and conflict are exact case material,
    # including a contrary source initially attached to another dispute.
    selected_facts = linked_fact_ids(source_record["facts"], selected_facts)
    sources = []
    fact_rows = []
    for fact in matter.facts:
        row = _wire(fact)
        if fact.id in selected_facts:
            row["text_state"] = "verbatim_on_file_not_proof_of_truth"
            sources.append(
                SourceSpan(fact.id, fact.statement, fact.provenance.kind, fingerprint(_wire(fact)))
            )
        else:
            row.pop("statement")
            row.pop("exact_words")
            row["provenance"]["span"] = None
            row["text_state"] = "read_by_fact_id"
            row["statement_identity"] = fingerprint({"statement": fact.statement})
        row["issues"] = sorted(
            thread.id for thread in matter.threads if fact.id in thread.chronology
        )
        fact_rows.append(row)
    thread_rows = []
    for thread in matter.threads:
        if thread.id in selected:
            row = _wire(thread)
            row["detail_state"] = "current_structured_file"
            row["checklist_context"] = requirements.context_projection(
                thread, matter.facts, as_of, records=matter.loop_records,
                source_current=source_current)
            from nm.work_the_file.event_observation_contracts import event_context

            row["event_context"] = event_context(thread, matter.facts)
            for authority in thread.authorities:
                encoded = _wire(authority)
                locator = encoded.get("locator") if isinstance(encoded, dict) else None
                span = encoded.get("span") if isinstance(encoded, dict) else None
                if isinstance(locator, str) and locator and isinstance(span, str) and span:
                    sources.append(
                        SourceSpan(locator, span, "retrieved_material", fingerprint(encoded))
                    )
        else:
            row = {
                "id": thread.id,
                "label": thread.label,
                "chronology": list(thread.chronology),
                "assessed": list(thread.assessed),
                "deferred_reason": thread.deferred_reason,
                "detail_state": "read_by_issue_id",
            }
        thread_rows.append(row)
    for question in matter.asked:
        source_id = f"question:{question.gate}:{question.thread}:{question.asked_on}"
        sources.append(SourceSpan(source_id, question.text, "recorded_question", "1"))
    if display_before_version is not None:
        from nm.Archives.legal_brain.communicate.preview_display import displayed_questions

        if (type(display_before_version) is not int
                or not 1 <= display_before_version <= matter.version):
            raise ContextRefused(
                "wrong_history", "Private history needs its admitted file version.")
        shown = displayed_questions(matter, before_version=display_before_version,
                                    selected_issue_ids=selected)
        # Historical rendered words support continuity, not facts or current
        # legal validity. Internal/unseen proposals and reasoning never enter.
        raw["private_display_history_as_of_version"] = display_before_version
        raw["displayed_private_questions"] = list(shown)
        sources.extend(SourceSpan(f"preview_question:{row['turn_id']}", row["text"],
            "historical_private_preview_question", row["display_identity"]) for row in shown)
        if include_admitted_instructions:
            earlier = _admitted_private_instructions(
                matter, display_before_version, selected, private_instruction_mode)
            raw["private_instruction_mode"] = private_instruction_mode.value
            raw["admitted_private_instructions"] = list(earlier)
            sources.extend(SourceSpan(f"instruction:{row['turn_id']}",
                row["original_instruction"]["text"], "historical_unconfirmed_advocate_input",
                row["original_instruction"]["text_identity"]) for row in earlier
                if row["detail_state"] ==
                "exact_prior_user_input_not_case_fact_or_current_authorization")
    known_sources = {source.source_id for source in sources}
    supplied = {}
    for row in uncertainties:
        key = (row.issue_id, row.dimension)
        if row.issue_id not in selected or key in supplied or not set(row.sources) <= known_sources:
            raise ContextRefused("invalid_uncertainty", "An uncertainty has an invalid file basis.")
        supplied[key] = row
    independent = tuple(
        supplied.get((issue_id, dimension), IndependentUncertainty(issue_id, dimension))
        for issue_id in selected
        for dimension in UncertaintyDimension
    )
    # The answer history is reachable by turn id, not a second complete chat in
    # the prefix. Pending actions, qualifications and opposing views stay in raw.
    raw["turn_receipts"] = [
        {
            "turn_id": row.get("turn_id"),
            "receipt_identity": fingerprint(row),
            "detail_state": "read_by_turn_id",
        }
        for row in raw["turn_receipts"]
    ]
    # Private scratch/tool diagnostics are never replayed as an advocate's
    # instruction or as initial reasoning context. Their immutable journal is
    # reachable by an authenticated loop-turn reader, not embedded recursively.
    raw["loop_records"] = [
        {
            "turn_id": row["identity"]["turn_id"],
            "identity": fingerprint(row["identity"]),
            "journal_identity": (
                row["events"][-1]["fingerprint"] if row["events"] else fingerprint(row["identity"])
            ),
            "steps": sum(event["kind"] == "model_started" for event in row["events"]),
            "event_count": len(row["events"]),
            "terminal": bool(row["events"] and row["events"][-1]["kind"] == "stop"),
            "detail_state": "read_by_loop_turn_id",
        }
        for row in raw.get("loop_records", [])
    ]
    raw.update(
        {
            "facts": fact_rows,
            "threads": thread_rows,
            "snapshot_id": snapshot,
            "checklist_context_as_of": as_of.isoformat(),
            "selected_issue_ids": list(selected),
            "independent_uncertainties": [_wire(row) for row in independent],
        }
    )
    text = _data_message(raw, label="checked_matter_file")
    policy.require_fit(text)
    return CheckedBrief(
        matter.id,
        advocate_id,
        snapshot,
        selected,
        text,
        tuple(sources),
        independent,
        _json(source_record),
    )


def linked_fact_ids(facts, selected) -> frozenset[str]:
    """One dependency closure for source projections, never factual inference."""
    records = {row["id"]: row for row in facts}
    if len(records) != len(facts):
        raise ContextRefused("broken_file", "Source facts have duplicate identities.")
    wanted, pending = set(selected), list(selected)
    while pending:
        ident = pending.pop()
        if ident not in records:
            raise ContextRefused("broken_file", "A linked source fact is missing.")
        row = records[ident]
        related = list(row["conflicts_with"])
        if row["superseded_by"]:
            related.append(row["superseded_by"])
        related.extend(candidate["id"] for candidate in facts
                       if candidate["superseded_by"] == ident
                       or ident in candidate["conflicts_with"])
        for linked in related:
            if linked not in wanted:
                wanted.add(linked)
                pending.append(linked)
    for ident in wanted:
        current, visited = ident, set()
        while current:
            if current in visited:
                raise ContextRefused("broken_file", "Source facts contain a circular correction.")
            visited.add(current)
            current = records[current]["superseded_by"]
    return frozenset(wanted)


def validated_handover(
    lines: tuple[HandoverLine, ...], brief: CheckedBrief
) -> tuple[HandoverLine, ...]:
    """Reject invented/paraphrased content; no model can certify its own summary."""
    for line in lines:
        source = brief.span(line.source_id)
        if source is None or not line.text.strip() or line.text not in source.verbatim:
            raise ContextRefused(
                "invalid_handover", "The handover is not faithful to its file source."
            )
    return lines


class ContextSession:
    """A provider-neutral context projection with an immutable full transcript."""

    def __init__(
        self,
        principles: PrinciplesSnapshot,
        tool_specs: tuple,
        brief: CheckedBrief,
        *,
        provider: str,
        model: str,
        policy: ContextPolicy | None = None,
        tool_offer: ToolOfferState | None = None,
        source_current=None,
        working_preferences=None,
        today=forum_today,
    ):
        if not provider.strip() or not model.strip():
            raise ContextRefused(
                "missing_model", "The conversation needs its pinned provider and model."
            )
        self.policy = policy or ContextPolicy()
        if source_current is not None and not callable(source_current):
            raise ContextRefused(
                "invalid_source_owner", "Source currentness comes from a trusted runtime owner.")
        # Never serialize or inherit this capability from a journal or model.
        # Recovery must supply its current trusted reader again.
        self._source_current = source_current
        if not callable(today):
            raise ContextRefused("invalid_clock_owner", "The forum date needs its runtime owner.")
        self._today = today
        from nm.Archives.legal_brain.understand.advocate_memory import PreferenceContext

        if working_preferences is not None and (
                type(working_preferences) is not PreferenceContext
                or working_preferences.account_id != brief.advocate_id):
            raise ContextRefused("wrong_scope", "Working preferences belong to another account.")
        self.working_preferences = working_preferences
        self.provider, self.model = provider, model
        self.principles = principles
        self.brief = brief
        self.tool_specs = tuple(
            sorted((_wire(spec) for spec in tool_specs), key=lambda spec: spec["name"])
        )
        names = [spec["name"] for spec in self.tool_specs]
        if len(names) != len(set(names)):
            raise ContextRefused(
                "duplicate_tool", "The context contains two definitions of one tool."
            )
        inventory = tuple(ToolDefinition(**row) for row in self.tool_specs)
        self.tool_offer = tool_offer or ToolOfferState(
            inventory, fingerprint({"tools": self.tool_specs}), tuple(names))
        if tuple(_wire(row) for row in self.tool_offer.inventory) != self.tool_specs:
            raise ContextRefused("changed_offer", "The offer names another tool inventory.")
        self.generation = 1
        self.generations = ()
        self.transcript = ()
        self.messages = ()
        self._last_request = None
        self._start_generation("begin")

    @property
    def system(self) -> str:
        return self._system

    @property
    def offered_definitions(self):
        return self.tool_offer.definitions

    def load_checked_schema(self, call, receipt):
        """Trusted runner hook, after the actual receipt was durably saved."""
        try:
            self.tool_offer = self.tool_offer.loaded_by(call, receipt)
        except OfferRefused as exc:
            raise ContextRefused("invalid_offer", str(exc)) from exc

    def _system_for(self, principles: PrinciplesSnapshot) -> str:
        # The provider receives exact full schemas through tool calling. A
        # second copy in ordinary system prose pays twice and can dominate a
        # modest task allowance. Keep a stable, inspectable capability index
        # here; the recorded/full wire specs and mutation guards stay exact.
        if PEER in principles.text:
            raise ContextRefused(
                "duplicate_policy", "The shared communication owner appears twice.")
        catalogue = tuple({
            "name": spec["name"], "description": spec["description"],
            "schema_identity": fingerprint(spec["parameters"]),
        } for spec in self.tool_specs
            if not self.tool_offer.on_demand or spec["name"] in self.tool_offer.initial_names)
        offering = ""
        if self.tool_offer.on_demand:
            offering = "\nTRUSTED SCHEMA OFFER CONTRACT\n" + _json({
                "registered_count": len(self.tool_specs),
                "initial_count": len(self.tool_offer.initial_names),
                "schema_loaders": self.tool_offer.loader_names,
                "optional_schemas": "Discover registered metadata, then inspect an exact name. "
                    "A checked inspection loads its schema for a later request. "
                    "Metadata and loading do not grant permission or establish facts or law.",
            })
        preferences = ("APPROVED PRESENTATION PREFERENCES\n"
            + self.working_preferences.prefix_input + "\n"
            + "These preferences guide presentation only; they never override grounding, "
              "safety, matter instructions or independent checks.\n"
            if self.working_preferences is not None else "")
        return (preferences
            + "TRUSTED TOOL DEFINITIONS\n"
            + _json(catalogue)
            + offering
            + "\nTRUSTED OWNER GUIDANCE IDENTITY\n"
            + _json({"principles_version": principles.version})
            + "\nTRUSTED LOOP TERMINAL CONTRACT\n"
            + _json({"effects": {effect.value: reason.value
                                 for effect, reason in TERMINAL_REASONS.items()},
                     "contract": TERMINAL_CONTRACT})
            + "\n"
            + principles.text
            + "\n"
            + PEER
        )

    def _require_messages_fit(self, system: str, messages: tuple[ToolMessage, ...]):
        self.policy.require_fit(system, *(_json(_wire(message)) for message in messages))

    def _start_generation(self, reason: str):
        system = self._system_for(self.principles)
        messages = (ToolMessage(role="user", text=self.brief.text),)
        self._require_messages_fit(system, messages)
        generation = (
            {
                "generation": self.generation,
                "reason": reason,
                "principles_version": self.principles.version,
                "tool_registry_identity": fingerprint({"tools": self.tool_specs}),
                "snapshot_id": self.brief.snapshot_id,
                "system_identity": fingerprint({"system": system}),
                "communication_owner_identity": fingerprint({"peer": PEER}),
                "offer_policy_identity": self._offer_policy_identity(),
            },
        )
        self._system, self.messages = system, messages
        self.transcript += messages
        self._last_request = None
        self.generations += generation

    def append(self, *messages: ToolMessage, defer_fit: bool = False):
        """Archive exact round bytes; deferred fit never permits a request.

        Trusted runners may finish archiving a tool round before rebuilding
        its checked working context. The outgoing request guard is unchanged.
        """
        if type(defer_fit) is not bool:
            raise ValueError("capacity deferral is an explicit runner decision")
        proposed = self.messages + tuple(messages)
        validate_tool_history(proposed, allow_pending=True)
        if not defer_fit:
            self.policy.require_fit(self.system, *(_json(_wire(message)) for message in proposed))
        # Store immutable wire copies too: caller-owned argument dictionaries
        # cannot rewrite an earlier request after the fact.
        copied = tuple(_message_from_wire(_wire(message)) for message in messages)
        self.messages += copied
        self.transcript += copied

    def _offer_policy_identity(self):
        return fingerprint({"registry": self.tool_offer.registry_version,
            "initial": self.tool_offer.initial_names, "loaders": self.tool_offer.loader_names})

    def assert_request(self, system: str, messages: tuple[ToolMessage, ...], *, model: str,
                       tools=None):
        """Compare actual outgoing bytes, not a flag saying history was appended."""
        encoded = tuple(_json(_wire(message)) for message in messages)
        validate_tool_history(messages)
        if (fingerprint({"tools": self.tool_specs})
                != self.generations[-1]["tool_registry_identity"]):
            raise ContextRefused("changed_prefix", "The running tool definitions were rewritten.")
        try:
            if self._offer_policy_identity() != self.generations[-1]["offer_policy_identity"]:
                raise OfferRefused("The admitted offer policy changed.")
            ToolOfferState.from_record(self.tool_offer.to_record(),
                tuple(ToolDefinition(**row) for row in self.tool_specs), self.transcript)
            self.tool_offer.require_offer(self.offered_definitions if tools is None else tools)
        except OfferRefused as exc:
            raise ContextRefused("changed_offer", str(exc)) from exc
        if (self.principles.version != self.generations[-1]["principles_version"]
                or fingerprint({"peer": PEER}) != self.generations[-1][
                    "communication_owner_identity"]
                or self._system_for(self.principles) != self.system):
            raise ContextRefused(
                "changed_prefix", "The admitted reasoning or communication changed.")
        if system != self.system or model != self.model:
            raise ContextRefused(
                "changed_prefix", "The running conversation's prefix or model changed."
            )
        if messages != self.messages:
            raise ContextRefused(
                "changed_history", "The request differs from its checked working record."
            )
        if (
            self._last_request is not None
            and encoded[: len(self._last_request)] != self._last_request
        ):
            raise ContextRefused("changed_history", "Earlier conversation bytes were rewritten.")
        self.policy.require_fit(system, *encoded)
        self._last_request = encoded

    def compact(
        self,
        matter: Matter,
        *,
        reason: str,
        principles: PrinciplesSnapshot | None = None,
        handover: tuple[HandoverLine, ...] = (),
    ) -> bool:
        """At a round boundary, rebuild from the file; invalid handover is omitted.

        Returns whether the handover was admitted. Its refusal is recorded in
        the generation reason, not disguised as a successfully checked summary.
        """
        if not reason.strip():
            raise ContextRefused("missing_reason", "A new context generation needs its reason.")
        if validate_tool_history(self.messages, allow_pending=True):
            raise ContextRefused("tool_round_open", "Context cannot compact during a tool round.")
        if matter.id != self.brief.matter_id or matter.advocate_id != self.brief.advocate_id:
            raise ContextRefused(
                "wrong_scope", "Compaction cannot move this conversation to another file."
            )
        brief = self._compaction_brief(matter)
        return self._compact_checked_brief(
            brief, reason=reason, principles=principles, handover=handover
        )

    def _compaction_brief(self, matter):
        as_of = self._today()
        anchor = _display_anchor({"text": self.brief.text}, matter)
        include_instructions = instruction_history_enabled({"text": self.brief.text})
        instruction_mode = _instruction_mode({"text": self.brief.text})
        brief = assemble_brief(
            matter, self.brief.selected_issue_ids, self.policy, advocate_id=self.brief.advocate_id,
            source_current=self._source_current, display_before_version=anchor,
            as_of=as_of,
            include_admitted_instructions=include_instructions,
            private_instruction_mode=instruction_mode)
        # A changed file invalidates only uncertainty rows whose actual basis
        # changed. Unrelated source-backed judgments survive compaction.
        preserved = tuple(
            row
            for row in self.brief.uncertainties
            if all(self.brief.span(source_id) == brief.span(source_id) for source_id in row.sources)
        )
        if preserved:
            brief = assemble_brief(
                matter,
                self.brief.selected_issue_ids,
                self.policy,
                advocate_id=self.brief.advocate_id,
                uncertainties=preserved,
                as_of=as_of,
                source_current=self._source_current,
                display_before_version=anchor,
                  include_admitted_instructions=include_instructions,
                  private_instruction_mode=instruction_mode,
            )
        return brief

    def compact_for_request(self, matter, prompt, tools, *, source_reads=()):
        """Fit actual request bytes from checked state, never truncate a story.

        Source bodies remain exact in the sealed transcript/journal. Their
        working references explicitly require re-reading before quotations or
        source-dependent work; missing bodies do not become assessed findings.
        """
        from nm.shared.model_port import tool_request_text

        if validate_tool_history(self.messages, allow_pending=True):
            raise ContextRefused("tool_round_open", "Compaction waits for a complete tool round.")
        brief = self._compaction_brief(matter)
        retained = saved_source_references(source_reads)
        candidate = ContextSession(
            self.principles, tuple(self.tool_specs), brief, provider=self.provider,
            model=self.model, policy=self.policy, tool_offer=self.tool_offer,
            source_current=self._source_current, working_preferences=self.working_preferences,
            today=self._today)
        if retained:
            candidate.append(retained)
        self.policy.require_fit(tool_request_text(prompt, tools, candidate.messages))
        self.compact(matter, reason="actual outgoing context capacity reached")
        if retained:
            self.append(retained)
        return True

    def _compact_checked_brief(
        self,
        brief: CheckedBrief,
        *,
        reason: str,
        principles: PrinciplesSnapshot | None = None,
        handover: tuple[HandoverLine, ...] = (),
    ) -> bool:
        """Private projection-owner hook; callers must validate their own scope.

        This shared mechanism never decides whether a matter projection or a
        task-specific projection is appropriate. The public owner does that.
        """
        if not reason.strip():
            raise ContextRefused("missing_reason", "A new context generation needs its reason.")
        if validate_tool_history(self.messages, allow_pending=True):
            raise ContextRefused("tool_round_open", "Context cannot compact during a tool round.")
        if (brief.matter_id, brief.advocate_id) != (self.brief.matter_id, self.brief.advocate_id):
            raise ContextRefused("wrong_scope", "Compaction cannot change its attributed file.")
        accepted = True
        try:
            checked = validated_handover(handover, brief)
        except ContextRefused as exc:
            if exc.code != "invalid_handover":
                raise
            checked, accepted = (), False
        next_principles = principles or self.principles
        proposed = (ToolMessage(role="user", text=brief.text),)
        if checked:
            proposed += (
                ToolMessage(
                    role="user",
                    text=_data_message(
                        [_wire(line) for line in checked], label="checked_verbatim_handover"
                    ),
                ),
            )
        # Check the actual provider-neutral wire shape before replacing any
        # generation. A refusal must leave the previous context recoverable.
        self._require_messages_fit(self._system_for(next_principles), proposed)
        self.brief, self.principles = brief, next_principles
        self.generation += 1
        self._start_generation(
            reason if accepted else reason + "; handover refused, checked brief only"
        )
        if checked:
            self.append(proposed[1])
        return accepted

    def refresh_principles(self, principles: PrinciplesSnapshot, matter: Matter) -> bool:
        if principles.version == self.principles.version:
            return False
        self.compact(matter, reason="principles changed at turn boundary", principles=principles)
        return True

    def clear_spent_result(
        self,
        call_id: str,
        *,
        locator: str,
        recorded_finding: HandoverLine,
        pending_locators: frozenset[str] = frozenset(),
    ):
        """A cited source is cleared only after its finding is on the checked file."""
        if validate_tool_history(self.messages, allow_pending=True):
            raise ContextRefused(
                "tool_round_open", "A result cannot be cleared during a tool round."
            )
        if not locator.strip() or locator in pending_locators:
            raise ContextRefused("pending_source", "A pending claim still needs this source span.")
        if recorded_finding.source_id != locator:
            raise ContextRefused(
                "invalid_handover", "The recorded finding belongs to a different source."
            )
        validated_handover((recorded_finding,), self.brief)
        result = next(
            (
                message
                for message in self.messages
                if message.role == "tool" and message.call_id == call_id
            ),
            None,
        )
        if result is None:
            raise ContextRefused("missing_result", "There is no completed result to clear.")
        try:
            raw = json.loads(result.text)
        except (ValueError, TypeError) as exc:
            raise ContextRefused(
                "unclear_locator", "The tool result has no checkable locator."
            ) from exc
        if locator not in _strings(raw):
            raise ContextRefused("unclear_locator", "The locator does not identify this result.")
        stub = ToolMessage(
            role="tool",
            call_id=call_id,
            text=_data_message(
                {
                    "locator": locator,
                    "finding": _wire(recorded_finding),
                    "state": "cleared_refetch_and_check_source_identity",
                },
                label="cleared_tool_result",
            ),
        )
        proposed = tuple(stub if message is result else message for message in self.messages)
        self._require_messages_fit(self.system, proposed)
        self.generation += 1
        self._start_generation("spent tool result cleared; full transcript retained")
        self.messages = proposed

    def to_record(self) -> dict:
        """Persist this only through the existing sealed matter store."""
        return _wire(
            {
                "schema": 2 if self.working_preferences is not None else 1,
                **({"working_preferences": {
                    "account_id": self.working_preferences.account_id,
                    "version": self.working_preferences.version,
                    "settings": self.working_preferences.preferences.as_dict(),
                    "notice": self.working_preferences.notice,
                }} if self.working_preferences is not None else {}),
                "provider": self.provider,
                "model": self.model,
                "principles": self.principles,
                "brief": self.brief,
                "tool_specs": self.tool_specs,
                "tool_offer": self.tool_offer.to_record(),
                "generation": self.generation,
                "generations": self.generations,
                "system": self.system,
                "messages": self.messages,
                "transcript": self.transcript,
                "last_request": self._last_request,
            }
        )

    @classmethod
    def from_record(
        cls, record: dict, matter: Matter, *, advocate_id: str,
        policy: ContextPolicy | None = None, source_current=None, today=forum_today,
    ) -> ContextSession:
        """Recovery verifies the current file, scope and prefix before reuse."""
        try:
            cls._require_record_shape(record)
            saved = record["brief"]
            rows = tuple(
                IndependentUncertainty(
                    row["issue_id"],
                    UncertaintyDimension(row["dimension"]),
                    AssessmentState(row["state"]),
                    row["basis"],
                    tuple(row["sources"]),
                )
                for row in saved["uncertainties"]
            )
            brief = assemble_brief(
                matter,
                tuple(saved["selected_issue_ids"]),
                policy,
                advocate_id=advocate_id,
                uncertainties=rows,
                as_of=date.fromisoformat(json.loads(saved["text"])["data"][
                    "checklist_context_as_of"]),
                source_current=source_current,
                display_before_version=_display_anchor(saved, matter),
                  include_admitted_instructions=instruction_history_enabled(saved),
                  private_instruction_mode=_instruction_mode(saved),
            )
            if brief.snapshot_id != saved["snapshot_id"]:
                raise ContextRefused(
                    "stale_context", "The saved context no longer matches the file."
                )
            # Audit appends change the file's CAS version and journal manifest,
            # not the substantive source. Keep the old sent bytes after checking
            # their source and every saved journal stub against the current file.
            _require_saved_projection(saved, brief, matter)
            brief = replace(
                brief, text=saved["text"], source_record_json=saved["source_record_json"]
            )
            if _wire(brief) != saved:
                raise ContextRefused("invalid_recovery", "The saved brief has unverified fields.")
            return cls._from_checked_record(record, brief, policy=policy,
                                            source_current=source_current, today=today)
        except (KeyError, TypeError, ValueError) as exc:
            raise ContextRefused(
                "invalid_recovery", "The saved context record cannot be verified."
            ) from exc

    @staticmethod
    def _require_record_shape(record: dict):
        expected = {
            "schema",
            "provider",
            "model",
            "principles",
            "brief",
            "tool_specs",
            "tool_offer",
            "generation",
            "generations",
            "system",
            "messages",
            "transcript",
            "last_request",
        }
        if type(record.get("schema")) is not int or record["schema"] not in (1, 2):
            raise ValueError("unknown context record")
        if record["schema"] == 2:
            expected.add("working_preferences")
        if set(record) != expected:
            raise ValueError("unknown context record")

    @classmethod
    def _from_checked_record(
        cls, record: dict, brief: CheckedBrief, *, policy: ContextPolicy | None = None,
        source_current=None,
        today=forum_today,
    ) -> ContextSession:
        """Restore history only after its projection owner has checked the brief."""
        try:
            cls._require_record_shape(record)
            if _wire(brief) != record["brief"]:
                raise ValueError("the restored context differs from its checked projection")
            working_preferences = None
            if record["schema"] == 2:
                from nm.Archives.legal_brain.understand.advocate_memory import PreferenceContext
                from nm.Archives.legal_brain.understand.advocate_memory_contracts import Preferences

                value = record["working_preferences"]
                if type(value) is not dict or set(value) != {
                        "account_id", "version", "settings", "notice"}:
                    raise ValueError("invalid working preferences")
                working_preferences = PreferenceContext(value["account_id"], value["version"],
                    Preferences.from_values(value["settings"]), value["notice"])
            session = cls(
                PrinciplesSnapshot(**record["principles"]),
                tuple(record["tool_specs"]),
                brief,
                provider=record["provider"],
                model=record["model"],
                policy=policy,
                source_current=source_current,
                today=today,
                working_preferences=working_preferences,
                tool_offer=ToolOfferState.from_record(record["tool_offer"],
                    tuple(ToolDefinition(**row) for row in record["tool_specs"]),
                    tuple(_message_from_wire(row) for row in record["transcript"])),
            )
            if record["system"] != session.system:
                raise ContextRefused(
                    "changed_prefix", "The saved prefix is not its recorded principles."
                )
            generation = record["generation"]
            if type(generation) is not int or generation < 1:
                raise ValueError("invalid generation")
            generations = tuple(record["generations"])
            if [row["generation"] for row in generations] != list(range(1, generation + 1)):
                raise ValueError("incomplete generation history")
            latest = generations[-1]
            if (
                latest["snapshot_id"] != brief.snapshot_id
                or latest["principles_version"] != session.principles.version
                or latest["tool_registry_identity"] != fingerprint({"tools": session.tool_specs})
                or latest["system_identity"] != fingerprint({"system": session.system})
                or latest["communication_owner_identity"] != fingerprint({"peer": PEER})
                or latest["offer_policy_identity"] != session._offer_policy_identity()
                or any(not row["reason"].strip() for row in generations)
            ):
                raise ValueError("generation identity differs")
            session.generation, session.generations = generation, generations
            session.messages = tuple(_message_from_wire(row) for row in record["messages"])
            session.transcript = tuple(_message_from_wire(row) for row in record["transcript"])
            validate_tool_history(session.transcript, allow_pending=True)
            if not session.messages or session.messages[0] != ToolMessage(
                role="user", text=brief.text
            ):
                raise ValueError("checked file missing")
            session._last_request = (
                tuple(record["last_request"]) if record["last_request"] is not None else None
            )
            last_request = session._last_request
            session.assert_request(session.system, session.messages, model=session.model)
            # Validation is not a provider call; do not claim these bytes have
            # already been sent when recovery preceded the first request.
            session._last_request = last_request
            return session
        except (KeyError, TypeError, ValueError) as exc:
            raise ContextRefused(
                "invalid_recovery", "The saved context record cannot be verified."
            ) from exc


def _message_from_wire(row: dict) -> ToolMessage:
    if set(row) != {"role", "text", "calls", "call_id"}:
        raise ValueError("unknown tool message fields")
    calls = tuple(ToolCall(**call) for call in row["calls"])
    return ToolMessage(role=row["role"], text=row["text"], calls=calls, call_id=row["call_id"])


def _strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(_strings(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(item) for item in value)) if value else set()
    return set()


def saved_source_references(receipts: tuple[dict, ...]) -> ToolMessage | None:
    """Exact receipt references, not a narrative or newly certified Finding.

    Only the trusted journal/runner calls this owner. Full original bodies
    remain in its sealed log; omission is explicit and requires an exact
    reader before source-dependent work. Failed reads retain their limits.
    """
    from nm.Archives.legal_brain.orchestrate.tools import (
        Assessment,
        Availability,
        Effect,
        ToolEnvelope,
        ToolKind,
        ToolOutcome,
    )
    from nm.Archives.legal_brain.retrieve.tool_sources import findings_from_envelope

    if not isinstance(receipts, tuple) or any(not isinstance(row, dict) for row in receipts):
        raise ContextRefused("unbound_source", "Source references need actual typed read receipts.")
    references = []
    seen = set()
    for raw in receipts:
        try:
            envelope = ToolEnvelope(
                raw["tool"], raw["version"], ToolKind(raw["kind"]), ToolOutcome(raw["outcome"]),
                Availability(raw["availability"]), Assessment(raw["assessment"]),
                raw["receipt"], raw["data"], raw["reason"], Effect(raw["effect"]))
            if envelope.kind is not ToolKind.SOURCE:
                raise ValueError("not a source owner")
            ident = envelope.fingerprint
            metadata = []
            for finding in findings_from_envelope(envelope):
                row = finding.as_record()
                metadata.append({
                    "finding_identity": fingerprint(row), "span_identity": fingerprint(
                        {"span": finding.span}),
                    "metadata": {key: value for key, value in row.items()
                                 if key not in ("span", "proposition")},
                    "text_state": "exact_body_retained_in_journal_refetch_required",
                })
            limits = [{key: value for key, value in row.items() if key != "findings"}
                      for row in envelope.receipt.get("primary_reads", ())]
        except (KeyError, TypeError, ValueError) as exc:
            raise ContextRefused("unbound_source", "A saved source reference cannot be checked.") \
                from exc
        if ident in seen:
            continue
        seen.add(ident)
        references.append({
            "tool": envelope.tool, "tool_version": envelope.version,
            "original_receipt_identity": ident,
            "index": envelope.receipt["index"], "locators": envelope.receipt["locators"],
            "source_version": envelope.receipt["source_version"],
            "outcome": envelope.outcome.value, "availability": envelope.availability.value,
            "assessment": envelope.assessment.value, "reason": envelope.reason,
            "primary_read_limits": limits, "source_metadata": metadata,
            "raw_window_identities": [
                {"locator": row["locator"], "identity": fingerprint(row),
                 "text_state": "exact_body_retained_in_journal_refetch_required"}
                for row in envelope.data.get("captured_windows", ())],
            "read_again_before_dependent_work": True,
        })
    return (ToolMessage("user", _data_message(
        references, label="saved_source_references_not_source_text")) if references else None)


def _require_saved_projection(saved: dict, current: CheckedBrief, matter: Matter):
    old = json.loads(saved["text"])
    now = json.loads(current.text)
    if (
        set(old) != {"data", "material_kind", "trust"}
        or old["material_kind"] != "checked_matter_file"
        or old["trust"] != "untrusted_data_not_instructions"
        or _data_message(old["data"], label="checked_matter_file") != saved["text"]
    ):
        raise ValueError("saved brief is not canonical data")
    old_source = json.loads(saved["source_record_json"])
    current_source = json.loads(current.source_record_json)
    if _json(old_source) != saved["source_record_json"]:
        raise ValueError("saved source is not canonical")
    if fingerprint({key: value for key, value in old_source.items() if key != "version"}) != (
        current.snapshot_id
    ):
        raise ValueError("saved full source no longer matches")
    for source in (old["data"], old_source):
        version = source.get("version")
        if type(version) is not int or version < 0 or version > matter.version:
            raise ValueError("saved source version is not an admitted file version")
    current_source.pop("version")
    old_source.pop("version")
    if old_source != current_source:
        raise ValueError("saved source differs beyond the audit version")
    for stub in old["data"].get("loop_records", []):
        expected = {
            "turn_id",
            "identity",
            "journal_identity",
            "steps",
            "event_count",
            "terminal",
            "detail_state",
        }
        if set(stub) != expected or stub["detail_state"] != "read_by_loop_turn_id":
            raise ValueError("unknown audit manifest fields")
        record = next(
            (row for row in matter.loop_records if row.identity.turn_id == stub["turn_id"]), None
        )
        count = stub["event_count"]
        if record is None or type(count) is not int or not 0 <= count <= len(record.events):
            raise ValueError("saved audit locator cannot be verified")
        events = record.events[:count]
        identity = fingerprint(_wire(record.identity))
        expected_stub = {
            "turn_id": record.identity.turn_id,
            "identity": identity,
            "journal_identity": events[-1].fingerprint if events else identity,
            "steps": sum(event.kind.value == "model_started" for event in events),
            "event_count": count,
            "terminal": bool(events and events[-1].kind.value == "stop"),
            "detail_state": "read_by_loop_turn_id",
        }
        if stub != expected_stub:
            raise ValueError("saved audit manifest is not its actual journal prefix")
    for value in (old["data"], now["data"]):
        value.pop("version")
        value.pop("loop_records")
    if old != now:
        raise ValueError("saved working projection differs beyond audit metadata")
