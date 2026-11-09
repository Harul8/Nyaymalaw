"""Plan AN.48, piece 48e: tentative times (owner decision D140, 9 Nov 2026: "Yes, and call it tentatively").

After Send and at each stop, NM says how long its next step should take, labelled tentative; each estimate is kept beside the time
the step took (steps.timed), so that the two can be compared and the figures below corrected. Cost stays internal (AN.37).

The figures are rough, from the times measured on the owner's saved turns and the recorded baseline (plan AN.48, column 7): the
understanding of a one-page matter took about 4.6 minutes and of a 57-page one about 12; the research of three to five disputes,
side by side, about 1.5 to 3; their analyses from about 5 minutes for three to about 40 for five, where the reviews asked for many
repairs; the check across the analyses and the overview about 1 to 5. Each step is a base and an amount for each page read, dispute
researched or written, or analysis checked across - in seconds.
"""
from __future__ import annotations

#: step -> (base seconds, seconds for each page read / dispute researched or written / analysis checked across).
FIGURES = {"understand": (270, 8), "research": (60, 30), "write": (180, 100), "finish": (60, 30)}


def seconds(step, count):
    """A step's tentative time in seconds, for the pages read (understand), the disputes researched or written, or the analyses
    checked across (finish)."""
    base, each = FIGURES[step]
    return int(base + each * max(0, int(count)))


def said(total):
    """A tentative time in the advocate's words: about so many minutes, never less than one."""
    minutes = max(1, round(int(total) / 60))
    return f"about {minutes} minute{'s' if minutes != 1 else ''}"


def pages_of(documents):
    """The pages a message's papers carry, as the understanding reads them."""
    return sum(len(document.get("pages") or ()) for document in documents or () if isinstance(document, dict))
