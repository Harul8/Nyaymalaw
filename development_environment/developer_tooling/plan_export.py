"""Plan AN.54, D231 stage 1 (17 Nov 2026): the Advocate build plan written out as text, checked against the sheet, for the owner to
see before anything about the way of working changes. READ-ONLY on the workbook; it writes only into the folder it is given.

  <venv python> development_environment/developer_tooling/plan_export.py [--out docs/proposed/D231] [--running COMMIT]

What it writes:
  rows/<ID>.md         every row of the sheet, every non-empty cell under its column's name: nothing of the sheet is left out.
  decisions/<ID>.md    each decision record in a file of its own: the owner's words (O rows), the product decisions (P rows) and the
                       decision register (Q rows) whole; and each D-numbered record, cut from the rows where it is written - a record
                       runs from the line or sentence that opens with its number to the next that opens with a number. A record that
                       opens with several numbers ("D229, D231, D232 ...") is filed under each of them.
  PIECES.md            one line a piece (the AN and SEQ rows): its status proposed from a closed list by the rule written at its
                       top, the status words the row uses in order, the decisions it holds, and a link to the row. With
                       --running (the commit the running server was started on), a row with commits - those it cites, and those
                       whose message names the row, leaving out commits that change only the plan workbook - is classed by
                       whether those commits are in the running code, a fact git answers, rather than by the row's words.
  CHECK.md             the checks made against the sheet, and what they found.

Until the owner accepts stage 2, the sheet stays the one work queue (P7) and these files are a view of it, made again from it.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOK = ROOT / "docs" / "Nyaymalaw_Implementation_Plan.xlsx"
SHEET = "Advocate build plan"
HEADERS = {1: "ID", 2: "Item", 3: "Description", 4: "Governs or depends on", 5: "Status", 6: "Notes"}
WHOLE = re.compile(r"^(O|P|Q)\d+$")
PIECE = re.compile(r"^(AN|SEQ)\.\d+$")
#: A record opens where a line, or a sentence, starts with a decision's number: "D12 (", "D229, D231", "D254. THE ...", "D3-D8".
OPENS = re.compile(r"(?:(?<=\n)|^|(?<=\. ))(D\d{1,3}(?:\s*(?:,|and|-|–|to)\s*D\d{1,3})*)(?=[ .(:,;'’])")
NUMBER = re.compile(r"D(\d{1,3})")
#: The closed list of a piece's status, and the rule that proposes one from the status cell (column 5). The rule reads the words the
#: plan writes in capitals; it cannot tell a piece built in whole from one built in part, which the owner's reading settles.
CLOSED = ("Applied", "Partly applied", "Built, not applied", "Built, where it runs not recorded", "Agreed, not built",
          "Done without a build", "For the owner", "Not classified")
HEX = re.compile(r"(?<![\w/])([0-9a-f]{7,40})(?![\w/])")
WORDS = re.compile(r"(?<![A-Z])(NOT APPLIED|NOT BUILT|APPLIED|BUILT|AGREED|PLANNED|DECIDED|PROPOSED|DONE|CHECKED|ANALYSED|MEASURED|"
                   r"SUPERSEDED|FOR THE OWNER)(?![A-Z])")


def cell_text(value) -> str:
    return "" if value is None else str(value)


def load():
    import openpyxl
    ws = openpyxl.load_workbook(BOOK, read_only=True, data_only=True)[SHEET]
    rows = []
    for number, values in enumerate(ws.iter_rows(values_only=True), 1):
        cells = {column: cell_text(value) for column, value in enumerate(values, 1) if cell_text(value).strip()}
        if cells:
            rows.append((number, cells))
    return rows


def row_name(number, cells):
    ident = cells.get(1, "").strip()
    return re.sub(r"[^\w.-]+", "_", ident) if ident else f"row-{number:03d}"


def column_name(column):
    return HEADERS.get(column, f"Column {column}")


def numbers(opening):
    found = []
    for part in re.split(r"\s*(?:,|and)\s*", opening):
        ends = [int(n) for n in NUMBER.findall(part)]
        if len(ends) == 2 and re.search(r"-|–|to", part):
            found.extend(range(ends[0], ends[1] + 1))
        else:
            found.extend(ends)
    return [f"D{n}" for n in found]


def records(text):
    """The cell cut at each opening: (preamble, [(opening, segment)]). Joined back in order, the pieces are the cell exactly."""
    marks = [m for m in OPENS.finditer(text)]
    if not marks:
        return text, []
    preamble, cut = text[:marks[0].start()], []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        cut.append((mark.group(1), text[mark.start():end]))
    return preamble, cut


def known_commits(running):
    """(every commit the repository knows, those the running code holds, {row ID: the commits whose message names it}), as full
    hashes; a commit that changes only the plan workbook is a record, not a build, and names no row here. Empty without --running."""
    if not running:
        return set(), set(), {}

    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True, encoding="utf8").stdout
    by_row = {}
    for block in git("log", "--all", "--format=%x00%H%x01%B%x01", "--name-only").split("\0")[1:]:
        full, message, files = block.split("\x01", 2)
        if {name for name in files.split() if name} <= {"docs/Nyaymalaw_Implementation_Plan.xlsx"}:
            continue
        for row in set(re.findall(r"\b((?:AN|SEQ)\.\d+)\b", message)):
            by_row.setdefault(row, set()).add(full)
    return set(git("rev-list", "--all").split()), set(git("rev-list", running).split()), by_row


def cited(cells, every):
    """The commits a row names anywhere, resolved against the repository by their prefix."""
    by_start = {}
    for full in every:
        by_start.setdefault(full[:7], []).append(full)
    found = set()
    for text in cells.values():
        for token in HEX.findall(text):
            if not (re.search(r"\d", token) and re.search(r"[a-f]", token)):
                continue
            matches = [full for full in by_start.get(token[:7], []) if full.startswith(token)]
            if len(matches) == 1:
                found.add(matches[0])
    return found


def status_of(cells, every=frozenset(), running=frozenset(), messages=frozenset()):
    status = cells.get(5, "")
    said = [m.group(1) for m in WORDS.finditer(status)]
    seen = set(said)
    named = (cited(cells, every) if every else set()) | set(messages)
    if named:
        held = len(named & running)
        how = f"commits: {held} of {len(named)} in the running code"
        proposed = "Applied" if held == len(named) else "Partly applied" if held else "Built, not applied"
        return proposed, said_in_order(said), how
    how = "words"
    if "APPLIED" in seen:
        proposed = "Applied"
    elif "BUILT" in seen:
        proposed = "Built, where it runs not recorded"
    elif "FOR THE OWNER" in seen and not seen & {"AGREED", "DECIDED", "DONE"}:
        proposed = "For the owner"
    elif seen & {"AGREED", "PLANNED", "DECIDED"}:
        proposed = "Agreed, not built"
    elif seen & {"DONE", "ANALYSED", "CHECKED", "MEASURED"}:
        proposed = "Done without a build"
    else:
        proposed = "Not classified"
    return proposed, said_in_order(said), how


def said_in_order(said):
    order = []
    for word in said:
        if not order or order[-1] != word:
            order.append(word)
    return order


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/proposed/D231")
    parser.add_argument("--running", help="the commit the running server was started on")
    args = parser.parse_args()
    out = ROOT / args.out
    every, running, by_row = known_commits(args.running)
    if out.exists():
        shutil.rmtree(out)
    (out / "rows").mkdir(parents=True)
    (out / "decisions").mkdir()
    rows = load()
    names, decisions, pieces, problems, cut_cells = {}, {}, [], [], 0
    for number, cells in rows:
        name = row_name(number, cells)
        if name in names.values():
            problems.append(f"two rows carry the ID {name}; the second is written as {name}-row-{number}")
            name = f"{name}-row-{number}"
        names[number] = name
        title = cells.get(2, "").strip().splitlines()[0] if cells.get(2) else ""
        body = [f"# {cells.get(1, '').strip() or f'Row {number}'}{' - ' + title if title else ''}", "",
                f"Row {number} of the '{SHEET}' sheet, written out by plan_export.py. The sheet is the record (P7).", ""]
        for column, text in sorted(cells.items()):
            body += [f"## {column_name(column)}", "", text, ""]
        (out / "rows" / f"{name}.md").write_text("\n".join(body), encoding="utf8")
        if WHOLE.match(name):
            decisions.setdefault(name, []).append((name, "the whole row", "\n\n".join(
                f"{column_name(column)}:\n{text}" for column, text in sorted(cells.items()) if column > 1)))
        if name.startswith("AN."):
            for column, text in sorted(cells.items()):
                if column < 3:
                    continue
                preamble, cut = records(text)
                if cut:
                    cut_cells += 1
                if preamble + "".join(segment for _, segment in cut) != text:
                    problems.append(f"{name} {column_name(column)}: the records cut from it do not join back into the cell")
                for opening, segment in cut:
                    for decision in numbers(opening):
                        decisions.setdefault(decision, []).append((name, column_name(column), segment.strip()))
        if PIECE.match(name):
            proposed, order, how = status_of(cells, every, running, by_row.get(name, ()))
            held = sorted({d for _, cut in [records(cells.get(3, ""))] for opening, _ in cut for d in numbers(opening)},
                          key=lambda d: int(d[1:]))
            pieces.append((name, title, proposed, order, held, how))
    # Each decision record in a file of its own.
    for decision, parts in decisions.items():
        lines = [f"# {decision}", "", "Written out from the Advocate build plan by plan_export.py; the sheet is the record (P7).", ""]
        for row, where, text in parts:
            lines += [f"## From [{row}](../rows/{row}.md), {where}", "", text, ""]
        (out / "decisions" / f"{decision}.md").write_text("\n".join(lines), encoding="utf8")
    # The index of the pieces.
    rule = ((f"A row with commits - those it cites, and those whose message names it, leaving out commits that change only the "
             f"plan workbook - is classed by git: all of them in the code the running server was started on ({args.running}) -> "
             f"Applied; some -> Partly applied; none -> Built, not applied. " if args.running else "")
            + "Otherwise the status is proposed by a rule from the words the plan writes in capitals in the row's Status: APPLIED anywhere -> "
            "Applied; else BUILT -> Built, where it runs not recorded; else FOR THE OWNER alone -> For the owner; else AGREED, PLANNED or DECIDED "
            "-> Agreed, not built; else DONE, ANALYSED, CHECKED or MEASURED -> Done without a build; else Not classified. The rule "
            "cannot tell a piece applied or built in whole from one in part, nor see a later piece left open: the words column shows "
            "what the row says, in order, and the row itself is the record.")
    index = ["# The pieces of the Advocate build plan", "",
             "D231 stage 1 (17 Nov 2026): one line a piece, made from the sheet by plan_export.py. Proposed for the owner to accept, "
             "change or refuse; until then the sheet stays the one work queue (P7).", "", f"Closed list: {'; '.join(CLOSED)}.", "",
             rule, "", "| Piece | What | Status (proposed) | How | Status words, in order | Decisions | Row |",
             "|---|---|---|---|---|---|---|"]
    for name, title, proposed, order, held, how in pieces:
        span = (f"{held[0]}-{held[-1]} ({len(held)})" if len(held) > 2 else ", ".join(held)) if held else ""
        safe = title.replace("|", "/")
        index.append(f"| {name} | {safe} | {proposed} | {how} | {' -> '.join(order)} | {span} | [{name}](rows/{name}.md) |")
    counts = {status: sum(1 for p in pieces if p[2] == status) for status in CLOSED}
    index += ["", "Counts: " + "; ".join(f"{status} {count}" for status, count in counts.items() if count) + "."]
    (out / "PIECES.md").write_text("\n".join(index) + "\n", encoding="utf8")
    # The checks against the sheet.
    filed = sorted((d for d in decisions if d.startswith("D")), key=lambda d: int(d[1:]))
    named = sorted({f"D{n}" for _, cells in rows if row_name(_, cells).startswith("AN.") for text in cells.values()
                    for n in NUMBER.findall(text) if 0 < int(n) < 1000}, key=lambda d: int(d[1:]))
    top = max(int(d[1:]) for d in named)
    unfiled = [f"D{n}" for n in range(1, top + 1) if f"D{n}" not in decisions]
    cells_seen = sum(len(cells) for _, cells in rows)
    written = sum(len(list((out / "rows").glob("*.md"))) for _ in [0])
    lost = []
    for number, cells in rows:
        text = (out / "rows" / f"{names[number]}.md").read_text(encoding="utf8")
        lost += [f"{names[number]} {column_name(column)}" for column, value in cells.items() if value not in text]
    check = ["# Checked against the sheet", "", f"Made from {BOOK.name}, sheet '{SHEET}'.", "",
             f"- Rows with content: {len(rows)}; row files written: {written}; cells: {cells_seen}; cells not found whole in "
             f"their row's file: {len(lost)}{' - ' + ', '.join(lost[:20]) if lost else ''}.",
             f"- Cells of the AN rows cut into decision records: {cut_cells}; every one joins back into its cell exactly: "
             f"{'yes' if not any('join back' in p for p in problems) else 'NO'}.",
             f"- Decision files: {len(decisions)} - {len(filed)} D-numbered, "
             f"{sum(1 for d in decisions if d[0] in 'OPQ')} whole rows (O, P, Q).",
             f"- D-numbers the AN rows name: D1-D{top}; with no record of their own (named only inside another's): "
             f"{', '.join(unfiled) if unfiled else 'none'}.",
             "- Rows D1-D15 of the scenario list (the 'D' scenarios) are rows, not decisions: they are in rows/, and the decision "
             "files D1-D15 hold only the AN.28-AN.31 records of those numbers.",
             f"- Other notes: {'; '.join(problems) if problems else 'none'}.", "",
             "What the check cannot show: whether a record's words are right, or whether a status proposed by the rule is the "
             "piece's true state - that is read from the row."]
    (out / "CHECK.md").write_text("\n".join(check) + "\n", encoding="utf8")
    print("\n".join(check[4:10]))
    print(f"pieces: {len(pieces)}; " + "; ".join(f"{status} {count}" for status, count in counts.items() if count))
    return 1 if lost or any("join back" in p for p in problems) else 0


if __name__ == "__main__":
    sys.exit(main())
