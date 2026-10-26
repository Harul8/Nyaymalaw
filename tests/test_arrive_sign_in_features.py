"""Phase A -- Arrive, as the product owner described it.

The `.feature` files under `tests/features/arrive/` are GENERATED from the column
"Scenarios (Given / When / Then)" of the Implementation Plan's Arrive rows, which state
each row's Must do and Must never so they can be read against the product owner's words
in column C. This module binds every step to the real page (`nm/app/index.html`,
`nm/app/app.js`, `nm/app/app.css`) and to the served routes through the shared
`client` fixture.

ONE RULE, ONE OWNER. Where a rule already has a checker elsewhere in the suite --
the whole-product recovery-code sweep, the reset-link reader, the page contract --
the step calls that checker rather than restating it, so the plain-English scenario
and the invariant test cannot drift apart.

WHAT THE PAGE STEPS DO NOT DO. They read the bytes of the page, the script and the
stylesheet; they do not run a browser. A screenshot at each width, and watching the
idle warning and sign-out happen, need a real browser and are recorded in the plan as
not yet run.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

import tests.test_the_page_and_the_script_agree as page_contract
from nm.arrive.advocate_contracts import (
    PASSWORD_RESET_MINUTES,
    PRIVACY_NOTICE_VERSION,
    SESSION_HOURS,
    SESSION_IDLE_MINUTES,
    AdvocateIdentity,
    Enrolment,
    enrol,
    utcnow,
)
from nm.arrive.store_directory import RETIRED_RECOVERY_FIELDS
from tests.registration import CONSENT
from tests.test_account_access_and_workspace import (
    _frontend,
    _product_sources,
    _served_paths,
    recovery_code_sites,
)
from tests.test_password_reset_by_email import reset_link_for

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "Cinder-lantern-42"
NEW_PASSWORD = "Harbour-meadow-17!"
OTHER_PASSWORD = "Quarry-willow-55!"
MISMATCH = "Different-pass-99!"
EYE = "\U0001F441"

scenarios("features/arrive")
# B. Open a matter and C. Take the brief share this module's steps for the page,
# script and stylesheet.
scenarios("features/open_a_matter")
scenarios("features/take_the_brief")


@pytest.fixture
def context() -> dict:
    """What one scenario's steps hand to each other."""
    return {}


# ================================ the page ===================================

#: Each card on the right of the sign-in page, by the name the scenarios use.
CARDS = {
    "sign-in": ('<form id="login"', "</form>"),
    "register": ('<form id="register"', "</form>"),
    "forgot-password": ('<form id="forgot"', "</form>"),
    "set-new-password": ('<form id="reset"', "</form>"),
    "result": ('<section id="outcome"', "</section>"),
}


def card_html(page: str, name: str) -> str:
    start, end = CARDS[name]
    at = page.find(start)
    assert at >= 0, f"the {name} card is not on the page"
    return page[at:page.index(end, at) + len(end)]


def visible_text(fragment: str) -> str:
    """The words a person sees: no comments, no tags, entities decoded."""
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(html.unescape(fragment).split())


def gate_html(page: str) -> str:
    return page[page.index('<div id="gate">'):page.index('<header class="masthead"')]


def _script() -> str:
    return (ROOT / "nm/app/app.js").read_text(encoding="utf8")


def _function(script: str, name: str) -> str:
    """One top-level function of the page script, from its declaration to its end."""
    at = script.find(f"function {name}(")
    assert at >= 0, f"{name} is not in the page script"
    return script[at:script.index("\n}\n", at)]


@given("the sign-in page", target_fixture="sign_in_page")
def the_sign_in_page() -> str:
    return (ROOT / "nm/app/index.html").read_text(encoding="utf8")


@given("the page script", target_fixture="page_script")
def the_page_script() -> str:
    return _script()


@given("the page stylesheet", target_fixture="stylesheet")
def the_page_stylesheet() -> str:
    """Comments stripped: a value inside a comment is not a declaration."""
    return re.sub(r"/\*.*?\*/", "", (ROOT / "nm/app/app.css").read_text(encoding="utf8"),
                  flags=re.S)


# ---------------------------------------------------------------- F-A-01 ---

@then(parsers.parse('the sign-in card shows "{title}" and "{lede}"'))
def sign_in_card_shows(sign_in_page, title, lede):
    text = visible_text(card_html(sign_in_page, "sign-in"))
    assert title in text and lede in text, text


@then("the sign-in card has an email field, a password field and a Sign in button")
def sign_in_card_controls(sign_in_page):
    controls = re.findall(r'<(?:input|button)\b[^>]*\bid="([^"]+)"',
                          card_html(sign_in_page, "sign-in"))
    assert controls == ["login-id", "login-password", "login-go"], controls


#: Everything the sign-in card may say, in order, and nothing more. The show-password
#: eye (F-A-10) is a glyph, not words, and is set aside.
SIGN_IN_WORDS = ["Welcome back.", "Sign in to your practice workspace.",
                 "Email or advocate ID", "Password", "Sign in",
                 "Forgot password", "Register"]


@then("the sign-in card carries no logo and no text below its links")
def sign_in_card_is_bare(sign_in_page):
    login = card_html(sign_in_page, "sign-in")
    assert 'class="mark"' not in login and "login-brand" not in login
    assert "login-foot" not in login
    words = " ".join(visible_text(login).replace(EYE, " ").split())
    assert words == " ".join(SIGN_IN_WORDS), words


@then("directly under the Sign in button there is one row as wide as the button")
def one_row_under_sign_in(sign_in_page, context):
    login = card_html(sign_in_page, "sign-in")
    after = login[login.index('id="login-go"'):]
    after = after[after.index("</button>") + len("</button>"):]
    after = re.sub(r"<!--.*?-->", "", after, flags=re.S).lstrip()
    assert after.startswith('<div class="login-alt login-alt-split">'), after[:120]
    context["row"] = after[:after.index("</div>")]
    style = re.sub(r"/\*.*?\*/", "", (ROOT / "nm/app/app.css").read_text(encoding="utf8"),
                   flags=re.S)
    rule_ = re.search(r"\.login-alt-split\s*\{([^}]*)\}", style)
    assert rule_ and "display: flex" in rule_.group(1) \
        and "justify-content: space-between" in rule_.group(1), (
            "the row is not laid out edge to edge under the button")


@then("the row shows Forgot password on the left and Register on the right")
def forgot_left_register_right(context):
    links = re.findall(r"<a\b[^>]*>([^<]+)</a>", context["row"])
    assert links == ["Forgot password", "Register"], links


# ================================ the served routes ==========================

def _register(client, email, password=PASSWORD, again=None, consent=CONSENT):
    """What the register card sends; `consent=None` sends no consent at all."""
    body = {"email": email, "password": password,
            "password_again": password if again is None else again}
    if consent is not None:
        body["consent"] = consent
    from tests.registration import confirm_registered
    return confirm_registered(client, client.post("/api/register", json=body))


def _login(client, email, password):
    """From a browser that holds no session, exactly as a stranger would."""
    return TestClient(client.app).post(
        "/api/login", json={"advocate_id": email, "password": password})


def _reset(client, token, password, again=None):
    return client.post("/api/password/reset", json={
        "token": token, "password": password,
        "password_again": password if again is None else again})


def _registered(client, context, email):
    response = _register(client, email)
    assert response.status_code == 200, response.text
    context["email"] = email


@given(parsers.parse('a registered advocate "{email}"'))
def a_registered_advocate(client, context, email):
    _registered(client, context, email)


@when("they sign in with the right password")
def sign_in_right_password(client, context):
    context["response"] = _login(client, context["email"], PASSWORD)


@then("sign-in succeeds")
def sign_in_succeeds(context):
    assert context["response"].status_code == 200, context["response"].text


@then("their own private workspace is named")
def own_workspace_named(context):
    workspace = context["response"].json()["workspace"]
    assert workspace["id"] == f"advocate:{context['email']}", workspace
    assert workspace["label"].strip(), "the workspace has no name to show"


@when(parsers.parse('someone signs in as "{email}" with a wrong password'))
def sign_in_wrong_password(client, context, email):
    context.setdefault("refusals", []).append(_login(client, email, "Wrong-password-9!"))


@when(parsers.parse('someone signs in as "{email}" with any password'))
def sign_in_unknown_account(client, context, email):
    context.setdefault("refusals", []).append(_login(client, email, "Any-password-9!"))


@then("both are refused with exactly the same message")
def refusals_identical(context):
    first, second = context["refusals"]
    assert first.status_code == second.status_code == 401
    assert first.json() == second.json()


# ---------------------------------------------------------------- F-A-02 ---

@then("the register card has exactly an email field, a password field, a retype-password "
      "field, two required privacy boxes and one optional OpenAI permission box")
