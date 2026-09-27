"""The search_matter model-facing door over its existing native owners."""

from __future__ import annotations

from dataclasses import asdict

from nm.legal_brain.orchestrate.tool_catalogue import _CONTROLS, _LIMIT, _STRING, VERSION
from nm.legal_brain.orchestrate.tools import RegisteredTool, ToolKind, ToolRefused, object_schema
from nm.open_matter.matter_documents_port import DocumentRefused
from nm.shared.model_port import ToolDefinition


def build_tool(*, file_of, matter_result, matter_documents) -> RegisteredTool:
    def search_matter(args, context):
        matter = file_of(context)
        query = args["query"].casefold()
        matches = []
        for fact in matter.facts:
            if query in fact.statement.casefold():
                matches.append({"locator": f"fact:{fact.id}", "fact": asdict(fact)})
        for receipt in matter.turn_receipts:
            receipt.validated_answer()
            if receipt.input_admitted and query in receipt.message.casefold():
                matches.append({"locator": f"turn:{receipt.turn_id}", "words": receipt.message})
        try:
            document_read = (
                matter_documents.search(
                    matter.id,
                    matter.advocate_id,
                    context.current_version,
                    args["query"],
                    limit=args["limit"],
                )
                if matter_documents is not None
                else None
            )
        except DocumentRefused as exc:
            raise ToolRefused(str(exc)) from exc
        if document_read is not None:
            matches.extend(document_read.matches)
        # A zero names the exact searched population and every unassessed
        # original. Uploaded text only joins this population through its owner.
        return matter_result(
            "search_matter",
            matter,
            {
                "matches": matches[: args["limit"]],
                "matched_count": (
                    len(matches)
                    if document_read is None
                    else len(matches) - len(document_read.matches) + document_read.matched_count
                ),
                "searched": [
                    "recorded facts",
                    "admitted canonical turn messages",
                    *(["bounded admitted document text"] if document_read is not None else []),
                ],
                "document_sources_searched": list(document_read.searched) if document_read else [],
                "not_searched": (
                    list(document_read.not_searched)
                    if document_read is not None
                    else ["admitted document text index"]
                ),
            },
            partial=document_read is None or document_read.partial,
            reason=(
                "Uploaded document text has not been read on this installation."
                if document_read is None
                else "Some originals or units were not searched; "
                "absence is only in the searched population."
                if document_read.partial
                else ""
            ),
        )

    return RegisteredTool(
        ToolDefinition(
            "search_matter",
            "Search recorded file text; upload-index absence stays explicit.",
            object_schema({"query": _STRING, "limit": _LIMIT}),
        ),
        ToolKind.MATTER,
        VERSION,
        True,
        _CONTROLS,
        search_matter,
    )
