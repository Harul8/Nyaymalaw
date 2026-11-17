"""Which test files drive the page in a browser (plan AN.57, piece 57a; D263): every test file that names the browser library,
and every one that borrows, directly or through another, from a file that does. Printed one a line for the runner's journeys
job, so a journey added tomorrow is run tomorrow without anyone listing it.

  python development_environment/developer_tooling/journey_files.py [tests folder]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BROWSER = re.compile(r"\bplaywright\b")
BORROWS = re.compile(r"^\s*from tests\.(\w+) import|^\s*import tests\.(\w+)", re.M)


def journey_files(folder: Path) -> list[Path]:
    sources = {path.stem: path.read_text(encoding="utf8", errors="replace") for path in sorted(folder.glob("test_*.py"))}
    found = {name for name, text in sources.items() if BROWSER.search(text)}
    grew = True
    while grew:
        grew = False
        for name, text in sources.items():
            if name not in found and {a or b for a, b in BORROWS.findall(text)} & found:
                found.add(name)
                grew = True
    return [folder / f"{name}.py" for name in sorted(found)]


if __name__ == "__main__":
    for path in journey_files(Path(sys.argv[1] if len(sys.argv) > 1 else "tests")):
        print(path.as_posix())