def register_card_inputs(sign_in_page):
    inputs = re.findall(r'<input\b[^>]*\bid="([^"]+)"', card_html(sign_in_page, "register"))
    assert inputs == ["reg-email", "reg-password", "reg-password2",
                      "reg-consent", "reg-adult", "reg-external-ai"], inputs
    card = card_html(sign_in_page, "register")
    for name in ("reg-consent", "reg-adult", "reg-external-ai"):
        tag = re.search(rf'<input\b[^>]*\bid="{name}"[^>]*>', card).group(0)
        assert not re.search(r"\schecked\b", tag)
        assert bool(re.search(r"\srequired\b", tag)) == (name != "reg-external-ai")


#: The registration's steps as the signed-off design draws them (owner decision O24; plan AN.15).
STEPS = ("Account", "Privacy and AI permission", "Confirm your email")


def register_steps(page: str) -> tuple[str, str]:
    """The register card's account step and its privacy step."""
    register = card_html(page, "register")
    first = register.index('<section class="reg-step" data-step="1"')
    second = register.index('<section class="reg-step" data-step="2"')
    return register[first:second], register[second:]


@then("the register card shows its steps: the account, then privacy and AI permission, then "
      "confirming the email")
def register_card_steps(sign_in_page):
    register = card_html(sign_in_page, "register")
    marks = re.findall(r'<li data-step="(\d)"[^>]*>.*?<b>([^<]+)</b>', register, re.S)
    assert marks == [("1", STEPS[0]), ("2", STEPS[1]), ("3", STEPS[2])], marks
    assert '<li data-step="1" aria-current="step">' in register
    assert re.findall(r'<section class="reg-step" data-step="(\d)"', register) == ["1", "2"]
    account, privacy = register_steps(sign_in_page)
    for name in ("reg-email", "reg-password", "reg-password2"):
        assert f'id="{name}"' in account, name
    for name in ("reg-consent", "reg-adult", "reg-external-ai"):
        assert f'id="{name}"' in privacy, name
    assert re.search(r'<section class="reg-step" data-step="2"[^>]*\shidden\b', register), (
        "the privacy step waits for the account step")
    confirm = sign_in_page[sign_in_page.index('<form id="confirm-email"'):]
    confirm = confirm[:confirm.index("</form>")]
    assert '<li data-step="3" aria-current="step">' in confirm, "the code is the third step"


@then("the account step has a Continue button and the privacy step a Back button and a Create "
      "account button")
def register_card_step_actions(sign_in_page):
    account, privacy = register_steps(sign_in_page)
    assert re.search(r'<button type="button"[^>]*id="reg-continue">\s*Continue\s*</button>', account)
    assert re.search(r'<button type="button" id="reg-back">\s*Back\s*</button>', privacy)
    assert re.search(r'<button type="submit"[^>]*id="register-go">\s*Create account\s*</button>', privacy)


@then("the register card has a Back to sign in link")
def register_card_back_link(sign_in_page):
    register = card_html(sign_in_page, "register")
    assert re.search(r'<a\b[^>]*id="show-login"[^>]*>\s*Back to sign in\s*</a>', register)


RULES = ("The password must be at least 8 characters and contain an upper-case letter, "
         "a lower-case letter, a numeral and a special character.")


@then("the register card states the password rules")
def register_card_rules(sign_in_page):
    account, _ = register_steps(sign_in_page)
    assert RULES in visible_text(account), "the rules are stated where the password is chosen"


@then("the register card carries no logo and only the words of its steps")
def register_card_is_bare(sign_in_page):
    register = card_html(sign_in_page, "register")
    for forbidden in ('class="mark"', "login-brand", "login-lede", "field-help"):
        assert forbidden not in register, forbidden
    # The notice and its boxes are F-A-09's and are checked there.
    register = re.sub(r'<section class="privacy-notice".*?</section>', " ", register, flags=re.S)
    register = re.sub(r'<label class="consent".*?</label>', " ", register, flags=re.S)
    remainder = visible_text(register)
    # Longer words first, so a shorter one is never taken out of a longer one.
    for piece in ("Email and password", "Privacy and AI permission", "What we keep, and what you allow",
                  "Confirm your email", "A six-digit code", "Account",
                  "Checking registration availability…", "Step 1 of 3", "Step 2 of 3",
                  "Create your account", "Your privacy, and your permission for AI",
                  "It becomes your sign-in name, and we send a six-digit code to it.", RULES,
                  "required.", "Retype password", "Password", "Email", "Continue", "Create account",
                  "Back to sign in", "Back", "Already have a confirmation code?", "1", "2", "3"):
        assert piece in remainder, f"{piece!r} is missing from the register card"
        remainder = remainder.replace(piece, " ", 1)
    leftover = remainder.replace("*", " ").replace(EYE, " ").split()
    assert not leftover, f"the register card says more than its steps: {leftover}"


@when(parsers.parse('a visitor registers "{email}" with a valid password typed twice'))
def register_valid(client, context, email):
    context["email"] = email
    context["response"] = _register(client, email)


@when(parsers.parse('a visitor registers "{email}" with two different passwords'))
def register_mismatch(client, context, email):
    context["response"] = _register(client, email, PASSWORD, MISMATCH)


@when(parsers.parse('a visitor registers "{email}" with the password "{password}"'))
def register_weak(client, context, email, password):
    context["response"] = _register(client, email, password)


@when(parsers.parse('a visitor registers "{email}" again with a different password'))
def register_again(client, context, email):
    context['response'] = client.post('/api/register', json={
        'email': email, 'password': OTHER_PASSWORD, 'password_again': OTHER_PASSWORD,
        'consent': CONSENT})


@then("the account is created")
def account_created(context):
    assert context["response"].status_code == 200, context["response"].text


@then("the response carries no recovery code or any other secret")
def response_has_no_secret(context):
    response = context["response"]
    assert set(response.json()) == {'state', 'advocate_id', 'detail'}, response.json()
    assert response.json()['state'] == 'confirmed'
    assert PASSWORD not in response.text


@then("they can sign in with that email and password")
def new_account_signs_in(client, context):
    assert _login(client, context["email"], PASSWORD).status_code == 200


@then(parsers.parse('registration is refused with "{words}"'))
def registration_refused_with(context, words):
    response = context["response"]
    assert response.status_code == 400 and words in response.json()["detail"], response.text


@then("registration is refused naming the password rule")
def registration_refused_rule(context):
    response = context["response"]
    assert response.status_code == 400, response.text
    assert "password" in response.json()["detail"].lower()


@then(parsers.parse('no account exists for "{email}"'))
def no_account(client, email):
    assert client.directory.identity(email) is None


@then("the response does not say whether the account exists")
def duplicate_refused_neutrally(context):
    response = context["response"]
    assert response.status_code == 202, response.text
    detail = response.json()["detail"].lower()
    assert context['email'] not in detail and 'if this address is eligible' in detail


@then("the original password still signs in")
def original_password_signs_in(client, context):
    assert _login(client, context["email"], PASSWORD).status_code == 200


# ---------------------------------------------------------------- F-A-03 ---

@given(parsers.parse('a registered advocate "{email}" signed in on two devices'))
def registered_on_two_devices(client, context, email):
    _registered(client, context, email)
    context["devices"] = [client.sign_in(email, password=PASSWORD, fresh=True)
                          for _ in range(2)]


@given(parsers.parse('a reset link was sent to "{email}"'))
def reset_link_was_sent(client, context, email):
    assert client.post("/api/password/forgot", json={"email": email}).status_code == 202
    _, context["token"] = reset_link_for(client, email)


@when(parsers.parse('someone asks for a reset link for "{email}"'))
def ask_for_reset_link(client, context, email):
    context.setdefault("asked", []).append(email)
    context.setdefault("answers", []).append(
        client.post("/api/password/forgot", json={"email": email}))


@then("both get exactly the same answer")
def same_answer(context):
    first, second = context["answers"]
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()


@then("a reset email is queued only for the registered account")
def email_only_for_registered(client, context):
    for address in context["asked"]:
        expected = 1 if address == context["email"] else 0
        messages = [m for m in client.outbox.messages_for(address)
                    if m['purpose'] == 'password-reset']
        assert len(messages) == expected, address


@when("the link is used to set a new valid password")
def use_link(client, context):
    context["response"] = _reset(client, context["token"], NEW_PASSWORD)


@then("the password is changed and both earlier sessions are signed out")
def password_changed_sessions_ended(context):
    response = context["response"]
    assert response.status_code == 200, response.text
    assert response.json() == {"reset": True, "sessions_ended": 2}
    for device in context["devices"]:
        assert device.get("/api/session").status_code == 401


@then("the old password no longer signs in")
def old_password_refused(client, context):
    assert _login(client, context["email"], PASSWORD).status_code == 401


