"""Fabricated original passages through authenticated saved/released turns.

Independent semantic outcomes are deliberately owned by this scripted fixture;
these cases qualify routing, budget, attribution and save/release mechanics.
"""
import json
import os
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from nm.brain import turn as boundary
from nm.brain.execution_contracts import effect_catalogue
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, ProviderUnavailable, Tier, Usage
from tests.brain_pressure_support import record_case
from tests.brain_reader_fixture import reader_operations, reader_repairs
from tests.test_brain_material import _with_source_ids, material, send
from tests.test_brain_pressure_release import PassageModel, answer_plan

FIRST = "The cedar samples reached the west laboratory on 8 June."
SECOND = "The glass samples reached the east laboratory on 11 June."
MESSAGE = FIRST + " " + SECOND


class RecoveryModel(PassageModel):
    """The fixture supplies each semantic outcome explicitly, without live calls."""

    def __init__(self, *, candidates=(), additions=(), roles=None, reconsidered=None,
                 gap_state="complete", gap_ids=(), partial_reader=False,
                 judge_failure=False, reject_addition=False, extra_rows=(), gap_area="detail",
                 review_requested=False, review_outcome="unresolved", wrong_owner_tier=False,
                 opening=True):
        requirement = ({"kind": "review", "target_ids": [], "operation": "none",
                        "success_condition": "Check the entire supplied original account."}
                       if review_requested else None)
        proposed = answer_plan(
            MESSAGE, candidates=candidates, opening=opening,
            requirement=requirement,
            purposes=("interpretation_review",) if review_requested else (
                ("account_contribution",) if not opening else ()),
            reply="The supplied account distinguishes these contributions.")
        if opening:
            proposed["opening"].update(subject="Supplied sample account", summary=MESSAGE)
        super().__init__([proposed], [{"status": review_outcome}] if review_requested else [])
        self.additions = tuple(additions)
        self.roles = roles or {}
        self.reconsidered = reconsidered or {}
        self.gap_state = gap_state
        self.gap_area = gap_area
        self.gap_ids = list(gap_ids)
        self.partial_reader = partial_reader
        self.judge_failure = judge_failure
        self.reject_addition = reject_addition
        self.extra_rows = tuple(extra_rows)
        self.recovery_read = False
        self.owner_reconsidered = False
        self.wrong_owner_tier = wrong_owner_tier

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        original = payload.get("original_input", payload)
        operation = prompt.operation
        if operation == "reconsider_account_sources":
            self.owner_reconsidered = True
            data = {"source_treatments": {identity: {
                "content_role": self.reconsidered.get(identity, self.roles.get(
                    identity, "reported_matter_account")),
                "reason": "The independent fixture rereads the complete original framing.",
            } for identity in original["source_ids"]}}
            self.seen.append({"operation": operation, "tier": tier.value,
                              "input": deepcopy(payload)})
            self.outputs.append({"operation": operation, "output": deepcopy(data)})
            return ModelResult(text=None, data=data,
                               tier=Tier.ROUTINE if self.wrong_owner_tier else tier,
                               provider="offline",
                               model="scripted-independent-Judge", usage=Usage(0, 0, 0),
                               latency_ms=0, completion=Completion.COMPLETE)
        if (self.judge_failure and self.recovery_read
                and operation == "verify_material_grounding"):
            self.seen.append({"operation": operation, "tier": tier.value,
                              "input": deepcopy(payload)})
            self.outputs.append({"operation": operation, "failure": "ProviderUnavailable"})
            raise ProviderUnavailable("Fabricated conditional Judge unavailable")
        if operation in ("extract_disputes", "extract_legal_details"):
            targeted = "recovery_scope" in original
            if targeted:
                self.recovery_read = True
                previous = self.next_material
                self.next_material = list(self.additions)
                try:
                    result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
                finally:
                    self.next_material = previous
            else:
                result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            data = deepcopy(result.data)
            if operation == "extract_legal_details" and self.partial_reader and not targeted:
                if "repairs" in schema.get("properties", {}):
                    data = {"repairs": {identity: {"proposals": [{"foreign": "bad"}]}
                                         for identity in schema["properties"]["repairs"][
                                             "properties"]}}
                else:
                    data["new_items"].append({"foreign": "bad"})
            if targeted and self.extra_rows and operation == "extract_legal_details":
                rows = [_with_source_ids(row, original) for row in self.extra_rows]
                extra = reader_operations(rows, original, link_field="related_material_ids")
                data["new_items"].extend(extra["new_items"])
            if "repairs" not in data:
                data = reader_repairs(data, schema)
        else:
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            data = deepcopy(result.data)
        if operation == "classify_account_sources":
            for identity, role in self.roles.items():
                data["source_treatments"][identity]["content_role"] = role
        if (operation == {"detail": "verify_material_grounding",
                         "dispute": "verify_disputes"}[self.gap_area]
                and "coverage_source_ids" in original):
            remaining = not self.recovery_read and not self.owner_reconsidered
            data["coverage"] = {
                "state": self.gap_state if remaining else "complete",
                "missing_source_ids": self.gap_ids if remaining else [],
                "reason": "The independent fixture identifies this original contribution gap."
                if remaining and self.gap_state != "complete" else
                "The independent fixture confirms the full original account is represented.",
            }
            if self.reject_addition and self.recovery_read:
                for row in data["verdicts"]:
                    if row["candidate_id"] == "D2":
                        row.update(verdict="reject", operation_supported=False,
                                   reason="This added interpretation changes the reported meaning.")
                        row["account_check"].update(supported=False)
        # Preserve the actual post-fabrication object, replacing super's log entry.
        self.outputs[-1]["output"] = deepcopy(data)
        return replace(result, data=data)


