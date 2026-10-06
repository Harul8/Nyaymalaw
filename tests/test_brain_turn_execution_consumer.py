"""Deterministic service checks; no real-model API or browser calls.

The model below declares explicit fixture decisions. These tests qualify
execution, persistence and replay boundaries, not legal or model semantics.
"""
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import turn as boundary
from nm.brain.conversation import WorkItem
from nm.brain.execution_contracts import effect_catalogue
from nm.brain.turn import BrainRefused, BrainService, BrainTurn, _CountedModel, chat_matter_id
from nm.shared.model_port import ContextOverflow, Prompt, ProviderUnavailable, Tier
from nm.shared.store_file_store import FileMatterStore
from tests.brain_reader_fixture import fixture_coverage, fixture_disposition
from tests.test_brain_material import Model, material, mutation_scope, plan

REVIEW = {"kind": "review", "target_ids": [], "operation": "none",
          "success_condition": "Check that the existing attributed record is faithful."}

INSTRUCTION_PURPOSES = {words: "non_account" for words in (
    "Check the saved record and leave it unchanged if it is faithful.",
    "Check the saved record and explain any unresolved distinction.",
    "Please review the earlier account.",
    "Check the saved record before confirming completion.",
    "Check the empty saved record.", "State any unresolved scope.",
    "Correct the records date to Wednesday.",
)}


class ConsumerModel(Model):
    def __init__(self, plans, *, unread_detail=False, unread_opening=False,
                 coverage_state="complete", record_goal_fulfilled=False):
        super().__init__(plans, source_purposes=INSTRUCTION_PURPOSES)
        self.seen = []
        self.unread_detail = unread_detail
        self.unread_opening = unread_opening
        self.coverage_state = coverage_state
        self.record_goal_fulfilled = record_goal_fulfilled

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        self.seen.append((prompt.operation, deepcopy(payload)))
        data = deepcopy(result.data)
        if prompt.operation in ("verify_disputes", "verify_material_grounding"):
            if self.unread_detail:
                data["verdicts"] = [row for row in data["verdicts"]
                                    if row["candidate_id"] != "D2"]
            if self.unread_opening:
                data["verdicts"] = [row for row in data["verdicts"]
                                    if row["candidate_id"] != "O1"]
            if "coverage_source_ids" in payload and self.coverage_state != "complete":
                # Deliberate independent uncertainty; this does not label an
                # empty extractor response complete or alter candidate support.
                identities = payload["coverage_source_ids"]
                data["coverage"] = fixture_coverage(
                    payload, state=self.coverage_state,
                    source_decisions={identity: "unresolved" for identity in identities},
                    dispositions=[fixture_disposition(payload, identity, status="unresolved")
                                  for identity in identities],
                    reason="Explicit fixture judgment: a distinction remains unresolved.")
        elif prompt.operation == "continue_conversation":
            receipt = payload["material_coverage"]["execution"]
            for unit in data["units"]:
                index = unit["request_index"]
                requirement = receipt["requests"][index]["record_requirement"]
                review = requirement["kind"] == "review"
                change = requirement["kind"] == "change"
                if not review and not change:
                    continue
                unit["blocks"][0].update(kind="completion", evidence_expression={
                    "operator": "record_result", "source_ids": [], "record_ids": [],
                    "focus": "none"})
                unit["record_outcome"] = {
                    "status": ("review_no_change" if review else
                               "performed" if change and self.record_goal_fulfilled else
                               "unresolved" if change else "none"),
                    "block_id": unit["blocks"][0]["id"] if review or change else "",
                    "effect_ids": [identity for identity, row in effect_catalogue(receipt).items()
                                   if row["performed"]]
                    if change and self.record_goal_fulfilled else [],
                    "current_record_ids": [],
                    "reason": "Explicit fixture judgment for this record goal."
                    if review or change else ""}
        elif prompt.operation == "verify_continuation":
            receipt = payload["input"]["material_coverage"]["execution"]
            for verdict in data["verdicts"]:
                requirement = receipt["requests"][verdict["request_index"]]["record_requirement"]
                if requirement["kind"] == "none":
                    continue
                verdict["record_check"] = {
                    "outcome": "no_change_justified" if requirement["kind"] == "review"
                    else "fulfilled" if requirement["kind"] == "change"
                    and self.record_goal_fulfilled else "unfinished"
                    if requirement["kind"] == "change" else "not_requested",
                    "reason": "Explicit independent fixture judgment for the declared record goal."}
        return replace(result, data=data)


