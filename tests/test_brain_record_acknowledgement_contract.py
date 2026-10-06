"""Direct observable acknowledgement contract checks, without app/model calls.

The caller supplies a mechanically admitted unit and, for final rendering, its
independently checked disposition. This helper does not evaluate source meaning.
"""
from copy import deepcopy

import pytest

from nm.brain import execution_contracts
from nm.brain.execution_contracts import ExecutionEvidenceInvalid, effect_catalogue
from tests.test_brain_continuation_record_outcome import evidence

STATEMENT = "The handover was on 4 May."


def inputs(status="performed", *, checked=True, reader="returned"):
    receipt = evidence(reader=reader)
    receipt["requests"][0]["response_mode"] = "record_acknowledgement"
    effect_id = next(iter(effect_catalogue(receipt)))
    record = {"id": "saved-observation", "statement": STATEMENT}
    catalogue = {record["id"]: {"id": record["id"], "type": "material", "record": record}}
    receipt["record_changes"] = [{"effect_id": effect_id, "kind": "details", "relation": "new",
                                  "before_records": [], "after_record": record}]
    unit = {
        "request_index": 0,
        "blocks": [{"id": "owned-block", "kind": "completion", "text": "Fabricated prose.",
                    "uncertainty": "reported", "span_ids": ["L1"], "record_ids": [],
                    "legal_source_ids": [], "inline_citations": []}],
        "questions": [], "next_work": [],
        "record_outcome": {"status": status, "block_id": "owned-block",
                           "effect_ids": [effect_id] if status == "performed" else [],
                           "current_record_ids": [record["id"]]
                           if status == "already_current" else [], "reason": "Declared outcome."},
        "sufficiency": {"status": "partial" if status == "unresolved" else "complete",
                        "block_id": "owned-block"},
        "work": {"create": True, "existing_id": ""}, "progress_updates": [],
    }
    if checked:
        unit["record_check"] = {
            "outcome": {"performed": "fulfilled", "already_current": "fulfilled",
                        "review_no_change": "no_change_justified",
                        "unresolved": "unfinished"}[status],
            "reason": "The test explicitly supplies the checked disposition.",
        }
    return {"units": [unit]}, receipt, catalogue


def render(continuation, receipt, catalogue, **kwargs):
    return execution_contracts.canonical_record_acknowledgements(
        continuation, receipt, record_catalogue=catalogue, **kwargs)


def test_pre_review_rendering_needs_no_invented_independent_verdict():
    continuation, receipt, catalogue = inputs(checked=False)
    original = deepcopy(continuation)
    result = render(continuation, receipt, catalogue, require_checked=False)
    assert result["units"][0]["blocks"][0]["text"] == (
        "Saved record changes:\nNew entry: " + STATEMENT)
    assert "record_check" not in result["units"][0]
    assert continuation == original
    assert receipt["requests"][0]["acknowledgement_delivery"] == "code_only"


def test_final_rendering_requires_checked_disposition():
    continuation, receipt, catalogue = inputs(checked=False)
    with pytest.raises(ExecutionEvidenceInvalid, match="no checked record outcome"):
        render(continuation, receipt, catalogue)


def test_checked_outcome_preserves_lifecycle_and_block_owners():
    continuation, receipt, catalogue = inputs()
    original = deepcopy(continuation["units"][0])
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["record_outcome"] == original["record_outcome"]
    assert result["record_check"] == original["record_check"]
    assert result["work"] == original["work"]
    assert result["progress_updates"] == original["progress_updates"]
    assert result["sufficiency"] == original["sufficiency"]
    assert result["blocks"][0]["id"] == original["blocks"][0]["id"]


def test_a_returned_reader_is_required_for_selected_performed_effect():
    continuation, receipt, catalogue = inputs(reader="not_run")
    with pytest.raises(ExecutionEvidenceInvalid, match="unperformed change"):
        render(continuation, receipt, catalogue)


def test_selected_effect_needs_canonical_entry_delta():
    continuation, receipt, catalogue = inputs()
    receipt["record_changes"] = []
    with pytest.raises(ExecutionEvidenceInvalid, match="unperformed change"):
        render(continuation, receipt, catalogue)


