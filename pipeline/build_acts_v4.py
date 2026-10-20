"""Build the new Act store from India Code and the texts we hold. AN OFFLINE JOB; THE READ AND
INDEX STAGES WRITE ONLY A NEW FOLDER AND A CANDIDATE LINEAGE RECORD. The marks stage corrects that
folder's standing marks in place, keeping the store as it was beside it; stop the server first.

    .venv-arrive\\Scripts\\python.exe pipeline\\build_acts_v4.py --stage read      (Acts, passages, reports)
    .venv-arrive\\Scripts\\python.exe pipeline\\build_acts_v4.py --stage index     (vectors, words, lineage)
    .venv-arrive\\Scripts\\python.exe pipeline\\build_acts_v4.py --stage marks     (P21's check, into the built store)

`--out acts_v5` builds into a new folder beside the store search reads (Q18, 21 Oct 2026: the CPC's
Orders read again); each stage is given the same folder.

Owner decisions of 19 Oct 2026 (the Advocate build plan, P20-P23):

  * P20 - an Act India Code publishes section by section takes India Code's sections, each read
    beside the same section in India Code's text of the Act's official PDF and in our text: a
    difference only in spacing keeps India Code's words; a few words that India Code's section
    alone has, where the PDF's text and ours agree on other words, take those words; anything
    else is listed for review and India Code's words stay. Amendment marks come out of the text
    into notes; other States' amendments printed inside a central section come out into notes,
    Telangana's and Andhra Pradesh's marked as applying. Schedules stay ours (India Code holds
    them only as PDFs). An Act India Code holds only as a PDF, or not at all, keeps our text.
  * P21 - an Act we hold that India Code does not list as in force is kept, marked not in force;
    'not listed' checked Act by Act: an Act India Code lists under another title is another file
    of that Act, and a Finance or Appropriation Act (India Code lists none) is not marked.
  * P22 - an Act India Code lists in force that we lack is added from it.
  * P23 - Telangana keeps what India Code lists under Telangana: the Andhra Pradesh-era Acts it
    does not list, and the Andhra Pradesh-era rules, regulations and orders, are left out.

The passages are cut as the current store cuts them (`append_bare_acts.passages_for`: a section
head carrying the whole section, then its sub-sections, clauses, provisos...), with one copy of
each Act, every passage's parent held beside it, and identifiers that never repeat. Schedules:
the Limitation Act's articles as rows of its schedule, the Code of Civil Procedure's Orders as
rules, any other schedule as its paragraphs.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.append_bare_acts import (  # noqa: E402 - the store's own reading and cutting
    Act, Section, _real_bm25, _real_encoder, bm25_tokens, parse_act, passages_for, read_act,
)

RAW = ROOT / "legal_database" / "raw_data" / "BareActs"
FETCHED = ROOT / "legal_database" / "raw_data" / "IndiaCode" / "2026-10-19"
ACT_TEXTS = ROOT / "legal_database" / "raw_data" / "IndiaCode" / "2026-10-19-act-texts"
EVIDENCE = ROOT / "outputs" / "corpus-indiacode-20261019"
OUT = ROOT / "legal_database" / "vector_store" / "acts_v4"
CANDIDATE = ROOT / ".nm" / "retrieval" / "candidates" / "bare_acts_v4.lineage.json"
JURISDICTION = {"CENTRAL": "Union of India", "Telangana": "Telangana"}
#: The States whose amendments to a central Act apply in Telangana.
APPLYING = ("telangana", "andhra pradesh")
#: P21: an instrument's standing, and the mark each of its passages carries.
NOT_IN_FORCE = "not in force according to India Code"
MARK = f"{NOT_IN_FORCE} (checked 19 Oct 2026)"
#: P21's own check, Act by Act ("a title our files spell differently is not a repeal"), made
#: after the build of 19 Oct 2026: our files holding an Act India Code lists under another title -
#: renamed since, or our file's title spelt or cut short otherwise - each with that Act's India
#: Code identifier (its number and year agree). Each is another file of that India Code Act, which
#: is taken once, from India Code (P20); none is an Act not in force.
LISTED_UNDER_ANOTHER_TITLE = {
    # The Banking Regulation Act, 1949 (10 of 1949), so named in 1965.
    "Union of India/1960_0_Banking Companies Act, 1949.txt": "AC_CEN_2_11_00002_194910_1517807317779",
    # The Prohibition of Benami Property Transactions Act, 1988 (45 of 1988), so named in 2016.
    "Union of India/1988_1_The Benami Transactions (Prohibition) Act, 1988.txt": "AC_CEN_2_2_00032_198845_1517807326369",
    # The Recovery of Debts and Bankruptcy Act, 1993 (51 of 1993), so named in 2016.
    "Union of India/1993_0_The Recovery Of Debts Due To Banks And Financial Institutions Act, 1993.txt":
        "AC_CEN_2_33_00045_199351_1524048948493",
    # The Pre-conception and Pre-natal Diagnostic Techniques (Prohibition of Sex Selection) Act, 1994
    # (57 of 1994), so named in 2003.
    "Union of India/1994_4_The Pre-Natal Diagnostic Techniques (Regulation And Prevention of misuse) Act, 1994.txt":
        "AC_CEN_12_13_00013_199457_1517807323443",
    # The National Commission for Minority Educational Institutions Act, 2004 (2 of 2005).
    "Union of India/2004_2_The National Commission For Minority Educational Institutions Act, 2004.txt":
        "AC_CEN_9_30_00003_200502_1517807320310",
    # The Commercial Courts Act, 2015 (4 of 2016), so named in 2018.
    "Union of India/2015_3_ï»¿The Commercial Courts, Commercial Division And Commercial Appellate "
    "Division Of High Courts Act, 2015.txt": "AC_CEN_3_46_00008_201604_1517807328347",
    # The Central Road and Infrastructure Fund Act, 2000 (54 of 2000), so named in 2018.
    "Union of India/2018_7_Central Road Fund Act, 2000.txt": "AC_CEN_30_42_00004_200054_1517807323465",
    # The Van (Sanrakshan Evam Samvardhan) Adhiniyam, 1980 (69 of 1980), so named in 2023.
    "Union of India/1980_15_The Forest (Conservation) Act, 1980.txt": "AC_CEN_16_18_00008_198069_1517807325332",
    # The Unified Waqf Management, Empowerment, Efficiency and Development Act, 1995 (43 of 1995),
    # so named in 2025.
    "Union of India/1980_9_The Wakf Act, 1995.txt": "AC_CEN_44_74_00001_199543_1517807323904",
    # The Coal Mines Provident Fund and Miscellaneous Provisions Act, 1948 (46 of 1948).
    "Union of India/1948_12_Coal Mines Provident Fund and Bonus Schemes Act, 1948.txt":
        "AC_CEN_8_8_00009_194846_1517807326587",
    # The Telangana Revenue Enquiries Act, 1893.
    "Telangana/2016_30_Telangana Revenue Enquiries Act, 1893.txt": "AC_TS_86_767_00007_00007_1553234010701",
    # The Telangana Prevention of Dangerous Activities of Boot-leggers, ... Act, 1986 (1 of 1986);
    # our file's title stops part way.
    "Telangana/2015_6_Telangana Prevention of Dangerous Activities of Boot-leggers, Dacoits, Drug-Offenders, "
    "Goondas, Immoral Traffic Offenders Land-Grabbers, Spurious Seed Offenders.txt":
        "AC_TS_86_750_00013_00013_1552906478626",
}
#: India Code lists no Finance Act and no Appropriation Act among the Acts in force, so its list
#: says nothing of one: such an Act is not marked (not assessed).
_UNLISTED_KIND = re.compile(r"^\W*(?:the\s+)?(?:finance|appropriation)(?:\s*\(no\.\s*\d+\))?\s+act\b", re.I)


# ----------------------------------------------------------------------------- choosing


def era(title: str, year: str | None) -> str:
    """Whose an instrument of the Telangana folder is, by its title and year (P23)."""
    lowered = title.lower()
    if "telangana" in lowered and "andhra pradesh" not in lowered and "telangana area" not in lowered:
        return "telangana"
    if "andhra pradesh" in lowered or "hyderabad" in lowered or re.search(r"\ba\.\s?p\.", lowered):
        return "andhra pradesh"
    return "telangana" if year and year.isdigit() and int(year) >= 2014 else "andhra pradesh"


def selection(inventory: list[dict], matches: list[dict]) -> list[dict]:
    """Every instrument of the new store, with where its text comes from and its standing; and
    every one left out, with why. One entry per instrument: an India Code Act matched by
    several of our files is taken once, from India Code."""
    chosen, seen = [], set()
    for row in matches:
        folder, verdict, india = row["jurisdiction"], row["verdict"], row.get("india_act_id")
        entry = {"jurisdiction": folder, "file": row["file"], "title": row["title"], "year": row["act_year"],
                 "india_act_id": india, "kind": row["kind"]}
        if not row["file"].endswith(".txt"):
            chosen.append({**entry, "source": None, "left_out": "not an Act's text (a PDF or a record file)"})
            continue
        same = LISTED_UNDER_ANOTHER_TITLE.get(f"{folder}/{row['file']}")
        if same:
            chosen.append({**entry, "source": None, "same_act_as": same,
                           "left_out": "another file of the same India Code Act, which India Code lists under "
                                       "another title (P20, P21)"})
            continue
        if folder == "Telangana" and not india and era(row["title"], row["act_year"]) == "andhra pradesh":
            chosen.append({**entry, "source": None, "left_out": "P23: an Andhra Pradesh-era instrument India Code "
                                                                 "does not list under Telangana"})
            continue
        if india and (verdict.endswith("refetch") or verdict.startswith("partly")):
            if india in seen:
                chosen.append({**entry, "source": None, "left_out": "another file of the same India Code Act"})
                continue
            seen.add(india)
            chosen.append({**entry, "source": "india_code", "standing": "in force"})
        elif verdict.startswith("not in India Code"):
            chosen.append({**entry, "source": "ours",
                           "standing": None if _UNLISTED_KIND.match(row["title"]) else NOT_IN_FORCE})
        else:
            chosen.append({**entry, "source": "ours",
                           "standing": "in force" if verdict.startswith("PDF only") else None})
    for act in inventory:
        if act["act_id"] in seen or any(row.get("india_act_id") == act["act_id"] for row in matches):
            continue
        seen.add(act["act_id"])
        chosen.append({"jurisdiction": JURISDICTION[act["state"]], "file": None, "title": act["title"],
                       "year": act["year"], "india_act_id": act["act_id"], "kind": "act",
                       "source": "india_code" if act["sections"] else "india_code_pdf_text",
                       "standing": "in force", "added": "P22: in force according to India Code; the corpus lacked it"})
    return chosen


# ----------------------------------------------------------------------------- India Code's text

_SUP = re.compile(r"<sup>\s*(\d+)\s*</sup>")
_BREAK = re.compile(r"<br\s*/?>|<hr[^>]*>|</p>|<p[^>]*>|</tr>|<center[^>]*>|</center>", re.I)
_STATE_AMENDMENT = re.compile(r"<b>\s*STATE\s+AMENDMENTS?\b", re.I)


def footnotes(footnotes_html: str) -> dict[str, str]:
    """India Code's footnotes to a section, by their number."""
    found = {}
    for number, text in re.findall(r"<sup>\s*(\d+)\s*</sup>\s*\.?\s*(.*?)(?=<sup>\s*\d+\s*</sup>|$)",
                                   footnotes_html or "", re.S):
        found[number] = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())
    return found


