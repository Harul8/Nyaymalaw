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

import json
import logging
import re
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

#: Plan AN.28, piece 4a (finding B6): a reading that may leave the page's text incomplete is read again once, against the image -
#: ILLEGIBLE_MOST places marked [illegible] or more than ILLEGIBLE_SHARE of its words, a place where the reader says it left text out,
#: or a page only partly read. The first reading is kept beside the second.
ILLEGIBLE_MOST = 3
ILLEGIBLE_SHARE = 0.02
_ILLEGIBLE = re.compile(r"\[\s*illegible[^\]]*\]", re.I)
_LEFT_OUT = re.compile(r"\[\s*(?:\.{3,}|…|[^\]]{0,60}?\b(?:omitted|not transcribed|not reproduced|continues|continued|remaining|rest of|"
                       r"truncated|and so on|etc)\b[^\]]{0,60}?)\]|^\s*(?:\.\s*){3,}$|^\s*…\s*$", re.I | re.M)
LOOK_AGAIN = """

You read this page before. Your first reading follows the page's name, with what code found in it that may leave the page's text incomplete. Look at the image again, place by place: write what the page says where you marked it unreadable or left text out, keeping [illegible] only where the image truly cannot be made out, and leave nothing out - a long table or a repeated entry is written out in full. Compare your text with the image line by line and correct it before you answer."""

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


#: Plan AN.28, piece 4c (findings A8, A9): the figures two copies of one page read differently, looked at again on both images.
RELOOK_OPERATION = "core_page_relook"
RELOOK_OUTPUT = 4000
RELOOK = """You receive the images of two pages that code found to be copies of one page, read separately, and the figures in which the two readings differ, each with the words just before it. Look at each image at that place and write the figure exactly as that image shows it - figures, letters and punctuation as written - or "unclear" where the image cannot settle it. Say what each image shows: do not choose between the copies, and do not correct one by the other.
Work in a loop: find each place on both images, write what each shows, compare what you wrote with the images, and correct it before you answer."""
RELOOK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["figures"], "properties": {"figures": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["after", "first_shows", "second_shows"],
                               "properties": {"after": {"type": "string"}, "first_shows": {"type": "string"},
                                              "second_shows": {"type": "string"}}}}}}


def corrected(text, read, shows, after):
    """A page's text with one figure as its image shows it (piece 4c), or the text unchanged: where the image shows a figure, it differs
    from the reading, and the reading's figure stands in the text once - or once after the words before it. A figure of more than one
    word, or one that cannot be placed, is left as read."""
    shows, read = " ".join(str(shows).split()), " ".join(str(read).split())
    if (not shows or shows.casefold() == "unclear" or not any(c.isdigit() for c in shows) or " " in read or " " in shows
            or shows.casefold() == read.casefold()):
        return text
    alone = rf"(?<![\w./-]){re.escape(read)}(?![\w./-])"
    spans = [(match.start(), match.end()) for match in re.finditer(alone, text, re.I)]
    if len(spans) != 1 and after.split():
        before = r"\W+".join(map(re.escape, after.split()))
        spans = [(match.start(1), match.end(1)) for match in re.finditer(before + r"\W+(" + alone + ")", text, re.I)]
    if len(spans) != 1:
        return text
    start, end = spans[0]
    # The page's own letters before the figure (Ac. of Ac.6.16) stay where the image is read for the figure alone.
    lead = re.match(r"\D*", text[start:end]).group(0)
    return text[:start] + (lead + shows if shows[:1].isdigit() else shows) + text[end:]