def test_current_entry_selection_cannot_invent_foreign_record():
    continuation, receipt, catalogue = inputs("already_current")
    continuation["units"][0]["record_outcome"]["current_record_ids"] = ["foreign-record"]
    with pytest.raises(ExecutionEvidenceInvalid, match="unowned current entry"):
        render(continuation, receipt, catalogue)


def test_current_state_is_displayed_without_claiming_historical_operation():
    continuation, receipt, catalogue = inputs("already_current")
    result = render(continuation, receipt, catalogue)
    assert result["units"][0]["blocks"][0]["text"] == "Current record entries:\n" + STATEMENT


def test_unresolved_outcome_cannot_turn_into_completion_by_rendering():
    continuation, receipt, catalogue = inputs("unresolved")
    result = render(continuation, receipt, catalogue)["units"][0]
    assert result["blocks"][0]["text"] == "The requested record work remains unfinished."
    assert result["record_check"]["outcome"] == "unfinished"
    assert result["sufficiency"]["status"] == "partial"
    assert result["progress_updates"] == []


@pytest.mark.parametrize("field", ["questions", "next_work"])
def test_substantive_followup_preserves_checked_content_instead_of_silently_dropping_it(field):
    continuation, receipt, catalogue = inputs("unresolved")
    continuation["units"][0][field] = [{"id": "followup", "block_id": "owned-block"}]
    original = deepcopy(continuation)
    assert render(continuation, receipt, catalogue) == original
    assert receipt["requests"][0]["acknowledgement_delivery"] == "substantive_followup"


def test_substantive_receipt_cannot_carry_forged_code_delivery_marker():
    continuation, receipt, catalogue = inputs()
    receipt["requests"][0].update(response_mode="substantive", acknowledgement_delivery="code_only")
    with pytest.raises(ExecutionEvidenceInvalid, match="no declared delivery owner"):
        render(continuation, receipt, catalogue)


def test_discarded_law_prose_does_not_leave_false_inline_anchors_on_code_status():
    continuation, receipt, catalogue = inputs("unresolved")
    block = continuation["units"][0]["blocks"][0]
    block.update(kind="assessment", legal_source_ids=["law-1"], record_ids=["research-1"],
                 inline_citations=[{"text": "Fabricated prose.", "legal_source_id": "law-1"}])
    before_review = render(continuation, receipt, catalogue, require_checked=False)["units"][0]
    assert before_review["blocks"][0]["kind"] == "limitation"
    assert before_review["blocks"][0]["inline_citations"] == []
    assert before_review["blocks"][0]["legal_source_ids"] == []
    assert before_review["blocks"][0]["record_ids"] == []
    assert before_review["blocks"][0]["span_ids"] == ["L1"]
    after_review = render({"units": [before_review]}, receipt, catalogue)["units"][0]
    assert "inline_citations" not in after_review["blocks"][0]


def test_fresh_rendering_stamps_its_explicit_contract():
    continuation, receipt, catalogue = inputs()
    render(continuation, receipt, catalogue)
    assert receipt['requests'][0]['acknowledgement_contract'] == (
        execution_contracts.RECORD_ACKNOWLEDGEMENT_CONTRACT)


@pytest.mark.parametrize('version', ['unknown-renderer', '', 2])
def test_unknown_saved_rendering_contract_is_refused(version):
    continuation, receipt, catalogue = inputs()
    receipt['requests'][0]['acknowledgement_contract'] = version
    with pytest.raises(ExecutionEvidenceInvalid, match='contract is unsupported'):
        render(continuation, receipt, catalogue, replay=True)


def test_unstamped_legacy_replay_keeps_its_original_block_metadata():
    continuation, receipt, catalogue = inputs()
    receipt['requests'][0]['acknowledgement_delivery'] = 'code_only'
    original = deepcopy(continuation['units'][0]['blocks'][0])
    result = render(continuation, receipt, catalogue, replay=True)
    block = result['units'][0]['blocks'][0]
    assert block['kind'] == original['kind']
    assert block['uncertainty'] == original['uncertainty']
    assert block['legal_source_ids'] == original['legal_source_ids']
    assert 'acknowledgement_contract' not in receipt['requests'][0]
    assert 'inline_citations' not in block


