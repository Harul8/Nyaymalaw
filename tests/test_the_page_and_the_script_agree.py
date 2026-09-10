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


# ============================ what is actually visible ======================

#: COMMENTS STRIPPED FIRST, and this is not fastidiousness. The first version
#: of this read `z-index: 100` out of a COMMENT in the `.build-warning` rule --
#: the comment explaining that `.gate` is at 100 -- and reported the banner as
#: stacking at 100 when it is declared at 200. A value inside a comment is not
#: a declaration, and a check that cannot tell the difference is reading prose.
STYLE = re.sub(r"/\*.*?\*/", "", (WEB / "app.css").read_text(encoding="utf-8"),
               flags=re.S)


def _z_index(selector: str) -> int:
    """The `z-index` declared in the LAST rule for this selector.

    Read from the text rather than from a browser, so it runs in the class-A
    cadence. That is a real limit -- a cascade this cannot see could still
    bury the banner -- and it catches the case that actually happened.
    """
    block = STYLE.rsplit(selector + " {", 1)[1].split("}", 1)[0]
    found = re.search(r"z-index:\s*(\d+)", block)
    assert found, f"{selector} declares no z-index"
    return int(found.group(1))


def test_the_build_banner_draws_above_the_gate():
    """MEASURED, 6 September 2026, and it nearly shipped.

    The banner was in the DOM, `hidden` was false, and the text was right --
    and it was drawn UNDERNEATH the sign-in screen, because the sign-in gate
    is `position: fixed; inset: 0; z-index: 100` and covers the viewport. It
    was invisible in the one place the staleness it warns about was refusing
    registrations.

    `hidden === false` was true and meant nothing. A control that is correct
    and unreachable is the shape this whole build keeps paying for, and the
    only thing that found it was looking at the pixels.

    THE SELECTOR MOVED FROM `.gate` TO `#gate` on 8 September 2026, and the
    reason is the second half of this same lesson. `.gate` had TWO owners --
    this overlay and a gate FIRING inside an answer -- so every disclosure in
    an advocate's answer inherited `position: fixed; inset: 0; z-index: 100`
    and painted the whole application white. The overlay is one element with
    an id, so it is addressed by one; `tests/test_no_css_class_has_two_owners
    .py` refuses the next collision.
    """
    assert _z_index(".build-warning") > _z_index("#gate"), (
        "the build banner stacks below the sign-in gate, so it is invisible "
        "on the screen where a stale server does its damage")


# ============================== the positive control ========================

def test_the_scan_would_catch_a_missing_element():
    """S11. A scan that cannot fail is not a scan, and this one is two regexes
    over two files -- exactly the kind that passes because it matched nothing.
    """
    assert LOOKUP.findall("$('planted-id')") == ["planted-id"]
    assert ELEMENT_ID.findall('<div id="planted-id">') == ["planted-id"]
    assert "planted-id" not in ids_on_the_page()


def test_late_rail_work_cannot_overwrite_newer_navigation():
    """BK-72's cheap guard; the real counterexample remains browser evidence.

    Every rail request takes a generation, checks it after awaiting the wire,
    and the automatic post-send refresh is expressly denied authority to close
    a navigator the advocate opened. Matter ids on rows and the pane make a
    distinct-file switch observable to the journey rather than inferred from
    a title both files share.
    """
    assert "const generation = ++state.railGeneration" in SCRIPT
    assert SCRIPT.count("generation !== state.railGeneration") >= 6
    assert "closeNavigator: false" in SCRIPT
    assert "row.dataset.matterId = m.matter_id" in SCRIPT
    assert "$('pane-advise').dataset.matterId = matterId" in SCRIPT


def test_the_page_sends_the_header_the_route_reads():
    """BK-31. ONE HEADER NAME, HELD IN TWO FILES, WITH NOTHING REFUSING DRIFT.

    The enrolment route moved from a shared installation code to per-advocate
    invitations and became `x_enrolment_invitation`. `web/app.js` kept sending
    `x-enrolment-code`, so the browser registration form could enrol nobody
    while every server-side test passed -- the failure lived in the gap
    between two correct components, which is CLAUDE.md §8's shape and §4's
    question: what refuses the second copy?

    Nothing did. The element-id scan above compares the page against the
    script and has no view of the Python at all, so this reads the route's
    OWN signature rather than a literal repeated here -- a constant in this
    file would be a third copy of the name and would drift with the other two.
    """
    assert not headers_the_script_never_sends(SCRIPT)


