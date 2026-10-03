"""One model choice owns work association without changing durable history."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nm.brain.conversation import WorkItem
from nm.brain.history import IncompleteConversation
from nm.brain.turn import chat_matter_id
from nm.brain.work_state import project_work
from nm.shared.model_port import SchemaViolation, require_schema
from tests.test_brain_continuation import (
    ContinuationModel,
    _continue,
    _operation_names,
    conversation_plan,
    unit,
    verdict,
)
from tests.test_brain_continuation_service import PublicContinuationModel, send
from tests.test_brain_turn import plan


def selection(proposed, value):
    result = deepcopy(proposed)
    result.pop("work")
    result["work_selector"] = value
    return result


def test_public_requested_clarification_creates_one_task_and_contribution_creates_none(
        client, wired, monkeypatch):
    first_words = ("A person mentioned two records without identifying either. "
                   "Help me clarify what to ask.")
    later_words = "I only want to add that I have not inspected either record."
    opening = plan("Clarify which record the person meant.", step="clarify")
    opening["items"][0]["clarification"] = "Which record did the person mean?"
    contribution = plan("Retain the reported inspection limit.", step="legal_work",
                        relation="continues", reply="I will retain the attributed limit.")
    contribution["items"][0]["intent"] = "contribution"
    requested = unit(text="You report that two records were mentioned without identification.",
                     question="Which two records did the person mention?")
    requested["blocks"][2]["text"] = (
        "The records remain unidentified, so the requested clarification needs that distinction.")
    reported = unit(text="You now report that you have not inspected either record.")
    reported["blocks"] = [reported["blocks"][0]]
    reported.update(questions=[], sufficiency={"status": "complete", "block_id": "account-0"})

    def choose_new(payload):
        assert payload["work_items"][0]["work_choices"] == ["$new_task"]
        assert payload["progress"]["rows"] == []
        return {"units": [selection(requested, "$new_task")]}

    def choose_none(payload):
        choices = payload["work_items"][0]["work_choices"]
        assert "$no_task" in choices and "$new_task" not in choices
        assert len([row for row in payload["progress"]["rows"] if row["kind"] == "task"]) == 1
        return {"units": [selection(reported, "$no_task")]}

    model = PublicContinuationModel([opening, contribution], [choose_new, choose_none])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "one-work-request")
    later = send(client, later_words, "one-work-contribution", opened=first)
    replay = send(client, later_words, "one-work-contribution", opened=first)

    assert first["metrics"]["llm_calls"] == later["metrics"]["llm_calls"] == 3
    assert replay["metrics"]["llm_calls"] == 0
    assert first["matter_id"] is later["matter_id"] is None
    first_unit = first["continuation"]["units"][0]
    later_unit = later["continuation"]["units"][0]
    assert first_unit["work"]["create"] is True and first_unit["work"]["existing_id"] == ""
    assert later_unit["work"]["create"] is False and later_unit["work"]["existing_id"] == ""
    assert "work_selector" not in first_unit and "work_selector" not in later_unit
    saved = wired.store.load(chat_matter_id("adv_demo", later["chat_id"]))
    assert [row["message"] for row in saved.brain_chat] == [first_words, later_words]
    progress = project_work(saved)
    tasks = [row for row in progress["rows"] if row["kind"] == "task"]
    assert len(tasks) == 1 and tasks[0]["status"] == "pending"
    assert any(row["kind"] == "question" and row["status"] == "pending"
               for row in progress["rows"])
    schema = next(schema for operation, schema in model.schemas
                  if operation == "continue_conversation")
    model_unit = schema["properties"]["units"]["items"]
    assert "work" not in model_unit["properties"]
    assert model_unit["properties"]["work_selector"]["enum"] == ["$new_task"]
    with pytest.raises(SchemaViolation):
        require_schema({"units": [selection(requested, "$no_task")]}, schema)


@pytest.mark.parametrize("intent,wrong_mode", [
    ("request", "$no_task"), ("contribution", "$new_task")])
def test_mixed_mode_cannot_borrow_another_requests_choice_or_enter_partial_retention(
        intent, wrong_mode):
    other_intent = "contribution" if intent == "request" else "request"
    items = tuple(WorkItem(
        request="Address the attributed contribution.", relation="continues",
        matter_scope="none", priority="ordinary", next_step="legal_work", intent=value)
        for value in (intent, other_intent))
    bad = unit(text="You report a changed instruction.")
    bad["blocks"] = [bad["blocks"][0], bad["blocks"][2]]
    bad["blocks"][1]["text"] = "The instruction remains reported and unassessed."
    bad.update(questions=[], sufficiency={"status": "partial", "block_id": "limit-0"})
    peer = unit(1, text="You report a changed instruction.")
    peer["blocks"] = [peer["blocks"][0]]
    peer.update(questions=[], sufficiency={"status": "complete", "block_id": "account-1"})
    good_mode = "$no_task" if other_intent == "contribution" else "$new_task"
    model = ContinuationModel([
        {"units": [selection(bad, wrong_mode), selection(peer, good_mode)]}, verdict(1),
        {"units": [selection(bad, wrong_mode)]}])

    result = _continue(model, latest="I report a changed instruction.",
                       plan=conversation_plan(items=items))

    assert [row["request_index"] for row in result.units] == [1]
    assert [row["state"] for row in result.coverage] == ["unavailable", "ok"]
    assert "work_selector" in result.coverage[0]["diagnostics"][0]
    assert _operation_names(model) == [
        "continue_conversation", "verify_continuation", "continue_conversation"]
    assert [row["request_index"] for row in model.calls[1][1]["units"]] == [1]
    assert [row["request_index"] for row in model.calls[2][1]["work_items"]] == [0]


@pytest.mark.parametrize("identifier", ["$new_task", "$no_task"])
def test_saved_task_identity_cannot_collide_with_a_selection_mode(identifier):
    progress = {"state": "ok", "rows": [{"id": identifier, "kind": "task",
                "text": "Saved task", "status": "pending"}]}
    model = ContinuationModel([])

    with pytest.raises(IncompleteConversation, match="reliable identity"):
        _continue(model, progress=progress)

    assert model.calls == []


def test_old_two_decision_writer_output_is_not_a_production_escape():
    from dataclasses import replace

    proposed = unit()

    class OldWireModel(ContinuationModel):
        def structured(self, *args, **kwargs):
            result = super().structured(*args, **kwargs)
            return replace(result, data={"units": [deepcopy(proposed)]})

    model = OldWireModel([{"units": [proposed]}, {"units": [proposed]}])
    result = _continue(model)

    assert result.units == () and result.coverage[0]["state"] == "unavailable"
    assert _operation_names(model) == ["continue_conversation", "continue_conversation"]
    assert "work_selector" in result.coverage[0]["diagnostics"][0]


def test_public_saved_question_and_work_refs_have_distinct_port_schemas_and_identities(
        client, wired, monkeypatch):
    first_words = ("I have two records. Help identify what to clarify and a possible "
                   "comparison, without inspecting them yet.")
    later_words = "Keep that question and comparison open; just restate them."
    opening = plan(first_words, step="legal_work")
    later = plan(later_words, step="legal_work", relation="continues")
    proposed = unit(text="You report holding two records.",
                    question="Which records would you want compared?")
    proposed["blocks"] = proposed["blocks"][:2]
    proposed["blocks"].append({
        **deepcopy(proposed["blocks"][0]), "id": "comparison", "kind": "next_step",
        "text": "If you want, we can compare the records you select."})
    proposed["questions"][0]["purpose"] = "Identify which records are intended for comparison."
    proposed["next_work"] = [{"id": "comparison-offer", "block_id": "comparison",
                              "purpose": "Offer a comparison if requested.",
                              "target_ids": [], "existing_id": ""}]
    proposed["sufficiency"] = {"status": "complete", "block_id": "account-0"}
    identities = {}

    def restate(payload):
        rows = payload["progress"]["rows"]
        identities["question"] = next(row["id"] for row in rows if row["kind"] == "question")
        identities["comparison"] = next(row["id"] for row in rows
                                        if row["kind"] == "task" and row["origin"] == "proposed")
        identities["requested"] = next(row["id"] for row in rows
                                       if row["kind"] == "task" and row["origin"] == "requested")
        response = deepcopy(proposed)
        response["blocks"][0]["text"] = "You ask to keep the saved question and comparison open."
        response["questions"][0]["existing_id"] = identities["question"]
        response["next_work"][0]["existing_id"] = identities["comparison"]
        return {"units": [selection(response, identities["requested"])]}

    class StrictPortModel(PublicContinuationModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            require_schema(result.data, schema)
            return result

    model = StrictPortModel([opening, later], [{"units": [proposed]}, restate])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, first_words, "typed-proposals-start")
    saved_id = chat_matter_id("adv_demo", first["chat_id"])
    first_saved = deepcopy(wired.store.load(saved_id).brain_chat[0])
    answer = send(client, later_words, "typed-proposals-restate", opened=first)
    replay = send(client, later_words, "typed-proposals-restate", opened=first)

    assert first["metrics"]["llm_calls"] == answer["metrics"]["llm_calls"] == 3
    assert replay["metrics"]["llm_calls"] == 0
    schemas = [schema for operation, schema in model.schemas
               if operation == "continue_conversation"]
    schema = schemas[1]
    properties = schema["properties"]["units"]["items"]["properties"]
    question_schema = properties["questions"]["items"]
    work_schema = properties["next_work"]["items"]
    assert question_schema is not work_schema
    assert question_schema["properties"]["existing_id"]["enum"] == ["", identities["question"]]
    assert set(work_schema["properties"]["existing_id"]["enum"]) == {
        "", identities["comparison"], identities["requested"]}
    raw = deepcopy(model.calls[-1][1]["units"][0])
    raw = selection(raw, raw["work"]["existing_id"])
    raw["questions"][0]["existing_id"] = identities["comparison"]
    with pytest.raises(SchemaViolation):
        require_schema({"units": [raw]}, schema)
    saved = wired.store.load(saved_id)
    assert saved.brain_chat[0] == first_saved
    assert len(saved.brain_chat) == 2
    result = answer["continuation"]["units"][0]
    assert result["questions"][0]["progress_id"] == identities["question"]
    assert result["next_work"][0]["progress_id"] == identities["comparison"]
    assert result["work"]["progress_id"] == identities["requested"]
    assert len(project_work(saved)["rows"]) == 3
