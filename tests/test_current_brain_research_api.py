"""Research reaches the authenticated shipped HTTP boundary and stays private."""
from copy import deepcopy
from dataclasses import replace
import pytest

from nm.brain.turn import saved_rows
from nm.shared.model_port import ModelError
from tests.test_current_brain_app import Harness, WiredModel, MIXED_MESSAGE, mixed_outputs, assert_ok
from tests.test_current_brain_research_turn import Search, plan


def test_owned_context_reaches_search_and_reopens_without_extra_calls(tmp_path):
    from tests.test_brain_dispute_query_context import MESSAGE, context_outputs
    app = Harness(tmp_path, WiredModel(*context_outputs()))
    search = Search()
    app.application.legal_search = search
    try:
        first = assert_ok(app.post(MESSAGE))
        assert first['metrics']['llm_calls'] == 4 and 'research' not in first
        row = saved_rows(app.held(first['chat_id']), 'adv_wiring')[0]
        research = row['research']
        assert research['state'] == 'ready'
        assert research['planning']['contract'] == 'dispute_queries_v2'
        assert research['planning']['plans']['dispute:1']['queries'][0]['passage_ids'] == ['current:p1', 'current:p2']
        assert len(search.calls) == 2
        assert '[current advocate context] It is a privately managed institution.' in search.calls[0][0]['context']
        assert '[current advocate context] An intermediary completed the proposal.' in search.calls[1][0]['context']
        reopened = assert_ok(app.client.get('/api/chats/' + first['chat_id']))
        assert reopened['turns'][0]['elements'] == first['elements']
        assert 'research' not in reopened['turns'][0]
        assert assert_ok(app.post(MESSAGE)) == {**first, 'replayed': True}
        assert len(app.model.calls) == 4 and len(search.calls) == 2
    finally:
        app.client.close()


def test_authenticated_turn_searches_saves_and_reopens_without_exposing_private_work(tmp_path):
    app = Harness(tmp_path, WiredModel(*mixed_outputs(MIXED_MESSAGE), plan()))
    search = Search()
    app.application.legal_search = search
    try:
        first = assert_ok(app.post(MIXED_MESSAGE))
        assert first['metrics']['llm_calls'] == 4 and 'research' not in first
        row = saved_rows(app.held(first['chat_id']), 'adv_wiring')[0]
        assert row['research']['state'] == 'ready' and len(search.calls) == 1
        reopened = assert_ok(app.client.get('/api/chats/' + first['chat_id']))
        assert reopened['turns'][0]['elements'] == first['elements']
        assert 'research' not in reopened['turns'][0]
        assert assert_ok(app.post(MIXED_MESSAGE)) == {**first, 'replayed':True}
        assert len(app.model.calls) == 4 and len(search.calls) == 1
    finally:
        app.client.close()


def test_provider_failure_keeps_original_search_and_confirmed_input_through_http(tmp_path):
    app = Harness(tmp_path, WiredModel(*mixed_outputs(MIXED_MESSAGE), ModelError('Provider unavailable')))
    app.application.legal_search = Search()
    try:
        result = assert_ok(app.post(MIXED_MESSAGE))
        row = saved_rows(app.held(result['chat_id']), 'adv_wiring')[0]
        assert result['input_admitted'] and row['research']['state'] == 'partial'
        assert len(row['research']['searches']['dispute:1']['queries']) == 1
        assert assert_ok(app.client.get('/api/chats/' + result['chat_id']))['turn_count'] == 1
    finally:
        app.client.close()


@pytest.mark.parametrize('damage', ['source', 'context', 'segment', 'owner', 'contract'])
def test_malformed_durable_search_is_guarded_history_refusal_not_server_error(tmp_path, damage):
    app = Harness(tmp_path, WiredModel(*mixed_outputs(MIXED_MESSAGE), plan()))
    app.application.legal_search = Search()
    try:
        result = assert_ok(app.post(MIXED_MESSAGE))
        matter = app.held(result['chat_id'])
        rows = deepcopy(matter.brain_chat)
        research = rows[0]['research']
        candidate = research['searches']['dispute:1']['candidates'][0]
        if damage == 'source': candidate['source']['chunk_id'] = ''
        elif damage == 'context': candidate['context'] = []
        elif damage == 'segment': candidate['context']['segments'] = [None]
        elif damage == 'owner': research['searches']['dispute:other'] = research['searches'].pop('dispute:1')
        else: research['contract'] = 'future'
        app.store.commit(replace(matter, brain_chat=rows), expected_version=matter.version)
        assert app.client.get('/api/chats/' + result['chat_id']).status_code == 409
        replay = app.post(MIXED_MESSAGE)
        assert replay.status_code == 409 and len(app.model.calls) == 4
    finally:
        app.client.close()