def make_service(tmp_path, planned, **options):
    store = FileMatterStore(tmp_path, key="consumer-fixture-sealing-key")
    model = ConsumerModel([planned], **options)
    return BrainService(store, model), store, model


def plain_plan(message="Say hello."):
    return plan(message, items=[{
        "request": message, "relation": "new", "matter_scope": "none",
        "priority": "ordinary", "next_step": "answer", "reply": "Hello.",
        "clarification": "", "material_purposes": [],
        "record_requirement": {"kind": "none", "target_ids": [], "operation": "none",
                               "success_condition": ""}}])


def test_legitimate_empty_review_has_actual_coverage_and_a_no_change_receipt(tmp_path):
    message = "Check the saved record and leave it unchanged if it is faithful."
    planned = plan(message, material_purposes=("interpretation_review",),
                   record_requirement=deepcopy(REVIEW))
    planned["items"][0].update(next_step="answer", matter_scope="none",
                               reply="No record change is needed.")
    brain, store, model = make_service(tmp_path, planned)
    result = brain.run(BrainTurn("adv", message, "empty-review")).as_dict()
    receipt = result["material_coverage"]["execution"]
    for stage in ("dispute_review", "detail_review"):
        assert receipt["stages"][stage]["state"] == "checked"
        assessment = receipt["stages"][stage]["account_coverage"]
        assert assessment["state"] == "complete"
        assert assessment["review_scope"]["requests"][0]["record_requirement"] == REVIEW
    assert receipt["requests"][0]["fulfillment"] == "no_change_justified"
    assert receipt["requests"][0]["fulfillment_check"]["receipt_id"] == receipt["id"]
    assert receipt["display"]["element"] in result["elements"]
    assert "No changes were made" in receipt["display"]["element"]["text"]
    saved = store.load(chat_matter_id("adv", "empty-review"))
    assert saved.brain_chat[0]["response"] == result
    assert [operation for operation, _ in model.seen].count("verify_disputes") == 1


def test_unread_detail_preserves_checked_peer_without_false_rejection_or_completion(tmp_path):
    message = "The documents arrived on Tuesday. The equipment arrived on Thursday."
    first = material("event", "Documents arrived Tuesday.",
                     "The documents arrived on Tuesday.", placement="matter")
    second = material("event", "Equipment arrived Thursday.",
                      "The equipment arrived on Thursday.", placement="matter")
    planned = plan(message, candidates=[first, second], opening=True,
                   material_purposes=("account_contribution",))
    brain, store, model = make_service(tmp_path, planned, unread_detail=True)
    result = brain.run(BrainTurn("adv", message, "partial-read")).as_dict()
    receipt = result["material_coverage"]["execution"]
    assert len(result["material"]) == 1
    assert result["material_coverage"]["rejected_details"] == 0
    assert result["material_coverage"]["withheld_details"] == 0
    assert result["material_coverage"]["unread_details"] == 1
    stage = receipt["stages"]["detail_review"]
    assert stage["state"] == "checked"
    assert stage["review_status"]["state"] == "partial"
    assert stage["account_coverage"]["state"] == "unassessed"
    assert receipt["requests"][0]["fulfillment"] != "fulfilled"
    assert "remains unfinished" in receipt["display"]["element"]["text"]
    assert store.load(result["matter_id"]).brain_chat[0]["message"] == message
    assert [operation for operation, _ in model.seen].count("verify_material_grounding") == 2


def test_empty_review_with_a_real_gap_cannot_be_complete_or_release_router_prose(tmp_path):
    message = "Check the saved record and explain any unresolved distinction."
    planned = plan(message, material_purposes=("interpretation_review",),
                   record_requirement=deepcopy(REVIEW))
    planned["items"][0].update(next_step="answer", matter_scope="none",
                               reply="UNREVIEWED FULL COMPLETION")
    brain, _, _ = make_service(tmp_path, planned, coverage_state="partial")
    result = brain.run(BrainTurn("adv", message, "empty-with-gap")).as_dict()
    receipt = result["material_coverage"]["execution"]
    assert receipt["requests"][0]["fulfillment"] == "unfinished"
    assert result["blocked"] is True
    assert "UNREVIEWED" not in json.dumps(result["elements"])
    assert "remains unfinished" in receipt["display"]["element"]["text"]


