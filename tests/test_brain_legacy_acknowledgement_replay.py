"""A frozen historically sealed response replays across the rendering upgrade."""
import json
from pathlib import Path

from nm.brain import turn as boundary
from nm.shared.store_file_store import FileMatterStore, _matter


class NeverCallModel:
    def structured(self, *args, **kwargs):
        raise AssertionError('Replaying an already saved turn must make no model calls')


def test_actual_prior_renderer_seal_survives_new_renderer(tmp_path):
    fixture = json.loads((Path(__file__).parent /
                          'legacy_record_acknowledgement_3958da8.json').read_text())
    assert fixture['captured_from_commit'] == '3958da8'
    store = FileMatterStore(tmp_path, key='historical-renderer-replay-key')
    frozen = _matter(fixture['matter'])
    store.commit(frozen, expected_version=0)
    before = store.load(frozen.id)
    result = boundary.BrainService(store, NeverCallModel()).run(
        boundary.BrainTurn(**fixture['request'])).as_dict()
    assert result['elements'] == fixture['expected_elements']
    assert result['material_coverage']['execution'] == fixture['expected_execution']
    assert result['continuation'] == fixture['expected_continuation']
    request = result['material_coverage']['execution']['requests'][0]
    assert request['acknowledgement_delivery'] == 'code_only'
    assert 'acknowledgement_contract' not in request
    block = result['continuation']['units'][0]['blocks'][0]
    assert block['kind'] == 'completion'
    assert block['uncertainty'] == 'reported'
    assert store.load(frozen.id) == before
