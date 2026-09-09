"""A DOCUMENTED DEFECT IS MARKED STRICT, NEVER CALLED.

BK-44, and the reason it is a sweep rather than a fix is CLAUDE.md §1.

`pytest.xfail("...")` called inside an `if` or an `except` reports the defect
and CAN NEVER XPASS, because the call only happens on the branch that takes it.
The day the defect is fixed, the branch stops being taken, the phase passes
quietly, and nothing says the marker is now a lie. The row stays open for ever
on evidence that stopped existing.

`@pytest.mark.xfail(strict=True, reason=...)` is the same documentation with
the opposite failure mode: when the defect goes, the test XPASSes, strict turns
that into a failure, and the suite tells you to delete the marker.

THE FILE THIS GUARDS ALREADY KNEW
---------------------------------
`tests/test_the_journey_login_to_logout.py` says so in its own header --
*"`xfail(strict=True)` and NAME that row. Strict is the whole point: the day
BK-32 lands, the phase passes, and a strict xfail that passes is an ERROR"* --
and then called `pytest.xfail(...)` imperatively at three sites, two of them on
rows marked DONE. A regression in a closed row reported REPRODUCED and the
command exited 0.

AND IT HAD ALREADY BEEN FOUND ONCE. Lines 268-274 of that file record the same
mistake at phase 3, fixed there: *"it called `pytest.xfail(...)` before the
assertion whenever `width < 820`, so the phase could never pass however the
product changed -- S11, a check that cannot fail, wearing the costume of one
that does."* Fixed at the one site it was found at. Three others were left.

That is the shape this sweep exists for. Stating a fix generally is not
applying it generally, and the population is EVERY test in the suite -- not the
journey file, which is merely where it was found this time.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def imperative_xfails(source: str) -> list[str]:
    """Every `pytest.xfail(...)` / bare `xfail(...)` CALL in the source.

    The decorator form is `@pytest.mark.xfail`, an Attribute on `mark`, and is
    the thing we want -- so matching on the call target keeps them apart
    without needing to know how the module was imported.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:                     # pragma: no cover -- defensive
        return []

    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # `pytest.xfail(...)`
        if isinstance(f, ast.Attribute) and f.attr == "xfail" \
                and isinstance(f.value, ast.Name):
            found.append(f"line {node.lineno}: {f.value.id}.xfail(...)")
        # `xfail(...)`, from `from pytest import xfail`
        elif isinstance(f, ast.Name) and f.id == "xfail":
            found.append(f"line {node.lineno}: xfail(...)")
    return found


def _suite() -> list[Path]:
    return sorted((ROOT / "tests").glob("test_*.py"))


def test_no_test_calls_xfail_instead_of_marking_it():
    """THE SWEEP. Every test file in the suite."""
    files = _suite()
    assert len(files) > 50, (
        f"only {len(files)} test files found, so this sweep is reading an "
        f"empty population and would pass on anything")

    offenders: list[str] = []
    for f in files:
        for hit in imperative_xfails(f.read_text(encoding="utf-8")):
            offenders.append(f"{f.relative_to(ROOT)}: {hit}")

    assert not offenders, (
        "these call `pytest.xfail(...)` instead of marking the test:\n  "
        + "\n  ".join(offenders)
        + "\n\nAn imperative xfail fires only on the branch that takes it, so "
          "it can never XPASS and the day the defect is fixed nothing says "
          "so. Use `@pytest.mark.xfail(strict=True, reason='BK-nn: ...')` and "
          "assert the rule in the body.")


def test_the_xfail_scan_can_see_a_planted_call():
    """THE POSITIVE CONTROL, in all the forms the call is written in.

    Both plants are shapes that were actually in the journey file: one guarded
    by `if`, one by `except`.
    """
    for planted in (
        "import pytest\ndef test_x():\n    if broken:\n"
        "        pytest.xfail('BK-40: ...')\n",
        "import pytest\ndef test_x():\n    try:\n        go()\n"
        "    except Exception:\n        pytest.xfail('BK-30: ...')\n",
        "from pytest import xfail\ndef test_x():\n    xfail('BK-1: ...')\n",
    ):
        assert imperative_xfails(planted), (
            f"the scan did not see the call in {planted!r}, so it would not "
            f"have caught BK-44 and reports a clean suite either way")


def test_the_xfail_scan_leaves_the_strict_marker_alone():
    """THE NEGATIVE CONTROL. The decorator is the thing we are asking for, and
    a sweep that flagged it would make the fix impossible to apply."""
    for allowed in (
        "import pytest\n@pytest.mark.xfail(strict=True, reason='BK-40: ...')\n"
        "def test_x():\n    assert thing\n",
        "import pytest\n@pytest.mark.xfail(raises=ValueError, strict=True)\n"
        "def test_x():\n    go()\n",
        "import pytest\n@pytest.mark.parametrize('w', [1])\n"
        "def test_x(w):\n    assert w\n",
    ):
        assert not imperative_xfails(allowed), (
            f"the scan flagged {allowed!r}, which is the marker form this "
            f"rule asks for")


def test_every_xfail_marker_is_strict_and_names_its_row():
    """THE OTHER HALF. A non-strict marker has the same defect as the call:
    it never reports that the defect is gone.

    And a marker with no row is a defect nobody can look up -- the suite would
    say a phase is expected to fail and not say what for.
    """
    offenders: list[str] = []
    for f in _suite():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "xfail"):
                    continue
                kw = {k.arg: k.value for k in dec.keywords}
                strict = kw.get("strict")
                if not (isinstance(strict, ast.Constant) and strict.value is True):
                    offenders.append(
                        f"{f.relative_to(ROOT)}::{node.name} — not strict")
                reason = kw.get("reason")
                text = reason.value if isinstance(reason, ast.Constant) else (
                    "".join(v.value for v in getattr(reason, "values", [])
                            if isinstance(v, ast.Constant)) if reason else "")
                if not any(t in str(text) for t in ("BK-", "B-", "J-", "GS-")):
                    offenders.append(
                        f"{f.relative_to(ROOT)}::{node.name} — names no row")

    assert not offenders, (
        "these xfail markers cannot report that the defect is gone, or do not "
        "say which defect:\n  " + "\n  ".join(offenders)
        + "\n\nEvery documented defect is `strict=True` and names the row it "
          "is documenting.")
