"""Structural completeness is separate from source validity and semantic quality."""

import pytest

from nm.legal_brain.understand import dispute
from nm.legal_brain.common.quotable_contracts import Quotable
from nm.legal_brain.orchestrate.turn import TurnInput
from nm.shared.metrics_contracts import TurnMetrics
from nm.work_the_file.matter_contracts import Matter
from tests.test_matter_memory import _engine, _Recorder

pytestmark = pytest.mark.class_a


def test_pending_account_survives_clarification_and_is_not_a_new_instruction():
    from dataclasses import replace

    from nm.work_the_file.matter_contracts import Fact, Provenance, Thread
    old = Fact.create(statement='First event. Second event.',
                      provenance=Provenance(kind='advocate_statement', turn='earlier'))
    m = Matter.create(advocate_id='adv', title='File').with_fact(old)
    assert dispute.pending_accounts(m, 'now') == (old,)
    q = Quotable(turn='Work on the existing dispute.', file=old.statement)
    assert dispute.schema_for(q)['properties']['background']['items'][
        'enum'] == ['S1', 'S2', 'S3']
    data = answer(background=['S1', 'S2', 'S3'])
    data.update(focus_thread_id='held', focus_quote='First event.')
    assert dispute.interpret(q, data, thread_ids=frozenset({'held'})).refused
    t = replace(Thread.create(label='Held'), chronology=(old.id,))
    m = m.with_thread(t)
    assert not dispute.pending_accounts(m, 'now')
    # Repeated submission still has its own history, not another recovery job.
    m = m.with_fact(Fact.create(statement=old.statement,
        provenance=Provenance(kind='advocate_statement', turn='repeat')))
    assert not dispute.pending_accounts(m, 'now')


def test_recovered_spans_keep_the_original_turn_not_the_clarification(tmp_path):
    from nm.work_the_file.matter_contracts import Fact, Provenance
    engine, _ = _engine(tmp_path, _Recorder())
    old = Fact.create(statement='An earlier unpaid invoice.',
                      provenance=Provenance(kind='advocate_statement', turn='earlier'))
    m = Matter.create(advocate_id='adv', title='File').with_fact(old)
    turn = TurnInput(message='It is a separate dispute.', advocate_id='adv',
                     jurisdiction='Telangana')
    engine._read_dispute = lambda *args: dispute.DisputeRead(dispute.Dispute.OPENS,
        described=(dispute.Described(old.statement, 'Invoice', '', (turn.message,),
                                     allocation_unit_ids=('S1', 'S2')),))
    engine._admit_thread = lambda m, t, met, b, f, *_a, **_k: (m, b)
    m, bound = engine._admit_facts(m, turn, TurnMetrics(turn_id=turn.turn_id))
    assert not bound.blocks
    scoped = [f for f in m.facts if f.id in bound.thread.chronology]
    assert any(f.statement == old.statement and f.provenance.turn == 'earlier' for f in scoped)
    assert any(f.statement == turn.message and f.provenance.turn == turn.turn_id for f in scoped)


def test_opponent_correction_requires_current_exact_words_not_old_file():
    from nm.legal_brain.understand import posture
    text = 'I act for A. Our ownership opponent is B, not C; please correct C.'
    data = dict(states_client=True, role='prospective_claimant', role_basis='stated',
                client_described_as='A', opponent='B', quoted=text,
                opponent_correction_quote=text)
    assert posture.interpret(Quotable(turn=text), data).opponent_correction_quote == text
    old = posture.interpret(Quotable(turn='Continue.', file=text), data)
    invented = posture.interpret(Quotable(turn=text), {**data, 'opponent': 'Invented'})
    assert not old.opponent_correction_quote
    assert not invented.opponent_correction_quote


