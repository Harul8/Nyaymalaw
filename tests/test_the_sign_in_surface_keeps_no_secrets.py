"""THE SIGN-IN PAGE HOLDS A RESET LINK ONCE AND WRITES IT NOWHERE. F-A-03.

The emailed link carries a bearer token in the address fragment. Every place
that token or a typed password could outlive the screen that used it is a
place the next person on a shared machine finds it: browser storage, a DOM
attribute, the address bar and its history, a hidden form that keeps its values.

A STATIC SCAN, and the browser journey is its complement: a browser test proves
the path it drove, this proves there is no path that could store the secret.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "frontend" / "app.js"
STORAGE = re.compile(r"(localStorage|sessionStorage)\s*\.\s*(\w+)")


def _script() -> str:
    return SCRIPT.read_text(encoding="utf8")


def _without_comments(text: str) -> str:
    """Comments discuss `localStorage` on purpose; code must not use it."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("//"))


def storage_writes(script: str) -> list[tuple[str, str]]:
    code = _without_comments(script)
    return (STORAGE.findall(code)
            + [(store, "[]") for store in re.findall(r"(localStorage|sessionStorage)\s*\[", code)])


def test_the_script_never_writes_to_browser_storage_at_all():
    """A BLANKET RULE. Scoping it to "secrets" needs a judgement at every future
    call site; nothing in this product needs to persist across a tab close."""
    writes = storage_writes(_script())
    assert not writes, f"frontend/app.js touches browser storage: {writes}"


def test_the_storage_sweep_can_see_a_planted_write():
    planted = _script().replace(
        "let resetToken = null;",
        "let resetToken = null;\nlocalStorage.setItem('nm_reset', 'x');", 1)
    assert "localStorage.setItem" in planted, "the plant did not apply"
    assert ("localStorage", "setItem") in storage_writes(planted)


def reset_token_problems(script: str) -> list[str]:
    problems = []
    code = _without_comments(script)
    if not re.search(r"^let resetToken = null;", code, re.M):
        problems.append("the reset token is not one module variable")
    if re.search(r"dataset\.\w*[Rr]eset", code):
        problems.append("the reset token is parked on a DOM node")
    take = code.find("function takeResetToken()")
    body = code[take:code.find("\n}\n", take)] if take >= 0 else ""
    captured = body.find("resetToken = match[1];")
    erased = body.find("history.replaceState(")
    if min(captured, erased) < 0 or not captured < erased:
        problems.append("the reset token stays in the address bar")
    handler = code.find("$('reset').addEventListener('submit'")
    flow = code[handler:code.find("\n});", handler)] if handler >= 0 else ""
    cleared = flow.find("clearResetPasswords();")
    sent = flow.find("await api('/api/password/reset'")
    if min(cleared, sent) < 0 or not cleared < sent:
        problems.append("the new passwords stay in the DOM during the request")
    if "resetToken = null;" not in flow[sent:] if sent >= 0 else True:
        problems.append("a spent reset token is not dropped")
    show = code.find("function showForm(")
    show_form = code[show:code.find("\n}\n", show)] if show >= 0 else ""
    if "if (which !== 'reset') clearResetPasswords();" not in show_form:
        problems.append("leaving the reset card keeps its passwords")
    return problems


def test_the_reset_token_and_passwords_leave_the_page_as_soon_as_they_are_used():
    assert not reset_token_problems(_script())


def test_the_reset_scan_sees_each_planted_leak():
    script = _script()
    mutations = {
        "the reset token stays in the address bar":
            script.replace("history.replaceState(", "void (", 1),
        "the new passwords stay in the DOM during the request":
            script.replace("  clearResetPasswords();\n  if (!token)", "  if (!token)", 1),
        "leaving the reset card keeps its passwords":
            script.replace("if (which !== 'reset') clearResetPasswords();", "", 1),
        "the reset token is parked on a DOM node":
            script.replace("resetToken = match[1];",
                           "resetToken = match[1]; document.body.dataset.resetToken = 1;", 1),
    }
    for expected, mutated in mutations.items():
        assert mutated != script, f"the plant for {expected!r} did not apply"
        assert expected in reset_token_problems(mutated), expected
