"""Unchanged source ownership can recover final unread proposal checks.

All meanings and verdicts are explicitly scripted. These public tests qualify
conditional dispatch, checked-peer reuse, owned capture and atomic replay;
they do not establish model quality. The unread selector is conservative source
eligibility, not proof of the reason a proposed record remains unread.
"""

import json
from copy import deepcopy

import pytest

from nm.brain import turn as owner
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage, require_schema
from tests.brain_reader_fixture import fresh_review_reply, source_portion_reply
from tests.test_brain_evidence_rendering_public import raw_unit
from tests.test_brain_material import material, send
from tests.test_brain_material_purpose import PurposeModel, item, open_account, routed
from tests.test_brain_source_support_verifiers import coverage, disposition, verdict

FIRST = "The east parcel was delivered,"
SECOND = " and the west parcel remains uncollected."
ACCOUNT = FIRST + SECOND
INSTRUCTION = "Review the account without treating this instruction as a new event."
MESSAGE = ACCOUNT + " " + INSTRUCTION


class ReaffirmedModel(PurposeModel):
    """Author repaired, resolved and genuinely rejected outcomes independently."""

    def __init__(self, *, mode="unread", peer=True):
        statements = ([FIRST.rstrip(","), SECOND.strip()] if peer else [ACCOUNT])
        if mode == "reject":
            statements = [ACCOUNT, "The recipient signed a parcel receipt."]
        planned = routed(MESSAGE, opening=True,
                         source_purposes={INSTRUCTION: "non_account"},
                         candidates=[material("event", statement, ACCOUNT, placement="matter")
                                     for statement in statements], items=[item(
                             MESSAGE, "", intent="contribution", opening=True,
                             purposes=("account_contribution",))])
        planned["opening"]["summary"] = ACCOUNT
        super().__init__([planned])
        self.mode = mode
        self.peer = peer
        self.owner_reconsidered = False
        self.material_reads = []

    def context_budget(self, tier):
        return 100_000

    def _review(self, operation, payload):
        references = payload["source_treatments"]
        is_material = operation == "verify_material_grounding"
        if is_material:
            self.material_reads.append((self.owner_reconsidered, deepcopy(payload)))
        failing = (is_material and not self.owner_reconsidered and self.mode != "reject"
                   and (self.mode != "resolved" or len(self.material_reads) == 1))
        faulty_id = "D2" if self.peer else "D1"
        rows = []
        for candidate in payload["candidates"]:
            identity = candidate["candidate_id"]
            row = verdict("material", references["L1"], source_id="L1")
            row["candidate_id"] = identity
            if self.mode == "reject" and identity == "D2":
                row.update(verdict="reject", operation_supported=False,
                           reason="The original account does not report a signed receipt.")
                row["account_check"]["supported"] = False
                row["account_check"]["source_checks"][0]["supports_proposal"] = False
            rows.append(row)
        # Distinct dispute coverage deliberately supplies a wrong source-purpose
        # judgment. Its owned conflict reaches the candidate-free source owner.
        purposes = {"L1": "account", "L2": "non_account" if is_material else "account"}
        if not is_material:
            portions = [disposition(source, reference, status="outside_scope")
                        for source, reference in references.items()]
        elif self.mode == "reject" or not self.peer:
            portions = [disposition("L1", references["L1"], status="represented",
                                    candidate_ids=("D1",)),
                        disposition("L2", references["L2"], status="non_account")]
        else:
            portions = [disposition("L1", references["L1"], status="represented",
                                    candidate_ids=("D1",), bounds=(0, len(FIRST))),
                        disposition("L1", references["L1"], status="represented",
                                    candidate_ids=("D2",), bounds=(len(FIRST), len(ACCOUNT))),
                        disposition("L2", references["L2"], status="non_account")]
        data = fresh_review_reply(payload, {"verdicts": rows, "coverage": coverage(
            references, purposes=purposes, dispositions=portions)})
        if failing:
            faulty = next(row for row in data["verdicts"] if row["candidate_id"] == faulty_id)
            faulty["account_check"]["source_selections"]["L2"] = {
                "supports_statement": True,
                "reason": "Deliberately wrong authority-as-fact judgment.",
                "support_spans": [{"extent": "whole_source"}]}
        return data

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        if prompt.operation == "reconsider_account_sources":
            self.owner_reconsidered = True
            assert payload["source_ids"] == ["L2"]
            assert "candidates" not in payload and "source_treatments" not in payload
            data = source_portion_reply(payload, {"source_treatments": {"L2": {
                "content_role": "work_instruction",
                "reason": "The scripted original instruction purpose is reaffirmed."}}})
        elif prompt.operation in ("verify_material_grounding", "verify_disputes"):
            data = self._review(prompt.operation, payload)
        elif prompt.operation == "continue_conversation":
            data = {"units": [raw_unit(payload)]}
        elif prompt.operation == "verify_continuation":
            unit, = payload["units"]
            data = {"accepted_units": [{
                "request_index": 0, "block_checks": [{
                    "block_id": block["id"], "requires_legal_support": False,
                    "verdict": "accept",
                    "reason": "Scripted acceptance of original account and limits."}
                    for block in unit["blocks"]], "proposal_checks": [], "progress_checks": [],
                "question_resolutions": [], "work_check": {
                    "existing_id": unit["work"]["existing_id"], "scope_preserved": True,
                    "verdict": "accept", "reason": "This contribution creates no completed task."},
                "record_check": {"outcome": "not_requested",
                                 "reason": "The fixture authors no requested completion claim."},
                "reason": "Explicit semantic verdict for ownership and persistence testing.",
            }], "rejected_units": []}
        else:
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            require_schema(result.data, schema)
            return result
        require_schema(data, schema)
        self.seen.append((prompt.operation, deepcopy(payload)))
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="scripted-reaffirmation", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def released(client, wired, monkeypatch, model, *, recovery_limit=8):
    from nm.app import api

    if recovery_limit != 8:
        class LimitedService(owner.BrainService):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, recovery_limit=recovery_limit)
        monkeypatch.setattr(api, "BrainService", LimitedService)
    opened = open_account(client, wired, monkeypatch, model, MESSAGE, turn_id="reaffirmed-reading")
    saved = wired.store.load(opened["matter_id"])
    before = len(model.seen)
    response = send(client, MESSAGE, "reaffirmed-reading")
    assert response.status_code == 200, response.text
    replay = response.json()
    assert replay["replayed"] and replay["metrics"]["llm_calls"] == 0
    assert replay["elements"] == opened["elements"]
    assert len(model.seen) == before and wired.store.load(saved.id) == saved
    assert saved.brain_chat[-1]["response"]["elements"] == opened["elements"]
    recovery = opened["metrics"]["recovery"]
    assert recovery["reserved_calls"] <= recovery_limit
    assert recovery["reply_reserve"] == 2
    assert recovery["dispatched_calls"] <= recovery_limit - 2
    execution = opened["material_coverage"]["execution"]
    event = execution["semantic_recovery"]["source_reconsideration"]
    assert event["state"] == ("unchanged" if recovery_limit == 8 else "partial")
    assert event["changed_source_ids"] == []
    assert saved.brain_chat[-1]["response"]["material_coverage"][
        "source_treatments"]["L2"]["content_role"] == "work_instruction"
    return opened, saved, execution