def wire(wired, monkeypatch, model, *, recovery_limit=8):
    from nm.app import api

    monkeypatch.setattr(wired, "_model_for", lambda *args, **kwargs: model)
    monkeypatch.setattr(wired, "legal_search", None)
    if recovery_limit != 8:
        class LimitedService(boundary.BrainService):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, recovery_limit=recovery_limit)
        monkeypatch.setattr(api, "BrainService", LimitedService)
    else:
        monkeypatch.setattr(api, "BrainService", boundary.BrainService)


def release(client, wired, monkeypatch, model, identity, *, recovery_limit=8):
    wire(wired, monkeypatch, model, recovery_limit=recovery_limit)
    response = send(client, MESSAGE, identity)
    assert response.status_code == 200, response.text
    data = response.json()
    saved = wired.store.load(data["matter_id"])
    conversation, _, _ = boundary._current_records(wired.store, saved)
    return data, saved, conversation


def evidence(identity, model, data, saved, expected, observed, *, scenario="faulty"):
    report = record_case(
        identity, boundary="POST /api/turn -> checked recovery -> atomic save -> released reply",
        user_passage=MESSAGE, model_outputs=model.outputs, calls=model.seen,
        expected=expected, observed=observed, scenario=scenario,
        protection_status="passed", claim_scope="mechanical",
        notes=("All model outputs are fabricated and semantic outcomes explicitly scripted. "
               "The released response, reopened saved record and complete recovery budget "
               "are captured in the observations. Legal corpus calls are disabled."),
    )
    evidence_dir = os.environ.get("NM_PRESSURE_EVIDENCE_DIR")
    if evidence_dir:
        report["released_response"] = deepcopy(data)
        report["reopened_saved_matter"] = asdict(saved)
        target = Path(evidence_dir) / (identity + ".json")
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    return report


def detail(words):
    return material("event", words, words, placement="matter")


def test_correct_account_has_no_conditional_recovery(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST), detail(SECOND)])
    data, saved, conversation = release(client, wired, monkeypatch, model, "good-recovery")
    observed = {
        "saved": [row["statement"] for row in conversation.open_material],
        "conditional_calls": data["metrics"]["recovery"]["dispatched_calls"],
        "reserved": data["metrics"]["recovery"]["reserved_calls"],
    }
    evidence("SEM-GOOD-01", model, data, saved,
             {"saved": [FIRST, SECOND], "conditional_calls": 0, "reserved": 0}, observed,
             scenario="known_good")


