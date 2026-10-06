"""Prepared scope-outcome mechanics preserve historical untracked receipts."""
from copy import deepcopy

import pytest

from nm.brain import execution_contracts as contracts
from nm.brain.execution_contracts import canonical_record_acknowledgements, effect_catalogue
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, build_mutation_authorities
from nm.shared.model_port import SchemaViolation
from tests.test_brain_execution_contracts import receipt, unit

LIE = "The correction was saved and the requested record work is complete."


def scope_evidence(*, relation="corrects", target="prior", operation="corrects",
                   kind="account_contribution", stamped=True, performed=True):
    evidence = receipt(
        relation=relation, targets=[target], retired=[target] if performed else [],
        activated=["result"] if performed else [])
    if not performed:
        evidence["effects"]["details"]["operations"] = []
    evidence["requests"][0]["record_requirement"] = {
        "kind": "none", "target_ids": [], "operation": "none", "success_condition": "",
    }
    evidence["requests"][0]["response_mode"] = "substantive"
    sources = {"L1": {"turn_id": "turn", "role": "advocate",
                       "quoted": "The exact requested account."}}
    targets = {identity: {"id": identity, "statement": "An earlier owned account."}
               for identity in ("prior", "other")}
    ledger = build_mutation_authorities(
        owner=evidence["owner"], expected_version=evidence["expected_version"],
        target_catalogue=targets, source_catalogue=sources, request_indices=[0], proposals=[{
            "request_index": 0, "authority_kind": kind, "authority_source_ids": ["L1"],
            "target_scope": "exact", "target_ids": [] if operation == "new" else ["prior"],
            "permitted_relations": [operation],
        }])
    evidence.update(mutation_authority_contract=AUTHORITY_CONTRACT, mutation_authorities=ledger)
    if stamped:
        evidence["scope_outcome_contract"] = "scoped_record_outcome_v2"
    return evidence


def test_fresh_requirement_derives_owned_non_new_scope_without_changing_original_metadata():
    evidence = scope_evidence(stamped=False)
    before = deepcopy(evidence)
    assert contracts.request_requires_record_outcome(evidence["requests"][0], evidence) is True
    assert contracts.request_requires_record_outcome(evidence["requests"][0]) is False
    assert evidence == before
    creation = scope_evidence(operation="new")
    assert contracts.request_requires_record_outcome(creation["requests"][0], creation) is False


def test_stamped_scope_rejects_none_but_historical_none_remains_explicitly_untracked():
    evidence = scope_evidence(performed=False)
    with pytest.raises(SchemaViolation, match="scope"):
        contracts.validate_record_outcome(unit("none", complete=True), evidence, ["prior"])
    historical = scope_evidence(stamped=False, performed=False)
    contracts.validate_record_outcome(unit("none", complete=True), historical, ["prior"])


@pytest.mark.parametrize("version", ["unowned-scope-outcome", True, {}])
def test_unknown_scope_outcome_version_cannot_downgrade_a_saved_requirement(version):
    evidence = scope_evidence(performed=False)
    evidence["scope_outcome_contract"] = version
    with pytest.raises(contracts.ExecutionEvidenceInvalid):
        contracts.validate_record_outcome(unit("none"), evidence, ["prior"])


def test_existing_v3_replay_does_not_rewrite_its_historical_linked_completion():
    evidence = scope_evidence(stamped=False, performed=False)
    evidence["record_changes"] = []
    evidence["requests"][0].update(
        record_requirement={"kind": "change"},
        acknowledgement_contract=contracts.RECORD_ACKNOWLEDGEMENT_CONTRACT)
    block = {"id": "old-linked", "kind": "completion", "text": LIE,
             "span_ids": [], "record_ids": [], "legal_source_ids": [],
             "inline_citations": [], "uncertainty": "none"}
    saved = {"units": [{
        "request_index": 0, "blocks": [block], "next_work": [], "questions": [{
            "id": "old-link", "block_id": "old-linked", "purpose": "Original saved purpose.",
            "target_ids": [], "existing_id": ""}],
        "record_outcome": {"status": "unresolved", "block_id": "old-linked",
                           "effect_ids": [], "current_record_ids": [], "reason": "Unfinished."},
        "record_check": {"outcome": "unfinished", "reason": "The original saved disposition."},
    }]}
    replayed = canonical_record_acknowledgements(
        saved, evidence, record_catalogue={}, replay=True)
    assert replayed["units"][0]["blocks"][0] == block
    fresh = canonical_record_acknowledgements(
        saved, deepcopy(evidence), record_catalogue={}, replay=False)
    assert LIE not in "\n".join(row["text"] for row in fresh["units"][0]["blocks"])


