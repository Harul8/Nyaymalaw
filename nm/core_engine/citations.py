"""Check the case citations in a piece of text against the held judgments.

Identity is decided by exact keys only (`nm.shared.citation_contracts`): the
citation as written and its measured reporter-name equivalents. Nothing here
ranks and nothing tolerates a near miss, so a page that is off by one is not
held rather than "probably" another case.

Four outcomes, and each says what it does not mean:

    found             exact indexed key found for one held case ID; name,
                      quotation and legal use remain separate checks
    check             held, but the case name written beside it is a
                      different case, the citation leads to more than one
                      held judgment, or quoted words are not in the text
    not_held          no held judgment carries it. NOT "wrong" and NOT
                      "non-existent": the corpus is two courts, not India
    could_not_check   the index could not be read. Never shown as not held,
                      because an unread index and an absent citation look
                      identical and mean opposite things

Name comparison certifies only complete recorded-name agreement. Variations or
incomplete parsing stay unassessed; fuzzy matching may suggest, never identify.
Quoted words found in a judgment are words in the judgment, not
the court's holding -- they may be a party's submission or an earlier
judgment quoted -- and the result says so.

Nothing is stored and nothing is sent to a model: the text is read, checked
and returned to its caller.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from nm.shared.citation_contracts import CASE, READ_FORMATS, find_reporter_citations
from nm.shared.text_contracts import fold_spacing, words

CONTRACT = "citation_check_v2"
ROOT = Path(__file__).resolve().parents[2]
_EXCERPT = 280
_QUOTE_WORDS = 4  # a fragment shorter than this is a phrase, not a checkable quotation
_NAME_GAP = 60    # characters allowed between a case name and its citation


class IndexUnavailable(RuntimeError):
    """The case identity index cannot be read, or was built partially."""


class TextUnavailable(RuntimeError):
    """A held judgment's own text cannot be read."""