def test_exhausted_unread_opening_does_not_restart_its_review_loop(tmp_path):
    message = "The records were delivered on Monday."
    planned = plan(message, opening=True, material_purposes=("account_contribution",))
    brain, _, model = make_service(tmp_path, planned, unread_opening=True)
    result = brain.run(BrainTurn("adv", message, "unread-opening")).as_dict()
    assert result["material_coverage"]["execution"]["stages"]["detail_review"]["opening_unread"]
    operations = [operation for operation, _ in model.seen]
    assert operations.count("verify_material_grounding") == 2
    assert "repair_opening" not in operations


def test_skipped_extraction_cannot_be_reported_as_completed_reading(tmp_path, monkeypatch):
    message = "Please review the earlier account."
    planned = plan(message, material_purposes=("interpretation_review",),
                   record_requirement=deepcopy(REVIEW))
    planned["items"][0]["matter_scope"] = "none"
    brain, store, _ = make_service(tmp_path, planned)
    monkeypatch.setattr(boundary, "_read_material", lambda *args, **kwargs: ((), ()))
    with pytest.raises(BrainRefused) as refused:
        brain.run(BrainTurn("adv", message, "skipped-reader"))
    assert refused.value.code == "material_execution_unconfirmed"
    assert store.load(chat_matter_id("adv", "skipped-reader")) is None


@pytest.mark.parametrize("saved_before_error", [False, True])
def test_save_failure_never_releases_a_prepared_receipt_but_lost_ack_reuses_exact_save(
    tmp_path, monkeypatch, saved_before_error,
):
    brain, store, _ = make_service(tmp_path, plain_plan())
    commit = store.commit

    def unreliable(matter, *, expected_version):
        if saved_before_error:
            commit(matter, expected_version=expected_version)
        raise OSError("Synthetic acknowledgement failure")

    monkeypatch.setattr(store, "commit", unreliable)
    request = BrainTurn("adv", "Say hello.", "save-ack")
    if not saved_before_error:
        with pytest.raises(BrainRefused) as refused:
            brain.run(request)
        assert refused.value.code == "brain_commit_unconfirmed"
        assert refused.value.committed == "unconfirmed"
        assert refused.value.gate_diagnostic["gate"] == "G-COMMIT"
        assert store.load(chat_matter_id("adv", "save-ack")) is None
    else:
        result = brain.run(request).as_dict()
        assert result["replayed"] is True
        assert result["material_coverage"]["execution"]["persistence"] == "committed"
        assert result["metrics"]["llm_calls"] > 0
        assert len(store.load(chat_matter_id("adv", "save-ack")).brain_chat) == 1


@pytest.mark.parametrize("damage", ["effect", "display", "changes", "snapshot", "fulfillment"])
def test_replay_rejects_tampered_result_evidence_before_model_calls(tmp_path, monkeypatch, damage):
    planned = plan("Review the saved record.", material_purposes=("interpretation_review",),
                   record_requirement=deepcopy(REVIEW))
    planned["items"][0]["matter_scope"] = "none"
    planned["items"][0].update(next_step="answer", matter_scope="none",
                               reply="No record change is needed.")
    brain, store, model = make_service(tmp_path, planned)
    request = BrainTurn("adv", "Review the saved record.", "tamper")
    first = brain.run(request).as_dict()
    damaged = deepcopy(store.load(chat_matter_id("adv", "tamper")))
    response = damaged.brain_chat[0]["response"]
    receipt = response["material_coverage"]["execution"]
    if damage == "effect":
        receipt["effects"]["details"]["after_record_ids"] = ["invented-record"]
    elif damage == "display":
        receipt["display"]["element"]["text"] = "An unsupported successful edit."
    elif damage == "changes":
        receipt["record_changes"] = [{"effect_id": "invented-effect", "kind": "details",
                                      "relation": "new", "before_records": [],
                                      "after_record": {
                                          "statement": "The wrong date is now right."}}]
    elif damage == "snapshot":
        response["continuation"]["record_snapshot"]["record_catalogue"] = {
            "invented-record": {"id": "invented-record", "type": "material",
                                "record": {"id": "invented-record"}}}
    else:
        receipt["requests"][0]["fulfillment"] = "fulfilled"
    calls = len(model.seen)
    monkeypatch.setattr(store, "load", lambda _: damaged)
    with pytest.raises(BrainRefused) as refused:
        brain.run(request)
    assert refused.value.status == 409
    assert len(model.seen) == calls
    assert first["committed"] == "committed"


