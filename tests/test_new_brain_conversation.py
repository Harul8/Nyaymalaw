"""The new brain reads the whole conversation before interpreting a turn."""
import json

import pytest

from nm.brain.conversation import Conversation, IncompleteConversation, Message, interpret
from nm.brain.history import from_turns
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ContextOverflow, ModelResult, SchemaViolation, Tier, Usage
from tests.brain_continuation_fixture import interpretation as route_contract
from tests.brain_continuation_fixture import no_record_requirement, scripted_message_labels


class Model:
    def __init__(self, data, *, budget=20000, completion=Completion.COMPLETE):
        self.data = data
        self.budget = budget
        self.completion = completion
        self.calls = []

    def context_budget(self, tier):
        assert tier in (Tier.ROUTINE, Tier.JUDGE)
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        from tests.brain_continuation_fixture import transport_message_parts
        payload = json.loads(prompt.user)
        original = payload.get("original_input", payload)
        data = (scripted_message_labels(self.data, original) if prompt.operation == "label_message"
                else transport_message_parts(self.data, original))
        return ModelResult(text=None, data=data, tier=tier,
                           provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0,
                           completion=self.completion)


def item(quoted, *, request=None, relation="continues", scope="current",
         priority="ordinary", step="legal_work", reply=None,
         clarification="", intent="request", material_purposes=(), record_requirement=None):
    if reply is None:
        reply = (f"I will check the material needed to address {quoted}."
                 if step == "legal_work" else "")
    return {"request": request or quoted, "relation": relation,
            "matter_scope": scope, "priority": priority,
            "next_step": step, "reply": reply, "clarification": clarification,
            "intent": intent, "material_purposes": list(material_purposes),
            "record_requirement": (no_record_requirement() if record_requirement is None
                                   else record_requirement)}


def interpretation(items, *, active_work_after="", opening=None):
    if opening is None:
        opening = {"ready": False, "party_name": "", "subject": "",
                   "summary": ""}
    elif "title" in opening:
        title = opening["title"]
        party_name, separator, subject = title.partition(":")
        opening = {"ready": opening["ready"],
                   "party_name": party_name if separator else "",
                   "subject": subject.strip() if separator else title,
                   "summary": opening["summary"]}
    return route_contract({"items": items, "opening": opening})


def test_first_greeting_has_no_prior_work_or_opening_and_takes_one_call_per_owner():
    model = Model(interpretation([
        item("Hello", relation="new", scope="none", step="answer",
             reply="Hello. What would you like help with?")]))

    plan = interpret(model, Conversation(()), "Hello")

    assert plan.items[0].request == "Hello"
    assert plan.items[0].next_step == "answer"
    assert plan.items[0].reply == plan.items[0].clarification == ""
    assert plan.opening.ready is False
    assert plan.active_work_after == ""
    assert len(model.calls) == 2
    prompt = model.calls[1][0]
    payload = json.loads(prompt.user)
    assert payload["earlier_conversation"] == []
    assert payload["current_matter_id"] is None
    assert payload["current_work"] == ""
    for branch in model.calls[1][1]["properties"]["items"]["items"]["anyOf"]:
        decisions = branch["properties"]
        assert "current" not in decisions["matter_scope"]["enum"]
        assert decisions["relation"]["enum"] == ["new", "uncertain"]
    assert "Empty history is a valid first turn" in prompt.system
    assert "opening" in prompt.system


