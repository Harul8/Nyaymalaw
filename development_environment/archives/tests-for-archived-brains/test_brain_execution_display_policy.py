"""Record-result display follows observed work and preserves saved policy history.

Public writers return raw evidence expressions. Every model result is an
explicit offline fixture; no provider or browser is used.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as boundary
from nm.brain.execution_contracts import ExecutionEvidenceInvalid
from tests.test_brain_continuation_service import send
from tests.test_brain_evidence_rendering_public import RawExpressionModel, raw_unit, reopened
from tests.test_brain_scope_span_public import (
    CUSTODY,
    INSTRUCTION,
    ORIGINAL,
    REVISED,
    SpanNeighbourModel,
    correction,
    route,
    saved_and_replayed,
    seed,
    writer,
)
from tests.test_brain_turn import plan

POLICY = "requested_record_work_v2"


def footer(answer):
    receipt = answer["material_coverage"]["execution"]
    return [element for element in answer["elements"]
            if element.get("material_execution_id") == receipt["id"]]


def display_receipt(*, required=False, ran=False, changed=False, policy=POLICY):
    """Only the observable display inputs; no fabricated semantic judgment."""
    effects = {kind: {"after_held_record_ids": []} for kind in ("disputes", "details")}
    value = {
        "id": "mex_display_fixture", "display_policy": policy,
        "material_selected": required,
        "requests": [{"request_index": 0, "record_requirement": {"kind": "none"}}],
        "stages": {name: {"state": "returned" if ran else "not_run"}
                   for name in ("source_classification", "dispute_extraction", "dispute_review",
                                "detail_extraction", "detail_review")},
        "effects": effects, "record_changes": [],
    }
    if changed:
        value["record_changes"] = [{
            "effect_id": "effect_owned", "kind": "details", "relation": "new",
            "before_records": [], "after_record": {"statement": ORIGINAL},
        }]
    for name in ("dispute_review", "detail_review"):
        value["stages"][name]["account_coverage"] = {"state": "complete"}
    return value


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("ran", [False, True])
@pytest.mark.parametrize("changed", [False, True])
def test_footer_appears_for_observed_record_work_only(required, ran, changed):
    evidence = display_receipt(required=required, ran=ran, changed=changed)
    original = deepcopy(evidence)
    rendered = boundary._execution_display(evidence)
    assert (rendered is not None) == (required or ran or changed)
    assert evidence == original
    if rendered is not None:
        assert rendered["contract"] == "material_result_display_v2"
        assert rendered["receipt_id"] == evidence["id"]
        assert rendered["element"]["disclosure"] is required
        assert rendered["element"]["text"] == (
            "New entry: " + ORIGINAL if changed else "No changes were made to the saved record.")


def test_typed_requested_work_alone_requires_a_footer_without_claiming_it_ran():
    evidence = display_receipt()
    evidence["requests"][0]["record_requirement"] = {"kind": "review"}
    rendered = boundary._execution_display(evidence)
    assert rendered["element"]["text"] == "No changes were made to the saved record."
    assert rendered["element"]["disclosure"] is True
    assert all(stage["state"] == "not_run" for stage in evidence["stages"].values())


def test_pure_greeting_has_no_record_footer_and_saved_replay_runs_no_models(
        client, wired, monkeypatch):
    message, identity = "Hello.", "display-pure-greeting"
    model = RawExpressionModel([plan(message)], [lambda payload: {"units": [raw_unit(
        payload, operator="acknowledgment", kind="acknowledgment", all_sources=False)]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, identity)
    execution = answer["material_coverage"]["execution"]
    assert answer["blocked"] is False
    assert execution["display_policy"] == POLICY
    assert execution["display"] is None
    assert execution["record_changes"] == []
    assert all(stage["state"] == "not_run" for stage in execution["stages"].values())
    assert footer(answer) == []
    assert [element["text"] for element in answer["elements"]] == ["I have your message."]
    saved = reopened(wired, answer)
    calls, version = len(model.calls), saved.version
    replay = send(client, message, identity)
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    assert replay["elements"] == answer["elements"]
    assert len(model.calls) == calls and reopened(wired, answer).version == version
    assert saved.brain_chat[-1]["response"]["elements"] == answer["elements"]


def test_actual_reading_and_saved_changes_have_a_code_footer(
        client, wired, monkeypatch):
    opened, records, _target, _custody = seed(client, wired, monkeypatch, "display-actual-work")
    execution = opened["material_coverage"]["execution"]
    displayed, = footer(opened)
    assert execution["display_policy"] == POLICY
    assert execution["stages"]["detail_extraction"]["state"] == "returned"
    assert len(execution["record_changes"]) == len(records) == 2
    assert displayed == execution["display"]["element"]
    assert displayed["text"] == "New entry: " + ORIGINAL + "\nNew entry: " + CUSTODY
    assert reopened(wired, opened).brain_chat[-1]["response"]["elements"] == opened["elements"]


@pytest.mark.parametrize("fault,target_words", [
    ("wrong_owned_target", CUSTODY), ("wrong_relation", ORIGINAL),
])
def test_held_scope_footer_names_the_exact_original_target_and_requests_confirmation(
        client, wired, monkeypatch, fault, target_words):
    identity = "display-held-" + fault
    opened, before, target, custody = seed(client, wired, monkeypatch, identity)
    message = INSTRUCTION + " " + REVISED
    proposed = correction(identity, custody if fault == "wrong_owned_target" else target,
                          relation="adds" if fault == "wrong_relation" else "corrects")
    model = SpanNeighbourModel(
        [route(message, target)], [lambda payload: writer(payload, fulfilled=False)],
        records=[proposed], selected_source="L2")
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, identity, opened=opened)
    execution = answer["material_coverage"]["execution"]
    displayed, = footer(answer)
    assert answer["blocked"] is False
    assert execution["record_changes"] == []
    assert execution["requests"][0]["fulfillment"] == "unfinished"
    assert f'whose original source reads: “{target_words}”' in displayed["text"]
    assert "Please confirm the record and the requested change." in displayed["text"]
    assert "The record reading remains unfinished." in displayed["text"]
    saved = saved_and_replayed(client, wired, model, answer, opened, identity, message)
    assert boundary._current_records(wired.store, saved)[0].open_material == before


@pytest.mark.parametrize("policy", ["unowned_display_policy", True, {}])
def test_unknown_display_policy_is_rejected_instead_of_using_legacy_default(policy):
    with pytest.raises(ExecutionEvidenceInvalid, match="display policy"):
        boundary._execution_display(display_receipt(policy=policy))


def test_durable_unknown_display_policy_refuses_replay_without_models_or_writes(
        client, wired, monkeypatch):
    message, identity = "Hello.", "display-durable-unknown"
    model = RawExpressionModel([plan(message)], [lambda payload: {"units": [raw_unit(
        payload, operator="acknowledgment", kind="acknowledgment", all_sources=False)]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    answer = send(client, message, identity)
    saved = reopened(wired, answer)
    rows = deepcopy(saved.brain_chat)
    rows[-1]["response"]["material_coverage"]["execution"]["display_policy"] = "unknown"
    wired.store.commit(replace(saved, brain_chat=rows, version=saved.version + 1),
                       expected_version=saved.version)
    before, calls = deepcopy(reopened(wired, answer)), len(model.calls)
    replay = client.post("/api/turn", json={"message": message, "turn_id": identity})
    assert replay.status_code == 409, replay.text
    assert "elements" not in replay.json()
    assert len(model.calls) == calls and reopened(wired, answer) == before


def test_historical_unstamped_greeting_keeps_its_original_footer_on_zero_call_replay(
        client, wired, monkeypatch):
    message, identity = "Hello.", "display-legacy-history"
    model = RawExpressionModel([plan(message)], [lambda payload: {"units": [raw_unit(
        payload, operator="acknowledgment", kind="acknowledgment", all_sources=False)]}])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    current_factory = boundary._material_execution

    def historical_factory(*args, **kwargs):
        # Reproduce the previous unstamped producer before saving and sealing,
        # rather than mutating a newer saved reply or its receipt digest.
        execution = current_factory(*args, **kwargs)
        execution.pop("display_policy")
        return execution

    monkeypatch.setattr(boundary, "_material_execution", historical_factory)
    answer = send(client, message, identity)
    execution = answer["material_coverage"]["execution"]
    assert "display_policy" not in execution
    assert execution["display"]["contract"] == "material_result_display_v1"
    monkeypatch.setattr(boundary, "_material_execution", current_factory)
    expected, calls = deepcopy(reopened(wired, answer)), len(model.calls)
    replay = send(client, message, identity)
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    assert replay["elements"] == expected.brain_chat[-1]["response"]["elements"]
    displayed, = footer(replay)
    assert displayed["text"] == "No changes were made to the saved record."
    assert len(model.calls) == calls and reopened(wired, answer) == expected
