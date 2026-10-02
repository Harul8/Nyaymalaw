"""Build model context from the complete, user-visible saved conversation."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from nm.brain.conversation import Conversation, IncompleteConversation, Message


def released_older_turns(store, matter) -> list[dict]:
    """Use the same authorised older transcript for readers and board citations."""
    from nm.open_matter.transcripts_api import project

    archived = store.transcripts_for(matter.id)
    older, problems = project(matter, archived)
    if (problems or any(row.get("unreadable") for row in archived)
            or not set(matter.turns_applied).issubset(
                {row.get("turn_id") for row in older})):
        raise IncompleteConversation("The saved matter conversation is incomplete")
    from_turns(older, state="ok")
    return older


def from_turns(turns: Sequence[Mapping], *, state: str,
               matter_id: str | None = None, current_work: str = "") -> Conversation:
    """Accept chronological saved turns only when every side can be recovered.

    ``turns`` is the authorised transcript projection. Its text is context,
    never an admission of a matter fact. A missing or withheld reply is carried
    by its released explanation, not by the model's unapproved draft.
    """
    if state != "ok":
        raise IncompleteConversation("The saved conversation is incomplete")
    messages: list[Message] = []
    seen: set[str] = set()
    for turn in turns:
        turn_id = turn.get("turn_id")
        words = turn.get("message")
        if (not isinstance(turn_id, str) or not turn_id.strip() or turn_id in seen
                or not isinstance(words, str) or not words.strip()
                or turn.get("message_source") == "not_held"):
            raise IncompleteConversation("A saved turn has no attributable user message")
        seen.add(turn_id)
        elements = turn.get("elements")
        if not isinstance(elements, list):
            raise IncompleteConversation("A saved turn has no readable reply")
        released = (turn.get("committed") is True
                    and turn.get("release_state") in ("released", "legacy_released"))
        withheld = (turn.get("committed") is False
                    and turn.get("release_state") == "withheld")
        if not released and not withheld:
            raise IncompleteConversation("The saved reply has no established release status")
        if withheld and elements:
            raise IncompleteConversation("An unreleased draft cannot enter conversation context")
        lines = []
        for element in elements:
            if not isinstance(element, Mapping) or not isinstance(element.get("text"), str):
                raise IncompleteConversation("A saved reply contains unreadable text")
            if element["text"].strip():
                lines.append(element["text"])
        if not lines and withheld:
            explanation = turn.get("blocked_reason")
            if not isinstance(explanation, str) or not explanation.strip():
                raise IncompleteConversation("A saved turn has no readable reply")
            lines.append(explanation)
        if not lines:
            raise IncompleteConversation("A released reply has no readable text")
        messages.extend((Message(turn_id, "advocate", words),
                         Message(turn_id, "nm", "\n".join(lines))))
    return Conversation(tuple(messages), current_matter_id=matter_id,
                        current_work=current_work)
