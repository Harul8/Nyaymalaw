"""Bounded local-only recall diagnostic; not a production search or quality gate.

Replay the three actually admitted enquiry texts to reconstruct pre-rerank pools,
then add one unchanged original message through the same lexical/vector legs.
No answer model, decomposition, reranking, index writing or historical code reuse.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
from nm.core_engine.retrieval import HybridSearcher, LEG_DEPTH, PER_QUERY_POOL, RRF_K

OUT = Path(__file__).resolve().parent
RESULT = OUT / 'original-account-recall-diagnostic.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fused(lexical, semantic):
    scores = {}
    for leg in (lexical, semantic):
        for rank, position in enumerate(dict.fromkeys(leg), 1):
            scores[position] = scores.get(position, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=lambda position: (-scores[position], position))[:PER_QUERY_POOL]


def main():
    if RESULT.exists():
        raise SystemExit('Diagnostic evidence exists; do not silently repeat.')
    live_path = OUT / 'live-served-capacity-remeasurement.json'
    retrieval_path = OUT / 'live-served-capacity-remeasurement-retrieval-1.json'
    live = read(live_path)
    context = json.loads(live['calls'][2]['user'])['original_context']
    research = read(retrieval_path)['research']
    expected = next(iter(research['searches'].values()))['corpus_revisions']
    assert all(value['corpus_revisions'] == expected for value in research['searches'].values())
    owned = [(work_id, query) for work_id, value in research['searches'].items() for query in value['queries']]
    assert len(owned) == 3, 'Keep this diagnostic bounded to its reviewed saved plan.'
    texts = tuple(query['text'] for _, query in owned) + (context['latest']['text'],)
    assert len(set(texts)) == len(texts)
    searcher = HybridSearcher.local(root=ROOT)
    before = {kind: collection.revision() for kind, collection in searcher.collections.items()}
    if before != expected:
        raise SystemExit('Corpus revision differs from saved live evidence; no search performed.')
    result = {
        'purpose': 'Independent exact original-account recall versus reconstructed saved enquiry pools',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'state': 'running', 'external_api_calls': 0, 'new_decomposition_calls': 0,
        'reranking_calls': 0, 'baseline_pool_status': 'Reconstructed raw legs, not originally recorded raw ranks',
        'saved_evidence': {live_path.name: digest(live_path), retrieval_path.name: digest(retrieval_path)},
        'original_context': context, 'saved_research': research,
        'retrieval_source_hash_before': digest(ROOT / 'nm/core_engine/retrieval.py'),
        'corpus_revisions_before': before, 'leg_depth': LEG_DEPTH, 'per_query_pool': PER_QUERY_POOL,
        'original_query': {'source_id': context['latest']['source_id'], 'text': texts[-1]},
        'collections': {},
        'limits': ['One synthetic first message, known prior case, not an unfamiliar quality evaluation.',
                   'No final ranking or answer review; candidate presence does not establish applicable law.',
                   'Rejected work remains rejected; this recall experiment does not satisfy missing work.',
                   'No accuracy or full-corpus recall denominator is inferred from pool size.'],
    }
    started = time.perf_counter()
    try:
        for kind, collection in searcher.collections.items():
            step = time.perf_counter()
            print(json.dumps({'kind': kind, 'phase': 'local_legs_started', 'query_count': len(texts)}), flush=True)
            semantic = collection.semantic_many(texts, LEG_DEPTH)
            lexical = [collection.lexical(text, LEG_DEPTH) for text in texts]
            baseline = {}
            for index, (work_id, query) in enumerate(owned):
                baseline.setdefault(work_id, []).append({
                    'query_id': query['query_id'], 'text': query['text'],
                    'lexical': lexical[index], 'semantic': semantic[index],
                    'fused_pool': fused(lexical[index], semantic[index]),
                })
            raw = set().union(*(set(leg) for leg in lexical[:-1]), *(set(leg) for leg in semantic[:-1]))
            pool = set().union(*(set(query['fused_pool']) for rows in baseline.values() for query in rows))
            actual_candidates = {candidate['position'] for value in research['searches'].values()
                                 for candidate in value['candidates'] if candidate['kind'] == kind}
            actual_context = {segment['position'] for value in research['searches'].values()
                              for candidate in value['candidates'] if candidate['kind'] == kind
                              for segment in candidate.get('context', {}).get('segments', [])}
            original_pool = fused(lexical[-1], semantic[-1])
            account_union = list(dict.fromkeys(lexical[-1] + semantic[-1]))
            rows = collection.read(account_union)
            original = {
                'lexical': lexical[-1], 'semantic': semantic[-1], 'fused_pool': original_pool,
                'new_vs_any_enquiry_leg': sorted(set(account_union) - raw),
                'new_fused_vs_enquiry_fused': [pos for pos in original_pool if pos not in pool],
                'new_fused_vs_saved_final_and_context': [pos for pos in original_pool if pos not in actual_candidates | actual_context],
                'rows': {str(pos): row for pos, row in rows.items()},
                'unread_positions': [pos for pos in account_union if pos not in rows],
            }
            result['collections'][kind] = {
                'baseline_work_legs': baseline, 'enquiry_raw_union': sorted(raw), 'enquiry_fused_union': sorted(pool),
                'actual_saved_final_positions': sorted(actual_candidates),
                'actual_saved_context_positions': sorted(actual_context),
                'account': original, 'seconds': round(time.perf_counter() - step, 3),
            }
            if collection.revision() != expected[kind]:
                raise RuntimeError('Corpus revision drifted during diagnostic.')
            RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'kind': kind, 'phase': 'local_legs_finished',
                'seconds': result['collections'][kind]['seconds'], 'enquiry_fused': len(pool),
                'account_fused': len(original_pool), 'new_fused': len(original['new_fused_vs_enquiry_fused']),
                'new_raw': len(original['new_vs_any_enquiry_leg'])}), flush=True)
        result['corpus_revisions_after'] = {kind: collection.revision() for kind, collection in searcher.collections.items()}
        result['retrieval_source_hash_after'] = digest(ROOT / 'nm/core_engine/retrieval.py')
        if result['corpus_revisions_after'] != before or result['retrieval_source_hash_after'] != result['retrieval_source_hash_before']:
            raise RuntimeError('Corpus or retrieval implementation changed; comparison is not admitted.')
        result['state'] = 'complete'
    except Exception as exc:
        result.update(state='failed', failure_type=type(exc).__name__, failure=str(exc))
        raise
    finally:
        result['seconds'] = round(time.perf_counter() - started, 3)
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'state': result['state'], 'seconds': result['seconds'], 'external_api_calls': 0}), flush=True)


if __name__ == '__main__':
    main()
