"""The read_thread model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _STRING, VERSION
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.legal_brain.reason import requirements
from nm.shared.model_port import ToolDefinition


def build_tool(*, file_of, matter_result, today, source_current) -> RegisteredTool:
    def read_thread(args, context):
        from nm.work_the_file.event_observation_contracts import event_context

        matter = file_of(context)
        thread = next((row for row in matter.threads if row.id == args["thread_id"]), None)
        value = (
            {
                **asdict(thread),
                "event_context": event_context(thread, matter.facts),
                "checklist_context": requirements.context_projection(
                    thread,
                    matter.facts,
                    today(),
                    records=matter.loop_records,
                    source_current=source_current,
                ),
            }
            if thread
            else {}
        )
        return matter_result("read_thread", matter, value, found=thread is not None)

    return RegisteredTool(
        ToolDefinition(
            "read_thread",
            "Read one exact recorded dispute and the shared derived checklist, "
            "including due follow-ups without treating them as legal deadlines.",
            object_schema({"thread_id": _STRING}),
        ),
        ToolKind.MATTER,
        VERSION,
        True,
        _CONTROLS,
        read_thread,
    )
