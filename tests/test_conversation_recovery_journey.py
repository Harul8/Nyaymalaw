"""Owner's quiet recovery contract, driven through the served page."""

import pytest

from tests.test_the_journey_login_to_logout import (
    BRIEF,
    WIDTHS,
    _open_matter,
    _sign_in,
    _start_matter,
)
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


def test_a_save_failure_does_not_disappear_like_a_success(page, journey):
    _sign_in(page, journey)
    _start_matter(page)  # a conversation opens on its message box; there is no opening form to record first
    page.evaluate(
        "() => { Storage.prototype.setItem = function() { "
        "throw Error('Synthetic quota failure'); }; }"
    )
    page.fill("#message", "Do not lose this unsaved synthetic instruction")
    page.locator("#draft-status").filter(has_text="Could not save this draft").wait_for()
    page.wait_for_timeout(5300)
    assert "Could not save this draft" in page.locator("#draft-status").inner_text()
    assert (
        page.locator("#message").input_value() == "Do not lose this unsaved synthetic instruction"
    )


@pytest.mark.parametrize("width,height", WIDTHS)
def test_composer_is_reachable_and_ime_enter_is_not_a_send(page, journey, width, height):
    _sign_in(page, journey, width, height)
    _start_matter(page)  # a conversation opens on its message box; there is no opening form to record first
    page.fill("#message", "Synthetic multi-dispute instruction")
    requests = []
    page.on(
        "request",
        lambda request: requests.append(request.url) if "/api/turn" in request.url else None,
    )
    page.locator("#message").dispatch_event("keydown", {"key": "Enter", "isComposing": True})
    assert not requests
    box = page.locator("#send").bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= width
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("#message").input_value() == "Synthetic multi-dispute instruction"
    assert not page.errors

    # THE POSITIVE CONTROL. `assert not requests` passes just as well when the
    # listener never matches a send, so the same listener must SEE the Enter
    # that is not composing.
    with page.expect_request(lambda request: "/api/turn" in request.url):
        page.locator("#message").dispatch_event("keydown", {"key": "Enter"})
    assert requests, "a real send reached the server and the listener saw nothing"


@pytest.mark.parametrize("outcome", ["reply", "failure", "cancel"])
def test_send_consumes_only_the_submitted_draft_before_the_response(page, journey, outcome):
    if outcome == "cancel":
        pytest.skip("Cancel, which abandoned the browser's request, was replaced by Stop (plan AN.42, D74-D78): the ring "
                    "stops NM after the step in progress on the server; there is no request for the page to abandon")
    _open_matter(page, journey, client="Synthetic composer lifecycle")
    held = []
    page.route("**/api/turn", lambda route: held.append(route))
    message = BRIEF + "\nAdditional unverified instruction." * 15
    page.fill("#message", message)
    before = page.locator("#message").bounding_box()["height"]
    page.click("#send")
    page.wait_for_function("document.getElementById('message').value === ''")
    assert page.locator("#message").bounding_box()["height"] < before
    assert page.locator("#thread .brief").last.inner_text() == message
    # Deliberately identical text: equality alone cannot identify the old draft.
    page.fill("#message", message)
    page.wait_for_function(
        "document.getElementById('draft-status').textContent === 'Saved on this device'"
    )
    assert len(held) == 1
    if outcome == "reply":
        held[0].continue_()
    elif outcome == "failure":
        held[0].abort()
    else:
        page.get_by_role("button", name="Cancel", exact=True).click()
        held[0].abort()
    page.wait_for_function("document.getElementById('send').dataset.state === 'send'")
    assert page.locator("#message").input_value() == message
    assert page.locator("#thread .brief").last.inner_text() == message
    if outcome != "reply":
        # A reply that never came is asked after on the server first (D73); the retry is offered once that is known.
        page.get_by_role("button", name="Send this brief again", exact=True).wait_for(timeout=15000)
    assert not page.errors


def test_failed_receipt_protection_never_dispatches_or_loses_the_text(page, journey):
    _open_matter(page, journey, client="Synthetic unavailable receipt storage")
    calls = []
    page.on("request", lambda req: calls.append(req) if req.url.endswith("/api/turn") else None)
    page.evaluate(
        "() => { window.__setItem = Storage.prototype.setItem; "
        "Storage.prototype.setItem = () => { throw Error('Synthetic quota'); }; }"
    )
    page.fill("#message", BRIEF)
    page.click("#send")
    page.get_by_text("The retry details could not be saved", exact=False).wait_for()
    assert not calls
    assert page.locator("#message").input_value() == ""
    assert page.locator("#thread .brief").last.inner_text() == BRIEF
    assert page.get_by_role("button", name="Send this brief again", exact=True).is_visible()

    # THE POSITIVE CONTROL. `assert not calls` passes just as well when the
    # listener's filter never matches a real send, so with storage back the
    # retry must be SEEN by the same listener.
    page.evaluate("() => { Storage.prototype.setItem = window.__setItem; }")
    with page.expect_request(lambda request: "/api/turn" in request.url):
        page.get_by_role("button", name="Send this brief again", exact=True).click()
    assert calls, "a real send reached the server and the listener saw nothing"
