"""F-B-02. A correction of the opening details is recorded beside the original.

Owner direction, 28 September 2026: the matter board's edit icon opens the
opening form to correct details or add what was missing. The rules below hold
for every correction, whatever the field: the original is never overwritten,
each correction names who, when and what changed, a removed party stays in the
history, a stale form cannot write over newer details, a retry is one
correction, and the details now in force are read through one owner.
"""
import re
from pathlib import Path

import pytest

from nm.app.api import application as _application

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def _open(client, **brief):
    result = client.post('/api/matters/intake', json={
        'request_key': 'correction-opening', 'title': '',
        'parties': {'Dr. Supriya': 'client'},
        'brief': {'objective': 'Recover a hand loan', **brief}})
    assert result.status_code == 200, result.text
    return result.json()


def _correct(client, opened, *, key='fix-1', version=None, title='', parties=None, **brief):
    return client.post(f"/api/matters/{opened['matter_id']}/opening", json={
        'request_key': key, 'expected_version': opened['version'] if version is None else version,
        'title': title, 'parties': parties if parties is not None else {'Dr. Supriya': 'client'},
        'brief': {'objective': 'Recover a hand loan', **brief}})


def test_a_correction_sits_beside_the_original_and_says_who_when_and_what(client):
    opened = _open(client)
    before = _application().store.load(opened['matter_id'])
    result = _correct(client, opened, parties={'Dr. Supriya': 'client', 'Mr. Rohit': 'adverse'},
                      other_party_state='identified')
    assert result.status_code == 200, result.text
    body = result.json()
    assert body['state'] == 'opening_corrected'
    assert body['matter_id'] == opened['matter_id'], 'a correction never opens another matter'
    assert 'against: Mr. Rohit added' in body['changes']
    held = _application().store.load(opened['matter_id'])
    # THE ORIGINAL IS UNTOUCHED; the correction is a separate attributed record.
    assert held.intake_answers['opening'] == before.intake_answers['opening']
    assert held.intake_opening_offer == before.intake_opening_offer
    row = held.intake_answers['opening_amendments']['answer'][-1]
    assert row['by'] == 'adv_demo' and row['at']
    assert row['previous']['parties'] == {'Dr. Supriya': 'client'}
    assert held.intake_parties == {'Dr. Supriya': 'client', 'Mr. Rohit': 'adverse'}
    assert held.version == before.version + 1
    listed = {m['matter_id']: m for m in client.get('/api/matters').json()['matters']}
    assert listed[opened['matter_id']]['opponent'] == 'Mr. Rohit', 'the board reads the correction'


def test_a_removed_or_moved_party_stays_named_in_the_history(client):
    opened = _open(client)
    first = _correct(client, opened, parties={'Dr. Supriya': 'client', 'Mr. Rohit': 'adverse'},
                     other_party_state='identified').json()
    second = _correct(client, first, key='fix-2', parties={'Dr. Supriya': 'client'})
    assert second.status_code == 200, second.text
    assert 'against: Mr. Rohit removed' in second.json()['changes']
    held = _application().store.load(opened['matter_id'])
    assert 'Mr. Rohit' not in held.intake_parties
    history = held.intake_answers['opening_amendments']['answer']
    assert [row['request_key'] for row in history] == ['fix-1', 'fix-2']
    assert history[-1]['previous']['parties']['Mr. Rohit'] == 'adverse'


def test_a_form_read_before_the_file_moved_cannot_write_over_it(client):
    opened = _open(client)
    assert _correct(client, opened, stage='Notice sent').status_code == 200
    stale = _correct(client, opened, key='fix-stale', stage='Something else')
    assert stale.status_code == 409, stale.text
    held = _application().store.load(opened['matter_id'])
    assert [row['request_key'] for row in held.intake_answers['opening_amendments']['answer']] \
        == ['fix-1']


def test_a_retry_is_one_correction_and_a_reused_key_cannot_carry_other_details(client):
    opened = _open(client)
    first = _correct(client, opened, forum='City Civil Court, Hyderabad')
    again = _correct(client, opened, forum='City Civil Court, Hyderabad')
    assert first.status_code == again.status_code == 200
    assert again.json()['version'] == first.json()['version']
    changed = _correct(client, opened, forum='Another forum')
    assert changed.status_code == 409
    held = _application().store.load(opened['matter_id'])
    assert len(held.intake_answers['opening_amendments']['answer']) == 1


def test_saving_unchanged_details_records_nothing(client):
    opened = _open(client)
    result = _correct(client, opened)
    assert result.status_code == 200 and result.json()['state'] == 'opening_unchanged'
    held = _application().store.load(opened['matter_id'])
    assert 'opening_amendments' not in held.intake_answers
    assert held.version == opened['version']


def test_another_account_cannot_correct_the_opening(client):
    opened = _open(client)
    client.sign_in('adv_other')
    assert _correct(client, opened, stage='Hijack').status_code == 404


def test_the_details_in_force_reach_the_model_and_the_conversation(client):
    from nm.open_matter.opening_contracts import current_opening, instruction_context

    opened = _open(client)
    _correct(client, opened, proceedings='none')
    held = _application().store.load(opened['matter_id'])
    assert current_opening(held)['proceedings'] == 'none'
    context = instruction_context(held)
    assert '"proceedings": "none"' in context and 'proceedings: no proceedings' in context
    notes = client.get(f"/api/matters/{opened['matter_id']}/transcript").json()['opening_changes']
    assert notes and 'proceedings: no proceedings' in notes[0]['changes']


def test_no_module_reads_the_original_opening_answer_around_its_owner():
    """ONE READER. A caller reading the original record directly keeps acting
    on details the advocate has since corrected -- the population is every
    source file in the product, not the module where this was found."""
    owner = ROOT / 'nm' / 'open_matter' / 'opening_contracts.py'
    pattern = re.compile(r"intake_answers[^\n]*[\"']opening[\"']")
    offenders = [str(path.relative_to(ROOT)) for path in (ROOT / 'nm').rglob('*.py')
                 if path != owner and pattern.search(path.read_text(encoding='utf8'))]
    assert not offenders, f'read the opening through current_opening/recorded_brief: {offenders}'