def test_localized_missing_account_gets_one_reader_and_owned_judge(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[detail(SECOND)],
                          gap_state="partial", gap_ids=["L2"])
    data, saved, conversation = release(client, wired, monkeypatch, model, "missing-recovery")
    calls = data["metrics"]["recovery"]
    targeted = [row["input"] for row in model.seen
                if row["operation"] == "extract_legal_details"
                and "recovery_scope" in row["input"]]
    observed = {
        "saved": [row["statement"] for row in conversation.open_material],
        "ids": [row["id"] for row in conversation.open_material],
        "phases": [row["phase"] for row in calls["events"]],
        "targeted_read_count": len(targeted),
        "owned_missing_ids": targeted[0]["recovery_scope"]["missing_source_ids"],
        "retained_original": targeted[0]["recovery_scope"]["retained_proposals"][0]["quoted"],
    }
    evidence("SEM-OMISSION-01", model, data, saved, {
        "saved": [FIRST, SECOND],
        "ids": ["missing-recovery:material:1", "missing-recovery:material:2"],
        "phases": ["omission_recovery:detail_reader", "omission_recovery:detail_review"],
        "targeted_read_count": 1, "owned_missing_ids": ["L2"], "retained_original": FIRST,
    }, observed)


@pytest.mark.parametrize("state,ids", [("complete", []), ("partial", []),
                                        ("unassessed", ["L2"])])
def test_nonlocalized_or_unassessed_coverage_does_not_guess_recovery(
        client, wired, monkeypatch, state, ids):
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[detail(SECOND)],
                          gap_state=state, gap_ids=ids)
    data, saved, conversation = release(client, wired, monkeypatch, model,
                                        "no-target-" + state)
    observed = {"conditional_calls": data["metrics"]["recovery"]["dispatched_calls"],
                "saved": [row["statement"] for row in conversation.open_material]}
    evidence("SEM-NO-TARGET-" + state, model, data, saved,
             {"conditional_calls": 0, "saved": [FIRST]}, observed,
             scenario="known_good")


def test_omission_judge_budget_retains_checked_peer_and_lists_unread(
        client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[detail(SECOND)],
                          gap_state="partial", gap_ids=["L2"])
    data, saved, conversation = release(client, wired, monkeypatch, model,
                                        "limited-recovery", recovery_limit=1)
    turn = saved.brain_chat[-1]["response"]
    observed = {
        "saved": [row["statement"] for row in conversation.open_material],
        "reserved": data["metrics"]["recovery"]["reserved_calls"],
        "dispatched": data["metrics"]["recovery"]["dispatched_calls"],
        "unread": turn["material_coverage"]["execution"]["unread_proposals"]["details"],
    }
    evidence("SEM-BUDGET-01", model, data, saved,
             {"saved": [FIRST], "reserved": 1, "dispatched": 1, "unread": ["D2"]}, observed)


@pytest.mark.parametrize("changed", [False, True])
def test_source_owner_reconsideration_is_candidate_free_and_bounded(
        client, wired, monkeypatch, changed):
    model = RecoveryModel(candidates=[detail(FIRST), detail(SECOND)],
                          roles={"L2": "examination_material"},
                          reconsidered={"L2": "reported_matter_account"}
                          if changed else {})
    data, saved, conversation = release(client, wired, monkeypatch, model,
                                        "source-" + str(changed).lower())
    owner = [row for row in model.seen
             if row["operation"] == "reconsider_account_sources"]
    observed = {
        "saved": [row["statement"] for row in conversation.open_material],
        "owner_calls": len(owner), "owner_tier": owner[0]["tier"],
        "owner_keys": sorted(owner[0]["input"]),
        "selected": owner[0]["input"]["source_ids"],
        "new_roles": [row["content_role"] for row in saved.brain_chat[-1]["response"][
            "material_coverage"]["source_treatments"].values()],
        "rereviews": sum(row["phase"] == "source_reconsideration:detail_review"
                         and "call" in row for row in data["metrics"]["recovery"]["events"]),
    }
    # The fixture's initial role conflict takes its existing single correction;
    # role unchanged then spends only one source-owner call, with no retry loop.
    evidence("SEM-SOURCE-" + str(changed), model, data, saved, {
        "saved": [FIRST, SECOND] if changed else [FIRST], "owner_calls": 1,
        "owner_tier": "judge", "owner_keys": ["earlier_conversation", "latest_message_spans",
                                                 "source_ids"],
        "selected": ["L2"], "new_roles": ["reported_matter_account",
             "reported_matter_account" if changed else "examination_material"],
        "rereviews": 1 if changed else 0,
    }, observed)