def test_premise_projection_never_calls_missing_rows_established():
    from dataclasses import replace

    from nm.work_the_file.matter_contracts import Thread
    from nm.work_the_file.projections_api import premises_projection
    t = replace(Thread.create(label='Unknown law'), premises=(
        {'kind': 'applicable_law', 'statement': '', 'basis': 'unestablished', 'source': ''},))
    m = Matter.create(advocate_id='adv', title='File').with_thread(t)
    out = premises_projection(m)
    assert out['state'] == 'not_assessed'
    assert out['threads'][0]['state'] == 'not_assessed'


def answer(*groups, background=(), instructions=(), belongs=None):
    """A dispute reading: each group is the sentence IDs of one dispute, of kind
    `other`, against nobody named -- placed `new` unless `belongs` puts it on the
    file."""
    belongs = belongs or {}
    return dict(client='', disputes=[
        dict(other_side='', contested=f'Dispute {i}', kind='other',
             on_file=belongs.get(i, 'new'), sentences=list(ids))
        for i, ids in enumerate(groups)],
        background=list(background), instructions=list(instructions), why='Inventory',
        focus_thread_id='', focus_quote='', advance_quote='', requirement_answers=[])


def test_existing_disputes_keep_their_ids_and_the_prompt_carries_the_principles_once():
    from nm.legal_brain.common.conversation import PRINCIPLES, guided
    from nm.work_the_file.matter_contracts import Thread

    a, b = Thread.create(label='First'), Thread.create(label='Second')
    q = Quotable(turn='One account. Another account.')
    assert guided(dispute.build_prompt(q)).system.count(PRINCIPLES) == 1
    read = dispute.interpret(q, answer(['S1'], ['S2'], belongs={0: a.id, 1: b.id}),
                             thread_ids=frozenset({a.id, b.id}))
    assert read.continues and [d.thread_id for d in read.described] == [a.id, b.id]


def test_new_work_beside_an_existing_dispute_opens_and_is_never_silently_dropped():
    from nm.work_the_file.matter_contracts import Thread

    a = Thread.create(label='Existing dispute')
    q = Quotable(turn='Existing debt. A separate access dispute. I act for A on both.')
    ids = frozenset({a.id})
    read = dispute.interpret(q, answer(['S1'], ['S2'], background=['S3'],
                                       belongs={0: a.id}), thread_ids=ids)
    assert not read.refused and read.opens and len(read.described) == 2
    dropped = answer(['S1'], background=['S3'], belongs={0: a.id})
    assert dispute.interpret(q, dropped, thread_ids=ids).refused, (
        "a reading that left the new work out was accepted as a continuation")
    forged = answer(['S1', 'S2'], background=['S3'], belongs={0: 'not-on-file'})
    assert dispute.interpret(q, forged, thread_ids=ids).refused


def test_literal_gate_calls_use_the_registered_vocabulary_across_the_product():
    import ast
    from pathlib import Path

    from nm.shared.gates_contracts import gate

    def inspect(source):
        seen, bad = [], []
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'fire' and len(node.args) >= 2
                    and all(isinstance(a, ast.Constant) and isinstance(a.value, str)
                            for a in node.args[:2]) and node.args[0].value.startswith('G-')):
                ident, state = (a.value for a in node.args[:2])
                seen.append((ident, state))
                if state not in gate(ident).states:
                    bad.append((ident, state))
        return seen, bad

    root = Path(__file__).resolve().parents[1] / 'nm'
    population = []
    for path in root.rglob('*.py'):
        seen, bad = inspect(path.read_text(encoding='utf-8-sig'))
        population.extend(seen)
        assert not bad, (path, bad)
    assert len(population) >= 50
    assert inspect('metrics.fire("G-GROUND", "matched", "unusable read")')[1]
    assert not inspect('metrics.fire("G-GROUND", "supported", "held source")')[1]


@pytest.mark.parametrize('value', [True, False, None])
def test_nullable_schema_types_do_not_crash_a_valid_factor_read(value):
    from nm.shared.model_port import SchemaViolation, require_schema

    schema = {'type': 'object', 'properties': {'held': {'type': ['boolean', 'null']}},
              'required': ['held']}
    require_schema({'held': value}, schema)
    with pytest.raises(SchemaViolation):
        require_schema({'held': 'unknown'}, schema)
    with pytest.raises(SchemaViolation):
        require_schema({'held': True}, {'type': 'object',
            'properties': {'held': {'type': 'integer'}}})