def _unbracket(text_html: str) -> tuple[str, list[dict]]:
    """The section's markup with each amendment mark taken out: a footnote number, and the
    brackets it opens round the words an amendment put there. Returns the markup and, for
    each mark, its footnote number and the words it marked."""
    out, marks, stack = [], [], []
    position = 0
    while position < len(text_html):
        found = _SUP.match(text_html, position)
        if found:
            after = found.end()
            while after < len(text_html) and text_html[after] == " ":
                after += 1
            if after < len(text_html) and text_html[after] == "[":
                stack.append({"note": found.group(1), "start": len(out)})
                position = after + 1
            else:
                marks.append({"note": found.group(1), "words": None})
                position = found.end()
            continue
        char = text_html[position]
        if char == "[":
            stack.append(None)
        elif char == "]" and stack:
            opened = stack.pop()
            if opened is not None:
                marks.append({"note": opened["note"],
                              "words": html.unescape(re.sub(r"<[^>]+>", " ", "".join(out[opened["start"]:])))})
                position += 1
                continue
        out.append(char)
        position += 1
    for opened in stack:  # a mark whose bracket the section never closes runs to its end
        if opened is not None:
            marks.append({"note": opened["note"],
                          "words": html.unescape(re.sub(r"<[^>]+>", " ", "".join(out[opened["start"]:])))})
    return "".join(out), marks