def test_recovered_duplicate_does_not_duplicate_original_effect(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)],
                          additions=[detail(FIRST), detail(SECOND)],
                          extra_rows=[detail(SECOND)], gap_state="partial", gap_ids=["L2"])
    data, saved, conversation = release(client, wired, monkeypatch, model, "dedup-recovery")
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "effect_count": len(data["material_coverage"]["execution"]["record_changes"]),
                "reserved": data["metrics"]["recovery"]["reserved_calls"]}
    evidence("SEM-DEDUP-01", model, data, saved,
             {"saved": [FIRST, SECOND], "effect_count": 2, "reserved": 2}, observed)


def test_recovery_addition_still_requires_independent_admission(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[detail(SECOND)],
                          reject_addition=True, gap_state="partial", gap_ids=["L2"])
    data, saved, conversation = release(client, wired, monkeypatch, model, "reject-recovery")
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "rejected": [row["candidate_id"] for row in data["material_coverage"][
                    "rejected_proposals"]],
                "effect_count": len(data["material_coverage"]["execution"]["record_changes"])}
    evidence("SEM-REJECT-01", model, data, saved,
             {"saved": [FIRST], "rejected": ["D2"], "effect_count": 1}, observed)


def test_recovery_judge_unavailable_retains_saved_checked_peer(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[detail(SECOND)],
                          judge_failure=True, gap_state="partial", gap_ids=["L2"])
    data, saved, conversation = release(client, wired, monkeypatch, model, "offline-recovery")
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "unread": [row["candidate_id"] for row in data["material_coverage"][
                    "unread_proposals"]], "partial": data["material_coverage"]["state"],
                "reserved": data["metrics"]["recovery"]["reserved_calls"]}
    evidence("SEM-UNAVAILABLE-01", model, data, saved,
             {"saved": [FIRST], "unread": ["D2"], "partial": "partial", "reserved": 2},
             observed)


def test_partial_reader_retains_only_owned_checked_effects(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], partial_reader=True)
    data, saved, conversation = release(client, wired, monkeypatch, model, "partial-reader")
    receipt = data["material_coverage"]["execution"]
    reader = receipt["stages"]["detail_extraction"]
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "reader_state": reader["state"], "admitted": reader["admissible_proposals"],
                "count": reader["read_status"]["proposal_count"],
                "performed": [row["performed"] for row in effect_catalogue(receipt).values()],
                "reserved": data["metrics"]["recovery"]["reserved_calls"]}
    evidence("SEM-PARTIAL-READER-01", model, data, saved, {
        "saved": [FIRST], "reader_state": "partial", "admitted": 1, "count": 1,
        "performed": [True], "reserved": 1,
    }, observed)


def test_zero_recovery_budget_keeps_checked_peer_without_dispatch(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[detail(SECOND)],
                          gap_state="partial", gap_ids=["L2"])
    data, saved, conversation = release(client, wired, monkeypatch, model,
                                        "zero-recovery", recovery_limit=0)
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "reserved": data["metrics"]["recovery"]["reserved_calls"],
                "dispatched": data["metrics"]["recovery"]["dispatched_calls"],
                "stage": data["material_coverage"]["execution"]["semantic_recovery"][
                    "omission_recovery"]["state"]}
    evidence("SEM-ZERO-BUDGET-01", model, data, saved,
             {"saved": [FIRST], "reserved": 0, "dispatched": 0, "stage": "partial"}, observed)


def test_source_resolution_precedes_opening_repair(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST), detail(SECOND)],
                          roles={"L1": "examination_material"},
                          reconsidered={"L1": "reported_matter_account"})
    data, saved, conversation = release(client, wired, monkeypatch, model, "opening-source")
    operations = [row["operation"] for row in model.seen]
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "opening_fallback": data["material_coverage"]["opening_fallback"],
                "opening_repairs": sum(operation == "repair_opening" for operation in operations),
                "owner_calls": operations.count("reconsider_account_sources")}
    evidence("SEM-OPENING-SOURCE-01", model, data, saved,
             {"saved": [FIRST, SECOND], "opening_fallback": False,
             "opening_repairs": 0, "owner_calls": 1}, observed)


