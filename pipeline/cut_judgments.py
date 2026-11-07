"""Cut a judgment on its own paragraphs (plan AN.45, D97-D98; owner, 5 Nov 2026: "Re-cut the judgments on their own paragraphs").

The search model reads 512 tokens. The judgments were cut before into fixed lengths, numbered in the order cut, so that "paragraph 12"
was often not the court's paragraph 12 and a quarter of the passages began in the middle of a sentence. Here:

  * A paragraph begins at a line that starts with its printed number. The judgment's paragraphs are the longest rising run of such
    numbers (a number may be missing; a numbered list inside a paragraph, starting again at 1, is not a paragraph). A judgment is cut
    on its printed numbers only where the run is long and whole enough (FEWEST_PARAGRAPHS, COVERAGE); otherwise it prints none for
    this purpose and is cut as unnumbered.
  * What stands before the first printed number - the court's heading, the bench, the headnote - is the judgment's opening.
  * A paragraph within LIMIT tokens is one passage. A longer one is split, at sentence ends, into the fewest parts of about equal
    size that each fit, and every part keeps the paragraph's number.
  * The opening, and the whole of a judgment printing no paragraph numbers, are cut at sentence ends into passages of about WINDOW
    tokens, which carry the court's number never: they are NM's own order, called "passage N".

Not one word of the judgment is removed or changed: every passage is a stretch of the raw text, and the stretches follow one another
with only blank space between. Sentence ends are told by code that does not take Mr., No., Sec., v., Rs., an initial or a decimal for
one. A stretch with no sentence end inside the limit is cut at a line end, and last at a word.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

#: What the search model reads is 512 tokens, two of them its own markers; a passage keeps ten tokens clear of that.
LIMIT = 500
#: Unnumbered text, and the opening of a judgment, are cut into passages of about this many tokens.
WINDOW = 320
#: A judgment is cut on its printed numbers only where the run reaches this many paragraphs ...
FEWEST_PARAGRAPHS = 5
#: ... and covers this share of the numbers from its first to its last (a few may be missing from the text) ...
COVERAGE = 0.75
#: ... starting at one of the first numbers (the first may be lost from the text), and rising by at most this much at a step.
FIRST_NUMBER = 3
MOST_STEP = 4
#: A printed paragraph is held as the court's paragraph for this many tokens at most (about five parts). What follows in the same
#: stretch - an order or annexure set after the last paragraph, a quotation run on - is cut as unnumbered text, so that no passage is
#: called "paragraph 8, part 54 of 68".
PARAGRAPH_MOST = 2400
#: A line that starts with a number and a full stop or bracket, the number not the start of a decimal or a date.
_MARK = re.compile(r"^[ \t]{0,12}(\d{1,3})[ \t]?[.)](?!\d)", re.M)
#: Where a sentence may end: a stop, question or exclamation mark, any closing quotation mark or bracket, then blank space.
_END = re.compile(r"[.?!][\"'”’)\]]*\s+")
#: Words before a stop that do not end a sentence.
_ABBREVIATIONS = frozenset((
    "mr mrs ms dr shri sri smt kum no nos sec secs ss art arts cl cls para paras vs v viz ie eg etc cf ors anr ltd pvt co inc rs re ex "
    "st hon jr sr j jj cj ac hc sc dt vol vols pp ed eds tel fax govt dept distt mohd md m/s hr hrs").split())


@dataclass(frozen=True)
class Passage:
    """One stretch of a judgment's raw text with its place: `text` is raw[start:end]."""
    start: int
    end: int
    text: str
    section: str          # "opening", "paragraph" or "text"
    paragraph: str        # the court's printed number, or "" (opening and unnumbered text)
    part: int             # 1-based place among the parts of its paragraph, or its window of the opening
    parts: int            # how many parts that paragraph, or the opening, was cut into
    order: int            # 1-based place in the judgment

    @property
    def locator(self) -> str:
        """What an answer and the reading pane call this passage."""
        if self.section == "text":
            return f"passage {self.order}"
        name = self.paragraph if self.section == "paragraph" else "opening"
        return f"{name} (part {self.part} of {self.parts})" if self.parts > 1 else name


@dataclass
class Cut:
    passages: list[Passage]
    numbering: str                                  # "printed" or "none"
    paragraphs: int = 0                             # printed paragraphs found
    first: int | None = None                        # the first and last printed numbers
    last: int | None = None
    notes: list[str] = field(default_factory=list)