def headers_the_script_never_sends(script: str) -> list[str]:
    """Every x- header the register route reads that `script` does not send.

    A FUNCTION SO THE CONTROL CAN CALL IT ON A MUTATED SCRIPT. Asserted
    inline, the check could only ever be run against the one file that is
    already correct, and a check that cannot be shown to fail is the shape
    this repository refuses everywhere else.
    """
    import inspect

    from nm.edge import api

    parameters = inspect.signature(api.register).parameters
    wire = [name.replace("_", "-") for name in parameters
            if name.startswith("x_")]
    assert wire, (
        "the register route takes no x- header, so either the invitation was "
        "dropped from the door or it moved somewhere this check cannot see")
    return [name for name in wire if name not in script]


def test_the_header_check_catches_the_exact_drift_it_was_written_for():
    """THE POSITIVE CONTROL, on the real bug rather than on a literal.

    The script as it stood on 10 September -- sending `x-enrolment-code` at a
    route reading `x-enrolment-invitation` -- must be reported. Without this
    the assertion above would pass on a script that had simply stopped
    mentioning headers at all.
    """
    stale = SCRIPT.replace("x-enrolment-invitation", "x-enrolment-code")
    assert stale != SCRIPT, (
        "the script no longer sends the invitation header literally, so this "
        "control is mutating nothing")
    assert headers_the_script_never_sends(stale) == ["x-enrolment-invitation"], (
        "the drift that shipped a registration form which could enrol nobody "
        "was not reported")


def invitation_exposure(page: str, script: str) -> list[str]:
    """Report a visible, retained or disconnected invitation value."""
    problems = []
    found = re.search(r'<input\b[^>]*\bid="reg-invitation"[^>]*>', page)
    if (not found or 'type="password"' not in found.group(0)
            or 'name="enrolment_invitation"' not in found.group(0)):
        problems.append("the invitation input is not concealed")
    capture = script.find("const invitation = $('reg-invitation').value.trim()")
    cleared = script.find("$('reg-invitation').value = '';", capture)
    sent = script.find("await api('/api/register'", capture)
    if min(capture, cleared, sent) < 0 or not capture < cleared < sent:
        problems.append("the invitation remains in the DOM during submission")
    header = script.find("'x-enrolment-invitation': invitation", sent)
    if sent < 0 or header < sent:
        problems.append("the captured invitation is not the request header value")
    return problems


def test_the_browser_conceals_and_clears_the_invitation_before_the_wire_wait():
    """BK-31-AC5. A bearer credential must not remain readable on the glass."""
    assert not invitation_exposure(HTML, SCRIPT)


def test_the_invitation_exposure_check_catches_each_failure():
    visible = HTML.replace('id="reg-invitation" name="enrolment_invitation" '
                           'type="password"',
                           'id="reg-invitation" name="enrolment_invitation" '
                           'type="text"')
    capture = SCRIPT.index("const invitation = $('reg-invitation').value.trim()")
    clear = SCRIPT.index("$('reg-invitation').value = '';", capture)
    statement = "$('reg-invitation').value = '';"
    retained = SCRIPT[:clear] + SCRIPT[clear + len(statement):]
    disconnected = SCRIPT.replace(
        "'x-enrolment-invitation': invitation",
        "'x-enrolment-invitation': password")
    assert invitation_exposure(visible, SCRIPT) == [
        "the invitation input is not concealed"]
    assert invitation_exposure(HTML, retained) == [
        "the invitation remains in the DOM during submission"]
    assert invitation_exposure(HTML, disconnected) == [
        "the captured invitation is not the request header value"]


def test_the_register_form_does_not_retype_the_invited_roster_identity():
    """BK-31-AC8. One owner for identity means one place to correct it."""
    retired = ("reg-name", "reg-email", "reg-enrolment", "reg-practice",
               "reg-firm")
    assert not [field for field in retired if field in HTML or field in SCRIPT]
