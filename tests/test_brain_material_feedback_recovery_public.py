"""Typed failed material reviews recover through the shipped save/replay route.

Every source reading and outcome is independently scripted. Reviewer replies use
the exact native wire with no semantic transport repair; this proves recovery,
owned proof and persistence, not model accuracy or requested completion quality.
"""

import json
from copy import deepcopy

import pytest

from nm.brain import turn as owner
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, Usage, require_schema
from tests.test_brain_evidence_rendering_public import raw_unit
from tests.test_brain_material import material, send
from tests.test_brain_material_coverage_groups import (
    account_group,
    portion,
    scripted_public_review,
)
from tests.test_brain_material_purpose import (
    PurposeModel,
    item,
    open_account,
    public_record,
    routed,
)
from tests.test_brain_source_support_verifiers import verdict

FIRST = "The east parcel was delivered,"
SECOND = " and the west parcel remains uncollected."
ACCOUNT = FIRST + SECOND
REQUEST = "Review this account from its original wording."
MIXED = "The custodian is unidentified, and I ask you to review this account."
PRESERVE = "Keep the stated uncertainty unchanged."
MIXED_END = len("The custodian is unidentified,")


class PublicFeedbackModel(PurposeModel):
    """Declare each normal, failed and replacement judgment in raw native form."""

    def __init__(self, mode="reaffirmed", *, independent_failure=False):
        request = MIXED if mode == "changed" else REQUEST
        self.message = ACCOUNT + " " + request + " " + PRESERVE
        second = (SECOND.strip() + " Its custodian is unidentified."
                  if mode == "changed" else SECOND.strip())
        if mode == "negative":
            second = "The recipient signed a receipt."
        statements = [ACCOUNT if mode == "negative" else FIRST.rstrip(","), second,
                      "The guard signed a receipt."]
        if independent_failure:
            statements.append("Collection of the west parcel remains pending.")
        planned = routed(self.message, opening=True, source_purposes={
            request: "non_account", PRESERVE: "non_account"}, candidates=[
                material("event", statement, ACCOUNT, placement="matter")
                for statement in statements], items=[item(
                    self.message, "", intent="contribution", opening=True,
                    purposes=("account_contribution",))])
        planned["opening"]["summary"] = ACCOUNT
        super().__init__([planned])
        self.mode = mode
        self.independent_failure = independent_failure
        self.independent_repaired = False
        self.reconsidered = False
        self.feedback_calls = []
        self.owner_calls = []

    def context_budget(self, tier):
        return 100_000

    def _groups(self, payload, *, material_reader, repaired):
        selected = {"L1": account_group(portion(status="outside_scope"))}
        if material_reader:
            if self.mode == "negative":
                selected["L1"] = account_group(portion(status="represented", candidates=("D1",)))
            else:
                selected["L1"] = account_group(
                    portion(status="represented", candidates=("D1",), bounds=(0, len(FIRST))),
                    portion(status="represented", candidates=(
                        "D4" if self.independent_repaired else "D2",),
                            bounds=(len(FIRST), len(ACCOUNT))))
        for identity in ("L2", "L3"):
            selected[identity] = {"content_purpose": "non_account",
                                  "reason": "The source supplies work authority or preservation."}
        if self.mode == "changed" and self.reconsidered:
            selected["L2"] = account_group(portion(
                status="represented" if material_reader and repaired else "outside_scope",
                candidates=("D2",) if material_reader and repaired else (), bounds=(0, MIXED_END)),
                context=[{"extent": "exact_subrange", "start": MIXED_END,
                          "end": len(payload["source_treatments"]["L2"]["quoted"]),
                          "reason": "The remaining original words direct review."}])
        return {"state": "complete", "reason": "The authored scoped source judgment is complete.",
                "source_groups": selected}

    def _material(self, payload):
        references = payload["source_treatments"]
        self.feedback_calls.append(deepcopy(payload))
        feedback = payload.get("rejected_review_context", {}).get("unread_proposals")
        repaired = bool(feedback) or self.mode == "normal" or self.mode == "negative" or (
            self.mode == "resolved" and len(self.feedback_calls) > 1)
        if self.independent_failure and feedback:
            self.independent_repaired = any(row["candidate_id"] == "D4" for row in feedback)
        readings = {identity: {"content_role": "reported_matter_account" if identity == "L1"
                              else "work_instruction",
                              "reason": "Read original framing independently of proposed work."}
                    for identity in references}
        if self.mode == "changed":
            readings["L2"]["content_role"] = "mixed"
        elif self.independent_failure or not repaired and self.mode != "internal":
            readings["L2"]["content_role"] = "reported_party_position"
        rows = []
        for candidate in payload["candidates"]:
            identity = candidate["candidate_id"]
            negative = identity == "D3" or identity == "D2" and self.mode == "negative"
            row = verdict("material", references["L1"], accept=not negative,
                          supports=not negative)
            row["candidate_id"] = identity
            if negative:
                row["account_check"]["supported"] = False
            del row["account_check"]["source_ids"], row["account_check"]["source_checks"]
            selected = dict.fromkeys(candidate["allowed_account_source_ids"])
            bounds = (0, len(ACCOUNT)) if identity == "O1" or self.mode == "negative" else (
                (0, len(FIRST)) if identity == "D1" else (len(FIRST), len(ACCOUNT)))
            selected["L1"] = {"supports_statement": not negative,
                              "reason": "The original account supplies the selected proposition.",
                              "support_spans": [{"extent": "exact_subrange",
                                                 "start": bounds[0], "end": bounds[1]}]}
            if identity == "D2" and not negative:
                if (self.independent_failure or self.mode == "changed"
                        or not repaired and self.mode != "internal"):
                    selected["L2"] = {
                        "supports_statement": True,
                        "reason": "The authored independent reading supplies account content.",
                        "support_spans": [{"extent": "exact_subrange", "start": 0,
                                           "end": MIXED_END}] if self.mode == "changed" else [
                                               {"extent": "whole_source"}]}
                if self.independent_failure or not repaired:
                    selected["L3"] = {"supports_statement": True,
                                      "reason": "Deliberate authority-as-fact contradiction.",
                                      "support_spans": [{"extent": "whole_source"}]}
            if identity == "D4" and not self.independent_repaired:
                selected["L3"] = {"supports_statement": True,
                                  "reason": "Independent authority-as-fact contradiction.",
                                  "support_spans": [{"extent": "whole_source"}]}
            row["account_check"]["source_selections"] = selected
            rows.append(row)
        return {"source_readings": readings, "verdicts": rows,
                "coverage": self._groups(payload, material_reader=True, repaired=repaired)}

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        if prompt.operation == "verify_material_grounding":
            data = self._material(payload)
        elif prompt.operation == "verify_disputes":
            data = {"verdicts": [], "coverage": self._groups(
                payload, material_reader=False, repaired=False)}
        elif prompt.operation == "reconsider_account_sources":
            self.owner_calls.append(deepcopy(payload))
            if self.independent_failure:
                self.seen.append((prompt.operation, deepcopy(payload)))
                raise ProviderUnavailable(
                    "The independently scoped source-owner call is unavailable.")
            self.reconsidered = True
            reference = payload["original_source_catalogue"]["L2"]
            data = {"source_treatments": {"L2": {
                "content_role": "mixed" if self.mode == "changed" else "work_instruction",
                "reason": "An independent original-source decision is explicitly authored.",
                "substantive_spans": [{"start": 0, "end": MIXED_END}]
                if self.mode == "changed" else []}}}
            assert reference["quoted"] == (MIXED if self.mode == "changed" else REQUEST)
        elif prompt.operation == "continue_conversation":
            data = {"units": [raw_unit(payload)]}
        elif prompt.operation == "verify_continuation":
            data = scripted_public_review(payload, outcome="not_requested")
        else:
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        require_schema(data, schema)
        self.seen.append((prompt.operation, deepcopy(payload)))
        return ModelResult(text=None, data=data, tier=tier, provider="offline-raw",
                           model="scripted-material-feedback", usage=Usage(0, 0, 0), latency_ms=0,
                           completion=Completion.COMPLETE)


