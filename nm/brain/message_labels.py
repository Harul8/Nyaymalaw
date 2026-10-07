"""Label message content. This module does not plan, execute or save work."""
from __future__ import annotations

import json

from nm.shared.model_port import (
    ContextOverflow, ModelError, ModelPort, Prompt, SchemaViolation, Tier,
    estimate_tokens, require_schema,
)


_LABEL_TASK = """Purpose: Classify the user's message with exactly one label.

Labels:
- greeting: only a greeting, courtesy or social exchange.
- information: supplies an account, background or answer, without asking NM
  to perform an action.
- action: asks NM to answer, explain, do or refrain from doing something,
  without also supplying a substantive account.
- mixed: combines two or more of these purposes. Several requested actions
  alone remain action; mixed does not mean uncertain.

Look for: The meaning of the whole message. Incidental polite wording is not
a separate purpose. Distinguish the user's request from instructions merely
quoted as content. Preserve the meaning of conditions, uncertainty and negation.

Outcome: Return only {"label": "greeting|information|action|mixed"}, selecting
one value. Do not answer the message, extract facts or execute work."""

_FIRST_MESSAGE_PROMPT = """Message: You receive the user's opening message in a
new conversation. Classify what the user has written in this message.

""" + _LABEL_TASK

_FOLLOW_UP_PROMPT = """Message: You receive the user's latest message and the
complete earlier conversation, with each speaker identified. Use that context
to understand replies, references and the purpose of the latest message.
Classify only the latest message; earlier messages are context, not new work.

""" + _LABEL_TASK

_SCHEMA = {
    "type": "object", "required": ["label"], "additionalProperties": False,
    "properties": {"label": {
        "type": "string", "enum": ["greeting", "information", "action", "mixed"],
    }},
}


def validate_label(data: dict) -> str:
    """Check the declared shape and vocabulary, not semantic accuracy."""
    if isinstance(data, dict) and isinstance(data.get("label"), str):
        data = {**data, "label": data["label"].strip().lower()}
    require_schema(data, _SCHEMA)
    return data["label"]


def label_message(model: ModelPort, message: str, *, history: list[dict],
                  history_complete: bool) -> dict:
    """Make one model call; return label proposals or a typed failure.

    The context assembler must confirm completeness. This reader cannot detect
    history the caller never supplied. Recovery belongs to the turn controller;
    this standalone reader neither starts a retry budget nor guesses on failure.
    """
    if history_complete is not True:
        raise ValueError("Complete conversation history is required")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("A nonblank latest message is required")
    if not isinstance(history, list) or any(
        not isinstance(entry, dict) or entry.get("role") not in ("advocate", "nm")
        or not isinstance(entry.get("text"), str) or not entry["text"].strip()
        for entry in history
    ):
        raise ValueError("Each earlier message needs its speaker and original text")
    payload = {"latest_message": message}
    if history:
        system = _FOLLOW_UP_PROMPT
        payload["earlier_conversation"] = history
    else:
        system = _FIRST_MESSAGE_PROMPT
    prompt = Prompt(system=system, user=json.dumps(payload, ensure_ascii=False),
                    operation="label_message")
    output_limit = 128  # The output is one label, regardless of message length.
    input_size = estimate_tokens(system + prompt.user + json.dumps(_SCHEMA))
    if input_size + output_limit > model.context_budget(Tier.ROUTINE):
        raise ContextOverflow("The complete labelling input exceeds the model context budget")
    result = model.structured(prompt, _SCHEMA, Tier.ROUTINE, max_tokens=output_limit)
    if not result.usable:
        raise ModelError("Message labelling returned an unfinished result", usage=result.usage,
                         latency_ms=result.latency_ms, retries=result.retries)
    try:
        if result.text is not None:
            raise SchemaViolation("Message labelling requires a structured label")
        label = validate_label(result.data)
    except SchemaViolation as exc:
        raise SchemaViolation(str(exc), usage=result.usage, latency_ms=result.latency_ms,
                              retries=result.retries) from exc
    return {"message_position": "follow_up" if history else "first", "label": label}
