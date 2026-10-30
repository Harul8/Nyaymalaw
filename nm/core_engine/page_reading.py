"""The model reads scanned pages of an advocate's own documents (owner decision,
15 Oct 2026). No storage or network here; the page images arrive drawn.

A page with no text layer (a scan or a photograph) reaches the model as an image.
What it writes becomes that page's text for research, answers and quotation
checks, so the step reads, compares its text with the page and corrects itself
before answering. Code checks only the shape: a page the model could not read stays
unread with its reason, never an empty success. A page that could not be read now
(a provider failure) stays waiting to be read again.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_port import (USAGE_LIMIT_WORDS, ContentRefused, ModelError, PageImage, Prompt, Tier,
                                  UsageLimitReached)

CONTRACT = "core_page_reading_v1"
OPERATION = "core_page_reading"
MAX_OUTPUT = 12000
log = logging.getLogger(__name__)
#: Pages read at once for one document, and at once across every document being read in this process (plan AN.25, P3, 30 Oct
#: 2026): one upload of a long scan no longer waits in waves of four, and many uploads together never ask the AI service for
#: more than ALL_AT_ONCE reads. Chosen without a paid run (a bounded live run is still to confirm them): 20 pages are 3 waves
#: of about 15 s, not 5.
AT_ONCE = 8
ALL_AT_ONCE = 16
_SHARED = threading.BoundedSemaphore(ALL_AT_ONCE)

SYSTEM = """You read pages of documents that an Indian advocate has shared about a client's matter. Each page reaches you as an image because it has no text layer: it is a scan or a photograph. What you write becomes that page's text. The research, the answer and every quotation from this page will rely on it, so it must say what the page says.

Work in a loop. Read the page and write out its text. Then compare your text with the image, line by line, and correct anything you misread, skipped or added. Only then answer.

Give the text in reading order and in the language or languages it is written in; do not translate. Keep names, dates, amounts, numbers and headings exactly as written, and show a table row by row. Mention stamps, seals, signatures and handwriting briefly in square brackets where they appear, for example [signature] or [stamp: Registrar, City Civil Court]. Where words cannot be made out, write [illegible] in their place rather than guessing.

Then say how much of the page you could read: all of it, part of it, or none (a blank page, or one too unclear to read). Add a short note only if the advocate should know something about this page, such as an edge cut off in the photograph; otherwise leave the note empty."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "readable", "note"],
    "properties": {
        "text": {"type": "string"},
        "readable": {"type": "string", "enum": ["all", "part", "none"]},
        "note": {"type": "string"},
    },
}


def _call(result, number):
    usage = result.usage
    return {"operation": OPERATION, "page": number, "provider": result.provider, "model": result.model,
            "tokens_in": usage.tokens_in, "tokens_out": usage.tokens_out,
            "cached_tokens": usage.cached_tokens, "cost_usd": usage.cost_usd,
            "latency_ms": result.latency_ms, "retries": result.retries}


def read_page(model, name, number, image: bytes):
    """One page as the record keeps it, and the call that read it (None if none returned)."""
    prompt = Prompt(system=SYSTEM, operation=OPERATION,
                    user=f'Page {number} of the document "{name}".',
                    images=(PageImage("image/jpeg", image),))
    try:
        result = model.structured(prompt, SCHEMA, Tier.ROUTINE, max_tokens=MAX_OUTPUT)
    except ModelPermissionRefused:
        raise
    except ContentRefused:
        return {"number": number, "state": "unread", "code": "unreadable",
                "reason": "the AI declined to read this page"}, None
    except UsageLimitReached as exc:
        # The AI account has no credit left (owner decision P51, 25 Oct 2026): said in the owner's
        # words, and the page keeps waiting to be read again when that is put right - not "just now",
        # which promises a retry that cannot succeed. The provider's own words stay in the diagnosis.
        log.warning("A page waits to be read again: %s: %s", type(exc).__name__, exc)
        return {"number": number, "state": "unread", "code": "scanned", "reason": USAGE_LIMIT_WORDS}, None
    except ModelError as exc:
        # Expected provider outcomes (unavailable, cut short, malformed): the page waits.
        # Why is kept for diagnosis (17 Oct 2026): the failure's kind and message, no page text.
        log.warning("A page waits to be read again: %s: %s", type(exc).__name__, exc)
        return {"number": number, "state": "unread", "code": "scanned",
                "reason": "the AI could not read this page just now; it can be read again"}, None
    reading = result.data
    text, note = reading["text"].strip(), reading["note"].strip()
    if reading["readable"] == "none" or not text:
        reason = "the AI could not make out this page" + (f" ({note})" if note else "")
        return {"number": number, "state": "unread", "code": "unreadable", "reason": reason}, _call(result, number)
    page = {"number": number, "state": "read", "text": text, "read_by": "ai", "model": result.model,
            "legible": reading["readable"]}
    if note:
        page["note"] = note
    return page, _call(result, number)


def _read_within_the_shared_limit(model, name, number, image):
    with _SHARED:
        return read_page(model, name, number, image)


def read_pages(model, name, images, progress=None):
    """Every drawn page, a few at a time: {number: page} and the calls made. At most AT_ONCE for this document, and with every
    other document being read, at most ALL_AT_ONCE. progress(done, total): told after each page is read (plan AN.25, P4), from
    whichever thread read it, one at a time."""
    numbers = sorted(images)
    finished, lock = [0], threading.Lock()

    def read(number):
        page = _read_within_the_shared_limit(model, name, number, images[number])
        if progress is not None:
            with lock:
                finished[0] += 1
                progress(finished[0], len(numbers))
        return page

    with ThreadPoolExecutor(max_workers=min(AT_ONCE, max(1, len(numbers)))) as pool:
        done = list(pool.map(read, numbers))
    return ({page["number"]: page for page, _ in done},
            [call for _, call in done if call is not None])