def test_adapter_schema_rejection_gets_one_contextual_correction():
    class InitiallyRejected(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "interpret_conversation" and not any(
                    call[0].operation == "interpret_conversation" for call in self.calls):
                self.calls.append((prompt, schema, tier, max_tokens))
                raise SchemaViolation("The provider could not parse its JSON response")
            return super().structured(prompt, schema, tier,
                                      max_tokens=max_tokens)

    model = InitiallyRejected(interpretation([
        item("Hello", relation="new", scope="none", step="answer",
             reply="Hello. What would you like help with?")]))
    plan = interpret(model, Conversation(()), "Hello")

    assert plan.items[0].request == "Hello"
    assert plan.items[0].next_step == "answer"
    assert plan.items[0].reply == plan.items[0].clarification == ""
    assert len(model.calls) == 3
    assert [call[2] for call in model.calls] == [Tier.ROUTINE, Tier.JUDGE, Tier.JUDGE]
    correction = json.loads(model.calls[2][0].user)
    assert correction["original_input"]["latest_message"] == "Hello"
    assert "provider could not parse" in correction["validation_issue"]
    assert "complete replacement" in model.calls[2][0].system


def test_first_general_legal_question_does_not_propose_a_matter():
    model = Model(interpretation([
        item("Explain anticipatory bail", relation="new", scope="none",
             reply=("An explanation requires checking the applicable law "
                    "and authorities."))],
        active_work_after="answer legal question"))

    plan = interpret(model, Conversation(()), "Explain anticipatory bail")

    assert plan.items[0].next_step == "legal_work"
    assert plan.items[0].request == "Explain anticipatory bail"
    assert plan.items[0].reply == plan.items[0].clarification == ""
    assert plan.opening.ready is False
    assert len(model.calls) == 2
    prompt = model.calls[1][0].system
    assert "answer for a conversational or other nonlegal reply" in prompt
    assert "regardless of whether it is general or an aside" in prompt


def test_legal_aside_remains_a_separate_source_dependent_work_item():
    conversation = Conversation(
        (Message("earlier", "advocate", "Please review my agreement."),),
        current_matter_id="matter", current_work="review agreement")
    model = Model(interpretation([
        item("What legal remedies apply here?", relation="aside",
             scope="current", step="legal_work",
             reply="That question requires checking the applicable sources.")],
        active_work_after="review agreement"))

    plan = interpret(model, conversation, "Before that, what legal remedies apply here?")

    assert plan.items[0].relation == "aside"
    assert plan.items[0].next_step == "legal_work"
    assert plan.active_work_after == "review agreement"
    assert len(model.calls) == 2


def test_first_concrete_account_can_propose_a_grounded_opening():
    latest = "My landlord kept my deposit after I moved out. Please help me recover it."
    opening = {"ready": True, "title": "Deposit recovery",
               "summary": "The landlord kept the deposit after the move."}
    model = Model(interpretation([
        item(latest, relation="new", scope="proposed",
             material_purposes=("account_contribution",),
             reply=("You say the deposit was kept after you moved out. I can "
                    "assess recovery once I have the agreement and the reason "
                    "given for withholding it."))],
        active_work_after="assess deposit recovery", opening=opening))

    plan = interpret(model, Conversation(()), latest)

    assert plan.opening.ready is True
    assert plan.material_review is True
    assert plan.opening.summary == opening["summary"]
    assert plan.items[0].matter_scope == "proposed"
    assert plan.items[0].request == latest
    assert plan.items[0].material_purposes == ("account_contribution",)
    assert plan.items[0].reply == plan.items[0].clarification == ""
    assert len(model.calls) == 2


def test_one_named_client_and_subject_compose_opening_title():
    latest = "Mira Patel says Dev Shah retained her records after the contract ended."
    opening = {"ready": True, "party_name": "Mira Patel",
               "subject": "Return of records",
               "summary": "Mira Patel reports that Dev Shah retained her records."}
    model = Model(interpretation([
        item(latest, relation="new", scope="proposed",
             reply="I will review the reported retention and the available record.",
             material_purposes=("account_contribution",))],
        opening=opening))

    result = interpret(model, Conversation(()), latest)

    assert result.opening.title == "Mira Patel: Return of records"
    assert result.opening.party_name == "Mira Patel"
    assert result.opening.subject == "Return of records"
    assert "one representative client-side name" in model.calls[1][0].system
    assert "opposing party or vs in party_name" in model.calls[1][0].system
    assert "leave it empty if identity or role is uncertain" in model.calls[1][0].system


def test_later_clarification_can_complete_opening_from_prior_advocate_words():
    conversation = Conversation((
        Message("earlier", "advocate",
                "My landlord withheld the deposit after I moved out."),
        Message("earlier", "nm",
                "What would you like to achieve?")),
        current_work="understand the advocate's objective")
    latest = "I want to recover that deposit."
    opening = {"ready": True, "title": "Deposit recovery",
               "summary": "The user says the landlord withheld a deposit and seeks its return."}
    model = Model(interpretation([
        item(latest, relation="continues", scope="proposed",
             material_purposes=("account_contribution",),
             reply=("You want the deposit returned. I can assess the recovery "
                    "options after checking the agreement and communications."))],
        active_work_after="assess deposit recovery", opening=opening))

    plan = interpret(model, conversation, latest)

    assert plan.opening.ready is True
    assert plan.opening.summary == opening["summary"]
    assert len(model.calls) == 2


def test_open_matter_requires_an_empty_opening_decision_on_followup():
    conversation = Conversation((
        Message("first", "advocate", "The deposit is disputed."),
        Message("first", "nm", "Please confirm the handover date.")),
        current_matter_id="mat_deposit")
    latest = "Correction: the handover was on 2 August."
    model = Model(interpretation([
        item(latest, relation="continues", scope="current", step="legal_work",
             intent="contribution",
             reply="I have recorded your corrected handover date.",
             material_purposes=("account_contribution",))]))

    plan = interpret(model, conversation, latest)

    opening = model.calls[1][1]["properties"]["opening"]["properties"]
    assert opening["ready"]["enum"] == [False]
    assert opening["party_name"]["enum"] == [""]
    assert opening["subject"]["enum"] == [""]
    assert opening["summary"]["enum"] == [""]
    assert plan.opening.ready is False
    assert plan.material_review is True


def test_legal_work_uses_source_contract_without_an_interim_draft():
    latest = "Please compare these two clauses."
    missing_requirement = interpretation([
        item(latest, relation="new", scope="none", reply="")])
    missing_requirement["items"][0].pop("record_requirement")
    invalid = Model(missing_requirement)

    with pytest.raises(SchemaViolation, match="record_requirement"):
        interpret(invalid, Conversation(()), latest)
    assert len(invalid.calls) == 3

    model = Model(interpretation([
        item(latest, relation="new", scope="none",
             reply="I can compare the clauses once I have their full text and context.")]))
    plan = interpret(model, Conversation(()), latest)
    assert plan.items[0].next_step == "legal_work"
    assert plan.items[0].request == latest
    assert plan.items[0].record_requirement == no_record_requirement()
    assert plan.items[0].reply == plan.items[0].clarification == ""
    assert len(model.calls) == 2


@pytest.mark.parametrize("relation,scope", [
    ("continues", "none"),
    ("changes", "none"),
    ("aside", "none"),
    ("new", "current"),
])
def test_first_message_cannot_claim_missing_prior_context(relation, scope):
    model = Model(interpretation([
        item("Hello", relation=relation, scope=scope,
             step="answer", reply="Hello.")]))

    with pytest.raises(SchemaViolation):
        interpret(model, Conversation(()), "Hello")


@pytest.mark.parametrize("opening", [
    {"ready": True, "title": "", "summary": "A purported fact",
     },
    {"ready": True, "title": "A matter", "summary": "",
     },
    {"ready": False, "title": "A matter", "summary": "",
     },
])
def test_opening_candidate_requires_a_complete_state(opening):
    model = Model(interpretation([
        item("Please help with this matter", relation="new", scope="proposed")],
        opening=opening))

    with pytest.raises(SchemaViolation):
        interpret(model, Conversation(()), "Please help with this matter")


@pytest.mark.parametrize("field", ["party_name", "subject", "summary"])
def test_unready_opening_ignores_only_empty_formatting_without_retry(field):
    opening = {"ready": False, "party_name": "", "subject": "", "summary": ""}
    opening[field] = " \n\t "
    model = Model(interpretation([
        item("Hello", relation="new", scope="none", step="answer", reply="Hello.")],
        opening=opening))
    result = interpret(model, Conversation(()), "Hello")
    assert result.opening.ready is False
    assert result.opening.title == result.opening.summary == ""
    assert len(model.calls) == 2


def test_mixed_message_keeps_each_request_and_the_entire_earlier_exchange():
    earlier = Conversation((Message("first", "advocate", "I need a review."),
                            Message("first", "nm", "Which document?"),
                            Message("second", "advocate", "The attached agreement."),
                            Message("second", "nm", "I can review its terms.")),
                           current_matter_id="m1", current_work="review agreement")
    latest = "Check clause 4; first tell me the capital of France."
    model = Model(interpretation([
        item("Check clause 4"),
        item("tell me the capital of France", relation="aside",
             scope="none", step="answer", reply="Paris.")],
        active_work_after="review agreement"))

    plan = interpret(model, earlier, latest)

    assert len(plan.items) == 2
    assert len(model.calls) == 2
    assert plan.items[1].request == "tell me the capital of France"
    assert plan.items[1].next_step == "answer"
    assert plan.items[1].reply == plan.items[1].clarification == ""
    assert [row.relation for row in plan.items] == ["continues", "aside"]
    payload = json.loads(model.calls[1][0].user)
    assert payload["earlier_conversation"] == [
        {"turn_id": message.turn_id, "role": message.role, "text": message.text}
        for message in earlier.messages]
    assert payload["latest_message"] == latest
    assert model.calls[1][0].system.count("Message:") == 2
    assert all(label in model.calls[1][0].system for label in
               ("Purpose:", "Look for:", "Outcome:"))


def test_saved_projection_restores_both_sides_and_refuses_gaps():
    turns = [{"turn_id": "one", "message": "Please review this.",
              "committed": True, "release_state": "released",
              "elements": [{"text": "Please provide the document."}]},
             {"turn_id": "two", "message": "I have now attached it.",
              "committed": True, "release_state": "released",
              "elements": [{"text": "The attachment is unreadable."}]}]
    conversation = from_turns(turns, state="ok", matter_id="m1")
    assert [(m.turn_id, m.role) for m in conversation.messages] == [
        ("one", "advocate"), ("one", "nm"),
        ("two", "advocate"), ("two", "nm")]
    assert conversation.messages[0].text == "Please review this."
    with pytest.raises(IncompleteConversation):
        from_turns(turns, state="incomplete", matter_id="m1")
    with pytest.raises(IncompleteConversation):
        from_turns([{**turns[0], "message_source": "not_held", "message": ""}], state="ok")
    with pytest.raises(IncompleteConversation):
        from_turns([turns[0], {**turns[0], "message": "Another turn"}], state="ok")


def test_unreleased_draft_is_not_used_as_conversation_context():
    conversation = from_turns([{"turn_id": "one", "message": "Please help.",
                                "committed": False, "release_state": "withheld",
                                "elements": [],
                                "blocked_reason": "The request could not be completed.",
                                "unapproved_draft": "Invented recommendation"}], state="ok")
    assert conversation.messages[1].text == "The request could not be completed."


def test_an_unreleased_response_cannot_enter_context_as_an_answer():
    with pytest.raises(IncompleteConversation):
        from_turns([{"turn_id": "one", "message": "Please help.",
                     "committed": False, "release_state": "withheld",
                     "elements": [{"text": "Unapproved conclusion"}],
                     "blocked_reason": "The request could not be completed."}], state="ok")


@pytest.mark.parametrize("invalid", [
    lambda row: {**row, "quoted": "unrequested duplicate citation"},
    lambda row: {**row, "anchor_turn_ids": ["missing"]},
    lambda row: {**row, "next_step": "invented"},
    lambda row: {**row, "request": ""},
])
def test_unattributed_or_invalid_interpretation_is_refused(invalid):
    conversation = Conversation((Message("one", "advocate", "Earlier words"),))
    model = Model(interpretation([invalid(item("Latest words"))]))
    with pytest.raises(SchemaViolation):
        interpret(model, conversation, "Latest words")


def test_an_aside_preserves_canonical_active_work_without_a_model_decision():
    conversation = Conversation((), current_work="draft reply")
    model = Model(interpretation([
        item("Hello", relation="aside", scope="none",
             step="answer", reply="Hello.")],
        active_work_after="research case law"))
    interpreted = interpret(model, conversation, "Hello")
    assert interpreted.active_work_after == "draft reply"
    assert "active_work_after" not in model.data


def test_model_cannot_supply_a_second_owner_for_active_work():
    proposal = interpretation([item("Hello", relation="aside", scope="none",
                                    step="answer", reply="Hello.")])
    proposal["active_work_after"] = "research case law"
    with pytest.raises(SchemaViolation):
        interpret(Model(proposal), Conversation((), current_work="draft reply"), "Hello")


def test_many_distinct_requests_do_not_hit_a_scenario_count_limit():
    phrases = [f"request {number}" for number in range(10)]
    latest = "; ".join(phrases)
    model = Model(interpretation([
        item(phrase, relation="new", scope="none") for phrase in phrases],
        active_work_after="review requests"))
    plan = interpret(model, Conversation(()), latest)
    assert len(plan.items) == len(phrases)
    assert len(model.calls) == 2


def test_urgent_and_ordinary_work_remain_distinct_in_one_interpretation():
    latest = "There is a deadline tomorrow; also review the draft when possible."
    model = Model(interpretation([
        item("There is a deadline tomorrow", relation="new", scope="none",
             priority="urgent"),
        item("review the draft when possible", relation="new", scope="none")],
        active_work_after="address deadline and review draft"))
    plan = interpret(model, Conversation(()), latest)
    assert [row.priority for row in plan.items] == ["urgent", "ordinary"]
    assert len(model.calls) == 2


def test_no_truncation_or_partial_model_output_is_accepted():
    conversation = Conversation((Message("one", "advocate", "A complete prior message"),))
    model = Model(interpretation([item("Continue", relation="new", scope="none")]),
                  budget=10)
    with pytest.raises(ContextOverflow):
        interpret(model, conversation, "Continue")
    assert model.calls == []

    limited = Model(model.data, completion=Completion.LENGTH_LIMITED)
    with pytest.raises(SchemaViolation):
        interpret(limited, conversation, "Continue")


@pytest.mark.parametrize(("purposes", "latest", "record_requirement"), [
    ((), "Repeat the delivery date in my saved account.", no_record_requirement()),
    (("account_contribution",), "The delivery arrived on 17 June.", no_record_requirement()),
    (("interpretation_review",), "Repair your actor description against my original account.",
     {
         "kind": "review",
         "target_ids": [],
         "operation": "none",
         "success_condition": (
             "The description faithfully retains the original unknown "
             "delivery actor."
         ),
     }),
    (("account_contribution", "interpretation_review"),
     "It arrived on 17 June. Repair your actor description against my original account.",
     {
         "kind": "review",
         "target_ids": [],
         "operation": "none",
         "success_condition": (
             "The account retains the new reported arrival date and the "
             "original unknown delivery actor."
         ),
     }),
])
def test_fresh_material_purposes_drive_reading_without_a_second_switch(
        purposes, latest, record_requirement):
    conversation = Conversation((
        Message("earlier", "advocate", "The delivery actor is unknown."),
        Message("earlier", "nm", "The description remains provisional.")),
        current_matter_id="current-file")
    data = interpretation([item(latest, material_purposes=purposes,
                                record_requirement=record_requirement)])
    model = Model(data)

    planned = interpret(model, conversation, latest)

    assert planned.items[0].material_purposes == purposes
    assert planned.material_review is bool(purposes)
    assert len(model.calls) == 2
    assert "material_review" not in data
    schema = model.calls[1][1]
    assert "material_review" not in schema["properties"]
    assert all("material_purposes" in branch["required"]
               for branch in schema["properties"]["items"]["items"]["anyOf"])


def test_mixed_account_and_review_purposes_preserve_an_independent_readonly_item():
    conversation = Conversation((
        Message("earlier", "advocate", "The delivery actor is unknown. It arrived at the depot."),
        Message("earlier", "nm", "The manager delivered it.")),
        current_matter_id="current-file")
    latest = ("It arrived on 17 June. Repair your description against my original account. "
              "Also repeat the previously reported location.")
    model = Model(interpretation([
        item("Record the arrival and reconcile your description",
             material_purposes=("account_contribution", "interpretation_review"),
             record_requirement={
                 "kind": "review",
                 "target_ids": [],
                 "operation": "none",
                 "success_condition": (
                     "The review establishes both the reported 17 June "
                     "arrival and the original unknown delivery actor."
                 ),
             }),
        item("Repeat the reported location", step="answer",
             reply="The reported location is unchanged.", material_purposes=()),
    ]))

    planned = interpret(model, conversation, latest)

    assert [item.material_purposes for item in planned.items] == [
        ("account_contribution", "interpretation_review"), ()]
    assert planned.material_review is True
    assert len(model.calls) == 2


def test_repeated_material_purpose_is_normalized_without_retry_or_lost_meaning():
    latest = "Review your saved formulation against the original account."
    model = Model(interpretation([item(
        latest, material_purposes=("interpretation_review", "interpretation_review"),
        record_requirement={
            "kind": "review",
            "target_ids": [],
            "operation": "none",
            "success_condition": (
                "The saved formulation faithfully represents the original "
                "account."
            ),
        })]))

    planned = interpret(model, Conversation((), current_matter_id="current-file"), latest)

    assert planned.items[0].material_purposes == ("interpretation_review",)
    assert planned.material_review is True
    assert len(model.calls) == 2


@pytest.mark.parametrize("fault", ["missing", "unknown"])
def test_invalid_fresh_purpose_gets_one_precise_correction_with_original_context(fault):
    conversation = Conversation((
        Message("earlier", "advocate", "The delivery actor is unknown."),),
        current_matter_id="current-file")
    latest = "Repair your saved delivery formulation against my original account."
    correct = interpretation([item(latest, material_purposes=("interpretation_review",),
                                    record_requirement={
                                        "kind": "review",
                                        "target_ids": [],
                                        "operation": "none",
                                        "success_condition": (
                                            "The delivery formulation "
                                            "preserves the original "
                                            "unknown actor."
                                        ),
                                    })])
    wrong = json.loads(json.dumps(correct))
    if fault == "missing":
        wrong["items"][0].pop("material_purposes")
    else:
        wrong["items"][0]["material_purposes"] = ["completed_record_change"]

    class CorrectedModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            if prompt.operation == "interpret_conversation":
                self.data = (correct if any(call[0].operation == "interpret_conversation"
                                           for call in self.calls) else wrong)
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)

    model = CorrectedModel(wrong)

    planned = interpret(model, conversation, latest)

    assert planned.items[0].material_purposes == ("interpretation_review",)
    assert len(model.calls) == 3
    feedback = json.loads(model.calls[2][0].user)
    assert "material_purposes" in feedback["validation_issue"]
    assert feedback["original_input"] == json.loads(model.calls[1][0].user)
    assert feedback["original_input"]["earlier_conversation"][0]["text"] == (
        "The delivery actor is unknown.")


def test_a_model_global_material_switch_cannot_override_owned_item_purposes():
    latest = "Repeat the reported delivery date."
    supplied = interpretation([
        item(latest, step="answer", reply="The reported date is unchanged.")])
    supplied["material_review"] = True
    model = Model(supplied)

    with pytest.raises(SchemaViolation, match="undeclared properties"):
        interpret(model, Conversation((), current_matter_id="current-file"), latest)

    assert len(model.calls) == 3
