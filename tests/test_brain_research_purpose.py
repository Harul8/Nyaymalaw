"""Requested factual work and legal authority keep separate served scopes."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.conversation import WorkItem
from nm.brain.execution_contracts import effect_catalogue
from nm.brain.work_state import project_work
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.brain_reader_fixture import (
    reader_operations,
    reviewed_record_verdicts,
    source_treatment_reply,
)
from tests.brain_research_fixture import Corpus, ResearchModel
from tests.test_brain_continuation_service import send
from tests.test_brain_turn import plan

ACCOUNT = (
    "We act for Nila. The equipment has not been returned. The payment remains withheld. "
    "Keep these reported issues on the file."
)
SUMMARY = "You report that the equipment has not been returned and payment remains withheld."
LEGAL_QUESTION = (
    "Which legal conditions govern recovery of the retained equipment and withheld payment?"
)
RECONCILIATION_REQUIREMENT = {
    "kind": "review", "operation": "none", "target_ids": [],
    "success_condition": (
        "Check the recorded formulations against the saved account, preserving "
        "uncertainty and leaving legal assessment unfinished."),
}


def opening():
    result = plan(ACCOUNT, scope="proposed", step="legal_work", reply="I will check the account.",
                  title="Nila: Reported equipment and payment issues",
                  summary="The advocate reports unreturned equipment and withheld payment.",
                  material_purposes=("account_contribution",),
                  record_requirement={
                      "kind": "change", "operation": "new", "target_ids": [],
                      "success_condition": (
                          "Retain the separately reported unreturned-equipment and withheld-"
                          "payment issues on the file without treating the account as proved.")})
    result["items"][0].update(response_basis="conversation_record", research_question="")
    # Original ACCOUNT L4 asks to retain these separately reported issues.
    # Scope is declared before either reader proposes a record.
    result["items"][0]["mutation_scopes"] = [{
        "authority_kind": "account_contribution", "authority_source_ids": ["L4"],
        "target_scope": "exact", "target_ids": [], "permitted_relations": ["new"],
    }]
    return result


def factual_unit(index=0, *, earlier=False, complete_task=False, record_result="none"):
    identifier = f"account-{index}"
    return {
        "request_index": index,
        "blocks": [{"id": identifier, "kind": "account", "text": SUMMARY,
                    "span_ids": ["P1S2", "P1S3"] if earlier else ["L2", "L3"],
                    "record_ids": [], "legal_source_ids": [], "uncertainty": "reported"}],
        "questions": [], "next_work": [], "work": {"existing_id": "", "create": True},
        "record_outcome": {"status": record_result,
                           "block_id": identifier if record_result != "none" else "",
                           "effect_ids": [], "current_record_ids": [],
                           "reason": "Explicit fixture declaration for this scoped record result."
                           if record_result != "none" else ""},
        "sufficiency": {"status": "complete", "block_id": identifier},
        "progress_updates": [{"target_id": "$work", "status": "complete",
                              "block_id": identifier, "span_ids": [],
                              "reason": "The requested attributed factual summary is displayed."}]
        if complete_task else [],
    }


def legal_limit(*, index=1, falsely_complete=False):
    return {
        "request_index": index,
        "blocks": [{"id": "legal-limit", "kind": "limitation",
                    "text": ("Legal research is unavailable; the requested assessment "
                             "remains unfinished."),
                    "span_ids": [], "record_ids": [], "legal_source_ids": [],
                    "uncertainty": "none"}],
        "questions": [], "next_work": [], "work": {"existing_id": "", "create": True},
        "sufficiency": {"status": "complete" if falsely_complete else "partial",
                        "block_id": "legal-limit"},
        "progress_updates": [],
    }


class RecordResearchModel(ResearchModel):
    """Deterministic proposals exercise the actual public orchestration boundary."""

    def __init__(self, routes, continuations, *, dispute_reads):
        super().__init__(routes, continuations)
        self.dispute_reads = iter(dispute_reads)
        self.prompt_systems = []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.prompt_systems.append(prompt.system)
        if prompt.operation in ("continue_conversation", "verify_continuation"):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            payload = json.loads(prompt.user)
            data = deepcopy(result.data)
            if prompt.operation == "continue_conversation":
                for unit in data["units"]:
                    if unit.get("record_outcome", {}).get("status") == "performed":
                        # The opening fixture explicitly declares this result;
                        # the catalogue only supplies its owned selector IDs.
                        unit["record_outcome"]["effect_ids"] = [
                            identity for identity, row in payload["record_effect_catalogue"].items()
                            if row["kind"] == "disputes"]
            else:
                receipt = payload["input"]["material_coverage"]["execution"]
                for row in data["verdicts"]:
                    requirement = receipt["requests"][row["request_index"]]["record_requirement"]
                    if requirement == opening()["items"][0]["record_requirement"]:
                        row["record_check"] = {
                            "outcome": "fulfilled",
                            "reason": ("Explicit independent fixture judgment: both separately "
                                       "reported issues were retained with attribution."),
                        }
                    elif requirement == RECONCILIATION_REQUIREMENT:
                        row["record_check"] = {
                            "outcome": "no_change_justified",
                            "reason": ("Explicit independent fixture judgment: the retained "
                                       "formulations preserve the account and its uncertainty."),
                        }
            return replace(result, data=data)
        if prompt.operation not in (
                "classify_account_sources", "extract_disputes", "verify_disputes"):
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        self.schemas.append((prompt.operation, deepcopy(schema)))
        self.tiers.append(tier)
        if prompt.operation == "classify_account_sources":
            data = source_treatment_reply(prompt.operation, payload)
        elif prompt.operation == "extract_disputes":
            data = reader_operations(next(self.dispute_reads), payload,
                                     link_field="related_dispute_ids")
        else:
            data = reviewed_record_verdicts(payload, {"verdicts": [{
                "candidate_id": row["candidate_id"], "candidate_role": "independent_dispute",
                "operation_supported": True, "verdict": "accept",
                "reason": "The reported issue remains a distinct attributed account.",
            } for row in payload["candidates"]]}, scripted_full_scope=True)
        return ModelResult(text=None, data=data, tier=tier, provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


def disputes():
    return [{"statement": statement, "label": label, "source_id": source,
             "relation": "new", "related_dispute_ids": [], "matter_scope": "proposed",
             "basis": "stated", "importance": "central",
             "why_material": "The reported conduct needs its own practical resolution.",
             "identification": "identified", "clarification": ""}
            for source, statement, label in (
                ("L2", "The equipment has not been returned.", "Unreturned equipment"),
                ("L3", "The payment remains withheld.", "Withheld payment"))]


def wire(wired, monkeypatch, model):
    corpus = Corpus(state="unavailable")
    wired.legal_search = corpus
    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    return corpus


def test_public_factual_reconciliation_completes_while_automatic_dispute_research_is_unavailable(
        client, wired, monkeypatch):
    latest = (
        "Reconcile the recorded formulations with my account and give me a short factual summary. "
        "Keep uncertainty visible and leave legal assessment unfinished."
    )
    requested = plan(latest, scope="current", step="legal_work", relation="continues",
                     reply="I will reconcile the attributed record.")
    requested["items"][0].update(response_basis="conversation_record", research_question="")
    requested["items"][0]["material_purposes"] = ["interpretation_review"]
    requested["items"][0]["record_requirement"] = deepcopy(RECONCILIATION_REQUIREMENT)
    model = RecordResearchModel(
        [opening(), requested],
        [{"units": [factual_unit(record_result="performed")]},
         {"units": [factual_unit(earlier=True, complete_task=True,
                                  record_result="review_no_change")]}],
        dispute_reads=[disputes(), []])
    corpus = wire(wired, monkeypatch, model)
    first = send(client, ACCOUNT, "factual-purpose-opening")
    prior = deepcopy(wired.store.load(first["matter_id"]).brain_chat[0])
    opening_receipt = prior["response"]["material_coverage"]["execution"]
    opening_continuation = prior["response"]["continuation"]
    performed = {identity: row for identity, row in effect_catalogue(opening_receipt).items()
                 if row["performed"]}
    assert len(performed) == 2
    assert set(opening_continuation["units"][0]["record_outcome"]["effect_ids"]) == set(performed)
    assert opening_continuation["units"][0]["record_check"]["outcome"] == "fulfilled"
    assert set(opening_continuation["record_snapshot"]["record_catalogue"]) == {
        row["result_id"] for row in performed.values()}
    call_start = len(model.calls)

    answer = send(client, latest, "factual-purpose-reconciliation", opened=first)
    calls = model.calls[call_start:]
    replay = send(client, latest, "factual-purpose-reconciliation", opened=first)

    assert first["metrics"]["llm_calls"] == 9
    assert answer["metrics"]["llm_calls"] == 9
    assert [operation for operation, _ in calls] == [
        "interpret_conversation", "classify_account_sources", "extract_disputes",
        "verify_disputes", "extract_legal_details", "verify_material_grounding",
        "decompose_disputes", "continue_conversation", "verify_continuation"]
    assert len(corpus.calls) == 4
    assert all(subject["kind"] == "dispute" for subject, _, _ in corpus.calls)
    classified = [payload for operation, payload in model.calls
                  if operation == "classify_account_sources"]
    assert len(classified) == 2
    assert all(not {"candidates", "prior_disputes", "assignment_targets"}.intersection(payload)
               for payload in classified)
    compose = next(payload for operation, payload in calls if operation == "continue_conversation")
    assert compose["work_items"][0]["research_question"] == ""
    assert compose["work_items"][0]["response_basis"] == "conversation_record"
    assert ["".join(span["text"] for span in row["source_spans"])
            for row in compose["earlier_conversation"]] == [
                ACCOUNT, "\n".join(row["text"] for row in first["elements"])]
    released = answer["continuation"]["units"][0]
    assert released["sufficiency"]["status"] == "complete"
    assert released["blocks"][0]["legal_source_ids"] == []
    assert answer["continuation"]["coverage"][0]["state"] == "ok"
    assert SUMMARY in "\n".join(row["text"] for row in answer["elements"])
    saved = wired.store.load(first["matter_id"])
    assert saved.brain_chat[0] == prior
    saved_receipt = saved.brain_chat[-1]["response"]["material_coverage"]["execution"]
    assert saved_receipt["review_scope"]["requests"][0]["record_requirement"] == \
        RECONCILIATION_REQUIREMENT
    for stage in ("dispute_review", "detail_review"):
        assessment = saved_receipt["stages"][stage]["account_coverage"]
        assert assessment["state"] == "complete"
        assert assessment["review_scope"] == saved_receipt["review_scope"]
    saved_continuation = saved.brain_chat[-1]["response"]["continuation"]
    assert saved_continuation["record_snapshot"]["record_catalogue"] == \
        opening_continuation["record_snapshot"]["record_catalogue"]
    assert released["record_outcome"]["status"] == "review_no_change"
    assert released["record_outcome"]["effect_ids"] == []
    assert released["record_check"]["outcome"] == "no_change_justified"
    assert [row["message"] for row in saved.brain_chat] == [ACCOUNT, latest]
    catalogue = saved.brain_chat[-1]["response"]["material_coverage"]["source_treatments"]
    assert all(payload["source_treatments"] == catalogue for operation, payload in calls
               if operation in ("extract_disputes", "extract_legal_details"))
    assert all(read["subject"]["kind"] == "dispute" and read["state"] == "unavailable"
               for read in saved.brain_chat[-1]["response"]["research_reads"])
    assert next(row for row in project_work(saved)["rows"]
                if row["id"] == released["work"]["progress_id"])["status"] == "complete"
    assert replay["replayed"] is True and replay["metrics"]["llm_calls"] == 0
    assert len(model.calls) == call_start + len(calls)
    assert all(all(label in system for label in ("Message:", "Purpose:", "Look for:", "Outcome:"))
               for system in model.prompt_systems)


@pytest.mark.parametrize("falsely_complete", [False, True])
def test_public_mixed_factual_and_legal_results_preserve_independent_completion(
        client, wired, monkeypatch, falsely_complete):
    latest = ("Give me a factual summary of the account. "
              "Separately, assess the legal basis for recovery.")
    requested = plan(latest, scope="current", step="legal_work", relation="continues",
                     reply="I will prepare the attributed factual summary.")
    requested["items"][0].update(request="Give me a factual summary of the account.",
                                 response_basis="conversation_record",
                                 research_question="")
    requested["items"].append({**requested["items"][0],
                               "request": "Assess the legal basis for recovery.",
                               "reply": "The legal assessment needs checked authority.",
                               "response_basis": "legal_authority",
                               "research_question": LEGAL_QUESTION})

    def mixed_reply(payload):
        assert [row["research_question"] for row in payload["work_items"]] == ["", LEGAL_QUESTION]
        assert [row["response_basis"] for row in payload["work_items"]] == [
            "conversation_record", "legal_authority"]
        assert payload["legal_sources"] == {}
        return {"units": [factual_unit(earlier=True, complete_task=True),
                          legal_limit(falsely_complete=falsely_complete)]}

    def repair_legal_only(payload):
        assert [row["request_index"] for row in payload["work_items"]] == [1]
        assert "legal-authority enquiry" in payload["correction"]["validation_issues"][0]["issue"]
        return {"units": [legal_limit()]}

    replies = [{"units": [factual_unit(record_result="performed")]}, mixed_reply]
    if falsely_complete:
        replies.append(repair_legal_only)
    model = RecordResearchModel([opening(), requested], replies, dispute_reads=[disputes()])
    corpus = wire(wired, monkeypatch, model)
    first = send(client, ACCOUNT, f"mixed-purpose-opening-{falsely_complete}")
    prior = deepcopy(wired.store.load(first["matter_id"]).brain_chat[0])
    call_start = len(model.calls)

    answer = send(client, latest, f"mixed-purpose-followup-{falsely_complete}", opened=first)
    calls = model.calls[call_start:]
    replay = send(client, latest, f"mixed-purpose-followup-{falsely_complete}", opened=first)

    assert answer["metrics"]["llm_calls"] == (6 if falsely_complete else 4)
    assert replay["metrics"]["llm_calls"] == 0
    assert len(model.calls) == call_start + len(calls)
    searched = corpus.calls[2:]
    assert len(searched) == 3
    assert [subject["kind"] for subject, _, _ in searched].count("dispute") == 2
    enquiries = [subject for subject, _, _ in searched if subject["kind"] == "request"]
    assert len(enquiries) == 1 and enquiries[0]["question"] == LEGAL_QUESTION
    units = answer["continuation"]["units"]
    assert [row["request_index"] for row in units] == [0, 1]
    assert [row["sufficiency"]["status"] for row in units] == ["complete", "partial"]
    saved = wired.store.load(first["matter_id"])
    assert saved.brain_chat[0] == prior
    assert [row["message"] for row in saved.brain_chat] == [ACCOUNT, latest]
    statuses = {row["id"]: row["status"] for row in project_work(saved)["rows"]}
    assert statuses[units[0]["work"]["progress_id"]] == "complete"
    assert statuses[units[1]["work"]["progress_id"]] == "pending"
    reviewed = [row["request_index"] for operation, payload in calls
                if operation == "verify_continuation" for row in payload["units"]]
    assert reviewed.count(0) == reviewed.count(1) == 1


@pytest.mark.parametrize("repair", [False, True])
def test_public_record_basis_cannot_inherit_saved_legal_enquiry(
        client, wired, monkeypatch, repair):
    legal_request = "Assess the legal basis for recovery."
    legal = plan(legal_request, scope="current", step="legal_work", relation="continues",
                 reply="That assessment needs checked legal authority.")
    legal["items"][0].update(response_basis="legal_authority", research_question=LEGAL_QUESTION)
    latest = ("Summarise the saved factual account. "
              "Leave legal research and document review pending.")
    factual = plan(latest, scope="current", step="legal_work", relation="continues",
                   reply="I will provide an attributed factual summary.")
    # A copied enquiry conflicts with the explicit current-result basis.
    factual["items"][0].update(response_basis="conversation_record",
                               research_question=LEGAL_QUESTION)
    corrected = deepcopy(factual)
    corrected["items"][0]["research_question"] = ""

    def repair_interpretation(payload):
        assert payload["original_input"]["latest_message"] == latest
        assert "requires an empty research_question" in payload["validation_issue"]
        assert payload["rejected_output"]["items"][0]["research_question"] == LEGAL_QUESTION
        assert any(row["question"] == LEGAL_QUESTION
                   for row in payload["original_input"]["saved_research_coverage"])
        return corrected if repair else factual

    replies = [{"units": [factual_unit(record_result="performed")]},
               {"units": [legal_limit(index=0)]}]
    if repair:
        replies.append({"units": [factual_unit(earlier=True, complete_task=True)]})
    model = RecordResearchModel([opening(), legal, factual, repair_interpretation], replies,
                                dispute_reads=[disputes()])
    corpus = wire(wired, monkeypatch, model)
    first = send(client, ACCOUNT, f"basis-inherit-opening-{repair}")
    second = send(client, legal_request, f"basis-inherit-legal-{repair}", opened=first)
    prior = deepcopy(wired.store.load(first["matter_id"]).brain_chat)
    call_start = len(model.calls)
    search_start = len(corpus.calls)
    body = {"message": latest, "turn_id": f"basis-inherit-factual-{repair}",
            "matter_id": first["matter_id"], "chat_id": first["chat_id"]}

    response = client.post("/api/turn", json=body)

    calls = model.calls[call_start:]
    assert second["metrics"]["llm_calls"] == 4
    assert len(corpus.calls) == search_start
    saved = wired.store.load(first["matter_id"])
    if repair:
        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["metrics"]["llm_calls"] == 4
        assert [operation for operation, _ in calls] == [
            "interpret_conversation", "interpret_conversation",
            "continue_conversation", "verify_continuation"]
        assert saved.brain_chat[:-1] == prior
        assert saved.brain_chat[-1]["message"] == latest
        assert saved.brain_chat[-1]["response"]["research_reads"] == []
        released = answer["continuation"]["units"][0]
        assert released["sufficiency"]["status"] == "complete"
        statuses = {row["id"]: row["status"] for row in project_work(saved)["rows"]}
        assert statuses[released["work"]["progress_id"]] == "complete"
        assert statuses[second["continuation"]["units"][0]["work"]["progress_id"]] == "pending"
        replay = client.post("/api/turn", json=body)
        assert replay.status_code == 200 and replay.json()["metrics"]["llm_calls"] == 0
    else:
        assert response.status_code == 503
        assert saved.brain_chat == prior
        assert [operation for operation, _ in calls] == [
            "interpret_conversation", "interpret_conversation"]
    assert len(model.calls) == call_start + len(calls)


@pytest.mark.parametrize("fault", ["missing_basis", "legal_basis_without_question"])
def test_public_fresh_basis_is_required_before_source_dispatch_or_admission(
        client, wired, monkeypatch, fault):
    request = "Assess the legal conditions governing recovery."
    routing = plan(request, scope="none", step="legal_work", reply="I will check the authority.")
    routing["items"][0].update(response_basis="legal_authority",
                               research_question="" if fault == "legal_basis_without_question"
                               else LEGAL_QUESTION)

    class MissingBasisModel(RecordResearchModel):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            if fault == "missing_basis" and prompt.operation == "interpret_conversation":
                result.data["items"][0].pop("response_basis")
            return result

    model = MissingBasisModel([routing, routing], [], dispute_reads=[])
    corpus = wire(wired, monkeypatch, model)

    response = client.post("/api/turn", json={"message": request, "turn_id": f"basis-{fault}"})

    assert response.status_code == 503
    assert [operation for operation, _ in model.calls] == [
        "interpret_conversation", "interpret_conversation"]
    correction = model.calls[1][1]
    assert "response_basis" in correction["validation_issue"]
    assert corpus.calls == []
    assert not wired.store.list_for("adv_demo").matters


@pytest.mark.parametrize("question", ["", LEGAL_QUESTION])
def test_older_in_process_work_items_keep_their_existing_evidence_basis(question):
    item = WorkItem("Review the account", "new", "none", "ordinary", "legal_work",
                    research_question=question)

    assert item.research_question == question
    assert item.response_basis == ("legal_authority" if question else "conversation_record")