def released(client, wired, monkeypatch, model, *, limit=8):
    if limit != 8:
        from nm.app import api

        class LimitedService(owner.BrainService):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, recovery_limit=limit)

        monkeypatch.setattr(api, "BrainService", LimitedService)
    result = open_account(client, wired, monkeypatch, model, model.message,
                          turn_id="typed-failed-review")
    saved = wired.store.load(result["matter_id"])
    original = deepcopy(saved)
    record = public_record(client, result["matter_id"])
    before = len(model.seen)
    replay = send(client, model.message, "typed-failed-review")
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] and replay.json()["metrics"]["llm_calls"] == 0
    assert len(model.seen) == before and wired.store.load(saved.id) == original
    assert public_record(client, saved.id) == record
    assert saved.brain_chat[-1]["response"]["elements"] == result["elements"]
    assert saved.brain_chat[-1]["message"] == model.message
    return result, saved, record


@pytest.mark.parametrize("mode,calls", [
    ("reaffirmed", 11), ("changed", 12), ("internal", 10),
])
def test_public_typed_failure_recovers_only_unread_material_and_saves_original_support(
        client, wired, monkeypatch, mode, calls):
    model = PublicFeedbackModel(mode)
    result, saved, record = released(client, wired, monkeypatch, model)
    execution = result["material_coverage"]["execution"]
    event = execution["semantic_recovery"]["failed_review_recovery"]
    assert event["state"] == "reviewed" and event["candidate_ids"] == ["D2"]
    assert event["source_owner_ids"] == ([] if mode == "internal" else ["L2"])
    assert event["unread_candidate_ids"] == []
    assert execution["stages"]["detail_review"]["unread"] == 0
    assert execution["stages"]["detail_review"]["rejected"] == 1
    assert result["metrics"]["llm_calls"] == calls
    assert len(model.owner_calls) == (0 if mode == "internal" else 1)
    if model.owner_calls:
        assert model.owner_calls[0]["source_ids"] == ["L2"]
        assert "candidates" not in model.owner_calls[0]
    repaired = [payload for payload in model.feedback_calls if payload.get(
        "rejected_review_context", {}).get("unread_proposals")]
    assert len(repaired) == 1
    assert [row["candidate_id"] for row in repaired[0]["candidates"]] == ["D2"]
    assert {row["candidate_id"] for row in repaired[0]["retained_candidate_context"]} == {
        "D1", "D3", "O1"}
    assert sum(any(row["candidate_id"] == "D1" for row in payload["candidates"])
               for payload in model.feedback_calls) == 1
    assert sum(any(row["candidate_id"] == "D3" for row in payload["candidates"])
               for payload in model.feedback_calls) == 1
    bindings = execution["coverage_application"]["bindings"]
    assert {row["candidate_id"] for row in bindings} == {"D1", "D2"}
    assert all(row["review"]["verdict"] == "accept" for row in bindings)
    assert len(saved.brain_chat[-1]["response"]["material"]) == 2
    assert len(record["rows"]) == 2
    assert execution["effects"] and result["committed"] == "committed"
    assert result["metrics"]["recovery"]["dispatched_calls"] == calls - 8
    assert result["metrics"]["recovery"]["reply_reserve"] == 2