@pytest.mark.parametrize("field", ["owner", "expected_version", "seal", "target"])
def test_derived_outcome_requirement_refuses_broken_or_foreign_permission_proofs(field):
    evidence = scope_evidence()
    if field == "owner":
        evidence["owner"]["advocate_id"] = "foreign-advocate"
    elif field == "expected_version":
        evidence["expected_version"] += 1
    elif field == "seal":
        evidence["mutation_authorities"]["seal"] = "0" * 64
    else:
        evidence["mutation_authorities"]["authorities"][0]["target_ids"] = ["other"]
    with pytest.raises(contracts.ExecutionEvidenceInvalid):
        contracts.request_requires_record_outcome(evidence["requests"][0], evidence)


@pytest.mark.parametrize("relation,target", [
    ("adds", "prior"), ("corrects", "other"),
])
def test_unrelated_or_wrong_operation_effect_cannot_complete_a_stamped_declared_scope(
        relation, target):
    evidence = scope_evidence(relation=relation, target=target)
    identity, = effect_catalogue(evidence)
    with pytest.raises(SchemaViolation, match="target and operation"):
        contracts.validate_record_outcome(
            unit("performed", effects=[identity], complete=True), evidence, ["result"])


def test_matching_effect_completes_and_only_checked_redundant_current_metadata_is_dropped():
    evidence = scope_evidence()
    identity, = effect_catalogue(evidence)
    declared = unit("performed", effects=[identity], current=["result", "other"], complete=True)
    contracts.validate_record_outcome(declared, evidence, ["result", "other"])
    assert declared["record_outcome"]["effect_ids"] == [identity]
    assert declared["record_outcome"]["current_record_ids"] == []
    with pytest.raises(SchemaViolation, match="active owned"):
        contracts.validate_record_outcome(
            unit("performed", effects=[identity], current=["foreign"]), evidence, ["result"])
    with pytest.raises(SchemaViolation, match="needs effects"):
        contracts.validate_record_outcome(
            unit("performed", current=["result"]), evidence, ["result"])


@pytest.mark.parametrize("state", ["complete", "partial", "unassessed"])
def test_scoped_no_change_review_needs_the_exact_owned_full_review_coverage(state):
    evidence = scope_evidence(kind="interpretation_review", performed=False)
    scope = {"requests": [{"request_index": 0,
                            "record_requirement": deepcopy(evidence["requests"][0][
                                "record_requirement"])}],
             "mutation_authority_contract": AUTHORITY_CONTRACT,
             "mutation_authorities": deepcopy(evidence["mutation_authorities"])}
    evidence["review_scope"] = deepcopy(scope)
    for stage in ("detail_review", "dispute_review"):
        evidence["stages"][stage]["account_coverage"] = {
            "contract": "independent_account_coverage_v1", "state": state,
            "missing_source_ids": [] if state == "complete" else ["L1"],
            "reason": "The independently scripted assessment covers the declared original scope.",
            "review_scope": deepcopy(scope),
        }
    declared = unit("review_no_change", current=["prior"], complete=True)
    if state != "complete":
        with pytest.raises(SchemaViolation, match="partial/unassessed"):
            contracts.validate_record_outcome(declared, evidence, ["prior"])
    else:
        contracts.validate_record_outcome(declared, evidence, ["prior"])
        evidence["stages"]["detail_review"]["account_coverage"]["review_scope"].pop(
            "mutation_authorities")
        with pytest.raises(SchemaViolation, match="exact requested account scope"):
            contracts.validate_record_outcome(declared, evidence, ["prior"])


