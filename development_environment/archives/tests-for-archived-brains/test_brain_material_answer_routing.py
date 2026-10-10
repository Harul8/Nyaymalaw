"""Checked account answers preserve extraction and admit legitimate unchanged results.

The model decisions here are scripted. These public-boundary checks prove
routing, persistence and review wiring, not real-model semantic quality.
"""
from copy import deepcopy

from nm.brain.dispute_state import proposed_disputes
from nm.brain.material_state import material_record
from tests.brain_continuation_fixture import no_record_requirement
from tests.test_brain_material import Model, material, mutation_scope, plan, send


def answer_plan(message, *, reply, candidates=(), opening=False,
                intent="request", material_purposes=(), record_requirement=None,
                record_disposition=None):
    routed = plan(message, candidates=candidates, opening=opening, items=[{
        "request": message, "relation": "new" if opening else "continues",
        "matter_scope": "proposed" if opening else "current",
        "priority": "ordinary", "next_step": "answer", "reply": reply,
        "clarification": "", "intent": intent,
        "response_basis": "conversation_record", "research_question": "",
        "material_purposes": list(material_purposes),
        "record_requirement": (no_record_requirement() if record_requirement is None
                               else record_requirement),
    }], material_purposes=("account_contribution",),
       record_disposition=record_disposition)
    if opening:
        routed["opening"].update(subject="Reported delivery", summary=message)
    return routed


def operations(response):
    return [row["operation"] for row in response["metrics"]["model_calls"]]


def current_record(wired, matter_id):
    saved = wired.store.load(matter_id)
    return material_record(saved, disputes=proposed_disputes(saved))


def test_current_answer_runs_correction_saves_lineage_and_replays_without_work(
        client, wired, monkeypatch):
    account = "The delivery took place on 16 June."
    correction = "Correction: the delivery took place on 17 June."
    original = material("event", account, account, placement="matter")
    revised = material(
        "event", "The delivery took place on 17 June.", correction,
        relation="corrects", scope="current", placement="matter",
        references=({"turn_id": "delivery-original", "role": "advocate",
                     "quoted": account},),
        related_material_ids=("delivery-original:material:1",))
    corrected = answer_plan(
        correction, reply="Your corrected account records delivery on 17 June.",
        candidates=[revised], intent="contribution",
        record_disposition="performed",
                     material_purposes=("account_contribution",))
    corrected["items"][0]["mutation_scopes"] = [mutation_scope("delivery-original:material:1")]
    seed = plan(account, candidates=[original], opening=True,
                material_purposes=("account_contribution",))
    seed["opening"].update(subject="Reported delivery", summary=account)
    # A second identical interpretation permits the old guard to exhaust its
    # correction bound, so the baseline reports refusal instead of fixture EOF.
    model = Model([seed, corrected, corrected])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    first = send(client, account, "delivery-original")
    assert first.status_code == 200, first.text
    opened = first.json()
    original_turn = deepcopy(wired.store.load(opened["matter_id"]).brain_chat[0])

    result = send(client, correction, "delivery-corrected", opened=opened)

    assert result.status_code == 200, result.text
    response = result.json()
    assert operations(response) == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "continue_conversation", "verify_continuation"]
    assert response["metrics"]["llm_calls"] == 8
    assert response["material"][0]["related_material_ids"] == [
        "delivery-original:material:1"]
    saved = wired.store.load(opened["matter_id"])
    assert saved.brain_chat[0] == original_turn
    assert [row["message"] for row in saved.brain_chat] == [account, correction]
    record = current_record(wired, opened["matter_id"])
    assert [(row["id"], row["statement"]) for row in record["rows"]] == [
        ("delivery-corrected:material:1", "The delivery took place on 17 June.")]
    assert len(record["history"]) == 2
    assert "17 June" in "\n".join(row["text"] for row in response["elements"])
    reader_count, interpretation_count = len(model.material_calls), len(model.calls)

    replay = send(client, correction, "delivery-corrected", opened=opened)

    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["metrics"]["llm_calls"] == 0
    assert len(model.material_calls) == reader_count
    assert len(model.calls) == interpretation_count
    assert current_record(wired, opened["matter_id"]) == record


