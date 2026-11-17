"""What a paragraph of an answer names of the law, and what it says NM did, checked by code against the paragraph's own
sources and words (plan AN.51, pieces 51d and 51f; D198, D203; the review's F-04 and F-33).

The writer labels each paragraph with a kind, and only the kinds account, law and analysis had to carry a source; a
paragraph labelled next step or summary was admitted with none, so "under section 17 time runs from discovery" inside a next
step passed every mechanical check, and only the reviewer model stood between it and the advocate. Here code reads the words,
whatever the label:

  named_without_source: each provision a paragraph names by its number must be found in held law its section rests on - a
  held provision that is it, or a passage whose own words name it, used by that paragraph or by another of the section (a
  line that sums a section up names what the section sets out) - or in a time limit code worked out. For a paragraph that
  sets out what the papers say (account) the advocate's own messages and papers it uses count too, since it reports them.

  effect_claimed: a paragraph may not say that NM did, saved, filed or will do something. What was done is code's alone to
  say (P10); the writer's instruction has always forbidden it, and nothing checked.

Both are mechanical. They read reference patterns that nm/shared/citation_contracts.py owns and compare tokens; whether a
passage supports what is said of it stays the reviewer's judgment, and an Act named without a provision is not checked here.
A paragraph that asks the advocate something or states a limit of the answer names law without stating it and is not held to
the first check. A fault found is the paragraph's own: the writer gets its second look, and what still fails is cut by its
sentence (writer v14's mechanism, unchanged).
"""
from __future__ import annotations

import re

from nm.shared.citation_contracts import ANY_PROVISION, provisions_named

#: Kinds of paragraph that ask or disclaim: they name law without stating it.
NOT_HELD_TO_SOURCES = frozenset({"question", "limitation"})
#: The kind that reports what the advocate's own messages and papers say.
REPORTS_THE_PAPERS = "account"
_HELD_LAW = frozenset({"provision", "judgment"})
#: A designation standing by itself in a source's words or label: "17", "65B", "6-A", "XXXIX".
_DESIGNATION = re.compile(r"(?<![\w.])(\d+)\s?-?\s?([A-Za-z]{0,3})(?![\w])|(?<![\w])([IVXLC]{1,7})(?![\w])")
_QUOTED = re.compile(r"\"[^\"]*\"|“[^”]*”|‘[^’]*’")

_ACTS = (r"saved|stored|recorded|updated|corrected|amended|replaced|removed|deleted|re-?worked|re-?calculated|"
         r"re-?computed|revised|filed|sent|submitted|lodged|served|registered|completed|incorporated|adjusted")
_WILL = (r"save|store|record|update|correct|amend|replace|remove|delete|re-?work|re-?calculate|revise|file|send|submit|lodge|"
         r"serve|register")
#: NM, "I" or "we" as the one who did or will do something. Narrower than the filter for words shown outside an answer
#: (shown_words): an answer's prose rightly says what the parties and the courts did.
_EFFECT = re.compile(
    rf"\b(?:I|We|NM|Nyaymalaw)\s+(?:have|has|had|am|are|is|will|shall)\s+(?:now\s+|already\s+|just\s+|duly\s+|also\s+)?"
    rf"(?:been\s+)?(?:{_ACTS})\b"
    rf"|\b(?:I|We|NM|Nyaymalaw)\s+(?:{_ACTS})\b"
    rf"|\b(?:I|We|NM|Nyaymalaw)\s+(?:will|shall)\s+(?:now\s+|also\s+)?(?:{_WILL})\b"
    rf"|\b(?:I|We|NM|Nyaymalaw)(?:'ve|’ve)\s+(?:now\s+|already\s+|just\s+)?(?:{_ACTS})\b"
    rf"|\b(?:this|that|it|your\s+\w+(?:\s+\w+)?)\s+(?:is|are|has\s+been|have\s+been)\s+(?:now\s+|already\s+)?"
    rf"(?:saved|stored|recorded|updated)\s+(?:in|to|on|with)\s+(?:NM|Nyaymalaw|your\s+(?:matter|file|record|conversation)|"
    rf"the\s+(?:matter|file|record|conversation|board))\b", re.I)


#: What a roman numeral follows where it numbers a part of an instrument.
_NUMBERED = re.compile(r"\b(?:Schedule|Part|Chapter|Annexure|Appendix|Order|Volume|Form|List|Table|Class)\s+$", re.I)


def _designation(number: str, letters: str = "") -> str:
    return f"{int(number)}{letters.upper()}" if number.isdigit() else number.upper()


def named(text: str) -> list[tuple[str, str]]:
    """Each provision the words name by its number, as (designation, the words naming it), in order and once each. Both of the
    owner's readers are asked: the one for lists, ranges and rules of an Order, and the one for a reference written short."""
    found: dict[str, str] = {}
    for one in provisions_named(text or ""):
        order = re.match(r"Order ([IVXLC]+A?)", one.reference)
        unit = order.group(1) if order else one.reference.split()[-1]
        match = re.fullmatch(r"(\d+)([A-Za-z]*)", unit)
        # The reference's own words where the paragraph writes them out ("section 21"), else the list it stands in.
        own = None if order else re.search(rf"(?i)\b(?:sections?|articles?|rules?)\s+{re.escape(unit)}(?![\w])", one.words)
        found.setdefault(_designation(*match.groups()) if match else unit.upper(), own.group(0) if own else one.words)
    for match in ANY_PROVISION.finditer(text or ""):
        unit = next((group for group in match.groups() if group), "")
        parts = re.fullmatch(r"(\d+)([A-Za-z]*)", unit)
        found.setdefault(_designation(*parts.groups()) if parts else unit.upper(), match.group(0))
    return list(found.items())


def designations(*texts) -> set[str]:
    """Every designation standing by itself in these words: what a source can be said to name."""
    out: set[str] = set()
    for text in texts:
        for number, letters, roman in _DESIGNATION.findall(str(text or "").replace("_", " ")):
            out.add(_designation(number, letters) if number else roman.upper())
            if number and letters:
                # A lettered provision also answers its number alone: a paragraph's "section 6-A" is read by the short
                # reader as 6, and a mechanical floor must not fault what it cannot read. The reviewer judges the rest.
                out.add(_designation(number))
    return out


def held(sources) -> set[str]:
    """Every designation the held law among these sources is or names."""
    return designations(*(part for source in sources if source.get("kind") in _HELD_LAW
                          for part in (source.get("locator"), source.get("text"))))


def named_without_source(kind: str, text: str, used: list[dict], also=frozenset()) -> list[str]:
    """The words of each provision this paragraph names that no source it uses is or names. used: the paragraph's sources as
    the catalogue holds them, with those read beside them (each: kind, text, locator). also: designations established
    elsewhere - by held law another paragraph of the section uses, or by a time limit code worked out."""
    if kind in NOT_HELD_TO_SOURCES:
        return []
    have = held(used) | set(also)
    if kind == REPORTS_THE_PAPERS:
        have |= designations(*(part for source in used for part in (source.get("locator"), source.get("text"))))
    return [words for designation, words in named(text) if designation not in have]


def effect_claimed(text: str) -> list[str]:
    """The words by which this paragraph says NM did, saved or will do something - outside anything it quotes."""
    plain = _QUOTED.sub(lambda quoted: " " * len(quoted.group(0)), text or "")
    # "Schedule I amended ...", "Part I registered ...": the numeral of a Schedule or a Part is not NM speaking.
    return [match.group(0) for match in _EFFECT.finditer(plain)
            if not (match.group(0)[:2].lower() == "i " and _NUMBERED.search(plain[:match.start()]))]
