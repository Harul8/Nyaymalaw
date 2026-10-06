"""Ack proposal defects stay local; narrowed review uses the same code owner."""
from copy import deepcopy

from nm.brain.conversation import WorkItem
from tests.test_brain_continuation import (
    ContinuationModel,
    _operation_names,
    conversation_plan,
    expression_block,
    unit,
)
from tests.test_brain_continuation_record_outcome import (
    declaration,
    evidence,
    run,
    verdict,
)


class DeniedRecoveryModel(ContinuationModel):
    def __init__(self, replies, denied_phase):
        super().__init__(replies)
        self.denied_phase = denied_phase
        self.recovery_claims = []

    def claim_recovery(self, phase):
        self.recovery_claims.append(phase)
        return phase != self.denied_phase


def receipt(*, mixed=False):
    value = evidence()
    value['record_changes'] = []
    value['requests'][0]['response_mode'] = 'record_acknowledgement'
    if mixed:
        value['requests'].append({'request_index': 1,
                                  'record_requirement': {'kind': 'none'},
                                  'response_mode': 'substantive'})
    return value


def plan(*, mixed=False):
    first = WorkItem(request='Review the attributed handover record', relation='new',
                     matter_scope='proposed', priority='ordinary', next_step='answer',
                     response_mode='record_acknowledgement',
                     record_requirement={'kind': 'change'})
    peers = (WorkItem(request='Explain the reported account', relation='new',
                      matter_scope='proposed', priority='ordinary', next_step='answer'),) \
        if mixed else ()
    return conversation_plan(items=(first, *peers))


def pure_none(index=0):
    value = unit(index, text='I changed and saved every record.')
    value.update(blocks=[value['blocks'][0]], questions=[],
                 sufficiency={'status': 'complete', 'block_id': f'account-{index}'})
    return value


def unresolved(index=0):
    value = pure_none(index)
    value['blocks'][0]['kind'] = 'limitation'
    value['sufficiency']['status'] = 'partial'
    value['record_outcome'] = declaration('unresolved', owner=f'account-{index}')
    return value


def test_none_ack_gets_one_local_correction_and_keeps_independent_peer():
    ordinary = unit(1)

    def repair(payload):
        assert [row['request_index'] for row in payload['correction']['validation_issues']] == [0]
        assert 'use unresolved' in payload['correction']['validation_issues'][0]['issue']
        return {'units': [unresolved()]}

    model = ContinuationModel([{'units': [pure_none(), ordinary]}, verdict(1),
                               repair, verdict(0, outcome='unfinished')])
    result = run(model, receipt(mixed=True), plan=plan(mixed=True))
    assert _operation_names(model) == ['continue_conversation', 'verify_continuation',
                                       'continue_conversation', 'verify_continuation']
    assert [row['state'] for row in result.coverage] == ['ok', 'ok']
    assert result.units[0]['record_outcome']['status'] == 'unresolved'
    assert result.units[1]['blocks'][0]['text'] == (
        'Your message includes: “The handover was on 4 May.”')
    statuses = model.schemas[0]['properties']['units']['items']['properties'][
        'record_outcome']['properties']['status']['enum']
    assert 'none' in statuses  # This peer has a genuine non-record deliverable.
    repaired_statuses = model.schemas[2]['properties']['units']['items']['properties'][
        'record_outcome']['properties']['status']['enum']
    assert 'none' not in repaired_statuses


def test_repeated_none_ack_is_unavailable_without_crashing_or_inventing_completion():
    model = ContinuationModel([{'units': [pure_none()]}, {'units': [pure_none()]}])
    result = run(model, receipt(), plan=plan())
    assert _operation_names(model) == ['continue_conversation', 'continue_conversation']
    assert result.units == ()
    assert result.coverage[0]['state'] == 'unavailable'


def narrowed_proposal():
    value = unit(text='I changed and saved every record.')
    value['questions'] = []
    value['blocks'].pop(1)
    value['record_outcome'] = declaration('unresolved', owner='limit-0')
    value['blocks'].insert(1, expression_block(
        'unsupported-conclusion', 'assessment', operator='checked_legal', sources=()))
    return value


def test_narrowed_pure_ack_is_canonicalized_before_its_independent_review():
    proposed = narrowed_proposal()
    model = ContinuationModel([{'units': [proposed]}, {'units': [proposed]},
                               verdict(0, outcome='unfinished')])
    result = run(model, receipt(), plan=plan())
    assert _operation_names(model) == ['continue_conversation', 'continue_conversation',
                                       'verify_continuation']
    reviewed = model.calls[-1][1]
    assert reviewed['input']['material_coverage']['execution']['requests'][0][
        'acknowledgement_delivery'] == 'substantive_followup'
    account, limitation, status = reviewed['units'][0]['blocks']
    assert account['id'] == 'account-0'
    assert account['text'] == 'Your message includes: “The handover was on 4 May.”'
    assert account['evidence_expression']['operator'] == 'source_account'
    assert limitation['id'] == 'limit-0'
    assert limitation['text'] == (
        'The requested conclusion remains unresolved on the supplied support.')
    assert limitation['evidence_expression']['operator'] == 'limitation'
    assert status['id'] == reviewed['units'][0]['record_outcome']['block_id']
    assert status['text'] == 'The requested record work remains unfinished.'
    assert status['evidence_expression']['operator'] == 'record_result'
    assert [block['id'] for block in result.units[0]['blocks']] == [
        'account-0', 'limit-0', status['id']]
    assert [block['text'] for block in result.units[0]['blocks']] == [
        account['text'], limitation['text'], status['text']]
    assert result.coverage[0]['state'] == 'partial'


def test_narrowed_extra_dispatch_requires_budget_and_keeps_checked_peer():
    proposed = narrowed_proposal()
    model = DeniedRecoveryModel([{'units': [proposed, unit(1)]}, verdict(1),
                                 {'units': [deepcopy(proposed)]}],
                                'continue_conversation:limited_review')
    result = run(model, receipt(mixed=True), plan=plan(mixed=True))
    assert _operation_names(model) == ['continue_conversation', 'verify_continuation',
                                       'continue_conversation']
    assert model.recovery_claims == ['continue_conversation:correction',
                                      'continue_conversation:limited_review']
    assert [row['request_index'] for row in result.units] == [1]
    assert [row['state'] for row in result.coverage] == ['unavailable', 'ok']
