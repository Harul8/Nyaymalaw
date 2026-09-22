"""Synthetic retrieval controls: no external model, corpus or credentials."""
import sqlite3
from dataclasses import replace
from datetime import date

import pytest
from nm.adapters.evidence.corpus import EXAMINED_CEILING, CorpusEvidenceAdapter
from nm.adapters.search.authority import AuthorityIndexSearch, _fts_query
from nm.core import conversation, investigation
from nm.knowledge.manifest import Manifest
from nm.ports.evidence import (
    Coverage,
    EvidenceNeed,
    EvidenceResult,
    Treatment,
    TreatmentState,
)
from nm.ports.model import Prompt
from nm.ports.search import ResolutionState

from tests.test_bounded_judgment_investigation import offer, run
from tests.test_corpus_conformance import _withdraw
from tests.test_immutable_corpus_publication import _runtime_publication
from tests.test_turn_contract import finding

pytestmark = pytest.mark.class_a


def index(tmp_path, rows):
    path = tmp_path / 'authority.db'
    with sqlite3.connect(path) as con:
        con.execute('create virtual table paras using fts5(case_id, case_name, '
                    "court, year, para_type, chunk_id, text, tokenize='porter unicode61')")
        con.executemany('insert into paras values (?, ?, ?, ?, ?, ?, ?)', rows)
        con.execute('create table identity(key text, value text)')
        con.executemany('insert into identity values (?, ?)', [
            ('built_at', '2026-09-22'), ('source', 'synthetic'),
            ('corpus_version', 'synthetic-v1'), ('indexed_paragraphs', str(len(rows))),
            ('source_paragraphs', str(len(rows))), ('attributable_kinds', 'ratio'),
        ])
    return path


def row(case, text, number=1, kind='ratio'):
    return (case, f'{case} v respondent', 'Supreme Court of India', '2020',
            kind, f'{case}-p{number:04}', text)


def need(question='possession title'):
    return EvidenceNeed(question=question, governing_date=date(2025, 1, 1),
                        want_authority=True)


def evidence(tmp_path, rows):
    with sqlite3.connect(tmp_path / 'chunks.db') as con:
        con.execute('create table chunks(id text, text text)')
    return CorpusEvidenceAdapter(tmp_path, Manifest(entries=()),
                                 authority_index=index(tmp_path, rows))


@pytest.mark.parametrize('method,args', [
    ('search', ('possession',)), ('discover', ('possession',)),
    ('expand', ('c1',)), ('passage', ('p1',)),
    ('resolve', ('(2020) 1 SCC 1',)), ('treatment', ('c1',)),
    ('case_identity', ('c1',)),
])
@pytest.mark.parametrize('during', [False, True])
def test_every_read_refuses_a_withdrawn_source(tmp_path, monkeypatch, method, args, during):
    snapshot = _runtime_publication(tmp_path)
    search = AuthorityIndexSearch.from_published_snapshot(snapshot)
    assert search.expand('c1').paragraphs and search.passage('p1')
    # Identity fixtures need no second database: the sentinel proves dispatch
    # was suppressed, not merely that the fixture happened to have no case.
    monkeypatch.setattr(search._identity_index, 'case', lambda _: 'SENSITIVE CASE')
    monkeypatch.setattr(search._identity_index, 'treatment', lambda _: Treatment(
        TreatmentState.CLEAN, 'synthetic checked scope'))
    monkeypatch.setattr(type(search._identity_index), 'available', property(lambda _: True))
    monkeypatch.setattr(search._identity_index, 'case_for_citation', lambda _: 'c1')
    assert search.resolve('(2020) 1 SCC 1').state is ResolutionState.RESOLVED
    assert search.treatment('c1').state is TreatmentState.CLEAN
    assert search.case_identity('c1') == 'SENSITIVE CASE'
    if during:
        original = getattr(search, '_' + method, None)
        assert callable(original), f'{method} must use the common guarded read boundary'

        def withdraw_during(*a, **kw):
            result = original(*a, **kw)
            _withdraw(snapshot)
            return result

        monkeypatch.setattr(search, '_' + method, withdraw_during)
    else:
        _withdraw(snapshot)
    result = getattr(search, method)(*args)
    if method in {'search', 'discover', 'expand'}:
        assert result.coverage is Coverage.NOT_ASSESSED
        assert 'withdrawn' in result.why
    elif method == 'resolve':
        assert result.state is ResolutionState.INDEX_UNAVAILABLE
    elif method == 'treatment':
        assert result.state is TreatmentState.NOT_CHECKED
        assert 'withdrawn' in result.scope
    else:
        assert result is None


