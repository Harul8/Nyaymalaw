"""In a real browser: what the page shows of the server (plan AN.52, 52a4), and a late reply (plan AN.53, 53i).

The page's script runs in Chromium against the served application, signed in through the page's own form. Where a case needs
the server to say something it cannot be made to say on demand - that its code is older than the code on disk, or that a turn
is still being worked on and then finishes - that one answer is stood in for at the browser's edge, and every other request
goes to the real server. So this checks the page: its requests, its screen, its own saving of drafts - not the engine.

Needs a browser (the `journey` extra); it is not part of the every-commit run.
"""
from __future__ import annotations

import json

import pytest

from tests.test_the_journey_login_to_logout import _sign_in
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page

STALE = "This server is running code that is no longer on disk. Everything it serves is the older code. Restart it."
FIRST = "A question of the first conversation, still being worked on."


def _api_requests(page, journey):
    seen = []
    page.on("request", lambda request: seen.append((request.method, request.url.replace(journey["base"], ""))))
    return seen


def _told_of_the_server(page):
    """Wait until the page has drawn the library's line from the server's answer (it says 'Checking...' until then)."""
    page.wait_for_function("!document.getElementById('health').textContent.trim().startsWith('Checking')", timeout=15000)


def _json(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


# ------------------------------------------------------------- 52a4: the server's state ---

def test_a_visitor_is_asked_nothing_of_the_server_and_a_signed_in_advocate_is_told_once(page, journey):
    seen = _api_requests(page, journey)
    page.goto(journey["base"] + "/app")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    page.wait_for_timeout(800)
    assert not [address for _method, address in seen if "/api/health" in address], "the sign-in screen asks nothing of health"
    assert page.is_hidden("#build-warning"), "and says nothing of the code"
    seen.clear()
    _sign_in(page, journey)
    _told_of_the_server(page)
    asked = [address for _method, address in seen if "/api/health" in address]
    assert asked == ["/api/health/detail"], f"asked once, of the signed-in address: {asked}"
    # This server's library is an empty folder and its model a stand-in: both are said, from the server's own words for them.
    assert page.inner_text("#health").startswith(("Legal library unavailable", "Chat available"))
    assert page.is_visible("#rehearsal-warning")
    assert page.is_hidden("#build-warning"), "the server runs the code on disk: no banner"
    assert not page.errors


def test_older_code_is_said_once_signed_in_and_the_banner_comes_down_with_the_workspace(page, journey):
    def stale(route):
        answer = route.fetch().json()
        _json(route, {**answer, "code_state": "stale", "why": STALE})
    page.route("**/api/health/detail", stale)
    page.goto(journey["base"] + "/app")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    assert page.is_hidden("#build-warning"), "not on the sign-in screen"
    _sign_in(page, journey)
    page.wait_for_selector("#build-warning:not([hidden])", timeout=15000)
    assert page.inner_text("#build-warning") == STALE
    page.evaluate("document.getElementById('signout').click()")   # the button sits in a menu; its own handler is what runs
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    assert page.is_hidden("#build-warning"), "the banner is not left up for whoever is at the sign-in screen next"
    assert not page.errors


def test_a_health_asking_that_fails_is_not_an_all_clear(page, journey):
    page.route("**/api/health/detail", lambda route: _json(route, {"detail": "The server could not say."}, status=503))
    _sign_in(page, journey)
    page.wait_for_selector("#build-warning:not([hidden])", timeout=15000)
    assert page.inner_text("#build-warning").startswith("The build could not be identified: ")
    assert page.inner_text("#health").startswith("Not ready")


# ------------------------------------------------------------- 53i: a late reply ---

class _WorkedOnElsewhere:
    """One conversation whose turn is being worked on (as after a reload, or from another tab), stood in for at the browser's
    edge: how the conversation reads, and how its turn stands - 'working' until `finish()`."""

    def __init__(self, page):
        self.finished, self.read, self.asked = False, 0, 0
        page.route("**/api/chats/c-first", self._conversation)
        page.route("**/api/chats/c-first/**", lambda route: _json(route, {"detail": "Not held in this check."}, status=404))
        page.route("**/api/turn-progress?*", self._progress)
        page.route("**/api/turn-events?*", lambda route: route.abort())   # no stream here: the page asks, as it does without one

    def _conversation(self, route):
        self.read += 1
        pending = {} if self.finished else {"pending": {
            "turn_id": "t-held", "state": "working", "message": FIRST, "documents": [], "elements": [], "steers": []}}
        _json(route, {"state": "ok", "chat_id": "c-first", "matter_id": None, "matter_version": 4,
                      "title": "The first conversation", "turns": [], **pending})

    def _progress(self, route):
        self.asked += 1
        _json(route, {"state": "finished" if self.finished else "working", "turn_id": "t-held", "chat_id": "c-first"})

    def finish(self):
        self.finished = True


def _following_the_first(page, journey):
    first = _WorkedOnElsewhere(page)
    _sign_in(page, journey)
    _told_of_the_server(page)
    # The conversation is opened by the page's own function for it (the one the history's lines call).
    page.evaluate("restorePendingChat('c-first')")
    page.wait_for_function(f"document.getElementById('thread').textContent.includes({json.dumps(FIRST)})", timeout=15000)
    page.wait_for_function("activeIntent && activeIntent.chatId === 'c-first'", timeout=15000)
    assert first.read == 1
    return first


def _heard_that_it_finished(page, first):
    asked = first.asked
    first.finish()
    page.wait_for_timeout(200)
    deadline = 12000
    while first.asked == asked and deadline > 0:      # the page asks every two seconds
        page.wait_for_timeout(250)
        deadline -= 250
    assert first.asked > asked, "the page asked how the turn stands and was told it had finished"
    page.wait_for_timeout(1500)                        # time for whatever the page does with that


def test_a_turn_that_finishes_while_the_advocate_is_still_in_its_conversation_is_read_again(page, journey):
    """The neighbour: the advocate stays, and the reply acts as it always did."""
    first = _following_the_first(page, journey)
    _heard_that_it_finished(page, first)
    assert first.read == 2, "its conversation is read again from the server"
    assert page.evaluate("activeIntent.chatId") == "c-first"
    assert not page.errors


def test_a_turn_that_finishes_after_the_advocate_opened_another_conversation_changes_nothing_on_screen(page, journey):
    first = _following_the_first(page, journey)
    page.click("#top-new")
    page.wait_for_function(f"!document.getElementById('thread').textContent.includes({json.dumps(FIRST)})", timeout=15000)
    assert page.evaluate("activeIntent.chatId") is None, "a new conversation is open"
    page.fill("#message", "Words being written in the second conversation.")
    _heard_that_it_finished(page, first)
    assert first.read == 1, "the first conversation is not opened over the one the advocate is in"
    assert FIRST not in page.inner_text("#thread")
    assert page.evaluate("activeIntent.chatId") is None, "and the next message does not go to the first"
    assert page.input_value("#message") == "Words being written in the second conversation.", "nor are the words lost"
    assert not page.errors
