"""Voice notes and dictation heard by the speech model (owner decisions, 15 Oct 2026:
gpt-transcribe through OpenAI, under the agreement the advocate accepted). No storage
or network here; the recording arrives checked and the model is bound for it.

A voice note's transcript becomes that recording's text for research, answers and
quotation checks, cited as the recording. Dictation comes back into the message box
for the advocate to check before sending, and its recording is not kept. Code checks
only the shape: a recording in which nothing was heard stays unread with its reason,
and a provider failure leaves it waiting to be transcribed again.
"""
from __future__ import annotations

import logging

from nm.core_engine.documents import AUDIO
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_port import ModelError

CONTRACT = "core_voice_v1"
OPERATION = "core_voice_note"
log = logging.getLogger(__name__)
#: What the speech model is told about a voice note; it does the hearing.
NOTE_PROMPT = ("A voice note an Indian advocate recorded about a client's matter: their own account, a "
               "client or witness speaking, or a call. It may mix English with Hindi or Telugu and name "
               "Indian courts, statutes, sections, places and people. Write what is said in the language "
               "spoken, Hindi in Devanagari and Telugu in Telugu script.")
DICTATION_PROMPT = ("An Indian advocate dictating a message to their legal research assistant: mostly English, "
                    "sometimes with Hindi or Telugu words, naming Indian courts, statutes, sections and people.")


def _call(heard, operation):
    return {"operation": operation, "provider": heard.provider, "model": heard.model,
            "latency_ms": heard.latency_ms, "retries": heard.retries, "usage": dict(heard.usage),
            "languages": list(heard.languages)}


def transcribe_note(model, name, data, fmt):
    """The recording's one unit as the record keeps it, and the call that heard it."""
    try:
        heard = model.transcribe(data, file_name=name, media_type=AUDIO[fmt], prompt=NOTE_PROMPT)
    except ModelPermissionRefused:
        raise
    except ModelError as exc:
        # Expected provider outcomes (unavailable, refused, malformed): the recording waits.
        # Why is kept for diagnosis (17 Oct 2026): the failure's kind and message, no words heard.
        log.warning("A recording waits to be transcribed again: %s: %s", type(exc).__name__, exc)
        return {"number": 1, "state": "unread", "code": "audio",
                "reason": "the recording could not be transcribed just now; it can be tried again"}, None
    text = heard.text.strip()
    if not text:
        return {"number": 1, "state": "unread", "code": "unreadable",
                "reason": "no speech was heard in this recording"}, _call(heard, OPERATION)
    page = {"number": 1, "state": "read", "text": text, "read_by": "ai", "model": heard.model, "legible": "all"}
    if heard.languages:
        page["note"] = "languages heard: " + ", ".join(heard.languages)
    return page, _call(heard, OPERATION)


def dictate(model, data, fmt):
    """The dictated words for the message box, and the call that heard them."""
    heard = model.transcribe(data, file_name=f"dictation.{fmt}", media_type=AUDIO[fmt], prompt=DICTATION_PROMPT)
    return heard.text.strip(), _call(heard, "core_dictation")