def test_source_owner_uncertainty_never_promotes_rejected_proposal(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST), detail(SECOND)],
                          roles={"L2": "examination_material"},
                          reconsidered={"L2": "uncertain"})
    data, saved, conversation = release(client, wired, monkeypatch, model, "uncertain-source")
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "final_role": data["material_coverage"]["source_treatments"]["L2"]["content_role"],
                "owner_calls": sum(row["operation"] == "reconsider_account_sources"
                                   for row in model.seen),
                "reader_calls": sum(row["operation"] == "extract_legal_details"
                                    for row in model.seen),
                "conditional_calls": data["metrics"]["recovery"]["dispatched_calls"]}
    evidence("SEM-UNCERTAIN-SOURCE-01", model, data, saved,
             {"saved": [FIRST], "final_role": "uncertain", "owner_calls": 1,
              "reader_calls": 1, "conditional_calls": 5}, observed)


def test_source_recheck_budget_never_reuses_old_negative_decision_as_approval(
        client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST), detail(SECOND)],
                          roles={"L2": "examination_material"},
                          reconsidered={"L2": "reported_matter_account"})
    data, saved, conversation = release(client, wired, monkeypatch, model,
                                        "source-budget", recovery_limit=3)
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "unread": [row["candidate_id"] for row in data["material_coverage"][
                    "unread_proposals"]], "reserved": data["metrics"]["recovery"]["reserved_calls"],
                "dispatched": data["metrics"]["recovery"]["dispatched_calls"]}
    # Opening reads all original account spans and is in the changed-source
    # dependency closure, so its previous decision also remains unassessed.
    evidence("SEM-SOURCE-BUDGET-01", model, data, saved,
             {"saved": [FIRST], "unread": ["D2", "O1"], "reserved": 3, "dispatched": 3},
             observed)


def test_dispute_omission_keeps_existing_material_id_and_rechecks_final_scope(
        client, wired, monkeypatch):
    addition = material("dispute", SECOND, SECOND)
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[addition],
                          gap_state="partial", gap_ids=["L2"], gap_area="dispute")
    data, saved, conversation = release(client, wired, monkeypatch, model, "dispute-omission")
    execution = data["material_coverage"]["execution"]
    observed = {"detail_ids": [row["id"] for row in conversation.open_material],
                "dispute_ids": [row["id"] for row in conversation.open_disputes],
                "phases": [row["phase"] for row in data["metrics"]["recovery"]["events"]],
                "complete": execution["semantic_coverage"]}
    evidence("SEM-DISPUTE-OMISSION-01", model, data, saved, {
        "detail_ids": ["dispute-omission:material:1"],
        "dispute_ids": ["dispute-omission:material:2"],
        "phases": ["omission_recovery:dispute_reader", "omission_recovery:dispute_review",
                   "omission_recovery:detail_review"], "complete": "complete",
    }, observed)


def test_partial_initial_reader_omission_aggregates_all_owned_effect_receipts(
        client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], additions=[detail(SECOND)],
                          partial_reader=True, gap_state="partial", gap_ids=["L2"])
    data, saved, conversation = release(client, wired, monkeypatch, model, "partial-aggregate")
    execution = data["material_coverage"]["execution"]
    stage = execution["stages"]["detail_extraction"]
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "state": stage["state"], "proposals": stage["proposals"],
                "admitted": stage["admissible_proposals"],
                "read_count": stage["read_status"]["proposal_count"],
                "performed": [row["performed"] for row in effect_catalogue(execution).values()],
                "initial_state": stage["initial_read_status"]["state"],
                "recovery_state": stage["recovery_read_status"]["state"]}
    evidence("SEM-PARTIAL-AGGREGATE-01", model, data, saved, {
        "saved": [FIRST, SECOND], "state": "partial", "proposals": 2,
        "admitted": 2, "read_count": 2, "performed": [True, True],
        "initial_state": "partial", "recovery_state": "returned",
    }, observed)


def test_requested_review_discloses_unread_reader_beside_independently_checked_effect(
        client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST)], partial_reader=True, review_requested=True)
    data, saved, conversation = release(client, wired, monkeypatch, model, "reader-review")
    execution = data["material_coverage"]["execution"]
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "material_state": data["material_coverage"]["state"],
                "semantic_coverage": execution["semantic_coverage"],
                "fulfillment": execution["requests"][0]["fulfillment"],
                "disclosed": "The record reading remains unfinished." in
                    execution["display"]["element"]["text"],
                "reader_gates": [(row["gate"], row.get("stage"))
                                 for row in execution["gate_diagnostics"]
                                 if row.get("stage")],
                "outcome": data["continuation"]["units"][0]["record_outcome"]["status"]}
    evidence("SEM-UNREAD-REVIEW-01", model, data, saved, {
        "saved": [FIRST], "material_state": "partial", "semantic_coverage": "complete",
        "fulfillment": "unfinished", "disclosed": True,
        "reader_gates": [("G-MODEL", "detail_extraction")], "outcome": "unresolved",
    }, observed)