def printed_run(raw: str) -> list[tuple[int, int]] | None:
    """The judgment's printed paragraphs: [(offset of the number, the number)] of the longest rising run, or None where the judgment
    prints no run long and whole enough to cut on."""
    marks = [(match.start(1), int(match.group(1))) for match in _MARK.finditer(raw)]
    if len(marks) < FEWEST_PARAGRAPHS:
        return None
    chain = [None] * len(marks)           # per mark: (length, numbers skipped, previous mark)
    by_number: dict[int, int] = {}        # per number: the mark ending the best run so far that ends in it
    best = None
    for index, (_, number) in enumerate(marks):
        top = None
        for before in range(number - 1, max(number - MOST_STEP - 1, 0), -1):
            held = by_number.get(before)
            if held is not None:
                length, skipped, _ = chain[held]
                candidate = (length + 1, skipped + (number - before - 1), held)
                if top is None or (candidate[0], -candidate[1]) > (top[0], -top[1]):
                    top = candidate
        if top is None and number <= FIRST_NUMBER:
            top = (1, number - 1, -1)
        if top is None:
            continue
        chain[index] = top
        held = by_number.get(number)
        # A tie goes to the earlier mark: the number that opens a paragraph comes before the same number in a list or a quotation
        # inside it (measured on 2,500 judgments, 244 had such a tie, and the earlier was the court's paragraph in most). The cost: a
        # list in a headnote numbered from 1 is taken for the first paragraphs.
        if held is None or (top[0], -top[1]) > (chain[held][0], -chain[held][1]):
            by_number[number] = index
        if best is None or (top[0], -top[1]) > (chain[best][0], -chain[best][1]):
            best = index
    if best is None:
        return None
    run, index = [], best
    while index != -1:
        run.append(marks[index])
        index = chain[index][2]
    run.reverse()
    span = run[-1][1] - run[0][1] + 1
    if len(run) < FEWEST_PARAGRAPHS or len(run) / span < COVERAGE:
        return None
    return run


def sentence_starts(text: str) -> list[int]:
    """Offsets in `text` where a sentence begins (not 0): after a stop, question or exclamation mark and blank space, unless the
    word before is an abbreviation or an initial or the next word begins in lower case."""
    starts = []
    for match in _END.finditer(text):
        at = match.end()
        if at >= len(text) or text[at].islower():
            continue
        words = text[:match.start() + 1].split()
        before = words[-1].rstrip(".?!\"'”’)]").lstrip("([\"'“‘").lower() if words else ""
        if text[match.start()] == "." and (before in _ABBREVIATIONS or (len(before) == 1 and before.isalpha())
                                           or (before.replace(".", "").isalpha() and "." in before and len(before.replace(".", "")) <= 3)):
            continue
        starts.append(at)
    return starts


def _pieces(raw: str, begin: int, end: int, count: Callable[[list[str]], list[int]]) -> list[tuple[int, int, int]]:
    """A stretch as its sentences: (start, end, tokens) of each, together the stretch less its blank space. A sentence longer than
    LIMIT is cut again at its line ends and, last, at words."""
    text = raw[begin:end]
    cuts = [0, *sentence_starts(text), len(text)]
    spans = [(begin + a, begin + b) for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]
    counts = count([raw[a:b] for a, b in spans]) if spans else []
    pieces = []
    for (a, b), tokens in zip(spans, counts):
        if tokens <= LIMIT:
            pieces.append((a, b, tokens))
        else:
            pieces.extend(_smaller(raw, a, b, count))
    return pieces


