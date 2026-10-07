"""Build model context from the complete, user-visible saved conversation."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from nm.brain.conversation import Conversation, IncompleteConversation, Message

LEGACY_CONTEXT = "legacy_elements_v1"
PUBLIC_CONTEXT = "public_reply_v2"
# Fresh calls use public wording/order; saved executions select their own version.
CURRENT_CONTEXT = PUBLIC_CONTEXT


def context_contract(turn: Mapping) -> str:
    """The execution owner selects reconstruction, never a matching quotation."""
    response = turn.get("response", {})
    coverage = response.get("material_coverage", {}) if isinstance(response, Mapping) else {}
    execution = coverage.get("execution", {}) if isinstance(coverage, Mapping) else {}
    contract = (execution.get("context_contract", LEGACY_CONTEXT)
                if isinstance(execution, Mapping) else LEGACY_CONTEXT)
    if contract not in (LEGACY_CONTEXT, PUBLIC_CONTEXT):
        raise IncompleteConversation("The saved context contract is unsupported")
    return contract


def resolve_history(messages: Sequence[Message], contract: str) -> tuple[Message, ...]:
    """Reconstruct a declared historical view from canonical public messages.

    Compatibility metadata is ephemeral and server-owned. It preserves earlier
    exact source identities without rewriting durable records or their seals.
    """
    if contract == PUBLIC_CONTEXT:
        return tuple(messages)
    if contract != LEGACY_CONTEXT:
        raise IncompleteConversation("The saved context contract is unsupported")
    if any(item.legacy_text == "" for item in messages):
        raise IncompleteConversation("This public reply has no legacy transcript representation")
    numbered = [item for item in messages if item.legacy_order is not None]
    if len({item.legacy_order for item in numbered}) != len(numbered):
        raise IncompleteConversation("Historical conversation order is ambiguous")
    ordered = sorted(numbered, key=lambda item: item.legacy_order)
    ordered.extend(item for item in messages if item.legacy_order is None)
    return tuple(replace(item, text=item.legacy_text or item.text) for item in ordered)


def word_views(messages: Sequence[Message]) -> dict[str, dict[tuple[str, str], str]]:
    """Source lookups, not transcripts: unavailable legacy words have no entry.

    Public context stays complete. Full legacy replay still requires every
    message via resolve_history; a source lookup never invents missing words.
    """
    return {contract: {(item.turn_id, item.role): item.text
                       for item in resolve_history(
                           [item for item in messages if contract == PUBLIC_CONTEXT
                            or item.legacy_text != ""], contract)}
            for contract in (LEGACY_CONTEXT, PUBLIC_CONTEXT)}


def released_older_turns(store, matter) -> list[dict]:
    """Use the same authorised older transcript for readers and board citations."""
    from nm.open_matter.transcripts_api import project

    archived = store.transcripts_for(matter.id)
    older, problems = project(matter, archived, chronology_contract=CURRENT_CONTEXT)
    if (problems or any(row.get("unreadable") for row in archived)
            or not set(matter.turns_applied).issubset(
                {row.get("turn_id") for row in older})):
        raise IncompleteConversation("The saved matter conversation is incomplete")
    legacy = sorted(older, key=lambda row: (str(row.get("at") or ""), str(row["turn_id"])))
    positions = {row["turn_id"]: index for index, row in enumerate(legacy)}
    # Presentation copies only: receipt/archive rows and their seals stay intact.
    older = [{**row, "_legacy_order": positions[row["turn_id"]]} for row in older]
    from_turns(older, state="ok")
    return older


def from_turns(turns: Sequence[Mapping], *, state: str,
               matter_id: str | None = None, current_work: str = "",
               contract: str = CURRENT_CONTEXT) -> Conversation:
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
        if not isinstance(turn, Mapping):
            raise IncompleteConversation("A saved turn is unreadable")
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
        legacy_text = "\n".join(lines)
        composed = turn.get("composed", [])
        if (not isinstance(composed, list)
                or any(not isinstance(item, Mapping) or not isinstance(item.get("text"), str)
                       or not item["text"].strip() for item in composed)
                or (withheld and composed)):
            raise IncompleteConversation("A saved public reply is unreadable")
        public_text = "\n".join(item["text"] for item in composed) if composed else legacy_text
        if not public_text:
            raise IncompleteConversation("A released reply has no readable text")
        order = turn.get("_legacy_order")
        if order is not None and (type(order) is not int or order < 0):
            raise IncompleteConversation("Historical conversation order is unreadable")
        metadata = dict(recorded_at=turn.get("at"), context_contract=context_contract(turn))
        messages.extend((Message(turn_id, "advocate", words,
                                 legacy_order=order * 2 if order is not None else None,
                                 **metadata),
                         Message(turn_id, "nm", public_text, legacy_text=legacy_text,
                                 legacy_order=order * 2 + 1 if order is not None else None,
                                 **metadata)))
    return Conversation(resolve_history(messages, contract), current_matter_id=matter_id,
                        current_work=current_work)
