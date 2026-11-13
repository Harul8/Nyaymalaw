"""One door for the short model sentences NM shows outside an answer (plan AN.51, piece 51b; D196; the review's F-09).

Outside an answer nothing a model writes is reviewed. Two small steps return a sentence to the advocate - how NM took a
follow-up, and how it took a message sent while a matter waits - and a third wording, the question put where NM could not tell.
Each was admitted as any text that was not empty and shown where the advocate expects NM's own status, so a reader that wrote
"I have corrected the date and re-worked the limitation period" would have been shown word for word beside code's true status.

Here code's own fixed sentence for the kind always stands first: it is NM's status. A model's wording is shown only after it,
marked as NM's reading, and only where it carries no link, asks for no secret, makes no claim that anything was, is being or
will be done, saved or changed (what was done is code's alone to say: P10), and is no longer than LONGEST. Wording that fails
any of these is left out whole: the reading is an extra, and code's sentence is complete without it.

The filter for links and secrets is the mid-turn questions' own (questions.py, their one owner). The filter for claims reads
English; a claim in another language is not caught by it, which is why code's sentence, never the model's, is the status.
"""
from __future__ import annotations

import re

from nm.core_engine.questions import _LINK, _SECRET  # one copy: the questions' filter, in its owner (a pinned piece, D143)

#: The longest reading shown, in characters; a longer one is cut at a word.
LONGEST = 300
#: How a model's wording is marked wherever it is shown.
MARK = "NM's reading:"

_ACTS = (r"saved|stored|recorded|updated|corrected|changed|amended|replaced|removed|deleted|added|re-?worked|re-?calculated|"
         r"re-?computed|re-?done|revised|fixed|filed|sent|submitted|applied|completed|finished|marked|noted|incorporated|"
         r"adjusted|done")
#: A claim that something was, is being or will be done: NM, "I" or "we" followed closely by an act; an act said of something
#: as done ("has been ...", "is now saved"); or what NM will do next. Wide on purpose - what it leaves out is only an extra.
_EFFECT = re.compile(
    rf"\b(?:i|we|nm)\b(?:'ve|'ll|'m|'re)?[^.?!;]{{0,40}}?\b(?:{_ACTS})\b"
    rf"|\b(?:has|have|had)\s+(?:now\s+|already\s+|just\s+)?been\b"
    rf"|\b(?:is|are|was|were|stands?|being)\s+(?:now\s+|already\s+|duly\s+|just\s+)?(?:{_ACTS})\b"
    rf"|\b(?:i|we|nm)(?:'ll|\s+will|\s+shall|\s+am\s+going\s+to|\s+is\s+going\s+to|\s+are\s+going\s+to)\b", re.I)


def reading(words) -> str:
    """A model's wording as NM may show it - one line, ended, at most LONGEST - or "" where it may not be shown."""
    if not isinstance(words, str):
        return ""
    line = " ".join(words.split())
    if not line or _LINK.search(line) or _SECRET.search(line) or _EFFECT.search(line):
        return ""
    if len(line) > LONGEST:
        line = line[:LONGEST].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return line if line[-1] in ".?!…" else line + "."


def after(code_says: str, shown: str) -> str:
    """Code's words, then a reading already admitted by `reading`, marked; code's words alone where there is none, or where
    the reading only repeats what code has said."""
    if not shown or shown.rstrip(".?!…").lower() in code_says.lower():
        return code_says
    return f"{code_says} {MARK} {shown}"


def said(fixed: str, words) -> str:
    """What NM says of a message: code's fixed sentence for its kind, then the model's wording, marked, where it may be shown."""
    return after(fixed, reading(words))


def asked(fixed: str, words) -> str:
    """The one question NM puts where it could not tell how a message was meant: the model's where it may be shown and is a
    question, else code's own."""
    shown = reading(words)
    return shown if shown.endswith("?") else fixed