@then("the new password signs in")
def new_password_signs_in(client, context):
    assert _login(client, context["email"], NEW_PASSWORD).status_code == 200


@then("using the same link again changes nothing")
def link_is_single_use(client, context):
    assert _reset(client, context["token"], OTHER_PASSWORD).status_code == 400
    assert _login(client, context["email"], OTHER_PASSWORD).status_code == 401
    assert _login(client, context["email"], NEW_PASSWORD).status_code == 200


@when("the link is used 31 minutes later")
def use_link_late(client, context, monkeypatch):
    from nm.app import api

    minutes = PASSWORD_RESET_MINUTES + 1
    assert minutes == 31, "the scenario's wording no longer matches the link lifetime"
    later = utcnow() + timedelta(minutes=minutes)
    monkeypatch.setattr(api, "utcnow", lambda: later)
    context["response"] = _reset(client, context["token"], NEW_PASSWORD)


@then("it is refused as not valid or expired")
def refused_as_expired(context):
    response = context["response"]
    assert response.status_code == 400, response.text
    assert "not valid or has expired" in response.json()["detail"]


@when("the link is used with two different new passwords")
def use_link_mismatch(client, context):
    context["response"] = _reset(client, context["token"], NEW_PASSWORD, MISMATCH)


@then(parsers.parse('it is refused with "{words}"'))
def refused_with(context, words):
    response = context["response"]
    assert response.status_code == 400 and words in response.json()["detail"], response.text


@then("the link still works afterwards")
def link_still_works(client, context):
    assert _reset(client, context["token"], NEW_PASSWORD).status_code == 200


@then("neither the link nor the new password appears readable in any stored file")
def nothing_readable_at_rest(client, context):
    assert context["response"].status_code == 200, context["response"].text
    scanned = 0
    for path in client.directory._root.rglob("*"):
        if path.is_file():
            scanned += 1
            raw = path.read_bytes()
            assert context["token"].encode() not in raw, path
            assert NEW_PASSWORD.encode() not in raw, path
    assert scanned >= 4, "the scan read almost nothing and would pass anything"


# ---------------------------------------------------------------- F-A-04 ---

@when("the served routes, the backend code, the page and the script are searched",
      target_fixture="recovery_sites")
def search_for_recovery_codes():
    page, script = _frontend()
    return recovery_code_sites(_product_sources(), page, script, _served_paths())


@then("no recovery code is found anywhere")
def no_recovery_code_anywhere(recovery_sites):
    assert recovery_sites == [], recovery_sites


@then('there is no "Use a recovery code" link and no recovery-code form')
def no_recovery_option(sign_in_page):
    assert not re.search(r"recovery[ _-]?code", sign_in_page, re.I)
    assert 'id="recovery"' not in sign_in_page


@given("an older account that still holds recovery-code data")
def older_account_with_codes(client, context):
    email = "legacy@chambers.in"
    client.sign_in(email, password=PASSWORD, fresh=True)
    path = client.directory._advocates / f"{email}.nm"
    record = json.loads(path.read_text(encoding="utf8"))
    record["recovery_codes"] = [{"id": "a", "salt": "b", "hash": "c", "used_at": None}]
    record["recovery_codes_issued_at"] = utcnow().isoformat()
    record["recovery_generation"] = 4
    path.write_text(json.dumps(record, indent=2), encoding="utf8")
    context.update(email=email, record=path,
                   generation=record["credential_generation"])


@when("it signs in with its password")
def older_account_signs_in(client, context):
    context["response"] = _login(client, context["email"], PASSWORD)


@then("the recovery-code data is gone from its record")
def recovery_data_gone(context):
    assert context["response"].status_code == 200, context["response"].text
    record = json.loads(context["record"].read_text(encoding="utf8"))
    assert not set(RETIRED_RECOVERY_FIELDS) & set(record), sorted(record)


@then("its password is unchanged")
def password_unchanged(client, context):
    record = json.loads(context["record"].read_text(encoding="utf8"))
    assert record["credential_generation"] == context["generation"]
    assert _login(client, context["email"], PASSWORD).status_code == 200


# ---------------------------------------------------------------- F-A-05 ---

@then("the logo appears exactly once")
def logo_once(sign_in_page):
    assert gate_html(sign_in_page).count('class="mark"') == 1


@then("it is on the left panel")
def logo_on_left(sign_in_page):
    gate = gate_html(sign_in_page)
    left = gate[gate.index('<aside class="arrival-story"'):gate.index("</aside>")]
    assert 'class="mark"' in left


@then(parsers.parse("the {card} card carries no logo"))
def card_has_no_logo(sign_in_page, card):
    fragment = card_html(sign_in_page, card)
    assert 'class="mark"' not in fragment and "login-brand" not in fragment, card


# ---------------------------------------------------------------- F-A-08 ---

@then(parsers.parse('the sign-in field is labelled "{label}" and does not insist on an '
                    'email address'))
def sign_in_field_takes_either(sign_in_page, label):
    login = card_html(sign_in_page, "sign-in")
    assert re.search(rf'<label\b[^>]*for="login-id"[^>]*>\s*{re.escape(label)}\s*</label>',
                     login), login
    field = re.search(r'<input\b[^>]*\bid="login-id"[^>]*>', login).group(0)
    assert 'type="email"' not in field, field


@given(parsers.parse('an existing account with the advocate ID "{advocate_id}"'))
def account_with_advocate_id(client, context, advocate_id):
    client.directory.enrol(Enrolment(
        identity=AdvocateIdentity(id=advocate_id, name=f"Advocate {advocate_id}"),
        credential=enrol(PASSWORD)))
    context["email"] = advocate_id


@when("they sign in with that advocate ID and the right password")
def sign_in_with_advocate_id(client, context):
    context["response"] = _login(client, context["email"], PASSWORD)


@when(parsers.parse('a visitor tries to register with "{name}" instead of an email address'))
def register_with_a_name(client, context, name):
    context["response"] = _register(client, name)


@then("registration is refused asking for an email address")
def refused_for_email(context):
    response = context["response"]
    assert response.status_code == 422, response.text
    assert "email address" in response.json()["detail"], response.text


# ---------------------------------------------------------------- F-A-09 ---

def notice_text(page: str) -> str:
    register = card_html(page, "register")
    at = register.find('<section class="privacy-notice"')
    assert at >= 0, "the privacy notice is not on the register card"
    return visible_text(register[at:register.index("</section>", at)])


@then("the register card's notice names each detail kept and what it is for")
def notice_names_details(sign_in_page):
    text = notice_text(sign_in_page)
    assert "to create your account, sign you in and keep the account secure, and for " \
        "nothing else" in text, text
    for detail, purpose in (("Your email address", "your sign-in name"),
                            ("Your email address", "password-reset links are sent"),
                            ("Your password", "cannot be read back"),
                            ("Your sign-ins", "network address")):
        assert detail in text and purpose in text, (detail, purpose)


@then("the notice says how to withdraw consent, how to see, correct or erase the details, "
      "and how to complain to the Data Protection Board of India")
def notice_names_rights(sign_in_page):
    text = notice_text(sign_in_page)
    for words in ("withdraw this consent at any time", "see, correct or erase your details",
                  "raise a grievance", "complain to the Data Protection Board of India"):
        assert words in text, words


@then("the notice names Nyaymalaw, through Rahul Lambade, Founder & CEO, and the contact "
      "haaruln@gmail.com")
def notice_names_fiduciary(sign_in_page):
    text = notice_text(sign_in_page)
    assert "Nyaymalaw is responsible for these details, through Rahul Lambade, Founder & CEO" \
        in text, text
    assert 'href="mailto:haaruln@gmail.com"' in card_html(sign_in_page, "register")


@then("the consent box and the 18-or-older box start unticked")
def boxes_start_unticked(sign_in_page):
    problems = page_contract.registration_surface_problems(sign_in_page, _script())
    assert not [p for p in problems if "unticked box" in p], problems


@then("the Create account button stays unavailable until both boxes are ticked")
def register_waits_for_boxes():
    script = _script()
    ready = _function(script, 'syncRegisterReady')
    assert "$('register-go').disabled = !(registrationCapabilities?.public_registration" in ready
    assert "&& $('reg-consent').checked && $('reg-adult').checked);" in ready
    assert "['reg-consent', 'reg-adult'].forEach((id) => $(id).addEventListener('change', " \
        "syncRegisterReady));" in script
    assert "\nsyncRegisterReady();\n" in script, "Register is not set before a box is ticked"
    handler = script[script.index("$('register').addEventListener('submit'"):
                     script.index("// THE REVEAL.")]
    assert "go.disabled = false" not in handler, "Register is re-enabled without the boxes"
    assert "syncRegisterReady();" in handler


