"""A consequential reply is released only as a checked, attributable unit."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.brain.conversation import (
    Conversation,
    Message,
    OpeningCandidate,
    TurnPlan,
    WorkItem,
)
from nm.brain.history import IncompleteConversation
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    ProviderUnavailable,
    SchemaViolation,
    Tier,
    TierUnavailable,
    Usage,
)


class ContinuationModel:
    provider = "scripted"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.tiers = []

    def context_budget(self, tier):
        return 100_000

    def resolved_model(self, tier):
        return "offline"

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append((prompt, payload))
        self.tiers.append(tier)
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        data = reply(payload) if callable(reply) else deepcopy(reply)
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline",
            model="offline", usage=Usage(0, 0, 0), latency_ms=0,
            completion=Completion.COMPLETE,
        )


def conversation_plan(*, items=None):
    if items is None:
        items = (WorkItem(
            request="Review the reported account", relation="new",
            matter_scope="proposed", priority="ordinary", next_step="legal_work",
            reply="I will review the account before reaching a supported view."),)
    return TurnPlan(tuple(items), "Review the reported account",
                    OpeningCandidate(False, "", ""), False)


def unit(index=0, *, text="You report holding a signed receipt.",
         span_ids=("L1",), question="What outcome would you like to achieve?"):
    blocks = [
        {"id": f"account-{index}", "kind": "account", "text": text,
         "span_ids": list(span_ids), "record_ids": [], "legal_source_ids": [],
         "uncertainty": "reported"},
        {"id": f"question-{index}", "kind": "question", "text": question,
         "span_ids": ["L1"], "record_ids": [], "legal_source_ids": [],
         "uncertainty": "none"},
        {"id": f"limit-{index}", "kind": "limitation",
         "text": "The record and applicable legal sources have not been checked.",
         "span_ids": [], "record_ids": [], "legal_source_ids": [],
         "uncertainty": "none"},
    ]
    return {"request_index": index, "blocks": blocks,
            "questions": [{"id": f"objective-{index}",
                           "block_id": f"question-{index}",
                           "purpose": "Understand the user's intended outcome.",
                           "target_ids": [], "existing_id": ""}],
            "next_work": [],
            "sufficiency": {"status": "needs_input", "block_id": f"limit-{index}"},
            "work": {"existing_id": "", "create": True}, "progress_updates": []}


def verdict(*indexes, accept=True, reason="The complete unit preserves its support and limits."):
    return {"verdicts": [{"request_index": index,
                          "verdict": "accept" if accept else "reject",
                          "reason": reason} for index in indexes]}


def mixed_purpose_unit():
    return {
        "request_index": 0,
        "blocks": [{"id": "mixed", "kind": "limitation",
                    "text": ("You report holding a signed receipt. Its contents have not been "
                             "assessed. Could you share what it records for the requested review?"),
                    "span_ids": ["L1"], "record_ids": [], "legal_source_ids": [],
                    "uncertainty": "reported"},
                   {"id": "next-work", "kind": "next_step",
                    "text": "If helpful, we can compare the reported terms with the record's text.",
                    "span_ids": ["L1"], "record_ids": [], "legal_source_ids": [],
                    "uncertainty": "reported"}],
        "questions": [{"id": "record-question", "block_id": "mixed",
                       "purpose": "Identify the reported record's contents.",
                       "target_ids": [], "existing_id": ""}],
        "next_work": [{"id": "review", "block_id": "next-work",
                       "purpose": "Offer a focused comparison if the user wants it.",
                       "target_ids": [], "existing_id": ""}],
        "sufficiency": {"status": "needs_input", "block_id": "mixed"},
        "work": {"existing_id": "", "create": True}, "progress_updates": [],
    }


def _continue(model, *, latest="I have a signed receipt.", conversation=None,
              plan=None, **kwargs):
    from nm.brain.continuation import continue_conversation

    return continue_conversation(
        model, conversation=conversation or Conversation(()), latest=latest,
        plan=plan or conversation_plan(), **kwargs)


def _operation_names(model):
    return [prompt.operation for prompt, _ in model.calls]


def test_first_turn_checks_the_entire_visible_reply_and_resolves_exact_words():
    proposed = unit()
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])

    result = _continue(model)

    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert model.tiers == [Tier.JUDGE, Tier.JUDGE]
    assert len(result.units) == 1
    assert result.coverage[0]["state"] == "ok"
    checked = model.calls[1][1]
    assert checked["units"] == [proposed]
    assert checked["input"]["earlier_conversation"] == []
    assert "I have a signed receipt." in json.dumps(result.units)
    for prompt, _ in model.calls:
        for heading in ("Message:", "Purpose:", "Look for:", "Outcome:"):
            assert heading in prompt.system


@pytest.mark.parametrize("accepted", (True, False))
def test_mixed_purpose_block_links_semantic_work_and_requires_independent_review(accepted):
    proposed = mixed_purpose_unit()
    if not accepted:
        proposed["blocks"][0]["text"] = (
            "The receipt proves the opposing party's liability. "
            "Could you share it for the requested review?")
    reason = ("The complete premise and requested work preserve the attributed limits."
              if accepted else "Possessing a receipt does not establish liability.")
    replies = [{"units": [proposed]}, verdict(0, accept=accepted, reason=reason)]
    if not accepted:
        replies.extend([{"units": [proposed]}, verdict(0, accept=False, reason=reason)])
    model = ContinuationModel(replies)

    result = _continue(model)

    checks = [payload for prompt, payload in model.calls
              if prompt.operation == "verify_continuation"]
    assert checks
    assert all(payload["units"] == [proposed] for payload in checks)
    assert model.tiers == [Tier.JUDGE, Tier.JUDGE] * (1 if accepted else 2)
    if accepted:
        assert result.units[0]["questions"] == proposed["questions"]
        assert result.units[0]["next_work"] == proposed["next_work"]
        assert result.units[0]["blocks"][0]["kind"] == "limitation"
        assert result.coverage[0]["state"] == "ok"
    else:
        assert result.units == ()
        assert result.coverage[0]["state"] == "unavailable"


def test_local_legal_source_ids_cannot_alias_another_research_passage():
    sources = tuple({
        "id": "A1", "subject_id": subject, "kind": "provision",
        "title": "Synthetic Act", "locator": "section 3", "text": passage,
        "verification": {"reason": "The synthetic passage was checked."},
    } for subject, passage in (
        ("request-alpha", "The relevant obligation depends on the applicable instrument."),
        ("request-beta", "The disputed event must be identified from the record."),
    ))

    def composed(payload):
        selected = next(key for key, source in payload["legal_sources"].items()
                        if source["subject_id"] == "request-alpha")
        proposed = unit()
        proposed["blocks"].insert(1, {
            "id": "source-assessment", "kind": "assessment",
            "text": "The supplied passage makes the applicable instrument relevant.",
            "span_ids": [], "record_ids": [], "legal_source_ids": [selected],
            "uncertainty": "conditional",
        })
        return {"units": [proposed]}

    model = ContinuationModel([composed, verdict(0)])

    result = _continue(model, checked_sources=sources)

    catalogue = model.calls[0][1]["legal_sources"]
    assert len(catalogue) == 2
    assert len(set(catalogue)) == 2
    assert all(key != "A1" for key in catalogue)
    block = next(row for row in result.units[0]["blocks"]
                 if row["id"] == "source-assessment")
    assert block["references"][0]["text"] == sources[0]["text"]
    assert block["references"][0]["subject_id"] == "request-alpha"
    assert sources[1]["text"] not in json.dumps(block)


def test_one_passage_preserves_the_distinct_checked_uses_of_two_requirements():
    shared = {"id": "A1", "kind": "provision", "title": "Synthetic Act",
              "locator": "section 3", "text": "The applicable instrument defines the obligation."}
    rows = [{"label": label, "sources": [{
        **shared, "verification": {"reason": reason},
    }]} for label, reason in (
        ("Identify the instrument", "It identifies the applicable instrument."),
        ("Identify the obligation", "It identifies the obligation's source."),
    )]
    requirements = {"state": "ok", "by_dispute": {"D1": rows},
                    "status_by_dispute": {"D1": "ok"}}
    disputes = {"state": "ok", "rows": [{"id": "D1", "label": "Contested obligation"}]}
    model = ContinuationModel([{"units": [unit()]}, verdict(0)])

    result = _continue(model, disputes=disputes, requirements=requirements,
                       latest_turn_id="current-turn-identity")

    catalogue = model.calls[0][1]["legal_sources"]
    assert len(catalogue) == 2
    assert {row["verification"]["reason"] for row in catalogue.values()} == {
        row["sources"][0]["verification"]["reason"] for row in rows}
    assert len({row["source_use_id"] for row in catalogue.values()}) == 2
    assert result.units[0]["blocks"][0]["references"][0]["turn_id"] == (
        "current-turn-identity")


def test_complete_history_preserves_correction_diversion_and_return():
    earlier = Conversation((
        Message("first", "advocate", "I thought the event was on Monday."),
        Message("first", "nm", "Please confirm the date if you can."),
        Message("correction", "advocate", "Correction: it was Tuesday."),
        Message("correction", "nm", "You have corrected the reported date."),
        Message("aside", "advocate", "Hello again."),
        Message("aside", "nm", "Hello."),
    ), current_matter_id="mat_current", current_work="Review the record")
    latest = "Please return to the review. I cannot obtain that document."
    proposed = unit(
        text="You corrected the reported date to Tuesday.", span_ids=("P3S1",),
        question="Is there another available record of the event?")
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])

    result = _continue(model, latest=latest, conversation=earlier)

    assert result.coverage[0]["state"] == "ok"
    payload = model.calls[0][1]
    history = payload["earlier_conversation"]
    assert [(row["turn_id"], row["role"]) for row in history] == [
        (message.turn_id, message.role) for message in earlier.messages]
    assert ["".join(span["text"] for span in row["source_spans"])
            for row in history] == [message.text for message in earlier.messages]
    assert "I cannot obtain that document." in json.dumps(payload)
    assert "Tuesday" in json.dumps(result.units[0]["blocks"][0]["references"])


def test_contextual_record_citation_preserves_answer_and_earlier_question():
    question = "Is the receipt unsigned?"
    conversation = Conversation((
        Message("first", "advocate", "We have a receipt."),
        Message("first", "nm", question),
        Message("answered", "advocate", "Yes."),
        Message("answered", "nm", "You have confirmed the reported receipt is unsigned."),
    ), current_matter_id="current")
    record = {"id": "answered:material:1", "kind": "circumstance",
              "source_turn_id": "answered", "quoted": "Yes.",
              "statement": "The advocate reports an unsigned receipt.",
              "prior_references": [{"turn_id": "first", "role": "nm", "quoted": question}]}
    proposed = unit(text=record["statement"], span_ids=())
    proposed["blocks"][0]["record_ids"] = [record["id"]]
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])

    result = _continue(model, conversation=conversation, latest="Summarise the reported account.",
                       material={"state": "ok", "rows": [record]})

    block = result.units[0]["blocks"][0]
    cited_record = next(ref for ref in block["references"] if ref["type"] == "material")
    assert cited_record["record"]["quoted"] == "Yes."
    context = [ref for ref in block["references"] if ref["type"] == "conversation"]
    assert [(ref["turn_id"], ref["role"], ref["text"]) for ref in context] == [
        ("first", "nm", question)]
    assert context[0]["id"] in block["span_ids"]
    assert context[0]["id"].startswith("context:first:nm:")
    assert model.calls[1][1]["units"] == [proposed]


def test_corrupt_record_context_refuses_before_composition():
    conversation = Conversation((
        Message("first", "advocate", "We have a receipt."),
        Message("first", "nm", "Is the receipt unsigned?"),
    ), current_matter_id="current")
    record = {"id": "first:material:1", "source_turn_id": "first",
              "quoted": "We have a receipt.", "statement": "A receipt is reported.",
              "prior_references": [{"turn_id": "first", "role": "advocate",
                                    "quoted": "Is the receipt unsigned?"}]}
    model = ContinuationModel([])

    with pytest.raises(IncompleteConversation, match="attributed"):
        _continue(model, conversation=conversation, material={"state": "ok", "rows": [record]})
    assert model.calls == []


def test_unknown_reference_gets_one_specific_repair_before_verification():
    bad = unit(span_ids=("foreign-record-span",))
    fixed = unit()
    model = ContinuationModel([
        {"units": [bad]}, {"units": [fixed]}, verdict(0),
    ])

    result = _continue(model)

    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]
    repair = model.calls[1][1]
    assert "foreign-record-span" in json.dumps(repair)
    assert repair["correction"]["validation_issues"]
    assert result.coverage[0]["state"] == "ok"
    assert "foreign-record-span" not in json.dumps(result.units)


def test_provider_schema_rejection_gets_one_feedback_correction_of_the_same_request():
    model = ContinuationModel([
        SchemaViolation("The provider rejected the response object."),
        {"units": [unit()]}, verdict(0),
    ])

    result = _continue(model)

    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]
    assert result.coverage[0]["state"] == "ok"
    feedback = model.calls[1][1]["correction"]
    assert "provider rejected" in json.dumps(feedback)
    assert model.calls[0][1]["latest_message_spans"] == (
        model.calls[1][1]["latest_message_spans"])


@pytest.mark.parametrize(("unsupported", "why"), [
    ("The signed receipt proves the allegation.", "Reported possession is not verified proof."),
    ("You concealed the facts deliberately.",
     "The record does not establish the user's intentions."),
    ("The statute guarantees recovery.", "No checked legal passage supports that conclusion."),
])
def test_semantic_repair_cannot_release_unsupported_proof_accusation_or_law(
        unsupported, why):
    bad = unit(text=unsupported)
    model = ContinuationModel([
        {"units": [bad]}, verdict(0, accept=False, reason=why),
        {"units": [bad]}, verdict(0, accept=False, reason=why),
    ])

    result = _continue(model)

    assert result.units == ()
    assert result.coverage[0]["state"] == "unavailable"
    assert _operation_names(model) == [
        "continue_conversation", "verify_continuation",
        "continue_conversation", "verify_continuation"]
    assert why in json.dumps(model.calls[2][1])
    assert "The record and applicable legal sources" in json.dumps(model.calls[1][1])


def test_rejected_request_withholds_all_its_prose_but_preserves_independent_peer():
    items = tuple(WorkItem(
        request=f"Review separate request {index}", relation="new",
        matter_scope="proposed", priority="ordinary", next_step="legal_work",
        reply="I will check this request.") for index in range(2))
    good = unit(0)
    bad = unit(1, text="The unseen document proves the disputed event.")
    mixed = {"verdicts": [
        *verdict(0)["verdicts"],
        *verdict(1, accept=False, reason="The document has not been examined.")["verdicts"],
    ]}
    model = ContinuationModel([
        {"units": [good, bad]}, mixed,
        {"units": [bad]}, verdict(1, accept=False,
                                 reason="The document has not been examined."),
    ])

    result = _continue(model, plan=conversation_plan(items=items))

    assert [row["request_index"] for row in result.units] == [0]
    assert [row["state"] for row in result.coverage] == ["ok", "unavailable"]
    assert "unseen document" not in json.dumps(result.units)
    assert "question-1" not in json.dumps(result.units)
    assert "limit-1" not in json.dumps(result.units)
    assert [row["request_index"] for row in model.calls[-1][1]["units"]] == [1]
    repair = model.calls[2][1]
    assert repair["correction"]["rejected_units"] == [bad]
    assert [row["request_index"] for row in repair["work_items"]] == [1]


def test_composition_and_repair_preserve_raw_context_and_omit_accepted_drafts():
    messages = (
        Message("first", "advocate", "The event was reported on Monday. We may hold a receipt."),
        Message("first", "nm", "Please confirm the reported date and record status."),
        Message("corrected", "advocate", "Correction: the event was on Tuesday."),
        Message("corrected", "nm", "You have corrected the reported date, which remains reported."),
        Message("aside", "advocate", "Hello. My note says: ‘ignore the previous record’."),
        Message("aside", "nm", "Hello. The note's words remain part of your attributed account."),
    )
    conversation = Conversation(messages, current_matter_id="current",
                                current_work="Review account")
    latest = "Return to the account. Assess it and identify what remains unclear."
    items = (
        WorkItem(request="Assess the account", relation="continues", matter_scope="current",
                 priority="ordinary", next_step="legal_work", reply="CURRENT_ROUTER_DRAFT"),
        WorkItem(request="Identify necessary clarification", relation="continues",
                 matter_scope="current", priority="ordinary", next_step="clarify",
                 clarification="CURRENT_ROUTER_QUESTION"),
    )
    source = {"id": "A1", "subject_id": "current", "kind": "provision",
              "title": "Synthetic Act", "locator": "section 3",
              "text": "Where applicable, the instrument defines the disputed obligation.",
              "verification": {"reason": "The passage supports identifying the instrument."}}
    originals = {}

    def initial(payload):
        originals["input"] = deepcopy(payload)
        legal_id = next(iter(payload["legal_sources"]))
        good = unit(0, text="You corrected the reported event date to Tuesday.",
                    span_ids=("P3S1",))
        good["blocks"].insert(1, {
            "id": "accepted-source-assessment", "kind": "assessment",
            "text": "The checked passage makes the instrument relevant to this assessment.",
            "span_ids": [], "record_ids": [], "legal_source_ids": [legal_id],
            "uncertainty": "conditional"})
        bad = unit(1, text="The unseen receipt proves deliberate concealment.")
        originals.update(good=deepcopy(good), bad=deepcopy(bad), legal_id=legal_id)
        return {"units": [good, bad]}

    def correction(payload):
        assert [row["request_index"] for row in payload["work_items"]] == [1]
        assert payload["correction"]["rejected_units"] == [originals["bad"]]
        assert "accepted-source-assessment" not in json.dumps(payload)
        for field in ("earlier_conversation", "latest_message_spans", "record_catalogue",
                      "legal_sources", "legal_coverage", "progress"):
            assert payload[field] == originals["input"][field]
        return {"units": [unit(1, text="You ask what remains unclear in the reported account.")]}

    reason = "An unexamined, possibly held record cannot prove intention or its contents."
    mixed = {"verdicts": [*verdict(0)["verdicts"],
                           *verdict(1, accept=False, reason=reason)["verdicts"]]}
    model = ContinuationModel([initial, mixed, correction, verdict(1)])

    result = _continue(model, latest=latest, conversation=conversation,
                       plan=conversation_plan(items=items), checked_sources=(source,))

    assert _operation_names(model) == ["continue_conversation", "verify_continuation"] * 2
    payload = originals["input"]
    assert "CURRENT_ROUTER_DRAFT" not in json.dumps(payload)
    assert "CURRENT_ROUTER_QUESTION" not in json.dumps(payload)
    assert all("reply" not in row and "clarification" not in row for row in payload["work_items"])
    history = payload["earlier_conversation"]
    assert [(row["turn_id"], row["role"],
             "".join(span["text"] for span in row["source_spans"]))
            for row in history] == [(row.turn_id, row.role, row.text) for row in messages]
    assert "".join(span["text"] for span in payload["latest_message_spans"]) == latest
    assert model.calls[2][1]["correction"]["validation_issues"] == [
        {"request_index": 1, "issue": reason}]
    for label in ("Message:", "Purpose:", "Look for:", "Outcome:"):
        assert model.calls[2][0].system.count(label) >= 2
    assert [row["request_index"] for row in result.units] == [0, 1]
    for block in result.units[0]["blocks"]:
        initial_block = next(row for row in originals["good"]["blocks"] if row["id"] == block["id"])
        assert {key: value for key, value in block.items() if key != "references"} == initial_block
    checked_block = next(row for row in result.units[0]["blocks"]
                         if row["id"] == "accepted-source-assessment")
    assert checked_block["references"][0]["id"] == originals["legal_id"]
    assert checked_block["references"][0]["text"] == source["text"]
    assert checked_block["references"][0]["verification"] == source["verification"]


def test_incomplete_verdict_retries_only_the_unresolved_request():
    items = tuple(WorkItem(
        request=f"Review separate request {index}", relation="new",
        matter_scope="proposed", priority="ordinary", next_step="legal_work",
        reply="I will check this request.") for index in range(2))
    model = ContinuationModel([
        {"units": [unit(0), unit(1)]}, verdict(0), verdict(1),
    ])

    result = _continue(model, plan=conversation_plan(items=items))

    assert _operation_names(model) == [
        "continue_conversation", "verify_continuation", "verify_continuation"]
    assert len(result.units) == 2
    assert [row["request_index"] for row in model.calls[-1][1]["units"]] == [1]


def test_verifier_outage_never_releases_the_unchecked_draft():
    model = ContinuationModel([
        {"units": [unit()]}, ProviderUnavailable("Synthetic outage"),
        {"units": [unit()]}, ProviderUnavailable("Synthetic outage"),
    ])

    result = _continue(model)

    assert result.units == ()
    assert result.coverage[0]["state"] == "unavailable"
    assert len(model.calls) == 2


@pytest.mark.parametrize("relation", ["aside", "new", "continues"])
def test_source_free_answer_route_needs_no_continuation_or_verifier(relation):
    model = ContinuationModel([])
    plan = conversation_plan(items=(WorkItem(
        request="Hello", relation=relation, matter_scope="none",
        priority="ordinary", next_step="answer", reply="Hello."),))

    result = _continue(model, latest="Hello", plan=plan)

    assert result.units == ()
    assert result.coverage == ()
    assert model.calls == []


@pytest.mark.parametrize("damage", ["no_requested_task", "contribution_task", "duplicate_owner"])
def test_progress_contract_repairs_only_invalid_unit_before_independent_check(damage):
    good = unit()
    invalid = deepcopy(good)
    items = None
    if damage == "no_requested_task":
        invalid["work"]["create"] = False
    elif damage == "contribution_task":
        good["work"]["create"] = False
        items = (WorkItem(request="A clarification of the reported account", relation="continues",
                          matter_scope="current", priority="ordinary", next_step="legal_work",
                          intent="contribution"),)
    else:
        invalid["next_work"] = [deepcopy(invalid["questions"][0])]
    model = ContinuationModel([{"units": [invalid]}, {"units": [good]}, verdict(0)])

    result = _continue(model, plan=conversation_plan(items=items))

    assert len(result.units) == 1
    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]
    assert model.calls[-1][1]["units"] == [good]
    assert model.calls[1][1]["correction"]["rejected_units"] == [invalid]
    assert len(result.units[0]["questions"]) == 1
    assert result.units[0]["next_work"] == []


def test_downgraded_writer_cannot_release_routine_response_or_reach_verifier():
    from nm.shared.model_traced import TracedModel

    class MissingWriter(ContinuationModel):
        def __init__(self):
            super().__init__([{"units": [unit()]}])
            self.dispatched = []

        def structured(self, prompt, schema, tier, *, max_tokens=None):
            self.dispatched.append((prompt.operation, tier))
            if tier is Tier.JUDGE:
                raise TierUnavailable("The synthetic writer tier is unavailable.")
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)

    inner = MissingWriter()
    traced = TracedModel(inner)

    result = _continue(traced)

    assert result.units == ()
    assert result.coverage[0]["state"] == "unavailable"
    assert inner.dispatched == [
        ("continue_conversation", Tier.JUDGE), ("continue_conversation", Tier.ROUTINE)]
    assert len(traced.calls) == 1
    assert traced.calls[0].downgraded_from == Tier.JUDGE.value


def progress_unit():
    proposed = unit(text="You intend to provide the reported record tomorrow.")
    proposed["progress_updates"] = [{
        "target_id": "$work", "status": "promised", "block_id": "account-0",
        "reason": "The advocate expressly promises the record in the selected words.",
        "span_ids": ["L2"]}]
    return proposed


def test_explicit_progress_sources_reach_display_owner_before_independent_review():
    proposed = progress_unit()
    unchanged = deepcopy(proposed)
    latest = "I have the reported account. I will provide the record tomorrow."
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])

    result = _continue(model, latest=latest, latest_turn_id="promise-source")

    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    checked = model.calls[1][1]["units"][0]
    assert checked["blocks"][0]["span_ids"] == ["L1", "L2"]
    assert checked["progress_updates"][0]["span_ids"] == ["L2"]
    references = result.units[0]["blocks"][0]["references"]
    assert [(row["id"], row["role"], row["turn_id"], row["text"]) for row in references] == [
        ("L1", "advocate", "promise-source", "I have the reported account."),
        ("L2", "advocate", "promise-source", "I will provide the record tomorrow.")]
    assert proposed == unchanged


@pytest.mark.parametrize("field,value,diagnostic", [
    ("target_id", "foreign-task", ".target_id 'foreign-task'"),
    ("block_id", "foreign-block", ".block_id 'foreign-block'"),
    ("span_ids", ["unknown-source"], ".span_ids selects unknown source 'unknown-source'"),
    ("span_ids", ["P1S1"], ".span_ids source 'P1S1' is not the advocate"),
    ("span_ids", ["L2", "L2"], ".span_ids contains duplicate source IDs"),
    ("reason", "", ".reason needs a nonempty explanation"),
])
def test_bad_progress_selection_gets_indexed_feedback_and_never_reaches_review(
        field, value, diagnostic):
    good = progress_unit()
    invalid = deepcopy(good)
    invalid["progress_updates"][0][field] = value
    model = ContinuationModel([{"units": [invalid]}, {"units": [good]}, verdict(0)])
    earlier = Conversation((Message("prior", "nm", "Please provide the reported record."),))

    result = _continue(model, latest=(
        "I have the reported account. I will provide the record tomorrow."), conversation=earlier)

    assert len(result.units) == 1
    assert _operation_names(model) == [
        "continue_conversation", "continue_conversation", "verify_continuation"]
    feedback = model.calls[1][1]["correction"]["validation_issues"][0]
    assert feedback["request_index"] == 0
    assert "progress_updates[0]" + diagnostic in feedback["issue"]
    checked = model.calls[-1][1]["units"][0]
    assert checked["progress_updates"][0] == good["progress_updates"][0]
    assert checked["blocks"][0]["span_ids"] == ["L1", "L2"]


def prior_task(status):
    return {"state": "ok", "rows": [{
        "id": "saved-task", "kind": "task", "origin": "requested",
        "text": "Review the reported account", "purpose": "Give the requested scoped review.",
        "status": status, "target_ids": [], "task_id": "", "source_turn_id": "prior",
        "request_index": 0, "block_id": "prior-response", "last_update_turn_id": "prior",
        "reason": "Earlier checked work status.", "matter_scope": "current",
    }], "events": [], "coverage": {"older_progress": "tracked"}, "diagnostics": []}


def complete_reply_unit(*, existing="saved-task", create=False):
    proposed = unit()
    proposed["blocks"] = [proposed["blocks"][0], proposed["blocks"][2]]
    proposed["questions"] = []
    proposed["work"] = {"existing_id": existing, "create": create}
    proposed["sufficiency"] = {"status": "complete", "block_id": "account-0"}
    return proposed


@pytest.mark.parametrize("accepted", [True, False])
def test_prior_complete_task_does_not_repeat_transition_or_exempt_latest_review(accepted):
    proposed = complete_reply_unit()
    reply = {"units": [proposed]}
    reason = "The latest requested scope still needs its own supported delivery."
    check = verdict(0, accept=accepted, reason=reason)
    model = ContinuationModel([reply, check] if accepted else [reply, check, reply, check])

    result = _continue(model, progress=prior_task("complete"))

    assert _operation_names(model) == ["continue_conversation", "verify_continuation"] * (
        1 if accepted else 2)
    assert all(payload["units"][0]["progress_updates"] == []
               for prompt, payload in model.calls if prompt.operation == "verify_continuation")
    assert all(payload["input"]["progress"]["rows"][0]["status"] == "complete"
               for prompt, payload in model.calls if prompt.operation == "verify_continuation")
    assert result.coverage[0]["state"] == ("ok" if accepted else "unavailable")
    assert len(result.units) == (1 if accepted else 0)


@pytest.mark.parametrize("status", [
    "new", "pending", "promised", "unavailable", "deferred", "cancelled",
])
def test_complete_immediate_reply_does_not_infer_new_or_existing_task_transition(status):
    is_new = status == "new"
    proposed = complete_reply_unit(existing="" if is_new else "saved-task", create=is_new)
    progress = None if is_new else prior_task(status)
    before = deepcopy(progress)
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])

    result = _continue(model, progress=progress)

    assert len(result.units) == 1
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
    assert result.units[0]["sufficiency"]["status"] == "complete"
    assert result.units[0]["progress_updates"] == []
    assert model.calls[-1][1]["units"] == [proposed]
    assert progress == before


@pytest.mark.parametrize("status", ["pending", "cancelled"])
def test_complete_immediate_reply_can_accompany_an_independently_checked_task_change(status):
    proposed = complete_reply_unit()
    proposed["progress_updates"] = [{
        "target_id": "$work", "status": status, "block_id": "account-0",
        "reason": "The user's explicit request supports the separate task-state change.",
        "span_ids": ["L1"]}]
    latest = ("Please reopen the earlier review; acknowledge this request."
              if status == "pending" else "Cancel the earlier review; acknowledge this request.")
    proposed["blocks"][0]["text"] = "You have requested a change to the earlier review."
    model = ContinuationModel([{"units": [proposed]}, verdict(0)])

    result = _continue(model, latest=latest, progress=prior_task("complete"))

    assert len(result.units) == 1
    assert result.units[0]["progress_updates"][0]["status"] == status
    assert result.units[0]["sufficiency"]["status"] == "complete"
    assert _operation_names(model) == ["continue_conversation", "verify_continuation"]
