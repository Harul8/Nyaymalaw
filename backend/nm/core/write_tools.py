"""Prepared file tools: the shared registry checks; the journal alone writes."""
from __future__ import annotations

from nm.core import file_mutation
from nm.core.original_instruction import InstructionRefused, prior_instructions
from nm.core.tools import (
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
from nm.domain.authority import Act
from nm.domain.clock import today as forum_today
from nm.domain.issue import IssueKind
from nm.domain.loop import digest
from nm.domain.matter import Side
from nm.domain.requirements import State
from nm.ports.model import ToolDefinition
from nm.ports.store import StorePort

VERSION = "source-bound-writes-v1"
PRIOR_VERSION = "prior-instruction-writes-v1"
_STRING = {"type": "string", "minLength": 1}
_CONTROLS = ("test_file_writes_use_trusted_messages_not_model_facts",
             "test_file_writes_cannot_change_permissions_or_journal_identity")


def write_tools(store: StorePort, *, today=forum_today) -> tuple[RegisteredTool, ...]:
    """No arbitrary field names, paths, actors, version or original-message arguments."""
    def instruction_source(matter, args, context):
        ident = args["instruction_turn_id"]
        if (not isinstance(ident, str) or not 1 <= len(ident) <= 100
                or any(not (character.isascii() and (character.isalnum()
                                                   or character in "_-")) for character in ident)
                or matter is None):
            raise ToolRefused("An earlier instruction needs its exact original portable turn.")
        try:
            rows = prior_instructions(matter, actor=context.identity.advocate_id,
                mode=context.identity.mode, before_version=context.identity.matter_version)
        except InstructionRefused as exc:
            raise ToolRefused("The earlier original instruction cannot be verified.") from exc
        sources = [row for row in rows if row.record.identity.turn_id == ident]
        if len(sources) != 1:
            raise ToolRefused("The earlier instruction is unavailable or ambiguous.")
        source = sources[0]
        start = source.record.events[0].payload
        if start.get("scope_identity") != digest({"requested_issue_ids": []}):
            if (not source.selected_issue_ids or args["new_dispute_label"] is not None
                    or not set(args["thread_ids"]) <= set(source.selected_issue_ids)):
                raise ToolRefused("The earlier instruction does not admit this dispute scope.")
        if source.original.state != "recorded":
            raise ToolRefused("No original advocate instruction was recorded for that turn.")
        return source

    def prepare(name, args, context):
        args = dict(args)
        matter = store.load(context.identity.matter_id)
        if context.issue_ids:
            selected = set(context.issue_ids)
            target = args.get("thread_id")
            if target is not None and target not in selected:
                raise ToolRefused("The exact dispute is outside this admitted work scope.")
            if "thread_ids" in args and not set(args["thread_ids"]) <= selected:
                raise ToolRefused("An assertion cannot choose a dispute outside this work scope.")
            if name == "correct_fact" and matter is not None:
                touched = {row.id for row in matter.threads
                           if args["old_fact_id"] in row.chronology}
                if not touched & selected:
                    raise ToolRefused("The corrected fact is outside this admitted work scope.")
            if name == "create_dispute" or (
                    name == "record_prior_instruction" and args["new_dispute_label"] is not None):
                parents = [row for row in matter.loop_records
                           if row.identity == context.identity] if matter is not None else []
                if (len(parents) != 1 or not parents[0].events
                        or parents[0].events[0].payload.get("scope_identity") != digest(
                            {"requested_issue_ids": []})):
                    raise ToolRefused("A narrowed task cannot silently add another dispute.")
        trusted = {"advocate_id": context.identity.advocate_id,
                   "current_version": context.current_version,
                   "turn_id": context.identity.turn_id,
                   "message": context.original_message}
        source = None
        if name == "record_prior_instruction":
            label, threads = args["new_dispute_label"], args["thread_ids"]
            if not ((label is not None and label.strip() and not threads)
                    or (label is None and threads)):
                raise ToolRefused("Choose either one new dispute or exact existing disputes.")
            source = instruction_source(matter, args, context)
            trusted.update(turn_id=source.record.identity.turn_id, message=source.original.text)
        try:
            if name == "record_prior_instruction":
                if args["new_dispute_label"] is not None:
                    mutation, detail = file_mutation.prepare_dispute(matter, **trusted,
                        label=args["new_dispute_label"], quoted=args["quoted"])
                else:
                    mutation, detail = file_mutation.prepare_admission(matter, **trusted,
                        thread_ids=args["thread_ids"], quoted=args["quoted"])
            elif name == "create_dispute":
                mutation, detail = file_mutation.prepare_dispute(matter, **trusted, **args)
            elif name == "write_fact":
                mutation, detail = file_mutation.prepare_admission(matter, **trusted, **args)
            elif name == "correct_fact":
                mutation, detail = file_mutation.prepare_correction(
                    matter, **trusted, **args, today=today())
            elif name in ("record_requirement_answer", "record_existing_requirement_answer"):
                mutation, detail = file_mutation.prepare_requirement_answer(
                    matter, **trusted, **args, today=today())
            else:
                mutation, detail = file_mutation.prepare_issue(matter, **trusted, **args)
        except file_mutation.MutationRefused as exc:
            raise ToolRefused(str(exc)) from exc
        if source is not None:
            detail = {**detail, "instruction_turn_id": source.record.identity.turn_id,
                "instruction_identity": source.original.text_identity,
                "instruction_provenance": source.original.provenance,
                "source_parent_identity": source.record.identity.fingerprint,
                "source_journal_identity": source.record.events[-1].fingerprint}
        envelope = ToolEnvelope(name, PRIOR_VERSION if source else VERSION,
            ToolKind.MATTER, ToolOutcome.RESULTS,
            Availability.AVAILABLE, Assessment.NOT_ASSESSED,
            {"matter_id": matter.id, "matter_version": matter.version,
             "snapshot": mutation.identity}, {"operation": name,
                "changed_fields": list(mutation.changed_fields), **detail},
            "This checked file update does not establish factual or legal truth.")
        return PreparedToolResult(envelope, mutation)

    schemas = (
        ("create_dispute", "Record a new source-bound unassessed dispute, including the first "
         "on an empty file. Inspect existing disputes first; similar labels or parties "
         "never establish that two disputes are one. This assigns no party or legal position.",
         {"label": _STRING, "quoted": _STRING}),
        ("write_fact", "Record an exact current advocate assertion on existing disputes.",
         {"quoted": _STRING, "thread_ids": {"type": "array", "minItems": 1,
             "maxItems": 20, "items": _STRING}}),
        ("correct_fact", "Propose an explicit correction to an exact current file entry, "
         "preserving the earlier words and reopening dependent work.",
         {"old_fact_id": _STRING, "quoted": _STRING}),
        ("record_requirement_answer", "Read an advocate reply against an exact existing "
         "requirement. Held means supplied information, not proven facts.",
         {"thread_id": _STRING, "requirement_key": _STRING,
          "answer": {"type": "string", "enum": [s.value for s in State]},
          "quoted": _STRING, "due_expression": {"type": "string"}}),
        ("record_existing_requirement_answer", "Apply or revalidate information already "
         "supplied in an exact current scoped advocate assertion against an existing "
         "requirement. Preserve its attribution, uncertainty and history; do not ask "
         "again merely because law was newly read. An old promise has no new date anchor.",
         {"thread_id": _STRING, "requirement_key": _STRING, "fact_id": _STRING,
          "answer": {"type": "string", "enum": [s.value for s in State]},
          "quoted": _STRING, "due_expression": {"type": "string"}}),
        ("add_issue", "Record a question supported by the current advocate words, "
         "without deleting standing questions or certifying its answer.",
         {"thread_id": _STRING, "statement": _STRING,
          "kind": {"type": "string", "enum": [k.value for k in IssueKind]},
          "runs_against": {"type": "string", "enum": [s.value for s in Side]},
          "quoted": _STRING}),
    )
    current = tuple(RegisteredTool(ToolDefinition(name, description, object_schema(properties)),
        ToolKind.MATTER, VERSION, False, _CONTROLS,
        lambda args, context, name=name: prepare(name, args, context), required_act=Act.RECORD)
        for name, description, properties in schemas)
    prior = RegisteredTool(ToolDefinition("record_prior_instruction",
        "Record an exact previously supplied advocate instruction by its recorded turn locator. "
        "Choose a nonblank new_dispute_label with empty thread_ids to create one unassessed "
        "dispute, or null label with existing thread_ids to link an assertion. Preserve the "
        "original attribution, denial and uncertainty; earlier supplied words are not new "
        "instructions, established facts, corrections or legal authority.", object_schema({
            "instruction_turn_id": _STRING, "quoted": _STRING,
            "new_dispute_label": {"type": ["string", "null"]},
            "thread_ids": {"type": "array", "minItems": 0, "maxItems": 20,
                           "items": _STRING}})), ToolKind.MATTER, PRIOR_VERSION, False,
        (*_CONTROLS, "test_old_input_requires_exact_before_admission_owned_complete_parent"),
        lambda args, context: prepare("record_prior_instruction", args, context),
        required_act=Act.RECORD)
    return (*current, prior)
