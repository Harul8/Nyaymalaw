"""The current document is separately identified; saved advice is immutable."""
from dataclasses import replace

import pytest
from nm.core.source_excerpt import capture, document_anchor
from nm.edge.api import application
from nm.ports.evidence import SourceDocument

from tests.test_saved_source_reader import _seed
from tests.test_turn_contract import finding

pytestmark = pytest.mark.class_a


def test_unique_anchor_preserves_original_whitespace_offsets():
    body = 'Header\n\nBefore. A\nretrieved   clause is retained. After.'
    start, length = document_anchor(body, 'A retrieved clause is retained.')
    assert body[start:start + length] == 'A\nretrieved   clause is retained.'
    assert document_anchor(body * 2, 'A retrieved clause is retained.') is None
    assert document_anchor(body, 'Invented words') is None


def test_document_paging_cannot_mix_generations_or_rewrite_saved_passage(client, monkeypatch):
    source = capture(finding(span='The exact words of the relied upon passage.'))
    url, _ = _seed(client, [source])
    held = SourceDocument('read', label='Current document', store='test',
                          snapshot_id='generation-one',
                          segments=(('Heading', 'Earlier material. ' * 700 + source.text),))
    evidence = application().evidence
    monkeypatch.setattr(evidence, 'document', lambda *args, **kwargs: held)
    first = client.get(url, params={'view': 'document'}).json()
    assert first['anchor_offset'] > 6000 and first['relied_on_matches']
    offset = first['anchor_offset'] // 6000 * 6000
    later = client.get(url, params={'view': 'document', 'offset': offset,
                       'document_identity': first['document_identity']})
    assert later.status_code == 200 and source.text in later.json()['text']
    held = replace(held, snapshot_id='generation-two', segments=(('Heading', 'Changed text.'),))
    assert client.get(url, params={'view': 'document', 'offset': 0,
                      'document_identity': first['document_identity']}).status_code == 409
    current = client.get(url, params={'view': 'document'}).json()
    assert current['anchor_offset'] is None and current['anchor_note']
    assert client.get(url).json()['text'] == source.text
    stranger = client.sign_in('adv_document_stranger', fresh=True)
    assert stranger.get(url, params={'view': 'document'}).status_code == 404