@pytest.mark.parametrize("peer", [False, True])
def test_reaffirmed_work_instruction_recovers_final_unread_with_positive_proof(
        client, wired, monkeypatch, peer):
    model = ReaffirmedModel(peer=peer)
    answer, saved, execution = released(client, wired, monkeypatch, model)
    rereads = [payload for after_owner, payload in model.material_reads if after_owner]
    assert len(rereads) == 1
    assert [row["candidate_id"] for row in rereads[0]["candidates"]] == ["D2" if peer else "D1"]
    retained = {row["candidate_id"] for row in rereads[0]["retained_candidate_context"]}
    assert retained == ({"D1", "O1"} if peer else {"O1"})
    assert execution["stages"]["detail_review"]["unread"] == 0
    assert answer["metrics"]["llm_calls"] == 11
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 3
    receipt = execution["coverage_application"]
    assert {row["candidate_id"] for row in receipt["bindings"]} == (
        {"D1", "D2"} if peer else {"D1"})
    assert all(row["review"]["verdict"] == "accept" for row in receipt["bindings"])
    assert len(saved.brain_chat[-1]["response"]["material"]) == (2 if peer else 1)
    if peer:
        initial = model.material_reads[0][1]["candidates"][0]
        assert initial["candidate_id"] == "D1"
        assert sum(any(row["candidate_id"] == "D1" for row in payload["candidates"])
                   for _, payload in model.material_reads) == 1


def test_resolved_earlier_issue_does_not_recheck_already_accepted_peers(
        client, wired, monkeypatch):
    model = ReaffirmedModel(mode="resolved")
    answer, _, execution = released(client, wired, monkeypatch, model)
    assert not any(after_owner for after_owner, _ in model.material_reads)
    assert execution["stages"]["detail_review"]["accepted"] == 2
    assert answer["metrics"]["llm_calls"] == 10
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 2


def test_unchanged_checked_semantic_reject_is_retained_without_forced_reconsideration(
        client, wired, monkeypatch):
    model = ReaffirmedModel(mode="reject")
    answer, saved, execution = released(client, wired, monkeypatch, model)
    assert not any(after_owner for after_owner, _ in model.material_reads)
    assert execution["stages"]["detail_review"]["rejected"] == 1
    assert execution["stages"]["detail_review"]["unread"] == 0
    assert [row["statement"] for row in saved.brain_chat[-1]["response"]["material"]] == [ACCOUNT]
    assert answer["metrics"]["llm_calls"] == 9
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 1


def test_budget_denial_keeps_original_checked_cache_and_saved_positive_peer(
        client, wired, monkeypatch):
    observations = []
    original = owner._recover_material

    def observe(*args, **kwargs):
        state = kwargs["detail_review_state"]
        cache = state["cache"]
        result = original(*args, **kwargs)
        observations.append((cache, state["cache"]))
        return result

    monkeypatch.setattr(owner, "_recover_material", observe)
    model = ReaffirmedModel()
    answer, saved, execution = released(client, wired, monkeypatch, model, recovery_limit=4)
    before, after = observations[0]
    assert after is before and set(after.decisions) == {"D1", "O1"}
    assert not any(after_owner for after_owner, _ in model.material_reads)
    assert execution["stages"]["detail_review"]["unread"] == 1
    assert [row["statement"] for row in saved.brain_chat[-1]["response"]["material"]] == [
        FIRST.rstrip(",")]
    assert [row["candidate_id"] for row in execution["coverage_application"]["bindings"]] == ["D1"]
    events = answer["metrics"]["recovery"]["events"]
    assert any(row["phase"] == "source_reconsideration:detail_review"
               and row["state"] == "budget_exhausted" for row in events)
    assert answer["metrics"]["llm_calls"] == 10
    assert answer["metrics"]["recovery"]["dispatched_calls"] == 2