def _lines(markup: str) -> list[str]:
    """Markup as the library's text lines: one line per break, tables between '{|' and '|}'
    (whose rows `passages_for` never cuts), tags out, entities read."""
    markup = re.sub(r"<table[^>]*>", "\n{|\n", markup, flags=re.I)
    markup = re.sub(r"</table>", "\n|}\n", markup, flags=re.I)
    markup = re.sub(r"</td>\s*<td[^>]*>", " | ", markup, flags=re.I)
    markup = _BREAK.sub("\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def india_code_section(record: dict) -> tuple[Section, dict]:
    """One India Code section as a library section, and its notes: the footnotes, what each
    amendment mark marked, and the States' amendments printed inside it (P20)."""
    text_html = record["text_html"] or ""
    cut = _STATE_AMENDMENT.search(text_html)
    own, states = (text_html[:cut.start()], text_html[cut.start():]) if cut else (text_html, "")
    markup, marks = _unbracket(own)
    notes = footnotes(record.get("footnotes_html") or "")
    amendments = []
    for block in re.split(r"(?=<b>\s*(?!STATE\s+AMENDMENT)[A-Z][A-Za-z .&-]{2,40}</b>\s*<br)", states)[1:]:
        state = html.unescape(re.sub(r"<[^>]+>", "", re.match(r"<b>(.*?)</b>", block).group(1))).strip()
        amendments.append({"state": state, "applies": state.lower() in APPLYING,
                           "text": "\n".join(_lines(block)[1:])})
    heading = " ".join(html.unescape(record.get("heading") or "").split())
    number = (record.get("number") or "").replace(" ", "")
    lines = _lines(markup)
    section = Section(number, heading, lines=lines, opening=[f"{number}. {heading}"])
    return section, {"footnotes": notes, "marks": [{**mark, "says": notes.get(mark["note"])} for mark in marks],
                     "state_amendments": amendments}


# ----------------------------------------------------------------------------- three readings

_WORD = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(match.group().lower(), match.start(), match.end()) for match in _WORD.finditer(text)]


def _holds(words: list[str], run: list[str]) -> bool:
    if not run:
        return True
    first = run[0]
    return any(words[k:k + len(run)] == run for k, word in enumerate(words) if word == first)


#: How often a word must stand in India Code's sections to count as a word of the statutes, and how
#: rarely to count as a misreading: measured over all 36,984 section records fetched.
KNOWN, RARE = 20, 3


def vocabulary() -> Counter:
    """How often each word stands in India Code's section records, Centre and Telangana."""
    counts: Counter = Counter()
    for path in FETCHED.glob("*/*.json"):
        for record in json.loads(path.read_text(encoding="utf-8"))["sections"]:
            counts.update(word for word, _, _ in _tokens(" ".join(_lines(record["text_html"] or ""))))
    return counts


def reconcile(section_text: str, pdf_text: str | None, our_text: str | None, words: Counter, *,
              context: int = 3):
    """India Code's section beside India Code's text of the Act's official PDF and ours (P20).

    Our text and the PDF's text often come from the same print and share its errors, and a
    printed section cut at a page break or a heading reads as words missing; so a difference is
    settled for India Code's words except where it is plainly a misreading in India Code's
    section alone: one word against one word, India Code's rare among all its sections (fewer
    than RARE times) and the PDF's a word of the statutes (KNOWN times or more), ours agreeing
    with the PDF where we hold the section ("clue" for "due", "representive"). A difference of a
    few words that both readings print as words of the statutes ("promise" and "promisee") is
    listed for review, with its context; India Code's words stay. Returns the text, the changes
    and the list for review."""
    if not pdf_text:
        return section_text, [], []
    mine = _tokens(section_text)
    pdf = _tokens(pdf_text)
    ours = [word for word, _, _ in _tokens(our_text or "")]
    a, b = [word for word, _, _ in mine], [word for word, _, _ in pdf]
    changed, review, edits = [], [], []
    for tag, a1, a2, b1, b2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "replace" or "".join(a[a1:a2]) == "".join(b[b1:b2]) or max(a2 - a1, b2 - b1) > 3:
            continue  # the same letters spaced differently, words one printing lacks, or a misaligned stretch
        if all(re.fullmatch(r"\d{1,2}", word) for word in a[a1:a2] + b[b1:b2]):
            continue  # footnote numbers
        around = (b[max(0, b1 - context):b1], b[b2:b2 + context])
        theirs, india = a[a1:a2], b[b1:b2]
        if (a2 - a1 == 1 and b2 - b1 == 1 and words.get(theirs[0], 0) < RARE and words.get(india[0], 0) >= KNOWN
                and (not ours or _holds(ours, [*around[0], *india, *around[1]]))):
            taken = pdf_text[pdf[b1][1]:pdf[b1][2]]
            edits.append((mine[a1][1], mine[a1][2], taken))
            changed.append({"india_code": theirs[0], "taken": taken,
                            "why": "a misreading in India Code's section: the official PDF's word, ours agreeing"})
        elif all(words.get(word, 0) >= KNOWN for word in theirs + india):
            review.append({"india_code": " ".join(theirs), "pdf": " ".join(india),
                           "context": " ".join([*around[0], "[...]", *around[1]]),
                           "ours": ("agrees with India Code" if ours and _holds(ours, [*around[0], *theirs, *around[1]])
                                    else "agrees with the PDF" if ours and _holds(ours, [*around[0], *india, *around[1]])
                                    else None)})
    text = section_text
    for start, end, taken in sorted(edits, reverse=True):
        text = text[:start] + taken + text[end:]
    return text, changed, review


# ----------------------------------------------------------------------------- schedules

