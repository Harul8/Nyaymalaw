"""Checked account answers reach the shipped page and saved material record.

Model decisions are explicitly scripted. These browser cases establish routing,
review handoffs, persistence, recovery accounting and rendering, not semantic quality.
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
from nm.shared.store_port import StaleWrite
from tests.test_brain_material import Model, material
from tests.test_brain_material_answer_routing import answer_plan, operations
from tests.test_the_journey_login_to_logout import _sign_in

pytestmark = pytest.mark.journey
playwright_api = pytest.importorskip("playwright.sync_api")

ARTIFACTS = Path(__file__).resolve().parents[1] / "outputs/material-recovery-accounting-20261005"
ACCOUNT = "The delivery date is disputed. The delivery took place on 16 June."
ORIGINAL_DATE = "The delivery took place on 16 June."


class BrowserModel(Model):
    """Expose the adapter identity required by the real composition wrappers."""

    provider = "scripted"

    def __init__(self, plans):
        super().__init__(plans)
        self.interpretations = []
        self.execution_inputs = []
        self.detail_inputs = []

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation == "extract_legal_details":
            self.detail_inputs.append(json.loads(prompt.user))
        if prompt.operation in ("continue_conversation", "verify_continuation"):
            payload = json.loads(prompt.user)
            supplied = payload["input"] if prompt.operation == "verify_continuation" else payload
            self.execution_inputs.append({
                "operation": prompt.operation,
                "execution": deepcopy(supplied["material_coverage"]["execution"]),
            })
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
        if prompt.operation == "interpret_conversation":
            self.interpretations.append(deepcopy(result.data))
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
    page.last_turn_request = deepcopy(sent.value.request.post_data_json)
    page.locator("#thread .turn").last.locator(".el > p.body").wait_for()
    page.wait_for_function("() => state.matterReady && !activeDelivery", timeout=30000)
    return response


def displayed_date(page, statement):
    page.locator("#matter-board-body .dispute-proposal-button").first.click()
    reader = page.locator("#dispute-reader")
    reader.wait_for(state="visible")
    reader.get_by_text(f"Event: {statement}", exact=True).wait_for()
    return reader


@pytest.mark.parametrize("outcome", ("correction", "no_change", "lost_ack"))
def test_checked_material_answer_survives_reopening(
        page, tmp_path, scripted_application_environment, monkeypatch, outcome):
    is_correction = outcome in ("correction", "lost_ack")
    original = material("event", ORIGINAL_DATE, ORIGINAL_DATE, placement="matter")
    disputed = material("dispute", "Delivery date dispute", "The delivery date is disputed.")
    seed = answer_plan(
        ACCOUNT, reply="Your account reports delivery on 16 June.",
        candidates=(disputed, original), opening=True, intent="contribution",
        material_purposes=("account_contribution",))
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

        if is_correction:
            message = "Correction: the delivery took place on 17 June."
            expected = "The delivery took place on 17 June."
            reply = "Your corrected account records delivery on 17 June."
            revised = material(
                "event", expected, message, relation="corrects", scope="current",
                placement="matter", related_material_ids=(f"{first_turn_id}:material:2",),
                references=({"turn_id": first_turn_id, "role": "advocate",
                             "quoted": ORIGINAL_DATE},))
            follow_up = answer_plan(
                message, reply=reply, candidates=(revised,), intent="contribution",
                material_purposes=("account_contribution",))
            expected_purposes = ["account_contribution"]
            expected_operations = [
                "interpret_conversation", "classify_account_sources", "extract_disputes",
                "extract_legal_details", "verify_material_grounding",
                "decompose_disputes", "continue_conversation", "verify_continuation"]
        else:
            message = "Check that your saved delivery description matches my account."
            expected = ORIGINAL_DATE
            reply = "The saved description matches your reported delivery date."
            follow_up = answer_plan(
                message, reply=reply, material_purposes=("interpretation_review",))
            expected_purposes = ["interpretation_review"]
            expected_operations = [
                "interpret_conversation", "classify_account_sources", "extract_disputes",
                "extract_legal_details", "decompose_disputes",
                "continue_conversation", "verify_continuation"]
        model.plans = iter([follow_up, follow_up])

        commit_versions = []
        if outcome == "lost_ack":
            original_commit = store.commit

            def commit_then_lose_acknowledgement(candidate, *, expected_version):
                original_commit(candidate, expected_version=expected_version)
                commit_versions.append(candidate.version)
                raise StaleWrite("Injected lost acknowledgement after successful commit")

            with monkeypatch.context() as patch:
                patch.setattr(store, "commit", commit_then_lose_acknowledgement)
                response = submit(page, message)
            assert response["replayed"] is True
        else:
            response = submit(page, message)
            assert response["replayed"] is False
        submitted_request = deepcopy(page.last_turn_request)

        assert operations(response) == expected_operations
        assert model.current_items[0]["material_purposes"] == expected_purposes
        assert len(model.interpretations) == 2
        assert all("material_review" not in plan for plan in model.interpretations)
        assert len(model.detail_inputs) == 2
        reader_input = model.detail_inputs[-1]
        original_row = before["rows"][0]
        supplied_row = next(row for row in reader_input["active_material"]
                            if row["id"] == original_row["id"])
        assert supplied_row["record_role"] == "nm_interpretation"
        for field in ("basis", "importance", "why_material", "prior_references"):
            assert supplied_row[field] == original_row[field]
        assert [(entry["turn_id"], entry["role"],
                 "".join(span["text"] for span in entry["source_spans"]))
                for entry in reader_input["earlier_conversation"]] == [
            (first_turn_id, "advocate", ACCOUNT),
            (first_turn_id, "nm", "Your account reports delivery on 16 June.")]
        assert "".join(span["text"] for span in reader_input["latest_message_spans"]) == message
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
        execution = response["material_coverage"]["execution"]
        assert execution == saved.brain_chat[-1]["response"]["material_coverage"]["execution"]
        assert execution["contract"] == "material_execution_v1"
        assert execution["owner"] == {
            "matter_id": matter_id, "advocate_id": actor, "turn_id": response["turn_id"],
            "offer_digest": saved.brain_chat[-1]["offer_digest"],
        }
        assert execution["expected_version"] == opened["matter_version"]
        assert execution["resulting_version"] == saved.version
        if outcome == "lost_ack":
            assert commit_versions == [saved.version]
        assert execution["persistence"] == "committed"
        assert execution["semantic_coverage"] == "unassessed"
        assert execution["requests"][0]["material_purposes"] == expected_purposes
        assert all(request["fulfillment"] == "unassessed" for request in execution["requests"])
        stages = execution["stages"]
        assert stages["source_classification"]["state"] == "returned"
        assert stages["dispute_extraction"] == {"state": "returned", "proposals": 0}
        assert stages["detail_extraction"] == {
            "state": "returned", "proposals": 1 if is_correction else 0}
        assert stages["detail_review"]["state"] == (
            "checked" if is_correction else "no_candidates")
        effects = execution["effects"]["details"]
        before_ids = {row["id"] for row in before["rows"]}
        after_ids = {row["id"] for row in record["rows"]}
        assert set(effects["activated_record_ids"]) == after_ids - before_ids
        assert set(effects["retired_record_ids"]) == before_ids - after_ids
        assert effects["held_record_ids"] == effects["outside_owned_record_ids"] == []
        assert execution["effects"]["disputes"]["activated_record_ids"] == []
        assert execution["effects"]["disputes"]["retired_record_ids"] == []
        assert execution["effects"]["disputes"]["operations"] == []
        prepared = {**deepcopy(execution), "persistence": "prepared_for_commit"}
        model_inputs = [entry for entry in model.execution_inputs
                        if entry["execution"]["owner"]["turn_id"] == response["turn_id"]]
        assert [entry["operation"] for entry in model_inputs] == [
            "continue_conversation", "verify_continuation"]
        assert all(entry["execution"] == prepared for entry in model_inputs)
        if is_correction:
            assert len(record["history"]) == 2
            assert record["rows"][0]["related_material_ids"] == [
                f"{first_turn_id}:material:2"]
            assert record["rows"][0]["prior_references"] == [
                {"turn_id": first_turn_id, "role": "advocate", "quoted": ORIGINAL_DATE}]
            assert effects["operations"] == [{
                "result_id": record["rows"][0]["id"], "relation": "corrects",
                "target_record_ids": [f"{first_turn_id}:material:2"],
                "retired_target_ids": [f"{first_turn_id}:material:2"],
                "source_references": [
                    {"turn_id": response["turn_id"], "role": "advocate", "quoted": message},
                    {"turn_id": first_turn_id, "role": "advocate", "quoted": ORIGINAL_DATE}],
            }]
        else:
            assert response["material"] == []
            assert record == before
            assert effects["operations"] == []
        reader = displayed_date(page, expected)
        if is_correction:
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
        interpreted_count = len(model.interpretations)
        execution_input_count = len(model.execution_inputs)
        detail_input_count = len(model.detail_inputs)
        replay = page.evaluate("""body => api('/api/turn', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        })""", submitted_request)
        assert replay["replayed"] is True
        assert replay["metrics"]["llm_calls"] == 0
        assert replay["material_coverage"]["execution"] == execution
        assert len(model.interpretations) == interpreted_count
        assert len(model.execution_inputs) == execution_input_count
        assert len(model.detail_inputs) == detail_input_count
        assert store.load(matter_id).brain_chat == saved.brain_chat
        assert not page.errors, page.errors
        health = page.request.get(f"{base}/api/health").json()
        assert health["code_state"] == "current", health
        receipt = {
            "boundary": "shipped browser, normal sign-in and authenticated HTTP endpoints",
            "model_decisions": "explicitly scripted; semantic model quality unqualified",
            "outcome": outcome, "opening_response": opened, "response": response,
            "lost_ack_commit_versions": commit_versions,
            "declared_interpretations": model.interpretations,
            "reader_input": reader_input,
            "execution_inputs": model_inputs, "execution": execution,
            "replayed_execution": replay["material_coverage"]["execution"],
            "replay_model_calls": replay["metrics"]["llm_calls"],
            "code_identity": {key: health[key] for key in ("serving", "tree", "code_state")},
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