@pytest.mark.parametrize("mode,calls", [("normal", 8), ("resolved", 9), ("negative", 8)])
def test_checked_or_resolved_material_does_not_trigger_an_extra_recovery_stage(
        client, wired, monkeypatch, mode, calls):
    model = PublicFeedbackModel(mode)
    result, _, _ = released(client, wired, monkeypatch, model)
    execution = result["material_coverage"]["execution"]
    assert "failed_review_recovery" not in execution["semantic_recovery"]
    assert model.owner_calls == []
    assert result["metrics"]["llm_calls"] == calls
    assert execution["stages"]["detail_review"]["unread"] == 0
    assert execution["stages"]["detail_review"]["rejected"] == (2 if mode == "negative" else 1)


def test_exhausted_shared_ledger_retains_checked_peers_and_truthful_unread_saved_state(
        client, wired, monkeypatch):
    observations = []
    original = owner._recover_material

    def observe(*args, **kwargs):
        cache = kwargs["detail_review_state"]["cache"]
        result = original(*args, **kwargs)
        observations.append((cache, kwargs["detail_review_state"]["cache"]))
        return result

    monkeypatch.setattr(owner, "_recover_material", observe)
    model = PublicFeedbackModel()
    result, saved, record = released(client, wired, monkeypatch, model, limit=3)
    execution = result["material_coverage"]["execution"]
    event = execution["semantic_recovery"]["failed_review_recovery"]
    assert event["state"] == "budget_exhausted" and event["candidate_ids"] == ["D2"]
    before, after = observations[0]
    assert after is before and set(after.decisions) == {"D1", "D3", "O1"}
    assert model.owner_calls == [] and len(model.feedback_calls) == 2
    assert execution["stages"]["detail_review"]["unread"] == 1
    assert [row["candidate_id"] for row in execution["coverage_application"]["bindings"]] == ["D1"]
    assert len(saved.brain_chat[-1]["response"]["material"]) == len(record["rows"]) == 1
    assert result["metrics"]["llm_calls"] == 9
    assert result["metrics"]["recovery"]["dispatched_calls"] == 1
    assert result["metrics"]["recovery"]["reply_reserve"] == 2


