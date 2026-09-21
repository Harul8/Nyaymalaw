"""D-041 / BK-31: the public door reaches an ordinary private matter.

Real Chromium, HTTP, composition and encrypted temporary storage; no invited
identity and no professional approval fixture for the new account.
"""
from __future__ import annotations

import re

import pytest

from tests import test_the_journey_login_to_logout as support
from tests.registration import CONSENT

pytestmark = pytest.mark.journey
journey = support.journey
page = support.page


def _registration(page, journey, email):
    page.goto(journey["base"] + "/")
    page.click("#show-register")
    assert page.locator("#reg-invitation").count() == 0
    page.fill("#reg-email", email)
    page.fill("#reg-password", journey["password"])
    page.fill("#reg-password2", journey["password"])
    # Implementation Plan F-A-09: Register waits for both privacy boxes.
    assert page.locator("#register-go").is_disabled()
    page.check("#reg-consent")
    page.check("#reg-adult")


@pytest.mark.parametrize("width", [390, 1280])
def test_email_registration_opens_own_workspace_and_matter(page, journey, width):
    email = f"new.account+{width}@example.test"
    page.set_viewport_size({"width": width, "height": 900})
    _registration(page, journey, email)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    with page.expect_response(lambda response: response.url.endswith("/api/register")) as pending:
        page.click("#register-go")
    response = pending.value
    assert response.status == 202
    assert response.request.post_data_json == {
        "email": email, "password": journey["password"],
        "password_again": journey["password"], "consent": {
            **CONSENT, "external_ai": False, "external_ai_notice_version": None},
    }
    assert "x-enrolment-invitation" not in response.request.headers
    page.wait_for_selector('#confirm-email:not([hidden])')
    assert journey['box'].directory.identity(email) is None
    messages = journey['box'].application.mail.messages_for(email)
    code = re.search(r'\b[0-9]{6}\b', messages[-1]['text']).group()
    page.fill('#confirm-code', code)
    page.click('#confirm-go')
    page.wait_for_selector('#outcome:not([hidden])')
    assert page.inner_text('#outcome-title') == 'Email confirmed'
    # F-A-04: no recovery codes anywhere.
    assert page.locator("#recovery-code-list li").count() == 0
    assert page.input_value("#reg-password") == page.input_value("#reg-password2") == ""
    assert not page.is_checked("#reg-consent") and not page.is_checked("#reg-adult")
    assert not page.is_checked('#reg-external-ai')
    assert journey['box'].directory.model_permission(email) is None
    assert page.request.get(journey["base"] + "/api/session").status == 401
    page.click("#outcome-signin")
    assert page.locator("#recovery-code-list li").count() == 0
    assert page.input_value("#login-id") == email
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])")
    assert email in page.inner_text("#workspace-name")
    assert page.inner_text("#who-detail") != " · "
    assert page.inner_text("#professional-approval") == "Professional profile not approved"
    support._reach_rail(page, width)
    assert page.locator("#rail-body .row[data-matter-id]").count() == 0
    support._start_matter(page)
    support._intake(page, client=f"Synthetic Self Registration {width}")
    with page.expect_response(lambda response: response.url.endswith("/api/turn")
                              and response.request.method == "POST") as pending:
        support._advise(page, support.BRIEF)
    turn = pending.value
    assert turn.status == 200
    matter_id = turn.json()["matter_id"]
    assert matter_id
    assert page.request.get(f"{journey['base']}/api/matters/{matter_id}/cover").status == 200
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])")
    support._reach_rail(page, width)
    row = page.locator(f'#rail-body .row[data-matter-id="{matter_id}"]')
    row.wait_for(state="visible")
    row.click()
    page.wait_for_function("id => document.querySelector('#pane-advise').dataset.matterId === id",
                           arg=matter_id)
    page.wait_for_function("brief => document.querySelector('#thread').textContent.includes(brief)",
                           arg=support.BRIEF)
    assert support.BRIEF in page.inner_text("#thread")
    support._sign_out(page)
    page.wait_for_selector("#gate:not([hidden])")
    page.reload()
    page.wait_for_selector("#login:not([hidden])")
    assert page.request.get(journey["base"] + "/api/session").status == 401
    assert not page.errors


