"""How an advocate writes a provision reference. ONE copy, and this is it.

THE SECOND COPY BIT, EXACTLY AS THE RULE SAYS IT WILL
------------------------------------------------------
`nm/Archives/legal_brain/verify/grounding.py` had a pattern for reading provision references out of
emitted text. `nm/Archives/legal_brain/retrieve/corpus_evidence.py` had a different one for reading
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
from dataclasses import dataclass
from enum import Enum

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


#: A provision unit that NAMES ITS OWN KIND. An Act is not made only of
#: sections: the Limitation Act's periods are SCHEDULE ARTICLES, the CPC's
#: procedure is ORDERS and RULES, and a constitution has ARTICLES throughout.
#: Where the unit says what it is, it is rendered as it says.
_NAMES_ITS_KIND = re.compile(
    r"^\s*(article|order|rule|schedule|clause|regulation|part|chapter|form|"
    r"proviso|paragraph|para)\b", re.I)


def provision_label(act: str, unit: str) -> str:
    """One rendering of "this provision of this Act". ONE COPY, and this is it.

    THE MEASURED DEFECT, 23 September 2026, on a live matter. A possession
    brief was served this, as the authority it rested on:

        Limitation Act, 1963 s.Article_64 -- "For possession of immovable
        property based on previous possession"

    `s.Article_64`. Four sites built the reference as `f"{act} s.{section}"`,
    hard-coding the prefix for EVERY provision -- and the corpus's
    `section_number` column holds `Article_64` for a schedule article just as
    it holds `53A` for a section. The advocate reads a citation that does not
    exist in the form given, on the one line whose whole job is to let them
    check the source themselves.

    THE GENERAL RULE: THE PREFIX BELONGS TO THE UNIT'S KIND, NOT TO THE
    RENDERER. An Act is not made only of sections. The Limitation Act's
    periods are Schedule Articles, the CPC's procedure is Orders and Rules,
    and a unit that names its own kind is rendered as it names itself. Only a
    bare designation -- `53A`, `138` -- is a section and takes `s.`.

    Underscores become spaces because they are a STORAGE artefact of the atom
    id, never how anyone writes a citation.

    It lives here because CLAUDE.md section 4 puts every provision-reference
    pattern in this module and `tests/test_citation_patterns.py` fails the
    build on a second one. A renderer of the same references answers to the
    same rule: `SECTION` and `ARTICLE` above already know the two are
    different, and a renderer elsewhere that did not would be that second
    definition wearing a different hat.
    """
    unit = " ".join(str(unit or "").replace("_", " ").split())
    act = " ".join(str(act or "").split())
    if not unit:
        return act
    if _NAMES_ITS_KIND.match(unit):
        # `Article 64`, `Order VII Rule 11`, `Schedule I` -- said as written,
        # with the leading word capitalised the way a citation is.
        head, _, rest = unit.partition(" ")
        unit = f"{head[:1].upper()}{head[1:].lower()}" + (f" {rest}" if rest else "")
        return f"{act} {unit}" if act else unit
    return f"{act} s.{unit}" if act else f"s.{unit}"


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


#: Everything that is not a letter or a digit. THE EXACT KEY a reporter
#: citation is stored and looked up under: `AIR 1990 SC 1`, `AIR1990SC1` and
#: `A.I.R. 1990 S.C. 1` are one citation and one key. Upper-cased first, so
#: the class is written once.
_NOT_KEY = re.compile(r"[^A-Z0-9]")


def reporter_key(raw: str) -> str:
    """The exact key for a reporter citation. ONE OWNER, at build and at read.

    `pipeline/build_identity_index.py` writes `citations.citation_key` with this
    and `AuthorityIndexSearch.resolve` looks a typed citation up with it, so
    the two cannot disagree about what a citation is -- which is CLAUDE.md
    §4's question answered structurally. Exact match on this key reached
    90.9% of held judgments where name matching reached 0.83% (CLAUDE.md §5);
    nothing here ranks, and nothing here tolerates a near miss.
    """
    return _NOT_KEY.sub("", (raw or "").upper())


# Explicit tool/curation keys, not patterns for inference from narrative text.
# Keeping these here preserves the existing single provision-syntax owner.
_EXPLICIT_ORDER_RULE = re.compile(
    r"(?:Order|O)[_.\s]*([0-9]+|[IVXLCDM]+)[_.\s]*"
    r"(?:Rule|R)[_.\s]*([0-9]+[A-Za-z]*)", re.I | re.ASCII,
)
_EXPLICIT_ORDER = re.compile(
    r"(?:Order|O)[_.\s]*([0-9]+|[IVXLCDM]+)", re.I | re.ASCII,
)
_EXPLICIT_UNIT = re.compile(
    r"(Section|Sec|S|Article|Art|Rule|R)[_.\s]*([0-9]+[A-Za-z]*)", re.I | re.ASCII,
)
_EXPLICIT_NUMBER = re.compile(r"([0-9]+)([A-Za-z]*)", re.ASCII)
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_PARTS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


class ProvisionKeyState(str, Enum):
    BOUND = "bound"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class ProvisionKeyBinding:
    reference: str
    state: ProvisionKeyState
    key: str | None
    candidate_keys: tuple[str, ...]
    reason: str


def _roman_number(raw: str) -> str | None:
    letters = raw.upper()
    numbers = [_ROMAN_VALUES[letter] for letter in letters]
    value = sum(
        -number if index + 1 < len(numbers) and number < numbers[index + 1] else number
        for index, number in enumerate(numbers)
    )
    remaining, parts = value, []
    for number, spelling in _ROMAN_PARTS:
        count, remaining = divmod(remaining, number)
        parts.append(spelling * count)
    # No permissive subtraction or malformed-key repair (IC is not XCIX).
    return str(value) if value > 0 and "".join(parts) == letters else None


def _designation(raw: str) -> str | None:
    match = _EXPLICIT_NUMBER.fullmatch(raw)
    if match is None or match[1].startswith("0"):
        return None
    return match[1] + match[2].upper()


def _explicit_key_identity(raw: str) -> tuple[str, ...]:
    text = raw.strip()
    order_rule = _EXPLICIT_ORDER_RULE.fullmatch(text)
    if order_rule:
        numeral = order_rule[1]
        order = _designation(numeral) if numeral.isdecimal() else _roman_number(numeral)
        rule = _designation(order_rule[2])
        if order is not None and rule is not None:
            return ("order_rule", order, rule)
        return ("exact", text)
    order_only = _EXPLICIT_ORDER.fullmatch(text)
    if order_only:
        numeral = order_only[1]
        order = _designation(numeral) if numeral.isdecimal() else _roman_number(numeral)
        return ("order", order) if order is not None else ("exact", text)
    unit = _EXPLICIT_UNIT.fullmatch(text)
    if unit:
        kind = {"section": "section", "sec": "section", "s": "section",
                "article": "article", "art": "article", "rule": "rule", "r": "rule"}
        number = _designation(unit[2])
        if number is not None:
            return (kind[unit[1].lower()], number)
        return ("exact", text)
    number = _designation(text)
    return ("section", number) if number is not None else ("exact", text)


def bind_provision_key(reference: str, held_keys: tuple[str, ...]) -> ProvisionKeyBinding:
    """Bind explicit syntax to one exact key in the actual routed source owner.

    This is identity normalization, not law, date, applicability or corpus
    ranking. The caller supplies the complete actual key population for its
    already-routed source. Unknown syntax can match only its exact spelling;
    missing keys and multiple equivalent keys never choose a neighbour or a
    fuller store. Historical narrative extraction above is deliberately unchanged.
    """
    if type(reference) is not str or not reference.strip():
        raise ValueError("a provision key is explicit nonblank text")
    if (
        type(held_keys) is not tuple
        or any(type(key) is not str or not key.strip() for key in held_keys)
        or len(set(held_keys)) != len(held_keys)
    ):
        raise ValueError("held provision keys are one exact typed distinct owner population")
    identity = _explicit_key_identity(reference)
    candidates = tuple(sorted(key for key in held_keys if _explicit_key_identity(key) == identity))
    if len(candidates) == 1:
        return ProvisionKeyBinding(
            reference, ProvisionKeyState.BOUND, candidates[0], candidates,
            "one exact provision identity is held by the routed source; legal status not assessed",
        )
    if candidates:
        return ProvisionKeyBinding(
            reference, ProvisionKeyState.AMBIGUOUS, None, candidates,
            "multiple owner keys encode this provision identity; none selected",
        )
    return ProvisionKeyBinding(
        reference, ProvisionKeyState.NOT_FOUND, None, (),
        "the exact provision identity is not held in this routed source's key population",
    )
