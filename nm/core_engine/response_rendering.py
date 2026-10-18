"""Code-owned rendering of the exact independently accepted response version."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import re

from nm.core_engine import calculation, limitation, research, response_authorities, response_review
from nm.core_engine import response_writer
from nm.shared.citation_contracts import case_short_names, statute_title

LEGACY_CONTRACT = "core_response_rendering_v1"
#: Authority-bound rendering with each source under its stored title.
STORED_TITLE_CONTRACT = "core_response_rendering_v2"
#: v2 with statutes under their shown names (owner decisions, 10-11 Oct 2026).
SHOWN_NAME_CONTRACT = "core_response_rendering_v3"
#: v3 linking each source at the words that cite it, never a whole paragraph;
#: sources not cited by name follow the paragraph as markers (11 Oct 2026).
CITED_WORDS_CONTRACT = "core_response_rendering_v4"
#: v4 with a heading before each dispute's part when a reply answers more than one
#: dispute, in the understanding's own name for it (owner decision, 15 Oct 2026).
HEADINGS_CONTRACT = "core_response_rendering_v5"
#: v5 linking the shorter case names an answer writes ('Bachhaj Nahar v Nilima Mandal',
#: 'Hero Vinoth') to the judgment the paragraph used (owner decision, 15 Oct 2026).
SHORT_NAME_CONTRACT = "core_response_rendering_v6"
#: v6 also showing each page of a document the advocate sent that a paragraph cites,
#: under the document's name and page (owner decisions, 15 Oct 2026).
DOCUMENT_PAGES_CONTRACT = "core_response_rendering_v7"
#: v7 with a code-owned Working box for each time limit worked out (item 9, 15 Oct 2026).
WORKING_CONTRACT = "core_response_rendering_v8"
#: v8 with the date each limit's standing was worked out, so a reopened answer never
#: shows its days left or passed as if counted today (open items round, 16 Oct 2026).
AS_OF_CONTRACT = "core_response_rendering_v9"
#: v9 that may release an answer with sections held back (owner decision, 17 Oct 2026;
#: gate G-SECTION): what the review or the date check still found after the rewrites is
#: confined to sections, so those are left out and code says so in their place. Each
#: paragraph shown names its own draft paragraph.
HELD_CONTRACT = "core_response_rendering_v10"
#: v10 with each source linked at the words its use names and no markers after a
#: paragraph, and each dispute's summary opening the answer under "In short" (owner
#: decisions, 17 Oct 2026; writer v5).
WORDS_CONTRACT = "core_response_rendering_v11"
#: v11 listing after a paragraph each source it uses but does not link (18 Oct 2026, writer
#: v7, where a source is linked from the writer's own words only where it chose to).
LISTED_CONTRACT = "core_response_rendering_v12"
#: v12 that may also hold back a section code's own checks still refused after the
#: rewrites NM may make, named in the saved release record (owner, 18 Oct 2026: "withhold
#: only the failed part and pass the remaining part"); the answer is otherwise v12's.
CONTRACT = "core_response_rendering_v13"
#: The versions that list after a paragraph each source it does not link.
_LISTED = (LISTED_CONTRACT, CONTRACT)
#: The versions that link each source at its own words and open with "In short".
_WORDED = (WORDS_CONTRACT, *_LISTED)
_HOLDS = (HELD_CONTRACT, *_WORDED)
_AS_OF = (AS_OF_CONTRACT, *_HOLDS)
_WORKING = (WORKING_CONTRACT, *_AS_OF)
_CITED = (CITED_WORDS_CONTRACT, HEADINGS_CONTRACT, SHORT_NAME_CONTRACT, DOCUMENT_PAGES_CONTRACT, *_WORKING)
_LEGAL = {"provision", "judgment"}
_ROLES = {"provision": "legislative_text", "court_disposition": "court_conclusion",
          "court_reasoning": "court_reasoning", "party_submission": "party_submission",
          "quoted_authority": "quoted_authority", "uncertain": "unclear"}
_ROLE_LABELS = {"original_account": "Original account", "opposing_account": "Opposing account",
    "contract": "Quoted contract terms", "provision": "Legislative text",
    "party_submission": "Party submission", "court_reasoning": "Court reasoning",
    "court_disposition": "Court disposition", "quoted_authority": "Quoted authority",
    "uncertain": "Unresolved source role", "supplied_document": "Document the advocate sent"}


def _statement(unit, use):
    treatment = use["treatment_source"]
    return {"assertion_statement": unit["text"],
        "assertion_role": _ROLES.get(use["role"], use["role"]),
        "source_role": use["role"], "support_excerpt": use["text"],
        "owner_label": use["speaker"], "owner_excerpt": "", "scope_excerpt": "",
        "source_treatment": use["treatment"].replace("_", " "),
        "treatment_excerpt": treatment["text"] if treatment else "", "reason": ""}


def _title(row, shown_names):
    """The reader's name for a source; statute words are never renamed."""
    if shown_names and row["kind"] == "provision":
        return statute_title(row["title"], row["source_identity"].get("act_id", ""))
    return row["title"]


