"""Add bare acts to the search: passages, vectors, BM25 and lineage. AN OFFLINE JOB.

    .venv-arrive\\Scripts\\python.exe pipeline\\append_bare_acts.py "<Act file>.txt" \\
        --jurisdiction "Union of India" --dry-run

LB-106 (owner, 29 September 2026): "adding more docs to the vector index as append and
rebuild BM25". Each Act file is in the library's raw form (as under
`legal_database/raw_data/BareActs/<jurisdiction>/`, named `<year>_<n>_<title>.txt`).
The job:

  1. finds the Act's sections (`parse_act`) and cuts them into passages the way the
     existing store holds them (`passages_for`) -- a section head carrying the whole
     section, then its sub-sections, clauses and provisos -- each headed
     "<Act>, -- s.<n>(<k>): <title>";
  2. refuses an Act already in the store;
  3. encodes the passages with the model the index was built with
     (BAAI/bge-large-en-v1.5, normalised) and writes a NEW vector index: the old one
     with the new vectors appended, so vector n stays passage n;
  4. rebuilds the BM25 index over every passage, old and new, with the same tokens and
     parameters, into a new folder;
  5. only then writes the new passages into the store at the next positions, in one
     transaction; swaps in the new index and BM25 folder, keeping the previous ones
     beside them as `.before-<time>`; and rewrites the lineage record the search checks
     at load.

RUN IT WITH --dry-run FIRST AND READ WHAT IT PRINTS: each Act's sections, and every
place its numbering was read as something other than sections -- a table, a schedule,
a list -- with the line. Nothing is written by a dry run.

Until step 5 completes nothing the search reads has changed. If it stops part-way,
the three members disagree and THE SEARCH REFUSES TO RUN rather than mapping a vector
onto the wrong passage -- the job prints what to restore. Stop the server before an
append -- it holds the index open, and Windows will not let an open file be replaced;
the job checks and refuses first -- and start it again after.

A new Act's sections become readable word for word only once the owner adds it to the
curated manifest (`pipeline/manifest.yaml`); the job prints the entry to review. Which
Acts the product covers is the owner's decision, never this job's.

Long, and it changes the library: the owner runs it; nothing in the repository does.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()
from nm.legal_brain.retrieve.hybrid_sections import (  # noqa: E402
    DOC_TYPE,
    EMBED_MODEL,
    bm25_tokens,
    check_lineage,
)

VECTOR_STORE = ROOT / "legal_database" / "vector_store"
LINEAGE = ROOT / ".nm" / "retrieval" / "bare_acts.lineage.json"
MODELS = ROOT / ".nm" / "models"
#: The BM25 parameters the existing index was built with (its params.index.json).
BM25_PARAMS = {"k1": 1.5, "b": 0.75, "delta": 0.5, "method": "robertson",
               "idf_method": "robertson"}

#: A section number: "22", "4A", "45-B" (read as 45B).
_NUMBER = r"(\d{1,4}(?:-?[A-Z]{1,3})?)"
#: A section as the library prints most of them: "22." on a line, its heading on the next.
_SECTION = re.compile(rf"^{_NUMBER}\.$")
#: ...its letter sometimes carried to the heading: "45." then "-B. Hearing of charge".
_LETTER_CARRIED = re.compile(r"^-\s?([A-Z]{1,3})\.\s*(.*)$")
#: ...and inserted ones: "22. Power of Registrar to call for information.- (1) The
#: Registrar may..." -- heading and text on one line, the heading ended by ".-";
_SECTION_INLINE = re.compile(rf"^{_NUMBER}\.\s+(.{{2,200}}?)(?:(\.)\s*|:\s*|\s)[-—–]+")
#: ...or the heading alone on the line, its text on the next ("2. Definitions." then
#: "In this Act..." -- the Indian Stamp Act, 1899 throughout).
_SECTION_HEADED = re.compile(rf"^{_NUMBER}\.\s+(\S.{{1,200}})$")
#: A table, "{|" or "[TABLE]" to "|}": its numbered rows are rows, never sections (the
#: table in section 320 of the Code of Criminal Procedure numbers its rows by the Penal
#: Code's sections).
_TABLE_OPEN = re.compile(r"^(?:\{\||\[TABLE\])")
_TABLE_CLOSE = "|}"
#: Schedules, forms, appendices, annexures -- a heading on its own line, where a run of
#: rows begins. ("[The Schedule]" in brackets is amended wording inside a section.)
_BACK_MATTER = re.compile(
    r"^(?:THE\s+)?(?:[A-Z]+\s+)?(?:SCHEDULE|FORM|APPENDIX|ANNEXURE)\b"
    r"|^(?:The\s+)?(?:[A-Z][a-z]+\s+)?(?:Schedule|Form|Appendix|Annexure)"
    r"(?:\s*[-–—.:]?\s*(?:No\.?\s*)?[A-Z0-9]+)?$")
#: Division markers: "(2)", "(b)", "(iv)" -- alone on a line, or opening it: "(2) On receipt".
_SUB = re.compile(r"^\((\d{1,3}[A-Z]?)\)(?:\s|$)")
_LETTERS = re.compile(r"^\(([a-z]{1,7})\)(?:\s|$)")
_NOTE = re.compile(r"^(Provided|Explanation|Illustration)\b")
_NOTE_KIND = {"Provided": "proviso", "Explanation": "explanation",
              "Illustration": "illustration"}
_NAME = re.compile(r"^(\d{4})_(\d+)_(.+)$")
_ONES = ("", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix")
#: Sub-clause numerals, (i) to (xxxix), in order.
_NUMERALS = ["x" * (n // 10) + _ONES[n % 10] for n in range(1, 40)]


@dataclass
class Section:
    number: str
    title: str
    lines: list[str] = field(default_factory=list)
    #: The lines that open it, as printed: ["22.", "<heading>"], or the one line.
    opening: list[str] = field(default_factory=list)
    #: Which of `lines` are the inside of a table: words of the division they sit in.
    tables: set[int] = field(default_factory=set)


@dataclass
class Act:
    act_id: str
    act_name: str
    title: str
    year: str
    sections: list[Section]
    #: Non-empty lines not appended: back matter, and numbering that never resumed.
    skipped: int = 0
    #: Where the text was read as something other than the Act's own sections, by line --
    #: for the owner to look at in a dry run before anything is appended.
    notes: list[str] = field(default_factory=list)


def parse_act(path: Path, jurisdiction: str) -> Act:
    """The Act's sections, from its raw text. Refuses a file it cannot place.

    A numbered line is only a CANDIDATE section. Tables, lists inside a section,
    annexures and schedules number their rows the same way -- "8." then "School
    certificate," is an item of rule 4 of the Central Motor Vehicles Rules, 1989, not its
    rule 8. The store's own chunker took every candidate for a section: its tables and
    schedules became sections, and 21,947 of its passage identifiers are used twice.
    Here:

      1. the rows of a "{|" ... "|}" table are never candidates;
      2. a RUN OF ROWS starts where the numbering restarts at 1 after the Act has begun,
         or at a heading such as "SCHEDULE", "FORM 3" or "Annexure II"; it goes on
         until the section after the one it interrupted (`_rows`) -- annexures printed
         inside rule 115 of those Rules are followed by rule 115B -- and its rows are
         not sections;
      3. the Act's sections are the LONGEST CHAIN of the remaining candidates whose
         numbers only go up, from section 1: a list's items that run ahead of the
         sections lose to the sections around them, which outnumber them;
      4. after the last section, the text from where a run begins is not appended.

    Every other numbered line stays as words of the section it sits in -- an inserted
    section printed out of its place among them -- and the notes say where, for the
    owner to read in a dry run before anything is appended."""
    match = _NAME.match(path.stem)
    if not match:
        raise ValueError(f"{path.name}: expected '<year>_<n>_<title>.txt'")
    year, number, title = match.group(1), match.group(2), match.group(3).strip()
    # The store's own casing, word by word, apostrophes included ("Women'S"): measured
    # to reproduce all 1,600 held names of this identifier form.
    act_name = f"{' '.join(jurisdiction.split())} {year} {number} {title}".title()
    act_id = f"{jurisdiction.upper()}_{year}_{number}_{title.upper()}"
    raw = path.read_text(encoding="utf8", errors="replace")
    lines = [line.strip() for line in raw.splitlines()]
    tables: set[int] = set()
    candidates: list[tuple[int, Section]] = []
    looks: list[bool] = []
    headings: set[int] = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if candidates and _BACK_MATTER.match(line):
            headings.add(len(candidates))
            candidates.append((i, Section("1", line, opening=[line])))
            looks.append(False)
            i += 1
            continue
        if candidates and _TABLE_OPEN.match(line):
            close = next((k for k in range(i + 1, len(lines)) if lines[k] == _TABLE_CLOSE),
                         None)
            if close is not None:
                tables.update(range(i, close + 1))
                i = close + 1
                continue
        opened = _opens_section(line, lines[i + 1] if i + 1 < len(lines) else "")
        if opened and (candidates or opened.number == "1"):
            j = i + len(opened.opening)
            while j < len(lines) and not lines[j]:
                j += 1
            after = lines[j] if j < len(lines) else ""
            # Printed as a section is: a heading ended ".-" on its line; or text opening
            # "(1)" or "-" after it; or, for "22." with its heading below, a heading ended
            # "." or ":" (a numbered sentence on one line ends so too).
            looks.append(bool(
                _SECTION_INLINE.match(line) or _TEXT_OPENS.match(after)
                or len(opened.opening) == 2
                and _HEADING_ENDS.search(opened.title.rstrip(" ]"))))
            candidates.append((i, opened))
            i += len(opened.opening)
            continue
        i += 1
    if not candidates:
        raise ValueError(f"{path.name}: no section 1 was found")
    numbers = [section.number for _, section in candidates]
    rows = _rows(numbers, looks, headings)
    chain = _chain(numbers, rows)
    notes: list[str] = []
    skipped, end, last = 0, len(lines), max(chain)
    trailing = next((k for k in range(last + 1, len(candidates)) if k in rows), None)
    if trailing is not None:
        cut = candidates[trailing][0]
        skipped, end = sum(1 for rest in lines[cut:] if rest), cut
        what = (repr(lines[cut][:40]) if trailing in headings
                else "a numbering restarting at 1")
        notes.append(f"line {cut + 1}: {what} after the last section ({numbers[last]}); "
                     f"{skipped} line(s) from there not appended")
    for k in sorted(headings):
        if candidates[k][0] < end:
            resumed = next((numbers[j] for j in range(k + 1, len(candidates)) if j in chain),
                           "?")
            notes.append(f"line {candidates[k][0] + 1}: {lines[candidates[k][0]][:40]!r} "
                         f"read as part of the section before it; the Act resumes at "
                         f"section {resumed}")
    words = [candidates[k][0] + 1 for k in range(len(candidates))
             if k not in chain and k not in headings and candidates[k][0] < end]
    if words:
        notes.append(f"{len(words)} numbered line(s) kept as words of the section they "
                     f"sit in, not as sections: line(s) "
                     + ", ".join(map(str, words[:12])) + (" ..." if len(words) > 12 else ""))
    opens = {candidates[k][0]: candidates[k][1] for k in chain}
    sections: list[Section] = []
    i = candidates[min(chain)][0]
    while i < end:
        if i in opens:
            sections.append(opens[i])
            i += len(opens[i].opening)
            continue
        if lines[i]:
            if i in tables:
                sections[-1].tables.add(len(sections[-1].lines))
            sections[-1].lines.append(lines[i])
        i += 1
    return Act(act_id, act_name, title, year, sections, skipped, notes)


#: How far a table's rows step, and how far past the section a run of rows interrupted
#: the next section may be numbered (sections omitted by repeal leave small gaps).
_GAP = 5


def _order(number: str) -> tuple[int, str]:
    digits = re.match(r"\d+", number).group()
    return int(digits), number[len(digits):]


def _resumes(interrupted: str, number: str) -> bool:
    """Whether `number` can be the section after section `interrupted`: its next
    lettered insertion (10TE after 10TD), or a number a little past it."""
    (base, letters), (after, suffix) = _order(interrupted), _order(number)
    return (after == base and suffix > letters) or base < after <= base + _GAP


def _rows(numbers: list[str], looks: list[bool], headings: set[int]) -> set[int]:
    """Which candidates are rows. A run starts at a number 1 after the Act has begun,
    or at a back-matter heading (the candidates in `headings`), and every candidate
    after it is a row, whatever its number, until the section after the one it
    interrupted: one that is not merely the next row, or is printed as sections are
    (`looks`: a heading ending ".", ".-" or ":", or text opening "(1)" or "-" --
    measured over the library's two-line candidates, 86% of those on the chain end
    their heading so, and 14% of rows). After a heading, being printed as a section is
    not enough: the First Schedule of the Code of Criminal Procedure numbers its rows by
    the Penal Code's sections, past the Code's own last section, and prints them alike.
    A run that is never followed by its section runs to the end."""
    rows: set[int] = set()
    interrupted = numbers[0]
    strict = False
    k = 1
    while k < len(numbers):
        if numbers[k] != "1":
            # The section a run would interrupt: the Act's furthest, reached a step at a
            # time -- a stray "3." inside rule 115B is not where the Rules have got to.
            n = numbers[k]
            if _order(n) > _order(interrupted) and (
                    _resumes(interrupted, n)
                    or k + 1 < len(numbers) and _resumes(n, numbers[k + 1])):
                interrupted = n
            strict = False
            k += 1
            continue
        strict = strict or k in headings
        rows.add(k)
        previous = numbers[k]
        k += 1
        while k < len(numbers) and numbers[k] != "1":
            n = numbers[k]
            (was, was_letters), (now, letters) = _order(previous), _order(n)
            next_row = now == was + 1 or (now == was and letters > was_letters)
            if _resumes(interrupted, n) and (not next_row or looks[k] and not strict):
                break
            rows.add(k)
            previous = n
            k += 1
    return rows


def _chain(numbers: list[str], rows: set[int]) -> set[int]:
    """The longest chain of candidates, in the order printed, whose numbers only go up
    (10TE after 10TD is up). It starts at the Act's section 1, the first candidate and
    the lowest number. A number equal to one already ending a chain is not taken, so a
    section printed again later is the later copy's words."""
    from bisect import bisect_left

    tails: list[tuple[int, str]] = []
    tail_at: list[int] = []
    back: dict[int, int] = {}
    for k, n in enumerate(numbers):
        if k in rows:
            continue
        key = _order(n)
        pos = bisect_left(tails, key)
        if pos < len(tails) and tails[pos] == key:
            continue
        if pos:
            back[k] = tail_at[pos - 1]
        if pos == len(tails):
            tails.append(key)
            tail_at.append(k)
        else:
            tails[pos], tail_at[pos] = key, k
    k = tail_at[-1]
    chain = {k}
    while k in back:
        k = back[k]
        chain.add(k)
    return chain