@then("the registration sends both boxes and the notice version the page shows")
def registration_sends_consent(sign_in_page):
    script = _script()
    problems = page_contract.registration_surface_problems(sign_in_page, script)
    assert "request missing consent: consentGiven()" not in problems, problems
    given_ = _function(script, "consentGiven")
    for part in ("$('privacy-notice').dataset.noticeVersion", "$('reg-consent').checked",
                 "$('reg-adult').checked"):
        assert part in given_, part


@then("the notice version on the page is the one the server records")
def notice_version_agrees(sign_in_page):
    problems = page_contract.registration_surface_problems(sign_in_page, _script())
    assert not [p for p in problems if "privacy notice" in p], problems
    assert f'data-notice-version="{PRIVACY_NOTICE_VERSION}"' in sign_in_page


#: The ways a registration can arrive without full consent, by the scenario's words.
CONSENT_GAPS = {
    "without agreeing to the privacy notice": {**CONSENT, "agreed": False},
    "without confirming they are 18 or older": {**CONSENT, "adult": False},
    "agreeing to an older version of the notice": {**CONSENT, "notice_version": "2020-01-01"},
    "sending no consent at all": None,
}


@when(parsers.re(r'a visitor registers "(?P<email>[^"]+)" (?P<gap>'
                 + "|".join(re.escape(gap) for gap in CONSENT_GAPS) + r")"))
def register_without_full_consent(client, context, email, gap):
    context["response"] = _register(client, email, consent=CONSENT_GAPS[gap])


@then("registration is refused and nothing was saved")
def refused_nothing_saved(context):
    response = context["response"]
    assert response.status_code == 422, response.text
    assert "Nothing was saved" in response.json()["detail"], response.text


@then("the account record holds the notice version, the time of consent and the "
      "18-or-older confirmation")
def consent_recorded(client, context):
    assert context["response"].status_code == 200, context["response"].text
    record = json.loads(
        client.directory._advocate_path(context["email"]).read_text(encoding="utf8"))
    consent = record["consent"]
    assert consent["notice_version"] == PRIVACY_NOTICE_VERSION, consent
    assert consent["adult_confirmed"] is True, consent
    given_at = datetime.fromisoformat(consent["given_at"])
    assert abs(utcnow() - given_at) < timedelta(minutes=5), given_at


# ---------------------------------------------------------------- F-A-10 ---

@then(parsers.parse('the sign-in password field has an eye button beside it, labelled '
                    '"{label}"'))
def sign_in_eye(sign_in_page, label):
    login = card_html(sign_in_page, "sign-in")
    wrap = re.search(r'<div class="pw-wrap">\s*<input\b[^>]*\bid="login-password"[^>]*>\s*'
                     r'<button\b([^>]*)>', login)
    assert wrap, "the sign-in password has no eye beside it"
    attributes = wrap.group(1)
    for part in ('class="pw-eye"', 'data-for="login-password"', f'aria-label="{label}"',
                 'aria-pressed="false"'):
        assert part in attributes, part


@then("every eye button on the page is a plain button that cannot send its form")
def eyes_never_submit():
    page_contract.test_every_password_reveal_is_a_button_and_not_a_submit()


@then("a sign-in that succeeds and one that is refused both clear and mask the password")
def sign_in_conceals(page_script):
    handler = page_script[page_script.index("$('login').addEventListener('submit'"):]
    handler = handler[:handler.index("\n});")]
    succeeded, refused = handler.split("} catch (err) {", 1)
    for branch in (succeeded, refused):
        assert "concealPasswords(['login-password']);" in branch, branch


@then("leaving the sign-in card clears and masks the password")
def leaving_conceals(page_script):
    assert "if (which !== 'login') concealPasswords(['login-password']);" \
        in _function(page_script, "showForm")


@then("every card puts its passwords away the same way")
def one_way_to_conceal(page_script):
    conceal = _function(page_script, "concealPasswords")
    for step in ("field.value = '';", "field.type = 'password';",
                 "setAttribute('aria-pressed', 'false')"):
        assert step in conceal, step
    assert page_script.count("field.type = 'password';") == 1, (
        "a second copy of putting a password away")
    for name, ids in (("clearRegistrationPasswords", "['reg-password', 'reg-password2']"),
                      ("clearResetPasswords", "['reset-password', 'reset-password2']")):
        assert f"concealPasswords({ids});" in _function(page_script, name), name


# ---------------------------------------------------------------- F-A-12 ---

@pytest.fixture
def clock(monkeypatch):
    """The served routes' clock, which the scenario moves forward."""
    from nm.app import api

    start = utcnow()
    now = [start]
    monkeypatch.setattr(api, "utcnow", lambda: now[0])
    return {"start": start, "now": now}


def _use_at(client, clock, after):
    clock["now"][0] = clock["start"] + after
    return client.post('/api/session/activity')


@given("an advocate who is signed in")
def advocate_signed_in(client, clock):
    assert SESSION_IDLE_MINUTES == 30 and SESSION_HOURS == 12, (
        "the scenarios' wording no longer matches the session limits")
    assert client.get("/api/session").status_code == 200


@when("nothing uses the session for 30 minutes")
def nothing_for_the_idle_limit(client, clock, context):
    context["response"] = _use_at(client, clock, timedelta(minutes=30))


@when("they use the app every 29 minutes for two hours")
def use_every_29_minutes(client, clock, context):
    for n in range(1, 5):
        context["response"] = _use_at(client, clock, timedelta(minutes=29 * n))
        assert context["response"].status_code == 200, n


@when("they use the app every 29 minutes until 12 hours after signing in")
def use_until_expiry(client, clock, context):
    after = timedelta(0)
    while after + timedelta(minutes=29) < timedelta(hours=12):
        after += timedelta(minutes=29)
        assert _use_at(client, clock, after).status_code == 200, after
    context["response"] = _use_at(client, clock, timedelta(hours=12))


@then("the session is refused")
def session_refused(context):
    assert context["response"].status_code == 401, context["response"].text


@then("the session still works")
def session_still_works(context):
    assert context["response"].status_code == 200, context["response"].text


def _idle_section(script: str) -> str:
    start = script.index("/* ------------------------------------------------------- "
                         "idle sign-out --- */")
    return script[start:script.index("// BK-31-AC20.", start)]


@then("typing, pointing, touching, scrolling and coming back to the tab all count as "
      "activity")
def activity_events(page_script):
    idle = _idle_section(page_script)
    events = re.search(r"const ACTIVITY_EVENTS = \[([^\]]*)\]", idle)
    assert events, "no list of activity events"
    named = set(re.findall(r"'([a-z]+)'", events.group(1)))
    assert {"keydown", "pointermove", "pointerdown", "touchstart", "wheel", "scroll"} <= named
    assert "ACTIVITY_EVENTS.forEach((type) => {" in idle
    assert "document.addEventListener('visibilitychange'" in idle and "'visible'" in idle


@then("the 30 minutes come from the server and are not written in the page")
def idle_limit_from_server(page_script):
    assert not re.search(r"\b30\b", _idle_section(page_script)), (
        "the page keeps its own copy of the idle limit")
    for source in ('r', 'me'):
        call = f'startIdleWatch({source}.session_idle_minutes, {source}.access_window);'
        assert call in page_script


@then("activity in one open tab counts for every open tab")
def activity_shared_across_tabs(page_script):
    idle = _idle_section(page_script)
    assert "new BroadcastChannel('nm-session')" in idle
    assert "postMessage({ type: 'activity'" in idle
    assert "if (data.type === 'activity') noteActivity(data.at, { share: false, report: false });" \
        in idle


@then("a warning appears 2 minutes before the sign-out")
def warning_before_sign_out(page_script):
    idle = _idle_section(page_script)
    assert "const IDLE_WARNING_MS = 2 * 60 * 1000;" in idle
    assert "if (now >= warnAt) showIdleWarning(endAt);" in idle


@then("activity after the 30 minutes signs out instead of starting them again")
def late_activity_signs_out(page_script):
    note = _function(page_script, "noteActivity")
    late = note.index("at - idle.lastActivity >= idle.limitMs")
    assert note.index("idleSignOut();", late) < note.index("idle.lastActivity = at;"), (
        "late activity restarts the clock before it is checked")


@then("the idle sign-out keeps the unsent draft and ends the session on the server")
def idle_sign_out_keeps_the_draft(page_script):
    sign_out = _function(page_script, "idleSignOut")
    assert "sessionEnded(" in sign_out and "api('/api/logout'" in sign_out
    assert "keepDraft();" in _function(page_script, "sessionEnded")
    assert "stopIdleWatch();" in _function(page_script, "clearPrivileged")


# ---------------------------------------------------------------- F-A-13 ---

PHONE = "(max-width: 820px)"
TABLET = "(max-width: 1024px) and (min-width: 821px)"


