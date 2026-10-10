"""Real Chrome context journeys with only scripted provider decisions.

The browser submits every tested message through the shipped composer. The
temporary encrypted store and captured interpreter inputs establish exact text,
history, isolation and reopening; these tests do not measure model judgment.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from assurance.journeys.served import PASSWORD, running
from nm.brain import turn as boundary
from nm.brain.turn import BrainService, BrainTurn, chat_matter_id
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit
from tests.test_brain_pressure_release import BASE_TURN, ORIGINAL, PassageModel, initial_plan
from tests.test_brain_turn import plan
from tests.test_chat_first_opening import page as page  # shared Chrome fixture
from tests.test_the_journey_login_to_logout import _sign_in, playwright_api

pytestmark = pytest.mark.journey
ARTIFACTS = Path(__file__).resolve().parents[1] / "outputs" / "brain-context-20261007"


@pytest.fixture
def journey(tmp_path):
    # A pre-existing matter is created through the actual brain/save boundary;
    # all subsequent inputs are sent by the browser, never a direct API client.
    with running(tmp_path / "served", model=RawExpressionModel([], [])) as (box, base):
        advocate = box.enrol()
        seeded = BrainService(
            box.application.store, PassageModel([initial_plan()], controls=[{}])
        ).run(BrainTurn(advocate, ORIGINAL, BASE_TURN,
                        offer={"message": ORIGINAL})).as_dict()
        assert seeded["blocked"] is False and seeded["matter_id"]
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD, "seeded": seeded}


def _route(message, relation="continues"):
    def interpret(payload):
        value = plan(message, relation=relation)
        value["active_work_after"] = payload["current_work"]
        return value
    return interpret


def _reply(payload):
    unit = raw_unit(payload)
    # Empty whitespace spans remain in the transcript; they are not assertions
    # selected by this scripted writer as an account.
    nonblank = {row["id"] for row in payload["latest_message_spans"] if row["text"].strip()}
    for block in unit["blocks"]:
        expression = block["evidence_expression"]
        expression["source_ids"] = [identity for identity in expression["source_ids"]
                                    if identity in nonblank]
    if "$no_task" in payload["work_items"][0]["work_choices"]:
        unit["work_selector"] = "$no_task"
    return {"units": [unit]}


def _script(journey, monkeypatch, routes):
    model = RawExpressionModel(routes, [_reply] * len(routes))
    monkeypatch.setattr(journey["box"].application, "_model_for",
                        lambda *args, **kwargs: model)
    return model


def _saved(journey, answer):
    identity = answer["matter_id"] or chat_matter_id(journey["advocate"], answer["chat_id"])
    return journey["box"].application.store.load(identity)


def _history(saved):
    return [message for row in saved.brain_chat for message in (
        {"turn_id": row["turn_id"], "role": "advocate", "text": row["message"]},
        {"turn_id": row["turn_id"], "role": "nm", "text": "\n".join(
            element["text"] for element in row["elements"] if element["text"].strip())},
    )]


def _open_saved_matter(page, journey):
    page.click("#tabs button[data-tab='advise']")
    matter_id = journey["seeded"]["matter_id"]
    page.locator(f"#rail-body [data-matter-id='{matter_id}']").click()
    playwright_api.expect(page.locator("#pane-advise")).to_have_attribute(
        "data-matter-id", matter_id)
    playwright_api.expect(page.locator("#matter-board")).to_be_visible()
    playwright_api.expect(page.locator("#thread .brief").first).to_have_text(ORIGINAL)
    playwright_api.expect(page.locator("#message")).to_be_enabled()


def _send(page, message):
    playwright_api.expect(page.locator("#send")).to_be_enabled()
    page.fill("#message", message)
    # Textarea normalises CRLF by HTML design; these inputs use LF, so the
    # exact string here must travel unchanged across composer/API/storage.
    assert page.input_value("#message") == message
    with page.expect_response(lambda response: response.url.endswith("/api/turn"),
                              timeout=30000) as result:
        page.click("#send")
    response = result.value
    assert response.status == 200, response.text()
    answer = response.json()
    assert answer["blocked"] is False, answer
    playwright_api.expect(page.locator("#send")).to_be_enabled()
    assert page.locator("#thread .brief").last.text_content() == message
    assert page.locator("#thread .turn").last.locator(".el > .body").all_text_contents() == [
        element["text"] for element in answer["elements"]]
    assert page.locator("#thread .failure").count() == 0
    return answer


def _capture(page, name):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / name), full_page=True)


def _assert_reopened_reply_words(page, saved):
    turns = page.locator("#thread .turn")
    assert turns.count() == len(saved.brain_chat)
    for index, row in enumerate(saved.brain_chat):
        assert turns.nth(index).locator(".el > .body").all_text_contents() == [
            element["text"] for element in row["elements"]]


def test_existing_matter_keeps_complete_context_across_diversions_and_reopen(
        page, journey, monkeypatch):
    messages = [
        "  Hello again.\nI am still here.  ",
        "A separate question: what is the capital of France?",
        "Please return to examining the earlier account.",
    ]
    model = _script(journey, monkeypatch, [
        _route(messages[0], "aside"), _route(messages[1], "aside"),
        _route(messages[2]),
    ])
    _sign_in(page, journey)
    _open_saved_matter(page, journey)
    store = journey["box"].application.store
    saved = _saved(journey, journey["seeded"])
    material = deepcopy(boundary._current_records(store, saved)[0].open_material)
    for message in messages:
        previous = deepcopy(saved)
        expected = _history(previous)
        start = len(model.calls)
        answer = _send(page, message)
        assert answer["matter_id"] == journey["seeded"]["matter_id"]
        calls = model.calls[start:]
        interpreted = next(payload for operation, payload in calls
                           if operation == "interpret_conversation")
        assert interpreted["latest_message"] == message
        assert interpreted["earlier_conversation"] == expected
        assert [operation for operation, _ in calls] == [
            "interpret_conversation", "continue_conversation", "verify_continuation"]
        saved = _saved(journey, answer)
        assert saved.brain_chat[:-1] == previous.brain_chat
        assert saved.brain_chat[-1]["message"] == message
        assert boundary._current_records(store, saved)[0].open_material == material
        assert answer["metrics"]["llm_calls"] == 3
        playwright_api.expect(page.locator("#matter-board")).to_be_visible()

    before_calls = len(model.calls)
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])")
    _open_saved_matter(page, journey)
    assert page.locator("#thread .brief").all_text_contents() == [ORIGINAL, *messages]
    _assert_reopened_reply_words(page, saved)
    assert _saved(journey, journey["seeded"]) == saved
    assert len(model.calls) == before_calls
    assert not page.errors
    _capture(page, "browser-matter.png")


def test_fresh_chat_is_empty_and_keeps_exact_words_without_old_matter_leakage(
        page, journey, monkeypatch):
    first = "\n  Hello.\t\n"
    followup = " \tPlease retain my original wording.\n"
    model = _script(journey, monkeypatch, [_route(first, "new"), _route(followup)])
    original = deepcopy(_saved(journey, journey["seeded"]))
    _sign_in(page, journey)
    _open_saved_matter(page, journey)
    page.click("#tabs button[data-tab='home']")
    page.click("#home-start")
    assert page.get_attribute("#pane-advise", "data-view") == "opening"
    assert not page.get_attribute("#pane-advise", "data-matter-id")
    assert page.is_hidden("#matter-board")
    assert page.is_hidden("#intake")
    assert page.locator("#thread .turn").count() == 0
    assert page.input_value("#message") == ""
    assert page.is_visible("#composer")
    conversation = page.locator("#pane-advise .conversation").bounding_box()
    composer = page.locator("#composer").bounding_box()
    assert conversation and composer
    assert abs(composer["x"] + composer["width"] / 2
               - conversation["x"] - conversation["width"] / 2) < 12
    assert abs(composer["y"] + composer["height"] / 2
               - conversation["y"] - conversation["height"] / 2) < 60
    _capture(page, "browser-empty.png")

    opened = _send(page, first)
    assert opened["matter_id"] is None
    first_saved = deepcopy(_saved(journey, opened))
    first_input = next(payload for operation, payload in model.calls
                       if operation == "interpret_conversation")
    assert first_input["latest_message"] == first
    assert first_input["earlier_conversation"] == []
    assert first_input["current_work"] == ""
    assert first_input["target_catalogue"] == []
    assert first_input["record_history"] == []
    assert first_saved.brain_chat[0]["message"] == first
    assert page.is_hidden("#matter-board")

    before_calls = len(model.calls)
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])")
    page.click("#tabs button[data-tab='advise']")
    page.locator("#rail-body [aria-label^='Continue chat:']").click()
    playwright_api.expect(page.locator("#thread .brief")).to_have_count(1)
    assert page.locator("#thread .brief").text_content() == first
    _assert_reopened_reply_words(page, first_saved)
    assert page.is_hidden("#matter-board")
    assert len(model.calls) == before_calls

    answered = _send(page, followup)
    assert answered["chat_id"] == opened["chat_id"]
    assert answered["matter_id"] is None
    interpreted = [payload for operation, payload in model.calls
                   if operation == "interpret_conversation"][-1]
    assert interpreted["latest_message"] == followup
    assert interpreted["earlier_conversation"] == _history(first_saved)
    assert interpreted["target_catalogue"] == []
    assert interpreted["record_history"] == []
    saved = _saved(journey, answered)
    assert [row["message"] for row in saved.brain_chat] == [first, followup]
    assert page.locator("#thread .brief").all_text_contents() == [first, followup]
    assert _saved(journey, journey["seeded"]) == original
    assert opened["metrics"]["llm_calls"] == answered["metrics"]["llm_calls"] == 3
    assert not page.errors
    _capture(page, "browser.png")