def relook(model, first, second, figures):
    """Figures two copies of one page read differently, looked at again on both images (plan AN.28, piece 4c, D2 and D3). first,
    second: {"name", "number", "image", "text"}; figures: as copy_figures.differences gives them. Returns (the first page's text as
    corrected, or None where unchanged; the second's; the call). What each image shows is the model's to read; code places it."""
    user = (f'The first image is page {first["number"]} of "{first["name"]}"; the second is page {second["number"]} of '
            f'"{second["name"]}".\n\n' + json.dumps({"figures": [{"after": figure["after"], "first_reads": figure["first"],
                                                                   "second_reads": figure["second"]} for figure in figures]},
                                                     ensure_ascii=False))
    prompt = Prompt(system=RELOOK, operation=RELOOK_OPERATION, user=user, effort="medium",
                    images=(PageImage("image/jpeg", first["image"]), PageImage("image/jpeg", second["image"])))
    result = model.structured(prompt, RELOOK_SCHEMA, Tier.ROUTINE, max_tokens=RELOOK_OUTPUT)
    shown = list(result.data["figures"])
    if len(shown) != len(figures):
        by_after = {item["after"].casefold(): item for item in shown}
        shown = [by_after.get(figure["after"].casefold()) for figure in figures]
    one, two = first["text"], second["text"]
    for figure, seen in zip(figures, shown):
        if seen is not None:
            one = corrected(one, figure["first"], seen["first_shows"], figure["after"])
            two = corrected(two, figure["second"], seen["second_shows"], figure["after"])
    return (one if one != first["text"] else None, two if two != second["text"] else None, _call(result, first["number"]))


def _call(result, number):
    usage = result.usage
    return {"operation": OPERATION, "page": number, "provider": result.provider, "model": result.model,
            "tokens_in": usage.tokens_in, "tokens_out": usage.tokens_out,
            "cached_tokens": usage.cached_tokens, "cost_usd": usage.cost_usd,
            "latency_ms": result.latency_ms, "retries": result.retries}


def doubts(reading):
    """What code finds in a reading that may leave the page's text incomplete (plan AN.28, piece 4a): places marked [illegible] -
    ILLEGIBLE_MOST or more, or more than ILLEGIBLE_SHARE of the words - places where the reader says it left text out, and a page
    said to be only partly readable. Empty where there is none."""
    text = reading["text"]
    marked, words, left = len(_ILLEGIBLE.findall(text)), len(text.split()), len(_LEFT_OUT.findall(text))
    found = []
    if marked and (marked >= ILLEGIBLE_MOST or marked / max(words, 1) > ILLEGIBLE_SHARE):
        found.append(f"{marked} place{'s' if marked != 1 else ''} marked [illegible]")
    if left:
        found.append(f"{left} place{'s' if left != 1 else ''} where the reading says text was left out")
    if reading["readable"] == "part":
        found.append("the reading says only part of the page could be read")
    return found


def read_page(model, name, number, image: bytes):
    """One page as the record keeps it, and the calls that read it. A reading code finds may be incomplete (doubts) is read again
    once against the image (plan AN.28, piece 4a, D2): the second reading is the page's text, the first kept beside it where they
    differ; a second look that fails leaves the first reading as it was."""
    page, call = _read_once(model, name, number, image)
    if call is None or page["state"] != "read" or not page.get("_doubts"):
        page.pop("_doubts", None)
        return page, [call] if call is not None else []
    found = page.pop("_doubts")
    again, second = _read_once(model, name, number, image, first=page["text"], found=found)
    calls = [call] + ([second] if second is not None else [])
    if second is None or again["state"] != "read":
        return page, calls
    again.pop("_doubts", None)
    if again["text"] != page["text"]:
        again["first_reading"] = page["text"]
    return again, calls


def _read_once(model, name, number, image, *, first=None, found=()):
    """One reading of a page as the record keeps it (with what code doubts in it, under "_doubts"), and the call that read it (None
    if none returned). first: the first reading, for a second look, with what code found in it."""
    user = f'Page {number} of the document "{name}".'
    if first is not None:
        user += ("\n\nYour first reading:\n" + first + "\n\nWhat code found in it: " + "; ".join(found) + ".")
    # A second look reasons a level above the first reading's own setting (plan AN.28, D4).
    prompt = Prompt(system=SYSTEM + (LOOK_AGAIN if first is not None else ""), operation=OPERATION, user=user,
                    images=(PageImage("image/jpeg", image),), effort="medium" if first is not None else None)
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
            "legible": reading["readable"], "_doubts": doubts({"text": text, "readable": reading["readable"]})}
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
            [call for _, calls in done for call in calls])