_PERIOD = re.compile(r"^(?:(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirty|Sixty|"
                     r"Ninety|Fifteen|Twenty)[\w -]*?(?:years?|days?|months?)|Ninety days|Thirty years)\.?$", re.I)
_PART = re.compile(r"^(?:PART\s+[IVXL]+|(?:FIRST|SECOND|THIRD)\s+DIVISION)\b", re.I)


@dataclass
class Article:
    number: str
    description: list[str] = field(default_factory=list)
    period: str = ""
    starts: list[str] = field(default_factory=list)
    division: str = ""
    part: str = ""


def limitation_articles(lines: list[str]) -> list[Article]:
    """The Limitation Act's schedule as rows: an article's number alone on its line, its
    description, its period ("Three years"), then when the period begins to run - the three
    columns of the schedule, as our text prints them one to a line."""
    articles: list[Article] = []
    division = part = ""
    current: Article | None = None
    for line in lines:
        if re.match(r"^(?:FIRST|SECOND|THIRD)\s+DIVISION", line, re.I):
            division, current = line, None
            continue
        if _PART.match(line):
            part, current = line, None
            continue
        if re.fullmatch(r"\d{1,3}[A-Z]?", line):
            current = Article(line, division=division, part=part)
            articles.append(current)
            continue
        if current is None or re.match(r"^State Amendment", line, re.I):
            current = None
            continue
        if not current.period and _PERIOD.match(line):
            current.period = line
        elif current.period:
            current.starts.append(line)
        else:
            current.description.append(line)
    return [article for article in articles if article.description and article.period]


#: An Order's heading as the Schedule prints it, alone on its line: "ORDER XXI", "ORDER XVI-A",
#: "ORDER XXVII A]". In capitals: a sentence naming an Order is not its heading (Q18, 21 Oct 2026:
#: the hyphen of "XXXII-A" had ended the numeral, so its rules were read as Order XXXII's repeats).
_ORDER = re.compile(r"^(?:\d{1,2}\s*)?\[?\s*ORDER\s+([IVXL]+)(?:[-\s]?([A-Z]))?\s*\]?\s*$")


#: An amendment's mark opening a printed line ("1[", "*[", "["), before a rule's number or an Order.
_LEADING_MARK = re.compile(r"^(?:\d{1,2}|\*)?\[\s*(?=\d|ORDER\b)|^[“\"]\s*(?=ORDER\b)")
#: An editor's mark of amendment inside a line ("3[(1)", "2[indigent persons.]"): not the Code's words.
_MARK = re.compile(r"(?<![\w(])\d{1,2}\[\s?|\*\[\s?|\]")
#: A rule's number opening its line, and where a rule's heading ends and its words begin.
_RULE_OPENS = re.compile(r"^(\d{1,3})([A-Z]{0,2})\.\s+\S")
_HEADING_END = re.compile(r"[.:]\s*[—–-]")


def _rule_lines(body: list[str]) -> list[str]:
    """One Order's lines as its rules can be read (Q18, 21 Oct 2026; the reader had dropped whole
    Orders and single rules without a word): the editors' marks of amendment set aside; a rule's
    heading printed over two lines joined ("1. Officers ... may authorise any person to sue or" /
    "defend for them. —(1) Where"); and a footnote's figure printed against a rule's number
    ("21. Judgment when pronounced" for rule 1, "315. Power to deal with evidence" for rule 15)
    read as that number where the rule before it numbers it so; a rule's dot run into its heading
    ("1A.When") spaced."""
    lines = [re.sub(r"^(\d{1,3}[A-Z]{0,2})\.(?=[A-Za-z])", r"\1. ", " ".join(_MARK.sub("", line).split()))
             for line in body]
    joined, k = [], 0
    while k < len(lines):
        line = lines[k]
        if (_RULE_OPENS.match(line) and not _HEADING_END.search(line[:260]) and k + 1 < len(lines)
                and _HEADING_END.search(lines[k + 1][:160]) and not _RULE_OPENS.match(lines[k + 1])):
            line, k = f"{line} {lines[k + 1]}", k + 1
        joined.append(line)
        k += 1
    opens = [k for k, line in enumerate(joined) if _RULE_OPENS.match(line) and _HEADING_END.search(line[:260])]
    expected = 1
    for k in opens:
        number, letters = _RULE_OPENS.match(joined[k]).groups()
        figure = int(number)
        # A figure out of the rules' order whose remainder is the next rule but one or two: the
        # footnote's figure against the number ("315" where rule 15 follows rule 13).
        if (not letters and not expected <= figure <= expected + 2 and len(number) > 1
                and expected <= int(number[1:]) <= expected + 2):
            joined[k] = number[1:] + joined[k][len(number):]
            figure = int(number[1:])
        if not letters and figure >= expected:
            expected = figure + 1
    return joined


def cpc_orders(lines: list[str], notes: list[str] | None = None) -> list[Section]:
    """The Code of Civil Procedure's First Schedule as its rules, each keyed "Order_VII_Rule_11"
    as the store already keys them, a lettered Order as "Order_XXXIIA_Rule_1". Each Order's rules
    are read as `read_act` reads an Act's sections - the longest chain of numbers that only go
    up - so a number printed inside a rule (a State's amendment, a list) stays its words. An
    Order a State's amendment prints (its heading quoted) is not read as the Code's; an Order
    printed a second time (Order XI as the Commercial Courts Act amends it for commercial
    disputes) is not read again. Each Order or second text not read is said in `notes`."""
    orders: list[tuple[str, list[str] | None]] = []
    for line in lines:
        if _FOOTNOTE_LINE.match(line) or re.fullmatch(r"\d{1,4}", line):
            continue  # a footnote, or a page's number
        if len(line) < 60 and re.match(r"^\s*(?:THE\s+)?(?:SECOND|THIRD|FOURTH|FIFTH)\s+SCHEDULE\b|^\s*APPENDIX\s+[A-Z]\b",
                                       line):
            break  # the First Schedule's end: the Code's other schedules, or its appendices of forms
        bare = _LEADING_MARK.sub("", line)
        heading = _ORDER.match(bare)
        if heading and not line.startswith(("“", "\"")):
            name = heading.group(1) + (heading.group(2) or "")
            if any(order == name for order, _ in orders):
                orders.append((name, None))
                if notes is not None:
                    notes.append(f"Order {name} is printed a second time ({line.strip()[:40]}); that text is not read")
                continue
            orders.append((name, []))
        elif orders and orders[-1][1] is not None:
            orders[-1][1].append(bare)
    rules: list[Section] = []
    seen: set[str] = set()
    for order, body in orders:
        if body is None:
            continue
        try:
            read = read_act("\n".join(_rule_lines(body)), act_id="CPC", act_name="CPC", title="CPC", year="1908",
                            name=f"Order {order}")
        except ValueError as error:
            if notes is not None:
                notes.append(f"Order {order} could not be read: {error}")
            continue
        for rule in read.sections:
            key = f"Order_{order}_Rule_{rule.number}"
            if key in seen:
                continue
            seen.add(key)
            rules.append(Section(key, rule.title.strip(" .—-"), lines=[*rule.opening, *rule.lines], opening=[]))
    return rules


