"""Public-boundary bounded repair, confirmed persistence and historical replay."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.turn import BrainRefused, CONTRACT, saved_rows
from nm.shared.model_port import ModelError, SchemaViolation
from tests.test_current_brain_app import Harness, WiredModel, MIXED_MESSAGE, mixed_outputs, assert_ok


def missing_outputs():
    values = mixed_outputs(MIXED_MESSAGE)
    values[1]["objectives"] = []
    values[2]["unit_reviews"] = values[2]["unit_reviews"][:1]
    values[2]["readings"]["current:p2"][0]["represented_by"] = []
    repair = {"disputes": [], "objectives": deepcopy(mixed_outputs(MIXED_MESSAGE)[1]["objectives"])}
    return [*values, repair, mixed_outputs(MIXED_MESSAGE)[2]]


def test_missing_outcome_repaired_through_authenticated_api_then_reopens_and_replays_without_calls(tmp_path):
    model = WiredModel(*missing_outputs())
    app = Harness(tmp_path, model)
    try:
        first = assert_ok(app.post(MIXED_MESSAGE))
        assert first["metrics"]["llm_calls"] == 5
        assert [c[0].operation for c in model.calls] == ["label_message", "extract_disputes_objectives",
            "review_prepared_response", "extract_disputes_objectives", "review_prepared_response"]
        assert [e["text"] for e in first["elements"]] == ["Message received."]
        matter = app.held(first["chat_id"])
        row = saved_rows(matter, "adv_wiring")[0]
        assert row["contract"] == CONTRACT
        assert row["release"]["renderer_version"] == "disputes_objectives_release_v6"
        assert row["recovery"]["attempted"] and row["recovery"]["outcome"] == "ready"
        before = row["recovery"]["before"]
        assert before["release"]["state"] == "partial"
        assert before["preparation"]["proposal"]["disputes"] == row["preparation"]["proposal"]["disputes"]
        assert len(row["preparation"]["proposal"]["objectives"]) == 1
        reopened = assert_ok(app.client.get("/api/chats/" + first["chat_id"]))
        assert reopened["turn_count"] == 1 and reopened["turns"][0]["elements"] == first["elements"]
        assert "recovery" not in reopened["turns"][0]
        assert assert_ok(app.post(MIXED_MESSAGE)) == {**first, "replayed": True}
        assert len(model.calls) == 5
    finally:
        app.client.close()


def test_repair_provider_failure_preserves_confirmed_independent_scope_with_truthful_lineage(tmp_path):
    values = missing_outputs()[:3] + [ModelError("Provider unavailable")]
    model = WiredModel(*values)
    app = Harness(tmp_path, model)
    try:
        result = assert_ok(app.post(MIXED_MESSAGE))
        row = saved_rows(app.held(result["chat_id"]), "adv_wiring")[0]
        assert row["release"]["state"] == "partial" and result["metrics"]["llm_calls"] == 4
        assert row["recovery"]["outcome"] == "failed" and row["recovery"]["failure"] == "model_error"
        assert row["preparation"] == row["recovery"]["before"]["preparation"]
        assert result["material"] == [] and result["board_changes"] == [] and result["service_status"] is None
        assert assert_ok(app.post(MIXED_MESSAGE))["replayed"] is True and len(model.calls) == 4
    finally:
        app.client.close()


def test_one_shared_shape_correction_prevents_an_additional_semantic_repair(tmp_path):
    values = missing_outputs()[:3]
    values.insert(0, SchemaViolation("Invalid label"))
    app = Harness(tmp_path, WiredModel(*values))
    try:
        result = assert_ok(app.post(MIXED_MESSAGE))
        row = saved_rows(app.held(result["chat_id"]), "adv_wiring")[0]
        assert len(app.model.calls) == 4 and row["release"]["state"] == "partial"
        assert row["recovery"] == {"attempted": False, "before": None,
                                   "outcome": "allowance_unavailable", "failure": None}
    finally:
        app.client.close()


def test_unfixed_semantic_gap_stays_pending_after_five_calls(tmp_path):
    values = missing_outputs()
    values[3] = {"disputes": [], "objectives": []}
    values[4] = deepcopy(values[2])
    app = Harness(tmp_path, WiredModel(*values))
    try:
        result = assert_ok(app.post(MIXED_MESSAGE))
        row = saved_rows(app.held(result["chat_id"]), "adv_wiring")[0]
        assert len(app.model.calls) == 5 and row["recovery"]["outcome"] == "partial"
        assert row["preparation"]["proposal"]["objectives"] == []
        assert row["release"]["proof"]["readings"]["current:p2"][0]["represented_by"] == []
    finally:
        app.client.close()


def every_mark_record(prepared, selected):
    """A genuine disputes_objectives_v2 record: the same words, cut by that version's own rule."""
    from nm.brain.disputes_objectives import PASSAGE_LEGACY_CONTRACT, _check_item, _passage_input
    _, choices = _passage_input(prepared["sources"], PASSAGE_LEGACY_CONTRACT)
    catalogue = {source["id"]: source["message"] for source in prepared["sources"]}
    record = {**deepcopy(prepared), "contract": PASSAGE_LEGACY_CONTRACT}
    for rows in record["proposal"].values():
        for row in rows:
            passage = {**choices[selected[row["id"]]], "passage_id": selected[row["id"]], "purpose": "support"}
            row.update(_check_item({"description": row["description"], "passages": [passage],
                                    "uncertainty": row["uncertainty"]}, catalogue, PASSAGE_LEGACY_CONTRACT))
    return record