def test_substantive_receipt_cannot_carry_unowned_contract_version():
    continuation, receipt, catalogue = inputs()
    receipt['requests'][0]['response_mode'] = 'substantive'
    receipt['requests'][0]['acknowledgement_contract'] = 'unknown-renderer'
    with pytest.raises(ExecutionEvidenceInvalid, match='no declared delivery owner'):
        render(continuation, receipt, catalogue, replay=True)


def partial_reader_stage():
    return {'state': 'partial', 'proposals': 1, 'admissible_proposals': 1,
            'proposal_validation': 'owned_extraction_proposals_v1',
            'read_status': {'state': 'partial', 'proposal_count': 1}}


def partial_effects(stage, *, review='checked'):
    receipt = evidence()
    receipt['stages']['detail_extraction'] = stage
    receipt['stages']['detail_review']['state'] = review
    return execution_contracts.effect_catalogue(receipt)


def test_partial_reader_admits_verified_positive_effect_without_certifying_coverage():
    stage = partial_reader_stage()
    assert execution_contracts.reader_admission_checked(stage)
    effect = next(iter(partial_effects(stage).values()))
    assert effect['performed'] is True
    assert effect['reader_returned'] is False
    assert effect['reader_admission_checked'] is True


@pytest.mark.parametrize('fault', ['bare_partial', 'zero', 'boolean', 'count_mismatch',
                                   'read_count_mismatch', 'declared_complete', 'wrong_contract'])
def test_partial_reader_without_owned_matching_positive_admission_has_no_performed_effect(fault):
    stage = partial_reader_stage()
    if fault == 'bare_partial':
        stage = {'state': 'partial'}
    elif fault == 'zero':
        stage.update(proposals=0, admissible_proposals=0)
        stage['read_status']['proposal_count'] = 0
    elif fault == 'boolean':
        stage.update(proposals=True, admissible_proposals=True)
        stage['read_status']['proposal_count'] = True
    elif fault == 'count_mismatch':
        stage['proposals'] = 2
    elif fault == 'read_count_mismatch':
        stage['read_status']['proposal_count'] = 2
    elif fault == 'declared_complete':
        stage['read_status']['state'] = 'complete'
    else:
        stage['proposal_validation'] = 'model_intention'
    assert not execution_contracts.reader_admission_checked(stage)
    assert next(iter(partial_effects(stage).values()))['performed'] is False


def test_partial_reader_still_needs_independent_grounding():
    effect = next(iter(partial_effects(partial_reader_stage(), review='partial').values()))
    assert effect['performed'] is False


def test_partial_reader_operations_cannot_exceed_its_owned_admission_count():
    receipt = evidence()
    receipt['stages']['detail_extraction'] = partial_reader_stage()
    effect = receipt['effects']['details']
    second = deepcopy(effect['operations'][0])
    second['result_id'] = 'second-unowned-observation'
    effect['operations'].append(second)
    effect['activated_record_ids'].append(second['result_id'])
    with pytest.raises(ExecutionEvidenceInvalid, match='exceed admitted reader proposals'):
        execution_contracts.effect_catalogue(receipt)


def test_partial_positive_effect_cannot_certify_complete_account_review():
    continuation, receipt, catalogue = inputs()
    receipt['stages']['detail_extraction'] = partial_reader_stage()
    requirement = {'kind': 'review', 'target_ids': [], 'operation': 'none',
                   'success_condition': 'Review the complete attributed account.'}
    receipt['requests'][0]['record_requirement'] = requirement
    receipt['stages']['dispute_review']['account_coverage'] = {
        'contract': 'independent_account_coverage_v1', 'state': 'complete',
        'reason': 'The independent fixture explicitly certifies the dispute scope.',
        'missing_source_ids': [], 'review_scope': {'requests': [
            {'request_index': 0, 'record_requirement': requirement}]}}
    effect = next(iter(execution_contracts.effect_catalogue(receipt).values()))
    assert effect['performed'] is True
    with pytest.raises(execution_contracts.ReviewCompletionIncomplete,
                       match='actual reading and review'):
        execution_contracts.validate_review_completion(
            continuation['units'][0], receipt, requirement=requirement)