def media_blocks(css: str, query: str) -> str:
    """The contents of every block for exactly this media query, joined."""
    head = f"@media {query} {{"
    found = []
    at = css.find(head)
    while at >= 0:
        depth = 0
        for end in range(at + len(head) - 1, len(css)):
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
                if depth == 0:
                    break
        found.append(css[at + len(head):end])
        at = css.find(head, end)
    assert found, f"no rules for {query}"
    return "\n".join(found)


def declarations(css: str, selector: str) -> str:
    """The declarations of every rule for exactly this selector, joined."""
    return "\n".join(re.findall(r"(?:^|[}\s])" + re.escape(selector) + r"\s*\{([^}]*)\}", css))


@then("at 820 px wide or narrower the sign-in page is one column")
def phone_is_one_column(stylesheet):
    assert "flex-direction: column" in declarations(media_blocks(stylesheet, PHONE), "#gate")


@then("the left panel keeps only its logo and the logo is not hidden")
def phone_keeps_the_logo(stylesheet):
    phone = media_blocks(stylesheet, PHONE)
    assert "display: none" in declarations(phone, ".arrival-story > :not(.arrival-wordmark)")
    for selector in (".arrival-story", ".arrival-wordmark", ".mark"):
        assert "display: none" not in declarations(phone, selector), selector


@then("between 821 and 1024 px wide the left panel and the gap beside it are narrower")
def tablet_narrows(stylesheet):
    tablet = media_blocks(stylesheet, TABLET)
    assert "width:" in declarations(tablet, ".arrival-story")
    assert "gap:" in declarations(tablet, "#gate")


@then("the sign-in page centres its cards with auto margins, not by aligning to the middle "
      "of a scrolling area")
def centring_is_safe(stylesheet):
    gate = declarations(stylesheet, "#gate")
    assert "overflow-y: auto" in gate
    assert "align-items: center" not in gate and "align-items: var(" not in gate, gate
    assert "margin-block: auto" in declarations(stylesheet, "#gate > *")
    # In one column the main axis is vertical, so centring moves to justify-content.
    assert "justify-content: flex-start" in declarations(media_blocks(stylesheet, PHONE), "#gate")


@then("the cards are at most 420 px wide and shrink with the screen")
def cards_shrink(stylesheet):
    card = declarations(stylesheet, ".login")
    assert "max-width: 420px" in card and "width: 100%" in card, card
    for selector in (".login", "#gate", ".arrival-story", ".privacy-notice", ".pw-wrap",
                     ".login label.consent"):
        assert "min-width" not in declarations(stylesheet, selector), selector


# ---------------------------------------------------------------- F-A-17 ---
#
# The top bar and the person menu (owner's conversation-window layout, 16 Oct 2026:
# '+ New matter' and 'Conversation history' across the top, replacing the sidebar's
# list of matters; no Home, My work, Legal library or Preparation tabs).

@given("the page", target_fixture="app_page")
def the_page() -> str:
    return (ROOT / "nm/app/index.html").read_text(encoding="utf8")


def ribbon_html(page: str) -> str:
    start = page.index('<header class="masthead" id="masthead"')
    return page[start:page.index("</header>", start)]


def pane_html(page: str, name: str) -> str:
    start = page.index(f'<main id="pane-{name}"')
    return page[start:page.index("</main>", start)]


def _board_html(page: str) -> str:
    board = page[page.index('<aside class="matter-board" id="matter-board"'):]
    return board[:board.index("</aside>")]


def _inner_function(script: str, name: str) -> str:
    """One function of a module script written inside its closure, to its end."""
    at = script.find(f"  function {name}(")
    assert at >= 0, f"{name} is not in the script"
    return script[at:script.index("\n  }\n", at)]


@then("the top bar has the NM logo and Nyaymalaw, a New matter button and a Conversation history button")
def top_bar_brand_new_and_history(app_page):
    ribbon = ribbon_html(app_page)
    assert re.search(r'<span class="mark">NM</span>\s*<span class="name">Nyaymalaw</span>', ribbon)
    assert '<button type="button" id="top-new" class="ghost top-action">+ New matter</button>' in ribbon
    assert re.search(r'<button type="button" id="top-history"[^>]*>Conversation history</button>', ribbon)
    script = _asset("app.js")
    assert "$('top-new').addEventListener('click', () => startMatter());" in script
    assert "$('top-history').addEventListener('click', () => openTab('advise'));" in script
    # The list of matters no longer sits beside the work.
    assert 'id="sidebar-board"' not in app_page and 'id="rail-new"' not in app_page


@then("it names the signed-in advocate beside the person menu button")
def sidebar_names_the_advocate(app_page):
    ribbon = ribbon_html(app_page)
    account = ribbon[ribbon.index('<div class="ribbon-account">'):]
    assert account.index('id="who-name"') < account.index('id="account-toggle"')
    toggle = re.search(r'<button\b[^>]*id="account-toggle"[^>]*>', account).group(0)
    for part in ('type="button"', 'aria-haspopup="true"', 'aria-expanded="false"',
                 'aria-controls="account-panel"'):
        assert part in toggle, part


@then("no Home, My work, Legal library or Preparation tab is shown after a sign-in")
def no_top_tabs(app_page, page_script):
    assert re.search(r'<nav class="tabs" id="tabs"[^>]*\bhidden>', app_page)
    assert "$('tabs').hidden" not in page_script and "tabs.hidden" not in page_script
    show = _function(page_script, "showApplication")
    assert "showTab('advise');" in show and "showTab('home')" not in show


@then("the person menu shows the name, email, active workspace, enrolment and practice, and "
      "professional approval")
def person_menu_profile(app_page, page_script):
    panel = app_page[app_page.index('<div id="account-panel"'):]
    details = re.findall(r'<dt>([^<]+)</dt><dd id="([^"]+)"', panel[:panel.index("</dl>")])
    assert details == [("Name", "profile-name"), ("Email", "profile-email"),
                       ("Active workspace", "profile-workspace"),
                       ("Enrolment and practice", "who-detail"),
                       ("Professional approval", "professional-approval")], details
    show = _function(page_script, "showApplication")
    for _, field in details:
        assert f"$('{field}').textContent" in show, f"{field} is never filled"


@then("the person menu has Signed-in devices, AI data sharing, Dictation and Sign out")
def person_menu_actions(app_page):
    panel = app_page[app_page.index('<div id="account-panel"'):app_page.index('<nav class="tabs"')]
    buttons = re.findall(r'<button id="([a-z-]+)" type="button" class="ghost"(?: hidden)?>([^<]+)</button>', panel)
    shown = [(id_, label) for id_, label in buttons if id_ != "advocate-preferences"]
    assert shown == [("devices", "Signed-in devices"), ("ai-sharing", "AI data sharing"),
                     ("dictation-setting", "Dictation"), ("signout", "Sign out")], buttons


@then("the menu opens from its button and closes on Escape, on a click elsewhere, and when "
      "the session ends")
def person_menu_behaviour(page_script):
    setter = _function(page_script, "setAccountMenu")
    assert "$('account-panel').hidden = !open;" in setter and "aria-expanded" in setter
    assert "$('account-toggle').addEventListener('click'" in page_script
    assert "ev.key === 'Escape'" in page_script
    assert "!$('account-menu').contains(ev.target)" in page_script
    assert "setAccountMenu(false);" in _function(page_script, "clearPrivileged")


@then("the name shown is the account's own name, or its email when it has none")
def name_from_the_account(page_script):
    show = _function(page_script, "showApplication")
    assert "const shownName = advocate.name || advocate.email || advocate.id;" in show
    for target in ("$('who-name').textContent = shownName;",
                   "$('profile-name').textContent = shownName;"):
        assert target in show, target


@then("ending the session clears the name, the workspace and every profile detail")
def session_end_clears_the_profile(page_script):
    clear = _function(page_script, "clearPrivileged")
    for detail in ("'who-name'", "'profile-name'", "'profile-email'", "'profile-workspace'",
                   "'who-detail'", "'professional-approval'"):
        assert detail in clear, detail


@then("at 820 px wide or narrower the top bar hides the wordmark and keeps its buttons on one row")
def phone_top_bar(stylesheet):
    phone = media_blocks(stylesheet, PHONE)
    assert ".masthead .brand .name { display: none; }" in phone
    assert re.search(r"\.top-action \{[^}]*white-space: nowrap;", phone)


# ---------------------------------------------------------------- F-A-18 ---
#
# No Home page: a sign-in opens a new matter with its board (owner, 15 and 16 Oct 2026).

@then("a sign-in opens a new matter with its board beside the conversation")
def sign_in_opens_a_new_matter(page_script):
    show = _function(page_script, "showApplication")
    for step in ("showTab('advise');", "if (!draftWaiting) startMatter();"):
        assert step in show, step
    start = _function(page_script, "startMatter")
    for step in ("showTab('advise');", "setWorkView('opening');", "loadChatBoard();", "$('message').focus();"):
        assert step in start, step


