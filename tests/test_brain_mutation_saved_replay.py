"""Public replay regressions for durable mutation authority.

Fresh valid GS-15 corrections are saved before fault injection. The mutations
below alter only offline test storage. No live provider or legal corpus is used.
"""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import mutation_contracts
from nm.brain.conversation import IncompleteConversation
from nm.shared.model_port import SchemaViolation
from tests.brain_golden_pressure_fixture import GoldenModel, evidence, release
from tests.brain_pressure_support import record_case
from tests.test_brain_golden_boundaries import owned_outcome
from tests.test_brain_mutation_release_neighbors import correction_fixture

pytestmark = pytest.mark.class_a


def reseal(value):
    body = {key: val for key, val in value.items() if key != "seal"}
    value["seal"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode()
    ).hexdigest()


def saved_correction(client, wired, monkeypatch, identity):
    model, opened, previous, date_target, custody_target = correction_fixture(
        client, wired, monkeypatch, identity=identity, declared_requirement=True
    )
    reply, saved, conversation = release(
        client, wired, monkeypatch, model, identity, opened=opened
    )
    execution = reply["material_coverage"]["execution"]
    assert execution["mutation_authority_contract"] == mutation_contracts.AUTHORITY_CONTRACT
    proposal, = reply["material"]
    assert proposal["mutation_authority"]["contract"] == mutation_contracts.BINDING_CONTRACT
    assert proposal["related_material_ids"] == [date_target]
    assert custody_target in {row["id"] for row in conversation.open_material}
    return model, opened, reply, saved, previous, date_target, custody_target