def test_live_research_and_checklist_schemas_restrict_sources_to_supplied_material():
    from jsonschema import ValidationError, validate

    from nm.legal_brain.retrieve import investigation
    from nm.legal_brain.reason import requirements

    rows = investigation.catalogue('Assess the supplied record.', 'A payment is disputed.', ())
    schema = investigation.schema_for(rows, 'snapshot')
    selector = next(k for k, v in investigation.focus_choices(rows).items()
                    if v['basis_id'] == 'account')
    data = dict(snapshot='snapshot', action='retrieve',
                focus=selector, purpose='interpretation')
    validate(data, schema)
    with pytest.raises(ValidationError):
        validate({**data, 'focus': 'Invented acknowledgment restarts time.'}, schema)
    passage = requirements.Passage('Retrieved provision', 'Some legal words in this passage.',
                                   'provision', 'source:1')
    req_schema = requirements.schema_for((passage,))
    assert req_schema['properties']['requirements']['items']['properties']['source']['enum'] == [
        'Retrieved provision']
    base = requirements.SCHEMA['properties']['requirements']['items']['properties']['source']
    assert 'enum' not in base


@pytest.mark.parametrize('count', [2, 3, 5])
def test_completely_omitted_paragraphs_are_named_without_guessing_their_meaning(count):
    spans = [f'The instructions for distinct subject {i}.' for i in range(count)]
    text = '\n\n'.join(spans)
    read = dispute.interpret(Quotable(turn=text), answer([f'S{count}']))
    assert read.refused == 'sentences not placed: ' + ', '.join(
        f'S{i}' for i in range(1, count))
    complete = dispute.interpret(Quotable(turn=text),
                                 answer(*[[f'S{i}'] for i in range(1, count + 1)]))
    assert not complete.refused and len(complete.described) == count


def test_rejected_candidate_cannot_certify_a_smaller_inventory():
    text = 'The first instruction. The second instruction.'
    read = dispute.interpret(Quotable(turn=text), answer(['S1'], ['S9']))
    assert read.refused
    assert read.found == ('Dispute 0',) and not read.described, (
        "what a refused reading had found before the bad label must be shown, not certified")
    assert not read.continues


def test_source_ids_copy_exact_words_including_quotes_without_model_transcription():
    text = 'I act for A on both claims.\n\nA wrote: “not yet”.\n\nB withheld payment.'
    result = dispute.interpret(Quotable(turn=text), answer(['S2'], ['S3'], background=['S1']))
    assert result.opens and not result.refused
    assert result.described[0].spans == ('I act for A on both claims.', 'A wrote: “not yet”.')
    assert result.described[1].spans == ('I act for A on both claims.', 'B withheld payment.')


@pytest.mark.parametrize('ids', [['S999'], ['S1'], [None]])
def test_source_ids_refuse_unknown_ids_or_omitted_units_even_in_one_paragraph(ids):
    assert dispute.interpret(Quotable(turn='First instruction. Second instruction.'),
                             answer(ids)).refused


def test_the_label_contract_requires_every_source_unit_and_real_ids():
    from jsonschema import ValidationError, validate
    q = Quotable(turn='Shared instruction. First dispute. Second dispute.')
    data = answer(['S2'], ['S3'], background=['S1'])
    validate(data, dispute.schema_for(q))
    read = dispute.interpret(q, data)
    assert read.opens and not read.refused and len(read.described) == 2
    assert read.described[0].spans == ('Shared instruction.', 'First dispute.')
    assert read.described[1].spans == ('Shared instruction.', 'Second dispute.')
    for mutation in (answer(['S2'], background=['S1']),
                     answer(['S2'], ['S3']),
                     answer(['S2'], ['S3'], background=['S1'], belongs={1: 'elsewhere'})):
        assert dispute.interpret(q, mutation).refused
    with pytest.raises(ValidationError):
        validate(answer(['S2'], ['S4'], background=['S1']), dispute.schema_for(q))


