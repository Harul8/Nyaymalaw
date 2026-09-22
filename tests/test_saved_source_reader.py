"""Saved citations are exact authorised releases, never a fresh source search."""
from __future__ import annotations

import copy
from dataclasses import asdict, replace

import pytest
from nm.core.grounding import verify
from nm.core.source_excerpt import capture
from nm.domain.answer import Answer, Element, ElementKind, Mode, Route
from nm.domain.source_excerpt import SourceExcerpt
from nm.domain.turn_receipt import answer_from_payload, answer_payload
from nm.edge.api import application

from tests.test_a_turn_receipt_is_not_an_archival_trace import _opened
from tests.test_turn_contract import finding

pytestmark = pytest.mark.class_a


def _answer(source=None):
    source = source or capture(finding())
    return Answer(route=Route.MATTER, mode=Mode.EXPLANATION,
                  mode_statement="Explain only.", elements=(Element(
                      kind=ElementKind.GROUND, text='Read the supplied passage.',
                      refs=(source.locator,), source=source),))


def _seed(client, sources=None):
    """Persist reader-specific text through the real encrypted matter store."""
    opened = _opened(client)
    store = application().store
    matter = store.load(opened['matter_id'])
    receipt = next(r for r in matter.turn_receipts if r.turn_id == opened['turn_id'])
    sources = sources or [capture(finding())]
    answer = replace(_answer(sources[0]), elements=tuple(
        Element(kind=ElementKind.GROUND, text="A material qualification remains.",
                refs=(s.locator,), source=s) for s in sources))
    updated = replace(receipt, answer=answer_payload(answer))
    store.commit(replace(matter, version=matter.version + 1,
                         turn_receipts=(updated,)), expected_version=matter.version)
    url = f"/api/matters/{matter.id}/turns/{receipt.turn_id}/sources/0"
    return url, sources


def test_actual_turn_saves_source_and_reopens_without_model_or_corpus(client, monkeypatch):
    out = _opened(client)
    rows = [(i, e) for i, e in enumerate(out['elements']) if e.get('source')]
    assert rows, 'a real served turn must capture at least one actual retrieved passage'
    i, element = rows[0]
    def forbidden(*args, **kwargs):
        raise AssertionError('source inspection initiated reasoning or retrieval')
    monkeypatch.setattr(application().engine, 'run', forbidden)
    restored = client.get(f"/api/matters/{out['matter_id']}/transcript").json()['turns']
    saved = next(r for r in restored if r['turn_id'] == out['turn_id'])
    assert saved['elements'][i]['source'] == element['source']
    response = client.get(f"/api/matters/{out['matter_id']}/turns/{out['turn_id']}/sources/{i}")
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    matter = application().store.load(out['matter_id'])
    receipt = next(r for r in matter.turn_receipts if r.turn_id == out['turn_id'])
    original = receipt.validated_answer().elements[i].source.text
    assert response.json()['text'] == original[:6000]
    assert 'text' not in element['source'] and 'namespace' not in element['source']
    assert response.json()['full_document_available'] is False


def test_same_labels_and_locators_in_different_namespaces_or_versions_stay_distinct(client):
    base = capture(finding())
    values = asdict(base)
    values.pop('digest')
    sources = [base, SourceExcerpt.capture(**{**values, 'namespace': 'another-act'}),
               SourceExcerpt.capture(**{**values, 'text': 'A later, different text.'})]
    url, _ = _seed(client, sources)
    rows = [client.get(url[:-1] + str(i)).json() for i in range(3)]
    assert len({r['digest'] for r in rows}) == 3
    assert [r['text'] for r in rows] == [s.text for s in sources]


def test_paging_keeps_every_unicode_character_and_whitespace(client):
    source = capture(finding(span=('First paragraph.\n\nन्याय — 原文  ' * 850)))
    url, _ = _seed(client, [source])
    parts, offset = [], 0
    while offset is not None:
        result = client.get(url, params={'offset': offset})
        assert result.status_code == 200
        page = result.json()
        assert len(page['text']) <= 6000 and page['offset'] == offset
        assert page['coverage'] == 'saved_passage'
        parts.append(page['text'])
        offset = page['next_offset']
    assert len(parts) > 2 and ''.join(parts) == source.text
    assert client.get(url, params={'offset': -1}).status_code == 416
    assert client.get(url, params={'offset': len(source.text)}).status_code == 416


def test_foreign_missing_and_unreleased_sources_are_not_disclosed(client):
    url, _ = _seed(client)
    stranger = client.sign_in('adv_reader_stranger', fresh=True)
    assert stranger.get(url).status_code == 404
    assert client.get(url.replace('receipt-opening', 'withheld-turn')).status_code == 404
    assert client.get(url[:-1] + '999').status_code == 404
    assert client.get(url[:-1] + '-1').status_code == 404
    client.post('/api/logout')
    assert client.get(url).status_code == 401


@pytest.mark.parametrize('field', ['text', 'locator', 'namespace', 'label', 'valid_from'])
def test_changed_snapshot_metadata_cannot_keep_an_old_digest(field):
    values = asdict(capture(finding()))
    values[field] += ' changed'
    with pytest.raises(ValueError, match='content identity'):
        SourceExcerpt(**values)


def test_an_invented_source_with_a_valid_digest_still_fails_grounding():
    original = finding()
    source = capture(finding(span='Invented words, not in the retrieved finding.'))
    report = verify(_answer(source), (), (original,))
    assert any('saved source excerpt' in v.detail for v in report.violations)
    assert verify(_answer(capture(original)), (), (original,)).clear


def test_wrong_reference_binding_is_refused():
    with pytest.raises(ValueError, match='exact reference'):
        Element(kind=ElementKind.GROUND, text='Source', refs=('wrong',),
                source=capture(finding()))


def test_old_receipts_decode_without_inventing_sources_and_unknown_keys_still_fail():
    value = answer_payload(_answer())
    value['elements'][0].pop('source')
    decoded = answer_from_payload(value)
    assert decoded.elements[0].source is None
    changed = copy.deepcopy(value)
    changed['elements'][0]['unapproved_source'] = 'made up'
    with pytest.raises(ValueError):
        answer_from_payload(changed)


def test_corrupt_source_receipt_fails_closed_at_the_reader(client, monkeypatch):
    url, _ = _seed(client)
    store = application().store
    matter = store.load(url.split('/')[3])
    damaged = copy.deepcopy(matter)
    damaged.turn_receipts[0].answer['elements'][0]['source']['text'] = 'altered'
    monkeypatch.setattr(store, 'load', lambda matter_id: damaged)
    assert client.get(url).status_code == 404