class CaseIdentityIndex:
    """Read-only access to the case identity index and the judgments it was built from."""

    def __init__(self, database: Path, judgments: Path):
        self.database, self.judgments = Path(database), Path(judgments)

    @classmethod
    def local(cls, root: Path | None = None) -> "CaseIdentityIndex":
        root = Path(root or ROOT)
        return cls(root / ".nm" / "identity.db", root / "legal_database" / "raw_data" / "CaseLaws")

    def _connect(self) -> sqlite3.Connection:
        if not self.database.is_file():
            raise IndexUnavailable(f"the case index is absent ({self.database.name})")
        con = None
        try:
            con = sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True)
            identity = dict(con.execute("select key, value from identity"))
            held = con.execute("select count(*) from cases").fetchone()[0]
        except sqlite3.Error as exc:
            if con is not None:
                con.close()
            raise IndexUnavailable(f"the case index could not be opened ({exc})") from exc
        if identity.get("partial") != "no":
            con.close()
            raise IndexUnavailable("the case index was built partially")
        if str(held) != identity.get("cases"):
            con.close()
            raise IndexUnavailable("the case index holds a different number of judgments than it records")
        return con

    def scope(self) -> dict:
        """What the index holds, measured from the index each time it is asked."""
        con = self._connect()
        try:
            metadata = dict(con.execute("select key, value from identity"))
            built = metadata.get("built_at")
            primary = [row[1] for row in sorted(con.execute("pragma table_info(citations)"),
                                               key=lambda row: row[5]) if row[5]]
            coverage = ("all_indexed_owners" if metadata.get("citation_ownership") == "all_pairs_v2"
                        and primary == ["citation_key", "case_id"] else "unassessed")
            courts = [{"court": court, "judgments": count, "from": first, "to": last}
                      for court, count, first, last in con.execute(
                          "select court, count(*), min(year), max(year) from cases "
                          "group by court order by count(*) desc")]
        except sqlite3.Error as exc:
            raise IndexUnavailable("the case index scope could not be read") from exc
        finally:
            con.close()
        return {"built_at": built, "judgments": sum(c["judgments"] for c in courts),
                "courts": courts, "collision_coverage": coverage}

    def judgments_for(self, keys: tuple[str, ...]) -> dict[str, dict]:
        """Every indexed owner of an exact key, grouped only by owned case ID."""
        con = self._connect()
        try:
            found = {}
            for key in keys:
                rows = con.execute(
                    "select c.case_id, c.source_file, c.court, c.year, c.title, c.decided_on, c.bench, "
                    "c.petitioner, c.respondent from citations x left join cases c using (case_id) "
                    "where x.citation_key = ? order by c.case_id", (key,)).fetchall()
                for row in rows:
                    if row[0] is None:
                        raise IndexUnavailable("a citation points to an unavailable case record")
                    identity = row[0]
                    if identity not in found:
                        found[identity] = dict(zip(("case_id", "source_file", "court", "year", "title",
                                                   "decided_on", "bench", "petitioner", "respondent"), row))
                        found[identity]["held_keys"] = [k for (k,) in con.execute(
                            "select distinct citation_key from citations where case_id = ? order by citation_key",
                            (identity,))]
                        found[identity]["matched_keys"] = []
                    if key not in found[identity]["matched_keys"]:
                        found[identity]["matched_keys"].append(key)
        except sqlite3.Error as exc:
            raise IndexUnavailable("the exact citation lookup could not be completed") from exc
        finally:
            con.close()
        return found

    def judgments_in_years(self, years: tuple[int, ...]) -> list[dict]:
        """Every held judgment decided in these years, for name-and-year suggestions."""
        con = self._connect()
        try:
            rows = con.execute(
                "select case_id, court, year, title, decided_on, bench, petitioner, respondent from cases "
                f"where year in ({','.join('?' * len(years))})", years).fetchall()
        finally:
            con.close()
        return [dict(zip(("case_id", "court", "year", "title", "decided_on", "bench", "petitioner",
                          "respondent"), row), held_keys=[]) for row in rows]

    def text(self, judgment: dict) -> str:
        path = self.judgments.joinpath(*str(judgment["source_file"]).replace("\\", "/").split("/"))
        if not path.resolve().is_relative_to(self.judgments.resolve()):
            raise TextUnavailable("the judgment's source location is outside the held corpus")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise TextUnavailable(f"the judgment's text could not be read ({path.name})") from exc
        for encoding in ("utf-8", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise TextUnavailable(f"the judgment's text is not readable text ({path.name})")


# --------------------------------------------------------------- names ----

#: Words that say nothing about WHICH case: parties every bench has seen, office
#: titles, places, reporters, and Indian name parts common enough that sharing
#: one proves nothing. A shared word from this list never counts as a match.
_GENERIC = frozenset("""
the and for with from into its his her their through thru vs versus anr ors others another etc
state states union india indian government govt republic central nation national
dead deceased lrs legal representatives represented heirs minor guardian next friend
secretary commissioner collector director officer chief general manager managing principal
registrar superintendent inspector police station public prosecutor magistrate judge court
district municipal municipality corporation council board bank ltd limited pvt private
company corp society cooperative cooperatives trust authority department dept ministry
committee commission tribunal university college school hospital office estate
mr mrs ms smt sri shri srimati kumari dr messrs
andhra pradesh telangana kerala tamil nadu karnataka maharashtra delhi bihar punjab haryana
rajasthan gujarat bengal west uttar madhya orissa odisha assam bombay madras calcutta mysore
hyderabad jammu kashmir himachal goa uttarakhand jharkhand chhattisgarh tripura manipur
air scc scr insc scale online supp cri crl
kumar singh rao reddy devi lal ram prasad sharma das khan ahmed babu naidu raju chand nath
gupta agarwal mohammed mohd muhammad bai ben begum
""".split())


def _distinctive(text: str | None) -> set[str]:
    return {w for w in words(text) if w.isalpha() and len(w) >= 3 and w not in _GENERIC}


def _name_beside(text: str, start: int, floor: int) -> str | None:
    """The case name written immediately before a citation, if one is."""
    window = text[floor:start]
    found = None
    for match in CASE.finditer(window):
        found = match
    if found is None or len(window) - found.end() > _NAME_GAP:
        return None
    # CASE may stop at a lowercase particle in the second party. Preserve the
    # rest of the written name; extra prose makes comparison unassessed, never
    # a reason to certify a truncated match.
    start = found.start()
    prefix = window[:start].strip()
    if prefix and _SIGNAL.sub("", prefix + " ").strip():
        start = 0  # Possible truncated first party: retain it, do not certify a suffix.
    return _SIGNAL.sub("", fold_spacing(window[start:].strip(" ,:;([\n")))


#: Words that introduce a citation rather than name a party: `In X v. Y`, `See X v. Y`.
_SIGNAL = re.compile(r"^(?:(?:In|See|Also|Cf\.?|And|But|Following|Per|Vide|Contra|Supra)\s+)+")


#: What may sit between two citations of ONE case written together:
#: `(1973) 4 SCC 225 : AIR 1973 SC 1461`, `...; also reported in ...`.
_PARALLEL = re.compile(r"[\s,;:=&()\[\]]*(?:(?:and|also|reported|in|at)[\s,;:=&()\[\]]*)*", re.I)


def _within(one: str, other: str, limit: int) -> bool:
    """Edit distance no greater than `limit` (bounded Levenshtein)."""
    if abs(len(one) - len(other)) > limit:
        return False
    row = list(range(len(other) + 1))
    for i, a in enumerate(one, 1):
        previous, row[0] = row[0], i
        for j, b in enumerate(other, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (a != b))
        if min(row) > limit:
            return False
    return row[-1] <= limit


def _names_agree(given: str, title: str) -> bool:
    """Does any distinctive word written agree with the judgment's name?

    Indian case names are spelt many ways (`Janaradhana`/`Janardhana`,
    `Goel`/`Gael`), joined or split (`Bhagatram`/`Bhagat Ram`) and shortened to
    initials (`BSNL`). Measured on 400 held judgments, exact word matching
    flagged the same case as a different one more often than it caught a real
    mismatch. This decides only whether to ask the advocate to check -- never
    which case a citation is -- so tolerance here cannot identify a wrong case.
    """
    written = [w for w in words(given) if w.isalpha()]
    mine = _distinctive(given) | {a + b for a, b in zip(written, written[1:])
                                  if len(a + b) >= 5 and (a not in _GENERIC or b not in _GENERIC)}
    theirs = _distinctive(title)
    every = [w for w in words(title) if w.isalpha()]
    joined = {a + b for a, b in zip(every, every[1:])}
    initials = {"".join(w[0] for w in every[i:j]) for i in range(len(every))
                for j in range(i + 3, min(len(every), i + 6) + 1)}
    acronyms = {w.lower() for w in re.findall(r"\b[A-Z]{3,6}\b", given)}
    for word in mine:
        if word in theirs or word in joined or (word in acronyms and word in initials):
            return True
        if len(word) >= 4 and any(len(t) >= 4 and _within(word, t, max(1, len(word) // 4)) for t in theirs):
            return True
    return False


def _party_words(judgment: dict) -> str:
    return " ".join(filter(None, (judgment["title"], judgment["petitioner"], judgment["respondent"])))


def _name_check(given: str | None, judgment: dict) -> str:
    if given is None:
        return "not_given"
    def normalized(value):
        return tuple("v" if token in {"v", "vs", "versus"} else token
                     for token in words(value or ""))
    supplied = normalized(given)
    alternatives = [judgment["title"]]
    if judgment.get("petitioner") and judgment.get("respondent"):
        alternatives.append(judgment["petitioner"] + " v " + judgment["respondent"])
    # This proves textual agreement only. It does not establish a correct
    # citation-to-case linkage or decide that a spelling variant is another case.
    if "v" in supplied and any(supplied == normalized(name) for name in alternatives):
        return "matches_recorded_name"
    return "not_assessed"


def _suggestions(given: str | None, citation, index: "CaseIdentityIndex") -> list[dict]:
    """Held judgments whose name and year match a citation the index does not record.

    RANKED, NEVER IDENTIFIED: the index may hold the case without this
    citation (it records only the citations its source listed). Every
    distinctive word written must agree, and the decision year must be the
    reporter year or the one before, so a suggestion is narrow -- and it is
    still only a suggestion, shown as unconfirmed.
    """
    if given is None or len(_distinctive(given)) < 1:
        return []
    out = []
    for judgment in index.judgments_in_years((citation.year - 1, citation.year)):
        party = _party_words(judgment)
        if all(_names_agree(word, party) for word in _distinctive(given)):
            out.append(judgment)
    return out[:3] if len(out) <= 3 else []


# -------------------------------------------------------------- quotes ----

_QUOTATION = re.compile(r"“([^”]+)”|\"([^\"]+)\"")
_PARAGRAPH = re.compile(r"\n[ \t]*\n")
_FRAGMENT_BREAK = re.compile(r"\.\s?\.\s?\.|…|\[[^\]]*\]")
_TYPOGRAPHY = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-",
                             " ": " "})


def _plain(text: str) -> str:
    """The quotation comparison: whitespace and typography only (`fold_spacing`), case kept."""
    return fold_spacing((text or "").translate(_TYPOGRAPHY))


def _fragments(quote: str) -> list[str]:
    parts = [_plain(part).strip(" ,;:.'\"") for part in _FRAGMENT_BREAK.split(quote)]
    return [part for part in parts if len(part.split()) >= _QUOTE_WORDS]


def _find_in_order(fragments: list[str], text: str) -> tuple[int, int] | None:
    """Where the quotation sits, every fragment found in order; the first letter may differ in case."""
    at, first = 0, None
    for fragment in fragments:
        hits = [i for i in (text.find(fragment, at), text.find(fragment[0].swapcase() + fragment[1:], at))
                if i >= 0]
        if not hits:
            return None
        found = min(hits)
        first = found if first is None else first
        at = found + len(fragment)
    return first, at


def _quotations(text: str) -> list[dict]:
    starts = [0] + [m.end() for m in _PARAGRAPH.finditer(text)]
    out = []
    for match in _QUOTATION.finditer(text):
        paragraph = max(i for i, s in enumerate(starts) if s <= match.start())
        out.append({"quote": match.group(1) or match.group(2), "start": match.start(), "paragraph": paragraph})
    return out


# --------------------------------------------------------------- check ----

def _held_twice(one: dict, other: dict) -> bool:
    """Only the same owned case ID. Similar names/date/court are not identity."""
    return one["case_id"] == other["case_id"]


def _distinct(judgments: dict[str, dict]) -> list[dict]:
    """The different judgments a citation's keys lead to."""
    distinct: list[dict] = []
    for judgment in judgments.values():
        same = next((held for held in distinct if _held_twice(held, judgment)), None)
        if same is None:
            distinct.append({**judgment, "also_held_as": []})
        elif judgment["case_id"] != same["case_id"] and judgment["case_id"] not in same["also_held_as"]:
            same["also_held_as"].append(judgment["case_id"])
    return distinct


def _scope_statement(scope: dict) -> str:
    courts = "; ".join(f"{c['court']}, {c['from']}-{c['to']} ({c['judgments']:,})" for c in scope["courts"])
    telangana = any("telangana" in c["court"].lower() and "pre-telangana" not in c["court"].lower()
                    for c in scope["courts"])
    missing = "" if telangana else " No Telangana High Court judgments are held."
    collision = (" The existing index does not establish that all owners of a citation key were retained."
                 if scope["collision_coverage"] == "unassessed" else "")
    return (f"Checked against {scope['judgments']:,} judgments: {courts}.{missing} "
            "A citation from any other court or reporter reads as not held." + collision)


def _public(judgment: dict) -> dict:
    return {**{key: judgment[key] for key in ("case_id", "title", "court", "decided_on", "bench",
                                            "held_keys", "also_held_as")},
            "matched_keys": list(judgment.get("matched_keys", []))}


def check_citations(text: str, index: CaseIdentityIndex) -> dict:
    """Every case citation in `text`, each checked against the held judgments."""
    text = text or ""
    citations = find_reporter_citations(text)
    result = {"contract": CONTRACT, "citations": [], "formats": list(READ_FORMATS),
              "summary": {"found": 0, "check": 0, "not_held": 0, "could_not_check": 0}}
    try:
        scope = index.scope()
        result["index"] = {"state": "readable", "reason": None, "scope": scope,
                           "statement": _scope_statement(scope)}
    except IndexUnavailable as exc:
        result["index"] = {"state": "unavailable", "reason": str(exc), "scope": None,
                           "statement": f"Citations could not be checked: {exc}."}
    if not citations:
        result["statement"] = ("No case citation was recognised in this text. Formats read: "
                               + "; ".join(READ_FORMATS) + ".")
        return result

    paragraph_starts = [0] + [m.end() for m in _PARAGRAPH.finditer(text)]

    def paragraph_of(position: int) -> int:
        return max(i for i, s in enumerate(paragraph_starts) if s <= position)

    rows, previous, texts = [], None, {}
    for number, citation in enumerate(citations, 1):
        floor = paragraph_starts[paragraph_of(citation.start)]
        between = text[previous["end"]:citation.start] if previous else ""
        if previous and previous["paragraph"] == paragraph_of(citation.start) and _PARALLEL.fullmatch(between):
            given = previous["name_given"]
        else:
            given = _name_beside(text, citation.start, max(floor, previous["end"] if previous else 0))
        row = {"id": f"c{number}", "text": citation.text, "start": citation.start, "end": citation.end,
               "reporter": citation.reporter, "keys": list(citation.keys),
               "paragraph": paragraph_of(citation.start), "name_given": given, "name_check": None,
               "judgments": [], "suggestions": [], "quotes": [], "reasons": [], "status": None,
               "lookup": "unavailable", "legal_validity": "not_assessed"}
        rows.append(row)
        previous = row
        if result["index"]["state"] != "readable":
            row["status"] = "could_not_check"
            row["reasons"].append(f"The case index could not be read ({result['index']['reason']}), "
                                  "so this citation was not checked.")
            continue
        try:
            held = _distinct(index.judgments_for(citation.keys))
        except IndexUnavailable as exc:
            row["status"] = "could_not_check"
            row["reasons"].append(f"The case index could not be read ({exc}), so this citation was not checked.")
            continue
        row["judgments"] = held
        row["lookup"] = "not_held" if not held else "ambiguous" if len(held) > 1 else "found"
        if not held:
            row["status"] = "not_held"
            row["reasons"].append("Nyaymalaw holds no judgment under this citation. That does not make it "
                                  "wrong: check it in the reporter.")
            try:
                row["suggestions"] = _suggestions(given, citation, index)
            except IndexUnavailable:
                row["suggestions"] = []
            if row["suggestions"]:
                row["reasons"].append(
                    "Nyaymalaw holds a judgment whose name and year match what is written, but does not "
                    "record this citation for it, so it cannot confirm they belong together: "
                    + "; ".join(f"{j['title']} ({j['court']}, {j['decided_on']})" for j in row["suggestions"])
                    + ".")
        elif len(held) > 1:
            row["status"] = "check"
            row["reasons"].append("This citation leads to more than one held judgment: "
                                  + "; ".join(f"{j['title']} ({j['decided_on']})" for j in held)
                                  + ". Check which one is meant.")
        else:
            judgment = held[0]
            row["name_check"] = _name_check(given, judgment)
            if row["name_check"] == "not_given":
                row["reasons"].append(f"Held: {judgment['title']}. No case name is written beside this "
                                      "citation; confirm this is the case meant.")
            elif row["name_check"] == "not_assessed":
                row["reasons"].append(f"Written name: {given}. Recorded name: {judgment['title']}. "
                    "Complete name agreement was not established; check that the name and citation "
                    "belong together. A spelling variation or shortened name does not establish a different case.")
            else:
                row["reasons"].append(f"Held: {judgment['title']}, {judgment['court']}, {judgment['decided_on']}.")

    # Quotations belong to the citations of their own paragraph, or of the
    # paragraph just before when that one ends in a colon and cites a case.
    by_paragraph: dict[int, list[dict]] = {}
    for row in rows:
        by_paragraph.setdefault(row["paragraph"], []).append(row)
    for quotation in _quotations(text):
        paragraph = quotation["paragraph"]
        owners = by_paragraph.get(paragraph)
        if not owners and paragraph > 0 and text[paragraph_starts[paragraph - 1]:paragraph_starts[paragraph]].rstrip().endswith(":"):
            owners = by_paragraph.get(paragraph - 1)
        owners = [row for row in owners or () if len(row["judgments"]) == 1]
        if not owners:
            continue
        fragments = _fragments(quotation["quote"])
        outcomes = {}
        for row in owners:
            judgment = row["judgments"][0]
            if not fragments:
                outcomes[row["id"]] = {"result": "not_assessed",
                                       "detail": "Too short to check as a quotation."}
                continue
            try:
                source = texts.get(judgment["case_id"]) or _plain(index.text(judgment))
            except TextUnavailable as exc:
                outcomes[row["id"]] = {"result": "not_assessed", "detail": f"Not checked: {exc}."}
                continue
            texts[judgment["case_id"]] = source
            span = _find_in_order(fragments, source)
            if span:
                outcomes[row["id"]] = {"result": "found", "detail": (
                    "These words are in the judgment's text. Read them in context: they may be the court's "
                    "reasoning, a party's submission or an earlier judgment quoted."),
                    "excerpt": {"before": source[max(0, span[0] - _EXCERPT):span[0]],
                                "words": source[span[0]:span[1]],
                                "after": source[span[1]:span[1] + _EXCERPT]}}
            else:
                outcomes[row["id"]] = {"result": "not_found",
                                       "detail": "These words are not in the held text of this judgment."}
        found_in = [row for row in owners if outcomes[row["id"]]["result"] == "found"]
        for row in owners:
            outcome = outcomes[row["id"]]
            if outcome["result"] == "not_found" and found_in:
                outcome = {"result": "found_elsewhere", "detail": "Found in another judgment cited here: "
                           + "; ".join(r["judgments"][0]["title"] for r in found_in) + "."}
            row["quotes"].append({"quote": quotation["quote"], **outcome})
            if outcome["result"] == "not_found":
                row["status"] = "check"
                row["reasons"].append("A quotation beside this citation is not in the held text of the "
                                      "judgment it leads to.")

    for row in rows:
        if row["status"] is None:
            row["status"] = "found"
        row["judgments"] = [_public(j) for j in row["judgments"]]
        row["suggestions"] = [_public({**j, "also_held_as": []}) for j in row["suggestions"]]
        result["summary"][row["status"]] += 1
        result["citations"].append(row)
    counts = result["summary"]
    result["statement"] = (f"{len(rows)} citation{'s' if len(rows) != 1 else ''} recognised: "
                           f"{counts['found']} found, {counts['check']} to check, "
                           f"{counts['not_held']} not held by Nyaymalaw, "
                           f"{counts['could_not_check']} could not be checked.")
    return result
