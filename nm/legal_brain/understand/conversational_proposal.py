"""An exact private conversational candidate, never a merits/release shortcut.

The existing conversation principles and peer register guide the model's
language. This owner does not classify words as harmless or prescribe greetings.
A model-selected conversational label establishes neither that the text is
nonlegal nor that any supplied factual information may skip its own checks.
"""

from dataclasses import dataclass

from nm.legal_brain.orchestrate.loop_contracts import LoopIdentity
from nm.legal_brain.orchestrate.tools import (
    Assessment,
    RegisteredTool,
)

MAX_CONVERSATION_CHARACTERS = 16000


@dataclass(frozen=True)
class ConversationalProposal:
    text: str
    identity: LoopIdentity

    def __post_init__(self):
        if (
            not isinstance(self.text, str)
            or not self.text.strip()
            or len(self.text) > MAX_CONVERSATION_CHARACTERS
            or not isinstance(self.identity, LoopIdentity)
        ):
            raise ValueError(
                "A conversational candidate needs bounded exact text and its work identity"
            )

    def private_data(self):
        return {
            "text": self.text,
            "assessment_state": Assessment.NOT_ASSESSED.value,
            "client_ready": False,
            "released": False,
        }


def conversational_tool() -> RegisteredTool:
    """Expose an unreleased stopping choice, not permission to publish prose."""

    from nm.legal_brain.understand.tool_propose_conversation import (
        build_tool as propose_conversation_tool,
    )

    return propose_conversation_tool()
