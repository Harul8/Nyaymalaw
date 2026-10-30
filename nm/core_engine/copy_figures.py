"""Figures that two copies of one page read differently (plan AN.27, P13; invariant I6).

Two scans of one passage were read separately by the AI and gave 6.06 and 6.16; NM called it a disagreement in the papers, then said
the advocate's figure could not be matched to either. A figure two readings give differently is for code to flag and for no model to
settle: the copies are found here, by their words, and the figures in which they differ are named with the words before them. Nothing
here says which reading is right.

A page is a dict with "document" (its name), "key" (which document it belongs to - two files of one name are two documents), "page"
and "text", and may carry an "id", which is kept. Two pages are copies of one page when they are in different documents, say enough
to be called a page, hold much of their wording in common and agree on almost all of their figures; two pages of one form (a register's
rows, each with figures of its own) differ in too many to be copies. Only figures are compared: a word read differently is a misreading
the reader's notes may well explain, not a figure the advocate relies on.
"""
from __future__ import annotations

import difflib
import re

from nm.core_engine import research

#: A page with fewer words says too little to be called a copy of another.
MIN_WORDS = 40
#: A cheap first look: the share of the shorter page's three-word runs the other holds as well.
SHARED_RUNS = 0.5
#: How much of two pages' words must agree for them to be copies of one page.
SIMILAR = 0.85
#: Copies differ in few figures: more than this many, and more than this share of the figures on a page, and they are two pages of
#: one form, not two copies.
FEW_FIGURES = 2
MOST_FIGURES = 0.2
#: The findings kept, in the papers' order.
MOST_FOUND = 20

#: Words and figures as a paper writes them: "6.06", "Ac.1.18", "30-10-1985", "596/80" stay whole.
_WORD = re.compile(r"[^\W_]+(?:[./-][^\W_]+)*")


def _words(page):
    return [word.casefold() for word in _WORD.findall(research._reading(page["text"]))]


def _figure(word):
    return any(character.isdigit() for character in word)


def _digits(words):
    return "".join(character for word in words for character in word if character.isdigit())


def _place(page):
    return {key: page[key] for key in ("document", "page", "key", "id") if key in page}


def _pairs(pages):
    """Every two pages that are copies of one page, in the papers' order, each with the figures in which they differ (none where they
    agree): the first, the second and a list of {"first", "second", "after"}."""
    held = []
    for page in pages:
        words = _words(page) if not page.get("recording") else []
        if len(words) >= MIN_WORDS:
            held.append((page, words, set(zip(words, words[1:], words[2:]))))
    for first in range(len(held)):
        for second in range(first + 1, len(held)):
            (one, left, runs), (two, right, other) = held[first], held[second]
            if one["key"] == two["key"] or len(runs & other) < SHARED_RUNS * min(len(runs), len(other)):
                continue
            matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
            if matcher.ratio() < SIMILAR:
                continue
            figures = []
            for tag, a, b, c, d in matcher.get_opcodes():
                if tag != "replace" or not (any(map(_figure, left[a:b])) and any(map(_figure, right[c:d]))):
                    continue
                if _digits(left[a:b]) != _digits(right[c:d]):
                    figures.append({"first": " ".join(left[a:b]), "second": " ".join(right[c:d]),
                                    "after": " ".join(left[max(0, a - 4):a])})
            if len(figures) <= max(FEW_FIGURES, MOST_FIGURES * sum(map(_figure, left))):
                yield one, two, figures


def differences(pages):
    """The figures in which copies of one page read differently, as a list in the papers' order: each the two pages and, for each
    figure, how each copy reads it and the words just before it. Empty where there are no copies, or they agree."""
    found = [{"first": _place(one), "second": _place(two), "figures": figures} for one, two, figures in _pairs(pages) if figures]
    return found[:MOST_FOUND]


def copies(pages):
    """Every pair of pages that are copies of one page, whether or not their figures agree (plan AN.27, P20 (b)): a set of
    {(key, page), (key, page)}. What a transaction a paper reports is, where another paper reports it on a copy of the same page,
    is for code to see by the pages' words, and for no reading of a name to hide."""
    return {frozenset({(one["key"], one["page"]), (two["key"], two["page"])}) for one, two, _ in _pairs(pages)}