def test_unrelated_question_completion_does_not_complete_the_unresolved_scope_task():
    evidence = scope_evidence(performed=False)
    contracts.validate_record_outcome(
        unit("unresolved", progress=[{"target_id": "independent-question", "status": "complete"}]),
        evidence, ["prior"])
    with pytest.raises(SchemaViolation, match="cannot complete"):
        contracts.validate_record_outcome(
            unit("unresolved", progress=[{"target_id": "$work", "status": "complete"}]),
            evidence, ["prior"])


def two_target_scope(*, both_effects=False):
    evidence = scope_evidence()
    old = evidence["mutation_authorities"]
    proposal = {key: value for key, value in old["authorities"][0].items() if key != "id"}
    evidence["mutation_authorities"] = build_mutation_authorities(
        owner=old["owner"], expected_version=old["expected_version"],
        target_catalogue=old["target_catalogue"], source_catalogue=old["source_catalogue"],
        request_indices=[0], proposals=[proposal, {**proposal, "target_ids": ["other"]}])
    if both_effects:
        details = evidence["effects"]["details"]
        details["activated_record_ids"].append("result-other")
        details["retired_record_ids"].append("other")
        details["operations"].append({**deepcopy(details["operations"][0]),
                                      "result_id": "result-other", "target_record_ids": ["other"],
                                      "retired_target_ids": ["other"]})
    return evidence


def test_partial_performed_scope_keeps_own_task_pending_and_unrelated_updates_unchanged():
    evidence = two_target_scope()
    identity, = effect_catalogue(evidence)
    independent = [{"target_id": "unrelated-task", "status": "complete"},
                   {"target_id": "answered-question", "status": "complete"}]
    declared = unit("performed", effects=[identity], progress=deepcopy(independent))
    contracts.validate_record_outcome(declared, evidence, ["result", "other"])
    assert declared["progress_updates"] == independent
    assert declared["sufficiency"]["status"] == "partial"
    assert declared["record_outcome"]["effect_ids"] == [identity]


@pytest.mark.parametrize("task_update", [False, True])
def test_one_target_effect_cannot_complete_two_exact_contribution_scopes(task_update):
    evidence = two_target_scope()
    identity, = effect_catalogue(evidence)
    declared = unit("performed", effects=[identity], complete=not task_update,
                    progress=[{"target_id": "$work", "status": "complete"}]
                    if task_update else [])
    with pytest.raises(SchemaViolation, match="every exact scoped target"):
        contracts.validate_record_outcome(declared, evidence, ["result", "other"])


@pytest.mark.parametrize("task_update", [False, True])
def test_all_matching_effects_can_complete_two_exact_contribution_scopes(task_update):
    evidence = two_target_scope(both_effects=True)
    selected = list(effect_catalogue(evidence))
    declared = unit("performed", effects=selected, complete=not task_update,
                    progress=[{"target_id": "$work", "status": "complete"}]
                    if task_update else [])
    contracts.validate_record_outcome(declared, evidence, ["result", "result-other"])
    assert declared["record_outcome"]["effect_ids"] == selected


def test_completed_exact_account_scope_requires_every_selected_current_target_after_full_review():
    evidence = two_target_scope()
    evidence["effects"]["details"].update(
        operations=[], activated_record_ids=[], retired_record_ids=[])
    scope = {"requests": [{"request_index": 0,
                            "record_requirement": deepcopy(evidence["requests"][0][
                                "record_requirement"])}],
             "mutation_authority_contract": AUTHORITY_CONTRACT,
             "mutation_authorities": deepcopy(evidence["mutation_authorities"])}
    evidence["review_scope"] = deepcopy(scope)
    for stage in ("detail_review", "dispute_review"):
        evidence["stages"][stage]["account_coverage"] = {
            "contract": "independent_account_coverage_v1", "state": "complete",
            "missing_source_ids": [], "reason": "The exact original account scope was reviewed.",
            "review_scope": deepcopy(scope)}
    with pytest.raises(SchemaViolation, match="every exact scoped target"):
        contracts.validate_record_outcome(
            unit("already_current", current=["prior"], complete=True), evidence, ["prior", "other"])
    contracts.validate_record_outcome(
        unit("already_current", current=["prior", "other"], complete=True),
        evidence, ["prior", "other"])

