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


# ============================================ reporter citations in text ====
#
# HOW A CASE CITATION IS WRITTEN, ONE COPY. The identity build reads judgment
# bodies for treatment with this and the citation engine reads an advocate's
# text with it, so a citation the build could link is one the advocate's check
# can find.
#
# A citation yields EXACT KEYS: the key of the citation as written, then the
# keys of the reporter names listed below as meaning the same series. Every
# key is looked up exactly. When two keys lead to different judgments the
# caller reports both; nothing here or there picks one.
#
# THE EQUIVALENTS ARE MEASURED, NOT ASSUMED (9 October 2026, case identity
# index, 302,909 keys). The index holds 16,055 of its 18,041 AIR Supreme Court
# citations only as `AIR 1973 SUPREME COURT 1461`, so the form advocates write,
# `AIR 1973 SC 1461`, read as not held. Checked pair by pair:
#
#   AIR "SC" = "Supreme Court"     1,895 shared keys agree; 73 lead to the same
#                                  judgment held twice; 18 lead to different
#                                  judgments -- shown as ambiguous, never picked
#   AIR "AP" = "Andhra Pradesh"    1,091 agree; 1 is the same judgment held twice
#   ALT and "Andh LT",             NOT the same series: the same volume and page
#   ALD and "Andh LD"              lead to a High Court case under one and a
#                                  Supreme Court case under the other (18 of 20
#                                  and 14 of 16 overlaps), so they are never merged
#   "ALD (Cri)" and "ALD (Crl)"    4 of 19 overlaps disagree; kept apart
#   SCR volume order               `[1964] 1 SCR 561` is held as `1964 SCR (1) 561`:
#                                  2,271 keys held both ways agree, 100 lead to a
#                                  different judgment (shown as ambiguous)
#   SCC Supp order                 `1993 Supp (3) SCC 575` is held as `1993 SCC
#                                  Supp (3) 575`: 96 agree, 4 differ
#
# An equivalent is added only with a measurement like these.

_YEAR = r"(?:18|19|20)\d{2}"


@dataclass(frozen=True)
class _Reporter:
    name: str
    written: str
    token: str | None
    """The letters the index keys carry for this series, when a written
    spelling differs from them (`Crl LJ` is held as `CRILJ`). None: the
    citation is looked up only as written."""
    example: str
    volume_order: str | None = None
    """The measured other order of the same parts, used when a volume is written."""
    supplement_order: str | None = None
    """The measured other order, used when a supplementary volume is written."""


#: Year-first reporters: `(2018) 5 SCC 379`, `2005 (3) ALT 456`, `2023 INSC 123`.
#: Order matters: a longer name is tried before its own prefix.
_VOLUME_REPORTERS = (
    _Reporter("SCC (Cri)", r"S\.?\s?C\.?\s?C\.?\s*\(\s*Cri?(?:l|minal)?\.?\s*\)", "SCCCRI",
              "(2010) 1 SCC (Cri) 123"),
    _Reporter("SCC (L&S)", r"S\.?\s?C\.?\s?C\.?\s*\(\s*L\s*&\s*S\s*\)", "SCCLS", "(2015) 2 SCC (L&S) 45"),
    _Reporter("SCC (Tax)", r"S\.?\s?C\.?\s?C\.?\s*\(\s*Tax\s*\)", "SCCTAX", "(2014) 3 SCC (Tax) 12"),
    _Reporter("SCC OnLine SC", r"S\.?\s?C\.?\s?C\.?\s*On\s?Line\s*S\.?\s?C\.?", "SCCONLINESC",
              "2021 SCC OnLine SC 512"),
    _Reporter("SCC", r"S\.?\s?C\.?\s?C\.?", "SCC", "(2018) 5 SCC 379",
              supplement_order="{year}SCCSUPP{volume}{page}"),
    _Reporter("SCR", r"S\.?\s?C\.?\s?R\.?", "SCR", "[1964] 1 SCR 561",
              volume_order="{year}SCR{volume}{page}"),
    _Reporter("SCALE", r"SCALE", "SCALE", "(2019) 4 SCALE 101"),
    _Reporter("INSC", r"INSC", "INSC", "2023 INSC 123"),
    _Reporter("SCJ", r"S\.?\s?C\.?\s?J\.?", "SCJ", "1956 SCJ 243"),
    _Reporter("Cri LJ", r"Cr(?:i|l)?\.?\s?L\.?\s?J\.?", "CRILJ", "2005 Cri LJ 1234"),
    _Reporter("AIR SCW", r"A\.?\s?I\.?\s?R\.?\s?S\.?\s?C\.?\s?W\.?", "AIRSCW", "2005 AIR SCW 123"),
    _Reporter("AIR", r"A\.?\s?I\.?\s?R\.?", "AIR", "1973 AIR 1461"),
    _Reporter("ALT (Cri)", r"A\.?\s?L\.?\s?T\.?\s*\(\s*Cri?l?\.?\s*\)", "ALTCRI", "2008 (2) ALT (Crl) 34"),
    _Reporter("ALT", r"A\.?\s?L\.?\s?T\.?", "ALT", "2005 (3) ALT 456"),
    _Reporter("ALD (Cri)", r"A\.?\s?L\.?\s?D\.?\s*\(\s*Cri?l?\.?\s*\)", None, "2006 (1) ALD (Crl) 580"),
    _Reporter("ALD", r"A\.?\s?L\.?\s?D\.?", "ALD", "(2005) 3 ALD 123"),
    _Reporter("APLJ", r"A\.?\s?P\.?\s?L\.?\s?J\.?", "APLJ", "(1990) 2 APLJ 123"),
    _Reporter("Andh LT", r"Andh\.?\s?L\.?\s?T\.?", "ANDHLT", "(1990) 3 Andh LT 605"),
    _Reporter("Andh LD", r"Andh\.?\s?L\.?\s?D\.?", "ANDHLD", "(1998) 3 Andh LD 273"),
)