def _sources(unit, catalogue, shown_names=False, documents=False):
    statements = {}
    labels = {}
    shown = _LEGAL | ({"document"} if documents else set())
    for use in unit["uses"]:
        identity = use["source_id"]
        if catalogue[identity]["kind"] in shown:
            statements.setdefault(identity, []).append(_statement(unit, use))
            labels.setdefault(identity, _ROLE_LABELS[use["role"]])
        treatment = use["treatment_source"]
        if treatment is not None and catalogue[treatment["source_id"]]["kind"] in _LEGAL:
            identity = treatment["source_id"]
            # The exact treatment is selected independently. Its statement role is
            # not inferred from proximity, parser metadata or a party's own label.
            statements.setdefault(identity, []).append({
                "assertion_statement": treatment["text"], "assertion_role": "unclear",
                "source_role": "treatment_support", "support_excerpt": treatment["text"],
                "owner_label": None, "owner_excerpt": "", "scope_excerpt": "",
                "source_treatment": "not applicable", "treatment_excerpt": "", "reason": ""})
            labels.setdefault(identity, "Passage selected for court treatment")

    rendered = []
    for identity, uses in statements.items():
        row = catalogue[identity]
        verification = deepcopy(uses[0])
        related = []
        for related_id, related_uses in statements.items():
            source = catalogue[related_id]
            source_title = _title(source, shown_names)
            for index, statement in enumerate(related_uses):
                if related_id == identity and index == 0:
                    continue
                related.append({**deepcopy(statement), "source_id": related_id,
                    "title": source_title, "locator": source["locator"],
                    "assertion_statement": " · ".join(filter(None, [source_title,
                        source["locator"]])) + ": " + statement["assertion_statement"]})
        verification["context_statements"] = related
        title = _title(row, shown_names)
        rendered.append({"brain": True, "id": identity, "digest": row["digest"],
            "kind": row["kind"], "label": title, "title": title,
            # This is a reader label, never an invented paragraph/section number.
            "locator": row["locator"] or "Saved passage", "text": row["text"],
            "qualification": labels[identity] + ".", "verification": verification})
    return rendered


def _unique_span(text, phrase):
    if not phrase:
        return None
    start = text.find(phrase)
    if start < 0 or text.find(phrase, start + 1) >= 0:
        return None
    end = start + len(phrase)
    word = lambda char: char.isalnum() or char == "_"
    if (start and word(phrase[0]) and word(text[start - 1])
            or end < len(text) and word(phrase[-1]) and word(text[end])):
        return None
    return start, end


def _anchors(text, sources):
    owners = {}
    for index, source in enumerate(sources):
        title, locator = source["title"], source["locator"]
        phrases = {title, f"{title} {locator}", f"{title} · {locator}"}
        # Bare numbers cannot identify a cited passage rather than a date/amount.
        if locator and not locator.isdecimal() and locator != "Saved passage":
            phrases.add(locator)
        for phrase in phrases:
            if phrase:
                owners.setdefault(phrase, set()).add(index)
    candidates = []
    for phrase, indices in owners.items():
        span = _unique_span(text, phrase)
        if len(indices) == 1 and span is not None:
            candidates.append((span[0], span[1], phrase, next(iter(indices))))
    chosen, linked = [], set()
    for start, end, phrase, index in sorted(candidates, key=lambda c: (-(c[1] - c[0]), c[0], c[3])):
        if index in linked or any(start < prior[1] and end > prior[0] for prior in chosen):
            continue
        chosen.append((start, end, phrase, index))
        linked.add(index)
    if not chosen and sources:
        chosen = [(0, len(text), text, 0)]
    return [{"text": phrase, "source_id": sources[index]["id"], "source_index": index}
            for _, _, phrase, index in sorted(chosen)]


