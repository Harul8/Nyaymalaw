"""Figures that two copies of one page read differently (plan AN.27, P13; invariant I6).

Two scans of one passage were read separately by the AI and gave 6.06 and 6.16; NM called it a disagreement in the papers, then said
the advocate's figure could not be matched to either. A figure two readings give differently is for code to flag and for no model to
settle: the copies are found here, by their words, and the figures in which they differ are named with the words before them. Nothing
here says which reading is right. Only the figures of a stretch two readings give differently are named (plan AN.28, B9): words
that stand beside them in that stretch - a printed footer, a scanner's mark - are not figures and are not shown as if they were.

A page is a dict with "document" (its name), "key" (which document it belongs to - two files of one name are two documents), "page"
and "text", and may carry an "id", which is kept. Two pages are copies of one page when they are in different documents, say enough
to be called a page, hold much of their wording in common and agree on almost all of their figures; two pages of one form (a register's
rows, each with figures of its own) differ in too many to be copies. Only figures are compared: a word read differently is a misreading
the reader's notes may well explain, not a figure the advocate relies on.

Finding the copies among hundreds of pages takes seconds, and the board, the writer, the review and the date check each ask for them
(plan AN.27, P22): they are found once for a set of pages and kept for the last few sets, as places in the pages, so that a caller
whose pages say the same but carry other IDs is answered in its own.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import threading
from collections import OrderedDict

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
#: Plan AN.28, piece 4b (finding B6): a page that two papers hold at the same place among pages already found to be copies - at
#: least POSITION_PAIRS of them, at one offset, one of them beside it - is a copy too where the figures on the two pages are much
#: the same (SHARED_FIGURES of the fewer, MIN_FIGURES at least), however differently their words were read.
POSITION_PAIRS = 2
SHARED_FIGURES = 0.5
MIN_FIGURES = 3
#: The findings kept, in the papers' order.
MOST_FOUND = 20
#: How many sets of pages the copies are kept for.
KEPT = 8

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


def _differ(left, right, matcher=None):
    """The figures in which two copies' words differ: each how one reads it, how the other does, and the words just before it."""
    figures = []
    for tag, a, b, c, d in (matcher or difflib.SequenceMatcher(None, left, right, autojunk=False)).get_opcodes():
        ones, others = [w for w in left[a:b] if _figure(w)], [w for w in right[c:d] if _figure(w)]
        if tag != "replace" or not (ones and others):
            continue
        if _digits(ones) != _digits(others):
            figures.append({"first": " ".join(ones), "second": " ".join(others), "after": " ".join(left[max(0, a - 4):a])})
    return figures


def _pairs(pages):
    """Every two pages that are copies of one page, in the papers' order, each as (the first's place in `pages`, the second's, the
    figures in which they differ - none where they agree): by their words, then by their place among pages already paired and the
    figures they share (_by_position)."""
    found = list(_by_words(pages))
    return sorted(found + _by_position(pages, found), key=lambda pair: (pair[0], pair[1]))