def _smaller(raw: str, begin: int, end: int, count) -> list[tuple[int, int, int]]:
    """A piece over LIMIT tokens, cut at its line ends; a line still over it, at words."""
    text = raw[begin:end]
    cuts = [0, *(m.end() for m in re.finditer(r"\n", text)), len(text)]
    spans = [(begin + a, begin + b) for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]
    out = []
    for (a, b), tokens in zip(spans, count([raw[a:b] for a, b in spans])):
        if tokens <= LIMIT:
            out.append((a, b, tokens))
            continue
        words = [m.start() for m in re.finditer(r"\S+", raw[a:b])]
        step = max(1, len(words) * (LIMIT - 20) // tokens)
        edges = [a + words[i] for i in range(0, len(words), step)] + [b]
        edges[0] = a
        for x, y in zip(edges, edges[1:]):
            if raw[x:y].strip():
                (tokens_xy,) = count([raw[x:y]])
                out.append((x, y, tokens_xy))
    return out


def _windows(pieces) -> list[list[tuple[int, int, int]]]:
    """Sentences gathered into passages of about WINDOW tokens, none over LIMIT; a small tail joins the passage before it."""
    groups, current, size = [], [], 0
    for piece in pieces:
        if current and size + piece[2] > WINDOW:
            groups.append(current)
            current, size = [], 0
        current.append(piece)
        size += piece[2]
    if current:
        groups.append(current)
    if len(groups) > 1 and sum(p[2] for p in groups[-1]) < WINDOW // 4 and (
            sum(p[2] for p in groups[-1]) + sum(p[2] for p in groups[-2]) <= LIMIT):
        groups[-2].extend(groups.pop())
    return groups


def _parts(pieces) -> list[list[tuple[int, int, int]]]:
    """Sentences gathered into the fewest parts that each fit LIMIT tokens, as near equal in size as the sentences allow."""
    total = sum(piece[2] for piece in pieces)
    if total <= LIMIT:
        return [pieces]

    def fill(cap):
        groups, current, size = [], [], 0
        for piece in pieces:
            if current and size + piece[2] > cap:
                groups.append(current)
                current, size = [], 0
            current.append(piece)
            size += piece[2]
        groups.append(current)
        return groups
    needed = len(fill(LIMIT))
    low, high = max(-(-total // needed), max(piece[2] for piece in pieces)), LIMIT
    while low < high:
        middle = (low + high) // 2
        if len(fill(middle)) <= needed:
            high = middle
        else:
            low = middle + 1
    return fill(high)


def cut(raw: str, count: Callable[[list[str]], list[int]]) -> Cut:
    """A judgment's raw text as passages. count(texts) gives the tokens of each text, as the search model's own tokenizer counts them
    without its two markers."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    run = printed_run(raw)
    stretches = []                                   # (section, paragraph, start, end)
    if run is None:
        stretches.append(("text", "", 0, len(raw)))
        result = Cut([], "none")
    else:
        if run[0][0] > 0 and raw[:run[0][0]].strip():
            stretches.append(("opening", "", 0, run[0][0]))
        for (at, number), (after, _) in zip(run, [*run[1:], (len(raw), 0)]):
            stretches.append(("paragraph", str(number), at, after))
        result = Cut([], "printed", len(run), run[0][1], run[-1][1])
    order = 0
    for section, paragraph, begin, end in stretches:
        if not raw[begin:end].strip():
            continue
        pieces = _pieces(raw, begin, end, count)
        tail = []
        if section == "paragraph":
            held, size = 0, 0
            while held < len(pieces) and size + pieces[held][2] <= PARAGRAPH_MOST:
                size += pieces[held][2]
                held += 1
            held = max(held, 1)
            pieces, tail = pieces[:held], pieces[held:]
            result.notes.extend([f"paragraph {paragraph} runs on: {len(tail)} sentences after its first {PARAGRAPH_MOST} tokens "
                                 "are cut as unnumbered text"] if tail else [])
        for kind, label, group in [*[(section, paragraph, g) for g in (_parts(pieces) if section == "paragraph" else _windows(pieces))],
                                   *[("text", "", g) for g in (_windows(tail) if tail else [])]]:
            a, b = group[0][0], group[-1][1]
            while a < b and raw[a].isspace():
                a += 1
            while b > a and raw[b - 1].isspace():
                b -= 1
            order += 1
            result.passages.append(Passage(a, b, raw[a:b], kind, label, 0, 0, order))
    # The place of each passage among its paragraph's parts (or the opening's windows), now that all are cut.
    sizes = {}
    for passage in result.passages:
        if passage.section != "text":
            sizes[(passage.section, passage.paragraph)] = sizes.get((passage.section, passage.paragraph), 0) + 1
    seen = {}
    placed = []
    for passage in result.passages:
        if passage.section == "text":
            placed.append(Passage(passage.start, passage.end, passage.text, "text", "", 1, 1, passage.order))
            continue
        key = (passage.section, passage.paragraph)
        seen[key] = seen.get(key, 0) + 1
        placed.append(Passage(passage.start, passage.end, passage.text, passage.section, passage.paragraph, seen[key], sizes[key],
                              passage.order))
    result.passages = placed
    return result
