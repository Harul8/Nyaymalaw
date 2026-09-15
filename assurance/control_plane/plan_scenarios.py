"""The Given/When/Then scenarios live in the implementation plan sheet.

    python assurance/control_plane/plan_scenarios.py --check   # exit 1 if a file differs
    python assurance/control_plane/plan_scenarios.py --write   # regenerate the files

WHY THE SHEET AND NOT THE FILES
---------------------------------
The product owner reads and decides from one place: `docs/Nyaymalaw_Implementation_Plan
.xlsx`. Each feature row's Must do and Must never are written, in the column
"Scenarios (Given / When / Then)", as the scenarios that test it. pytest-bdd can only
read `.feature` files, so those files under `tests/features/` are GENERATED from that
column and carry a header saying so. Nobody edits them; nobody needs to open them.

ONE OWNER, AND A CHECK THAT REFUSES THE SECOND. A generated file that someone edits by
hand would quietly test something the sheet does not say.
`tests/test_the_scenarios_come_from_the_plan.py` fails the build when any file differs
from the sheet, when a file has no row, and when a row has no file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "docs" / "Nyaymalaw_Implementation_Plan.xlsx"
FEATURES = ROOT / "tests" / "features"
COLUMN = "Scenarios (Given / When / Then)"

#: The directory each journey phase's feature files are written to.
PHASE_DIRECTORIES = {
    "A": "arrive", "B": "open_a_matter", "C": "take_the_brief", "D": "work_the_file",
    "E": "advise", "F": "act", "G": "carry", "H": "close", "I": "leave",
}


def header(row_id: str) -> str:
    return (f"# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row {row_id}, "
            f'column "{COLUMN}".\n# Edit the sheet, then run '
            f"`python assurance/control_plane/plan_scenarios.py --write`.\n")


def sheet_rows(sheet: Path = SHEET) -> list[dict]:
    """Every feature row that carries scenarios, with its cells by header."""
    from openpyxl import load_workbook

    worksheet = load_workbook(sheet, read_only=True, data_only=True).active
    rows = worksheet.iter_rows(values_only=True)
    headers = [str(cell or "").strip() for cell in next(rows)]
    if COLUMN not in headers:
        raise ValueError(f'the plan sheet has no "{COLUMN}" column')
    found = []
    for values in rows:
        row = dict(zip(headers, values, strict=False))
        is_feature = str(row.get("Row type") or "").strip() == "Feature"
        if is_feature and str(row.get(COLUMN) or "").strip():
            found.append(row)
    return found


def expected_files(rows: list[dict]) -> dict[Path, str]:
    """The exact bytes each generated file must hold, keyed by path under tests/features."""
    files: dict[Path, str] = {}
    for row in rows:
        row_id = str(row.get("ID") or "").strip()
        parts = row_id.split("-")
        if len(parts) != 3 or parts[0] != "F" or parts[1] not in PHASE_DIRECTORIES:
            raise ValueError(f"row {row_id!r} carries scenarios but its ID is not F-<phase>-<nn>")
        scenarios = str(row[COLUMN]).replace("\r\n", "\n").strip("\n")
        text = (header(row_id) + f"Feature: {row_id} {str(row.get('Feature') or '').strip()}\n\n"
                + scenarios + "\n")
        path = Path(PHASE_DIRECTORIES[parts[1]]) / f"{row_id}.feature"
        if path in files:
            raise ValueError(f"two rows claim the ID {row_id}")
        files[path] = text
    return files


def problems(expected: dict[Path, str], features: Path = FEATURES) -> list[str]:
    """Differences between the sheet and the files on disk. Empty means they agree."""
    found = []
    on_disk = {path.relative_to(features): path for path in features.rglob("*.feature")}
    for relative, text in sorted(expected.items()):
        path = on_disk.get(relative)
        if path is None:
            found.append(f"{relative}: in the sheet and not generated")
        elif path.read_text(encoding="utf8").replace("\r\n", "\n") != text:
            found.append(f"{relative}: differs from the sheet")
    for relative in sorted(set(on_disk) - set(expected)):
        found.append(f"{relative}: a feature file with no row in the sheet")
    return found


def write(expected: dict[Path, str], features: Path = FEATURES) -> None:
    for relative, text in expected.items():
        target = features / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf8", newline="\n")
    for path in features.rglob("*.feature"):
        if path.relative_to(features) not in expected:
            first = path.read_text(encoding="utf8").splitlines()[:1]
            if first and first[0].startswith("# GENERATED from docs/Nyaymalaw_Implementation_Plan"):
                path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="regenerate the feature files")
    args = parser.parse_args()
    expected = expected_files(sheet_rows())
    if args.write:
        write(expected)
    found = problems(expected)
    for line in found:
        print(line)
    print(f"{len(expected)} feature file(s) from the sheet; {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