def test_unreleased_unit_has_fixed_truthful_status_without_interpreter_prose():
    item = WorkItem("Perform the work", "new", "none", "ordinary", "answer",
                    reply="UNREVIEWED FALSE COMPLETION")
    scoped = type("Plan", (), {"items": (item,)})()
    elements = boundary._continuation_elements(scoped, {"units": []})
    assert elements[0]["kind"] == "status"
    assert "unfinished" in elements[0]["text"]
    assert "UNREVIEWED" not in elements[0]["text"]
    assert "ask me to continue" not in elements[0]["text"]


@pytest.mark.parametrize("same_goal", [False, True])
def test_inherited_scope_alias_copies_only_an_explicit_continuation_of_the_exact_goal(same_goal):
    earlier = deepcopy(REVIEW)
    if not same_goal:
        earlier["success_condition"] = "Review a broader and distinct account."
    progress = {"rows": [{"id": "prior-task", "kind": "task", "text": "Original full goal",
                           "matter_scope": "current", "record_requirement": earlier}]}
    receipt = {"owner": {"turn_id": "now"}, "requests": [{
        "request_index": 0, "relation": "continues", "intent": "request",
        "matter_scope": "current", "record_requirement": deepcopy(REVIEW)}]}
    original = deepcopy(progress)
    scope = boundary._execution_review_scope(receipt, progress)
    aliases = [row for row in scope["requests"] if "task_id" in row]
    assert len(aliases) == int(same_goal)
    if aliases:
        assert aliases[0]["request"] == "Original full goal"
        assert aliases[0]["record_requirement"] == earlier
    assert progress == original


def test_original_result_replays_after_later_source_bound_supersession(tmp_path):
    original = "The records arrived on Tuesday."
    corrected = "Correction: the records arrived on Wednesday."
    first = material("event", original, original, placement="matter")
    revision = material(
        "event", "The records arrived on Wednesday.", corrected,
        relation="corrects", scope="current", placement="matter",
        references=[{"turn_id": "first", "role": "advocate", "quoted": original}],
        related_material_ids=["first:material:1"])
    store = FileMatterStore(tmp_path, key="consumer-fixture-sealing-key")
    model = ConsumerModel([
        plan(original, candidates=[first], opening=True,
             material_purposes=("account_contribution",)),
        plan(corrected, candidates=[revision], material_purposes=("account_contribution",),
             mutation_scopes=[mutation_scope("first:material:1")],
             record_disposition="performed")])
    brain = BrainService(store, model)
    initial_request = BrainTurn("adv", original, "first")
    initial = brain.run(initial_request).as_dict()
    brain.run(BrainTurn("adv", corrected, "second", matter_id=initial["matter_id"],
                        chat_id=initial["chat_id"]))
    saved = store.load(initial["matter_id"])
    current, _, _ = boundary._current_records(store, saved)
    assert [(row["id"], row["statement"]) for row in current.open_material] == [
        ("second:material:1", "The records arrived on Wednesday.")]
    assert [row["message"] for row in saved.brain_chat] == [original, corrected]
    calls = len(model.seen)
    replay = brain.run(initial_request).as_dict()
    assert replay["replayed"] is True and len(model.seen) == calls
    assert replay["material_coverage"]["execution"] == initial["material_coverage"]["execution"]
    assert replay["continuation"]["record_snapshot"] == initial["continuation"]["record_snapshot"]


def test_greeting_omits_irrelevant_record_status_and_keeps_prepared_writer_context(tmp_path):
    brain, _, model = make_service(tmp_path, plain_plan())
    result = brain.run(BrainTurn("adv", "Say hello.", "greeting")).as_dict()
    receipt = result["material_coverage"]["execution"]
    display = receipt["display"]
    assert receipt["material_selected"] is False and receipt["record_changes"] == []
    assert display is None and receipt["gate_diagnostics"] == []
    assert all("saved record" not in element["text"] for element in result["elements"])
    writer = next(payload for operation, payload in model.seen
                  if operation == "continue_conversation")
    assert writer["material_coverage"]["execution"]["display"] is None
    reviewer = next(payload for operation, payload in model.seen
                    if operation == "verify_continuation")
    assert reviewer["input"]["material_coverage"]["execution"]["display"] is None


