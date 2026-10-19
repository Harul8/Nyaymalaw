"""An opening records instructions, not fabricated parties or permissions."""
import pytest

from nm.app.api import application as _application

pytestmark = pytest.mark.class_a


def offer(**changes):
    return {"request_key": "durable-opening", "brief": {}, **changes}


def test_unknown_opening_is_a_saved_matter_without_a_clearance(client):
    result = client.post('/api/matters/intake', json=offer())
    assert result.status_code == 200, result.text
    row = result.json()
    assert row['title'] == 'New matter'
    matter = _application().store.load(row['matter_id'])
    assert matter.intake_parties == {}
    assert not matter.screens and not matter.facts and not matter.threads
    assert matter.intake_answers['capacity']['state'] == 'not_assessed'
    assert row['opening_brief']['state'] == 'recorded'
    assert not row['opening_brief']['establishes_facts']
    listed = client.get('/api/matters').json()['matters']
    assert any(m['matter_id'] == row['matter_id'] for m in listed)


def test_whole_opening_survives_storage_restart_before_a_message(client, tmp_path):
    from nm.shared.store_file_store import FileMatterStore
    from tests.test_turn_contract import KEY

    body = offer(title='Contract review', parties={'Synthetic Client': 'client'}, brief={
        'objective': 'Review the proposed obligations, not litigation.',
        'instructing': 'representative', 'instructor_name': 'Synthetic Director',
        'instructor_role': 'Director', 'authority_basis': 'Authority still to be checked',
        'proceedings': 'none', 'other_party_state': 'none_identified',
        'urgency': 'stated', 'reported_date': '2026-10-10',
        'date_source': 'Advocate-reported appointment, not a legal computation',
        'urgency_details': 'A review is requested before the appointment.',
    })
    result = client.post('/api/matters/intake', json=body)
    assert result.status_code == 200, result.text
    mid = result.json()['matter_id']
    restored = FileMatterStore(tmp_path, key=KEY).load(mid)
    record = restored.intake_answers['opening']
    assert record['by'] == 'adv_demo' and record['at']
    for key, value in body['brief'].items():
        assert record['answer'][key] == value
    assert restored.intake_answers['scope']['answer'] == body['brief']['objective']
    assert not restored.facts and not restored.screens
    assert client.get(f'/api/matters/{mid}').json()['opening_brief']['brief'] == record['answer']


def test_replay_compares_all_opening_fields_and_keeps_one_matter(client):
    body = offer(brief={'objective': 'Read the contract'})
    first = client.post('/api/matters/intake', json=body)
    assert first.status_code == 200
    repeat = client.post('/api/matters/intake', json=body)
    assert repeat.json()['matter_id'] == first.json()['matter_id']
    assert repeat.json()['version'] == first.json()['version']
    body['brief']['objective'] = 'Send the contract'
    assert client.post('/api/matters/intake', json=body).status_code == 409
    held = _application().store.load(first.json()['matter_id'])
    assert held.intake_answers['scope']['answer'] == 'Read the contract'


@pytest.mark.parametrize('brief', [
    {'urgency': 'clear'}, {'proceedings': True}, {'instructing': 'verified'},
    {'capacity': {'state': 'not_in_doubt', 'basis': ''}},
    {'urgency': 'none_reported', 'reported_date': '2026-10-10'},
    {'reported_date': '2026-02-30'}, {'scope': 'unsupported duplicate owner'},
    {'objective': 'x' * 4001}, {'instructor_name': 'An unnamed authority'},
    {'proceedings': 'none', 'case_reference': 'a reference'},
])
def test_malformed_or_contradictory_brief_creates_no_matter(client, brief):
    before = client.get('/api/matters').json()
    result = client.post('/api/matters/intake', json=offer(brief=brief))
    assert result.status_code == 422, result.text
    assert client.get('/api/matters').json() == before


def test_party_presence_does_not_silently_contradict_none_identified(client):
    result = client.post('/api/matters/intake', json=offer(
        parties={'Other Person': 'related'}, brief={'other_party_state': 'none_identified'}))
    assert result.status_code == 422


def test_another_account_cannot_read_or_change_the_opening(client):
    first = client.post('/api/matters/intake', json=offer(brief={'objective': 'Private marker'}))
    mid = first.json()['matter_id']
    client.sign_in('adv_other')
    assert client.get(f'/api/matters/{mid}').status_code == 404
    second = client.post('/api/matters/intake', json=offer())
    assert second.status_code == 200 and second.json()['matter_id'] != mid
    assert _application().store.load(mid).intake_answers['scope']['answer'] == 'Private marker'


@pytest.mark.parametrize('parties', [
    {' Same name': 'client', 'same NAME ': 'adverse'},
    {'Person': 'verified'},
])
def test_ambiguous_or_invented_party_roles_cannot_be_saved(client, parties):
    result = client.post('/api/matters/intake', json=offer(
        parties=parties, brief={'other_party_state': 'identified'}))
    assert result.status_code == 422