@pytest.mark.parametrize('identifier', ['c1', 'c1" OR case_id:"c2', 'c1 OR c2', 'c1:c2'])
def test_expansion_treats_case_identity_as_exact_data(tmp_path, identifier):
    search = AuthorityIndexSearch(index(tmp_path, [row('c1', 'possession'),
                                                  row('c2', 'possession')]))
    result = search.expand(identifier, query='possession')
    assert result.coverage is Coverage.ANSWERED
    assert {p.case_id for p in result.paragraphs} == ({'c1'} if identifier == 'c1' else set())


def test_discovery_really_reads_its_declared_candidate_pool(tmp_path):
    search = AuthorityIndexSearch(index(tmp_path, [row(f'c{i}', 'possession')
                                                  for i in range(201)]))
    result = search.discover('possession')
    assert result.paragraphs_ranked == 200
    assert len(search.search('possession', limit=10000).hits) == 100


@pytest.mark.parametrize('raw,expected', [
    ('part-performance', '"part" "performance"'),
    ('title/possession', '"title" "possession"'),
    ('s. 53A AND possession', '"53A" "possession"'),
])
def test_literal_search_does_not_join_separate_words(raw, expected):
    assert _fts_query(raw) == expected


def test_empty_and_unsearched_authority_queries_are_different(tmp_path):
    adapter = evidence(tmp_path, [row('c1', 'possession title')])
    result = adapter._fetch_authority(need('zirconium kryptonite'))
    assert result.coverage is Coverage.SEARCHED_NO_MATCH and not result.findings
    assert 'not' in result.search_note and 'corpus' in result.search_note
    assert adapter._fetch_authority(need('please')).coverage is Coverage.NOT_ASSESSED


def test_a_rejected_population_still_reports_the_bound(tmp_path):
    adapter = evidence(tmp_path, [row('c1', 'possession', i)
                                 for i in range(EXAMINED_CEILING + 1)])
    result = adapter._fetch_authority(need())
    assert result.coverage is Coverage.SEARCHED_NO_MATCH and not result.findings
    assert f'first {EXAMINED_CEILING}' in result.search_note
    assert str(EXAMINED_CEILING) in result.search_note


def test_correspondence_terms_cannot_be_lost_to_primary_query_length(monkeypatch):
    monkeypatch.setattr(CorpusEvidenceAdapter, '_corresponding_terms',
                        classmethod(lambda cls, _: ['verified', 'correspondence']))
    terms = CorpusEvidenceAdapter._terms(need(
        'possession title ownership execution transfer cancellation injunction damages notice'))
    assert {'verified', 'correspondence'} <= set(terms)


def test_keyword_matches_are_not_a_semantic_support_verdict(tmp_path, monkeypatch):
    adapter = evidence(tmp_path, [row('c1', 'possession title')])
    monkeypatch.setattr(adapter._citator, 'treatment', lambda *a, **kw: Treatment(
        TreatmentState.CLEAN, 'synthetic reviewed treatment'))
    result = adapter._fetch_authority(need())
    assert len(result.findings) == 1
    candidate = result.findings[0]
    assert candidate.supports is None and not candidate.usable and candidate.quotable
    assert 'not assessed' in candidate.blocking_reason
    assessed = replace(candidate, supports=True)
    assert assessed.usable
    assert not replace(candidate, supports=False).quotable


@pytest.mark.parametrize('bad', ['true', 1, [], {}])
def test_support_state_cannot_be_truthy_untyped_data(bad):
    with pytest.raises(ValueError, match='support'):
        replace(finding(), supports=bad)