def test_repair_outage_keeps_refusal_instead_of_falling_back_to_partial_admission(tmp_path):
    from nm.shared.model_port import ModelError, ModelResult, Usage
    engine, _ = _engine(tmp_path, _Recorder())
    calls = []

    def read(prompt, schema, key, tier):
        calls.append(prompt)
        if len(calls) == 2:
            raise ModelError('temporarily unavailable')
        return ModelResult(text=None, tier=tier, data=answer(['S2']),
                           model='controlled', provider='scripted',
                           usage=Usage(0, 0, 0), latency_ms=0)

    engine._read = read
    result = engine._read_dispute(Matter.create(advocate_id='adv', title='File'),
        TurnInput(message='The first subject.\n\nThe second subject.', advocate_id='adv',
                  jurisdiction='Telangana'), TurnMetrics(turn_id='t'))
    assert len(calls) == 2 and result.refused


def test_shared_background_reaches_every_dispute_and_instructions_reach_none():
    shared = 'I act for the company on both proposed claims. No proceedings exist.'
    a, b = 'Payment on contract A is withheld.', 'The equipment on contract B was not returned.'
    ask = 'Please assess both.'
    text = '\n\n'.join((shared, a, b, ask))
    read = dispute.interpret(Quotable(turn=text),
                             answer(['S3'], ['S4'], background=['S1', 'S2'], instructions=['S5']))
    assert not read.refused
    assert all('I act for the company on both proposed claims.' in d.spans
               and 'No proceedings exist.' in d.spans for d in read.described)
    assert b not in read.described[0].spans and a not in read.described[1].spans
    assert all(ask not in d.spans for d in read.described) and read.instructions == (ask,)


@pytest.mark.parametrize('repair_succeeds', [True, False])
def test_production_read_repairs_once_or_reports_incomplete(tmp_path, repair_succeeds):
    from nm.shared.model_port import ModelResult, Usage

    text = 'The first subject.\n\nThe second subject.'
    engine, _ = _engine(tmp_path, _Recorder())
    calls = []

    def read(prompt, schema, key, tier):
        calls.append(prompt)
        data = (answer(['S1'], ['S2'])
                if len(calls) == 2 and repair_succeeds else answer(['S2']))
        return ModelResult(text=None, tier=tier, data=data, model='controlled', provider='scripted',
                           usage=Usage(0, 0, 0), latency_ms=0)

    engine._read = read
    result = engine._read_dispute(Matter.create(advocate_id='adv', title='File'),
        TurnInput(message=text, advocate_id='adv', jurisdiction='Telangana'),
        TurnMetrics(turn_id='t'))
    assert len(calls) == 2
    assert 'sentences not placed: S1' in calls[1].user
    assert bool(result.refused) is not repair_succeeds
    if repair_succeeds:
        assert len(result.described) == 2


def test_failed_inventory_never_admits_a_subset_as_a_complete_matter(tmp_path):
    engine, _ = _engine(tmp_path, _Recorder())
    engine._read_dispute = lambda *args: dispute.DisputeRead(
        dispute.Dispute.CANNOT_TELL, refused='incomplete inventory')
    m = Matter.create(advocate_id='adv', title='File')
    turn = TurnInput(message='Keep the whole brief.', advocate_id='adv', jurisdiction='Telangana')
    m, bound = engine._admit_facts(m, turn, TurnMetrics(turn_id='t'))
    assert bound.blocks and not m.threads
    assert any(f.statement == turn.message for f in m.facts)


