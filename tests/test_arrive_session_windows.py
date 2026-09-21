"""User activity renews an access window; polling and uncertainty never do."""
from datetime import timedelta

import pytest

pytestmark = pytest.mark.class_a


def test_background_reads_cannot_keep_a_session_alive(client, monkeypatch):
    from nm.edge import api
    start = api.utcnow()
    clock = [start]
    monkeypatch.setattr(api, 'utcnow', lambda: clock[0])
    initial = client.get('/api/session').json()['access_window']['valid_until']
    for minute in (5, 10, 20, 29):
        clock[0] = start + timedelta(minutes=minute)
        result = client.get('/api/session')
        assert result.status_code == 200
        assert result.json()['access_window']['valid_until'] == initial
    clock[0] = start + timedelta(minutes=30)
    assert client.get('/api/session').status_code == 401
    assert client.get('/api/matters').status_code == 401
    assert client.post('/api/session/activity').status_code == 401


def test_user_activity_extends_idle_but_never_absolute_expiry(client, monkeypatch):
    from nm.edge import api
    start = api.utcnow()
    clock = [start]
    monkeypatch.setattr(api, 'utcnow', lambda: clock[0])
    before = client.get('/api/session').json()['access_window']
    for minute in range(29, 720, 29):
        clock[0] = start + timedelta(minutes=minute)
        response = client.post('/api/session/activity')
        assert response.status_code == 200, response.text
        window = response.json()['access_window']
        assert window['absolute_expires_at'] == before['absolute_expires_at']
        assert 0 < window['remaining_seconds'] <= 1800
    clock[0] = start + timedelta(hours=12)
    assert client.post('/api/session/activity').status_code == 401


def test_deleted_account_cannot_use_an_old_session_to_read_private_routes(client):
    identity = client.get('/api/session').json()['advocate']['id']
    client.directory._advocate_path(identity).unlink()
    for route in ('/api/session', '/api/matters', '/api/drafts/key', '/api/sessions'):
        assert client.get(route).status_code == 401, route


def test_unavailable_guessing_controls_refuse_before_deriving_password(client, monkeypatch):
    from nm.edge import api
    directory = api.application().directory
    monkeypatch.setattr(directory.inner, 'failures_since', lambda *args: None)
    def must_not_authenticate(*args):
        raise AssertionError('authentication ran without admission controls')
    monkeypatch.setattr(directory.inner, 'authenticate_and_open_session', must_not_authenticate)
    response = client.post('/api/login', json={'advocate_id': 'unknown', 'password': 'guess'})
    assert response.status_code == 503
    assert response.headers['retry-after'] == '60'


@pytest.mark.parametrize('contents', [b'bad row', b'not-a-date\ta\ts',
                                    b'2026-09-21T00:00:00\ta\ts', b'\xff'])
def test_corrupt_guess_counters_are_not_treated_as_zero_failures(client, contents):
    client.directory._attempts.write_bytes(contents)
    response = client.post('/api/login', json={'advocate_id': 'unknown', 'password': 'guess'})
    assert response.status_code == 503
    assert 'NOT RUNNING' in client.get('/api/health').json()['rate_limiting']


def test_failed_counter_write_never_reports_an_ordinary_bad_password(client, monkeypatch):
    from nm.ports.directory import AuthenticationUnavailable
    def fail_write(*args):
        raise AuthenticationUnavailable('synthetic write failure with internal details')
    monkeypatch.setattr(client.directory, 'note_failure', fail_write)
    response = client.post('/api/login', json={'advocate_id': 'unknown', 'password': 'guess'})
    assert response.status_code == 503
    assert 'internal details' not in response.text
    assert response.headers['retry-after'] == '60'


