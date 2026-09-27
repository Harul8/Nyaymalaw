"""Prepared file tools: the shared registry checks; the journal alone writes."""

from __future__ import annotations

from nm.legal_brain.orchestrate.loop_contracts import digest
from nm.legal_brain.orchestrate.tools import (
    Assessment,
    Availability,
    PreparedToolResult,
    RegisteredTool,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    ToolRefused,
)
from nm.shared.clock_contracts import today as forum_today
from nm.shared.store_port import StorePort
from nm.work_the_file import file_mutation
from nm.work_the_file.original_instruction import InstructionRefused, prior_instructions

VERSION = "source-bound-writes-v1"
PRIOR_VERSION = "prior-instruction-writes-v1"
_STRING = {"type": "string", "minLength": 1}
_CONTROLS = (
    "test_file_writes_use_trusted_messages_not_model_facts",
    "test_file_writes_cannot_change_permissions_or_journal_identity",
)


def write_tools(store: StorePort, *, today=forum_today) -> tuple[RegisteredTool, ...]:
    """No arbitrary field names, paths, actors, version or original-message arguments."""

    def instruction_source(matter, args, context):
        ident = args["instruction_turn_id"]
        if (
            not isinstance(ident, str)
            or not 1 <= len(ident) <= 100
            or any(
                not (character.isascii() and (character.isalnum() or character in "_-"))
                for character in ident
            )
            or matter is None
        ):
            raise ToolRefused("An earlier instruction needs its exact original portable turn.")
        try:
            rows = prior_instructions(
                matter,
                actor=context.identity.advocate_id,
                mode=context.identity.mode,
                before_version=context.identity.matter_version,
            )
        except InstructionRefused as exc:
            raise ToolRefused("The earlier original instruction cannot be verified.") from exc
        sources = [row for row in rows if row.record.identity.turn_id == ident]
        if len(sources) != 1:
            raise ToolRefused("The earlier instruction is unavailable or ambiguous.")
        source = sources[0]
        start = source.record.events[0].payload
        if start.get("scope_identity") != digest({"requested_issue_ids": []}):
            if (
                not source.selected_issue_ids
                or args["new_dispute_label"] is not None
                or not set(args["thread_ids"]) <= set(source.selected_issue_ids)
            ):
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
                touched = {
                    row.id for row in matter.threads if args["old_fact_id"] in row.chronology
                }
                if not touched & selected:
                    raise ToolRefused("The corrected fact is outside this admitted work scope.")
            if name == "create_dispute" or (
                name == "record_prior_instruction" and args["new_dispute_label"] is not None
            ):
                parents = (
                    [row for row in matter.loop_records if row.identity == context.identity]
                    if matter is not None
                    else []
                )
                if (
                    len(parents) != 1
                    or not parents[0].events
                    or parents[0].events[0].payload.get("scope_identity")
                    != digest({"requested_issue_ids": []})
                ):
                    raise ToolRefused("A narrowed task cannot silently add another dispute.")
        trusted = {
            "advocate_id": context.identity.advocate_id,
            "current_version": context.current_version,
            "turn_id": context.identity.turn_id,
            "message": context.original_message,
        }
        source = None
        if name == "record_prior_instruction":
            label, threads = args["new_dispute_label"], args["thread_ids"]
            if not (
                (label is not None and label.strip() and not threads) or (label is None and threads)
            ):
                raise ToolRefused("Choose either one new dispute or exact existing disputes.")
            source = instruction_source(matter, args, context)
            trusted.update(turn_id=source.record.identity.turn_id, message=source.original.text)
        try:
            if name == "record_prior_instruction":
                if args["new_dispute_label"] is not None:
                    mutation, detail = file_mutation.prepare_dispute(
                        matter, **trusted, label=args["new_dispute_label"], quoted=args["quoted"]
                    )
                else:
                    mutation, detail = file_mutation.prepare_admission(
                        matter, **trusted, thread_ids=args["thread_ids"], quoted=args["quoted"]
                    )
            elif name == "create_dispute":
                mutation, detail = file_mutation.prepare_dispute(matter, **trusted, **args)
            elif name == "write_fact":
                mutation, detail = file_mutation.prepare_admission(matter, **trusted, **args)
            elif name == "correct_fact":
                mutation, detail = file_mutation.prepare_correction(
                    matter, **trusted, **args, today=today()
                )
            elif name in ("record_requirement_answer", "record_existing_requirement_answer"):
                mutation, detail = file_mutation.prepare_requirement_answer(
                    matter, **trusted, **args, today=today()
                )
            else:
                mutation, detail = file_mutation.prepare_issue(matter, **trusted, **args)
        except file_mutation.MutationRefused as exc:
            raise ToolRefused(str(exc)) from exc
        if source is not None:
            detail = {
                **detail,
                "instruction_turn_id": source.record.identity.turn_id,
                "instruction_identity": source.original.text_identity,
                "instruction_provenance": source.original.provenance,
                "source_parent_identity": source.record.identity.fingerprint,
                "source_journal_identity": source.record.events[-1].fingerprint,
            }
        envelope = ToolEnvelope(
            name,
            PRIOR_VERSION if source else VERSION,
            ToolKind.MATTER,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "matter_id": matter.id,
                "matter_version": matter.version,
                "snapshot": mutation.identity,
            },
            {"operation": name, "changed_fields": list(mutation.changed_fields), **detail},
            "This checked file update does not establish factual or legal truth.",
        )
        return PreparedToolResult(envelope, mutation)

    from nm.work_the_file.tool_add_issue import build_tool as add_issue
    from nm.work_the_file.tool_correct_fact import build_tool as correct_fact
    from nm.work_the_file.tool_create_dispute import build_tool as create_dispute
    from nm.work_the_file.tool_record_existing_requirement_answer import (
        build_tool as record_existing_requirement_answer,
    )
    from nm.work_the_file.tool_record_prior_instruction import (
        build_tool as record_prior_instruction,
    )
    from nm.work_the_file.tool_record_requirement_answer import (
        build_tool as record_requirement_answer,
    )
    from nm.work_the_file.tool_write_fact import build_tool as write_fact

    return (
        create_dispute(prepare=prepare),
        write_fact(prepare=prepare),
        correct_fact(prepare=prepare),
        record_requirement_answer(prepare=prepare),
        record_existing_requirement_answer(prepare=prepare),
        add_issue(prepare=prepare),
        record_prior_instruction(prepare=prepare),
    )