@pytest.mark.parametrize("linked", ["questions", "next_work"])
@pytest.mark.parametrize("status", [
    "unresolved", "performed", "already_current", "review_no_change",
])
def test_fresh_direct_renderer_owns_completion_words_even_if_completion_is_linked(linked, status):
    evidence = receipt(activated=["result"] if status == "performed" else [])
    evidence["requests"][0]["record_requirement"] = {"kind": "review" if status == (
        "review_no_change") else "change"}
    identity, = effect_catalogue(evidence)
    result_record = {"id": "result", "statement": "An admitted attributed result."}
    evidence["record_changes"] = [{
        "effect_id": identity, "relation": "new", "kind": "details", "before_records": [],
        "after_record": result_record,
    }] if status == "performed" else []
    catalogue = {"result": {"type": "material", "record": result_record}}
    block = {"id": "linked-status", "kind": "completion", "text": LIE,
             "span_ids": [], "record_ids": [], "legal_source_ids": [],
             "inline_citations": [], "uncertainty": "none"}
    safe = {**deepcopy(block), "id": "genuine-question", "kind": "question",
            "text": "Which original account identifies this event?"}
    declared = {
        "request_index": 0, "blocks": [block, safe], "questions": [], "next_work": [],
        "record_outcome": {
            "status": status, "block_id": "linked-status", "effect_ids": [identity]
            if status == "performed" else [], "current_record_ids": ["result"]
            if status in ("already_current", "review_no_change") else [],
            "reason": "The owned result."},
        "record_check": {
            "outcome": {"unresolved": "unfinished", "performed": "fulfilled",
                        "already_current": "fulfilled",
                        "review_no_change": "no_change_justified"}[status],
            "reason": "The independently checked disposition.",
        },
    }
    declared[linked] = [{"id": "status-link", "block_id": "linked-status",
                         "purpose": "The model incorrectly reused the completion owner.",
                         "target_ids": [], "existing_id": ""}]
    declared["questions"].append({"id": "actual-question", "block_id": "genuine-question",
                                  "purpose": "Identify the original account.",
                                  "target_ids": [], "existing_id": ""})
    rendered = canonical_record_acknowledgements(
        {"units": [declared]}, evidence, record_catalogue=catalogue)
    blocks = {row["id"]: row for row in rendered["units"][0]["blocks"]}
    assert LIE not in "\n".join(row["text"] for row in blocks.values())
    assert blocks["genuine-question"] == safe
    assert any(row["text"].startswith({
        "unresolved": "The requested record work remains unfinished.",
        "performed": "Saved record changes:", "already_current": "Current record entries:",
        "review_no_change": "The requested record review completed without a selected change.",
    }[status]) for row in blocks.values())


@pytest.mark.parametrize("link_field", [None, "questions", "next_work"])
def test_fresh_completion_kind_is_never_free_prose_under_an_unscoped_none_result(link_field):
    evidence = scope_evidence(operation="new", stamped=False, performed=False)
    declared = unit("none")
    block = declared["blocks"][0]
    block.update(kind="completion", text=LIE)
    declared.update(questions=[], next_work=[])
    if link_field:
        declared[link_field] = [{"id": "followup", "block_id": block["id"]}]
    with pytest.raises(SchemaViolation, match="completion block"):
        canonical_record_acknowledgements(
            {"units": [declared]}, evidence, record_catalogue={})