def test_previous_passage_turn_v3_keeps_its_old_release_and_replays_without_upgrade(tmp_path):
    from nm.brain.release import prepare_release
    from tests.test_new_brain_release import ReviewModel
    app = Harness(tmp_path, WiredModel(*mixed_outputs(MIXED_MESSAGE)))
    try:
        first = assert_ok(app.post(MIXED_MESSAGE))
        matter = app.held(first["chat_id"])
        rows = deepcopy(matter.brain_chat)
        row = rows[0]
        row["contract"] = "current_brain_turn_v3"
        row.pop("research")
        row.pop("recovery")
        row["preparation"] = every_mark_record(row["preparation"],
                                               {"dispute:1": "current:p1", "objective:1": "current:p2"})
        assert row["preparation"]["proposal"]["objectives"][0]["passages"][0]["quote"] == (
            " I want the deposit returned.")  # the v2 rule kept the space before a sentence
        row["release"] = prepare_release(ReviewModel({"greeting":False,"omissions":[],
            "unit_reviews":[{"unit_id":identity,"verdict":"supported","reason":"none"}
                for identity in ("dispute:1","objective:1")]}), row["preparation"], "mixed")
        assert row["release"]["renderer_version"] == "disputes_objectives_release_v2"
        historical = replace(matter, brain_chat=rows)
        app.store.commit(historical, expected_version=matter.version)
        assert saved_rows(app.held(first["chat_id"]), "adv_wiring")[0] == row
        replayed = assert_ok(app.post(MIXED_MESSAGE))
        assert replayed == {**first, "replayed":True} and len(app.model.calls) == 3
    finally:
        app.client.close()


@pytest.mark.parametrize("damage", ["false_completion", "changed_before_source", "lost_supported_peer", "missing_lineage"])
def test_recovery_replay_cannot_manufacture_completion_or_replace_prior_checked_work(tmp_path, damage):
    app = Harness(tmp_path, WiredModel(*missing_outputs()))
    try:
        result = assert_ok(app.post(MIXED_MESSAGE))
        matter = app.held(result["chat_id"])
        rows = deepcopy(matter.brain_chat)
        row = rows[0]
        if damage == "false_completion": row["recovery"]["outcome"] = "not_needed"
        elif damage == "changed_before_source": row["recovery"]["before"]["preparation"]["sources"][-1]["message"]["text"] = "Different account."
        elif damage == "missing_lineage": del row["recovery"]
        else: row["recovery"]["before"]["preparation"]["proposal"]["disputes"][0]["description"] = "Different prior supported work."
        with pytest.raises(BrainRefused):
            saved_rows(replace(matter, brain_chat=rows), "adv_wiring")
    finally:
        app.client.close()
