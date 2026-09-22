"""Owner's quiet recovery contract, driven through the served page."""

import pytest

from tests.test_opening_journey import saved
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


def open_recovery(page):
    page.locator("#workspace-more summary").click()
    page.click("#draft-open")
    page.wait_for_selector("#draft-dialog[open]")


def reopen(page, mid):
    page.reload()
    page.get_by_role("button", name="My work", exact=True).click()
    page.locator(f'#rail-body [data-matter-id="{mid}"]').click()
    saved(page)


def test_recovery_is_on_demand_and_success_disappears_without_losing_text(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.click("#in-go")
    mid, _ = saved(page)
    text = "Synthetic unsent instruction about two disputed transactions."
    page.fill("#message", text)
    page.locator("#draft-status").filter(has_text="Saved on this device").wait_for()
    reopen(page, mid)
    assert not page.locator("#draft-dialog").is_visible()
    assert page.locator("#draft-recovery").inner_text() == ""
    assert page.locator("#message").input_value() == ""
    open_recovery(page)
    page.get_by_role("button", name="Recover unsent draft", exact=False).click()
    page.locator("#draft-restored").filter(has_text="Draft restored").wait_for()
    assert page.locator("#message").input_value() == text
    page.wait_for_function(
        "document.getElementById('draft-restored').textContent === ''", timeout=7000
    )
    assert page.locator("#message").input_value() == text
    assert page.locator("#thread .turn").count() == 0
    assert not page.locator("#draft-dialog").is_visible()
    assert not page.errors


def test_recovery_does_not_offer_another_matters_draft(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.click("#in-go")
    first, _ = saved(page)
    page.fill("#message", "Synthetic first matter only")
    page.locator("#draft-status").filter(has_text="Saved on this device").wait_for()
    _start_matter(page)
    page.click("#in-go")
    second, _ = saved(page)
    assert first != second
    open_recovery(page)
    page.get_by_text("No recoverable drafts for this input.", exact=True).wait_for()
    assert page.locator("#draft-recovery button").count() == 0
    page.keyboard.press("Escape")
    assert not page.locator("#draft-dialog").is_visible()


def test_a_save_failure_does_not_disappear_like_a_success(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.click("#in-go")
    saved(page)
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
    _start_matter(page)
    page.click("#in-go")
    saved(page)
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


@pytest.mark.parametrize("outcome", ["reply", "failure", "cancel"])
def test_send_consumes_only_the_submitted_draft_before_the_response(page, journey, outcome):
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
    page.wait_for_function("document.getElementById('send').textContent === 'Send'")
    assert page.locator("#message").input_value() == message
    assert page.locator("#thread .brief").last.inner_text() == message
    if outcome != "reply":
        assert page.get_by_role("button", name="Send this brief again", exact=True).is_visible()
    assert not page.errors


@pytest.mark.parametrize("committed", [False, True])
def test_cleared_composer_recovers_receipt_and_retries_exactly_once_after_reload(
    page, journey, committed
):
    _open_matter(page, journey, client="Synthetic receipt survives reload")
    mid, _ = saved(page)
    calls = []

    def intercept(route):
        calls.append(route.request.post_data)
        response = route.fetch() if committed or len(calls) > 1 else None
        if response is not None:
            assert response.status == 200
        if len(calls) == 1:
            route.abort()
        else:
            route.fulfill(response=response)

    page.route("**/api/turn", intercept)
    page.fill("#message", BRIEF)
    page.click("#send")
    page.get_by_role("button", name="Send this brief again", exact=True).wait_for()
    assert page.locator("#message").input_value() == ""
    # An identical new draft is distinct from the protected receipt.
    page.fill("#message", BRIEF)
    page.locator("#draft-status").filter(has_text="Saved on this device").wait_for()
    reopen(page, mid)
    open_recovery(page)
    page.get_by_role("button", name="Recover unsent draft", exact=False).click()
    page.locator("#draft-restored").filter(has_text="Draft restored").wait_for()
    if committed:
        # The recorded transcript resolves the uncertainty without another call.
        assert len(calls) == 1
        assert page.get_by_role("button", name="Send this brief again", exact=True).count() == 0
    else:
        page.get_by_role("button", name="Send this brief again", exact=True).click()
        page.wait_for_function("document.getElementById('send').textContent === 'Send'")
        assert len(calls) == 2 and calls[0] == calls[1]
    assert page.locator("#message").input_value() == BRIEF
    assert not page.errors


def test_failed_receipt_protection_never_dispatches_or_loses_the_text(page, journey):
    _open_matter(page, journey, client="Synthetic unavailable receipt storage")
    calls = []
    page.on("request", lambda req: calls.append(req) if req.url.endswith("/api/turn") else None)
    page.evaluate(
        "() => { Storage.prototype.setItem = () => { throw Error('Synthetic quota'); }; }"
    )
    page.fill("#message", BRIEF)
    page.click("#send")
    page.get_by_text("The retry details could not be saved", exact=False).wait_for()
    assert not calls
    assert page.locator("#message").input_value() == ""
    assert page.locator("#thread .brief").last.inner_text() == BRIEF
    assert page.get_by_role("button", name="Send this brief again", exact=True).is_visible()


@pytest.mark.parametrize("width,height", WIDTHS)
def test_matter_header_is_one_line_and_opening_record_is_only_in_casefile(
    page, journey, width, height
):
    _sign_in(page, journey, width, height)
    _start_matter(page)
    title = (
        "Synthetic long matter title with several independently disputed transactions " * 2
    ).strip()
    page.fill("#in-title", title)
    page.click("#in-go")
    saved(page)
    header = page.locator(".workspace-heading").bounding_box()
    assert header["height"] <= 46
    assert page.locator("#matter-heading").get_attribute("title") == title
    assert (
        page.locator("#matter-heading").evaluate("el => getComputedStyle(el).whiteSpace")
        == "nowrap"
    )
    assert page.locator("#rail #opening-record").count() == 0
    assert page.get_by_text("MATTER WORKSPACE", exact=True).count() == 0
    assert page.locator("#thread").bounding_box()["height"] > height * 0.5
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Case file", exact=True).click()
    page.locator("#opening-record").wait_for(state="visible")
    assert page.locator("#pane-casefile #opening-record").count() == 1
    assert not page.errors
