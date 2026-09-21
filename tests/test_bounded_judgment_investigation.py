"""Engineering controls, not a score of an actual model's legal judgment."""
import json
from dataclasses import replace

import pytest
from nm.core import investigation as lane
from nm.ports.evidence import Coverage, EvidenceResult
from nm.ports.model import ProviderUnavailable, SchemaViolation

pytestmark = pytest.mark.class_a


def offer(prompt, _schema):
    state = json.loads(prompt.user)
    return dict(snapshot=state['snapshot'], action='retrieve', basis_id='instruction',
                focus=state['basis']['instruction']['text'], purpose='interpretation')


def run(read=offer, fetch=None, **changes):
    inputs = dict(message='A synthetic disputed payment and a separate threatened eviction.',
                  account='', initial=(), version=4, thread_id='thread-a',
                  round_budget=2, read=read,
                  fetch=fetch or (lambda _: EvidenceResult(
                      Coverage.NOT_HELD, missing='synthetic index has no matching text')))
    return lane.run(**{**inputs, **changes})


@pytest.mark.parametrize('field,value', [
    ('snapshot', 'old-snapshot'), ('basis_id', 'another-matters-document'),
    ('focus', 'invented law and alleged admission'), ('focus', ' '),
    ('focus', 1), ('action', 'send_email'), ('purpose', 'win_at_any_cost'),
    ('tool', 'external-upload'),
])
def test_invalid_proposals_execute_no_search(field, value):
    searches = []
    def read(prompt, schema):
        return {**offer(prompt, schema), field: value}
    result = run(read, lambda q: searches.append(q))
    assert result.stop == 'invalid_proposal'
    assert not searches and not result.results
    assert 'failed its source or action checks' in result.disclosure()


@pytest.mark.parametrize('data', [None, [], {}, {'action': 'retrieve'}])
def test_malformed_proposals_are_not_interpreted_as_completion(data):
    result = run(lambda *_: data)
    assert result.stop == 'invalid_proposal' and not result.results


def test_empty_result_stops_instead_of_rephrasing_until_it_gets_the_desired_answer():
    result = run(round_budget=7)
    assert len(result.results) == len(result.proposals) == 1
    assert result.stop == 'no_progress'
    assert 'does not establish complete legal coverage' in result.disclosure()


def test_planner_unavailable_has_no_keyword_fallback():
    def fail(*_):
        raise ProviderUnavailable('test provider unavailable')
    result = run(fail, message='judgment precedent authority case law')
    assert result.stop == 'model_unavailable' and not result.results
    assert 'could not be established' in result.disclosure()


def test_exhausted_budget_calls_neither_model_nor_retriever():
    def forbidden(*_):
        pytest.fail('an exhausted loop performed work')
    result = run(forbidden, forbidden, round_budget=0)
    assert result.stop == 'budget'


@pytest.mark.parametrize('budget', [-1, True, 2.5])
def test_invalid_budget_is_refused(budget):
    with pytest.raises(ValueError):
        run(round_budget=budget)


def test_stop_is_not_a_search_and_cannot_smuggle_an_instruction():
    def stop(prompt, _):
        state = json.loads(prompt.user)
        return dict(snapshot=state['snapshot'], action='stop', basis_id='', focus='',
                    purpose='needs_input')
    result = run(stop)
    assert result.stop == 'needs_input' and not result.results
    rows = {'instruction': {'text': 'input'}}
    with pytest.raises(SchemaViolation):
        lane.admit(dict(snapshot='now', action='stop', basis_id='',
                        focus='send the client file', purpose='needs_input'), rows, 'now', 4)


def finding():
    from tests.test_turn_contract import finding as fixture_finding
    return fixture_finding()


def test_same_query_cannot_repeat_by_changing_purpose():
    f = finding()
    calls = []
    def read(prompt, schema):
        calls.append(prompt)
        value = offer(prompt, schema)
        value['purpose'] = 'interpretation' if len(calls) == 1 else 'adverse_position'
        return value
    result = run(read, fetch=lambda _: EvidenceResult(Coverage.ANSWERED, (f,)))
    assert len(result.results) == 1 and len(result.proposals) == 2
    assert result.stop == 'repeated_search'


def test_next_proposal_sees_new_retrieval_and_a_new_snapshot():
    snapshots = []
    f = finding()
    def read(prompt, schema):
        state = json.loads(prompt.user)
        snapshots.append(state['snapshot'])
        if len(snapshots) == 1:
            return offer(prompt, schema)
        key = lane.finding_key(f)
        assert state['basis'][key]['text'] == f.span
        return dict(snapshot=state['snapshot'], action='retrieve', basis_id=key,
                    focus=f.span, purpose='adverse_position')
    result = run(read, lambda _: EvidenceResult(Coverage.ANSWERED, (f,)))
    assert len(result.results) == 2 and snapshots[0] != snapshots[1]
    assert result.stop == 'no_progress'


