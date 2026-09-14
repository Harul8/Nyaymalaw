"""THE PAGE HOLDS THE NEW CODES ONCE AND WRITES THEM NOWHERE. BK-31-AC20.

The packet's own words: *reuse one-time code display with a save
acknowledgement; clear secrets on exit/logout, never persist them in browser
storage.* Every clause there is a place a last-resort credential can end up
outliving the screen that showed it.

WHY A STATIC SCAN AND NOT A BROWSER ASSERTION
-----------------------------------------------
A browser test proves the codes are not in storage on the path it drove. This
proves there is no code path that could put them there — which is the question,
because the path nobody drove is the one that leaks. The two are complements
and the browser journey is separate.

`localStorage` survives the tab, the browser restart and the next person on a
shared machine. `sessionStorage` survives a reload. A recovery code in either
is a printed code somebody left on the desk, except that it is also readable by
every script that ever runs on this origin.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "frontend" / "app.js"
PAGE = ROOT / "frontend" / "index.html"

#: What the rotation flow handles that must never be written down.
SECRET_NAMES = ("rotationProof", "recovery_codes", "recoveryCodes",
                "reauth-password", "proof")


def _script() -> str:
    return SCRIPT.read_text(encoding="utf8")


def _without_comments(text: str) -> str:
    """Comments discuss `localStorage` on purpose; code must not use it."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//"))


def test_the_script_never_writes_to_browser_storage_at_all():
    """A BLANKET RULE, not a rule about the rotation flow.

    Scoping it to "secrets" needs a judgement about what is secret at every
    future call site, and that judgement is made once, in a hurry, by whoever
    adds the next feature. Nothing in this product needs to persist anything
    across a tab close: the session is a cookie the server minted and the draft
    is already deliberately in memory only.
    """
    code = _without_comments(_script())
    writes = re.findall(r"(localStorage|sessionStorage)\s*\.\s*(\w+)", code)
    writes += [(store, "[]") for store in
               re.findall(r"(localStorage|sessionStorage)\s*\[", code)]
    assert not writes, (
        "frontend/app.js touches browser storage: "
        + ", ".join(f"{s}.{m}" for s, m in writes)
        + ". A recovery code or session state left there outlives the screen "
          "that showed it and is readable by every later script on this origin.")


def test_the_storage_sweep_can_see_a_planted_write():
    """POSITIVE CONTROL. The blanket rule above passes identically whether it
    is working or has stopped matching -- and a regex that stopped matching
    would report a clean script for a page parking recovery codes in
    `localStorage`, which is the exact failure it exists to prevent."""
    planted = _script().replace(
        "  rotationProof = null;",
        "  localStorage.setItem('nm_proof', rotationProof || '');\n"
        "  rotationProof = null;", 1)
    assert "localStorage.setItem" in planted, "the plant did not apply"

    code = _without_comments(planted)
    writes = re.findall(r"(localStorage|sessionStorage)\s*\.\s*(\w+)", code)
    assert writes, "the sweep cannot see a planted storage write"
    assert ("localStorage", "setItem") in writes

    # And the real script must NOT be flagged, or the sweep is merely strict.
    assert not re.findall(r"(localStorage|sessionStorage)\s*\.\s*(\w+)",
                          _without_comments(_script()))


def test_the_proof_is_a_closure_variable_and_not_a_dom_attribute():
    """`dataset` and hidden inputs are storage too — readable by anything on
    the page and surviving in the DOM until something clears them."""
    code = _without_comments(_script())
    for name in SECRET_NAMES:
        assert f"dataset.{name}" not in code, f"{name} was parked on a DOM node"
    assert "rotationProof = null" in code, (
        "nothing sets the proof back to null, so it survives the exchange")
    assert re.search(r"let rotationProof\b", code), (
        "the proof is not a module-scope variable this file can reason about")