@pytest.mark.parametrize('coverage', [Coverage.NOT_ASSESSED, Coverage.HELD_NOT_FOUND])
def test_failed_retrieval_is_not_reported_as_completed_research(coverage):
    result = run(offer, lambda _: EvidenceResult(coverage, missing='synthetic outage'))
    assert result.stop == 'retrieval_unavailable'
    assert 'could not' in result.disclosure()
    assert len(result.results) == 1


def test_prompt_carries_independent_checks_and_never_promotes_the_passage():
    candidate = replace(finding(), supports=None)
    prompt = conversation.with_evidence(Prompt(system='policy', user='question'), (candidate,))
    assert '"support_assessed": false' in prompt.user
    assert '"may_rely": false' in prompt.user
    assert candidate.span not in prompt.system
    rows = investigation.catalogue('question', '', (candidate,))
    data = rows[investigation.finding_key(candidate)]
    assert data['support_assessed'] is False
    assert data['treatment'] == candidate.treatment.state.value


def test_the_requested_provision_cannot_certify_its_own_retrieval():
    from nm.core import grounding

    from tests.test_grounding_gate import answer_of

    f = replace(finding(), proposition='What does section 999 say?')
    report = grounding.verify(answer_of('Apply under section 999.'), (f,), (f,))
    assert report.withholding and any('999' in v.detail for v in report.violations)


def test_search_notes_never_become_an_advocates_legal_decision(tmp_path):
    from nm.core.turn import TurnInput
    from nm.domain.matter import Thread
    from nm.domain.metrics import TurnMetrics

    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    thread = Thread.create('synthetic thread')
    candidate = replace(finding(), supports=None)
    from nm.ports.evidence import ParaKind, SourceKind
    candidate = replace(candidate, source_kind=SourceKind.AUTHORITY,
                        para_kind=ParaKind.ATTRIBUTABLE)
    result = EvidenceResult(Coverage.ANSWERED, (candidate,), search_note='Search was bounded.')
    grounds, decisions, relied = [], {}, []
    engine._read_coverage(result, thread, TurnMetrics('synthetic-turn'), grounds, relied,
                         turn=TurnInput(message='question', advocate_id='synthetic'),
                         concluded=decisions)
    assert not decisions and not relied
    assert any('not been assessed' in e.text for e in grounds)


def test_match_count_uses_the_index_tokenizer_not_substrings(tmp_path):
    adapter = evidence(tmp_path, [row('stemmed', 'courts executed agreements'),
                                 row('substring', 'agreements and nonexecution')])
    result = adapter._fetch_authority(need('execute agreement'))
    assert [f.locator.split('::')[0] for f in result.findings] == ['stemmed']
    assert result.findings[0].confidence == 1.0


def test_query_numbers_and_truncation_remain_visible(tmp_path):
    adapter = evidence(tmp_path, [row('c1', '53A possession title')])
    result = adapter._fetch_authority(need(
        '53A possession title ownership execution transfer cancellation injunction damages notice'))
    assert '53a' in adapter._terms(need('s.53A'))
    assert 'omitted 2' in result.search_note
    assert result.assumption is None


def test_a_corrupt_index_is_an_unavailable_search_not_an_exception(tmp_path):
    adapter = evidence(tmp_path, [])
    with sqlite3.connect(adapter._authority_db) as con:
        con.execute('drop table identity')
    result = adapter._fetch_authority(need())
    assert result.coverage is Coverage.NOT_ASSESSED and not result.findings


def test_exhausted_search_budget_never_claims_corpus_absence(tmp_path):
    from nm.core.turn import MAX_EVIDENCE_ROUNDS
    from nm.domain.metrics import TurnMetrics

    from tests.test_turn_contract import build

    engine, _ = build(tmp_path)
    metrics = TurnMetrics('synthetic', evidence_rounds=MAX_EVIDENCE_ROUNDS)
    result = engine._fetch(need(), metrics)
    assert result.coverage is Coverage.NOT_ASSESSED and metrics.evidence_bound_hit
    assert metrics.evidence_rounds == MAX_EVIDENCE_ROUNDS