def test_unavailable_first_inventory_cannot_silently_create_one_dispute(tmp_path):
    from nm.shared.model_port import ModelError
    engine, _ = _engine(tmp_path, _Recorder())
    def unavailable(*args):
        raise ModelError('unavailable')
    engine._read = unavailable
    matter = Matter.create(advocate_id='adv', title='File')
    turn = TurnInput(message='A payment dispute. A separate equipment dispute.',
                     advocate_id='adv', jurisdiction='Telangana')
    saved, bound = engine._admit_facts(matter, turn, TurnMetrics(turn_id='t'))
    assert bound.blocks and not saved.threads
    assert any(f.statement == turn.message for f in saved.facts)


def test_fixed_inventory_metadata_never_reaches_the_provider():
    from nm.shared.model_port import on_the_wire
    data = {'x-nm-read': 'dispute', 'x-nm-fixed-inventory': [{'thread_id': 'a'}],
            'type': 'object', 'properties': {}}
    wire = on_the_wire(data)
    assert wire == {'type': 'object', 'properties': {}}
    assert 'x-nm-fixed-inventory' in data


def test_rent_route_is_specific_and_all_causes_have_definitions():
    from nm.legal_brain.retrieve.resolution_sources import article_for
    from nm.work_the_file.matter_contracts import CAUSE_MEANS, CauseOfAction

    assert set(CAUSE_MEANS) == set(CauseOfAction) - {CauseOfAction.NOT_ESTABLISHED}
    edge = article_for(CauseOfAction.ARREARS_OF_RENT)
    assert edge.provision == 'Article_52'
    assert 'indiacode.nic.in' in edge.curated_from
    assert 'each' in edge.accrues_on
    assert article_for(CauseOfAction.BREACH_OF_CONTRACT).provision == 'Article_55'


def test_ambiguous_new_work_asks_about_proposals_not_a_nonexistent_board_control():
    from nm.legal_brain.understand.threading import bind
    from nm.work_the_file.matter_contracts import Fact, Provenance, Thread
    m = Matter.create(advocate_id='adv', title='File').with_thread(Thread.create(label='Existing'))
    message = 'Additional claim A. Additional claim B.'
    fact = Fact.create(statement=message,
                       provenance=Provenance(kind='advocate_statement', turn='test'))
    result = bind(m, message, fact, described=(
        dispute.Described('Additional claim A.', 'A'),
        dispute.Described('Additional claim B.', 'B')))
    assert result.blocks
    assert 'A; B' in result.question and 'Should I add' in result.question
    assert 'Please choose the dispute on the board' not in result.question


def test_cross_dispute_claims_require_attributed_distinct_premises():
    from nm.legal_brain.reason.adversarial import read_exposures
    positions = ({'thread': 'a', 'facts': [{'id': 'f1', 'statement': 'The debt remains due.'}]},
                 {'thread': 'b', 'facts': [
                     {'id': 'f2', 'statement': 'The debt was fully repaid.'}]})
    row = dict(from_thread='a', to_thread='b', what='Accounts conflict',
               consequence='Reconcile the same debt before relying on either account',
               from_fact='f1', to_fact='f2', from_quote='The debt remains due.',
               to_quote='The debt was fully repaid.')
    assert read_exposures({'exposures': [row]}, ('a', 'b'), positions)
    for changed in ({'to_fact': 'f1'}, {'to_quote': 'Invented words'}, {'from_fact': ''}):
        assert read_exposures({'exposures': [{**row, **changed}]}, ('a', 'b'), positions) is None
    assert read_exposures({'exposures': []}, ('a', 'b'), positions) == ()


def test_opposition_legal_argument_cannot_be_generated_with_no_retrieved_law(tmp_path):
    from types import SimpleNamespace

    from nm.work_the_file.matter_contracts import Thread
    engine, _ = _engine(tmp_path, _Recorder())
    engine._read = lambda *a: pytest.fail('No legal basis should mean no legal attack generation')
    out = engine._attacks(TurnInput(advocate_id='adv', message='Assess this.'),
                         Thread.create(label='Claim'), SimpleNamespace(account='Allegations only.'),
                         TurnMetrics(turn_id='t'), sources=())
    assert len(out) == 1 and out[0].disclosure and 'not yet been retrieved' in out[0].text