def _by_position(pages, found):
    """Copies the words alone missed (plan AN.28, piece 4b): for two papers with POSITION_PAIRS or more pages paired at one offset, a
    page of each at that offset, neither paired, beside a pair at it, holding much the same figures. Their figures that differ are
    named only where they are few, as for any copies; past that they are copies all the same, with none named."""
    numbered = {}
    for index, page in enumerate(pages):
        if type(page.get("page")) is int and not page.get("recording"):
            numbered.setdefault(page["key"], {})[page["page"]] = index
    paired = {(one, two) for one, two, _ in found} | {(two, one) for one, two, _ in found}
    used = {index for one, two, _ in found for index in (one, two)}
    offsets = {}
    for one, two, _ in found:
        first, second = pages[one], pages[two]
        if type(first.get("page")) is int and type(second.get("page")) is int:
            counted = offsets.setdefault((first["key"], second["key"]), {})
            counted[second["page"] - first["page"]] = counted.get(second["page"] - first["page"], 0) + 1
    more = []
    for (key, other), counted in offsets.items():
        offset = max(counted, key=lambda step: (counted[step], -abs(step)))
        if counted[offset] < POSITION_PAIRS:
            continue
        for number, one in numbered.get(key, {}).items():
            two = numbered.get(other, {}).get(number + offset)
            if two is None or one in used or two in used:
                continue
            beside = [(numbered[key].get(number + step), numbered[other].get(number + offset + step)) for step in (-1, 1)]
            if not any(pair in paired for pair in beside):
                continue
            first, second = sorted((one, two))
            left, right = _words(pages[first]), _words(pages[second])
            ones, others = {w for w in left if _figure(w)}, {w for w in right if _figure(w)}
            if min(len(ones), len(others)) < MIN_FIGURES or len(ones & others) < SHARED_FIGURES * min(len(ones), len(others)):
                continue
            figures = _differ(left, right)
            if len(figures) > max(FEW_FIGURES, MOST_FIGURES * sum(map(_figure, left))):
                figures = []
            used |= {one, two}
            more.append((first, second, figures))
    return more


def _by_words(pages):
    """Every two pages whose words show them to be copies of one page, as (the first's place, the second's, their figures that
    differ)."""
    held = []
    for index, page in enumerate(pages):
        words = _words(page) if not page.get("recording") else []
        if len(words) >= MIN_WORDS:
            held.append((index, page["key"], words, set(zip(words, words[1:], words[2:]))))
    for first in range(len(held)):
        for second in range(first + 1, len(held)):
            (one, key, left, runs), (two, other_key, right, other) = held[first], held[second]
            if key == other_key or len(runs & other) < SHARED_RUNS * min(len(runs), len(other)):
                continue
            matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
            if matcher.ratio() < SIMILAR:
                continue
            figures = _differ(left, right, matcher)
            if len(figures) <= max(FEW_FIGURES, MOST_FIGURES * sum(map(_figure, left))):
                yield one, two, figures


_found, _guard = OrderedDict(), threading.Lock()


def _digest(pages):
    """What the pages say to the finder - each one's paper, number, words and whether it is a recording - and nothing else."""
    digest = hashlib.blake2b(digest_size=16)
    for page in pages:
        digest.update(repr((page["key"], page["page"], bool(page.get("recording")), len(page["text"]))).encode("utf-8"))
        digest.update(page["text"].encode("utf-8", "replace"))
    return digest.digest()


def _copies_among(pages):
    """(the pages as a list, the pairs among them): found once for these pages and kept for the next to ask (plan AN.27, P22), the
    last KEPT sets of pages only. The pairs are places in the pages, never the pages."""
    pages = list(pages)
    key = _digest(pages)
    with _guard:
        if key in _found:
            _found.move_to_end(key)
            return pages, _found[key]
    pairs = tuple((first, second, tuple(figures)) for first, second, figures in _pairs(pages))
    with _guard:
        _found[key] = pairs
        while len(_found) > KEPT:
            _found.popitem(last=False)
    return pages, pairs


def differences(pages):
    """The figures in which copies of one page read differently, as a list in the papers' order: each the two pages and, for each
    figure, how each copy reads it and the words just before it. Empty where there are no copies, or they agree."""
    pages, pairs = _copies_among(pages)
    found = [{"first": _place(pages[one]), "second": _place(pages[two]), "figures": [dict(figure) for figure in figures]}
             for one, two, figures in pairs if figures]
    return found[:MOST_FOUND]


def copies(pages):
    """Every pair of pages that are copies of one page, whether or not their figures agree (plan AN.27, P20 (b)): a set of
    {(key, page), (key, page)}. What a transaction a paper reports is, where another paper reports it on a copy of the same page,
    is for code to see by the pages' words, and for no reading of a name to hide."""
    pages, pairs = _copies_among(pages)
    return {frozenset({(pages[one]["key"], pages[one]["page"]), (pages[two]["key"], pages[two]["page"])}) for one, two, _ in pairs}
