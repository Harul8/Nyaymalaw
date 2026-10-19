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

from nm.arrive.advocate_contracts import PRIVACY_NOTICE_VERSION

pytestmark = pytest.mark.class_a

WEB = pathlib.Path(__file__).resolve().parents[1] / "nm"
HTML = (WEB / "app/index.html").read_text(encoding="utf-8")
SCRIPT = (WEB / "app/app.js").read_text(encoding="utf-8")

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
STYLE = re.sub(r"/\*.*?\*/", "", (WEB / "app/app.css").read_text(encoding="utf-8"),
               flags=re.S)


def _z_index(selector: str, style: str = STYLE) -> int:
    """The LAST explicit z-index declaration for this exact selector.

    Read from the text rather than from a browser, so it runs in the class-A
    cadence. That is a real limit -- a cascade this cannot see could still
    bury the banner -- and it catches the case that actually happened.
    """
    blocks = re.findall(r'(?:^|[{}])\s*' + re.escape(selector) + r'\s*\{([^{}]*)\}',
                        style, flags=re.M)
    declarations = [found.group(1) for block in blocks
                    if (found := re.search(r'z-index:\s*(-?\d+)', block))]
    assert declarations, f"{selector} declares no z-index"
    return int(declarations[-1])


def test_stacking_check_preserves_inherited_value_and_catches_real_overrides():
    base = '#gate {z-index:100;} @media(max-width:600px) { #gate {gap:1rem;} }'
    assert _z_index('#gate', base) == 100
    assert _z_index('#gate', base + '#gate {z-index:300;}') == 300
    with pytest.raises(AssertionError):
        _z_index('#gate', '#gate {gap:1rem;}')


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


def registration_surface_problems(page: str, script: str) -> list[str]:
    """D-041: a connected public account form, never a credential grant."""
    problems = []
    form = re.search(r'<form\b[^>]*\bid="register"[^>]*>(.*?)</form>', page, re.S)
    controls = re.findall(r'<(?:input|select|textarea)\b[^>]*>',
                          form.group(1) if form else "")
    fields = [match.group(1) for control in controls
              if (match := re.search(r'\bid="([^"]+)"', control))]
    if len(controls) != 6 or sorted(fields) != [
            "reg-adult", "reg-consent", "reg-email", "reg-external-ai",
            "reg-password", "reg-password2"]:
        problems.append("registration does not have exactly the three account inputs "
                        "and two required notices plus separate optional AI permission")
    email = re.search(r'<input\b[^>]*\bid="reg-email"[^>]*>', page)
    if not email or 'type="email"' not in email.group(0):
        problems.append("the email input is absent or mistyped")
    # F-A-09: both boxes start unticked, and the notice the card shows is the
    # version the server records the consent against.
    for box in ("reg-consent", "reg-adult", "reg-external-ai"):
        tag = re.search(rf'<input\b[^>]*\bid="{box}"[^>]*>', page)
        if not tag or 'type="checkbox"' not in tag.group(0) \
                or re.search(r"\schecked\b", tag.group(0)):
            problems.append(f"{box} is not an unticked box")
        if tag:
            required = bool(re.search(r"\srequired\b", tag.group(0)))
            if required != (box != "reg-external-ai"):
                problems.append(f"{box} has the wrong required/optional boundary")
    notice = re.search(r'<section\b[^>]*\bid="privacy-notice"[^>]*'
                       r'\bdata-notice-version="([^"]+)"', page)
    if not notice or notice.group(1) != PRIVACY_NOTICE_VERSION:
        problems.append("the register card's privacy notice is not the version the server records")
    start = script.find("$('register').addEventListener('submit'")
    capture = script.find("const email = $('reg-email').value.trim()", start)
    cleared = script.find("clearRegistrationPasswords();", capture)
    sent = script.find("await api('/api/register'", capture)
    if min(start, capture, cleared, sent) < 0 or not start < capture < cleared < sent:
        problems.append("registration secrets are retained or email is disconnected")
    end = script.find("// THE REVEAL.", sent)
    request = script[sent:end] if sent >= 0 and end > sent else ""
    for field in ("email: email", "password: password", "password_again: again",
                  "consent: consentGiven()"):
        if field not in request:
            problems.append(f"request missing {field}")
    if "x-enrolment-" in request or "reg-invitation" in page:
        problems.append("the public form still requires an invitation")
    forbidden = ("reg-name", "reg-enrolment", "reg-practice", "reg-firm")
    if any(field in page or field in script for field in forbidden):
        problems.append("the public form claims a professional or firm identity")
    return problems


def test_public_registration_sends_email_without_invitation_or_profile_claims():
    assert not registration_surface_problems(HTML, SCRIPT)


def test_registration_surface_control_catches_each_failure():
    mutations = [
        (HTML.replace('type="email"', 'type="text"'), SCRIPT),
        (HTML, SCRIPT.replace("email: email", "username: email")),
        (HTML, SCRIPT.replace("clearRegistrationPasswords();", "/* retained */")),
        (HTML, SCRIPT.replace("email: email", "'x-enrolment-code': email")),
        (HTML + '<input id="reg-firm">', SCRIPT),
        (HTML.replace('<label for="reg-email">',
                      '<input id="reg-approved"><label for="reg-email">'), SCRIPT),
        (HTML.replace('<label for="reg-email">',
                      '<input name="professional_approval"><label for="reg-email">'), SCRIPT),
        (HTML.replace('id="reg-consent" name="consent" required',
                      'id="reg-consent" name="consent" required checked'), SCRIPT),
        (HTML.replace(f'data-notice-version="{PRIVACY_NOTICE_VERSION}"',
                      'data-notice-version="2020-01-01"'), SCRIPT),
        (HTML, SCRIPT.replace("consent: consentGiven(),", "")),
        (HTML.replace('id="reg-external-ai" name="external_ai"',
                      'id="reg-external-ai" name="external_ai" checked'), SCRIPT),
        (HTML.replace('id="reg-external-ai" name="external_ai"',
                      'id="reg-external-ai" name="external_ai" required'), SCRIPT),
        (HTML.replace('id="reg-consent" name="consent" required',
                      'id="reg-consent" name="consent"'), SCRIPT),
        (HTML.replace('id="reg-adult" name="adult" required',
                      'id="reg-adult" name="adult"'), SCRIPT),
    ]
    assert len(mutations) == 14
    for page, script in mutations:
        assert (page, script) != (HTML, SCRIPT), "control mutated nothing"
        assert registration_surface_problems(page, script)


