"""AN OPTIONAL LIBRARY IS AVAILABLE ONLY IF IT IMPORTS. The rule, not the case.

WHY
---
Measured 18 September 2026, on code written the day before. `vosk` was
installed with `--no-deps`, `importlib.util.find_spec("vosk")` answered yes, and
`/api/health` reported

    dictation_live : installed; vosk-model-small-en-in-0.4 loads on first use

while the first frame of speech raised `ModuleNotFoundError: No module named
'srt'` from inside `vosk/__init__.py`. A feature that could not run reported the
shape of a clean result -- defect shape **S1**, the most repeated one in the
register -- because the check answered on a PROXY: a package directory on the
import path is not a library that runs.

Three sites decided such a question, in two adapters, by `find_spec`. The fix is
one mechanism, `nm.adapters.optional`, and this file is what keeps it one:

* nothing else in the product may look at the import path, so a fourth site
  cannot reappear beside it; and
* an adapter whose library is unusable must SAY SO, whichever half is missing --
  not installed, or installed and unimportable with the reason.

The population for both is drawn from the code: every module under
`backend/nm/`, and every speech adapter that reports readiness, so an adapter
added to a sibling module tomorrow is covered without this file being edited.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest
from nm.adapters import optional

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
#: The one module permitted to ask the import path anything.
OWNER = Path("backend/nm/adapters/optional.py")


def _import_path_lookups() -> list[str]:
    """Every call to `find_spec` in the product, wherever it is spelled."""
    found: list[str] = []
    for file in sorted((ROOT / "backend" / "nm").rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        for node in ast.walk(ast.parse(file.read_text(encoding="utf8"))):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", ""))
            if name in ("find_spec", "find_module"):
                found.append(f"{file.relative_to(ROOT).as_posix()}:{node.lineno}")
    return found


def _speech_adapters() -> list[tuple[object, type]]:
    """Every speech adapter class that answers `/api/health`, found by import."""
    package = importlib.import_module("nm.adapters.speech")
    out: list[tuple[object, type]] = []
    for info in pkgutil.iter_modules(list(package.__path__)):
        module = importlib.import_module(f"nm.adapters.speech.{info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and callable(getattr(cls, "readiness", None)):
                out.append((module, cls))
    return out


def test_the_scan_can_see_the_product():
    """A guard on the guards below: an empty population passes both."""
    assert _import_path_lookups(), (
        "not one import-path lookup was found in backend/nm/ -- the scan below "
        "would then be asserting nothing over nothing")
    assert len(_speech_adapters()) >= 2, (
        "fewer than two speech adapters were discovered; the readiness rule "
        "below would be asserting almost nothing")


def test_only_one_module_may_ask_the_import_path():
    """S9: two owners for one truth, and the second one answers on a proxy.

    `find_spec` is the cheap wrong answer to "is this library available". It is
    allowed to live in exactly one place, where the docstring says what it is
    for and `library()` sits beside it.
    """
    strays = [site for site in _import_path_lookups()
              if not site.startswith(OWNER.as_posix())]
    assert not strays, (
        "these decide something from the import path instead of from "
        "`nm.adapters.optional`:\n  " + "\n  ".join(strays)
        + f"\n\n{OWNER.as_posix()} is the only module permitted to. Use "
          "`library(name)` for availability, or `library_path(name)` for a "
          "path lookup that must not import.")


def test_a_library_that_is_installed_and_will_not_import_is_not_usable(tmp_path, monkeypatch):
    """THE DEFECT ITSELF, as a rule: present is not usable."""
    (tmp_path / "nm_a_library_that_raises.py").write_text(
        "raise RuntimeError(\"No module named 'srt'\")\n", encoding="utf8")
    monkeypatch.syspath_prepend(str(tmp_path))
    optional.forget("nm_a_library_that_raises")
    try:
        found = optional.library("nm_a_library_that_raises")
        assert found.present, "it is on the import path"
        assert not found.usable, "it does not import, so it is not available"
        assert "RuntimeError" in (found.reason or ""), found.reason
        assert "srt" in (found.reason or ""), (
            "the reason is recorded verbatim: the administrator's next step is "
            "in it")
        assert found.why_not("the live speech library").startswith("NOT USABLE"), (
            found.why_not("the live speech library"))
    finally:
        optional.forget("nm_a_library_that_raises")


def test_a_library_that_is_absent_and_one_that_works_are_told_apart():
    """FOUR STATES, NOT TWO: which half is missing is the actionable part."""
    absent = optional.library("nm_no_library_is_installed_under_this_name")
    assert not absent.present and not absent.usable
    assert absent.why_not("the live speech library").startswith("NOT INSTALLED")

    present = optional.library("json")
    assert present.usable and present.reason is None
    assert present.why_not("the standard library") == "", (
        "a usable library has nothing to say about why it is not")


def test_library_path_does_not_import_what_it_locates():
    """The path lookup stays a path lookup -- it is how CUDA libraries shipped
    inside `torch` are put on the search path, before anything imports torch."""
    assert optional.library_path("nm_no_library_is_installed_under_this_name") is None
    here = optional.library_path("nm")
    assert here is not None and here.name == "nm"


@pytest.mark.parametrize("state, reason", [
    ("absent", None),
    ("installed but unimportable", "ModuleNotFoundError: No module named 'srt'"),
])
def test_no_speech_adapter_reports_a_library_it_cannot_use_as_ready(monkeypatch, state, reason):
    """Every speech adapter, including one added after this was written.

    The health line for a library that cannot run must not begin the way a
    working one does. That is S1 in one assertion: the third state is visible in
    the OUTPUT, not merely representable in the type.
    """
    for module, cls in _speech_adapters():
        unusable = optional.Library(name="stand-in", present=reason is not None, reason=reason)
        monkeypatch.setattr(module, "library", lambda _name, answer=unusable: answer,
                            raising=True)
        said = cls().readiness()
        assert said.startswith("NOT "), (
            f"{cls.__module__}.{cls.__name__}.readiness() says {said!r} while its "
            f"library is {state}")
        if reason:
            assert "srt" in said, (
                f"{cls.__module__}.{cls.__name__}.readiness() hides why the library "
                f"did not load: {said!r}")