@then("a sign-in after a session ended part-way through a brief goes back to that brief")
def sign_in_returns_to_the_draft(page_script):
    show = _function(page_script, "showApplication")
    waiting = show.index("const draftWaiting = Boolean(state.draft && "
                         "state.draft.advocate === advocate.id")
    assert waiting < show.index("if (!draftWaiting) startMatter();") < show.index("if (draftWaiting) {")
    assert "showThreadBoard(draft.matterId)" in show[show.index("if (draftWaiting) {"):]
    assert "keepDraft();" in _function(page_script, "sessionEnded")


# ================================ B. Open a matter ============================

# ---------------------------------------------------------------- F-B-01 ---
#
# Conversation first (owner decision, 16 Oct 2026): a new matter opens straight into
# the conversation, with no form, its board beside it.

@then("New matter opens a new conversation with the message box ready and no form")
def new_matter_opens_the_conversation(page_script):
    assert "$('top-new').addEventListener('click', () => startMatter());" in page_script
    start = _function(page_script, "startMatter")
    for step in ("showIntake(false);", "$('matter-heading').textContent = 'New matter';", "$('message').focus();"):
        assert step in start, step


@then("the board says it fills in as NM understands the matter")
def new_board_waits(page_script):
    assert "if (!chatId) { renderBoardWaiting(); return; }" in _function(page_script, "loadChatBoard")
    assert "The board fills in as NM understands this matter" in _function(page_script, "renderBoardWaiting")


@then("the conversation history is read afresh each time it is opened")
def history_read_afresh(page_script):
    assert "showMatterList();" in _function(page_script, "openTab")
    assert "await loadMatterList();" in _function(page_script, "showMatterList")
    load = _function(page_script, "loadMatterList")
    assert "const generation = ++state.matterListGeneration;" in load and "data = await api('/api/work');" in load


# ---------------------------------------------------------------- F-B-02 ---
#
# The live matter board beside the conversation (owner, 16 Oct 2026).

@then("the matter board comes before the conversation in the window and there are no Board, "
      "Documents or Research notes tabs")
def board_beside_the_conversation(app_page, page_script):
    pane = pane_html(app_page, "advise")
    assert pane.index('<aside class="matter-board" id="matter-board"') < pane.index('<section class="conversation"')
    for gone in ('id="matter-tabs"', "data-matter-tab", 'id="chat-board"', 'id="chat-documents"', 'id="chat-notes"'):
        assert gone not in app_page, gone
    assert "syncMatterTabs" not in page_script


@then("the board is read from the server for this conversation when it opens and after every answer")
def board_from_the_server(page_script):
    assert "await api(`/api/chats/${encodeURIComponent(chatId)}/board`)" in _function(page_script, "loadChatBoard")
    assert "loadChatBoard();" in _function(page_script, "startMatter")
    assert "else if (intent.chatId) loadChatBoard();" in _function(page_script, "deliver")


@then("while NM works on a message the board says what NM is doing")
def board_says_what_nm_is_doing(page_script):
    status = _function(page_script, "syncBoardStatus")
    assert "activeDelivery.entry.context === activeIntent" in status
    assert "activeDelivery.entry.progress.label" in status and "NM is working on your latest message" in status
    assert "syncBoardStatus();" in _function(page_script, "updateWorkspace")


@then("a Board that cannot be read says so rather than showing an empty one")
def unreadable_board_says_so(page_script):
    board = _function(page_script, "loadChatBoard")
    assert "stateBlock('unbuildable', `The board could not be read:" in board
    assert "not an empty matter" in board


@then("each dispute shows its last days, how much is in hand and its items under Needed and Would strengthen "
      "with their marks")
def each_dispute_shows_what_it_needs(page_script):
    # The readability design (owner, 18 Oct 2026); behaviour in tests/js/checklist_board.mjs.
    card = _function(page_script, "renderDisputeCard")
    for step in ("meta.append(...deadlineChips(listed.time_limits));",
                 "`${listed.in_hand} of ${listed.items.length} in hand`",
                 "for (const [group, groupTitle] of CHECK_GROUPS) {", "row.append(checkMark(item.status), words);"):
        assert step in card, step
    assert "const CHECK_GROUPS = [['needed', 'Needed'], ['would_strengthen', 'Would strengthen']];" in page_script
    chips = _function(page_script, "deadlineChips")
    assert "`By ${dayDate(limit.last_day) || rows.get('Last day')}" in chips and "Last day not worked out" in chips
    assert "out.push(renderCheckLegend());" in _function(page_script, "renderChatBoard")


@then("choosing a dispute or an item opens its details in the reading pane on the right")
def a_dispute_or_item_opens_in_the_reading_pane(page_script):
    card = _function(page_script, "renderDisputeCard")
    assert ("window.NmBrainSources.showContent(dispute.name,\n    renderDisputeDetail(dispute, board), title, false, "
            "number ? `Dispute ${number}` : 'Dispute')") in card
    assert ("window.NmBrainSources.showContent(item.need,\n        renderChecklistItem(item, dispute), row, false, "
            "`${groupTitle} · ${place}`)") in card
    detail = _function(page_script, "renderDisputeDetail")
    for part in ("`Between ${dispute.between.join(' · ')}`", "dispute.why_it_matters", "'Time limits'",
                 "'Where it was picked up from'", "'Legal questions'", "`Why it was asked: ${question.why}`",
                 "'Rights at stake'", "'Relief sought'", "'Still needed'", "'Related points for your decision'"):
        assert part in detail, part
    item = _function(page_script, "renderChecklistItem")
    for part in ("'Why it is needed'", "'What shows it'", "'What you said'", "'Where it stands'",
                 "'Tell NM about this'", "'Not available'", "openLaw(law, lawLink)"):
        assert part in item, part
    assert "'board-pane'" not in page_script, "a dispute no longer opens in the board's own pane"


@then("the Files button beside the board's title lists the files and the research notes in the reading pane")
def board_files_button(app_page, page_script):
    head = _board_html(app_page)
    head = head[:head.index("</div>")]
    assert 'id="matter-board-title">Matter board</h2>' in head and 'id="board-files"' in head
    assert 'id="board-files-count"' in head
    assert "$('board-files').addEventListener('click', () => openBoardFiles());" in page_script
    files = _function(page_script, "openBoardFiles")
    for step in ("window.NmBrainSources.showContent('Files in this matter', [files, note, notes], $('board-files'), false,",
                 "'Research notes'", "renderChatNotes(notesBody);", "return loadChatDocuments(files);"):
        assert step in files, step
    assert "`Files · ${sent}`" in _function(page_script, "updateWorkspace")


@then("a document opens in the reading pane on the right")
def document_opens_in_the_reading_pane(page_script):
    assert ("window.NmBrainSources.showContent(document_.name, renderDocumentPages(document_, turn), opener, false,"
            in _function(page_script, "loadChatDocuments"))
    # 17 Oct 2026 (owner decision 4): "Read here" opens what NM read; the name opens the file as sent.
    listing = _function(page_script, "renderChatDocuments")
    assert "read.addEventListener('click', () => open(document_, turn, read));" in listing
    assert "name.href = `/api/documents/${encodeURIComponent(document_.document_ref)}/original`;" in listing


@then("at 820 px wide or narrower a Matter board button opens the board")
def phone_board_button(app_page, stylesheet):
    toggle = re.search(r'<button id="board-toggle"[^>]*>\s*Matter board</button>', app_page)
    assert toggle and 'aria-controls="matter-board"' in toggle.group(0)
    phone = media_blocks(stylesheet, PHONE)
    assert "#pane-advise.has-board.show-board > .matter-board { display: flex; }" in phone
    assert "#pane-advise.has-board.show-board > .conversation { display: none; }" in phone
    # The button appears with the board (P38, 21 Oct 2026).
    assert '#pane-advise.has-board:not([data-view="list"]) .workspace-navigation { display: flex;' in phone
    assert "pane.classList.toggle('show-board', open);" in _function(_asset("app.js"), "toggleMatterBoard")


@then("a new matter shows the conversation alone and the board appears once it has something on it")
def board_once_it_has_something(page_script, stylesheet):
    """P38 (owner, 21 Oct 2026); its behaviour in tests/js/board_shown.mjs."""
    assert re.search(r"#pane-advise \{[^}]*grid-template-columns: minmax\(0, 1fr\); \}", stylesheet)
    assert "#pane-advise > .matter-board { display: none;" in stylesheet
    assert "#pane-advise.has-board > .matter-board { display: flex; }" in stylesheet
    fit = _function(page_script, "fitBoard")
    assert "$('pane-advise').classList.toggle('has-board', filled);" in fit
    assert "state (empty|building)" in fit
    load = _function(page_script, "loadChatBoard")
    assert load.count("fitBoard();") == 3
    assert "fitBoard();" in _function(page_script, "renderBoardWaiting")
    assert "fitBoard();" in _function(page_script, "closeOpenMatter")


