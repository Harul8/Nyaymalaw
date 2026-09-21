"""Arrive: the served key boundary must not become an alternate login."""
import base64

import pytest
from nm.adapters.store.directory import FileDirectory

from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a


def test_draft_key_requires_a_current_device_bound_session(client):
    first = client.get('/api/drafts/key')
    assert first.status_code == 200
    assert first.headers['cache-control'] == 'no-store'
    assert len(base64.b64decode(first.json()['key'])) == 32
    assert first.json()['lifetime_hours'] == 72
    assert client.get('/api/drafts/key').json() == first.json()
    client.cookies.clear()
    assert client.get('/api/drafts/key').status_code == 401


def test_draft_key_survives_restart_but_is_separate_for_each_account_and_device(client):
    identity = client.get('/api/session').json()['advocate']['id']
    directory = client.directory
    one = directory.device_draft_key(identity, 'device-one')
    two = directory.device_draft_key(identity, 'device-two')
    assert one['key'] != two['key'] and one['namespace'] != two['namespace']
    restarted = FileDirectory(directory._root, key=KEY)
    assert restarted.device_draft_key(identity, 'device-one') == one
    stored = (directory._root / 'draft-keys' / (one['namespace'] + '.nm')).read_bytes()
    assert base64.b64decode(one['key']) not in stored
    with pytest.raises(ValueError):
        directory.device_draft_key('not-an-account@example.test', 'device-one')


def test_corrupt_protection_is_an_explicit_failure_not_a_new_key(client):
    one = client.get('/api/drafts/key').json()
    path = client.directory._root / 'draft-keys' / (one['namespace'] + '.nm')
    path.write_bytes(b'corrupt')
    # The failure must remain visible, not overwrite the only means of recovery.
    with pytest.raises(ValueError, match='unreadable'):
        client.directory.device_draft_key(
            client.get('/api/session').json()['advocate']['id'], client.cookies['nm_device'])
    assert path.read_bytes() == b'corrupt'
    response = client.get('/api/drafts/key')
    assert response.status_code == 503
    assert 'could not be opened' in response.json()['detail']
def test_protected_browser_storage_contract_runs_in_class_a():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which('node')
    assert node, 'Node.js is required to verify protected browser drafts; not assessed without it'
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/protected-drafts.test.cjs'],
                            cwd=root, capture_output=True, text=True, encoding='utf8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'tests 12' in result.stdout, 'the expected draft-control population was not executed'
