"""In a real browser: a conversation's unsent words come back with it after a reload (found mending the browser journeys, 15 Nov
2026).

Words typed in a conversation are kept on the device as they are typed, and the page says so ("Saved on this device"). The page read
them back only from Recover a draft - a record under the file icon, which is shown for a matter saved before conversations and for
the opening form, not for a conversation - so after a reload the words were kept and could not be had (measured: the box empty, no
"Draft restored"). Opening a conversation whose message box is empty now takes back the last words saved for it, and says so; they
never come back into another conversation.

Chromium against the served application with the offline doubles; signed in through the page's own form. Needs a browser.
"""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import BRIEF, _advise, _reopen, _sign_in, _start_matter
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


def _type_and_keep(page, words):
    page.fill("#message", words)
    page.locator("#draft-status").filter(has_text="Saved on this device").wait_for()


def test_a_conversations_unsent_words_come_back_when_it_is_reopened_after_a_reload(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    _advise(page, f"Words kept across a reload. {BRIEF}")
    _type_and_keep(page, "Unsent words to finish after lunch.")
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    _reopen(page, "Words kept across a reload.")
    page.wait_for_function("() => document.getElementById('message').value === 'Unsent words to finish after lunch.'",
                           timeout=10000)
    assert "Draft restored" in page.inner_text("#draft-restored")
    assert not page.errors


def test_one_conversations_words_never_come_back_into_another(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    _advise(page, f"The conversation with words. {BRIEF}")
    _type_and_keep(page, "Words that belong only here.")
    _start_matter(page)
    _advise(page, f"The conversation without words. {BRIEF}")
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    _reopen(page, "The conversation without words.")
    page.wait_for_timeout(1500)  # what would come back comes back from the device at once; give it the moment it takes
    assert page.input_value("#message") == ""
    _reopen(page, "The conversation with words.")
    page.wait_for_function("() => document.getElementById('message').value === 'Words that belong only here.'",
                           timeout=10000)
    assert not page.errors