# ---------------------------------------------------------------- F-B-03 ---
#
# Conversation history, and the conversation window it opens (owner, 16 Oct 2026).

@then("the conversation history is read from the server and lists every saved conversation")
def list_from_the_server(page_script):
    load = _function(page_script, "loadMatterList")
    assert "data = await api('/api/work');" in load
    assert "data.chats.map((chat) =>" in load and "row.dataset.chatId = chat.chat_id;" in load


@then("a list that cannot be read says so rather than looking empty")
def unreadable_list_says_so(page_script):
    load = _function(page_script, "loadMatterList")
    assert "This is a failure to " in load and "not a statement that you have no matters" in load


@then("choosing a conversation in the history restores it with its board beside it")
def choosing_a_conversation_restores_it(page_script):
    load = _function(page_script, "loadMatterList")
    assert "const selection = restorePendingChat(chat.chat_id);" in load and "row.onclick = open;" in load
    assert "startMatter(chatId);" in _function(page_script, "restorePendingChat")
    assert "loadChatBoard();" in _function(page_script, "startMatter")


@then("the reading pane is part of the conversation window, closed until a link opens it")
def reading_pane_beside(app_page, stylesheet):
    assert '<dialog id="brain-source-reader" class="reading-pane"' in pane_html(app_page, "advise")
    begin = _inner_function(_asset("brain-sources.js"), "begin")
    assert "node('pane-advise').classList.add('reading');" in begin
    assert "dialog.show();" in begin and "showModal" not in begin
    assert "#pane-advise.reading { grid-template-columns: minmax(0, 1fr) minmax(280px, 360px); }" in stylesheet
    assert re.search(r"#pane-advise\.has-board\.reading \{ grid-template-columns: [^;]+ minmax\(0, 1fr\) [^;]+; \}",
                     stylesheet)
    # P38 (owner, 21 Oct 2026) replaces the 18 Oct design's pane always there on a wide screen:
    # the pane shows only while open, and its Close is never hidden.
    assert "#pane-advise > .reading-pane[open] { display: flex; flex-direction: column; }" in stylesheet
    assert "(min-width: 1200px)" not in stylesheet
    assert ".reader-close { display: none" not in stylesheet


@then("each part of the conversation window scrolls on its own, its scroll bar shown only under the pointer")
def each_part_scrolls_on_its_own(stylesheet):
    """P38 (owner, 21 Oct 2026). Words kept for a screen reader inside the board's checklist
    were placed from the whole board, outside the part that scrolls, and scrolled the page."""
    parts = "#rail-body, #matter-board-body, #pane-advise .thread, #brain-source-body"
    assert f"{parts} {{ position: relative; }}" in stylesheet
    assert f"{parts}, #brain-source-body .whole {{\n  scrollbar-width: thin; scrollbar-color: transparent transparent; }}" \
        in stylesheet
    shown = stylesheet[stylesheet.index("#rail-body:hover"):]
    shown = shown[:shown.index("}")]
    for part in ("#rail-body", "#matter-board-body", "#pane-advise .thread", "#brain-source-body"):
        assert f"{part}:hover" in shown and f"{part}:focus-within" in shown, part
    assert "scrollbar-color: var(--ink-3) transparent;" in shown


@then("the reading pane closes on Close or Escape")
def reading_pane_closes(app_page):
    sources = _asset("brain-sources.js")
    assert "node('brain-source-close').addEventListener('click', () => close());" in sources
    keydown = sources[sources.index("document.addEventListener('keydown'"):]
    keydown = keydown[:keydown.index("\n  });\n")]
    assert "event.key !== 'Escape'" in keydown and "close();" in keydown
    assert "node('pane-advise').classList.remove('reading');" in _inner_function(sources, "close")


def _composer(page: str) -> str:
    composer = page[page.index('<form id="composer"'):]
    return composer[:composer.index("</form>")]


# ================================ C. Take the brief ===========================
#
# Rewritten 16 Oct 2026 to the owner's decisions of 15 Oct 2026 (F-C-01 to F-C-03):
# attached files are checked and read, dictation goes to GPT Transcribe, and live
# words come from GPT Live Transcribe only for an advocate who turns them on.

def _asset(name: str) -> str:
    """A browser asset's source, found through the layout's closed asset list."""
    layout = json.loads((ROOT / "nm" / "source_layout.json").read_text(encoding="utf8"))
    return (ROOT / layout["browser_assets"][name]).read_text(encoding="utf8")


def _wav(seconds: float = 0.2) -> bytes:
    """A short silent 16-bit mono WAV recording."""
    import struct

    frames = b"\x00\x00" * int(16000 * seconds)
    return (b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16) + b"data"
            + struct.pack("<I", len(frames)) + frames)


def _nothing_kept(client, data: bytes) -> None:
    for path in client.directory._root.rglob("*"):
        if path.is_file():
            assert data not in path.read_bytes(), path


# ---------------------------------------------------------------- F-C-01 ---

@then("under the brief a plus button offers Attach documents, photos or recordings, and Record a voice note")
def plus_button_under_the_brief(app_page, page_script):
    composer = _composer(app_page)
    assert composer.index('id="message"') < composer.index('id="plus-toggle"')
    items = re.findall(
        r'<button type="button" role="menuitem" id="(plus-[a-z]+)">([^<]+)</button>', composer)
    assert items == [("plus-attach", "Attach documents, photos or recordings"),
                     ("plus-record", "Record a voice note")], items
    assert "$('plus-panel').hidden = !open;" in _function(page_script, "setPlusMenu")


@then("there is no files bar above the chat")
def no_files_bar(app_page):
    materials = _asset("intake-materials.js")
    assert "materials-entry" not in app_page and "materials-entry" not in materials
    assert "$('workspace-focus').after(" not in materials
    assert "Add files or record a voice note" not in app_page


class _ClamAV:
    """Stands in for the malware check: it flags any file carrying the marker."""

    name = "recorded-check"

    def check(self, data):
        if b"FLAGGED" in data:
            return "held", "ClamAV reported a threat in this file (Eicar-Test-Signature)"
        return "clear", "no threat found by ClamAV"


@when("a clean file and a flagged file are attached")
def attach_clean_and_flagged(client, wired, context, monkeypatch):
    monkeypatch.setattr(wired.documents, "checker", _ClamAV())
    for name, data in (("memo.txt", b"Return memo: funds insufficient."), ("bad.txt", b"FLAGGED words")):
        reply = client.post("/api/documents", content=data, headers={"x-nm-document-name": name})
        assert reply.status_code == 201, reply.text
        context[name] = reply.json()


@then("the clean file is read and the flagged file is held unread with ClamAV's reason")
def clean_read_flagged_held(context):
    clean, flagged = context["memo.txt"], context["bad.txt"]
    assert (clean["state"], clean["pages_read"]) == ("read", 1)
    assert (flagged["state"], flagged["pages_read"]) == ("held", 0)
    assert "Eicar-Test-Signature" in flagged["check"]["reason"]


# ---------------------------------------------------------------- F-C-02 ---

class _Hearing:
    """Stands in for GPT Transcribe, and remembers what it was given."""

    def __init__(self, refuse=None):
        self.heard, self.refuse = [], refuse

    def transcribe(self, audio, *, file_name, media_type, prompt=""):
        from nm.shared.model_port import Transcription

        if self.refuse is not None:
            raise self.refuse
        self.heard.append({"audio": audio, "media_type": media_type, "prompt": prompt})
        return Transcription(text="We act for the plaintiff.", provider="openai", model="gpt-transcribe",
                             latency_ms=5, retries=0, languages=("en",), usage={})


@then("beside the plus button there is a mic button that starts recording and stops on a "
      "second press")
def mic_beside_the_plus(app_page, page_script):
    composer = _composer(app_page)
    assert composer.index('id="plus-menu"') < composer.index('id="dictate"')
    assert ("$('dictate').addEventListener('click', () => {\n  if (dictation.recorder) "
            "stopDictation();\n  else startDictation();\n});") in page_script


@then("the words come back into the brief box to be checked, and nothing is sent by itself")
def words_into_the_brief(page_script):
    transcribe = _function(page_script, "transcribeDictation")
    added = _function(page_script, "addDictated")
    assert "addDictated(heard.text);" in transcribe
    assert "if (!replaceProvisional(words)) insertIntoBrief(words);" in added
    for body in (transcribe, added):
        assert "send(" not in body and "requestSubmit" not in body
    assert "stopDictation({ discard: true });" in _function(page_script, "clearPrivileged")