def test_legitimate_no_change_review_needs_no_omission_retry(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[], review_requested=True, review_outcome="review_no_change")
    data, saved, conversation = release(client, wired, monkeypatch, model, "no-change-recovery")
    execution = data["material_coverage"]["execution"]
    observed = {"saved": [row["statement"] for row in conversation.open_material],
                "fulfillment": execution["requests"][0]["fulfillment"],
                "conditional": data["metrics"]["recovery"]["dispatched_calls"],
                "changes": execution["record_changes"]}
    evidence("SEM-NOCHANGE-01", model, data, saved,
             {"saved": [], "fulfillment": "no_change_justified", "conditional": 0,
              "changes": []}, observed, scenario="known_good")


def test_source_reconsideration_cannot_downgrade_independence(client, wired, monkeypatch):
    model = RecoveryModel(candidates=[detail(FIRST), detail(SECOND)],
                          roles={"L2": "examination_material"},
                          reconsidered={"L2": "reported_matter_account"}, wrong_owner_tier=True)
    wire(wired, monkeypatch, model)
    response = send(client, MESSAGE, "wrong-source-tier")
    observed = {"http": response.status_code,
                "saved": wired.store.load(boundary.chat_matter_id(
                    "adv_demo", "wrong-source-tier")) is not None}
    record_case("SEM-INDEPENDENCE-01", boundary="POST /api/turn -> source-owner independence",
                user_passage=MESSAGE, model_outputs=model.outputs, calls=model.seen,
                expected={"http": 503, "saved": False}, observed=observed,
                notes="A fabricated routine-tier source-owner response cannot pass as Judge.")


def test_source_rereview_replacement_holds_stale_assignment_and_keeps_checked_dispute(
        client, wired, monkeypatch):
    seed_plan = answer_plan(MESSAGE, candidates=[material("dispute", FIRST, FIRST)], opening=True)
    seed_plan["opening"].update(subject="Supplied sample dispute", summary=MESSAGE)
    seed_model = PassageModel([seed_plan])
    seed, _, _ = release(client, wired, monkeypatch, seed_model, "assignment-original")
    original_id = "assignment-original:material:1"
    replaced_dispute = material(
        "dispute", FIRST, FIRST, relation="corrects", scope="current", references=[{
            "turn_id": "assignment-original", "role": "advocate", "quoted": FIRST}])
    replaced_dispute["related_dispute_ids"] = [original_id]
    assigned_detail = material("event", SECOND, SECOND, scope="current",
                               placement="dispute", dispute_ids=[original_id])
    model = RecoveryModel(candidates=[replaced_dispute, assigned_detail], opening=False,
                          roles={"L1": "examination_material"},
                          reconsidered={"L1": "reported_matter_account"})
    wire(wired, monkeypatch, model)
    delivered = send(client, MESSAGE, "assignment-recovery", opened=seed)
    assert delivered.status_code == 200, delivered.text
    data = delivered.json()
    saved = wired.store.load(data["matter_id"])
    conversation, _, _ = boundary._current_records(wired.store, saved)
    observed = {"disputes": [row["id"] for row in conversation.open_disputes],
                "details": [row["id"] for row in conversation.open_material],
                "unread": [row["candidate_id"] for row in data["material_coverage"][
                    "unread_proposals"]],
                "state": data["material_coverage"]["execution"]["semantic_recovery"][
                    "source_reconsideration"]["state"]}
    model.seen = [*seed_model.seen, *model.seen]
    model.outputs = [*seed_model.outputs, *model.outputs]
    evidence("SEM-ASSIGNMENT-CLOSURE-01", model, data, saved, {
        "disputes": ["assignment-recovery:material:2"], "details": [],
        "unread": ["D1"], "state": "partial",
    }, observed)