def test_registration_mismatch_clears_both_passwords(page, journey):
    email = "mismatch@example.test"
    _registration(page, journey, email)
    page.fill("#reg-password2", journey["password"] + "different")
    requests = []

    def assert_no_registration_request():
        assert not requests, "unexpected registration request"

    page.on("request", lambda request: requests.append(request.url)
            if request.url.endswith("/api/register") else None)
    page.click("#register-go")
    page.wait_for_selector("#outcome:not([hidden])")
    assert "do not match" in page.inner_text("#outcome-body")
    assert_no_registration_request()
    assert page.input_value("#reg-password") == page.input_value("#reg-password2") == ""
    # Prove the same recorder and absence assertion can see a real request.
    # Empty input cannot enrol anybody and sends no password or profile claim.
    status = page.evaluate("""async () => {
      const response = await fetch('/api/register', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
      });
      return response.status;
    }""")
    assert status == 422
    assert len(requests) == 1
    with pytest.raises(AssertionError, match="unexpected registration request"):
        assert_no_registration_request()
    page.click("#outcome-back")
    assert page.input_value("#reg-email") == email
    page.fill("#reg-password", journey["password"])
    page.fill("#reg-password2", journey["password"])
    page.click('#register [data-for="reg-password"]')
    page.click("#show-login")
    page.click("#show-register")
    assert page.input_value("#reg-password") == page.input_value("#reg-password2") == ""
    assert page.get_attribute("#reg-password", "type") == "password"
    assert not page.errors


def test_pending_registration_owns_its_one_time_result(page, journey):
    held = []

    def delay_acknowledgement(route):
        held.append((route, route.fetch()))
        page.evaluate("window.registrationResponseHeld = true")

    page.route("**/api/register", delay_acknowledgement)
    _registration(page, journey, "delayed-registration@example.test")
    page.click("#register-go")
    page.wait_for_function("() => document.querySelector('#register')"
                           ".getAttribute('aria-busy') === 'true'")
    assert page.locator("#register-go").is_disabled()
    assert page.locator("#show-login").is_disabled()
    # Keyboard activation still reaches an anchor's handler; the state owner
    # must refuse it as well as exposing aria-disabled to assistive technology.
    page.focus("#show-login")
    page.press("#show-login", "Enter")
    assert page.is_visible("#register") and page.is_hidden("#login")
    assert page.input_value("#reg-password") == page.input_value("#reg-password2") == ""
    page.wait_for_function("() => window.registrationResponseHeld === true")
    assert len(held) == 1
    route, response = held[0]
    assert response.status == 202, response.text()
    route.fulfill(response=response)
    page.wait_for_selector('#confirm-email:not([hidden])')
    assert 'confirmation' in page.inner_text('#confirmation-detail')
    assert journey['box'].directory.identity('delayed-registration@example.test') is None
    assert page.get_attribute("#register", "aria-busy") is None
    assert not page.errors


def test_unconfirmed_registration_does_not_claim_no_account_was_created(page, journey):
    page.route("**/api/register", lambda route: route.abort())
    _registration(page, journey, "unconfirmed-registration@example.test")
    page.click("#register-go")
    page.wait_for_selector("#outcome:not([hidden])")
    assert 'could not be confirmed' in page.inner_text('#outcome-body')
    assert page.input_value("#reg-password") == page.input_value("#reg-password2") == ""
    assert page.get_attribute("#register", "aria-busy") is None
    page.click("#outcome-back")
    page.click("#show-login")
    assert page.is_visible("#login")
    assert not page.errors


def test_full_length_email_stays_readable_on_a_phone(page, journey):
    email = 'u' * 64 + '@' + '.'.join(['d' * 63, 'e' * 63, 'f' * 61])
    assert len(email) == 254
    page.set_viewport_size({"width": 390, "height": 844})
    _registration(page, journey, email)
    page.click("#register-go")
    page.wait_for_selector('#confirm-email:not([hidden])')
    messages = journey['box'].application.mail.messages_for(email)
    code = re.search(r'\b[0-9]{6}\b', messages[-1]['text']).group()
    page.fill('#confirm-code', code)
    page.click('#confirm-go')
    page.wait_for_selector("#outcome:not([hidden])")
    assert page.inner_text("#outcome-title") == "Email confirmed"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.click("#outcome-signin")
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])")
    assert email in page.inner_text("#workspace-name")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not page.errors