@pytest.mark.parametrize("requested_change_performed", [False, True])
def test_footer_displays_exact_actual_date_change_without_confusing_an_unrelated_change(
    tmp_path, requested_change_performed,
):
    original = "The records arrived on Tuesday. The equipment arrived on Thursday."
    old_record = "The records arrived on Tuesday."
    old_equipment = "The equipment arrived on Thursday."
    latest = ("Correction: the records arrived on Wednesday." if requested_change_performed
              else "Correct the records date to Wednesday. The equipment arrived on Friday.")
    old = old_record if requested_change_performed else old_equipment
    new = ("The records arrived on Wednesday." if requested_change_performed
           else "The equipment arrived on Friday.")
    quotation = latest if requested_change_performed else "The equipment arrived on Friday."
    target = "first:material:1" if requested_change_performed else "first:material:2"
    revision = material(
        "event", new, quotation, relation="corrects", scope="current", placement="matter",
        references=[{"turn_id": "first", "role": "advocate", "quoted": old}],
        related_material_ids=[target])
    requirement = {"kind": "change", "target_ids": ["first:material:1"],
                   "operation": "corrects",
                   "success_condition": "The saved records-delivery entry states Wednesday."}
    second = plan(latest, candidates=[revision], material_purposes=("account_contribution",),
                  record_requirement=requirement)
    second["items"][0].update(
        next_step="answer" if requested_change_performed else "legal_work",
        reply="The requested entry is revised." if requested_change_performed
        else "The requested records date remains unresolved.")
    # Author both permissions from the original input before extraction. A
    # requested records-date edit and an independently supplied equipment date
    # are distinct contributions; permission for one cannot authorize the other.
    second["items"][0]["mutation_scopes"] = [{
        "authority_kind": "account_contribution",
        "authority_source_ids": ["L1"],
        "target_scope": "exact",
        "target_ids": ["first:material:1"],
        "permitted_relations": ["corrects"],
    }]
    if not requested_change_performed:
        second["items"][0]["mutation_scopes"].append({
            "authority_kind": "account_contribution",
            "authority_source_ids": ["L2"],
            "target_scope": "exact",
            "target_ids": ["first:material:2"],
            "permitted_relations": ["corrects"],
        })
    store = FileMatterStore(tmp_path, key="consumer-fixture-sealing-key")
    model = ConsumerModel([
        plan(original, opening=True, material_purposes=("account_contribution",), candidates=[
            material("event", old_record, old_record, placement="matter"),
            material("event", old_equipment, old_equipment, placement="matter")]), second],
        record_goal_fulfilled=requested_change_performed)
    brain = BrainService(store, model)
    initial = brain.run(BrainTurn("adv", original, "first")).as_dict()
    result = brain.run(BrainTurn("adv", latest, "second", matter_id=initial["matter_id"],
                                chat_id=initial["chat_id"])).as_dict()
    receipt = result["material_coverage"]["execution"]
    assert len(receipt["record_changes"]) == 1
    change = receipt["record_changes"][0]
    assert [row["statement"] for row in change["before_records"]] == [old]
    assert change["after_record"]["statement"] == new
    footer = receipt["display"]["element"]
    assert footer in result["elements"]
    assert footer["text"] == "Revised entry: " + old + " → " + new
    request = receipt["requests"][0]
    assert request["fulfillment"] == ("fulfilled" if requested_change_performed else "unfinished")
    if not requested_change_performed:
        catalogue = result["continuation"]["record_snapshot"]["record_catalogue"]
        assert catalogue["first:material:1"]["record"]["statement"] == old_record
        assert "The records arrived on Wednesday." not in footer["text"]
        assert any(row["gate"] == "G-EFFECT" for row in receipt["gate_diagnostics"])


def test_programming_failure_is_observed_as_failure_without_invented_usage():
    class Broken:
        def structured(self, *args, **kwargs):
            raise ValueError("Synthetic programming failure")

    counted = _CountedModel(Broken())
    with pytest.raises(ValueError):
        counted.structured(Prompt(system="Test", user="{}", operation="synthetic"),
                           {}, Tier.ROUTINE)
    receipt = counted.metrics()["model_calls"][0]
    assert receipt["state"] == "ValueError"
    assert receipt["usage_recorded"] is False and receipt["cost_usd"] is None


@pytest.mark.parametrize("error", [ContextOverflow("Synthetic capacity limit"),
                                   ProviderUnavailable("Synthetic unavailable local analysis")])