@given("the dictation model", target_fixture="speech")
def the_dictation_model(wired, monkeypatch):
    hearing, bound = _Hearing(), []

    def reader(advocate_id, *, session_current):
        bound.append((advocate_id, session_current()))
        return hearing

    monkeypatch.setattr(wired, "dictation_reader", reader)
    hearing.bound = bound
    return hearing


@when("an advocate sends a short recording to be transcribed")
def send_a_recording(client, context):
    context["audio"] = _wav()
    context["response"] = client.post("/api/dictation", content=context["audio"],
                                      headers={"x-nm-document-name": "dictation.wav"})


@then("the words come back and the recording is not stored anywhere")
def words_back_and_nothing_kept(client, context, speech):
    response = context["response"]
    assert response.status_code == 200, response.text
    assert response.json() == {"text": "We act for the plaintiff."}
    assert [heard["audio"] for heard in speech.heard] == [context["audio"]]
    _nothing_kept(client, context["audio"])


@then("the recording went to GPT Transcribe with the dictation prompt")
def through_gpt_transcribe(wired, speech):
    from nm.core_engine import voice

    assert wired.transcription_model == "gpt-transcribe"
    assert speech.heard[0]["prompt"] == voice.DICTATION_PROMPT and speech.heard[0]["media_type"] == "audio/wav"
    (_, signed_in), = speech.bound
    assert signed_in is True


@when("an advocate who has not accepted AI processing dictates")
def dictate_without_permission(client, wired, context, monkeypatch):
    from nm.shared.external_ai_contracts import ModelPermissionRefused

    refusal = ModelPermissionRefused("AI processing needs your permission: enable it in AI data sharing.")
    monkeypatch.setattr(wired, "dictation_reader", lambda advocate_id, *, session_current: _Hearing(refusal))
    context["response"] = client.post("/api/dictation", content=_wav(),
                                      headers={"x-nm-document-name": "dictation.wav"})


@then("dictation is refused, saying AI processing needs their permission")
def dictation_refused_without_permission(context):
    response = context["response"]
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == {
        "why": "AI processing needs your permission: enable it in AI data sharing.",
        "code": "model_permission_required"}


# ---------------------------------------------------------------- F-C-03 ---

@then("dictation opens the live words socket only when the advocate's dictation setting is live")
def live_words_only_when_turned_on(page_script):
    start = _function(page_script, "startDictation")
    assert "live = (await api('/api/account/dictation')).live === true;" in start
    assert start.index("if (!live ||") < start.index("await openLiveWords(stream, session);")


@then("the dictation setting offers GPT Transcribe by default and GPT Live Transcribe")
def the_dictation_setting(client):
    app_page = _asset("index.html")
    dialog = app_page[app_page.index('id="dictation-setting-dialog"'):]
    dialog = dialog[:dialog.index("</dialog>")]
    assert "GPT Transcribe</strong> (default)" in dialog and "GPT Live Transcribe</strong>" in dialog
    setting = client.get("/api/account/dictation").json()
    assert (setting["live"], setting["model"]) == (False, "gpt-transcribe")


@then("the live words come from a socket and are written into the brief box as they arrive")
def live_words_into_the_brief(app_page, page_script):
    live = _function(page_script, "openLiveWords")
    assert "/ws/dictation" in live and "new WebSocket(" in live and "showLiveWords(heard.words)" in live
    assert "replaceProvisional((words || '').trim())" in _function(page_script, "showLiveWords")
    assert 'id="message"' in _composer(app_page)


@then("the live words stop being written the moment the advocate edits them")
def live_words_let_go_on_an_edit(page_script):
    replace = _function(page_script, "replaceProvisional")
    assert "if (held !== dictation.provisional) {" in replace
    assert "dictation.ours = false;" in replace
    assert "You edited the brief" in _function(page_script, "showLiveWords")


@then("the final live words replace the words they stood in for, or the recording is transcribed if they do "
      "not finish")
def final_replaces_the_live_words(page_script):
    close = _function(page_script, "closeLiveWords")
    assert "live.socket.send('done');" in close and "LIVE_FINAL_WAIT_MS" in close
    stop = page_script[page_script.index("recorder.addEventListener('stop', async () => {"):]
    stop = stop[:stop.index("\n  });")]
    assert stop.index("addDictated(words);") < stop.index("transcribeDictation(blob, session);")


@then("the audio is sent as 24 kHz mono frames of about a tenth of a second")
def audio_as_the_model_wants_it(page_script):
    from nm.shared.model_openai_adapter import LiveTranscription

    worklet = _asset("dictation-worklet.js")
    assert "const FRAME_SAMPLES = 2400;" in worklet and "new Int16Array(FRAME_SAMPLES)" in worklet
    assert "const LIVE_SAMPLE_RATE = 24000;" in page_script
    assert "new AudioContext({ sampleRate: LIVE_SAMPLE_RATE })" in page_script
    assert LiveTranscription.RATE == 24000


@then("the page does not play the advocate's own voice back")
def no_playback(page_script):
    live = _function(page_script, "openLiveWords")
    assert "silence.gain.value = 0;" in live
    assert "node.connect(silence);" in live and "silence.connect(context.destination);" in live


@when("a stranger opens the live dictation socket")
def stranger_opens_the_socket(client, context):
    context["stranger"] = TestClient(client.app)


@then("the socket is refused before any audio is read")
def socket_refused_for_a_stranger(context):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with context["stranger"].websocket_connect(
                "/ws/dictation", headers={"origin": "http://testserver"}) as socket:
            socket.receive_json()


@then("a socket opened from another page is refused the same way")
def socket_refused_from_another_page(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
                "/ws/dictation", headers={"origin": "https://foreign.example"}) as socket:
            socket.receive_json()


@given("an advocate who turned live words on")
def live_words_turned_on(client):
    reply = client.post("/api/account/dictation", json={"live": True, "expected_version": 0})
    assert reply.status_code == 200 and reply.json()["model"] == "gpt-live-transcribe", reply.text


class _LiveLink:
    """The provider's side of a live stream: deltas, then the committed item's words."""

    def __init__(self):
        self.sent, self.closed = [], False

    async def send(self, message):
        self.sent.append(json.loads(message))

    def __aiter__(self):
        return self._events()

    async def _events(self):
        events = [
            {"type": "conversation.item.input_audio_transcription.delta", "item_id": "i1", "delta": "word1"},
            {"type": "conversation.item.input_audio_transcription.delta", "item_id": "i1", "delta": " word2"},
            {"type": "input_audio_buffer.committed", "item_id": "i1"},
            {"type": "conversation.item.input_audio_transcription.completed", "item_id": "i1",
             "transcript": "word1 word2 and the last one"}]
        for event in events:
            yield json.dumps(event)

    async def close(self):
        self.closed = True


@given("the live dictation model", target_fixture="live_speech")
def the_live_dictation_model(wired, monkeypatch):
    from nm.shared.model_openai_adapter import LiveTranscription

    model = SimpleNamespace(link=_LiveLink(), sessions=[])

    async def live_transcription(**request):
        session = LiveTranscription(model.link, model="gpt-live-transcribe", minutes=request["minutes"])
        model.sessions.append(session)
        return session

    model.live_transcription = live_transcription
    monkeypatch.setattr(wired, "live_dictation_reader", lambda advocate_id, *, session_current: model)
    return model


@when("the page sends two frames of speech and then stops")
def send_two_frames(client, context):
    with client.websocket_connect("/ws/dictation", headers={"origin": "http://testserver"}) as socket:
        for frame in (b"\x01\x02" * 1200, b"\x03\x04" * 1200):
            socket.send_bytes(frame)
        socket.send_text("done")
        context["heard"] = []
        while True:
            message = socket.receive_json()
            context["heard"].append(message)
            if "final" in message:
                break


@then("the words heard so far come back as they are heard")
def words_as_heard(context, live_speech):
    assert context["heard"][:2] == [{"words": "word1"}, {"words": "word1 word2"}]
    appended = [event for event in live_speech.link.sent if event["type"] == "input_audio_buffer.append"]
    assert len(appended) == 2


@then("the final words come back when it stops")
def final_words_on_stop(context):
    assert context["heard"][-1] == {"final": "word1 word2 and the last one"}


@then("no audio is stored anywhere")
def no_live_audio_stored(client):
    for frame in (b"\x01\x02" * 1200, b"\x03\x04" * 1200):
        _nothing_kept(client, frame)


@when("an advocate with live words off opens the live dictation socket")
def live_words_off(client, context):
    with client.websocket_connect("/ws/dictation", headers={"origin": "http://testserver"}) as socket:
        context["opened"] = socket.receive_json()


@then("the socket says the live words are off and the recording goes on")
def live_words_off_but_recording_goes_on(context):
    assert context["opened"] == {"live": False, "why": "Live words are off in your dictation settings."}
    live = _function(_asset("app.js"), "openLiveWords")
    assert "Listening; the words will appear when you stop." in live and "settle(null);" in live
