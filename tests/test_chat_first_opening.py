"""The first message opens a matter; its board waits for saved details."""

from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import _sign_in, playwright_api

pytestmark = pytest.mark.journey
OPENING_MESSAGE = "We act for Farah Begum. Raghav Reddy built a wall on her land yesterday."


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    from assurance.journeys.served import PASSWORD, running
    from tests.test_brain_turn import Model, plan

    opening = plan(
        "Assess the reported wall on the client's land", scope="proposed",
        step="legal_work",
        reply=("You report a wall on the client's land. The assessment is "
               "pending; the conveyance and boundary records are needed."),
        title="Land boundary concern",
        summary="The advocate reports that a wall was built on the client's land.")
    model = Model([opening, opening])
    with running(tmp_path_factory.mktemp("chat_first"), model=model) as (box, base):
        advocate = box.enrol()
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD}


@pytest.fixture
def page():
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        opened = context.new_page()
        opened.errors = []
        opened.on("pageerror", lambda error: opened.errors.append(str(error)))
        try:
            yield opened
        finally:
            context.close()
            browser.close()


def test_chat_opens_first_and_board_waits_for_a_successful_read(page, journey):
    _sign_in(page, journey)
    page.click("#home-start")

    assert page.get_attribute("#pane-advise", "data-view") == "opening"
    assert page.is_hidden("#intake")
    assert page.locator("#rail-body .dispute-proposal-item").count() == 0
    assert page.is_visible("#composer")
    assert page.locator("#thread .turn").count() == 0
    assert not page.get_attribute("#pane-advise", "data-matter-id")
    chat = page.locator("#pane-advise .conversation").bounding_box()
    composer = page.locator("#composer").bounding_box()
    assert chat and composer
    assert abs((composer["x"] + composer["width"] / 2)
               - (chat["x"] + chat["width"] / 2)) < 12
    assert abs((composer["y"] + composer["height"] / 2)
               - (chat["y"] + chat["height"] / 2)) < 60

    def fail_board_read(route):
        route.abort("failed")

    page.route("**/api/matters/*", fail_board_read)
    message = OPENING_MESSAGE
    page.fill("#message", message)
    with page.expect_response(lambda response: response.url.endswith("/api/turn"),
                              timeout=30000) as turn_result:
        page.click("#send")
    assert turn_result.value.status == 200, turn_result.value.text()
    page.get_by_role("button", name="Retry matter board").wait_for(timeout=30000)

    matter_id = page.get_attribute("#pane-advise", "data-matter-id")
    assert matter_id
    assert page.locator("#rail-body .dispute-proposal-item").count() == 0
    assert page.get_attribute("#pane-advise", "data-view") == "opening"
    assert page.get_by_text(message, exact=True).count() == 1

    page.unroute("**/api/matters/*", fail_board_read)
    with page.expect_response(lambda response: response.url.endswith(
            f"/api/matters/{matter_id}") and response.status == 200,
            timeout=30000):
        page.get_by_role("button", name="Retry matter board").click()
    page.get_by_text("No disputes identified yet.").wait_for(timeout=30000)
    assert page.get_attribute("#pane-advise", "data-view") == "matter"
    assert page.get_attribute("#pane-advise", "data-matter-id") == matter_id
    assert not page.errors


def test_pending_chat_reopens_from_my_work_with_its_history(page, journey):
    from nm.brain.turn import BrainService, BrainTurn, chat_matter_id
    from tests.test_brain_turn import Model, plan

    greeting = "Hello"
    chat_id = "browser-pending-greeting"
    store = journey["box"].application.store
    first = BrainService(store, Model([plan(greeting)])).run(
        BrainTurn(journey["advocate"], greeting, chat_id,
                  offer={"message": greeting})).as_dict()
    assert first["chat_id"] == chat_id and first["matter_id"] is None

    _sign_in(page, journey)
    with page.expect_response(lambda response: response.url.endswith("/api/chats")
                              and response.status == 200, timeout=30000):
        page.click("#tabs button[data-tab='advise']")
    pending = page.get_by_role("button", name="Continue chat: Hello")
    pending.wait_for(timeout=30000)
    assert pending.get_attribute("data-matter-id") is None

    with page.expect_response(lambda response: response.url.endswith(
            f"/api/chats/{chat_id}") and response.status == 200, timeout=30000):
        pending.click()
    page.locator("#thread .brief").get_by_text(greeting, exact=True).wait_for()
    assert page.get_attribute("#pane-advise", "data-view") == "opening"
    assert not page.get_attribute("#pane-advise", "data-matter-id")
    assert page.locator("#rail-body .dispute-proposal-item").count() == 0
    assert page.is_visible("#composer")

    page.fill("#message", OPENING_MESSAGE)
    with page.expect_response(lambda response: response.url.endswith("/api/turn"),
                              timeout=30000) as turn_result:
        page.click("#send")
    assert turn_result.value.status == 200, turn_result.value.text()
    opened = turn_result.value.json()
    assert opened["chat_id"] == chat_id
    assert opened["matter_id"] == chat_matter_id(journey["advocate"], chat_id)
    matter = store.load(opened["matter_id"])
    assert [turn["message"] for turn in matter.brain_chat] == [greeting, OPENING_MESSAGE]
    assert not page.errors