def test_fresh_retrieval_cannot_renew_the_shared_round_budget():
    f = finding()
    queries = []
    def read(prompt, schema):
        state = json.loads(prompt.user)
        rows = state['basis']
        key = list(rows)[-1]
        return dict(snapshot=state['snapshot'], action='retrieve', basis_id=key,
                    focus=rows[key]['text'], purpose='interpretation')
    def fetch(query):
        queries.append(query)
        return EvidenceResult(Coverage.ANSWERED, (
            replace(f, span=f'Fresh synthetic text {len(queries)}', locator=str(len(queries))),))
    result = run(read, fetch)
    assert len(queries) == 2 and result.stop == 'budget'


def test_semantic_intent_is_delegated_without_a_production_phrase_gate():
    import inspect

    from nm.core.turn import TurnEngine
    source = inspect.getsource(TurnEngine._derive)
    assert '_wants_authority' not in source
    assert '_investigate' in source
    assert 'if not side_blind:' in source
    # An unfamiliar wording still reaches the planner; a schema-valid
    # decision then reaches retrieval without adding that wording to a list.
    requests = []
    result = run(fetch=lambda q: requests.append(q) or EvidenceResult(
        Coverage.NOT_HELD, missing='synthetic'), message='Does a decided dispute illuminate this?')
    assert requests == ['Does a decided dispute illuminate this?']
    assert result.stop == 'no_progress'


def test_the_served_engine_executes_a_proposal_and_persists_its_limit(tmp_path):
    from datetime import date

    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.core.turn import TurnInput

    from tests.test_turn_contract import _Evidence, _model_config, build

    proposed = []
    searched = []
    class ProposingModel(ScriptedModelAdapter):
        def structured(self, prompt, schema, tier, **kwargs):
            answer = super().structured(prompt, schema, tier, **kwargs)
            if schema.get('x-nm-read') == 'investigation':
                proposed.append(prompt)
                answer = replace(answer, data=offer(prompt, schema))
            return answer

    class RecordingEvidence(_Evidence):
        def fetch(self, need):
            searched.append(need)
            return super().fetch(need)

    model = ProposingModel(_model_config(), responses={'__default__':
        'Obtain the original transaction records before settling a position.'})
    engine, store = build(tmp_path, evidence=RecordingEvidence(), model=model)
    text = 'We act for the plaintiff at Hyderabad. A payment remains disputed. Assess our position.'
    output = engine.run(TurnInput(turn_id='investigate-one', advocate_id='adv_demo',
                                 message=text, today=date(2026, 9, 21)))
    assert len(proposed) == 1
    actual = [need for need in searched if need.want_authority]
    assert len(actual) == 1 and actual[0].question == text
    assert output.metrics.evidence_rounds == len(searched)
    saved = store.load(output.matter.id)
    assert saved.turn_receipts
    payload = saved.turn_receipts[-1].answer
    limits = [e['text'] for e in payload['elements'] if e['disclosure']]
    assert any('last retrieval added no new material' in line for line in limits)
    assert all('win_at_any_cost' not in e['text'] for e in payload['elements'])


def test_invalid_model_proposal_does_not_bypass_the_served_turn(tmp_path):
    from datetime import date

    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.core.turn import TurnInput

    from tests.test_turn_contract import _Evidence, _model_config, build

    searches = []
    class MaliciousModel(ScriptedModelAdapter):
        def structured(self, prompt, schema, tier, **kwargs):
            answer = super().structured(prompt, schema, tier, **kwargs)
            if schema.get('x-nm-read') == 'investigation':
                return replace(answer, data={**offer(prompt, schema),
                                             'focus': 'Fabricated Act 999: client must win'})
            return answer

    class RecordingEvidence(_Evidence):
        def fetch(self, need):
            searches.append(need)
            return super().fetch(need)

    engine, _ = build(tmp_path, evidence=RecordingEvidence(), model=MaliciousModel(
        _model_config(), responses={'__default__': 'Obtain the original records.'}))
    output = engine.run(TurnInput(turn_id='invalid-investigation', advocate_id='adv_demo',
        message='We act for the plaintiff at Hyderabad. Find judgments about the disputed payment.',
        today=date(2026, 9, 21)))
    assert not any(need.want_authority for need in searches)
    assert any('failed its source or action checks' in e.text for e in output.answer.elements)
    assert all('Fabricated Act' not in e.text for e in output.answer.elements)