def test_proposed_matter_answer_opens_and_saves_checked_account(
        client, wired, monkeypatch):
    account = "The delivery took place on 16 June."
    candidate = material("event", account, account, placement="matter")
    routed = answer_plan(account, reply="Your account reports delivery on 16 June.",
                         candidates=[candidate], opening=True, intent="contribution",
                  material_purposes=("account_contribution",))
    model = Model([routed, routed])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    result = send(client, account, "new-delivery")

    assert result.status_code == 200, result.text
    response = result.json()
    assert response["route"] == "matter"
    assert operations(response) == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "continue_conversation", "verify_continuation"]
    assert [row["statement"] for row in current_record(
        wired, response["matter_id"])["rows"]] == [account]
    saved = wired.store.load(response["matter_id"])
    assert saved.brain_chat[0]["message"] == account
    assert saved.brain_chat[0]["elements"] == response["elements"]


def test_current_account_recap_answer_uses_existing_record_without_extraction(
        client, wired, monkeypatch):
    account = "The delivery took place on 16 June."
    request = "Repeat the delivery date in my saved account."
    original = material("event", account, account, placement="matter")
    recap = answer_plan(request, reply="Your saved account reports delivery on 16 June.",
                 material_purposes=())
    recap["_response_expressions"] = {0: {
        "operator": "source_account", "source_ids": [],
        "record_ids": ["recap-original:material:1"], "focus": "none",
    }}
    model = Model([plan(account, candidates=[original], opening=True,
                        material_purposes=("account_contribution",)), recap, recap])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    seed = send(client, account, "recap-original")
    assert seed.status_code == 200, seed.text
    opened = seed.json()
    before = current_record(wired, opened["matter_id"])
    reader_count = len(model.material_calls)

    result = send(client, request, "delivery-recap", opened=opened)

    assert result.status_code == 200, result.text
    response = result.json()
    assert operations(response) == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    assert response["metrics"]["llm_calls"] == 3
    assert response["material"] == []
    assert len(model.material_calls) == reader_count
    assert current_record(wired, opened["matter_id"]) == before
    assert "16 June" in "\n".join(row["text"] for row in response["elements"])


def test_authorised_no_change_review_answer_is_delivered_without_invented_rows(
        client, wired, monkeypatch):
    account = "The delivery took place on 16 June."
    request = "Check that your saved delivery description matches my account."
    original = material("event", account, account, placement="matter")
    review = answer_plan(
        request, reply="The saved description matches your reported delivery date.",
                  material_purposes=("interpretation_review",),
        record_disposition="review_no_change",
        record_requirement={
            "kind": "review",
            "target_ids": ["review-original:material:1"],
            "operation": "none",
            "success_condition": (
                "The saved delivery description matches the reported 16 "
                "June date."
            ),
        })
    review["_source_purposes"] = {request: "non_account"}
    model = Model([plan(account, candidates=[original], opening=True,
                        material_purposes=("account_contribution",)), review, review])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    seed = send(client, account, "review-original")
    assert seed.status_code == 200, seed.text
    opened = seed.json()
    before = current_record(wired, opened["matter_id"])

    result = send(client, request, "delivery-review", opened=opened)

    assert result.status_code == 200, result.text
    response = result.json()
    assert operations(response) == [
        "interpret_conversation", "classify_account_sources", "extract_disputes", "verify_disputes",
        "extract_legal_details", "verify_material_grounding",
        "continue_conversation", "verify_continuation"]
    assert response["metrics"]["llm_calls"] == 8
    assert response["material"] == []
    assert current_record(wired, opened["matter_id"]) == before
    assert response["blocked"] is False
    execution = response["material_coverage"]["execution"]
    assert execution["record_changes"] == []
    assert execution["requests"][0]["fulfillment"] == "no_change_justified"
    assert response["elements"][0]["text"] == (
        "The requested record review completed without a selected change.\n"
        "Current entries:\n" + account)
    unit, = response["continuation"]["units"]
    assert unit["record_outcome"]["current_record_ids"] == ["review-original:material:1"]


def test_legal_authority_cannot_use_answer_route_to_bypass_research(
        client, wired, monkeypatch):
    request = "Does this limitation period apply to my claim?"
    routed = plan(request, items=[{
        "request": request, "relation": "new", "matter_scope": "none",
        "priority": "ordinary", "next_step": "answer",
        "reply": "The limitation period applies.", "clarification": "",
        "intent": "request", "response_basis": "legal_authority",
        "research_question": "Which limitation period applies to this claim?",
     "record_requirement": no_record_requirement()}])
    model = Model([routed, routed])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    result = send(client, request, "authority-bypass")

    assert result.status_code == 503, result.text
    assert len(model.calls) == 2
    assert all(prompt.operation == "interpret_conversation" for prompt in model.calls)
    assert model.material_calls == []
    assert "The limitation period applies." not in result.text