#: A heading as sections end theirs, and text as sections open theirs.
_HEADING_ENDS = re.compile(r"(?:[.:]\s*[-—–]?|[-—–])$")
_TEXT_OPENS = re.compile(r"^(?:[-—–]|\(1\))")
#: A numbered line, as an arrangement of sections lists them or a section opens.
_LISTED = re.compile(rf"^{_NUMBER}\.(?:\s|$)")


def _opens_section(line: str, following: str) -> Section | None:
    """The section `line` opens, printed in any of the library's three ways, if it
    opens one; whether its number may open one is `parse_act`'s question."""
    marker, inline, headed = (_SECTION.match(line), _SECTION_INLINE.match(line),
                              _SECTION_HEADED.match(line))
    # A heading alone on its line needs its text after it: a line of the arrangement of
    # sections that big Codes print first is followed by the next line of it.
    if headed and (not following or _LISTED.match(following) or not (
            _TEXT_OPENS.match(following) or _HEADING_ENDS.search(headed.group(2).rstrip(" ]")))):
        headed = None
    if marker and following:
        number, heading, opening = marker.group(1), following, [line, following]
        carried = _LETTER_CARRIED.match(following)
        if carried:
            number, heading = number + carried.group(1), carried.group(2) or following
    elif inline:
        number, opening = inline.group(1), [line]
        heading = inline.group(2).strip() + (inline.group(3) or "")
    elif headed:
        number, heading, opening = headed.group(1), headed.group(2), [line]
    else:
        return None
    return Section(number.replace("-", ""), heading, opening=opening)


