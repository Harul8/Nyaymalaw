"""The list_deadlines model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.Archives.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _STRING, VERSION, _date
from nm.Archives.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, object_schema
from nm.shared.model_port import ToolDefinition
from nm.work_the_file import deadlines


def build_tool(*, file_of, matter_result) -> RegisteredTool:
    def list_deadlines(args, context):
        matter = file_of(context)
        register = deadlines.read_matter(matter)
        today = _date(args["as_of"])
        partial = bool(register.unreadable or register.unassessed)
        return matter_result(
            "list_deadlines",
            matter,
            {
                "deadlines": [asdict(row) for row in deadlines.register(register.rows, today)],
                "unreadable": [asdict(problem) for problem in register.unreadable],
                "unassessed_threads": list(register.unassessed),
            },
            partial=partial,
            reason="Some deadlines could not be read or were not assessed." if partial else "",
        )

    return RegisteredTool(
        ToolDefinition(
            "list_deadlines",
            "Read the recorded register with incomplete entries disclosed.",
            object_schema({"as_of": _STRING}),
        ),
        ToolKind.MATTER,
        VERSION,
        True,
        _CONTROLS,
        list_deadlines,
    )
