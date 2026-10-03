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
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, SchemaViolation, Tier, Usage


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
                           "target_ids": []}],
            "next_work": [],
            "sufficiency": {"status": "needs_input", "block_id": f"limit-{index}"}}


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
                    "uncertainty": "reported"}],
        "questions": [{"id": "record-question", "block_id": "mixed",
                       "purpose": "Identify the reported record's contents.", "target_ids": []}],
        "next_work": [{"id": "review", "block_id": "mixed",
                       "purpose": "Review the available record when supplied.", "target_ids": []}],
        "sufficiency": {"status": "needs_input", "block_id": "mixed"},
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
    assert model.tiers == [Tier.ROUTINE, Tier.JUDGE]
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
    assert model.tiers == [Tier.ROUTINE, Tier.JUDGE] * (1 if accepted else 2)
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


def test_answer_only_diversion_needs_no_continuation_or_verifier():
    model = ContinuationModel([])
    plan = conversation_plan(items=(WorkItem(
        request="Hello", relation="aside", matter_scope="none",
        priority="ordinary", next_step="answer", reply="Hello."),))

    result = _continue(model, latest="Hello", plan=plan)

    assert result.units == ()
    assert result.coverage == ()
    assert model.calls == []