#: The lines one part of a long schedule or text holds: search reads at most 500 passages of
#: one provision (nm/core_engine/retrieval.py, MAX_CONTEXT_SEGMENTS).
PART_LINES = 120


def _parts(block: Section) -> list[Section]:
    """A long block as parts of PART_LINES lines, keyed "<key>", "<key>_part_2"..."""
    if len(block.lines) <= PART_LINES:
        return [block]
    parts = []
    for start in range(0, len(block.lines), PART_LINES):
        number = len(parts) + 1
        parts.append(Section(block.number if number == 1 else f"{block.number}_part_{number}",
                             block.title if number == 1 else f"{block.title} (part {number})",
                             lines=block.lines[start:start + PART_LINES],
                             opening=block.opening if number == 1 else []))
    return parts


def schedule_blocks(lines: list[str]) -> list[Section]:
    """Any other Act's back matter as schedules: a heading such as "THE FIRST SCHEDULE", "FORM 3"
    or "ANNEXURE II" opens one, keyed "Schedule_1", "Schedule_2"... in order; its lines follow,
    a long one in parts."""
    blocks: list[Section] = []
    for line in lines:
        if re.match(r"^(?:THE\s+)?(?:[A-Z]+\s+)?(?:SCHEDULE|FORM|APPENDIX|ANNEXURE)\b", line) and len(line) < 80:
            blocks.append(Section(f"Schedule_{len(blocks) + 1}", line, lines=[], opening=[line]))
        elif blocks:
            blocks[-1].lines.append(line)
        elif line.strip():
            blocks.append(Section("Schedule_1", "Schedule", lines=[line], opening=[]))
    return [part for block in blocks if block.lines for part in _parts(block)]


def text_blocks(raw: str, act_id: str, act_name: str, title: str, year: str) -> Act:
    """A text whose sections cannot be read (no section 1 is printed as the reader knows it): kept
    whole, as numbered parts of its lines, rather than lost."""
    lines = [" ".join(line.split()) for line in raw.splitlines() if line.strip()]
    whole = Section("Text", title, lines=lines, opening=[])
    return Act(act_id, act_name, title, year, _parts(whole), notes=["read as text: no section 1 was found"])


# ----------------------------------------------------------------------------- reading an Act


def identity(entry: dict, act: dict | None) -> tuple[str, str, str, str]:
    """The Act's identifier and name in the store's own form - "UNION OF INDIA_1881_26_THE
    NEGOTIABLE INSTRUMENTS ACT, 1881" - India Code's number and title where it is India Code's."""
    jurisdiction = entry["jurisdiction"]
    if act is not None:
        title = " ".join((act["act"].get("dc.title") or [entry["title"]])[0].split()).rstrip(". ")
        year = (act["act"].get("dc.date.act_year") or [entry["year"] or ""])[0]
        number = (act["act"].get("dc.identifier.act_number") or ["0"])[0]
    else:
        named = re.match(r"(\d{4})_(\d+)_(.*)\.txt$", entry["file"])
        year, number, title = named.group(1), named.group(2), named.group(3).strip()
    act_name = f"{' '.join(jurisdiction.split())} {year} {number} {title}".title()
    return f"{jurisdiction.upper()}_{year}_{number}_{title.upper()}", act_name, title, year


def schedules_from(back: list[str], title: str, notes: list[str] | None = None) -> tuple[list[Section], list[Article]]:
    if "limitation act, 1963" in title.lower():
        return [], limitation_articles(back)
    if "code of civil procedure, 1908" in title.lower():
        return cpc_orders(back, notes), []
    return schedule_blocks(back), []


def back_matter(act: Act, title: str) -> list[str]:
    """What follows an Act's last section in our text. Our Limitation Act prints its schedule
    straight after section 32 ("[See sections 2(j) and 3]"), so the reader keeps it inside that
    section: it is taken back out."""
    if "limitation act, 1963" in title.lower() and act.sections:
        last = act.sections[-1]
        start = next((k for k, line in enumerate(last.lines) if re.match(r"^\[?See sections", line)), None)
        if start is not None:
            back, last.lines = last.lines[start:], last.lines[:start]
            return back + act.back_matter
    return act.back_matter


#: A footnote line of a printed Act ("1. Subs. by Act 55 of 2002, s. 7 ..."): not the statute's words.
_FOOTNOTE_LINE = re.compile(r"^\s*\d{1,3}\s*\.?\s*(Subs\.|Ins\.|Omitted|Rep\.|The words|Added|Renumbered|Cl\.|"
                            r"Sub-s|Now see|The original|Certain|Vide|Ss?\.\s*\d)", re.I)


def statute_words(section: Section) -> str:
    """A printed section's lines without its footnote lines, for reading beside India Code's."""
    return "\n".join(line for line in section.lines if not _FOOTNOTE_LINE.match(line))


