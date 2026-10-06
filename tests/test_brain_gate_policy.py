"""Pure gate declaration/diagnostic contracts; no current-owner wiring claim."""
import json
import re

import pytest

from nm.shared import gates_contracts as draft

NEW_IDS = {'G-CORE', 'G-EFFECT', 'G-INCOMPLETE', 'G-COMMIT'}


def test_candidate_unavailability_still_discloses_only_its_need():
    assert draft.gate('G-MODEL').scope is draft.Scope.NEED
    assert draft.gate('G-MODEL').response is draft.Response.DISCLOSE


@pytest.mark.parametrize('gate_id,state,response,scope', [
    ('G-CORE', 'unconfirmed', 'withhold', 'turn'),
    ('G-EFFECT', 'unsupported', 'withhold', 'need'),
    ('G-INCOMPLETE', 'unassessed', 'disclose', 'need'),
    ('G-INCOMPLETE', 'partial', 'disclose', 'need'),
    ('G-COMMIT', 'unconfirmed', 'withhold', 'turn'),
    ('G-COMMIT', 'failed', 'withhold', 'turn'),
])
def test_diagnostic_response_scope_and_invariant_come_from_one_authoritative_row(
        gate_id, state, response, scope):
    row = draft.gate(gate_id)
    diagnostic = draft.gate_diagnostic(gate_id, state)
    assert diagnostic == {'gate': gate_id, 'state': state, 'response': response,
                          'scope': scope, 'recovery': 'system',
                          'invariant': row.condition, 'reason': state}
    assert row.built is False  # This external draft is not an owner consultation.


@pytest.mark.parametrize('kwargs', [
    {'gate_id': 'PRIVATE_MATTER_TEXT', 'state': 'invalid'},
    {'gate_id': 'G-CORE', 'state': 'PRIVATE_MATTER_TEXT'},
    {'gate_id': ['PRIVATE_MATTER_TEXT'], 'state': 'invalid'},
    {'gate_id': 'G-CORE', 'state': ['PRIVATE_MATTER_TEXT']},
])
def test_diagnostic_refuses_undeclared_inputs_without_copying_them_into_exception(kwargs):
    with pytest.raises((ValueError, KeyError)) as error:
        draft.gate_diagnostic(**kwargs)
    assert 'PRIVATE_MATTER_TEXT' not in str(error.value)


def test_diagnostic_has_no_free_text_or_model_output_parameter():
    with pytest.raises(TypeError):
        draft.gate_diagnostic('G-CORE', 'invalid', reason='PRIVATE_MATTER_TEXT')


def test_short_gate_ids_round_trip_existing_document_and_trace_scanners():
    for gate_id in NEW_IDS:
        assert re.findall(r'\bG-[A-Z]+\b', gate_id) == [gate_id]
        assert re.findall(r'\bG-[A-Z]{3,}\b', gate_id) == [gate_id]
    ids = [row['id'] for row in draft.as_rows()]
    assert len(ids) == len(set(ids))
    assert NEW_IDS <= set(ids)


def test_withholding_scope_inventory_preserves_need_isolation_and_separates_wiring():
    turn_ids = {row.id for row in draft.withholding() if row.scope is draft.Scope.TURN}
    assert turn_ids == {'G-GROUND', 'G-ATTRIB', 'G-QUOTE', 'G-STALE', 'G-CORE', 'G-COMMIT'}
    need_ids = {row.id for row in draft.withholding() if row.scope is draft.Scope.NEED}
    assert need_ids == {'G-DATE', 'G-INFORCE', 'G-BINDING', 'G-EFFECT'}
    assert {row.id for row in draft.GATES if not row.built} == NEW_IDS
    assert json.loads(json.dumps(draft.as_rows())) == draft.as_rows()
