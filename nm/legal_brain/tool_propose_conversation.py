"""The propose_conversation model-facing door over its existing native owners."""

from __future__ import annotations

from nm.legal_brain.conversational_proposal import ConversationalProposal
from nm.legal_brain.tools import (
    Assessment,
    Availability,
    Effect,
    OfferRole,
    RegisteredTool,
    ToolContext,
    ToolEnvelope,
    ToolKind,
    ToolOutcome,
    object_schema,
)
from nm.shared.model_port import ToolDefinition


def build_tool() -> RegisteredTool:
    name, version = "propose_conversation", "conversation-proposal-v1"

    def propose(args: dict, context: ToolContext):
        candidate = ConversationalProposal(args["text"], context.identity)
        return ToolEnvelope(
            name,
            version,
            ToolKind.CONTROL,
            ToolOutcome.RESULTS,
            Availability.AVAILABLE,
            Assessment.NOT_ASSESSED,
            {
                "operation": name,
                "turn_id": context.identity.turn_id,
                "work_identity": context.identity.fingerprint,
            },
            candidate.private_data(),
            "Conversational intent and exact wording have not been independently assessed. "
            "This candidate cannot release advice or bypass case, duty or publication checks.",
            Effect.CONVERSATION,
        )

    return RegisteredTool(
        ToolDefinition(
            name,
            "Propose a natural conversational reply when the immediate interaction calls for "
            "acknowledgement rather than legal analysis or another question. Follow the current "
            "conversation principles and peer register; do not impose stock phrases. This is "
            "private unchecked wording, not a finding of nonlegal content or permission to "
            "publish. Supplied matter information still requires its own assessment.",
            object_schema(
                {
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Exact proposed text; the owner enforces "
                        "a 16,000-character bound.",
                    }
                }
            ),
        ),
        ToolKind.CONTROL,
        version,
        False,
        ("test_conversation_proposals_are_not_a_merits_bypass",),
        propose,
        offer_role=OfferRole.INITIAL,
    )