#: AIR courts whose two written names are measured as one series (see above).
#: The SCW weekly is held year-first (`2005 AIR SCW 123`) and written either way.
_AIR_EQUIVALENTS = {
    "SC": ("AIR{year}SC{page}", "AIR{year}SUPREMECOURT{page}"),
    "SUPREMECOURT": ("AIR{year}SC{page}", "AIR{year}SUPREMECOURT{page}"),
    "AP": ("AIR{year}AP{page}", "AIR{year}ANDHRAPRADESH{page}"),
    "ANDHRAPRADESH": ("AIR{year}AP{page}", "AIR{year}ANDHRAPRADESH{page}"),
    "SCW": ("AIR{year}SCW{page}", "{year}AIRSCW{page}"),
}
_AIR_EXAMPLES = ("AIR 1973 SC 1461", "AIR 1978 Supreme Court 597", "AIR 1990 AP 123",
                 "AIR 2005 SCW 123", "AIROnline 2019 SC 123")

_VOLUME_FORM = re.compile(
    r"(?<![\w/])[\(\[]?(?P<year>" + _YEAR + r")[\)\]]?\s*"
    r"(?:(?P<supp>Suppl?\.?)\s*)?"
    r"(?:[\(\[]?(?P<volume>\d{1,2})[\)\]]?\s*)?"
    r"(?P<reporter>" + "|".join(f"(?P<r{i}>{r.written})" for i, r in enumerate(_VOLUME_REPORTERS)) + r")"
    r"\s*(?P<page>\d{1,5})(?![\d/])", re.I)

_AIR_FORM = re.compile(
    r"(?<![A-Za-z])A\.?\s?I\.?\s?R\.?\s*(?P<online>On\s?line\s*)?(?P<year>" + _YEAR + r")\s*"
    r"(?P<court>S\.?\s?C\.?\s?W\.?|S\.?\s?C\.?|Supreme\s+Court|A\.?\s?P\.?|Andhra\s+Pradesh"
    r"|(?:[A-Z]\.){1,3}|[A-Z][A-Za-z]{1,14}\.?)\s*"
    r"(?:\((?P<series>[A-Za-z]{2,10})\.?\)\s*)?"
    r"(?P<page>\d{1,5})(?![\d/])", re.I)


@dataclass(frozen=True)
class ReporterCitation:
    """A case citation found in text, with every exact key it may be held under."""

    start: int
    end: int
    text: str
    reporter: str
    keys: tuple[str, ...]
    """The citation as written first, then its measured equivalents."""
    year: int
    """The reporter year. A judgment is reported in its own year or the next."""


#: The formats the recogniser reads, one example each, shown to an advocate
#: when nothing in their text was recognised. Each is tested to be read.
READ_FORMATS = tuple(r.example for r in _VOLUME_REPORTERS) + _AIR_EXAMPLES


def _volume_citation(m: re.Match) -> ReporterCitation:
    reporter = next(r for i, r in enumerate(_VOLUME_REPORTERS) if m.group(f"r{i}") is not None)
    written = reporter_key(m.group(0))
    keys = [written]
    parts = {"year": m.group("year"), "volume": m.group("volume") or "", "page": m.group("page")}
    if reporter.token:
        keys.append(reporter_key(m.group("year") + (m.group("supp") or "") + (m.group("volume") or ""))
                    + reporter.token + m.group("page"))
    if m.group("supp") and reporter.supplement_order:
        keys.append(reporter.supplement_order.format(**parts))
    elif m.group("volume") and reporter.volume_order:
        keys.append(reporter.volume_order.format(**parts))
    return ReporterCitation(m.start(), m.end(), m.group(0), reporter.name, tuple(dict.fromkeys(keys)),
                            int(m.group("year")))