def test_service_limits_do_not_invent_network_failure_or_ask_to_restart_history(
    tmp_path, monkeypatch, error,
):
    brain, _, _ = make_service(tmp_path, plain_plan())

    def unavailable(*args, **kwargs):
        raise error

    monkeypatch.setattr(boundary, "interpret", unavailable)
    with pytest.raises(BrainRefused) as refused:
        brain.run(BrainTurn("adv", "Say hello.", "service-limit"))
    assert "start a new chat" not in refused.value.why.lower()
    assert "could not be reached" not in refused.value.why.lower()


@pytest.mark.parametrize("assessment,review_state", [(None, "partial"), ("unassessed", "checked")])
def test_empty_unconfirmed_review_differs_from_valid_unassessed_judgment(
        tmp_path, assessment, review_state):
    message = "Check the empty saved record. State any unresolved scope."
    planned = plan(message, material_purposes=("interpretation_review",),
                   record_requirement=deepcopy(REVIEW))
    planned["items"][0]["matter_scope"] = "none"
    brain, store, _ = make_service(tmp_path, planned, coverage_state=assessment)
    result = brain.run(BrainTurn("adv", message, "unconfirmed-empty-review")).as_dict()
    receipt = result["material_coverage"]["execution"]
    detail_review = receipt["stages"]["detail_review"]
    assert detail_review["state"] == review_state
    assert detail_review["account_coverage"]["state"] == "unassessed"
    assert ("validation_issue" in detail_review["account_coverage"]) == (assessment is None)
    assert receipt["requests"][0]["fulfillment"] == "unfinished"
    assert "remains unfinished" in receipt["display"]["element"]["text"]
    assert store.load(chat_matter_id("adv", "unconfirmed-empty-review")).brain_chat



def test_review_guard_refuses_owned_dispute_when_verifier_returns_without_its_status_sink(
    tmp_path, monkeypatch,
):
    message = "The contractor stopped work and disputes the amount payable."
    candidate = material("dispute", "Whether payment is due after work stopped.", message)
    planned = plan(message, candidates=[candidate], opening=True,
                   material_purposes=("account_contribution",), dispute_scope={message: "account"})
    brain, store, model = make_service(tmp_path, planned)

    def unchecked_return(model, *, candidates, **kwargs):
        # Inject a future integration regression: extraction returned, but no
        # independent admission/status/coverage was obtained for these rows.
        return tuple(candidates)

    monkeypatch.setattr(boundary, "verify_disputes", unchecked_return)
    with pytest.raises(BrainRefused) as refused:
        brain.run(BrainTurn("adv", message, "missing-review-sink"))
    assert refused.value.code == "material_execution_unconfirmed"
    assert refused.value.gate_diagnostic["gate"] == "G-CORE"
    assert refused.value.gate_diagnostic["state"] == "unconfirmed"
    assert store.load(chat_matter_id("adv", "missing-review-sink")) is None
    assert "verify_disputes" not in [operation for operation, _ in model.seen]
    assert "continue_conversation" not in [operation for operation, _ in model.seen]


def test_review_guard_keeps_real_checked_peer_and_footer_when_another_detail_is_unread(tmp_path):
    first = "The documents arrived on Tuesday."
    second = "The equipment arrived on Thursday."
    message = first + " " + second
    planned = plan(message, opening=True, material_purposes=("account_contribution",), candidates=[
        material("event", first, first, placement="matter"),
        material("event", second, second, placement="matter")])
    brain, store, _ = make_service(tmp_path, planned, unread_detail=True)
    result = brain.run(BrainTurn("adv", message, "checked-peer-unread-neighbour")).as_dict()
    receipt = result["material_coverage"]["execution"]
    stage = receipt["stages"]["detail_review"]
    assert stage["state"] == "checked"
    assert stage["review_status"]["checked_items"] >= 1
    assert stage["review_status"]["unread_items"] == 1
    assert stage["account_coverage"]["state"] == "unassessed"
    performed = [row for row in effect_catalogue(receipt).values() if row["performed"]]
    assert len(performed) == 1 and performed[0]["review_checked"] is True
    assert len(receipt["record_changes"]) == 1
    assert receipt["record_changes"][0]["after_record"]["statement"] == first
    footer = receipt["display"]["element"]
    assert footer in result["elements"] and "New entry: " + first in footer["text"]
    assert "No changes were made" not in footer["text"] and second not in footer["text"]
    assert "remains unfinished" in footer["text"]
    assert receipt["requests"][0]["fulfillment"] != "fulfilled"
    saved = store.load(result["matter_id"]).brain_chat[0]["response"]
    assert saved["elements"] == result["elements"]
    assert saved["material_coverage"]["execution"] == receipt
