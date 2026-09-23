"""Phase A -- Arrive, as the product owner described it.

The `.feature` files under `tests/features/arrive/` are GENERATED from the column
"Scenarios (Given / When / Then)" of the Implementation Plan's Arrive rows, which state
each row's Must do and Must never so they can be read against the product owner's words
in column C. This module binds every step to the real page (`frontend/index.html`,
`frontend/app.js`, `frontend/app.css`) and to the served routes through the shared
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

import pytest
from fastapi.testclient import TestClient
from nm.adapters.store.directory import RETIRED_RECOVERY_FIELDS
from nm.domain.advocate import (
    PASSWORD_RESET_MINUTES,
    PRIVACY_NOTICE_VERSION,
    SESSION_HOURS,
    SESSION_IDLE_MINUTES,
    AdvocateIdentity,
    Enrolment,
    enrol,
    utcnow,
)
from pytest_bdd import given, parsers, scenarios, then, when

import tests.test_the_page_and_the_script_agree as page_contract
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
    return (ROOT / "frontend" / "app.js").read_text(encoding="utf8")


def _function(script: str, name: str) -> str:
    """One top-level function of the page script, from its declaration to its end."""
    at = script.find(f"function {name}(")
    assert at >= 0, f"{name} is not in the page script"
    return script[at:script.index("\n}\n", at)]


@given("the sign-in page", target_fixture="sign_in_page")
def the_sign_in_page() -> str:
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf8")


@given("the page script", target_fixture="page_script")
def the_page_script() -> str:
    return _script()


@given("the page stylesheet", target_fixture="stylesheet")
def the_page_stylesheet() -> str:
    """Comments stripped: a value inside a comment is not a declaration."""
    return re.sub(r"/\*.*?\*/", "", (ROOT / "frontend" / "app.css").read_text(encoding="utf8"),
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
    style = re.sub(r"/\*.*?\*/", "", (ROOT / "frontend" / "app.css").read_text(encoding="utf8"),
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


@then("the register card has a Register button and a Back to sign in link")
def register_card_actions(sign_in_page):
    register = card_html(sign_in_page, "register")
    assert re.search(r'<button\b[^>]*id="register-go"[^>]*>\s*Register\s*</button>', register)
    assert re.search(r'<a\b[^>]*id="show-login"[^>]*>\s*Back to sign in\s*</a>', register)


RULES = ("The password must be at least 8 characters and contain an upper-case letter, "
         "a lower-case letter, a numeral and a special character.")


@then("the register card states the password rules")
def register_card_rules(sign_in_page):
    assert RULES in visible_text(card_html(sign_in_page, "register"))


@then("the register card carries only account details, delivery status and confirmation navigation")
def register_card_is_bare(sign_in_page):
    register = card_html(sign_in_page, "register")
    for forbidden in ('class="mark"', "login-brand", "login-lede", "field-help"):
        assert forbidden not in register, forbidden
    # The notice and its two boxes are F-A-09's and are checked there.
    register = re.sub(r'<section class="privacy-notice".*?</section>', " ", register, flags=re.S)
    register = re.sub(r'<label class="consent".*?</label>', " ", register, flags=re.S)
    remainder = visible_text(register)
    for piece in (RULES, "Checking registration availability…",
                  "Already have a confirmation code?", "required.", "Retype password",
                  "Back to sign in", "Register",
                  "Password", "Email"):
        assert piece in remainder, f"{piece!r} is missing from the register card"
        remainder = remainder.replace(piece, " ", 1)
    leftover = remainder.replace("*", " ").replace(EYE, " ").split()
    assert not leftover, f"the register card says more than the details: {leftover}"


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
    from nm.edge import api

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


@then("the Register button stays unavailable until both boxes are ticked")
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
    from nm.edge import api

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

@given("the page", target_fixture="app_page")
def the_page() -> str:
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf8")


def ribbon_html(page: str) -> str:
    start = page.index('<header class="masthead" id="masthead"')
    return page[start:page.index("</header>", start)]


def ribbon_first_row(page: str) -> str:
    ribbon = ribbon_html(page)
    return ribbon[ribbon.index('<div class="ribbon-row">'):ribbon.index('<nav class="tabs"')]


def pane_html(page: str, name: str) -> str:
    start = page.index(f'<main id="pane-{name}"')
    return page[start:page.index("</main>", start)]


@then("the ribbon's first row has the NM logo and Nyaymalaw on the left")
def ribbon_brand(app_page):
    row = ribbon_first_row(app_page)
    brand, account = row.index('<div class="brand">'), row.index('<div class="ribbon-account">')
    assert brand < account, "the logo is not before the advocate's details"
    assert re.search(r'<span class="mark">NM</span>\s*<span class="name">Nyaymalaw</span>',
                     row[brand:account])


@then("on its right the advocate's name, the active workspace and a person menu button, in "
      "that order")
def ribbon_account(app_page):
    row = ribbon_first_row(app_page)
    account = row[row.index('<div class="ribbon-account">'):]
    order = [account.index(marker) for marker in (
        'id="who-name"', 'id="workspace-context" aria-label="Active workspace"',
        'id="account-toggle"')]
    assert order == sorted(order), order
    toggle = re.search(r'<button\b[^>]*id="account-toggle"[^>]*>', account).group(0)
    for part in ('type="button"', 'aria-haspopup="true"', 'aria-expanded="false"',
                 'aria-controls="account-panel"'):
        assert part in toggle, part
    assert 'class="person-icon"' in account and 'class="menu-arrow"' in account


@then("the ribbon's tabs are exactly Home, My work, Legal library and Preparation")
def ribbon_tabs(app_page):
    ribbon = ribbon_html(app_page)
    nav = ribbon[ribbon.index('<nav class="tabs" id="tabs"'):]
    tabs = re.findall(r'<button class="tab[^"]*" data-tab="([a-z]+)"[^>]*>([^<]+)</button>', nav)
    assert tabs == [("home", "Home"), ("advise", "My work"), ("search", "Legal library"),
                    ("prepare", "Preparation")], tabs


@then("the ribbon is outside every page, and every page scrolls inside itself below it")
def ribbon_outside_every_page(app_page, stylesheet):
    ribbon_end = app_page.index("</header>", app_page.index('<header class="masthead"'))
    panes = re.findall(r'<main id="(pane-[a-z]+)"', app_page)
    assert len(panes) == 6, panes
    for pane in panes:
        assert app_page.index(f'<main id="{pane}"') > ribbon_end, f"{pane} is not below the ribbon"
    ribbon = declarations(stylesheet, ".masthead")
    assert "flex: none" in ribbon and "position: fixed" not in ribbon, ribbon
    body = declarations(stylesheet, "body")
    assert "flex-direction: column" in body and "100dvh" in body, body
    assert "min-height: 0" in declarations(stylesheet, "main")


@then("moving between pages never hides the ribbon; only the sign-in gate does")
def ribbon_never_hidden(page_script):
    hides = [found.start()
             for found in re.finditer(r"\$\('masthead'\)\.hidden = true", page_script)]
    gate = page_script.index("function showGate(")
    assert len(hides) == 1 and gate < hides[0] < page_script.index("\n}\n", gate), hides
    assert "masthead" not in _function(page_script, "showTab")


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


@then("the person menu has Signed-in devices and Sign out")
def person_menu_actions(app_page):
    panel = app_page[app_page.index('<div id="account-panel"'):app_page.index('<nav class="tabs"')]
    assert '<button id="devices" type="button" class="ghost">Signed-in devices</button>' in panel
    assert '<button id="signout" type="button" class="ghost">Sign out</button>' in panel


@then("the menu opens from its button and closes on Escape, on a click elsewhere, and when "
      "the session ends")
def person_menu_behaviour(page_script):
    setter = _function(page_script, "setAccountMenu")
    assert "$('account-panel').hidden = !open;" in setter and "aria-expanded" in setter
    assert "$('account-toggle').addEventListener('click'" in page_script
    assert "ev.key === 'Escape'" in page_script
    assert "!$('account-menu').contains(ev.target)" in page_script
    assert "setAccountMenu(false);" in _function(page_script, "clearPrivileged")


@then("Case file and History are not tabs")
def case_file_and_history_are_not_tabs(app_page):
    ribbon = ribbon_html(app_page)
    for name in ("casefile", "history"):
        assert f'data-tab="{name}"' not in ribbon, name


@then("an open matter offers Case file and History while it is open")
def work_links_for_the_open_matter(app_page, page_script):
    links = re.search(r'<nav class="work-links" id="work-links"[^>]*\bhidden>(.*?)</nav>',
                      pane_html(app_page, "advise"), re.S)
    assert links, "My work has no Case file and History links, or they start shown"
    assert re.findall(r'data-tab="([a-z]+)">([^<]+)</button>', links.group(1)) == [
        ("casefile", "Case file"), ("history", "History")]
    assert "$('work-links').hidden = !state.matterId;" in _function(page_script, "updateWorkspace")


@then("they open on that matter, with the matter's own tab still marked")
def work_links_open_on_the_matter(page_script):
    assert "if (['advise', 'casefile', 'history'].includes(pane)) return state.workTab;" \
        in _function(page_script, "tabFor")
    assert "const tab = tabFor(name);" in _function(page_script, "showTab")
    assert "if (link.dataset.tab === 'casefile') $('casefile-matter').value = '';" in page_script
    assert "const want = held || state.matterId || '';" in _function(
        page_script, "loadCasefileMatters")
    history = _function(page_script, "loadHistoryMatters")
    assert "sel.value = state.matterId;" in history and "showHistory(state.matterId);" in history


@then("the library availability line is on the Legal library page and not in the ribbon")
def health_on_the_library_page(app_page):
    assert 'id="health"' not in ribbon_html(app_page)
    assert '<div class="health" id="health" role="status">' in pane_html(app_page, "search")


@then("at 820 px wide or narrower the name and workspace move into the person menu")
def phone_name_in_the_menu(app_page, stylesheet):
    phone = media_blocks(stylesheet, PHONE)
    assert "display: none" in declarations(
        phone, ".ribbon-account > .who-name, .ribbon-account > .workspace-context")
    panel = app_page[app_page.index('<div id="account-panel"'):]
    assert 'id="profile-name"' in panel and 'id="profile-workspace"' in panel


@then("the tabs stay on one row that scrolls inside the ribbon")
def phone_tabs_scroll(stylesheet):
    tabs = declarations(media_blocks(stylesheet, PHONE), ".tabs")
    assert "flex-wrap: nowrap" in tabs and "overflow-x: auto" in tabs, tabs


@then("the Matters button is inside My work")
def matters_button_in_my_work(app_page):
    assert 'id="matters-toggle"' in pane_html(app_page, "advise")
    assert 'id="matters-toggle"' not in ribbon_html(app_page)


@then("the name shown is the account's own name, or its email when it has none")
def name_from_the_account(page_script):
    show = _function(page_script, "showApplication")
    assert "const shownName = advocate.name || advocate.email || advocate.id;" in show
    for target in ("$('who-name').textContent = shownName;",
                   "$('profile-name').textContent = shownName;"):
        assert target in show, target


@then("ending the session clears the name, the workspace and every profile detail")
def session_end_clears_the_ribbon(page_script):
    clear = _function(page_script, "clearPrivileged")
    assert "['who-name', 'workspace-name', 'profile-name', 'profile-email', " \
        "'profile-workspace']" in clear
    for detail in ("'who-detail'", "'professional-approval'"):
        assert detail in clear, detail


# ---------------------------------------------------------------- F-A-18 ---

HOME_WORDS = ("Nyaymalaw is a legal research and matter workspace for advocates practising "
              "Telangana and Union of India law.",
              "Every answer shows the Act, section or judgment it rests on.")


@then(parsers.parse('the home page says "{words}"'))
def home_says(app_page, words):
    assert words in visible_text(pane_html(app_page, "home"))


@then(parsers.parse('the home page has one button, "{label}", and nothing else'))
def home_has_one_button(app_page, label):
    home = pane_html(app_page, "home")
    assert re.findall(r"<button\b[^>]*>([^<]*)</button>", home) == [label]
    assert not re.search(r"<(?:a|input|select|textarea|form|nav|img)\b", home), (
        "the home page carries more than its introduction and button")
    text = visible_text(home)
    for piece in (*HOME_WORDS, label):
        text = text.replace(piece, " ", 1)
    assert not text.split(), f"the home page says more: {text}"


@then("the Start a matter button starts a new matter under Home")
def home_starts_a_matter(page_script):
    assert "$('home-start').addEventListener('click', startMatter);" in page_script
    start = _function(page_script, "startMatter")
    assert "state.workTab = 'home';" in start and "showTab('advise');" in start


@then("a sign-in shows the Home page")
def sign_in_lands_on_home(page_script):
    show = _function(page_script, "showApplication")
    landing = "showTab(draftWaiting ? 'advise' : 'home');"
    assert landing in show
    assert "showTab(" not in show.replace(landing, ""), "a second landing decision"


@then("a sign-in after a session ended part-way through a brief goes back to that brief in "
      "My work")
def sign_in_returns_to_the_draft(page_script):
    show = _function(page_script, "showApplication")
    waiting = show.index("const draftWaiting = Boolean(state.draft && "
                         "state.draft.advocate === advocate.id")
    assert waiting < show.index("showTab(draftWaiting ? 'advise' : 'home');") \
        < show.index("if (draftWaiting) {")
    assert "keepDraft();" in _function(page_script, "sessionEnded")


# ================================ B. Open a matter ============================

OPENING = '#pane-advise[data-view="opening"]'
LISTING = '#pane-advise[data-view="list"]'


def _intake_submit(script: str) -> str:
    submit = script[script.index("$('intake').addEventListener('submit'"):]
    return submit[:submit.index("\n});")]


# ---------------------------------------------------------------- F-B-01 ---

@then("Start a matter opens the intake form alone, with Home still the marked tab")
def start_opens_the_intake_alone(page_script, stylesheet):
    start = _function(page_script, "startMatter")
    for part in ("state.workTab = 'home';", "showTab('advise');", "setWorkView('opening');",
                 "selectIntent(null, { opening: true });"):
        assert part in start, part
    assert "showMatterList" not in start, "a new matter must not load the list of other matters"
    # LB-84 keeps the intake's recovery menu reachable, but no matter heading
    # or board is shown before a matter exists.
    for hidden in (".rail", ".matters-toggle", ".workspace-heading > div:first-child"):
        assert "display: none" in declarations(stylesheet, f"{OPENING} {hidden}"), hidden


@then("recording the intake saves the matter on the server with the form's parties before "
      "the chat opens")
def intake_saves_the_matter_first(page_script):
    submit = _intake_submit(page_script)
    saved = submit.index("await api('/api/matters/intake'")
    assert "parties: state.intake.parties" in submit[:saved]
    assert "brief: state.intake.brief" in submit[:saved]
    assert "JSON.stringify(payload)" in submit[:saved]
    assert "request_key: intent.opening.key, ...payload" in submit[saved:]
    closed = submit.index("showIntake(false);", saved)
    board = submit.index(
        "showThreadBoard(opened.matter_id, { adoptOpening: true, restore: false })")
    assert saved < closed < board, "the chat opens before the server confirms the matter"
    assert "opened.state !== 'intake_opened'" in submit


@then("if the matter cannot be opened the form keeps its answers and says so")
def failed_opening_keeps_the_form(page_script):
    submit = _intake_submit(page_script)
    failure = submit[submit.index("} catch (e) {"):]
    assert "showIntake(false)" not in failure
    # A missing acknowledgement is not evidence that the commit did not happen.
    assert "Opening was not confirmed" in failure
    assert "server may have saved" in failure
    assert "original answers and retry identity are kept" in failure


@when(parsers.parse('an advocate opens a matter for "{client_name}" against "{adverse}" '
                    'without a title'))
def open_a_matter_without_a_title(client, context, client_name, adverse):
    context["parties"] = {client_name: "client", adverse: "adverse"}
    context["response"] = client.post("/api/matters/intake", json={
        "request_key": "scenario-opening", "parties": context["parties"]})


@then(parsers.parse('the matter is saved as "{title}" with both parties recorded'))
def matter_saved_as(wired, context, title):
    response = context["response"]
    assert response.status_code == 200, response.text
    opened = response.json()
    assert opened["state"] == "intake_opened" and opened["title"] == title, opened
    context["matter_id"] = opened["matter_id"]
    saved = wired.store.load(opened["matter_id"])
    assert saved.title == title and saved.intake_parties == context["parties"]


@then("it is in My work's list straight away")
def in_my_work_straight_away(client, context):
    rows = client.get("/api/matters").json()["matters"]
    row = next((r for r in rows if r["matter_id"] == context["matter_id"]), None)
    assert row, rows
    client_name, adverse = list(context["parties"])
    assert (row["client"], row["opponent"]) == (client_name, adverse), row


# ---------------------------------------------------------------- F-B-02 ---

@then("in an open matter the board is the left pane and the chat the right")
def board_left_chat_right(app_page, stylesheet):
    advise = pane_html(app_page, "advise")
    rail = advise.index('<aside class="rail" id="rail">')
    board = advise.index('id="matter-board"')
    assert rail < board < advise.index("</aside>") < advise.index('<section class="conversation"')
    assert "grid-template-columns: 19rem minmax(0, 1fr)" in declarations(stylesheet, "main")


@then("the board is filled from My work's row for this matter, with the same fields as the "
      "list")
def board_is_my_works_row(page_script):
    board = _function(page_script, "renderMatterBoard")
    assert "await api('/api/matters')" in board
    assert "row.matter_id === matterId" in board and "matterFields(fields, m);" in board
    assert "matterFields(dl, m);" in _function(page_script, "showMatterList")
    fields = _function(page_script, "matterFields")
    # `'posture'` WAS RENAMED `'position'` in 602e3f0's plain-language pass;
    # the field and what it shows -- blocked, or no unresolved posture -- did
    # not change.
    for label in ("'client'", "'against'", "'deadline'", "'last worked'", "'position'"):
        assert label in fields, label


@then("the board is read again after every message")
def board_after_every_message(page_script):
    assert "renderMatterBoard(matterId, generation);" in _function(page_script, "showThreadBoard")
    assert "await showThreadBoard(state.matterId, {" in _function(page_script, "deliver")


@then("a board that cannot be read says so rather than showing an empty one")
def unreadable_board_says_so(page_script):
    assert _function(page_script, "renderMatterBoard").count("stateBlock('unbuildable'") == 2


@then("the issues recorded on the matter are listed on the board under its details")
def issues_on_the_board(app_page, page_script):
    rail = app_page[app_page.index('<aside class="rail" id="rail">'):]
    rail = rail[:rail.index("</aside>")]
    assert rail.index('id="matter-board"') < rail.index('id="rail-meta"') \
        < rail.index('id="rail-body"')
    show = _function(page_script, "showThreadBoard")
    assert "$('rail-title').textContent = 'Matter board';" in show
    # THE DISPUTE AGENDA, since 602e3f0: one row per dispute on the matter,
    # read from the board's `agenda`, and an agenda that cannot be read says
    # so rather than rendering an empty board.
    assert "renderDisputeAgenda(body, data.agenda);" in show
    agenda = _function(page_script, "renderDisputeAgenda")
    assert "const rows = agenda.disputes;" in agenda
    assert "if (!agenda || !Array.isArray(agenda.disputes))" in agenda


# ---------------------------------------------------------------- F-B-03 ---

@then("My work has no new-matter button and no welcome page")
def my_work_is_only_the_list(app_page, page_script):
    advise = pane_html(app_page, "advise")
    for gone in ('id="new-matter"', 'id="welcome"', 'id="welcome-start"'):
        assert gone not in advise, gone
    assert "$('new-matter')" not in page_script and "$('welcome" not in page_script


@then("choosing the My work tab always shows the list of matters")
def my_work_tab_lists(page_script, stylesheet):
    chosen = _function(page_script, "openTab")
    assert "state.workTab = 'advise';" in chosen and "showMatterList();" in chosen
    assert "b.addEventListener('click', () => openTab(b.dataset.tab));" in page_script
    assert "setWorkView('list');" in _function(page_script, "showMatterList")
    assert "display: none" in declarations(stylesheet, f"{LISTING} .conversation")


@then("opening a matter shows its board and restores its conversation, with My work still "
      "the marked tab")
def opening_a_matter_resumes_it(page_script):
    assert "row.onclick = () => showThreadBoard(m.matter_id);" in _function(
        page_script, "showMatterList")
    show = _function(page_script, "showThreadBoard")
    assert "setWorkView('matter');" in show
    assert "if (restore && !(await restoreConversation(matterId, generation))) return;" in show
    assert "workTab" not in show, "opening a matter must not move it to another tab"


def _frontend_file(name: str) -> str:
    return (ROOT / "frontend" / name).read_text(encoding="utf8")


def _backend_file(relative: str) -> str:
    return (ROOT / "backend" / "nm" / relative).read_text(encoding="utf8")


def _composer(page: str) -> str:
    composer = page[page.index('<form id="composer"'):]
    return composer[:composer.index("</form>")]


# ---------------------------------------------------------------- F-B-04 ---

@then("Matter cover & instructions, Attributed file and Protective handoff sit in the matter's "
      "header beside Case file and History")
def matter_tools_in_the_header():
    tools = _frontend_file("matter-workspace.js")
    assert "document.getElementById('workspace-menu').prepend(toolbar);" \
        in tools
    page = _frontend_file('index.html')
    header = page[page.index('id="workspace-focus"'):page.index('<form id="intake"')]
    assert 'id="workspace-menu"' in header and '<summary>More</summary>' in header
    assert ".after(toolbar)" not in tools, "the tools are still a bar of their own"
    for label in ("'Matter cover & instructions'", "'Attributed file'", "'Protective handoff'"):
        assert label in tools, label


# ================================ C. Take the brief ===========================

# ---------------------------------------------------------------- F-C-01 ---

@then("under the brief a plus button opens Upload documents, Upload photos, audio or video, "
      "and Record a voice note to keep")
def plus_button_under_the_brief(app_page, page_script):
    composer = _composer(app_page)
    assert composer.index('id="message"') < composer.index('id="plus-toggle"')
    items = re.findall(
        r'<button type="button" role="menuitem" id="(plus-[a-z]+)">([^<]+)</button>', composer)
    assert items == [("plus-documents", "Upload documents"),
                     ("plus-media", "Upload photos, audio or video"),
                     ("plus-voice", "Record a voice note to keep")], items
    assert "$('plus-panel').hidden = !open;" in _function(page_script, "setPlusMenu")


@then("each opens the original-material window, which keeps what it receives sealed and unread")
def plus_items_open_the_materials_window():
    materials = _frontend_file("intake-materials.js")
    for kind in ("documents", "media", "voice"):
        assert f"$('plus-{kind}').addEventListener('click', () => openFor('{kind}'));" \
            in materials, kind
    assert "They are not scanned" in materials


@then("there is no files bar above the chat")
def no_files_bar():
    materials = _frontend_file("intake-materials.js")
    assert "materials-entry" not in materials and "$('workspace-focus').after(" not in materials


# ---------------------------------------------------------------- F-C-02 ---

AUDIO = b"OggS\x00synthetic-opus-recording"


class _Transcriber:
    """Stands in for the speech model, and remembers what it was given."""

    def __init__(self):
        self.heard = []

    def transcribe(self, audio, media_type):
        from nm.domain.dictation import Transcript

        self.heard.append((audio, media_type))
        return Transcript(text="We act for the plaintiff.", language="en", seconds=2.0,
                          device="cuda")


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
    assert "insertIntoBrief(words);" in transcribe
    assert "send(" not in transcribe and "requestSubmit" not in transcribe
    assert "stopDictation({ discard: true });" in _function(page_script, "clearPrivileged")


@given("the dictation service", target_fixture="speech")
def the_dictation_service(wired, monkeypatch):
    # `wired`, NEVER an imported `application()`: a step that resolves the
    # application itself patches whichever one was wired last -- a previous
    # test's -- and the route then runs the real model. See the fixture.
    fake = _Transcriber()
    monkeypatch.setattr(wired.transcriber, "inner", fake)
    return fake


@when("an advocate sends a short recording to be transcribed")
def send_a_recording(client, context):
    context["response"] = client.post("/api/dictation", content=AUDIO,
                                      headers={"content-type": "audio/webm"})


@then("the words come back and the recording is not stored anywhere")
def words_back_and_nothing_kept(client, context, speech):
    response = context["response"]
    assert response.status_code == 200, response.text
    assert response.json() == {"text": "We act for the plaintiff.", "language": "en",
                               "seconds": 2.0, "device": "cuda", "stored": False}
    assert speech.heard == [(AUDIO, "audio/webm")]
    for path in client.directory._root.rglob("*"):
        if path.is_file():
            assert AUDIO not in path.read_bytes(), path


@then("it went through the recorded local speech processor")
def through_the_local_speech_processor(wired):
    from nm.bootstrap.egress_policy import TRANSCRIPTION_PROCESSOR, egress_policy
    from nm.domain.egress import Sink

    policed = wired.transcriber
    assert policed.sink is Sink.TRANSCRIPTION
    assert policed.processor_id == TRANSCRIPTION_PROCESSOR
    recorded = egress_policy(ROOT).find(TRANSCRIPTION_PROCESSOR)
    assert recorded is not None and recorded.region == "in"
    assert Sink.TRANSCRIPTION in recorded.purposes


@when("the local speech model is not installed and an advocate dictates")
def dictate_without_the_model(client, wired, context, monkeypatch):
    import sys

    from nm.adapters.speech.local_whisper import LocalWhisper

    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    monkeypatch.setattr(wired.transcriber, "inner", LocalWhisper(model="tiny"))
    context["response"] = client.post("/api/dictation", content=AUDIO,
                                      headers={"content-type": "audio/webm"})


@then("dictation asks the speech model for English unless the installation sets another language")
def dictation_asks_for_english():
    """MEASURED 15 September 2026: left to detect, a few seconds of
    Indian-accented English came back in Urdu script, and an advocate cannot
    correct a brief they cannot read."""
    adapter = _backend_file("adapters/speech/local_whisper.py")
    assert 'language: str = "en"' in adapter
    assert 'language=None if wanted in ("", "auto") else wanted,' in adapter
    assert '"translate" if self.translate else "transcribe"' in adapter
    wiring = _backend_file("bootstrap/composition.py")
    assert 'language=settings.get("NM_DICTATION_LANGUAGE") or "en",' in wiring


@then("dictation is refused, saying the local speech model is not installed")
def dictation_refused_not_installed(context):
    response = context["response"]
    assert response.status_code == 503, response.text
    assert "the local speech model is not installed" in response.json()["detail"]


# ---------------------------------------------------------------- F-C-03 ---

class _LiveEngine:
    """Stands in for the live speech model, and remembers what it was fed."""

    def __init__(self, fail=None):
        self.fed = []
        self.rate = None
        self.fail = fail

    def listen(self, sample_rate):
        if self.fail:
            raise self.fail
        self.rate = sample_rate
        return self

    def hear(self, pcm):
        self.fed.append(pcm)
        return " ".join(f"word{number}" for number in range(1, len(self.fed) + 1))

    def close(self):
        return "word1 word2 and the last one"


@then("the live words come from a socket and are written into the brief box as they arrive")
def live_words_into_the_brief(app_page, page_script):
    assert "/ws/dictation" in page_script
    live = _function(page_script, "openLiveWords")
    assert "new WebSocket(" in live and "showLiveWords(heard.words)" in live
    assert "replaceProvisional((words || '').trim())" in _function(page_script, "showLiveWords")
    assert 'id="message"' in _composer(app_page)


@then("the live words stop being written the moment the advocate edits them")
def live_words_let_go_on_an_edit(page_script):
    replace = _function(page_script, "replaceProvisional")
    assert "if (held !== dictation.provisional) {" in replace
    assert "dictation.ours = false;" in replace
    assert "You edited the brief" in _function(page_script, "showLiveWords")


@then("the final transcription replaces the live words it stood in for")
def final_replaces_the_live_words(page_script):
    transcribe = _function(page_script, "transcribeDictation")
    assert "if (!replaceProvisional(words)) insertIntoBrief(words);" in transcribe


@then("the audio is sent as 16 kHz mono frames of about a tenth of a second")
def audio_as_the_model_wants_it(page_script):
    worklet = _frontend_file("dictation-worklet.js")
    assert "const FRAME_SAMPLES = 1600;" in worklet
    assert "new Int16Array(FRAME_SAMPLES)" in worklet
    assert "const LIVE_SAMPLE_RATE = 16000;" in page_script
    assert "new AudioContext({ sampleRate: LIVE_SAMPLE_RATE })" in page_script
    rate = _backend_file("domain/dictation.py")
    assert "LIVE_SAMPLE_RATE = 16_000" in rate


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


@given("the live dictation service", target_fixture="live_speech")
def the_live_dictation_service(wired, monkeypatch):
    engine = _LiveEngine()
    monkeypatch.setattr(wired.live_dictation, "inner", engine)
    return engine


@when("the page sends two frames of speech and then stops")
def send_two_frames(client, context):
    with client.websocket_connect(
            "/ws/dictation", headers={"origin": "http://testserver"}) as socket:
        context["opened"] = socket.receive_json()
        context["heard"] = []
        for frame in (b"\x01\x02" * 800, b"\x03\x04" * 800):
            socket.send_bytes(frame)
            context["heard"].append(socket.receive_json())
        socket.send_text("done")
        context["final"] = socket.receive_json()


@then("the words heard so far come back after each frame")
def words_after_each_frame(context, live_speech):
    from nm.domain.dictation import LIVE_SAMPLE_RATE

    assert context["opened"] == {"live": True}
    assert [row["words"] for row in context["heard"]] == ["word1", "word1 word2"]
    assert live_speech.rate == LIVE_SAMPLE_RATE
    assert len(live_speech.fed) == 2


@then("the final words come back when it stops")
def final_words_on_stop(context):
    assert context["final"] == {"words": "word1 word2 and the last one", "done": True}


@then("no audio is stored anywhere")
def no_live_audio_stored(client, live_speech):
    for frame in live_speech.fed:
        for path in client.directory._root.rglob("*"):
            if path.is_file():
                assert frame not in path.read_bytes(), path


@when("the live speech model is not downloaded and an advocate dictates")
def live_model_missing(client, wired, context, monkeypatch, tmp_path):
    from nm.adapters.speech.vosk_live import VoskLive

    monkeypatch.setattr(wired.live_dictation, "inner",
                        VoskLive(model_dir=tmp_path / "no-model-here"))
    with client.websocket_connect(
            "/ws/dictation", headers={"origin": "http://testserver"}) as socket:
        context["opened"] = socket.receive_json()


@then("the socket says the live words are off and the recording goes on")
def live_words_off_but_recording_goes_on(context, page_script):
    opened = context["opened"]
    assert opened["live"] is False
    assert "not downloaded" in opened["why"] or "not installed" in opened["why"]
    assert "will appear when you stop" in opened["why"]
    # The page keeps recording for the final transcription and says so.
    assert "sayDictation(`${heard.why} Listening.`)" in _function(page_script, "openLiveWords")
