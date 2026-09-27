"""An exact private conversational candidate, never a merits/release shortcut.

The existing conversation principles and peer register guide the model's
language. This owner does not classify words as harmless or prescribe greetings.
A model-selected conversational label establishes neither that the text is
nonlegal nor that any supplied factual information may skip its own checks.
"""
from dataclasses import dataclass

from nm.core.tools import (
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
from nm.domain.loop import LoopIdentity
from nm.ports.model import ToolDefinition

MAX_CONVERSATION_CHARACTERS = 16000


@dataclass(frozen=True)
class ConversationalProposal:
    text: str
    identity: LoopIdentity

    def __post_init__(self):
        if (not isinstance(self.text, str) or not self.text.strip()
                or len(self.text) > MAX_CONVERSATION_CHARACTERS
                or not isinstance(self.identity, LoopIdentity)):
            raise ValueError(
                "A conversational candidate needs bounded exact text and its work identity")

    def private_data(self):
        return {"text": self.text, "assessment_state": Assessment.NOT_ASSESSED.value,
                "client_ready": False, "released": False}


def conversational_tool() -> RegisteredTool:
    """Expose an unreleased stopping choice, not permission to publish prose."""
    name, version = "propose_conversation", "conversation-proposal-v1"

    def propose(args: dict, context: ToolContext):
        candidate = ConversationalProposal(args["text"], context.identity)
        return ToolEnvelope(name, version, ToolKind.CONTROL, ToolOutcome.RESULTS,
            Availability.AVAILABLE, Assessment.NOT_ASSESSED,
            {"operation": name, "turn_id": context.identity.turn_id,
             "work_identity": context.identity.fingerprint}, candidate.private_data(),
            "Conversational intent and exact wording have not been independently assessed. "
            "This candidate cannot release advice or bypass case, duty or publication checks.",
            Effect.CONVERSATION)

    return RegisteredTool(
        ToolDefinition(name,
            "Propose a natural conversational reply when the immediate interaction calls for "
            "acknowledgement rather than legal analysis or another question. Follow the current "
            "conversation principles and peer register; do not impose stock phrases. This is "
            "private unchecked wording, not a finding of nonlegal content or permission to "
            "publish. Supplied matter information still requires its own assessment.",
            object_schema({"text": {"type": "string", "minLength": 1,
                "description": "Exact proposed text; the owner enforces "
                "a 16,000-character bound."}})),
        ToolKind.CONTROL, version, False,
        ("test_conversation_proposals_are_not_a_merits_bypass",), propose,
        offer_role=OfferRole.INITIAL)
