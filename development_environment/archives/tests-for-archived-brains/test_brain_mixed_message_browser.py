"""Multiple authored requests survive the browser/brain/save/reopen boundary.

Routing and review meanings are supplied by fixtures. This proves the deployed
handoffs and call sharing, not a real model's ability to discover each request.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from nm.brain import turn as boundary
from tests.test_brain_context_browser import (
    _assert_reopened_reply_words,
    _history,
    _open_saved_matter,
    _saved,
    _send,
)
from tests.test_brain_context_browser import (
    journey as journey,
)
from tests.test_brain_context_browser import (
    page as page,
)
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit
from tests.test_brain_pressure_release import BASE_TURN, OLD_DATE, OLD_RIG, ORIGINAL
from tests.test_brain_turn import plan
from tests.test_the_journey_login_to_logout import _sign_in

pytestmark = pytest.mark.journey
ARTIFACTS = Path(__file__).resolve().parents[1] / "outputs" / "brain-mixed-message-20261007"

MIXED = (
    "Hello again. First, repeat the northern depot arrival date. "
    "Separately, repeat the southern depot arrival date. "
    "Do not change the saved account. I may ask for legal advice later, "
    "but do not start it now."
)
REQUESTS = (
    "Repeat the northern depot arrival date without changing the saved account.",
    "Repeat the southern depot arrival date without changing the saved account.",
)
FOLLOWUP = "Repeat only the second date again, leaving the account unchanged."


def _route(requests):
    def interpreted(payload):
        proposed = plan(requests[0], scope="current", relation="continues")
        proposed["items"] = [plan(request, scope="current", relation="continues")["items"][0]
                             for request in requests]
        proposed["active_work_after"] = payload["current_work"]
        return proposed
    return interpreted


def _reply(original_passages):
    def written(payload):
        items = payload["work_items"]
        assert len(items) == len(original_passages)
        original = next(row for row in payload["earlier_conversation"]
                        if row["turn_id"] == BASE_TURN and row["role"] == "advocate")
        units = []
        for item, quotation in zip(items, original_passages, strict=True):
            matching = [span["id"] for span in original["source_spans"]
                        if span["text"].strip() == quotation]
            assert len(matching) == 1
            unit = raw_unit({**payload, "work_items": [item]})
            # Fixture meaning: each requested factual repetition is completely
            # supplied by one exact earlier advocate passage. No legal finding,
            # new fact, mutation or separately deferred instruction is proposed.
            unit["blocks"] = unit["blocks"][:1]
            unit["blocks"][0]["evidence_expression"]["source_ids"] = matching
            unit["sufficiency"] = {"status": "complete", "block_id": "main"}
            units.append(unit)
        return {"units": units}
    return written


def test_two_factual_outcomes_share_calls_preserve_deferred_law_and_followup_context(
        page, journey, monkeypatch):
    model = RawExpressionModel(
        [_route(REQUESTS), _route((REQUESTS[1],))],
        [_reply((OLD_DATE, OLD_RIG)), _reply((OLD_RIG,))],
    )
    monkeypatch.setattr(journey["box"].application, "_model_for",
                        lambda *args, **kwargs: model)
    store = journey["box"].application.store
    baseline = deepcopy(_saved(journey, journey["seeded"]))
    baseline_material = deepcopy(boundary._current_records(store, baseline)[0].open_material)
    _sign_in(page, journey)
    _open_saved_matter(page, journey)

    first = _send(page, MIXED)
    requests = first["material_coverage"]["execution"]["requests"]
    assert [row["request_index"] for row in requests] == [0, 1]
    assert [row["request"] for row in requests] == list(REQUESTS)
    assert all(row["record_requirement"]["kind"] == "none" for row in requests)
    assert all(row["material_purposes"] == [] for row in requests)
    assert [row["request_index"] for row in first["continuation"]["units"]] == [0, 1]
    assert [row["state"] for row in first["continuation"]["coverage"]] == ["ok", "ok"]
    assert [row["continuation_request_index"] for row in first["elements"]] == [0, 1]
    assert OLD_DATE in first["elements"][0]["text"]
    assert OLD_RIG in first["elements"][1]["text"]
    assert first["metrics"]["llm_calls"] == 3
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    interpreter = model.calls[0][1]
    assert interpreter["latest_message"] == MIXED
    assert interpreter["earlier_conversation"] == _history(baseline)
    writer = model.calls[1][1]
    assert [row["request"] for row in writer["work_items"]] == list(REQUESTS)
    assert all(row["response_basis"] == "conversation_record"
               and row["research_question"] == "" for row in writer["work_items"])
    assert [row["request_index"] for row in model.calls[2][1]["units"]] == [0, 1]
    assert all(row["state"] == "not_run"
               for row in first["material_coverage"]["execution"]["stages"].values())

    saved = deepcopy(_saved(journey, first))
    assert saved.brain_chat[-1]["response"]["research_reads"] == []
    assert saved.brain_chat[:-1] == baseline.brain_chat
    assert saved.brain_chat[-1]["message"] == MIXED
    saved_execution = saved.brain_chat[-1]["response"]["material_coverage"]["execution"]
    assert saved_execution["requests"] == requests
    assert saved.brain_chat[-1]["response"]["continuation"] == first["continuation"]
    assert boundary._current_records(store, saved)[0].open_material == baseline_material

    page.reload()
    page.wait_for_selector("#masthead:not([hidden])")
    _open_saved_matter(page, journey)
    _assert_reopened_reply_words(page, saved)
    assert page.locator("#thread .brief").all_text_contents() == [ORIGINAL, MIXED]
    assert _saved(journey, first) == saved
    assert len(model.calls) == 3  # Reopening is a read, not another model activity.

    second = _send(page, FOLLOWUP)
    assert second["metrics"]["llm_calls"] == 3
    assert [operation for operation, _ in model.calls[3:]] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    followup_input = model.calls[3][1]
    assert followup_input["latest_message"] == FOLLOWUP
    assert followup_input["earlier_conversation"] == _history(saved)
    followup_requests = second["material_coverage"]["execution"]["requests"]
    assert [row["request"] for row in followup_requests] == [REQUESTS[1]]
    assert len(second["continuation"]["units"]) == len(second["elements"]) == 1
    assert OLD_RIG in second["elements"][0]["text"]
    final = _saved(journey, second)
    assert final.brain_chat[-1]["response"]["research_reads"] == []
    assert final.brain_chat[:-1] == saved.brain_chat
    assert boundary._current_records(store, final)[0].open_material == baseline_material
    assert page.locator("#thread .brief").all_text_contents() == [ORIGINAL, MIXED, FOLLOWUP]
    assert not page.errors
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.locator("#thread .turn").last.scroll_into_view_if_needed()
    page.screenshot(path=str(ARTIFACTS / "browser.png"), full_page=True)