@pytest.mark.parametrize("fault", [
    "missing_certificate",
    "resealed_certificate_target",
    "resealed_certificate_owner",
    "resealed_certificate_version",
    "certificate_seal",
    "removed_ledger",
    "rebuilt_permission_drift",
])
def test_saved_mutation_binding_tamper_refuses_public_replay_without_model_or_write(
    client, wired, monkeypatch, fault
):
    identity = "mutation-replay-" + fault
    model, opened, reply, saved, previous, date_target, custody_target = saved_correction(
        client, wired, monkeypatch, identity
    )
    changed = deepcopy(saved.brain_chat)
    row = changed[-1]
    execution = row["response"]["material_coverage"]["execution"]
    proposal, = row["response"]["material"]
    ledger = execution["mutation_authorities"]
    certificate = proposal["mutation_authority"]
    if fault == "missing_certificate":
        proposal.pop("mutation_authority")
    elif fault == "resealed_certificate_target":
        certificate["target_ids"] = [custody_target]
        reseal(certificate)
    elif fault == "resealed_certificate_owner":
        certificate["owner"]["advocate_id"] = "another-owned-test-advocate"
        reseal(certificate)
    elif fault == "resealed_certificate_version":
        certificate["expected_version"] += 1
        reseal(certificate)
    elif fault == "certificate_seal":
        certificate["seal"] = "0" * 64
    elif fault == "removed_ledger":
        execution.pop("mutation_authorities")
    elif fault == "rebuilt_permission_drift":
        decisions = []
        for grant in ledger["authorities"]:
            decision = {key: deepcopy(value) for key, value in grant.items() if key != "id"}
            decision["target_ids"] = [custody_target]
            decisions.append(decision)
        execution["mutation_authorities"] = mutation_contracts.build_mutation_authorities(
            owner=ledger["owner"], expected_version=ledger["expected_version"],
            target_catalogue=ledger["target_catalogue"],
            source_catalogue=ledger["source_catalogue"], proposals=decisions,
            request_indices=[0],
        )
    # Keep the top-level convenience copy consistent when it exists. This test
    # targets the authority binding, not a redundant response-copy mismatch.
    if "material" in row:
        row["material"] = deepcopy(row["response"]["material"])
    wired.store.commit(
        replace(saved, brain_chat=changed, version=saved.version + 1),
        expected_version=saved.version,
    )
    before = deepcopy(wired.store.load(opened["matter_id"]))
    calls_before = len(model.seen)
    binding_issues = []
    progress_issues = []
    validate = mutation_contracts.validate_record_mutation

    def traced(*args, **kwargs):
        try:
            return validate(*args, **kwargs)
        except SchemaViolation as exc:
            binding_issues.append(str(exc))
            raise

    monkeypatch.setattr(mutation_contracts, "validate_record_mutation", traced)
    # Projection modules may hold their imported boundary reference. Instrument
    # the same function there without changing what it decides.
    from nm.brain import dispute_state, material_state, turn, work_state

    for owner in (dispute_state, material_state, turn):
        if getattr(owner, "validate_record_mutation", None) is validate:
            monkeypatch.setattr(owner, "validate_record_mutation", traced)
    project = work_state.project_work

    def traced_progress(*args, **kwargs):
        try:
            return project(*args, **kwargs)
        except IncompleteConversation as exc:
            progress_issues.append(str(exc))
            raise

    monkeypatch.setattr(work_state, "project_work", traced_progress)
    if turn.project_work is project:
        monkeypatch.setattr(turn, "project_work", traced_progress)
    response = client.post("/api/turn", json={
        "message": model.dossier.message, "turn_id": identity,
        "matter_id": opened["matter_id"], "chat_id": opened["chat_id"],
    })
    result = response.json()
    earlier_ledger_fault = fault in ("removed_ledger", "rebuilt_permission_drift")
    expected_owner = (
        "nm.brain.work_state.project_work" if earlier_ledger_fault
        else "nm.brain.mutation_contracts.validate_record_mutation"
    )
    required_issue = (
        "saved record result seal disagrees with its original owned evidence"
        if earlier_ledger_fault else (
            "Versioned mutation requires its saved authority binding"
            if fault == "missing_certificate"
            else "Saved mutation differs from its source-linked authority binding"
        )
    )
    actual_owner = (
        "nm.brain.work_state.project_work" if progress_issues
        else "nm.brain.mutation_contracts.validate_record_mutation" if binding_issues
        else None
    )
    actual_issues = progress_issues if progress_issues else binding_issues
    expected = {
        "http": 409,
        "matter_reply_released": False,
        "additional_model_calls": 0,
        "no_storage_mutation": True,
        "rejecting_owner": expected_owner,
        "precise_mismatch": True,
        "later_binding_gate_rejected": not earlier_ledger_fault,
    }
    observed = {
        "http": response.status_code,
        "matter_reply_released": "elements" in result,
        "additional_model_calls": len(model.seen) - calls_before,
        "no_storage_mutation": wired.store.load(opened["matter_id"]) == before,
        "rejecting_owner": actual_owner,
        "precise_mismatch": any(required_issue in issue for issue in actual_issues),
        "later_binding_gate_rejected": bool(binding_issues),
    }
    record_case(
        identity, boundary="POST /api/turn -> saved mutation projection -> durable replay",
        user_passage=model.dossier.message,
        model_outputs=model.outputs,
        expected=expected, observed=observed,
        calls=[*model.seen, {"operation": "inject_saved_authority_fault", "fault": fault,
                            "changed_saved_response": row["response"]},
               {"operation": "public_replay", "response": result,
                            "owning_binding_issues": binding_issues,
                            "earlier_progress_issues": progress_issues}],
        scenario="faulty", claim_scope="mechanical", protection_status="blocked",
        notes="The original save contained an independently scoped date correction. "
        "Tampered fields are resealed where specified; no reinterpretation or retry "
        "may turn corruption into a fresh success reply. Ledger drift is rejected by "
        "the earlier original-evidence result seal; certificate drift reaches the "
        "mutation binding gate. No unexecuted later gate is claimed as observed. "
        "GS-15/17/18 are curated repository conversations, not acquired judgment text.",
    )
    assert observed == expected


