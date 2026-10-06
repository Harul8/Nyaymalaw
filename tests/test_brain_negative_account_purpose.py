"""Negative cache scope freshness against immutable original account references."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import requirements_state as candidate
from nm.brain.legal_requirements import EMPTY_READING_VERIFICATION
from tests.test_brain_research_account_purpose_reuse import _history
from tests.test_brain_research_semantic_reuse import _covered_read
from tests.test_brain_research_state import REVISION, append, matter, subject


def negative_history():
    file, subjects, original, _ = _history()
    turns = deepcopy(file.brain_chat)
    read = turns[-1]['response']['research_reads'][0]
    read['rows'] = []
    read['coverage'].update(checked_items=1, unread_items=0, withheld_items=1)
    return replace(file, brain_chat=turns), subjects, original, read


def project(file, subjects, current):
    return candidate.research_record(file, subjects=subjects,
        material_by_subject={row['id']: [] for row in subjects},
        corpus_revision=REVISION, source_treatments=current)


@pytest.mark.parametrize('role', ['examination_material', 'reported_party_position', 'uncertain'])
def test_negative_result_invalidates_only_consequential_original_role_change(role):
    file, subjects, original, read = negative_history()
    before = deepcopy(file.brain_chat)
    current = {'new-address': {**original['old-span'], 'content_role': role}}
    result = project(file, subjects, current)
    identity = subjects[0]['id']
    assert result['state'] == 'ok'
    assert result['reuse_allowed'][identity] is False
    assert result['coverage_by_subject'][identity]['account_purpose_freshness'] == 'changed'
    assert result['fingerprints'][identity] == read['fingerprint']
    assert result['by_subject'][identity] == []
    assert file.brain_chat == before


def test_negative_result_keeps_unchanged_purpose_despite_local_ids_reason_and_new_source():
    file, subjects, original, read = negative_history()
    current = {'remapped': {**original['old-span'], 'reason': 'Different exact explanation.'},
        'unrelated': {'turn_id':'new-turn', 'role':'advocate', 'quoted':'A new unrelated request.',
                      'content_role':'work_instruction', 'reason':'Fresh unrelated instruction.'}}
    result = project(file, subjects, current)
    identity = subjects[0]['id']
    assert result['reuse_allowed'][identity] is True
    assert result['coverage_by_subject'][identity]['account_purpose_freshness'] == 'current'
    assert result['fingerprints'][identity] == read['fingerprint']


@pytest.mark.parametrize('current', [None, {}, {'broken': {'turn_id':'absent'}}])
def test_negative_result_does_not_invent_missing_current_owner(current):
    file, subjects, _, _ = negative_history()
    result = project(file, subjects, current)
    identity = subjects[0]['id']
    assert result['reuse_allowed'][identity] is False
    assert result['coverage_by_subject'][identity]['account_purpose_freshness'] == 'unknown'


def test_owned_no_supplied_passages_receipt_stays_independent_of_account_roles():
    file, subjects, original, read = negative_history()
    turns = deepcopy(file.brain_chat)
    read = turns[-1]['response']['research_reads'][0]
    read['coverage'].pop('retrieved_coverage')
    read['coverage'].update(checked_items=0, withheld_items=0,
        semantic_extent='no_supplied_passages',
        empty_reading={'contract': EMPTY_READING_VERIFICATION, 'subject_id':subjects[0]['id'],
            'semantic_extent':'no_supplied_passages', 'outcome':'no_supplied_passages',
            'source_ids':[], 'sources':[], 'source_checks':[]})
    file = replace(file, brain_chat=turns)
    current = {'address':{**original['old-span'], 'content_role':'examination_material'}}
    result = project(file, subjects, current)
    assert result['reuse_allowed'][subjects[0]['id']] is True
    status = result['coverage_by_subject'][subjects[0]['id']]
    assert status['account_purpose_freshness'] == 'not_required'


def test_legacy_pure_law_negative_without_classified_account_scope_stays_reusable():
    file = matter()
    selected = subject(file)
    read = _covered_read(selected, rows=[])
    read['coverage'].update(checked_items=1, unread_items=0, withheld_items=1)
    result = project(append(file, [read]), (selected,), None)
    assert result['reuse_allowed'][selected['id']] is True