def _span(text, phrase):
    """The one place a phrase occurs, ignoring case, on word boundaries."""
    if not phrase or not phrase.strip():
        return None
    found = [m.span() for m in re.finditer(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", text, re.I)]
    return found[0] if len(found) == 1 else None


def _names(source):
    title = source["title"]
    names = {title}
    if title[:4].casefold() == "the ":
        names.add(title[4:])
    return {name for name in names if name.strip()}


# A sentence ends at terminal punctuation followed by space and a capital letter;
# "s. 170", "No. 5" and "Rs. 50,000" therefore stay inside their sentence.
_SENTENCE_END = re.compile(r"[.!?](?=\s+[A-Z(\"'“])")


def _sentence(text, start, end):
    begin = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    after = _SENTENCE_END.search(text, end)
    return text[begin:after.start() + 1 if after else len(text)]


def _short_names(source):
    """v6: the shorter names an advocate writes for a used judgment (one owner:
    nm/shared/citation_contracts.py)."""
    return case_short_names(source["title"]) if source["kind"] == "judgment" else set()


def _worded(unit, sources, *, listed=False):
    """v11 (owner decisions, 17 Oct 2026): each shown source is linked at the words of the
    paragraph its use names, where they stand; no marker follows the paragraph. Where two
    sources name overlapping words the first keeps the link, and the reading pane opened
    from it offers the others. listed (v12): each shown source left without a link follows
    the paragraph as a marker, which the page folds under "Sources"."""
    index = {source["id"]: number for number, source in enumerate(sources)}
    candidates = sorted((use["words"]["start"], use["words"]["end"], index[use["source_id"]])
                        for use in unit["uses"] if use.get("words") and use["source_id"] in index)
    chosen, linked = [], set()
    for start, end, number in candidates:
        if number in linked or any(start < prior[1] and end > prior[0] for prior in chosen):
            continue
        chosen.append((start, end, number))
        linked.add(number)
    markers = [{"source_id": source["id"], "source_index": number} for number, source in enumerate(sources)
               if listed and number not in linked]
    return [{"text": unit["text"][start:end], "source_id": sources[number]["id"], "source_index": number,
             "start": start, "end": end} for start, end, number in chosen], markers


def _cited_words(text, sources, authority, *, short=False):
    """v4: link a source at the words that cite it and list the rest as markers.

    Words come from the authority checks (a case citation matched to one used
    judgment; a provision reference binding one used provision whose Act is
    named in the same sentence) and from a source's own name or locator found
    once, ignoring case. A name shared by several used sources, a bare number or
    the whole paragraph never becomes a link.
    """
    index = {source["id"]: number for number, source in enumerate(sources)}
    candidates = []
    for row in authority["case_associations"]:
        matched = {index[i] for i in row["matching_source_ids"] if i in index}
        if row["association"] == "matched" and len(matched) == 1:
            candidates.append((row["start"], row["end"], matched.pop(), 0))
    for row in authority["prose_provisions"]:
        matched = sorted(index[i] for i in row["candidate_source_ids"] if i in index)
        if row["key_match"] != "one_used_identity" or not matched:
            continue
        sentence = _sentence(text, row["start"], row["end"])
        if any(re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", sentence, re.I)
               for name in _names(sources[matched[0]])):
            candidates.append((row["start"], row["end"], matched[0], 0))
    owners, proper = {}, set()
    for number, source in enumerate(sources):
        locator = source["locator"]
        phrases = set(_names(source))
        if short:
            names = _short_names(source)
            phrases |= names
            # A one-word party name links only where it is written as a name.
            proper |= {name.casefold() for name in names if len(name.split()) == 1}
        if locator and locator != "Saved passage":
            phrases |= {f"{name}{joint}{locator}" for name in _names(source) for joint in (" ", " · ")}
            if not locator.isdecimal():
                phrases.add(locator)
        for phrase in phrases:
            owners.setdefault(phrase.casefold(), (phrase, set()))[1].add(number)
    for phrase, numbers in owners.values():
        span = _span(text, phrase)
        if span is not None and phrase.casefold() in proper and not text[span[0]].isupper():
            span = None
        if len(numbers) == 1 and span is not None:
            candidates.append((span[0], span[1], next(iter(numbers)), 1))
    chosen, linked = [], set()
    for start, end, number, rank in sorted(candidates, key=lambda c: (c[3], -(c[1] - c[0]), c[0], c[2])):
        if (number in linked or (start, end) == (0, len(text))
                or any(start < prior[1] and end > prior[0] for prior in chosen)):
            continue
        chosen.append((start, end, number))
        linked.add(number)
    anchors = [{"text": text[start:end], "source_id": sources[number]["id"],
                "source_index": number, "start": start, "end": end}
               for start, end, number in sorted(chosen)]
    markers = [{"source_id": source["id"], "source_index": number}
               for number, source in enumerate(sources) if number not in linked]
    return anchors, markers


#: Shown elements that are not draft paragraphs: v5 headings, v8 Working boxes and v10
#: code's notices about sections held back.
NOT_PARAGRAPHS = frozenset({"HEADING", "WORKING", "NOTICE", "HELD"})


def unit_index(elements, element):
    """The draft paragraph a rendered element shows. Headings (v5), Working boxes (v8,
    17 Oct 2026: they had been counted as paragraphs) and notices have no paragraph of
    their own; from v10 each paragraph names its own, as held sections are left out."""
    if not 0 <= element < len(elements) or elements[element].get("kind") in NOT_PARAGRAPHS:
        raise IndexError("This rendered element shows no draft paragraph")
    if "unit" in elements[element]:
        return elements[element]["unit"]
    return element - sum(1 for item in elements[:element] if item.get("kind") in NOT_PARAGRAPHS)


#: What a held section was to cover when it answers no single dispute.
OPENING = "the opening and the points not tied to one dispute"
#: What the check found, in plain words, by its fixed category; {where} is the section or
#: the answer.
_FOUND = {"grounding": "a statement was not supported by the words it relies on",
          "attribution": "a statement was attributed to a judgment from a passage that is not the court's own reasoning",
          "quotation": "a quotation did not match its source word for word",
          "omission": "something {where} needed was missing",
          "framing": "{where} framed the matter in a way its sources do not support",
          "effect": "{where} claimed an outcome that was not established"}
_DATE_FOUND = ("a date was stated that is not in your messages or documents, the sources or the time "
               "limits code worked out")
#: The short IDs the models are shown, as words a reader can follow.
_SHORT_IDS = re.compile(r"\b(?:U|DOC|M|P|J|C|K)\d+\b")
_SHORT_WORDS = {"U": "a paragraph", "DOC": "a document page", "M": "a message", "P": "a provision", "J": "a judgment",
                "C": "a checklist item", "K": "an item on the matter's checklist"}


def held_sections(draft, review, date_findings=()):
    """G-SECTION (owner decision, 17 Oct 2026): the sections (one dispute's part each) of
    an answer that what the review or the date check still finds is confined to. [] when
    nothing is found; None when what is found is not confined - a finding that names no
    paragraph concerns the whole answer, an answer not written in sections has none to
    hold, and an answer that would keep no dispute's section has nothing to release."""
    findings = [*([] if review["accepted"] else review["proposal"]["findings"]), *date_findings]
    if not findings:
        return []
    parts = draft.get("parts") or []
    if not parts or any(not finding["unit_ids"] for finding in findings):
        return None
    affected = {identity for finding in findings for identity in finding["unit_ids"]}
    held = [index for index, ids in enumerate(response_writer.part_ids(draft)) if ids & affected]
    if all(part["dispute_id"] is None or index in held for index, part in enumerate(parts)):
        return None
    return held


#: What code's own checks found in a section they held back (v13), in plain words.
_CODE_FOUND = {"quotation": _FOUND["quotation"],
               "checks": "what was written did not pass NM's own checks of its form and sources"}


def _release(draft, review, held, layout=None):
    """The saved release record checked against the review and the date findings it
    carries (the date check reads today's date, so its findings are kept, not redone).
    From v13 (layout given) it may also name, as "unwritten", the sections code's own
    checks held back: exactly the parts of the answer's layout the draft does not hold,
    in order (dispute None: the opening), each with what code found; and, as "trimmed", the
    sections shown without checklist items code's checks refused, in order, each with how
    many and what code found."""
    if held is None:
        return [], [], [], []
    known = {unit["id"] for unit in draft["units"]}.union(*response_writer.part_ids(draft))
    optional = ({"unwritten", "trimmed"} & set(held)) if layout is not None and isinstance(held, dict) else set()
    if (not isinstance(held, dict) or set(held) != {"parts", "date_findings"} | optional
            or not isinstance(held["date_findings"], list) or any(
                not isinstance(f, dict) or f.get("category") != "grounding" or not f.get("unit_ids")
                or not set(f["unit_ids"]) <= known or not isinstance(f.get("mismatch"), str)
                for f in held["date_findings"])):
        raise ValueError("Unknown release record")
    unwritten, trimmed = held.get("unwritten", []), held.get("trimmed", [])
    shown = [part["dispute_id"] for part in draft.get("parts") or []]
    if layout is not None:
        missing = [part["dispute_id"] for part in layout if part["dispute_id"] not in shown]
        if ("unwritten" in held or missing) and (
                not isinstance(unwritten, list) or not unwritten or any(
                    not isinstance(entry, dict) or set(entry) != {"dispute_id", "found"}
                    or entry["found"] not in _CODE_FOUND for entry in unwritten)
                or [entry["dispute_id"] for entry in unwritten] != missing
                or not any(identity is not None for identity in shown)):
            raise ValueError("Unknown release record")
        if "trimmed" in held and (
                not isinstance(trimmed, list) or not trimmed or any(
                    not isinstance(entry, dict) or set(entry) != {"dispute_id", "items", "found"}
                    or entry["dispute_id"] is None or entry["dispute_id"] not in shown
                    or type(entry["items"]) is not int or entry["items"] < 1 or entry["found"] not in _CODE_FOUND
                    for entry in trimmed)
                or [entry["dispute_id"] for entry in trimmed]
                != [identity for identity in shown if identity in {entry["dispute_id"] for entry in trimmed}]):
            raise ValueError("Unknown release record")
    expected = held_sections(draft, review, held["date_findings"])
    if expected is None or expected != held["parts"] or not (expected or unwritten or trimmed):
        raise ValueError("Held sections differ from what the checks found")
    return held["parts"], held["date_findings"], unwritten, trimmed


def _dispute_names(research_record):
    """The understanding's own name for each dispute, by its id."""
    names = {}
    if research_record.get("contract") in research.QUESTION_PLANS:
        for dispute in research_record["plan"]["proposal"]["understanding"]["disputes"]:
            names.setdefault(dispute["id"], dispute["name"])
    return names


def _part_names(research_record, draft):
    """Each section's name: the understanding's own name for its dispute, or OPENING."""
    names = _dispute_names(research_record)
    return [OPENING if part["dispute_id"] is None else names.get(part["dispute_id"], "") or "this dispute"
            for part in draft.get("parts") or []]


def _notice(kind, text, **extra):
    return {"kind": kind, "text": text, "source": None, "sources": [], "refs": [], "inline_citations": [],
            "citation_markers": [], "disclosure": True, **extra}


def found_words(findings, date_findings=(), *, where="the section"):
    """What the check found, in plain words (owner decision, 17 Oct 2026). Nothing that
    failed is shown: an omission says what is missing, so the check's own explanation
    follows it (short IDs shown as words); every other finding concerns words that were
    wrong, so only its category is said, in code's words; a date found nowhere likewise."""
    found = [_FOUND.get(f["category"], f["category"]).format(where=where)
             + (": " + _SHORT_IDS.sub(lambda m: _SHORT_WORDS[m.group().rstrip("0123456789")], f["mismatch"].strip())
                if f["category"] == "omission" else "")
             for f in findings]
    if date_findings:
        found.append(_DATE_FOUND)
    return " ".join(item if item.endswith(".") else item + "." for item in
                    (item[0].upper() + item[1:] for item in dict.fromkeys(found)))


def _held_notice(index, name, draft, findings, date_findings):
    """In a held section's place: what it was to cover and what the check found."""
    ids = response_writer.part_ids(draft)[index]
    said = found_words([f for f in findings if set(f["unit_ids"]) & ids],
                       [f for f in date_findings if set(f["unit_ids"]) & ids])
    return _notice("HELD", f"Held back: {name}. After the rewrites NM may make, the independent check still "
                   f"found a problem in this section, so it is not shown. What the check found: {said}",
                   held={"part": index, "section": name,
                         "retry": f"Please try the held-back section on {name} again."})


def _headings(research_record, draft, also=()):
    """Where each dispute's part begins, with the understanding's name for that dispute;
    none when the reply answers one dispute or was written whole. An opening part (no
    dispute) has no heading. also: the disputes of sections held back by code's checks,
    which the answer still covers (v13)."""
    parts = draft.get("parts") or []
    if len(({part["dispute_id"] for part in parts} | set(also)) - {None}) < 2:
        return {}
    names = {}
    if research_record.get("contract") in research.QUESTION_PLANS:
        for dispute in research_record["plan"]["proposal"]["understanding"]["disputes"]:
            names.setdefault(dispute["id"], dispute["name"])
    headings, start = {}, 0
    for part in parts:
        if part["dispute_id"] is None:
            start += part["units"]
            continue
        if part["dispute_id"] not in names or not names[part["dispute_id"]].strip():
            raise ValueError("A part of the reply names no dispute of its research")
        if part["dispute_id"] not in headings.values():
            headings[start] = part["dispute_id"]
        start += part["units"]
    return {position: names[identity] for position, identity in headings.items()}


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_RESULTS = {"early": "Early", "in_time": "In time", "late": "Late", "open": "Open", "expired": "Passed"}
_DAYS = {"early": "Days before the earliest day", "in_time": "Days to spare", "late": "Days late",
         "open": "Days left", "expired": "Days since the last day"}
_COURT_CLOSED = "Limitation Act s.4 not applied: the court calendar is not held"


def _date(iso):
    """'14 September 2026 (Monday)', the same everywhere it is shown."""
    day = date.fromisoformat(iso)
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year} ({_WEEKDAYS[day.weekday()]})"


def limit_rows(entry):
    """A dispute's time limit on the board (18 Oct 2026), in the Working box's own labelled
    rows: its last day and where it stands as of the day it was worked out, or why it was
    not assessed."""
    if "not_assessed" in entry:
        return [["Not assessed", entry["not_assessed"]]]
    state = entry["standing"]["state"]
    rows = [["Last day", _date(entry["last_day"])]]
    if entry.get("as_of"):
        rows.append(["As of", _date(entry["as_of"])])
    return rows + [["Result", _RESULTS[state]], [_DAYS[state], str(entry["standing"]["days"])]]


def _shown(working, earlier, as_of=None):
    """A Working box's labelled rows and lists: fixed labels over saved values, no
    sentences (owner, 15 Oct 2026). The screen and the research note both show these."""
    if "not_assessed" in working:
        return [["Not assessed", working["not_assessed"]]], []
    rows, start = [], working["runs_from"]

    def row(label, value):
        if value not in (None, ""):
            rows.append([label, str(value)])

    row("Provision", f"{working['provision']}, {working['act']}")
    row("Period", f"“{working['period']}”")
    if working["words"] and working["words"] != working["period"]:
        row("The Act’s words", f"“{working['words']}”")
    row("Runs from", _date(start["date"]))
    if start.get("after"):
        row("Starts the day after", earlier.get(start["after"], start["after"]))
    row("Event", start.get("event"))
    if start.get("quote"):
        row("Whose words", f"“{start['quote']}”")
    row("Counting starts after", _date(working["counting_starts_after"]))
    row("Period ends", _date(working["period_end"]))
    for copy in working["copies"]:
        row("Copy applied for / ready", f"{_date(copy['applied'])} / {_date(copy['ready'])}")
    if working["copy_days"]:
        row("Copy time left out (days)", working["copy_days"])
    row("Last day", _date(working["last_day"]))
    if working["earliest_day"]:
        row("Earliest day", _date(working["earliest_day"]))
    if working["step_taken"]:
        row("Taken on", _date(working["step_taken"]["date"]))
        row("Whose words", f"“{working['step_taken']['quote']}”")
    standing = working["standing"]
    if as_of:
        row("As of", _date(as_of))
    row("Result", _RESULTS[standing["state"]])
    row(_DAYS[standing["state"]], standing["days"])
    row("Court closed on the last day", _COURT_CLOSED)
    lists = [[title, list(items)] for title, items in (
        ("Owner’s ruling applied", working["owner_rulings"]), ("Assumed", working["assumptions"]),
        ("Still needed", working["missing"]), ("May extend time (not counted)", working["may_extend"])) if items]
    return rows, lists


def _working(record, *, as_of=False):
    """One code-owned Working box per time limit: code's arithmetic as data and as
    labelled rows; the answer's own words explain it. From v9 each says the date its
    standing was worked out."""
    boxes, earlier = [], {entry["id"]: entry["what"] for entry in record["calculations"]}
    for entry in record["calculations"]:
        provision, worked = entry["provision"], entry["working"]
        working = {"what": entry["what"], "provision": entry["provision_name"], "act": provision["act"],
                   "period": provision["period_words"], "words": provision.get("words") or provision.get("from"),
                   "runs_from": deepcopy(entry["start"]), "copies": deepcopy(entry["copies"]),
                   "step_taken": deepcopy(entry["done"]), "earliest_day": entry["earliest"],
                   "counting_starts_after": worked["start"], "period_end": worked["period_end"],
                   "copy_days": worked["copy_days"], "last_day": worked["last_day"],
                   "owner_rulings": [limitation.RULINGS[r] for r in worked["rulings"]],
                   "standing": deepcopy(entry["standing"]),
                   "assumptions": list(entry["assumptions"]), "missing": list(entry["missing"]),
                   "may_extend": list(entry["may_extend"])}
        boxes.append({"kind": "WORKING", "text": entry["what"], "source": None, "sources": [],
                      "refs": [], "inline_citations": [], "citation_markers": [], "working": working})
    for item in record["not_assessed"]:
        boxes.append({"kind": "WORKING", "text": item["what"], "source": None,
                      "sources": [], "refs": [], "inline_citations": [], "citation_markers": [],
                      "working": {"what": item["what"], "not_assessed": item["why"]}})
    for box in boxes:
        box["working"]["rows"], box["working"]["lists"] = _shown(
            box["working"], earlier, record.get("today") if as_of else None)
    return boxes


def render(context, research_record, sources, draft, review, execution=None, *,
           authority_evidence=None, contract=CONTRACT, time_limits=None, held=None):
    """No new prose; the declared version owns its exact reviewed dependencies. From v10,
    held (the saved release record) leaves out the sections G-SECTION holds back."""
    if contract not in {LEGACY_CONTRACT, STORED_TITLE_CONTRACT, SHOWN_NAME_CONTRACT, *_CITED}:
        raise ValueError("Unknown response rendering contract")
    checked_draft = response_writer.validate(draft, context, sources)
    if contract == LEGACY_CONTRACT:
        if authority_evidence is not None or review.get("contract") != response_review.LEGACY_CONTRACT:
            raise ValueError("Legacy rendering requires its original review without authority enrichment")
        checked_review = response_review.validate(review, context, research_record,
            sources, checked_draft, execution=execution)
    else:
        if authority_evidence is None or review.get("contract") not in {
                response_review.AUTHORITY_CONTRACT, response_review.ALIAS_CONTRACT,
                response_review.RESPECTED_CONTRACT, response_review.PARTS_CONTRACT,
                response_review.CHECKLIST_CONTRACT, response_review.ROWS_CONTRACT, response_review.CONTRACT}:
            raise ValueError("Current rendering requires an authority-bound current review")
        checked_authorities = response_authorities.validate(authority_evidence, context,
            research_record, sources, checked_draft)
        # v13: the review was told the sections code's checks held back; the release
        # record that names them is checked in full below.
        unwritten_ids = ([entry.get("dispute_id") for entry in held["unwritten"] if isinstance(entry, dict)]
                         if contract == CONTRACT and isinstance(held, dict)
                         and isinstance(held.get("unwritten"), list) else [])
        shortened = ([[entry.get("dispute_id"), entry.get("items")] for entry in held["trimmed"]
                      if isinstance(entry, dict)]
                     if contract == CONTRACT and isinstance(held, dict) and isinstance(held.get("trimmed"), list)
                     else [])
        checked_review = response_review.validate(review, context, research_record,
            sources, checked_draft, execution=execution, authority_evidence=checked_authorities,
            time_limits=calculation.for_answer(time_limits) if time_limits is not None else None,
            held_back=unwritten_ids or None, shortened=shortened or None)
    if contract == WORDS_CONTRACT and checked_draft["contract"] not in response_writer.WORDED:
        # Otherwise every source would be shown unlinked, with nothing to say so.
        raise ValueError("A v11 rendering links each source at the words its use names, "
                         "which only a writer v5 or v6 draft gives")
    if contract in _LISTED and checked_draft["contract"] not in response_writer.LINKED:
        raise ValueError("A v12 rendering lists the sources a paragraph does not link, as a writer v7 or later "
                         "draft leaves them")
    if held is not None and contract not in _HOLDS:
        raise ValueError("Only a v10 or later rendering may hold sections back")
    layout = response_writer.parts(research_record) if contract == CONTRACT else None
    held_parts, date_findings, unwritten, trimmed = _release(checked_draft, checked_review, held, layout)
    if not checked_review["accepted"] and not held_parts:
        raise ValueError("A response without accepted independent review cannot be rendered")
    authorities = ({row["unit_id"]: row for row in checked_authorities["units"]}
                   if contract in _CITED else {})
    headings = (_headings(research_record, checked_draft, also=[entry["dispute_id"] for entry in unwritten])
                if contract in (HEADINGS_CONTRACT, SHORT_NAME_CONTRACT, DOCUMENT_PAGES_CONTRACT, *_WORKING) else {})
    held_at, held_units, start = {}, set(), 0
    for index, part in enumerate(checked_draft.get("parts") or []):
        if index in held_parts:
            held_at[start] = index
            held_units.update(range(start, start + part["units"]))
        start += part["units"]
    names = _part_names(research_record, checked_draft) if held_parts else []
    findings = [] if checked_review["accepted"] else checked_review["proposal"]["findings"]
    # v13: each section code's checks held back goes where it stands in the answer's
    # layout, before the first section shown that follows it (or at the end).
    unwritten_at, disputes = {}, _dispute_names(research_record) if unwritten or trimmed else {}
    if unwritten:
        order = {part["dispute_id"]: index for index, part in enumerate(layout)}
        starts, start = [], 0
        for part in checked_draft["parts"]:
            starts.append((order[part["dispute_id"]], start))
            start += part["units"]
        for entry in unwritten:
            at = next((position for index, position in starts if index > order[entry["dispute_id"]]),
                      len(checked_draft["units"]))
            unwritten_at.setdefault(at, []).append(entry)

    def unwritten_notices(entries):
        out = []
        for entry in entries:
            name = OPENING if entry["dispute_id"] is None else disputes.get(entry["dispute_id"]) or "this dispute"
            if headings and entry["dispute_id"] is not None:
                out.append({"kind": "HEADING", "text": name, "source": None, "sources": [], "refs": [],
                            "inline_citations": [], "citation_markers": []})
            said = _CODE_FOUND[entry["found"]]
            out.append(_notice("HELD", f"Held back: {name}. After the rewrites NM may make, NM's own checks still "
                               f"found a problem in this section, so it is not shown. What the checks found: "
                               f"{said[0].upper()}{said[1:]}.",
                               held={"part": None, "section": name,
                                     "retry": f"Please try the held-back section on {name} again."}))
        return out

    elements = []
    held_count = len(held_parts) + len(unwritten)
    if held_count:
        many = held_count > 1
        found_by = ("the independent check still found" if not unwritten else "a check still found")
        elements.append(_notice("NOTICE", f"This answer is incomplete: {held_count} of its "
            f"{len(checked_draft['parts']) + len(unwritten)} sections {'are' if many else 'is'} held back below, "
            f"because {found_by} a problem in {'them' if many else 'it'} after the rewrites NM may "
            "make. The sections shown were checked by the independent review."))
    for entry in trimmed:
        # v13: what a section shown goes without (owner, 18 Oct 2026).
        name, said, many = disputes.get(entry["dispute_id"]) or "this dispute", _CODE_FOUND[entry["found"]],             entry["items"] > 1
        elements.append(_notice("NOTICE", f"Left out of the checklist for {name}: {entry['items']} "
            f"{'items' if many else 'item'}, because NM's own checks still found a problem in {'them' if many else 'it'} "
            f"after the rewrites NM may make: {said}. The rest of that section is shown, checked by the independent "
            "review."))
    def paragraph(position, unit):
        legal_sources = _sources(unit, sources, shown_names=contract in {SHOWN_NAME_CONTRACT, *_CITED},
                                 documents=contract in (DOCUMENT_PAGES_CONTRACT, *_WORKING))
        element = {"kind": unit["kind"].upper(), "text": unit["text"],
            "source": deepcopy(legal_sources[0]) if legal_sources else None,
            "sources": legal_sources,
            "refs": list(dict.fromkeys(source["locator"] for source in legal_sources))}
        if contract in _WORDED:
            element["inline_citations"], element["citation_markers"] = _worded(
                unit, legal_sources, listed=contract in _LISTED)
        elif contract in _CITED:
            element["inline_citations"], element["citation_markers"] = _cited_words(
                unit["text"], legal_sources, authorities[unit["id"]],
                short=contract in (SHORT_NAME_CONTRACT, DOCUMENT_PAGES_CONTRACT, *_WORKING))
        else:
            element["inline_citations"] = _anchors(unit["text"], legal_sources)
        if contract in _HOLDS:
            element["unit"] = position
        return element

    # v11: each dispute's summary, in order, under "In short": after the answer's opening
    # and before the first dispute's part. A reply with no dispute part keeps any summary
    # where it was written.
    lift_at, start = None, 0
    for part in checked_draft.get("parts") or []:
        if part["dispute_id"] is not None:
            lift_at = start
            break
        start += part["units"]
    lifted = [position for position, unit in enumerate(checked_draft["units"])
              if contract in _WORDED and lift_at is not None and unit["kind"] == "summary"
              and position not in held_units]
    for position, unit in enumerate(checked_draft["units"]):
        here = unwritten_at.get(position, [])
        # A held opening comes first; "In short" then opens the disputes.
        elements.extend(unwritten_notices([entry for entry in here if entry["dispute_id"] is None]))
        if position == lift_at:
            elements.extend(paragraph(lifted_at, checked_draft["units"][lifted_at]) for lifted_at in lifted)
        elements.extend(unwritten_notices([entry for entry in here if entry["dispute_id"] is not None]))
        if position in headings:
            elements.append({"kind": "HEADING", "text": headings[position], "source": None, "sources": [],
                             "refs": [], "inline_citations": [], "citation_markers": []})
        if position in held_at:
            elements.append(_held_notice(held_at[position], names[held_at[position]], checked_draft,
                                         findings, date_findings))
        if position in held_units or position in lifted:
            continue
        elements.append(paragraph(position, unit))
    elements.extend(unwritten_notices(unwritten_at.get(len(checked_draft["units"]), [])))
    if held_count:
        many = held_count > 1
        elements.append(_notice("NOTICE", f"Shall I try the held-back {'sections' if many else 'section'} again, "
            f"or continue without {'them' if many else 'it'}? If {'they' if many else 'it'} may need a fact, a "
            "document or a narrower question, tell me and I will use it."))
    if contract in _WORKING and time_limits is not None:
        # The Working boxes follow the answer's opening paragraph; from v11, "In short".
        summaries = [i for i, element in enumerate(elements) if element["kind"] == "SUMMARY"]
        first = summaries[-1] if contract in _WORDED and summaries else next(
            (i for i, element in enumerate(elements) if element["kind"] not in NOT_PARAGRAPHS), 0)
        elements[first + 1:first + 1] = _working(time_limits, as_of=contract in _AS_OF)
    return elements