def test_the_proof_is_dropped_whether_the_rotation_succeeded_or_failed():
    """A failed rotation must not leave a usable authorisation in the tab.

    The `finally` is the point: an exception between earning the proof and
    spending it is exactly when a variable gets left behind.
    """
    code = _script()
    flow = code[code.index("$('reauth-form').addEventListener"):]
    flow = flow[:flow.index("$('outcome-resume')")]
    assert "finally" in flow, "the rotation has no finally clause"
    tail = flow[flow.index("finally"):]
    assert "rotationProof = null" in tail, (
        "the proof is not cleared in the finally clause, so a thrown error "
        "leaves it spendable")


def test_leaving_the_one_time_screen_removes_the_codes_from_the_document():
    """Hiding the card leaves the codes in the DOM. The acknowledgement has to
    empty it, which is what the registration flow already does."""
    code = _script()
    resume = code[code.index("$('outcome-resume').addEventListener"):]
    resume = resume[:resume.index("\n});") + 4]
    assert "clearRecoveryCodeDisplay()" in resume, (
        "the acknowledgement hides the codes without removing them")
    assert "forgetRotationSecrets()" in resume


def test_the_password_field_is_cleared_on_every_exit_from_the_card():
    """A hidden card keeps its values. The next person on this machine must not
    return to a form already carrying the credential."""
    code = _script()
    show_form = code[code.index("function showForm("):]
    show_form = show_form[:show_form.index("\n}\n")]
    # THE SPECIFIC STATEMENT, not two substrings that happen to co-occur. The
    # first version asserted `"reauth-password" in show_form and "value = ''"
    # in show_form` -- and `showForm` clears the invitation field with
    # `invitation.value = ''` a few lines above, so deleting the password clear
    # entirely left both substrings present and the test green. A mutation run
    # is the only reason that was found.
    cleared = re.search(
        r"\$\('reauth-password'\)[^;]*;\s*if \(field\) field\.value = '';",
        show_form)
    assert cleared, (
        "showForm does not clear the reauthentication password field; a hidden "
        "card keeps its values and the next person returns to a filled form")


def test_a_generation_the_server_cannot_state_stops_the_rotation():
    """§9 on the surface, and it had no test at all until a mutation run said so.

    `null` from `/api/session` means the directory could not say which set is
    current. A client reading that as 0 would send 0 as its expectation, and a
    legacy account genuinely on 0 would accept it -- so an unreadable record
    would authorise the very replacement it cannot verify.
    """
    code = _script()
    flow = code[code.index("$('reauth-form').addEventListener"):]
    flow = flow[:flow.index("$('outcome-resume')")]
    assert "recovery_generation === null" in flow, (
        "the page does not check for an unstateable generation")
    assert "undefined" in flow, "an absent field is not distinguished from null"
    guard = flow[flow.index("recovery_generation === null"):]
    assert "throw" in guard[:400], (
        "the null check does not stop the rotation, so it is a comment with an "
        "`if` in front of it")


def test_the_acknowledgement_exists_and_says_what_it_acknowledges():
    """*I saved them* is the whole point of a one-time display. A button
    labelled Continue asks the advocate to agree to nothing."""
    page = PAGE.read_text(encoding="utf8")
    assert 'id="outcome-resume"' in page
    match = re.search(r'id="outcome-resume"[^>]*>([^<]+)<', page)
    assert match and "saved" in match.group(1).lower(), (
        f"the acknowledgement reads {match.group(1) if match else None!r}, "
        f"which does not acknowledge saving anything")


def test_every_id_the_rotation_script_touches_exists_on_the_page():
    """The rename trap, on the surface where it is invisible until a browser
    hits it. `frontend/index.html` and `frontend/app.js` are two files that have to agree
    and nothing in a Python test suite would otherwise notice."""
    page = PAGE.read_text(encoding="utf8")
    code = _script()
    touched = set(re.findall(r"\$\('([a-z0-9-]+)'\)", code))
    rotation = {i for i in touched
                if i.startswith(("reauth", "outcome-resume", "replace-codes"))}
    assert rotation, "the scan found no rotation ids, so it checked nothing"
    missing = sorted(i for i in rotation if f'id="{i}"' not in page)
    assert not missing, f"frontend/app.js addresses ids the page does not define: {missing}"