def read_entry(entry: dict, words: Counter) -> tuple[Act, list[Article], dict]:
    """One instrument read from its source, with its schedules and the record of how."""
    record: dict = {"source": entry["source"], "standing": entry.get("standing"), "notes": {}, "changed": [],
                    "review": [], "schedule_source": None, "schedule_notes": []}
    ours = None
    if entry.get("file"):
        path = RAW / entry["jurisdiction"] / entry["file"]
        try:
            ours = parse_act(path, entry["jurisdiction"])
        except ValueError:
            if entry["source"] == "ours":
                named = re.match(r"(\d{4})_(\d+)_(.*)\.txt$", entry["file"])
                year, number, title = named.group(1), named.group(2), named.group(3).strip()
                act_name = f"{' '.join(entry['jurisdiction'].split())} {year} {number} {title}".title()
                ours = text_blocks(path.read_text(encoding="utf-8", errors="replace"),
                                   f"{entry['jurisdiction'].upper()}_{year}_{number}_{title.upper()}", act_name, title,
                                   year)
                record["read_as"] = "text"
    if entry["source"] == "ours":
        act = ours
        extra, articles = schedules_from(back_matter(act, entry["title"]), entry["title"], record["schedule_notes"])
        act.sections.extend(extra)
        record["schedule_source"] = "ours" if extra or articles else None
        return act, articles, record
    state = "CENTRAL" if entry["jurisdiction"] == "Union of India" else "Telangana"
    fetched = json.loads((FETCHED / state / f"{entry['india_act_id']}.json").read_text(encoding="utf-8"))
    act_id, act_name, title, year = identity(entry, fetched)
    if entry["source"] == "india_code_pdf_text":
        texts = sorted((FETCHED / state / "files" / entry["india_act_id"]).glob("*.txt"))
        raw = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in texts[:1])
        try:
            act = read_act(raw, act_id=act_id, act_name=act_name, title=title, year=year, name=title)
        except ValueError:
            act, record["read_as"] = text_blocks(raw, act_id, act_name, title, year), "text"
        extra, articles = schedules_from(act.back_matter, title, record["schedule_notes"])
        act.sections.extend(extra)
        record["schedule_source"] = "India Code's PDF text" if extra or articles else None
        return act, articles, record
    pdf_sections: dict[str, str] = {}
    texts = sorted((ACT_TEXTS / state / entry["india_act_id"]).glob("*.txt"))
    for path in texts:
        if path.name[:1] == "H" or path.name[:2] == "Hh":
            continue
        try:
            read = read_act(path.read_text(encoding="utf-8", errors="replace"), act_id=act_id, act_name=act_name,
                            title=title, year=year, name=path.name)
        except ValueError:
            continue
        for section in read.sections:
            pdf_sections.setdefault(section.number, statute_words(section))
    our_back = back_matter(ours, title) if ours is not None else []
    our_sections = {section.number: statute_words(section) for section in (ours.sections if ours else [])}
    sections = []
    taken: dict[str, Section] = {}
    for entry_section in fetched["sections"]:
        section, notes = india_code_section(entry_section)
        if not section.number:
            continue
        if section.number in taken:
            # India Code holds a few sections twice (the Customs Act's s.79): the same words are
            # taken once; different words follow the first record's as its words.
            if taken[section.number].lines != section.lines:
                taken[section.number].lines.extend(section.lines)
            continue
        taken[section.number] = section
        text, changed, review = reconcile("\n".join(section.lines), pdf_sections.get(section.number),
                                          our_sections.get(section.number), words)
        section.lines = text.split("\n")
        sections.append(section)
        if any(notes.values()):
            record["notes"][section.number] = notes
        record["changed"].extend({"section": section.number, **change} for change in changed)
        record["review"].extend({"section": section.number, **item} for item in review)
    act = Act(act_id, act_name, title, year, sections)
    extra, articles = schedules_from(our_back, title, record["schedule_notes"])
    act.sections.extend(extra)
    record["schedule_source"] = "ours" if extra or articles else None
    return act, articles, record


# ----------------------------------------------------------------------------- passages


def article_rows(act: Act, articles: list[Article]) -> list[dict]:
    """The Limitation Act's articles, each one passage keyed "Article_<n>" (as the store keys
    them), its three columns kept apart in the passage's record for the page to lay out."""
    rows = []
    for article in articles:
        key = f"Article_{article.number}"
        words = "\n".join([article.number, *article.description, article.period, *article.starts])
        heading = " ".join(article.description)[:200]
        full = f"{act.act_name},  — Article {article.number}: {heading}\n{words}"
        chunk_id = f"{act.act_id}_SCHEDULE_{key}"
        rows.append({"atom_type": "schedule_article", "chunk_id": chunk_id, "parent_chunk_id": None,
                     "section_number": key, "blob": {
                         "chunk_id": chunk_id, "doc_type": "bare_act", "act_id": act.act_id, "act_name": act.act_name,
                         "year": "", "chapter": "", "section_number": key, "section_title": heading,
                         "sub_section": "", "clause": "", "sub_clause": "", "atom_type": "schedule_article",
                         "parent_chunk_id": "", "parent_chain": [key.lower()], "full_text": full, "keywords": [],
                         "schedule_columns": {"division": article.division, "part": article.part,
                                              "description": " ".join(article.description),
                                              "period": article.period, "time_from_which_period_begins_to_run":
                                                  " ".join(article.starts)}}})
    return rows


def cited(rows: list[dict]) -> list[dict]:
    """A schedule's passages cite it as the schedule does - "Order VII Rule 11", "Schedule 2" -
    not as a section ("s.Order_VII_Rule_11"); the statute's own words are untouched."""
    for row in rows:
        key = row["section_number"]
        if not re.match(r"^(?:Order|Schedule|Text)_", key):
            continue
        head, _, rest = row["blob"]["full_text"].partition("\n")
        shown = key.replace("_part_", " part ").replace("_", " ")
        row["blob"]["full_text"] = head.replace(f"s.{key}", shown, 1) + ("\n" + rest if rest else "")
    return rows


def check(rows: list[dict]) -> list[str]:
    """What the current search requires of a store (nm/core_engine/retrieval.py): identifiers
    that never repeat; within an Act and section, one root and every parent held there."""
    problems = []
    ids = Counter(row["chunk_id"] for row in rows)
    problems += [f"repeated identifier {chunk}" for chunk, count in ids.items() if count > 1][:20]
    by_section: dict[tuple, list[dict]] = {}
    for row in rows:
        by_section.setdefault((row["blob"]["act_id"], row["section_number"]), []).append(row)
    for (act_id, section), group in by_section.items():
        held = {row["chunk_id"] for row in group}
        roots = [row for row in group if not row["parent_chunk_id"]]
        if len(roots) != 1:
            problems.append(f"{act_id} {section}: {len(roots)} roots")
        orphans = [row["chunk_id"] for row in group if row["parent_chunk_id"] and row["parent_chunk_id"] not in held]
        if orphans:
            problems.append(f"{act_id} {section}: parent not held for {orphans[0]}")
    problems += [f"empty passage {row['chunk_id']}" for row in rows if not row["blob"]["full_text"].strip()][:20]
    return problems


