"""How an advocate writes a provision reference. ONE copy, and this is it.

THE SECOND COPY BIT, EXACTLY AS THE RULE SAYS IT WILL
------------------------------------------------------
`nm/core/grounding.py` had a pattern for reading provision references out of
emitted text. `nm/adapters/evidence/corpus.py` had a different one for reading
them out of a question. When the first was hardened against a false positive --
`O.S. 442/2023` parsing as "section 442", because `O.S. 442` contains `S. 442`
-- the second was not, because nothing connected them.

The consequence, found by running one realistic seven-turn scenario rather than
a unit test:

    "We act for the plaintiff in O.S. 442/2023 ... what is the step under
     section 6 of the Specific Relief Act?"

retrieved SECTION 442 of the Specific Relief Act, found nothing (there is no
s.442), reported NOT_HELD -- and the grounding gate then correctly withheld the
whole turn because the answer cited s.6 and s.6 had never been retrieved. Two
correct components, one wrong answer, and the defect living in the gap between
them.

CLAUDE.md's rule 4 is the fix: the question is not "where is the other copy"
but "what makes a second copy impossible". This module is that answer. Both
call sites import from here, and `tests/test_citation_patterns.py` asserts that
neither defines its own.
"""
from __future__ import annotations

import re

# The two guards, each learned by firing wrongly:
#
#   (?<![A-Za-z]\.)   a section marker preceded by another abbreviation
#                     letter-dot belongs to that abbreviation. `O.S. 442` is an
#                     Original Suit; `R.S.A. 12` a Regular Second Appeal.
#   (?![/ ]\s*(?:of\s*)?\d{4})
#                     `442/2023` and `442 of 2023` are numbers of record. No
#                     one writes a section that way.
_NOT_ABBREV = r"(?<![A-Za-z]\.)"
_NOT_CASE_NUMBER = r"(?![/ ]\s*(?:of\s*)?\d{4})"
_NUM = _NOT_CASE_NUMBER + r"(\d+[A-Za-z]{0,2})"

#: A section reference: `section 138`, `s. 6`, `sec 53A`.
SECTION = re.compile(_NOT_ABBREV + r"\b(?:sections?|sec\.?|s\.)\s*" + _NUM + r"\b", re.I)

#: A Schedule Article: `Article 65`, `art. 137`.
ARTICLE = re.compile(r"\b(?:articles?|art\.)\s*" + _NUM + r"\b", re.I)

#: An Order of the CPC: `Order XXXIX`.
ORDER = re.compile(r"\b(?:order)\s+([IVXL]+)\b", re.I)

#: Every provision reference in one pass, for coverage checking.
ANY_PROVISION = re.compile(
    SECTION.pattern + "|" + ARTICLE.pattern + "|" + ORDER.pattern, re.I)

#: A case name. Requires the ` v ` pivot with a capitalised token on each side,
#: so ordinary prose does not match. A false positive here withholds a good
#: turn, which is a real cost -- but a false NEGATIVE puts an invented citation
#: in front of a judge.
CASE = re.compile(
    r"\b([A-Z][\w.&'-]*(?:\s+[A-Z][\w.&'-]*){0,5})\s+"
    r"(?:v\.?|vs\.?|versus)\s+"
    r"([A-Z][\w.&'-]*(?:\s+[A-Z][\w.&'-]*){0,5})")


def wanted_section(text: str) -> str | None:
    """The provision a question is ASKING FOR, in the corpus's own key form.

    Sections come back as written; Schedule Articles as `Article_65`, because
    that is the `section_number` the chunks layer stores them under and all 137
    of them are absent from the parents layer entirely.
    """
    m = SECTION.search(text or "")
    if m:
        return m.group(1)
    a = ARTICLE.search(text or "")
    if a:
        return f"Article_{a.group(1)}"
    return None


def last_wanted_section(text: str) -> str | None:
    """The provision reference an ACCOUNT is asking for: the most recent one.

    `wanted_section` takes the first match, which is right for a single message
    -- an advocate leads with what they are asking about. It is wrong for an
    accumulated account, where the oldest sentence is the furthest from what
    they mean now. A thread that opened on one provision and moved to another
    would keep answering about the first, forever, and the answer would be
    correct about a provision nobody asked about.

    The rule, stated without naming a provision: IN A NARRATIVE, THE OPERATIVE
    REFERENCE IS THE LATEST ONE. In a question, it is the first.
    """
    text = text or ""
    last = None
    for m in SECTION.finditer(text):
        last = m.group(1)
    if last:
        # A section named later than any Article outranks it and vice versa, so
        # compare positions rather than preferring one kind outright.
        sec_at = max((m.start() for m in SECTION.finditer(text)), default=-1)
        art_at = max((m.start() for m in ARTICLE.finditer(text)), default=-1)
        if art_at > sec_at:
            arts = [m.group(1) for m in ARTICLE.finditer(text)]
            return f"Article_{arts[-1]}"
        return last
    arts = [m.group(1) for m in ARTICLE.finditer(text)]
    return f"Article_{arts[-1]}" if arts else None


def provisions_cited(text: str) -> set[str]:
    """Every provision NUMBER named in a piece of text, upper-cased."""
    out: set[str] = set()
    for groups in ANY_PROVISION.findall(text or ""):
        for g in (groups if isinstance(groups, tuple) else (groups,)):
            if g:
                out.add(g.upper())
    return out


def cases_named(text: str) -> set[str]:
    """Every case name in a piece of text."""
    return {f"{a.strip()} v {b.strip()}" for a, b in CASE.findall(text or "")}