def test_mislabeled_free_account_prose_remains_explicit_semantic_dependency(
    client, wired, monkeypatch
):
    """Characterize the remaining failure rather than claim a renderer detects meaning."""
    identity = "mutation-release-mislabeled-operational-account"
    model, opened, previous, date_target, custody_target = correction_fixture(
        client, wired, monkeypatch, identity=identity, declared_requirement=True
    )
    core = model.hook
    lie = "I revised the recorded date, confirmed persistence and finished the correction."

    def fabricated_wrong_accept(operation, payload, schema, data, current_model):
        data = core(operation, payload, schema, data, current_model)
        if operation == "extract_legal_details":
            return {"new_items": [], "changes": []}
        if operation == "continue_conversation":
            for unit in data["units"]:
                unit["blocks"][0].update(kind="account", text=lie)
                unit["sufficiency"] = {
                    "status": "partial", "block_id": unit["blocks"][0]["id"]
                }
                unit["record_outcome"] = {
                    "status": "unresolved", "block_id": unit["blocks"][0]["id"],
                    "effect_ids": [], "current_record_ids": [],
                    "reason": "The selected date correction has no actual effect.",
                }
        if operation == "verify_continuation":
            for accepted in data["accepted_units"]:
                accepted["record_check"] = {
                    "outcome": "unfinished",
                    "reason": "No record changed; this fixture wrongly accepts free prose.",
                }
                for check in accepted["block_checks"]:
                    check.update(
                        verdict="accept",
                        reason="Deliberately wrong ACCEPT of an operational lie labeled account.",
                    )
        return data

    model.hook = fabricated_wrong_accept
    data, saved, current = release(client, wired, monkeypatch, model, identity, opened=opened)
    text = "\n".join(element["text"] for element in data["elements"])
    expected = {
        "false_free_prose_released": True,
        "truthful_code_status_present": True,
        "unchanged_record": True,
        "typed_fulfillment": "unfinished",
        "saved_exact_reply": True,
    }
    observed = {
        "false_free_prose_released": lie in text,
        "truthful_code_status_present": "requested record work remains unfinished" in text,
        "unchanged_record": current.open_material == previous.open_material,
        "typed_fulfillment": data["material_coverage"]["execution"]["requests"][0]["fulfillment"],
        "saved_exact_reply": saved.brain_chat[-1]["response"]["elements"] == data["elements"],
    }
    evidence(
        identity, model, data, saved, expected, observed, scenario="faulty",
        claim_scope="semantic_dependency", protection_status="gap_demonstrated",
        notes="An independently scoped plan and code-owned outcome do not certify unrestricted "
        "prose deliberately mislabeled account. Forced wrong semantic ACCEPT remains a known "
        "dependency; no production keyword matcher or test-specific exception conceals it.",
    )
    assert observed == expected


def test_original_saved_binding_replays_at_historical_snapshot_after_later_unchanged_turn(
    client, wired, monkeypatch
):
    identity = "mutation-replay-valid-historical"
    model, opened, reply, saved, previous, date_target, custody_target = saved_correction(
        client, wired, monkeypatch, identity
    )
    later = GoldenModel(model.dossier, hook=owned_outcome("none", empty=True, linked=True))
    later_reply, saved_after, current_after = release(
        client, wired, monkeypatch, later, identity + "-later", opened=opened
    )
    assert saved_after.version > saved.version
    calls_before = len(later.seen)
    repeated, reopened, current_replayed = release(
        client, wired, monkeypatch, later, identity, opened=opened
    )
    expected = {
        "replayed": True,
        "additional_model_calls": 0,
        "reply_matches_original": True,
        "original_binding_matches": True,
        "no_duplicate_turn": True,
        "no_duplicate_effect": True,
        "independent_custody_retained": True,
    }
    observed = {
        "replayed": repeated["replayed"],
        "additional_model_calls": len(later.seen) - calls_before,
        "reply_matches_original": repeated["elements"] == reply["elements"],
        "original_binding_matches": repeated["material"] == reply["material"],
        "no_duplicate_turn": reopened == saved_after,
        "no_duplicate_effect": current_replayed.open_material == current_after.open_material,
        "independent_custody_retained": custody_target
        in {row["id"] for row in current_replayed.open_material},
    }
    record_case(
        identity, boundary="POST /api/turn -> historical saved binding -> exact durable replay",
        user_passage=model.dossier.message,
        model_outputs=[*model.outputs, *later.outputs], expected=expected, observed=observed,
        calls=[*model.seen, *later.seen], scenario="legitimate", claim_scope="mechanical",
        protection_status="admitted", notes="Saved authority uses its original snapshot version, "
        "not the later current matter version; unrelated later input cannot duplicate the effect.",
    )
    assert observed == expected
