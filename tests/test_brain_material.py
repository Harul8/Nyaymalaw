"""Legal material is a sourced proposal from each served conversation turn."""
import json
from dataclasses import replace

import pytest

from nm.brain.turn import chat_matter_id
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage
from tests.brain_continuation_fixture import continuation_reply, interpretation
from tests.brain_reader_fixture import reader_operations


class Model:
    def __init__(self, plans):
        self.plans = iter(plans)
        self.calls = []
        self.material_calls = []
        self.next_material = []
        self.current_items = []

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return 20000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        continuation = continuation_reply(prompt.operation, json.loads(prompt.user),
                                          scripted_items=self.current_items)
        if continuation is not None:
            data = continuation
        elif prompt.operation in ("extract_disputes", "extract_legal_details"):
            self.material_calls.append(prompt)
            payload = json.loads(prompt.user)
            sources = payload.get("original_input", payload)
            rows = [_with_source_ids(row, sources) for row in self.next_material]
            if prompt.operation == "extract_disputes":
                data = reader_operations([
                    {key: value for key, value in row.items() if key != "kind"}
                    for row in rows if row["kind"] == "dispute"], sources,
                    link_field="related_dispute_ids")
            else:
                data = reader_operations([row for row in rows
                                          if row["kind"] != "dispute"], sources,
                                         link_field="related_material_ids")
        elif prompt.operation in ("verify_disputes", "verify_material_grounding"):
            payload = json.loads(prompt.user)
            data = {"verdicts": [
                {"candidate_id": row["candidate_id"],
                 "operation_supported": True,
                 **({"candidate_role": "independent_dispute"}
                    if prompt.operation == "verify_disputes" else {}),
                 "verdict": "accept", "reason": "Attributable proposal"}
                for row in payload["candidates"]]}
        else:
            self.calls.append(prompt)
            planned = next(self.plans)
            self.next_material = planned["material"]
            data = {key: value for key, value in planned.items() if key != "material"}
            if prompt.operation == "interpret_conversation":
                data = interpretation(data)
                self.current_items = data["items"]
        return ModelResult(text=None, data=data, tier=tier,
                           provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def _with_source_ids(row, payload):
    """Script citations from the immutable spans supplied to the model."""
    matching = [span["id"] for span in payload["latest_message_spans"]
                if row["quoted"] in span["text"]]
    converted = {key: value for key, value in row.items()
                 if key not in {"quoted", "prior_references"}}
    converted["source_id"] = matching[0] if matching else "unsupported_source"
    earlier = payload["earlier_conversation"]
    if earlier:
        converted["prior_source_ids"] = []
        for ref in row["prior_references"]:
            matching = [span["id"] for message in earlier
                        if message["turn_id"] == ref["turn_id"]
                        and message["role"] == ref["role"]
                        for span in message["source_spans"]
                        if ref["quoted"] in span["text"]]
            converted["prior_source_ids"].append(
                matching[0] if matching else "unsupported_prior_source")
    return converted


def material(kind, statement, quoted, *, relation="new", references=(),
             scope="proposed", basis="stated", importance="relevant",
             why="It may affect the requested legal work.",
             placement="unresolved", dispute_ids=(), related_material_ids=()):
    row = {"kind": kind, "statement": statement, "quoted": quoted,
           "relation": relation, "prior_references": list(references),
           "matter_scope": scope, "basis": basis,
           "importance": importance, "why_material": why}
    if kind == "dispute":
        row.update(label=statement[:80], identification="identified",
                   clarification="", related_dispute_ids=[])
    else:
        row.update(placement=placement, dispute_ids=list(dispute_ids),
                   related_material_ids=list(related_material_ids))
    return row


def plan(message, *, candidates=(), items=None, opening=False,
         active_work="review the account"):
    if items is None:
        items = [{"request": message, "relation": "new",
                  "matter_scope": "proposed" if opening else "current",
                  "priority": "ordinary",
                  "next_step": "legal_work",
                  "reply": ("I will check the account and available material "
                            "before reaching a legal view."),
                  "clarification": ""}]
    return {"items": items, "material": list(candidates),
            "material_review": bool(candidates) or opening,
            "active_work_after": active_work,
            "opening": {"ready": opening,
                        "party_name": "",
                        "subject": "Contractor dispute" if opening else "",
                        "summary": "The advocate describes a dispute over stopped work."
                        if opening else "",
                        }}


def send(client, message, turn_id, *, opened=None):
    body = {"message": message, "turn_id": turn_id}
    if opened is not None:
        body.update(matter_id=opened["matter_id"], chat_id=opened["chat_id"])
    return client.post("/api/turn", json=body)


def test_greeting_and_general_question_add_no_matter_material(
        client, wired, monkeypatch):
    greeting = "Hello"
    question = "What is the legal meaning of consideration?"
    model = Model([
        plan(greeting, candidates=[], items=[
            {"request": greeting, "relation": "new",
             "matter_scope": "none", "priority": "ordinary",
             "next_step": "answer",
             "reply": "Hello. What would you like help with?", "clarification": ""}],
             active_work=""),
        plan(question, candidates=[], items=[
            {"request": question, "relation": "new",
             "matter_scope": "none", "priority": "ordinary",
             "next_step": "legal_work",
             "reply": "I will check the applicable law before explaining it.",
             "clarification": ""}], active_work="answer legal question"),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    first = send(client, greeting, "greeting-turn").json()
    second = client.post("/api/turn", json={
        "message": question, "turn_id": "question-turn", "chat_id": first["chat_id"]})

    assert second.status_code == 200, second.text
    assert first["matter_id"] is None and second.json()["matter_id"] is None
    assert first["material"] == second.json()["material"] == []
    saved = wired.store.load(chat_matter_id("adv_demo", first["chat_id"]))
    assert [row["response"]["material"] for row in saved.brain_chat] == [[], []]
    assert saved.facts == ()
    assert len(model.calls) == 2
    assert model.material_calls == []


def test_first_account_retains_distinct_sourced_material_without_admission(
        client, wired, monkeypatch):
    message = ("The contractor stopped work on 12 June. "
               "We paid an advance of 4 lakh. They say materials were not supplied.")
    candidates = [
        material("event", "The contractor stopped work on 12 June.",
                 "contractor stopped work on 12 June", importance="central"),
        material("circumstance", "The advocate says an advance of 4 lakh was paid.",
                 "We paid an advance of 4 lakh", importance="central"),
        material("position", "The contractor says materials were not supplied.",
                 "They say materials were not supplied", basis="attributed"),
    ]
    model = Model([plan(message, candidates=candidates, opening=True)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = send(client, message, "material-first")

    assert served.status_code == 200, served.text
    response = served.json()
    assert [row["statement"] for row in response["material"]] == [
        row["statement"] for row in candidates]
    assert all(row["source_turn_id"] == "material-first" and row["id"]
               for row in response["material"])
    assert len({row["id"] for row in response["material"]}) == 3
    saved = wired.store.load(response["matter_id"])
    assert saved.brain_chat[0]["response"]["material"] == response["material"]
    assert saved.facts == ()
    assert len(model.calls) == 1
    assert len(model.material_calls) == 2
    assert response["metrics"]["llm_calls"] == 6
    payload = json.loads(model.calls[0].user)
    assert payload["earlier_conversation"] == []
    assert payload["latest_message"] == message
    assert all(label in model.calls[0].system for label in
               ("Message:", "Purpose:", "Look for:", "Outcome:"))


def test_correction_and_diversion_keep_prior_words_and_proposals(
        client, wired, monkeypatch):
    first = "We paid the contractor an advance of 4 lakh."
    correction = "Correction: the advance was 3 lakh, not 4 lakh."
    aside = "Hi. What is the capital of France?"
    original = material("circumstance", "The advocate says 4 lakh was paid.",
                        "an advance of 4 lakh", importance="central")
    revised = material(
        "circumstance", "The advocate corrects the advance to 3 lakh.",
        "the advance was 3 lakh, not 4 lakh", relation="corrects",
        references=({"turn_id": "material-one", "role": "advocate",
                     "quoted": "an advance of 4 lakh"},),
        scope="current", importance="central")
    aside_item = {"request": aside, "relation": "aside",
                  "matter_scope": "none", "priority": "ordinary",
                  "next_step": "answer",
                  "reply": "Hello. Paris is the capital of France.",
                  "clarification": ""}
    model = Model([
        plan(first, candidates=[original], opening=True),
        plan(correction, candidates=[revised]),
        plan(aside, candidates=[], items=[aside_item]),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "material-one").json()
    corrected = send(client, correction, "material-two", opened=opened)
    diverted = send(client, aside, "material-three", opened=opened)

    assert corrected.status_code == 200, corrected.text
    assert diverted.status_code == 200, diverted.text
    assert corrected.json()["material"][0]["relation"] == "corrects"
    assert corrected.json()["material"][0]["prior_references"] == [
        {"turn_id": "material-one", "role": "advocate",
         "quoted": first}]
    assert diverted.json()["material"] == []
    saved = wired.store.load(opened["matter_id"])
    assert [row["message"] for row in saved.brain_chat] == [first, correction, aside]
    assert saved.brain_chat[0]["response"]["material"][0]["statement"] == original["statement"]
    assert saved.brain_chat[1]["response"]["material"][0]["statement"] == revised["statement"]
    assert saved.facts == ()
    assert len(model.calls) == 3
    assert len(model.material_calls) == 4
    assert [row["text"] for row in json.loads(model.calls[2].user)["earlier_conversation"]
            if row["role"] == "advocate"] == [first, correction]


def test_reported_correction_is_read_when_interpretation_marks_material_content(
        client, wired, monkeypatch):
    first = "The keys were handed over on Monday."
    correction = "Correction: the keys were handed over on Tuesday."
    original = material("event", "The keys were handed over on Monday.",
                        first)
    revised = material(
        "event", "The keys were handed over on Tuesday.", correction,
        relation="corrects", scope="current",
        references=({"turn_id": "first", "role": "advocate", "quoted": first},),
        related_material_ids=("first:material:1",))
    second_plan = plan(correction, candidates=[revised], items=[{
        "request": "Correct the handover date", "relation": "continues",
        "matter_scope": "current", "priority": "ordinary",
        "next_step": "legal_work", "reply": "I have noted the corrected date.",
        "intent": "contribution",
        "clarification": ""}])
    second_plan["material_review"] = True
    model = Model([plan(first, candidates=[original], opening=True), second_plan])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "first")
    assert opened.status_code == 200, opened.text
    changed = send(client, correction, "second", opened=opened.json())

    assert changed.status_code == 200, changed.text
    assert changed.json()["metrics"]["llm_calls"] == 6
    matter = wired.store.load(opened.json()["matter_id"])
    from nm.brain.dispute_state import proposed_disputes
    from nm.brain.material_state import material_record
    record = material_record(matter, disputes=proposed_disputes(matter))
    assert [row["id"] for row in record["rows"]] == ["second:material:1"]
    assert len(record["history"]) == 2


@pytest.mark.parametrize("relation", ("new", "changes"))
def test_work_request_without_new_material_preserves_record_with_three_calls(
        client, wired, monkeypatch, relation):
    first = "The reported delivery date is disputed. We have an unsigned note."
    request = "Please assess the account already on this file."
    original = [
        material("dispute", "Disputed delivery date",
                 "The reported delivery date is disputed."),
        material("evidence", "The advocate reports an unsigned note.",
                 "We have an unsigned note.", placement="disputes",
                 dispute_ids=("recorded:material:1",)),
    ]
    work_plan = plan(request, items=[{
        "request": request, "relation": relation, "matter_scope": "current",
        "priority": "ordinary", "next_step": "legal_work",
        "reply": "I will assess the existing account and identify any limit in its support.",
        "clarification": ""}])
    assert work_plan["material_review"] is False
    model = Model([plan(first, candidates=original, opening=True), work_plan])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    opened = send(client, first, "recorded")
    assert opened.status_code == 200, opened.text
    matter_id = opened.json()["matter_id"]
    before = client.get(f"/api/matters/{matter_id}").json()
    reader_count = len(model.material_calls)

    response = send(client, request, "work-request", opened=opened.json())

    assert response.status_code == 200, response.text
    released = response.json()
    assert released["metrics"]["llm_calls"] == 3
    assert [row["operation"] for row in released["metrics"]["model_calls"]] == [
        "interpret_conversation", "continue_conversation", "verify_continuation"]
    assert released["material"] == []
    assert len(model.material_calls) == reader_count
    after = client.get(f"/api/matters/{matter_id}").json()
    assert after["proposed_disputes"] == before["proposed_disputes"]
    assert after["material_record"] == before["material_record"]
    saved = wired.store.load(matter_id)
    assert [row["message"] for row in saved.brain_chat] == [first, request]
    assert saved.facts == ()


def test_answer_to_prior_nm_question_can_support_material(
        client, wired, monkeypatch):
    first = "The contractor stopped work."
    question = "Did the stoppage occur on 12 June?"
    answer = "Yes."
    first_item = {"request": first, "relation": "new",
                  "matter_scope": "proposed", "priority": "ordinary",
                  "next_step": "clarify",
                  "reply": "", "clarification": question}
    confirmed = material(
        "event", "The advocate confirms the stoppage occurred on 12 June.",
        "Yes", scope="current", importance="relevant",
        references=({"turn_id": "question-turn", "role": "nm",
                     "quoted": question},))
    model = Model([
        plan(first, opening=True, items=[first_item]),
        plan(answer, candidates=[confirmed]),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "question-turn").json()
    served = send(client, answer, "answer-turn", opened=opened)

    assert served.status_code == 200, served.text
    assert served.json()["material"][0]["quoted"] == "Yes."
    assert served.json()["material"][0]["relation"] == "new"
    assert served.json()["material"][0]["related_material_ids"] == []
    assert served.json()["material"][0]["prior_references"] == [
        {"turn_id": "question-turn", "role": "nm", "quoted": question}]
    assert wired.store.load(opened["matter_id"]).facts == ()
    assert len(model.calls) == 2
    assert len(model.material_calls) == 4


def test_one_message_keeps_separate_disputes_and_work_in_two_focused_calls(
        client, wired, monkeypatch):
    first = "The contractor stopped work"
    second = "my tenant has withheld rent"
    research = "find authorities on the contractor issue"
    message = f"{first}; separately, {second}. Also {research}."
    items = [
        {"request": research, "relation": "new",
         "matter_scope": "proposed", "priority": "ordinary",
         "next_step": "legal_work",
         "reply": "I will check the applicable authorities.",
         "clarification": ""},
    ]
    candidates = [
        material("dispute", "The advocate describes a contractor work dispute.",
                 first, importance="central"),
        material("dispute", "The advocate describes a separate rent dispute.",
                 second, scope="other", importance="central"),
    ]
    model = Model([plan(message, candidates=candidates, opening=True,
                        items=items)])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = send(client, message, "multiple-material")

    assert served.status_code == 200, served.text
    assert [row["matter_scope"] for row in served.json()["material"]] == [
        "proposed", "other"]
    assert [row["quoted"] for row in served.json()["material"]] == [
        f"{first};", f"separately, {second}."]
    assert len(model.calls) == 1
    assert len(model.material_calls) == 2
    assert served.json()["metrics"]["llm_calls"] == 7


@pytest.mark.parametrize("invalid_candidate", [
    material("event", "A date was provided.", "words absent from the message",
             scope="current"),
    material("event", "The advocate corrects the date.", "the date was Tuesday",
             relation="corrects", scope="current",
             references=({"turn_id": "valid-first", "role": "advocate",
                          "quoted": "words absent from the earlier message"},)),
])
def test_unsupported_material_refuses_the_whole_turn_without_a_write(
        client, wired, monkeypatch, invalid_candidate):
    first = "The contractor stopped work on Monday."
    next_message = "The date was Tuesday, not Monday."
    if invalid_candidate["quoted"] == "the date was Tuesday":
        next_message = "Correction: the date was Tuesday, not Monday."
    model = Model([
        plan(first, opening=True),
        plan(next_message, candidates=[invalid_candidate]),
    ])
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    opened = send(client, first, "valid-first").json()
    refused = send(client, next_message, "invalid-second", opened=opened)

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["committed"] == "not_committed"
    assert refused.json()["detail"]["why"] == (
        "NM could not validate the analysis returned by the AI service. "
        "Please try again later.")
    saved = wired.store.load(opened["matter_id"])
    assert [row["turn_id"] for row in saved.brain_chat] == ["valid-first"]
    assert saved.facts == ()
    assert len(model.calls) == 2
    assert len(model.material_calls) == 5
    retries = [json.loads(prompt.user) for prompt in model.material_calls
               if "original_input" in json.loads(prompt.user)]
    assert len(retries) == 1
    assert retries[0]["validation_issue"]
    assert "source references" in retries[0]["how_to_correct"]


def test_invalid_first_source_selection_is_repaired_once_before_commit(
        client, wired, monkeypatch):
    message = "The delivery was delayed."
    candidate = material("event", "The advocate reports a delayed delivery.",
                         "delivery was delayed")

    class RepairingModel(Model):
        def __init__(self):
            super().__init__([plan(message, candidates=[candidate], opening=True)])
            self.rejected = False

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier,
                                        max_tokens=max_tokens)
            if prompt.operation == "extract_legal_details" and not self.rejected:
                self.rejected = True
                row = {**result.data["new_items"][0],
                       "source_id": "unsupported_source"}
                return replace(result, data={"new_items": [row], "changes": []})
            return result

    model = RepairingModel()
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)

    served = send(client, message, "repaired-source")

    assert served.status_code == 200, served.text
    assert served.json()["material"][0]["quoted"] == message
    assert served.json()["metrics"]["llm_calls"] == 7
    repair = [json.loads(prompt.user) for prompt in model.material_calls
              if "original_input" in json.loads(prompt.user)]
    assert len(repair) == 1
    assert repair[0]["validation_issue"]
    assert repair[0]["original_input"]["latest_message_spans"][0]["text"] == message
    saved = wired.store.load(served.json()["matter_id"])
    assert [row["turn_id"] for row in saved.brain_chat] == ["repaired-source"]
