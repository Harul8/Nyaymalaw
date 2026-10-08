"""Private research handoff, execution coverage, persistence and replay."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.retrieval import HybridSearcher
from nm.brain.turn import BrainRefused, BrainService, CONTRACT, saved_rows
from nm.shared.model_port import ModelError, SchemaViolation
from tests.test_current_brain_app import MIXED_MESSAGE, WiredModel, mixed_outputs, greeting_outputs
from tests.test_current_brain_turn import MemoryStore, turn
from tests.test_current_brain_retrieval import Collection


def plan():
    return {'plans': [{'dispute_id':'dispute:1', 'queries': [
        {'text':'return of money retained under an agreement', 'purpose':'Seek the obligations and exceptions.',
         'passage_ids':['current:p1']}], 'uncertainty':None}]}


class Search:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail
        self.inner = HybridSearcher({'provision':Collection(), 'judgment':Collection('judgment')})

    def search(self, queries):
        self.calls.append(deepcopy(queries))
        if self.fail: raise OSError('Local retrieval unavailable')
        return self.inner.search(queries)


def run(*extra, store=None, search=None, outputs=None):
    model = WiredModel(*(outputs or mixed_outputs(MIXED_MESSAGE)), *extra)
    search = search or Search()
    store = store or MemoryStore()
    service = BrainService(store=store, model=model, legal_search=search, session_current=lambda:True)
    result = service.run(turn(message=MIXED_MESSAGE)).as_dict()
    return service, result, model, store, search


def test_research_is_source_bound_saved_private_and_replayed_without_calls():
    brain, result, model, store, search = run(plan())
    row = saved_rows(store.value, 'adv_owner')[0]
    assert row['contract'] == CONTRACT and row['research']['state'] == 'ready'
    assert result['metrics']['llm_calls'] == 4
    assert model.calls[-1][0].operation == 'decompose_disputes'
    assert len(search.calls) == 1 and len(search.calls[0]) == 2
    assert search.calls[0][-1]['query_id'] == 'dispute:1:original'
    assert 'supplier refuses to return my deposit' in search.calls[0][-1]['text']
    assert '[current advocate support]' in search.calls[0][-1]['text']
    assert 'research' not in result and result['elements'][0]['text'] == 'Message received.'
    assert all(c['legal_status'] == 'candidate_unassessed' for c in row['research']['searches']['dispute:1']['candidates'])
    again = brain.run(turn(message=MIXED_MESSAGE)).as_dict()
    assert again == {**result, 'replayed':True} and len(model.calls) == 4 and len(search.calls) == 1


def test_planning_outage_preserves_original_account_search_and_explicit_gap():
    _, result, model, store, search = run(ModelError('Unavailable'))
    research = store.value.brain_chat[0]['research']
    assert research['state'] == 'partial' and research['planning'] is None
    assert research['planning_failure'] == {'stage':'decomposition', 'code':'model_error'}
    assert len(search.calls[0]) == 1 and research['searches']['dispute:1']['state'] == 'ready'
    assert result['committed'] == 'committed' and len(model.calls) == 4


def test_bad_route_preserves_other_route_and_original_search_without_extra_call():
    proposal = plan()
    proposal['plans'][0]['queries'].append({'text':'foreign', 'purpose':'bad owner', 'passage_ids':['other:p1']})
    _, _, model, store, search = run(proposal)
    research = store.value.brain_chat[0]['research']
    assert research['state'] == 'partial' and len(search.calls[0]) == 2 and len(model.calls) == 4
    assert research['planning']['issues'][0]['query_id'] == 'dispute:1:q2'


def test_search_failure_does_not_lose_checked_input_or_claim_research_complete():
    _, result, _, store, _ = run(plan(), search=Search(fail=True))
    research = saved_rows(store.value,'adv_owner')[0]['research']
    assert research['state'] == 'partial' and research['searches'] == {}
    assert research['failures'] == {'dispute:1': {'stage':'search', 'code':'search_unavailable'}}
    assert result['input_admitted'] is True and result['service_status'] is None


def test_decomposition_uses_shared_correction_allowance():
    _, result, model, store, _ = run(SchemaViolation('bad plan'), plan())
    assert result['metrics']['llm_calls'] == 5 and len(model.calls) == 5
    assert store.value.brain_chat[0]['research']['state'] == 'ready'
    assert 'correction_feedback' in model.calls[-1][0].user


def test_spent_extraction_allowance_cannot_reset_for_decomposition():
    from tests.test_current_brain_extraction_repair import missing_outputs
    _, result, model, store, search = run(SchemaViolation('bad plan'), outputs=missing_outputs())
    assert result['metrics']['llm_calls'] == 6 and len(model.calls) == 6
    assert store.value.brain_chat[0]['research']['state'] == 'partial'
    assert len(search.calls[0]) == 1


@pytest.mark.parametrize('damage', ['scope','owner','source','contract','empty_ready','downgrade','missing_source_identity','context_shape','context_segment'])
def test_reopen_rejects_detached_research_and_unknown_or_downgraded_contract(damage):
    _, _, _, store, _ = run(plan())
    rows = deepcopy(store.value.brain_chat)
    research = rows[0]['research']
    if damage == 'scope': research['input_digest'] = 'different'
    elif damage == 'owner': research['searches']['dispute:other'] = research['searches'].pop('dispute:1')
    elif damage == 'source': research['searches']['dispute:1']['candidates'][0]['text'] = 'invented'
    elif damage == 'context_shape': research['searches']['dispute:1']['candidates'][0]['context'] = []
    elif damage == 'context_segment': research['searches']['dispute:1']['candidates'][0]['context']['segments'] = [None]
    elif damage == 'missing_source_identity': research['searches']['dispute:1']['candidates'][0]['source']['chunk_id'] = ''
    elif damage == 'contract': research['contract'] = 'future'
    elif damage == 'empty_ready': research['searches'] = {}
    else: rows[0]['contract'] = 'current_brain_turn_v5'
    with pytest.raises(BrainRefused): saved_rows(replace(store.value,brain_chat=rows), 'adv_owner')


def test_no_dispute_uses_no_planning_or_search_and_keeps_v5_replay_unchanged():
    search, model, store = Search(), WiredModel(*greeting_outputs()), MemoryStore()
    brain = BrainService(store=store, model=model, legal_search=search, session_current=lambda:True)
    result = brain.run(turn()).as_dict()
    row = deepcopy(store.value.brain_chat[0])
    assert row['research']['state'] == 'not_needed' and len(model.calls) == 3 and search.calls == []
    row['contract'] = 'current_brain_turn_v5'
    del row['research']
    store.value = replace(store.value,brain_chat=(row,))
    assert saved_rows(store.value,'adv_owner')[0] == row
    assert brain.run(turn()).as_dict() == {**result,'replayed':True}
    assert len(model.calls) == 3


def test_lost_save_acknowledgement_does_not_repeat_research():
    brain, result, model, store, search = run(plan(), store=MemoryStore(lost_ack=True))
    assert result['replayed'] is True and store.commits == 1
    brain.run(turn(message=MIXED_MESSAGE))
    assert len(model.calls) == 4 and len(search.calls) == 1


@pytest.mark.parametrize('fail_first', [False, True])
def test_two_disputes_keep_independent_original_search_when_one_plan_is_missing(fail_first):
    message = 'The seller retained my deposit. A co-owner denied access to our shared shop.'
    descriptions = ['The seller retained the deposit.', 'A co-owner denied access to the shared shop.']
    proposal = {'disputes': [{'description': description, 'selections': [
        {'passage_id': f'current:p{index}', 'purpose':'support'}], 'uncertainty':None}
        for index, description in enumerate(descriptions,1)], 'objectives':[]}
    review = {'greeting':False, 'unit_reviews': [
        {'unit_id':f'dispute:{index}', 'verdict':'supported'} for index in (1,2)],
        'readings':{f'current:p{index}':[{'kind':'dispute','contribution':'reported',
            'description':description,'support_passage_ids':[f'current:p{index}'],
            'context_passage_ids':[],'uncertainty':None,'represented_by':[f'dispute:{index}']}]
            for index, description in enumerate(descriptions,1)}}
    model = WiredModel({'label':'information'}, proposal, review, plan())
    search, store = Search(), MemoryStore()
    normal = search.search
    def selective(queries):
        if fail_first and queries[0]['query_id'].startswith('dispute:1:'):
            raise OSError('First independent search unavailable')
        return normal(queries)
    search.search = selective
    brain = BrainService(store=store,model=model,legal_search=search,session_current=lambda:True)
    brain.run(turn(message=message))
    research = saved_rows(store.value,'adv_owner')[0]['research']
    assert research['state'] == 'partial' and len(model.calls) == 4
    assert set(research['searches']) == ({'dispute:2'} if fail_first else {'dispute:1','dispute:2'})
    assert set(research['failures']) == ({'dispute:1'} if fail_first else set())
    assert len(research['searches']['dispute:2']['queries']) == 1
    assert research['searches']['dispute:2']['queries'][0]['query_id'] == 'dispute:2:original'