@pytest.mark.parametrize("limit,calls", [(8, 12), (4, 10)])
def test_source_owner_failure_preserves_independent_material_recovery_and_terminal_gap(
        client, wired, monkeypatch, limit, calls):
    model = PublicFeedbackModel(independent_failure=True)
    result, saved, record = released(client, wired, monkeypatch, model, limit=limit)
    execution = result["material_coverage"]["execution"]
    recovery = execution["semantic_recovery"]
    source_owner = recovery["source_reconsideration"]
    assert source_owner["state"] == "partial"
    assert source_owner["failure"] == "ProviderUnavailable"
    assert source_owner["source_ids"] == ["L2"] and len(model.owner_calls) == 1
    event = recovery["failed_review_recovery"]
    assert event["candidate_ids"] == ["D2", "D4"] and event["source_owner_ids"] == ["L2"]
    repaired = [payload for payload in model.feedback_calls if payload.get(
        "rejected_review_context", {}).get("unread_proposals")]
    expected_ids = {"D1"}
    if limit == 8:
        assert event["state"] == "partial" and event["unread_candidate_ids"] == ["D2"]
        assert len(repaired) == 1
        assert [row["candidate_id"] for row in repaired[0]["candidates"]] == ["D2", "D4"]
        failures = repaired[0]["rejected_review_context"]["unread_proposals"]
        assert [row["candidate_id"] for row in failures] == ["D4"]
        assert failures[0]["sources"]["L3"]["reading"]["content_role"] == "work_instruction"
        assert failures[0]["sources"]["L3"]["selection"]["supports_statement"] is True
        assert set(failures[0]["sources"]) == {"L1", "L3"}
        assert {row["candidate_id"] for row in repaired[0]["retained_candidate_context"]} == {
            "D1", "D3", "O1"}
        assert [row["candidate_id"] for row in model.feedback_calls[-1]["candidates"]] == ["D2"]
        assert execution["stages"]["detail_review"]["unread"] == 1
        expected_ids.add("D4")
    else:
        assert event["state"] == "budget_exhausted" and repaired == []
        assert len(model.feedback_calls) == 2
        assert execution["stages"]["detail_review"]["unread"] == 2
    assert execution["stages"]["detail_review"]["rejected"] == 1
    for identity in ("D1", "D3"):
        assert sum(any(row["candidate_id"] == identity for row in payload["candidates"])
                   for payload in model.feedback_calls) == 1
    bindings = execution["coverage_application"]["bindings"]
    assert {row["candidate_id"] for row in bindings} == expected_ids
    assert all(row["review"]["verdict"] == "accept" for row in bindings)
    assert len(saved.brain_chat[-1]["response"]["material"]) == len(record["rows"]) == (
        len(expected_ids))
    assert execution["semantic_coverage"] == ("partial" if limit == 8 else "unassessed")
    assert result["committed"] == "committed" and execution["effects"]
    assert result["metrics"]["llm_calls"] == calls
    assert result["metrics"]["recovery"]["dispatched_calls"] == calls - 8
    assert result["metrics"]["recovery"]["reply_reserve"] == 2