@dataclass(frozen=True)
class _Open:
    """A division of a section that later lines may belong to."""
    label: str
    id: str
    chain: tuple[str, ...]


def _row(act: Act, section: Section, atom: str, text: str, *, chunk_id: str,
         owner: _Open | None, chain: tuple[str, ...], sub: _Open | None = None,
         clause: _Open | None = None, roman: _Open | None = None) -> dict:
    """One passage, in the shape the store's rows of this identifier form already have
    (measured over 339,266 of them): the same fields in the same order, `year` and
    `chapter` empty, a section head's parent empty in the record and absent in the
    column, and a header citing the division, e.g. "s.29A(d)(ii) [proviso]"."""
    cite = f"s.{section.number}" + "".join(f"({o.label})" for o in (sub, clause, roman) if o)
    if atom in _NOTE_KIND.values():
        cite += f" [{atom}]"
    full = f"{act.act_name},  — {cite}: {section.title}\n{text}".strip()
    return {"atom_type": atom, "chunk_id": chunk_id,
            "parent_chunk_id": owner.id if owner else None,
            "section_number": section.number, "blob": {
                "chunk_id": chunk_id, "doc_type": DOC_TYPE, "act_id": act.act_id,
                "act_name": act.act_name, "year": "", "chapter": "",
                "section_number": section.number, "section_title": section.title,
                "sub_section": f"({sub.label})" if sub else "",
                "clause": f"({clause.label})" if clause else "",
                "sub_clause": f"({roman.label})" if roman else "",
                "atom_type": atom, "parent_chunk_id": owner.id if owner else "",
                "parent_chain": list(chain), "full_text": full, "keywords": []}}


