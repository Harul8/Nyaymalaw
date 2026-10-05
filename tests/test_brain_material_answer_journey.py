"""Checked account answers reach the shipped page and saved material record.

Model decisions are explicitly scripted. These two browser cases establish
routing, review handoffs, persistence and rendering, not semantic-model quality.
The browser talks to the real application; no HTTP response is mocked.
"""
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from assurance.journeys.served import PASSWORD, running
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.test_brain_material import Model, material
from tests.test_brain_material_answer_routing import answer_plan, operations
from tests.test_the_journey_login_to_logout import _sign_in

pytestmark = pytest.mark.journey
playwright_api = pytest.importorskip("playwright.sync_api")

ARTIFACTS = Path(__file__).resolve().parents[1] / "outputs/material-answer-routing-20261005"
ACCOUNT = "The delivery date is disputed. The delivery took place on 16 June."
ORIGINAL_DATE = "The delivery took place on 16 June."


class BrowserModel(Model):
    """Expose the adapter identity required by the real composition wrappers."""

    provider = "scripted"

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation == "decompose_disputes":
            payload = json.loads(prompt.user)
            data = {"plans": [{
                "subject_id": row["subject"]["id"],
                "queries": [{"text": row["subject"]["question"]}],
            } for row in payload["subjects"]]}
            return ModelResult(
                text=None, data=data, tier=tier, provider="scripted", model="offline",
                usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        return replace(result, provider="scripted")


@pytest.fixture
def page():
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        opened = context.new_page()
        errors = []
        opened.on("pageerror", lambda error: errors.append(str(error)))
        opened.errors = errors
        try:
            yield opened
        finally:
            context.close()
            browser.close()


def submit(page, message):
    page.fill("#message", message)
    with page.expect_response(lambda response: response.url.endswith("/api/turn"),
                              timeout=30000) as sent:
        page.click("#send")
    assert sent.value.status == 200, sent.value.text()
    response = sent.value.json()
    page.locator("#thread .turn").last.locator(".el > p.body").wait_for()
    page.wait_for_function("() => state.matterReady && !activeDelivery", timeout=30000)
    return response


def displayed_date(page, statement):
    page.locator("#matter-board-body .dispute-proposal-button").first.click()
    reader = page.locator("#dispute-reader")
    reader.wait_for(state="visible")
    reader.get_by_text(f"Event: {statement}", exact=True).wait_for()
    return reader


@pytest.mark.parametrize("outcome", ("correction", "no_change"))
def test_checked_material_answer_survives_reopening(
        page, tmp_path, scripted_application_environment, outcome):
    original = material("event", ORIGINAL_DATE, ORIGINAL_DATE, placement="matter")
    disputed = material("dispute", "Delivery date dispute", "The delivery date is disputed.")
    seed = answer_plan(
        ACCOUNT, reply="Your account reports delivery on 16 June.",
        candidates=(disputed, original), opening=True, intent="contribution")
    model = BrowserModel([seed])
    with running(tmp_path, model=model) as (box, base):
        actor = box.enrol()
        _sign_in(page, {"base": base, "advocate": actor, "password": PASSWORD})
        page.click("#home-start")
        opened = submit(page, ACCOUNT)
        matter_id, first_turn_id = opened["matter_id"], opened["turn_id"]
        store = box.application.store
        first_saved = deepcopy(store.load(matter_id).brain_chat[0])
        before = page.request.get(f"{base}/api/matters/{matter_id}").json()["material_record"]
        reader = displayed_date(page, ORIGINAL_DATE)
        reader.get_by_text(ORIGINAL_DATE, exact=True).wait_for()
        page.click("#dispute-reader-close")

        if outcome == "correction":
            message = "Correction: the delivery took place on 17 June."
            expected = "The delivery took place on 17 June."
            reply = "Your corrected account records delivery on 17 June."
            revised = material(
                "event", expected, message, relation="corrects", scope="current",
                placement="matter", related_material_ids=(f"{first_turn_id}:material:2",),
                references=({"turn_id": first_turn_id, "role": "advocate",
                             "quoted": ORIGINAL_DATE},))
            follow_up = answer_plan(message, reply=reply, candidates=(revised,),
                                    intent="contribution")
            expected_operations = [
                "interpret_conversation", "classify_account_sources", "extract_disputes",
                "extract_legal_details", "verify_material_grounding",
                "decompose_disputes", "continue_conversation", "verify_continuation"]
        else:
            message = "Check that your saved delivery description matches my account."
            expected = ORIGINAL_DATE
            reply = "The saved description matches your reported delivery date."
            follow_up = answer_plan(message, reply=reply, material_review=True)
            expected_operations = [
                "interpret_conversation", "classify_account_sources", "extract_disputes",
                "extract_legal_details", "decompose_disputes",
                "continue_conversation", "verify_continuation"]
        model.plans = iter([follow_up, follow_up])

        response = submit(page, message)

        assert operations(response) == expected_operations
        assert response["metrics"]["llm_calls"] == len(expected_operations)
        page.locator("#thread .turn").last.get_by_text(reply, exact=True).wait_for()
        saved = store.load(matter_id)
        assert saved.brain_chat[0] == first_saved
        assert [turn["message"] for turn in saved.brain_chat] == [ACCOUNT, message]
        assert saved.brain_chat[-1]["elements"] == response["elements"]
        fetched = page.request.get(f"{base}/api/matters/{matter_id}")
        assert fetched.status == 200, fetched.text()
        record = fetched.json()["material_record"]
        assert [row["statement"] for row in record["rows"]] == [expected]
        if outcome == "correction":
            assert len(record["history"]) == 2
            assert record["rows"][0]["related_material_ids"] == [
                f"{first_turn_id}:material:2"]
            assert record["rows"][0]["prior_references"] == [
                {"turn_id": first_turn_id, "role": "advocate", "quoted": ORIGINAL_DATE}]
        else:
            assert response["material"] == []
            assert record == before
        reader = displayed_date(page, expected)
        if outcome == "correction":
            assert reader.get_by_text(f"Event: {ORIGINAL_DATE}", exact=True).count() == 0
            reader.get_by_text(f"Earlier your message: {ORIGINAL_DATE}", exact=True).wait_for()
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ARTIFACTS / f"{outcome}-material.png"), full_page=True)
        page.click("#dispute-reader-close")

        page.reload()
        page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
        page.get_by_role("button", name="My work", exact=True).click()
        page.locator(f"#rail-body .row[data-matter-id='{matter_id}']").click()
        page.locator("#thread .turn").last.get_by_text(reply, exact=True).wait_for()
        displayed_date(page, expected)
        page.screenshot(path=str(ARTIFACTS / f"{outcome}-reopened.png"), full_page=True)
        reopened = page.request.get(f"{base}/api/matters/{matter_id}")
        assert reopened.status == 200, reopened.text()
        assert reopened.json()["material_record"] == record
        assert store.load(matter_id).brain_chat == saved.brain_chat
        assert not page.errors, page.errors
        receipt = {
            "boundary": "shipped browser, normal sign-in and authenticated HTTP endpoints",
            "model_decisions": "explicitly scripted; semantic model quality unqualified",
            "outcome": outcome, "opening_response": opened, "response": response,
            "before_material": before, "reopened_material": reopened.json()["material_record"],
            "saved_messages": [turn["message"] for turn in saved.brain_chat],
            "original_turn_unchanged": saved.brain_chat[0] == first_saved,
            "rendered_reply": page.locator("#thread .turn").last.inner_text(),
            "rendered_material": page.locator("#dispute-reader").inner_text(),
            "screenshots": [f"{outcome}-material.png", f"{outcome}-reopened.png"],
            "paid_calls": 0,
        }
        (ARTIFACTS / f"{outcome}-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
