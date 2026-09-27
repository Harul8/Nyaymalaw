"""The read_practice_playbook model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.shared.model_port import ToolDefinition


def build_tool(*, current, envelope, snapshot, evidence, search, controls) -> RegisteredTool:
    def read(args, context):
        current()
        rows = [row for row in snapshot.payload["playbooks"] if row["id"] == args["id"]]
        if len(rows) != 1:
            raise ToolRefused("That exact playbook is not in the admitted owner catalogue.")
        pointers = []
        for pointer in rows[0]["pointers"]:
            if pointer["kind"] == "act_section":
                result = evidence.read_provision(pointer["act"], pointer["section"], as_of=None)
                held = bool(result.findings)
                pointers.append(
                    {
                        **pointer,
                        "state": "located_not_assessed" if held else "not_located",
                        "locators": [row.locator for row in result.findings],
                        "reason": "A held passage does not establish current applicability."
                        if held
                        else "The pointed provision is not established in the held population.",
                    }
                )
            elif search is not None:
                result = search.resolve(pointer["citation"])
                pointers.append(
                    {
                        **pointer,
                        "state": "not_assessed",
                        "reason": "The exact identity lookup was performed; paragraph support and "
                        "applicability still require an actual source read.",
                        "resolution": result.state.value,
                    }
                )
            else:
                pointers.append(
                    {
                        **pointer,
                        "state": "not_assessed",
                        "reason": "No exact judgment-identity reader is configured.",
                    }
                )
        current()
        return envelope(
            "read_practice_playbook", {"playbook": rows[0], "pointers": pointers}, context
        )

    return RegisteredTool(
        ToolDefinition(
            "read_practice_playbook",
            "Read an exact owner-edited "
            "playbook and inspect its source pointers. Never apply periods or rules from "
            "guidance; retrieve the actual legal source and assess applicability.",
            object_schema({"id": {"type": "string", "minLength": 1}}),
        ),
        ToolKind.CONTROL,
        snapshot.version,
        True,
        controls,
        read,
    )
