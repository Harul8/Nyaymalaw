"""In a real browser: an Admin closes an account at the advocate's written request from the Admin page (plan AN.53, 53h7d; D241,
D246: two steps, the address typed, a reason naming the request).

Chromium against the served application on a real port. The Admin signs in through the workspace's own form and opens the
account's page in the Admin area. An active account offers no closure, only Suspend; once suspended it offers Close the account,
whose dialog says what goes and that it cannot be undone, and asks for the account's address typed out. A wrong address is
refused in the server's words and nothing goes; the right one closes the account, the page goes back to the Users list, says so,
and the account is no longer listed. Only who the server's settings name as an admin is set in the server (the journey harness
names none). Needs a browser (the `journey` extra).
"""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page
ADMIN, CLOSING = "root@example.test", "closing@example.test"
REQUEST = "Written request of 12 Nov 2026 from the advocate"


@pytest.fixture
def admin_area(journey, monkeypatch):
    from nm.arrive.admin_access import roster_from

    box = journey["box"]
    box.enrol(ADMIN)
    box.enrol(CLOSING)
    monkeypatch.setattr(box.application, "admin_roster", roster_from({"NM_ADMINS": f"{ADMIN}:admin"}))
    return box


def _signed_in_as_the_admin(page, journey):
    page.goto(journey["base"] + "/app")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    page.fill("#login-id", ADMIN)
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)


def _account_page(page, journey):
    page.goto(journey["base"] + f"/admin#users/{CLOSING}")
    page.get_by_role("button", name="End all sessions…").wait_for(timeout=15000)


def _dialog_for(page, button, *, password):
    page.get_by_role("button", name=button).click()
    dialog = page.locator("#adm-dialog")
    dialog.wait_for(state="visible", timeout=5000)
    if password:
        page.fill("#adm-f-password", password)
    page.fill("#adm-f-reason", REQUEST)
    return dialog


def test_an_admin_closes_a_suspended_account_from_its_page(page, journey, admin_area):
    _signed_in_as_the_admin(page, journey)
    _account_page(page, journey)
    assert page.get_by_role("button", name="Close the account…").count() == 0, "an active account offers no closure"
    suspending = _dialog_for(page, "Suspend the account…", password=journey["password"])
    assert "Why (one line, kept in the audit log)" in suspending.inner_text(), "another change's dialog is as it was"
    page.get_by_role("button", name="Suspend", exact=True).click()
    page.get_by_role("button", name="Close the account…").wait_for(timeout=15000)

    dialog = _dialog_for(page, "Close the account…", password=None)
    said = dialog.inner_text()
    # D246 (3): what goes, said.
    for goes in ("every conversation of theirs, kept or deleted", "all the papers they sent", "they can no longer sign in",
                 "It cannot be undone"):
        assert goes in said, goes
    # D246 (4) and (5): what is kept, and the backups, said at the closure.
    for kept in ("eight years as a billing record", "two years", "90 days", "sign-in logs’ lines for a year",
                 "audit log, which keeps that you closed the account", "gone from every copy within 35 days"):
        assert kept in said, kept
    assert "Whose written request, and its date" in said, "the reason says whose request it is"
    page.fill("#adm-f-address", "someone-else@example.test")
    page.get_by_role("button", name="Close the account", exact=True).click()
    page.wait_for_function("document.querySelector('#adm-dialog .adm-dialog-message').textContent.includes('address')",
                           timeout=10000)
    assert admin_area.directory._advocate_path(CLOSING).exists(), "a wrong address closes nothing"

    page.fill("#adm-f-address", CLOSING)
    page.get_by_role("button", name="Close the account", exact=True).click()
    page.wait_for_function("location.hash === '#users'", timeout=15000)
    page.wait_for_function("document.body.innerText.includes('account is closed')", timeout=15000)
    assert not admin_area.directory._advocate_path(CLOSING).exists()
    assert page.locator(f"a[href='#users/{CLOSING.replace('@', '%40')}']").count() == 0, "no longer listed"
    assert not page.errors