def read_stage(only: set[str] | None) -> None:
    inventory = json.loads((EVIDENCE / "india_code_acts.json").read_text(encoding="utf-8"))
    matches = json.loads((EVIDENCE / "our_acts_vs_india_code.json").read_text(encoding="utf-8"))
    chosen = selection(inventory, matches)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "selection.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=1), encoding="utf-8")
    kept = [entry for entry in chosen if entry["source"]]
    if only:
        kept = [entry for entry in kept if entry["title"] in only or entry.get("india_act_id") in only]
    print(f"instruments: {len(kept)} kept, {sum(1 for entry in chosen if not entry['source'])} left out", flush=True)
    words = vocabulary()
    print(f"India Code's words: {len(words)} distinct", flush=True)
    rows, acts, failures, reviews = [], [], [], []
    seen_ids: set[str] = set()
    for number, entry in enumerate(kept, 1):
        try:
            act, articles, record = read_entry(entry, words)
        except (ValueError, OSError, KeyError) as error:
            failures.append({"title": entry["title"], "file": entry.get("file"), "error": str(error)[:300]})
            continue
        if act.act_id in seen_ids:
            failures.append({"title": entry["title"], "file": entry.get("file"),
                             "error": f"identifier {act.act_id} already taken by another instrument"})
            continue
        seen_ids.add(act.act_id)
        made = cited(passages_for(act)) + article_rows(act, articles)
        rows.extend(made)
        acts.append({"act_id": act.act_id, "act_name": act.act_name, "title": act.title, "year": act.year,
                     "jurisdiction": entry["jurisdiction"], "india_act_id": entry.get("india_act_id"),
                     "file": entry.get("file"), "source": entry["source"], "standing": record["standing"],
                     "kind": entry["kind"], "added": entry.get("added"), "sections": len(act.sections),
                     "articles": len(articles), "passages": len(made), "schedule_source": record["schedule_source"],
                     "schedule_notes": record["schedule_notes"],
                     "notes": record["notes"], "changed": record["changed"], "read_as": record.get("read_as", "sections")})
        reviews.extend({"act": act.title, **item} for item in record["review"])
        if number % 100 == 0:
            print(f"   {number}/{len(kept)} read, {len(rows)} passages", flush=True)
    problems = check(rows)
    sizes = Counter((row["blob"]["act_id"], row["section_number"]) for row in rows)
    long = [f"{act_id} {section}: {count} passages" for (act_id, section), count in sizes.items() if count > 500]
    (OUT / "long_provisions.json").write_text(json.dumps(long, ensure_ascii=False, indent=1), encoding="utf-8")
    with (OUT / "passages.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (OUT / "acts.json").write_text(json.dumps(acts, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "review.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "problems.json").write_text(json.dumps(problems, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"acts": len(acts), "passages": len(rows), "failures": len(failures),
                      "words taken from the PDF and ours": sum(len(act["changed"]) for act in acts),
                      "differences for review": len(reviews), "problems": len(problems), "first problems": problems[:8],
                      "provisions longer than search reads whole": long,
                      "by source": Counter(act["source"] for act in acts),
                      "by standing": Counter(act["standing"] for act in acts)}, default=str, indent=1), flush=True)


# ----------------------------------------------------------------------------- the store and its indexes