def _is_numeral(label: str, clause: _Open | None, next_label: str) -> bool:
    """Whether "(label)" numbers a sub-clause rather than a lettered clause.

    Statutes number sub-clauses (i), (ii), (iii)... and letter clauses (a), (b)...
    -- and (i), (v), (x), (ii), (vv), (xx) are both. One of those is the NEXT LETTER
    when it follows the clause lettered just before it ((h) -> (i), (hh) -> (ii),
    (u) -> (v)) and what comes after it is not its numeral successor ((i) then (j) is a
    letter; (i) then (ii) is a numeral). The store's own chunker read every (i) after
    (h) as a sub-clause of (h), citing a definitions clause as "(h)(i)"."""
    if label not in _NUMERALS:
        return False
    if clause is None or len(set(label)) != 1 or len(label) > 2:
        return True
    before = chr(ord(label[0]) - 1) * len(label)
    lettered_next = clause.label == before or (
        len(label) == 1 and clause.label[:1] == before and len(clause.label) == 2
        and clause.label[0] != clause.label[1])
    successor = _NUMERALS[_NUMERALS.index(label) + 1]
    return not (lettered_next and next_label != successor)


def passages_for(act: Act) -> list[dict]:
    """The passages the store holds for an Act, cut the way it already cut them: a
    section head carrying the whole section, then its sub-sections, lettered clauses,
    numeral sub-clauses, provisos, explanations and illustrations, each carrying ONLY
    its own words (the words of its children are theirs), each headed with its citation.

    The store's rules, measured on its rows and kept: a numeral item belongs to the
    innermost open clause, else sub-section, else the section; a proviso, explanation or
    illustration belongs to the innermost open division of any kind and is numbered
    through the section ("_PROVISO_3" is the section's third proviso). Where the store's
    chunker was wrong it is not copied: see `_is_numeral`, and `parse_act`, which reads
    the tables, lists and schedules the store cut as sections as rows."""
    rows = []
    for section in act.sections:
        n = section.number
        head = _Open(n, f"{act.act_id}_SECTION_{n}", (f"section_{n}",))
        rows.append(_row(act, section, "section_head",
                         "\n".join([*section.opening, *section.lines]),
                         chunk_id=head.id, owner=None, chain=head.chain))
        labels = [None if k in section.tables else (_SUB.match(line) or _LETTERS.match(line))
                  for k, line in enumerate(section.lines)]
        following, later = [""] * len(labels), ""
        for k in range(len(labels) - 1, -1, -1):
            following[k] = later
            if labels[k]:
                later = labels[k].group(1)
        sub = clause = roman = None
        counts: dict[str, int] = {}
        current: dict | None = None
        for k, line in enumerate(section.lines):
            number, letters = _SUB.match(line), _LETTERS.match(line)
            note = _NOTE.match(line)
            if k in section.tables:
                if current is not None:
                    current["blob"]["full_text"] += f"\n{line}"
                continue
            if number:
                label = number.group(1)
                sub = _Open(label, f"{head.id}_SUB_{label}", (*head.chain, f"sub_section_{label}"))
                clause = roman = None
                current = _row(act, section, "sub_section", line, chunk_id=sub.id,
                               owner=head, chain=sub.chain, sub=sub)
            elif letters and _is_numeral(letters.group(1), clause, following[k]):
                label, owner = letters.group(1), clause or sub or head
                roman = _Open(label, f"{owner.id}_SUBCLAUSE_{label}",
                              (*owner.chain, f"sub_clause_{label}"))
                current = _row(act, section, "sub_clause", line, chunk_id=roman.id,
                               owner=owner, chain=roman.chain, sub=sub, clause=clause,
                               roman=roman)
            elif letters and len(letters.group(1)) <= 2:
                label, owner = letters.group(1), sub or head
                clause = _Open(label, f"{owner.id}_CLAUSE_{label}",
                               (*owner.chain, f"clause_{label}"))
                roman = None
                current = _row(act, section, "clause", line, chunk_id=clause.id,
                               owner=owner, chain=clause.chain, sub=sub, clause=clause)
            elif note:
                kind, owner = _NOTE_KIND[note.group(1)], roman or clause or sub or head
                count = counts[kind] = counts.get(kind, 0) + 1
                current = _row(act, section, kind, line,
                               chunk_id=f"{owner.id}_{kind.upper()}_{count}", owner=owner,
                               chain=(*owner.chain, f"{kind}_{count}"), sub=sub,
                               clause=clause, roman=roman)
            elif current is not None:
                current["blob"]["full_text"] += f"\n{line}"
                continue
            else:
                continue
            rows.append(current)
    return rows


