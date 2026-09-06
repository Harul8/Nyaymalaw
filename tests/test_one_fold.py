"""ONE DEFINITION OF "THIS IS THE SAME TEXT", and this refuses the second.

WHAT WAS MEASURED, 6 September 2026
------------------------------------
Six `_fold` functions in `nm/`, and they were not the same function:

    chronology, dispute, posture   words only  ── identical, three copies
    grounding                      words only, plus the `vs`/`v` pivot
    issue, decision                WHITESPACE COLLAPSE ONLY

So the product held two different answers to "are these the same sentence",
and which one you got depended on which module you were standing in:

    "Is the agreement enforceable?"  vs  "Is the agreement enforceable"
        chronology.conflicts  ── the same event
        issue.merge           ── two issues

The second is the duplicate-issue defect surviving its own fix. `restates`
made the READ able to name an id; the folded statement was the fallback for
when it did not, and the fallback was folding on punctuation.

WHY A SCANNER AND NOT A CODE REVIEW
-------------------------------------
None of the six was written by someone ignoring a rule. They were written by
six people who each needed a fold, found no one place to get it, and wrote the
two-line version — which is CLAUDE.md §4 exactly: the question is not where the
other copy is, it is what makes a second copy impossible.

The same mechanism `tests/test_citation_patterns.py` uses for provision
patterns, drawing its population from the WHOLE package rather than from a
list — a list would not have contained `nm/domain/decision.py`, which was
three days old when this was written.

THE BOUND
----------
A caller may need MORE normalisation than the base and that is not a second
copy — `nm.core.grounding._citation_fold` folds `vs` and `versus` to `v`,
which is right for a case name and wrong for an advocate's sentence. What it
may not do is define its own base, so the rule is that it must CALL `fold`.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.class_a

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "nm"

#: The one module allowed to define the base. Its docstring carries the
#: argument; this carries the enforcement.
HOME = PACKAGE / "domain" / "text.py"

#: The base fold's own pattern. A second compilation of it, under any name, is
#: a second fold wearing a variable.
WORD_PATTERN = "[a-z0-9]+"


def _sources() -> list[tuple[pathlib.Path, ast.Module]]:
    out = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((path, ast.parse(path.read_text(encoding="utf-8"),
                                    filename=str(path))))
    return out


def _calls(node: ast.AST) -> set[str]:
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def folds_defined(sources) -> list[tuple[str, str, bool]]:
    """Every function in `nm/` whose name says it folds text.

    Returned as (module, function, calls_the_base) so the caller decides what
    is permitted -- the scan does not encode the exception, the assertion does.
    """
    out = []
    for path, tree in sources:
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if "fold" not in node.name.lower():
                continue
            rel = path.relative_to(PACKAGE.parent).as_posix()
            out.append((rel, node.name, "fold" in _calls(node)))
    return out


def word_patterns(sources) -> list[str]:
    """Modules that compile the base fold's own word pattern."""
    out = []
    for path, tree in sources:
        if path == HOME:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == WORD_PATTERN:
                out.append(path.relative_to(PACKAGE.parent).as_posix())
                break
    return out


# ================================ the rule ==================================

def test_only_one_module_defines_the_base_fold():
    """A fold that does not call `fold` IS a base fold, whatever it is named.

    Renaming the six copies would have satisfied a check on the name `_fold`
    and changed nothing, so the test is about the BODY.
    """
    offenders = [(mod, name) for mod, name, calls_base in folds_defined(_sources())
                 if not calls_base and mod != "nm/domain/text.py"]
    assert not offenders, (
        f"these define their own text fold instead of calling "
        f"`nm.domain.text.fold`: {offenders}. Six of these existed on "
        f"6 September 2026 and two of them disagreed with the other four "
        f"about whether a question mark makes two sentences different.")


def test_the_base_fold_is_where_it_says_it_is():
    """The counterpart. A scan that would pass on an empty package proves
    nothing -- if `fold` were renamed or moved, the check above would go
    quietly green with no fold anywhere."""
    defined = folds_defined(_sources())
    assert ("nm/domain/text.py", "fold", False) in defined, (
        f"`nm.domain.text.fold` is not where the rule says it is: {defined}")


def test_nothing_else_compiles_the_word_pattern():
    """The same rule reached through the regex rather than the function. Five
    of the six copies were `re.compile(r"[a-z0-9]+")` and a `join`, so a
    module holding that pattern is holding a fold whether or not it wrapped
    one in a `def`."""
    assert not word_patterns(_sources()), (
        f"these compile the base fold's own word pattern: "
        f"{word_patterns(_sources())}. Use `nm.domain.text.fold`.")


# =============================== the bound ==================================

def test_a_composition_on_the_base_is_permitted():
    """Not every fold is the same fold, and the rule must not say so.

    `_citation_fold` normalises the case-name pivot, which is a fact about
    citations: "K. Venkata Rao vs Sunkara" and "K. Venkata Rao v Sunkara" are
    one case. Applying that to an advocate's sentence would merge "the notice
    vs the reply" with "the notice v the reply", so it is right that it lives
    in `grounding` and wrong that it would live in `text`.
    """
    from nm.core.grounding import _citation_fold
    from nm.domain.text import fold

    assert _citation_fold("Rao vs Sunkara") == _citation_fold("Rao v Sunkara")
    assert fold("Rao vs Sunkara") != fold("Rao v Sunkara"), (
        "the base fold has taken on the citation pivot, so every module now "
        "reads `vs` and `v` as one word -- including the ones comparing an "
        "advocate's sentences")


# ========================== the positive control ============================
#
# A SWEEP THAT CANNOT FAIL IS NOT A SWEEP (defect shape S11). These plant the
# member the scan is meant to catch and assert it is caught, because the whole
# point of scanning a package rather than a list is that the scan must work on
# code nobody has thought about yet.

def test_the_scan_catches_a_planted_fold(tmp_path):
    planted = ast.parse(
        'def _fold(text):\n'
        '    return " ".join((text or "").lower().split())\n')
    found = folds_defined([(PACKAGE / "planted.py", planted)])
    assert found == [("nm/planted.py", "_fold", False)], found


def test_the_scan_catches_a_fold_renamed_to_hide(tmp_path):
    """The rename that would defeat a name-only check."""
    planted = ast.parse(
        'def normalise_for_comparison(text):\n'
        '    return text.lower().strip()\n')
    assert folds_defined([(PACKAGE / "planted.py", planted)]) == [], (
        "this is the KNOWN LIMIT, asserted rather than hoped for: a fold "
        "named nothing like one is not caught, and no scanner catches it. "
        "What the scan buys is that the obvious way to write the seventh "
        "copy is refused, which is how all six were written.")


def test_the_pattern_scan_catches_a_planted_regex():
    planted = ast.parse('import re\n_W = re.compile(r"[a-z0-9]+")\n')
    assert word_patterns([(PACKAGE / "planted.py", planted)]) \
        == ["nm/planted.py"]
