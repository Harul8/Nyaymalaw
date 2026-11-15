"""In a real browser: signing out asks about unsent drafts only where there are some (found mending the browser journeys, 15 Nov
2026).

Sign out asks "Sign out and discard this account's unsent drafts on this device?" before it discards them. The page counted an
open conversation as a draft with work, so once an advocate had used a conversation every sign-out asked it, with nothing unsent -
a warning that is always shown teaches the advocate to dismiss it, and the one time words are unsent it is dismissed too. Now only
what is truly unsent - words typed, a message waiting to be sent or confirmed, the opening form's fields - is asked about; an
open conversation alone is not.

Chromium against the served application with the offline doubles; signed in through the page's own form. Needs a browser.
"""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import BRIEF, _advise, _sign_in, _sign_out, _start_matter
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


def _asked(page):
    """Each question the page asks, answered No - as a dismissed dialog is."""
    seen = []

    def answer(dialog):
        seen.append(dialog.message)
        dialog.dismiss()
    page.on("dialog", answer)
    return seen


def test_signing_out_after_an_answered_conversation_asks_nothing(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    _advise(page, f"Signing out after an answer. {BRIEF}")
    asked = _asked(page)
    _sign_out(page)
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    assert asked == [], f"nothing was unsent, yet the page asked: {asked}"
    assert not page.errors


def test_signing_out_with_words_unsent_asks_first_and_keeps_them_when_refused(page, journey):
    """THE POSITIVE CONTROL: where words are unsent the question is still asked, and No keeps the advocate signed in."""
    _sign_in(page, journey)
    _start_matter(page)
    page.fill("#message", "Words not yet sent.")
    page.locator("#draft-status").filter(has_text="Saved on this device").wait_for()
    asked = _asked(page)
    _sign_out(page)
    page.wait_for_function("() => !document.getElementById('signout').disabled")
    assert len(asked) == 1 and "unsent drafts" in asked[0]
    assert page.is_visible("#masthead") and page.input_value("#message") == "Words not yet sent."
    assert not page.errors