def _air_citation(m: re.Match) -> ReporterCitation:
    court = reporter_key(m.group("court"))
    keys = [reporter_key(m.group(0))]
    if not m.group("online") and not m.group("series") and court in _AIR_EQUIVALENTS:
        keys.extend(form.format(year=m.group("year"), page=m.group("page"))
                    for form in _AIR_EQUIVALENTS[court])
    name = "AIR Online" if m.group("online") else "AIR"
    return ReporterCitation(m.start(), m.end(), m.group(0), name, tuple(dict.fromkeys(keys)),
                            int(m.group("year")))


def find_reporter_citations(text: str) -> tuple[ReporterCitation, ...]:
    """Every case citation in `text`, in order. Overlapping readings keep the earlier, longer one."""
    text = text or ""
    found = sorted([*map(_volume_citation, _VOLUME_FORM.finditer(text)),
                    *map(_air_citation, _AIR_FORM.finditer(text))],
                   key=lambda c: (c.start, -(c.end - c.start)))
    kept: list[ReporterCitation] = []
    for citation in found:
        if not kept or citation.start >= kept[-1].end:
            kept.append(citation)
    return tuple(kept)


# ================================== the search indexes' legal tokens =========
#
# FROZEN WITH THE INDEXES THEY BUILT. The word indexes over the bare acts and
# the judgments were cut with exactly these patterns, beside a lowercase
# whitespace split: "Section 138" is also `section_138`, "(2018) 5 SCC 379"
# also `(2018)_5_scc_379`. A query must be cut the same way or its words and
# the index's never meet -- and nothing errors when they do not, recall just
# goes. Measured 10 October 2026, the judgment index holds 36,523 SCC, 12,984
# AIR, 3,912 section, 1,776 article and 710 order-rule tokens cut this way
# (including the stray newlines and doubled underscores the replacement
# leaves), and `tests/test_search_tokens_match_the_built_index.py` checks the
# tokeniser still reproduces every one.
#
# They live HERE, beside the provision and citation readers, and not in the
# search, because two copies of them existed -- one in the live search, one in
# the archived search the index builds still import -- and a second copy is how
# a reader is hardened in one place and not the other. They are deliberately
# NOT those readers: SECTION refuses `O.S. 442` and these do not. Hardening
# them changes the tokens of an index already built, so a new tokenisation
# arrives only with a rebuilt index.
_SEARCH_NGRAMS = (
    re.compile(r"\bsection\s+\d+[a-z]{0,3}\b", re.I),
    re.compile(r"\bart(?:icle)?\.?\s+\d+[a-z]{0,3}\b", re.I),
    re.compile(r"\border\s+[ivx]+\s+rule\s+\d+\b", re.I),
    re.compile(r"\bair\s+\d{4}\s+(?:sc|hc|all|bom|cal|del|mad|kar|ker|gau|p&h)\s+\d+\b", re.I),
    re.compile(r"\(?\d{4}\)?\s+\(?\d+\)?\s+scc\s+\d+\b", re.I),
    re.compile(r"\b(?:ipc|crpc|cpc|ibc|sarfaesi|fema|cgst|sgst|igst|gst|ni\s+act|hma|hindu\s+marriage"
               r"|special\s+marriage|companies\s+act|negotiable\s+instruments|consumer\s+protection"
               r"|arbitration(?:\s+and\s+conciliation)?)\b", re.I),
)


def bm25_tokens(text: str) -> list[str]:
    """The search indexes' own tokenisation: lowercase whitespace split plus legal n-grams."""
    text = text or ""
    return text.lower().split() + [
        m.group(0).lower().replace(" ", "_").replace(".", "")
        for pattern in _SEARCH_NGRAMS for m in pattern.finditer(text)]


#: The provision a matter was FILED UNDER, read off a cause title to stratify
#: the evaluation frame (`pipeline/build_eval_frame.py`). It lives here for the
#: same reason as the search tokens, and it carries hardening SECTION does not
#: have: it reads `u/s` and refuses a detached letter.
#:
#: A TRAILING LETTER IS A SUB-SECTION ONLY WHEN IT IS ATTACHED. An earlier
#: form allowed whitespace before it and captured the first letter of the
#: NEXT word: "under Section 482 of Cr.P.C" became `482O`, "under Section 151
#: CPC" became `151C`, and 282 of 1,000 gold labels were wrong in a way that
#: reads exactly like the real sub-section suffixes (138A, 437A) it must be
#: able to tell them from. The letter must touch the digits and must not be
#: the start of a word.
FILED_UNDER = re.compile(
    r"\bunder\s+(?:sec(?:tion)?s?\.?|s\.|u/s\.?)\s*([0-9]+[A-Za-z]?)(?![A-Za-z])",
    re.I)


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
