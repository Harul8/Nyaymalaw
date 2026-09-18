"""A STEP PATCHES THE APPLICATION UNDER TEST, or it patches a previous test's.

WHY
---
Measured 18 September 2026, on F-C-03's socket scenario. The step

    @given("the live dictation service", target_fixture="live_speech")
    def the_live_dictation_service(monkeypatch):
        from nm.edge.api import application
        monkeypatch.setattr(application().live_dictation, "inner", engine)

put a stand-in speech engine on `application()` -- and `application()` is a
module global that the composition root injects. The `client` fixture is what
injects it, this step did not ask for `client`, so the step ran FIRST and
`application()` returned **whichever application the previous test in the run
had wired**. The stand-in went onto a dead object, the socket ran the real
speech model, and the words came back `['', '']`.

Run alone, the same step raised *no application wired* -- the identical defect
being honest, which is why it went unnoticed in a batch: the silent form looks
like a product bug (S1 again -- the patch was absent and the run read as
success).

THE RULE, therefore: any step, fixture or test that reaches the wired
application must DEPEND on something that wires one. `conftest.wired` is that
dependency, and asking for it makes the ordering structural instead of
incidental.

WHAT IS DELIBERATELY NOT FLAGGED
---------------------------------
A private helper called from inside a test body -- `_provision_deciding(...)`,
`_application()` -- cannot run before its caller, and its caller holds the
fixture. Flagging those would mean rewriting call sites to prove something the
call graph already guarantees. What is flagged is every function pytest itself
invokes: a step, a fixture, a test.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
#: Fixtures that wire an application before they hand anything back.
WIRING = {"client", "wired", "app", "signed_in"}
#: The decorators pytest and pytest-bdd call the function through.
CALLED_BY_PYTEST = ("given", "when", "then", "fixture", "parametrize")
#: The one owner: the fixture that resolves `application()` for everybody else.
OWNER = "tests/conftest.py"


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = set()
    for decorator in node.decorator_list:
        call = decorator.func if isinstance(decorator, ast.Call) else decorator
        names.add(call.attr if isinstance(call, ast.Attribute) else getattr(call, "id", ""))
    return names


def _calls_application(node: ast.AST) -> bool:
    """Whether this function CALLS `application()`.

    Matched on the call, never on the text: a docstring that names the mistake
    -- this file is full of them -- is not the mistake.
    """
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "application":
            return True
    return False


def _invoked_by_pytest() -> list[tuple[str, int, bool, set[str]]]:
    """Every step, fixture and test in the suite, with the fixtures it asks for."""
    out = []
    for file in sorted(ROOT.joinpath("tests").rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        src = file.read_text(encoding="utf8")
        tree = ast.parse(src)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_test = node.name.startswith("test_")
            if not (is_test or _decorators(node) & set(CALLED_BY_PYTEST)):
                continue
            out.append((file.relative_to(ROOT).as_posix(), node.lineno,
                        _calls_application(node), {a.arg for a in node.args.args}))
    return out


def test_the_scan_can_see_the_suite():
    """A guard on the guard: an empty population passes the test below."""
    found = _invoked_by_pytest()
    assert len(found) >= 200, (
        f"only {len(found)} steps, fixtures and tests were discovered — this "
        f"file would then be asserting almost nothing")
    assert any(reaches for _, _, reaches, _ in found), (
        "not one of them reaches the wired application; the rule below would "
        "be vacuous")


def test_no_step_reaches_an_application_it_did_not_ask_for():
    """THE POINT. `application()` is whatever was wired LAST.

    Without a wiring fixture in the signature, that is a previous test's
    application, and a patch applied to it is silently inert.
    """
    strays = [f"{path}:{line}" for path, line, reaches, args in _invoked_by_pytest()
              if reaches and not (WIRING & args) and path != OWNER]
    assert not strays, (
        "these are invoked by pytest and reach the wired application without "
        "depending on a fixture that wires one:\n  " + "\n  ".join(strays)
        + "\n\nAdd the `wired` fixture to the signature and use it instead of "
          "importing `nm.edge.api.application`. A step that resolves the "
          "application itself gets the previous test's, and the patch it makes "
          "there changes nothing — which is how F-C-03's socket came to run the "
          "real speech model against a stand-in's assertions.")
