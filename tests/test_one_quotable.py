"""B-108 — the prompt and the verbatim guard are one value, everywhere.

WHAT WAS MEASURED, 6 September 2026
-------------------------------------
Every read with a verbatim guard was shown more than it would accept, and
nothing in the prompt said so. On a three-fact matter with one follow-up:

    read          the guard accepted        shown and NOT quotable
    ------------  ------------------------  -----------------------------
    cause         message + advocate words  6 of 8 spans
    posture       message + advocate words  6 of 8 spans
    chronology    the message ONLY          13 of 14 — the whole file
    dispute       the message ONLY          8 of 9
    issues        the account ONLY          2 of 7 — INCLUDING THIS TURN
    factors       account + the entry       6 of 11

B-108 found this the hard way: gpt-5.2 quoted a span across three lines of the
account including our own `[1984-04-15]` stamp, the guard correctly refused
it, the cause was not taken, and the turn was withheld. A weaker model had
quoted one clean sentence and passed. The gap between SHOWN and QUOTABLE
widened the moment the model got better at using its context.

WHY THIS TEST IS A SCAN
-------------------------
The two sides took separate parameters — `build_prompt(message, account)` and
`interpret(message, data, advocate_words)` — so passing different things to
them was not a mistake anyone could see. It is what the signatures asked for.
A review cannot hold six of those in step; a scan can.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.class_a

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "nm"
HOME = PACKAGE / "domain" / "quotable.py"


def _sources():
    out = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path, ast.parse(path.read_text(encoding="utf-8"),
                                    filename=str(path))))
    return out


def _rel(path) -> str:
    return path.relative_to(PACKAGE.parent).as_posix()


def functions_named(sources, needle: str) -> dict[str, list[ast.FunctionDef]]:
    out: dict[str, list[ast.FunctionDef]] = {}
    for path, tree in sources:
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and needle in node.name:
                out.setdefault(_rel(path), []).append(node)
    return out


def _params(fn: ast.FunctionDef) -> list[str]:
    a = fn.args
    return [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]


# ================================ the rule ==================================


def test_a_read_that_builds_a_prompt_and_a_guard_uses_one_value():
    """THE STRUCTURAL PROPERTY. If both functions take `quotable`, a caller
    handing the prompt one thing and the guard another has to work at it.

    Population from the package: any module with BOTH a prompt builder and a
    reader. `nm/open_matter/quarantine.py` added tomorrow is covered tomorrow.
    """
    sources = _sources()
    builders = functions_named(sources, "build_prompt")
    builders.update({k: v for k, v in
                     functions_named(sources, "build_inventory_prompt").items()
                     if k not in builders})
    readers = {}
    for needle in ("interpret", "read"):
        for mod, fns in functions_named(sources, needle).items():
            readers.setdefault(mod, []).extend(fns)

    wrong = []
    for mod, prompt_fns in sorted(builders.items()):
        reader_fns = [f for f in readers.get(mod, [])
                      if f.name in ("interpret", "read", "read_inventory")]
        if not reader_fns:
            continue
        prompt_takes = any("quotable" in _params(f) for f in prompt_fns)
        guard_takes = any("quotable" in _params(f) for f in reader_fns)
        if prompt_takes != guard_takes:
            wrong.append(
                f"{mod}: prompt takes quotable={prompt_takes}, "
                f"reader takes quotable={guard_takes}")

    assert not wrong, (
        "these build a prompt from one value and check the answer against "
        "another:\n  " + "\n  ".join(wrong)
        + "\n\nBoth take the `Quotable`, or neither does. One of each is how "
          "the prompt came to show what the guard would refuse.")


# ========================== the positive control ============================


def test_the_scan_catches_a_prompt_and_a_guard_that_disagree():
    """The mismatch the rule is about, planted directly."""
    tree = ast.parse('def build_prompt(quotable):\n    pass\n'
                     'def interpret(message, data, advocate_words=""):\n    pass\n')
    sources = [(PACKAGE / "planted.py", tree)]
    builders = functions_named(sources, "build_prompt")
    readers = functions_named(sources, "interpret")
    assert any("quotable" in _params(f) for f in builders["nm/planted.py"])
    assert not any("quotable" in _params(f) for f in readers["nm/planted.py"])


# ============================== the behaviour ===============================


def containment_guards(sources) -> list[tuple[str, int]]:
    """`fold(a) in fold(b)` — the exact shape all seven guards used.

    Both sides folded with the BASE fold. `nm.Archives.legal_brain.verify.grounding` asks a different
    question with `_citation_fold` — is this quotation in the retrieved
    authority — and is not swept by this, which is why the check is on the
    call and not on the word "in".
    """
    def _is_fold(node) -> bool:
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "fold")

    found = []
    for path, tree in sources:
        if path == HOME:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                continue
            if not isinstance(node.ops[0], (ast.In, ast.NotIn)):
                continue
            if _is_fold(node.left) and _is_fold(node.comparators[0]):
                found.append((_rel(path), node.lineno))
    return found


def test_nothing_decides_the_advocates_words_by_hand():
    """ONE GUARD, AND IT IS `Quotable.accepts`.

    Seven modules each had their own `fold(quoted) not in fold(...)`, and the
    thing on the right differed at every one — which is the whole defect, and
    was invisible because each looked correct where it stood.
    """
    stray = containment_guards(_sources())
    assert not stray, (
        f"these compare a quotation against text by hand instead of asking "
        f"`Quotable.accepts`: {stray}. The prompt cannot then say what the "
        f"guard will take, which is B-108.")


def test_the_scan_catches_a_planted_hand_guard():
    """S11. A scan that cannot fail is not a scan."""
    planted = ast.parse('def read(said, account):\n'
                        '    if fold(said) not in fold(account):\n'
                        '        return None\n')
    assert containment_guards([(PACKAGE / "planted.py", planted)]) \
        == [("nm/planted.py", 2)]


def test_the_scan_leaves_a_different_question_alone():
    """THE BOUND. `nm.Archives.legal_brain.verify.grounding` asks whether a quotation is in the
    RETRIEVED AUTHORITY, which is a different question with a different right
    answer, and folds with `_citation_fold`. A scan that swept it would push
    the citation pivot into the base fold to satisfy itself."""
    planted = ast.parse('def verify(q, corpus):\n'
                        '    if _citation_fold(q) not in _citation_fold(corpus):\n'
                        '        return None\n')
    assert containment_guards([(PACKAGE / "planted.py", planted)]) == []