def test_consistency_refusal_never_republishes_the_rejected_candidate(client, monkeypatch):
    from dataclasses import replace

    from nm.app.api import application
    from nm.legal_brain.verify.consistency import Verdict
    from tests.test_a_withheld_turn_commits_no_conclusion import BRIEF

    engine = application().engine
    candidate = "The opponent's account remains disputed."
    real_complete = engine._model.complete
    def complete(prompt, tier, **kwargs):
        answer = real_complete(prompt, tier, **kwargs)
        if 'single next step' in prompt.user.lower():
            return replace(answer, text=candidate)
        return answer
    monkeypatch.setattr(engine._model, 'complete', complete)
    examined = []
    def contradict(text, *args, **kwargs):
        examined.append(text)
        return text, Verdict(claim_id='side', quoted=candidate, why='controlled refusal')
    monkeypatch.setattr(engine, '_consistent_step', contradict)
    response = client.post('/api/turn', json={'message': BRIEF})
    assert response.status_code == 200, response.text
    elements = response.json()['elements']
    assert candidate in examined, 'The controlled candidate never reached the check'
    refusal = [e for e in elements if 'I withheld the next step' in e['text']]
    assert len(refusal) == 1, elements
    assert candidate not in refusal[0]['text']
    assert not any(e['kind'] == 'action' for e in elements)


def test_consistency_instructions_preserve_independent_adverse_analysis():
    from nm.legal_brain.verify.consistency import SYSTEM
    assert "not advising the opponent" in SYSTEM
    assert "not merely discussing material that may hurt our client" in SYSTEM


def test_inventory_contract_recognises_reorganisation_without_erasing_history():
    assert 'not merely add detail' in dispute.SYSTEM
    assert 'do not report the unchanged inventory as the split' in dispute.SYSTEM
    assert 'does not establish facts or erase prior records' in dispute.SYSTEM


def test_research_selectors_preserve_quoted_unicode_text_and_refuse_cross_source():
    import json

    from nm.legal_brain.retrieve import investigation
    from nm.legal_brain.retrieve.evidence_port import Coverage, EvidenceResult

    text = 'The witness wrote "payment disputed" — not an admission.'
    searches = []
    def choose(prompt, schema):
        state = json.loads(prompt.user)
        chosen = next(k for k, v in state['focus_choices'].items()
                      if v['basis_id'] == 'instruction')
        assert all('"' not in v for v in schema['properties']['focus']['enum'])
        return dict(snapshot=state['snapshot'], action='retrieve',
                    focus=chosen, purpose='interpretation')
    args = dict(message=text, account='Another account.', initial=(), version=1,
                thread_id='a', round_budget=1, read=choose,
                fetch=lambda q: searches.append(q) or EvidenceResult(
                    Coverage.NOT_HELD, missing='No matching judgment in the test corpus'))
    investigation.run(**args)
    assert searches == [text]
    searches.clear()
    def wrong_basis(prompt, schema):
        return {**choose(prompt, schema), 'basis_id': 'account'}
    result = investigation.run(**{**args, 'read': wrong_basis})
    assert result.stop == 'invalid_proposal' and not searches


def test_accrual_receives_undated_exclusions_as_well_as_selectable_dates(tmp_path):
    from datetime import date

    from nm.legal_brain.reason import accrual
    from nm.work_the_file.matter_contracts import Fact, Provenance

    dated = Fact.create(statement='A disputed event.', date=date(2026, 8, 5),
                        provenance=Provenance(kind='advocate_statement', turn='old'))
    context = 'The relevant denial date is unknown. This event is a different dispute.'
    prompt = accrual.build_prompt('The controlling trigger', [dated], context=context)
    assert dated.id in prompt.user and context in prompt.user
    recorder = _Recorder()
    engine, _ = _engine(tmp_path, recorder)
    engine._read_accrual('The controlling trigger', [dated], TurnMetrics(turn_id='t'),
                         context=context)
    assert any(context in p.user for p in recorder.prompts)