def test_one_selected_session_ends_without_ending_the_others(client):
    selected = client.sign_in(fresh=True)
    survivor = client.sign_in(fresh=True)
    row = next(s for s in selected.get('/api/sessions').json()['sessions'] if s['this_one'])
    result = client.post('/api/sessions/revoke-one', json={'reference': row['reference']})
    assert result.status_code == 200, result.text
    assert result.json()['outcome'] == 'closed'
    assert selected.get('/api/session').status_code == 401
    assert survivor.get('/api/session').status_code == 200
    assert client.get('/api/session').status_code == 200
    repeated = client.post('/api/sessions/revoke-one', json={'reference': row['reference']})
    assert repeated.json()['outcome'] == 'already_ended'


def test_device_description_is_recognisable_but_not_a_claim_of_location(client):
    from nm.edge import api
    assert api._client_label('Mozilla Windows Chrome/120 Safari/537 Edg/120') == 'Edge on Windows'
    assert api._client_label('Mozilla Android Chrome/120') == 'Chrome on Android'
    unknown = api._client_label('<script>secret device description</script>')
    assert unknown == 'Other browser or client'
    own = next(s for s in client.get('/api/sessions').json()['sessions'] if s['this_one'])
    assert own['client_label'] == 'Other browser or client'
    assert own['source'] == 'testclient'
    assert 'location' not in own


def test_current_foreign_and_unknown_references_cannot_end_another_account(client):
    from nm.domain.advocate import AdvocateIdentity, Enrolment, enrol, utcnow

    directory = client.directory
    foreign = 'foreign-session@example.test'
    directory.enrol(Enrolment(AdvocateIdentity(id=foreign, name='Synthetic Other'),
                              enrol('Synthetic-other-92!'), utcnow()))
    token = directory.open_session(foreign, 'foreign-device', utcnow())
    reference = directory.session(token, 'foreign-device', utcnow()).reference
    denied = client.post('/api/sessions/revoke-one', json={'reference': reference})
    unknown = client.post('/api/sessions/revoke-one', json={'reference': '0' * 64})
    assert denied.status_code == unknown.status_code == 404
    assert denied.json() == unknown.json()
    assert directory.session(token, 'foreign-device', utcnow()) is not None
    own = next(s for s in client.get('/api/sessions').json()['sessions'] if s['this_one'])
    assert client.post('/api/sessions/revoke-one',
                       json={'reference': own['reference']}).status_code == 409
    assert client.get('/api/session').status_code == 200


@pytest.mark.parametrize('contents', [b'broken', b'{}', b'[]'])
def test_unreadable_session_inventory_is_not_reported_as_complete(client, contents):
    directory = client.directory
    (directory._sessions / ('0' * 64 + '.nm')).write_bytes(contents)
    assert client.get('/api/sessions').status_code == 503
    assert client.post('/api/sessions/revoke').status_code == 503
    assert client.get('/api/session').status_code == 200


def test_expired_session_is_labelled_ended_without_read_refresh(client):
    from nm.domain.advocate import utcnow

    identity = client.get('/api/session').json()['advocate']['id']
    client.directory.open_session(identity, 'old-device', utcnow() - timedelta(hours=13))
    listed = client.get('/api/sessions').json()['sessions']
    expired = next(s for s in listed if s['device'] == 'old-device')
    assert not expired['live']
    assert 'expired' in expired['ended_because']


def test_interrupted_session_replacement_leaves_previous_record_intact(client, monkeypatch):
    from nm.adapters.store import directory as module

    selected = client.sign_in(fresh=True)
    row = next(s for s in selected.get('/api/sessions').json()['sessions'] if s['this_one'])
    replace_file = module.os.replace
    def fail_session_write(source, destination):
        if destination.parent == client.directory._sessions:
            raise OSError('synthetic storage failure')
        return replace_file(source, destination)
    monkeypatch.setattr(module.os, 'replace', fail_session_write)
    response = client.post('/api/sessions/revoke-one', json={'reference': row['reference']})
    assert response.status_code == 503
    assert 'could not be confirmed' in response.json()['detail']
    assert selected.get('/api/session').status_code == 200
    assert not list(client.directory._sessions.glob('*.tmp'))
