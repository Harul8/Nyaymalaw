"""The screen an advocate actually sees, checked on the bytes of both files.

WHY THIS EXISTS
----------------
`$('register-state')` returns `null` when the element is gone, and
`null.textContent = ''` throws — inside a submit handler, so the form silently
does nothing and the advocate presses Register again. There is no compiler
between these two files and nothing else in the build reads them.

It is the same failure that produced "register click is not working": the code
was right, the wiring between what runs and what is on the page was not, and
the only way to see it was to be sitting in front of the browser.

WHAT IT DOES NOT DO. It does not run the page. A headless browser in the
class-A cadence is a different trade, and the defects it would catch are not
these — these are two files disagreeing about a name, which is a text problem.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
SCRIPT = (WEB / "app.js").read_text(encoding="utf-8")

#: `$('literal')` only. A template literal is built at runtime -- `pane-${p}`
#: names four elements and no scanner can tell which -- so those are out of
#: this check's reach, and saying so is better than a regex that half-catches
#: them and reads as though it covered everything.
LOOKUP = re.compile(r"""\$\(\s*'([A-Za-z0-9_-]+)'\s*\)""")
ELEMENT_ID = re.compile(r"""\bid\s*=\s*["']([A-Za-z0-9_-]+)["']""")


def ids_on_the_page() -> set[str]:
    return set(ELEMENT_ID.findall(HTML))


def ids_the_script_reaches_for() -> set[str]:
    return set(LOOKUP.findall(SCRIPT))


# ================================ the rule ==================================

def test_every_element_the_script_reaches_for_is_on_the_page():
    """THE DEFECT, AS A RULE. `$()` on a missing id returns null and the next
    property access throws inside whatever handler asked for it."""
    missing = sorted(ids_the_script_reaches_for() - ids_on_the_page())
    assert not missing, (
        f"app.js reaches for these and index.html does not have them: "
        f"{missing}. `$()` returns null and the handler throws where nobody "
        f"is looking.")


def test_the_registration_outcome_is_wired_in_both_directions():
    """The card added on 6 September 2026, asserted by name.

    The check above passes if BOTH files lose an element together, which is
    what a deletion looks like. This says the outcome card is there — an
    advocate who registers must be told it worked, and told where to go next.
    """
    for element in ("outcome", "outcome-title", "outcome-body",
                    "outcome-signin", "outcome-back"):
        assert element in ids_on_the_page(), f"{element} is not on the page"
        assert element in ids_the_script_reaches_for(), (
            f"{element} is on the page and nothing in app.js touches it, so "
            f"it is decoration")


def test_the_outcome_card_reports_failure_as_well_as_success():
    """BOTH STATES, OR IT IS A CELEBRATION RATHER THAN A REPORT. A card that
    only ever appears on success sends every failure back to a grey line under
    a form, which is where the advocate is not looking."""
    assert "showOutcome('good'" in SCRIPT
    assert SCRIPT.count("showOutcome('bad'") >= 2, (
        "the server's refusal and the client-side password mismatch must both "
        "reach the card, or one of the two ways a registration can fail is "
        "reported somewhere else")


# =========================== the reveal control =============================

def test_every_password_reveal_is_a_button_and_not_a_submit():
    """A default-type button inside a form IS a submit button, so clicking the
    eye would post a half-filled registration. Reasoned about in a comment
    when it was written; asserted here, because a comment does not fail."""
    eyes = re.findall(r"<button[^>]*class=\"pw-eye\"[^>]*>", HTML) \
        + re.findall(r"<button[^>]*pw-eye[^>]*>", HTML)
    assert eyes, "no reveal control found -- this test is asserting nothing"
    for tag in eyes:
        assert 'type="button"' in tag, (
            f"a reveal control without type=button submits the form: {tag}")


# ============================== the positive control ========================

def test_the_scan_would_catch_a_missing_element():
    """S11. A scan that cannot fail is not a scan, and this one is two regexes
    over two files -- exactly the kind that passes because it matched nothing.
    """
    assert LOOKUP.findall("$('planted-id')") == ["planted-id"]
    assert ELEMENT_ID.findall('<div id="planted-id">') == ["planted-id"]
    assert "planted-id" not in ids_on_the_page()