def index_stage() -> None:
    """The passages into a new store, its vectors and its words, and a candidate lineage record
    in the form the search checks - written beside, never over, the current one."""
    import faiss
    import numpy as np

    rows = [json.loads(line) for line in (OUT / "passages.jsonl").read_text(encoding="utf-8").splitlines()]
    problems = check(rows)
    if problems:
        raise SystemExit("the passages do not hold together; nothing indexed: " + "; ".join(problems[:5]))
    store = OUT / f"{OUT.name}.db"
    if store.exists():
        raise SystemExit(f"{store} exists; give a new folder rather than overwrite")
    # P21: each passage of an Act India Code does not list as in force says so, for the answer
    # and the reading pane; its words, and so its vectors, are untouched.
    standing = {act["act_id"]: act["standing"] for act in json.loads((OUT / "acts.json").read_text(encoding="utf-8"))}
    for row in rows:
        if standing.get(row["blob"]["act_id"]) == NOT_IN_FORCE:
            row["blob"]["standing"] = MARK
    with sqlite3.connect(store) as db:
        db.execute("create table chunks (doc_type text, pos integer, chunk_id text, act_id text, case_id text, "
                   "parent_chunk_id text, atom_type text, section_number text, blob text, primary key (doc_type, pos))")
        db.executemany("insert into chunks values (?,?,?,?,?,?,?,?,?)", [
            ("bare_act", pos, row["chunk_id"], row["blob"]["act_id"], None, row["parent_chunk_id"], row["atom_type"],
             row["section_number"], json.dumps(row["blob"], ensure_ascii=False)) for pos, row in enumerate(rows)])
        db.execute("create index idx_chunks_chunk_id on chunks(chunk_id)")
        db.execute("create index idx_chunks_doc_act on chunks(doc_type, act_id, section_number)")
        db.execute("create index idx_chunks_doc_parent on chunks(doc_type, parent_chunk_id)")
        db.execute("create table acts (act_id text primary key, record text)")
        db.executemany("insert into acts values (?,?)", [
            (act["act_id"], json.dumps(act, ensure_ascii=False))
            for act in json.loads((OUT / "acts.json").read_text(encoding="utf-8"))])
    texts = [row["blob"]["full_text"] for row in rows]
    encode = _real_encoder()
    vectors = np.asarray(encode(texts), dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    index_path = OUT / f"{OUT.name}.index"
    faiss.write_index(index, str(index_path))
    words_path = OUT / f"{OUT.name}_bm25s"
    if _real_bm25([bm25_tokens(text) for text in texts], words_path) != len(rows):
        raise SystemExit("the word index does not hold every passage")
    sample = list(range(0, len(texts), max(1, len(texts) // 60)))[:60]
    again = np.asarray(encode([texts[k] for k in sample]), dtype="float32")
    similarity = (again * vectors[sample]).sum(axis=1)
    record = {"schema": 1, "doc_type": "bare_act", "model": "BAAI/bge-large-en-v1.5", "dimensions": int(vectors.shape[1]),
              "metric": "inner product on normalised vectors", "passages": len(rows),
              "vector_index": {"path": f"{OUT.name}/{index_path.name}", "vectors": int(index.ntotal),
                               "bytes": index_path.stat().st_size, "sha256": _sha256(index_path)},
              "bm25": {"path": f"{OUT.name}/{words_path.name}", "num_docs": len(rows),
                       "params_sha256": _sha256(words_path / "params.index.json")},
              "passage_store": {"path": f"{OUT.name}/{store.name}", "count": len(rows), "max_pos": len(rows) - 1},
              "verified": {"sampled": len(sample), "same_vector": int((similarity > 0.99).sum()),
                           "lowest_similarity": round(float(similarity.min()), 4),
                           "mean_similarity": round(float(similarity.mean()), 4),
                           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
              "recorded_by": "pipeline/build_acts_v4.py", "recorded_at": datetime.now(timezone.utc).isoformat(
                  timespec="seconds"),
              "built_from": {"decisions": "Owner decisions P20-P23, 19 Oct 2026",
                             "india_code": str(FETCHED.relative_to(ROOT)), "act_texts": str(ACT_TEXTS.relative_to(ROOT)),
                             "ours": str(RAW.relative_to(ROOT))}}
    CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"passages": len(rows), "verified": record["verified"], "candidate": str(CANDIDATE)}, indent=1))


def marks_stage() -> None:
    """P21's Act-by-Act check applied to the store already built (19 Oct 2026): each instrument's
    standing as the selection now gives it goes into the store's Act records and its passages'
    marks; an instrument the selection now leaves out as another file of an India Code Act keeps
    its passages, recorded as left out with the stored India Code copy it is another file of, for
    the one-copy register to hide. Words, vectors and the word index are untouched; every change
    is listed in marks.json, and the store as it was is kept beside it."""
    inventory = json.loads((EVIDENCE / "india_code_acts.json").read_text(encoding="utf-8"))
    matches = json.loads((EVIDENCE / "our_acts_vs_india_code.json").read_text(encoding="utf-8"))
    chosen = {(entry["jurisdiction"], entry["file"]): entry for entry in selection(inventory, matches)
              if entry.get("file")}
    acts = json.loads((OUT / "acts.json").read_text(encoding="utf-8"))
    from_india_code = {act["india_act_id"]: act["act_id"] for act in acts
                       if act["india_act_id"] and act["source"] in ("india_code", "india_code_pdf_text")}
    changes = []
    for act in acts:
        entry = chosen.get((act["jurisdiction"], act["file"])) if act["file"] else None
        if entry is None:
            continue
        if entry["source"] is None and entry.get("same_act_as"):
            now = {"standing": None, "left_out": entry["left_out"],
                   "same_act_as": from_india_code[entry["same_act_as"]]}
        elif entry["source"] is None:
            raise SystemExit(f"{act['title']}: the selection now leaves it out ({entry['left_out']}); rebuild instead")
        else:
            now = {"standing": entry["standing"]}
        was = {key: act.get(key) for key in now}
        if was != now:
            changes.append({"act_id": act["act_id"], "title": act["title"], "was": was, "now": now})
            act.update(now)
    if not changes:
        print("the store's marks already follow the selection; nothing changed")
        return
    store = OUT / f"{OUT.name}.db"
    kept = OUT / f"{OUT.name}.before-marks.db"
    if not kept.exists():
        kept.write_bytes(store.read_bytes())
        (OUT / "acts.before-marks.json").write_bytes((OUT / "acts.json").read_bytes())
    records = {act["act_id"]: act for act in acts}
    passages = 0
    with sqlite3.connect(store) as db:
        for change in changes:
            act_id = change["act_id"]
            db.execute("update acts set record=? where act_id=?",
                       (json.dumps(records[act_id], ensure_ascii=False), act_id))
            marked = records[act_id]["standing"] == NOT_IN_FORCE
            for pos, blob in db.execute("select pos, blob from chunks where doc_type='bare_act' and act_id=?",
                                        (act_id,)).fetchall():
                item = json.loads(blob)
                if marked == ("standing" in item):
                    continue
                if marked:
                    item["standing"] = MARK
                else:
                    item.pop("standing")
                db.execute("update chunks set blob=? where doc_type='bare_act' and pos=?",
                           (json.dumps(item, ensure_ascii=False), pos))
                passages += 1
    (OUT / "acts.json").write_text(json.dumps(acts, ensure_ascii=False, indent=1), encoding="utf-8")
    previous = json.loads((OUT / "marks.json").read_text(encoding="utf-8")) if (OUT / "marks.json").exists() else []
    (OUT / "marks.json").write_text(json.dumps(previous + [{
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "why": "P21's Act-by-Act check after the build: Acts India Code lists under another title are other files "
               "of the India Code Act (P20); India Code lists no Finance or Appropriation Act",
        "passages_changed": passages, "changes": changes}], ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"instruments changed": len(changes), "passages changed": passages,
                      "marked now": sum(1 for act in acts if act["standing"] == NOT_IN_FORCE),
                      "left out now": sum(1 for act in acts if act.get("left_out"))}, indent=1))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    global OUT, CANDIDATE
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=("read", "index", "marks"), required=True)
    parser.add_argument("--only", help="titles or India Code act_ids, separated by '|': read these alone (a trial)")
    parser.add_argument("--out", default=OUT.name, help="the store's folder under legal_database/vector_store")
    args = parser.parse_args()
    if args.out != OUT.name:
        if not re.fullmatch(r"acts_v\d+", args.out):
            raise SystemExit("--out names a folder such as acts_v5")
        OUT = OUT.parent / args.out
        CANDIDATE = CANDIDATE.with_name(f"bare_{args.out}.lineage.json")
    sys.stdout.reconfigure(encoding="utf-8")
    if args.stage == "read":
        read_stage(set(args.only.split("|")) if args.only else None)
    elif args.stage == "index":
        index_stage()
    else:
        marks_stage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
