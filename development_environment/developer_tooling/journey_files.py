"""Which test files drive the page in a browser (plan AN.57, piece 57a; D263): every test file that names the browser library,
and every one that borrows, directly or through another, from a file that does. Printed one a line for the runner's journeys
job, so a journey added tomorrow is run tomorrow without anyone listing it.

What a file borrows is read from its imports as Python reads them (plan AN.48, D306): `from tests.<file> import ...`,
`import tests.<file>`, and `from tests import <file> as <name>` - one file or several - all name the file borrowed. The last form
was missed while the imports were matched as text, and the AI permission journey, which borrows the login journey that way, was
left out of the job.

  python development_environment/developer_tooling/journey_files.py [tests folder]
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BROWSER = re.compile(r"\bplaywright\b")


def borrowed(text: str) -> set[str]:
    """The test files of the tests folder a file's source imports, by their names; none where it cannot be parsed."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[1] for alias in node.names if alias.name.startswith("tests.")}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if (node.level == 0 and module == "tests") or (node.level == 1 and not module):
                names |= {alias.name for alias in node.names}
            elif node.level == 0 and module.startswith("tests."):
                names.add(module.split(".")[1])
            elif node.level == 1 and module:
                names.add(module.split(".")[0])
    return names


def journey_files(folder: Path) -> list[Path]:
    sources = {path.stem: path.read_text(encoding="utf8", errors="replace") for path in sorted(folder.glob("test_*.py"))}
    found = {name for name, text in sources.items() if BROWSER.search(text)}
    borrows = {name: borrowed(text) for name, text in sources.items()}
    grew = True
    while grew:
        grew = False
        for name in sources:
            if name not in found and borrows[name] & found:
                found.add(name)
                grew = True
    return [folder / f"{name}.py" for name in sorted(found)]


if __name__ == "__main__":
    for path in journey_files(Path(sys.argv[1] if len(sys.argv) > 1 else "tests")):
        print(path.as_posix())