@dataclass
class Store:
    vector_store: Path
    lineage: Path


def append(rows: list[dict], store: Store, *, encode: Callable[[list[str]], "object"],
           build_bm25: Callable[[list[list[str]], Path], int], dry_run: bool = False) -> dict:
    """Append `rows` to the index, the BM25 index and the passage store, in the order that
    leaves the search refusing -- never mis-mapping -- if it stops part-way."""
    import faiss
    import numpy as np

    if not rows:
        raise RuntimeError("no passages to append")
    identifiers = [r["chunk_id"] for r in rows]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("the new passages repeat a chunk identifier; nothing appended")
    record = json.loads(store.lineage.read_text(encoding="utf8"))
    problems = check_lineage(record, store.vector_store)
    if problems:
        raise RuntimeError("the current set is not consistent; nothing appended: "
                           + "; ".join(problems))
    base = int(record["passages"])
    db = store.vector_store / record["passage_store"]["path"]
    index_path = store.vector_store / record["vector_index"]["path"]
    bm25_dir = store.vector_store / record["bm25"]["path"]
    new_index = index_path.with_name(index_path.name + ".new")
    new_bm25 = bm25_dir.with_name(bm25_dir.name + ".new")
    if not dry_run:
        _can_swap(index_path, bm25_dir)
    con = sqlite3.connect(db)
    try:
        acts = {r["blob"]["act_id"] for r in rows}
        held = [a for a in acts if con.execute(
            "select 1 from chunks where doc_type=? and act_id=? limit 1",
            (DOC_TYPE, a)).fetchone()]
        if held:
            raise RuntimeError("already in the store, nothing appended: "
                               + ", ".join(sorted(held)))
        texts = [r["blob"]["full_text"] for r in rows]
        vectors = np.asarray(encode(texts), dtype="float32")
        index = faiss.read_index(str(index_path))
        if index.ntotal != base or vectors.shape != (len(rows), index.d):
            raise RuntimeError("the new vectors do not fit the index; nothing appended")
        index.add(vectors)
        summary = {"appended": len(rows), "passages": base + len(rows), "acts": sorted(acts)}
        if dry_run:
            return {**summary, "dry_run": True}
        try:
            faiss.write_index(index, str(new_index))
            old_texts = [json.loads(b).get("full_text", "") for (b,) in con.execute(
                "select blob from chunks where doc_type=? order by pos", (DOC_TYPE,))]
            if new_bm25.exists():
                shutil.rmtree(new_bm25)
            docs = build_bm25([bm25_tokens(t) for t in old_texts + texts], new_bm25)
            if docs != base + len(rows):
                raise RuntimeError("the rebuilt BM25 index does not hold every passage; "
                                   "nothing appended")
            # THE PASSAGES, AT THE NEXT POSITIONS, IN ONE TRANSACTION. A failed
            # insert rolls back the store and removes both staged indexes.
            with con:
                for offset, r in enumerate(rows):
                    con.execute(
                        "insert into chunks (doc_type, pos, chunk_id, act_id, case_id, "
                        "parent_chunk_id, atom_type, section_number, blob) "
                        "values (?,?,?,?,?,?,?,?,?)",
                        (DOC_TYPE, base + offset, r["chunk_id"], r["blob"]["act_id"], None,
                         r["parent_chunk_id"], r["atom_type"], r["section_number"],
                         json.dumps(r["blob"], ensure_ascii=False)))
        except BaseException:
            new_index.unlink(missing_ok=True)
            shutil.rmtree(new_bm25, ignore_errors=True)
            raise
    finally:
        con.close()
    # THE SWAP. The previous members are kept beside the new ones, under a name of their
    # own: the library already holds older `.bak` files that are not this job's.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    try:
        os.replace(index_path, index_path.with_name(f"{index_path.name}.before-{stamp}"))
        os.replace(new_index, index_path)
        os.replace(bm25_dir, bm25_dir.with_name(f"{bm25_dir.name}.before-{stamp}"))
        os.replace(new_bm25, bm25_dir)
    except OSError as exc:
        raise RuntimeError(
            f"the passages were written but the swap failed ({exc}); the search refuses the "
            f"set until it agrees. To undo: delete bare_act rows with pos >= {base} from "
            f"{db.name} and restore the '.before-{stamp}' index and BM25 folder.") from exc
    record = {**record, "passages": base + len(rows),
              "vector_index": {**record["vector_index"], "vectors": base + len(rows),
                               "bytes": index_path.stat().st_size, "sha256": _sha256(index_path)},
              "bm25": {**record["bm25"], "num_docs": base + len(rows),
                       "params_sha256": _sha256(bm25_dir / "params.index.json")},
              "passage_store": {**record["passage_store"], "count": base + len(rows),
                                "max_pos": base + len(rows) - 1},
              "appended": [*record.get("appended", ()), {
                  "acts": sorted(acts), "passages": len(rows),
                  "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]}
    problems = check_lineage(record, store.vector_store)
    if problems:
        raise RuntimeError("appended, but the set does not agree -- the search will refuse it: "
                           + "; ".join(problems))
    store.lineage.write_text(json.dumps(record, indent=2), encoding="utf8")
    return summary


def _can_swap(*members: Path) -> None:
    """Refuse, before anything is written, when a member cannot be replaced -- on Windows
    a running server holding the index open. Each is renamed aside and straight back."""
    for member in members:
        aside = member.with_name(member.name + ".swap-check")
        try:
            os.replace(member, aside)
        except OSError as exc:
            raise RuntimeError(f"{member.name} cannot be replaced ({exc}) -- stop the server "
                               f"first; nothing appended") from exc
        os.replace(aside, member)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _real_encoder():
    os.environ.pop("SSLKEYLOGFILE", None)
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(str(MODELS / EMBED_MODEL.replace("/", "__")), device=device,
                                local_files_only=True)
    return lambda texts: model.encode(texts, normalize_embeddings=True, batch_size=32,
                                      convert_to_numpy=True, show_progress_bar=True)


def _real_bm25(tokens: list[list[str]], folder: Path) -> int:
    import bm25s

    retriever = bm25s.BM25(**BM25_PARAMS)
    retriever.index(tokens, show_progress=True)
    retriever.save(str(folder))
    return int(json.loads((folder / "params.index.json").read_text(encoding="utf8"))["num_docs"])


def _ranges(numbers: list[str]) -> str:
    """Section numbers as the owner checks them against an arrangement: "1-14, 20-75,
    75A, 76-88"."""
    out: list[str] = []
    start = previous = None
    for n in [*numbers, None]:
        if (n is not None and n.isdigit() and previous is not None and previous.isdigit()
                and int(n) == int(previous) + 1):
            previous = n
            continue
        if start is not None:
            out.append(start if start == previous else f"{start}-{previous}")
        start = previous = n
    return ", ".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--jurisdiction", required=True,
                    help="as the library's folders name it, e.g. 'Union of India' or 'Telangana'")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse, encode and check; change nothing")
    args = ap.parse_args(argv)
    rows, seen = [], set()
    for path in args.files:
        act = parse_act(path, args.jurisdiction)
        if act.act_id in seen:
            raise SystemExit(f"{path.name}: {act.act_id} was given twice; nothing appended")
        seen.add(act.act_id)
        cut = passages_for(act)
        print(f"\n{act.act_name}: {len(act.sections)} sections, {len(cut)} passages"
              + (f"; {act.skipped} line(s) not appended" if act.skipped else ""))
        print("  sections: " + _ranges([s.number for s in act.sections]))
        for note in act.notes:
            print(f"  NOTE {note}")
        rows += cut
    summary = append(rows, Store(VECTOR_STORE, LINEAGE), encode=_real_encoder(),
                     build_bm25=_real_bm25, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    if not args.dry_run:
        print("Start the server again to search the new passages. To read their sections "
              "word for word, review and add a manifest entry, e.g. act_patterns: "
              + ", ".join(repr(a) for a in summary["acts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
