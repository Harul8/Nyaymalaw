"""In a real browser: a message whose reply was lost, across a session that expired, is sent again exactly once after the advocate
signs in again (BK-36 and BK-46 for the conversation window; written again on 15 Nov 2026 for the test the matter model had).

The reply to a message is lost before the server has it; then the advocate's session ends (an expiry, made on the server) and the
page asks them to sign in. Signing in again without reloading, the page still holds what was being done: the message is in the
conversation, the box is not refilled with it, and Send this brief again sends it with the exact request it was first sent with - the
same turn - so the conversation keeps it once.

Chromium against the served application with the offline doubles; the expiry is made in the server's own directory. Needs a browser.
"""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import BRIEF, _advise, _reach_rail, _sign_in, _start_matter
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page
WORDS = "Keep this exact instruction once, whatever happens to its reply."


def _kept(page, journey, chat_id):
    chat = page.request.get(journey["base"] + f"/api/chats/{chat_id}").json()
    held = chat.get("pending") or {}
    return [turn.get("message") for turn in chat.get("turns") or []] + ([held["message"]] if held.get("message") else [])


def test_a_lost_reply_across_an_expired_session_is_sent_again_exactly_once(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    _advise(page, f"Lost reply across an expiry. {BRIEF}")
    chat = page.evaluate("() => shownChatId()")
    assert chat

    first = []

    def lose(route):
        first.append(route.request.post_data)
        route.abort()  # the reply is lost before the server has the message
    page.route("**/api/turn", lose)
    page.fill("#message", WORDS)
    page.click("#send")
    retry = page.get_by_role("button", name="Send this brief again", exact=True)
    retry.wait_for(timeout=20000)
    page.unroute("**/api/turn", lose)
    assert len(first) == 1 and WORDS not in _kept(page, journey, chat), "nothing of it reached the server"

    # THE SESSION ENDS (an expiry, on the server), and the page's next request meets it.
    ended = journey["box"].directory.close_all_sessions(journey["advocate"], "journey: an expiry", except_token="")
    assert ended >= 1
    page.click("#top-history")
    page.wait_for_selector("#gate:not([hidden])", timeout=30000)

    # SIGNING IN AGAIN WITHOUT A RELOAD: the page still holds what was being done.
    page.fill("#login-id", journey["advocate"])
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    if not retry.is_visible():
        _reach_rail(page, 1280)  # back to the conversation it was sent in, from the conversation history
        row = page.locator(f"#rail-body .row[data-chat-id='{chat}']")
        row.wait_for(timeout=15000)
        row.click()
    retry.wait_for(timeout=15000)
    assert page.input_value("#message") == "", "the box is not refilled with a message already in the conversation"
    assert WORDS in page.locator("#thread .brief").all_text_contents()

    again = []
    page.on("request", lambda request: again.append(request.post_data) if request.url.endswith("/api/turn")
            and request.method == "POST" else None)
    retry.click()
    page.wait_for_function("() => document.getElementById('send').dataset.state !== 'working'", timeout=60000)
    assert again and again[0] == first[0], "the retry is the exact request first sent - the same turn"
    assert _kept(page, journey, chat).count(WORDS) == 1, "and the conversation keeps the message once"
    assert not page.errors
