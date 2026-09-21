"""Actual account/HTTP and dispatch boundaries; fake provider, zero paid calls."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from nm.adapters.model.openai_adapter import OpenAIModelAdapter
from nm.adapters.store.directory import FileDirectory
from nm.bootstrap.model_permission import require_permission, text_policy
from nm.core.duty import DUTY_SCHEMA
from nm.domain.advocate import utcnow
from nm.domain.egress import DataClass, EgressRefused, Route, Sink, refuse
from nm.domain.external_ai import NOTICE_VERSION, ModelPermission, ModelPermissionRefused
from nm.edge import api
from nm.ports.directory import AuthenticationUnavailable
from nm.ports.model import Prompt, RateLimited, Tier

from tests.registration import CONSENT
from tests.test_model_port_contract import _config, _FakeOpenAI
from tests.test_public_email_registration import EMAIL, _login, _register
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a


def choice(client, accepted=True, version=0, **extra):
    return client.post('/api/account/model-permission', json={
        'accepted': accepted, 'notice_version': NOTICE_VERSION,
        'expected_version': version, **extra})


def test_confirmation_preserves_explicit_registration_permission(client):
    client.cookies.clear()
    assert _register(client, consent={**CONSENT, 'external_ai': True,
                     'external_ai_notice_version': NOTICE_VERSION}).status_code == 200
    row = client.directory.model_permission(EMAIL)
    assert row and row.permits(EMAIL, utcnow()) and row.version == 1
    blob = json.loads(client.directory._advocate_path(EMAIL).read_text(encoding='utf8'))
    assert isinstance(blob['model_permission'], str)
    assert NOTICE_VERSION not in blob['model_permission'], 'permission not sealed'
    assert _login(client).status_code == 200
    assert client.get('/api/account/model-permission').json()['accepted'] is True


@pytest.mark.parametrize('external,version', [
    ('true', NOTICE_VERSION), (1, NOTICE_VERSION), (True, None),
    (True, 'old'), (False, NOTICE_VERSION),
])
def test_registration_cannot_imply_permission(client, external, version):
    client.cookies.clear()
    result = _register(client, consent={**CONSENT, 'external_ai': external,
                       'external_ai_notice_version': version})
    assert result.status_code == 422
    assert client.directory.identity(EMAIL) is None


def test_existing_account_and_own_matters_remain_available_without_permission(client):
    assert client.get('/api/account/model-permission').json() == {
        'notice_version': NOTICE_VERSION, 'accepted': False, 'version': 0, 'recorded_at': None}
    opened = client.post('/api/matters/intake', json={
        'request_key': 'no-external-permission', 'title': 'Own synthetic matter'})
    assert opened.status_code == 200, opened.text
    assert client.get('/api/matters/' + opened.json()['matter_id']).status_code == 200
    assert client.directory.model_permission('adv_demo') is None


def test_permission_survives_restart_withdrawal_and_stale_tab_cannot_regrant(client, tmp_path):
    assert choice(client).json()['accepted'] is True
    assert FileDirectory(tmp_path, key=KEY).model_permission('adv_demo').accepted
    assert choice(client, False, 1).json()['accepted'] is False
    assert choice(client, True, 1).status_code == 409
    current = client.directory.model_permission('adv_demo')
    assert current.version == 2 and not current.accepted
    assert choice(client, True, 2).json()['version'] == 3


def test_identity_csrf_and_shape_are_enforced(client):
    assert choice(client, account_id='another').status_code == 422
    assert choice(client, version=True).status_code == 422
    assert choice(client, notice_version='old').status_code == 422
    assert client.post('/api/account/model-permission', headers={'X-NM-CSRF': 'wrong'},
        json={'accepted': True, 'notice_version': NOTICE_VERSION,
              'expected_version': 0}).status_code == 403
    other = client.sign_in('other', fresh=True)
    assert choice(other).status_code == 200
    assert client.directory.model_permission('adv_demo') is None
    assert client.directory.model_permission('other').account_id == 'other'
    client.cookies.clear()
    assert client.get('/api/account/model-permission').status_code == 401


@pytest.mark.parametrize('corruption', ['bytes', 'copied_account', 'plaintext', 'null'])
def test_corrupt_or_copied_permission_never_grants_or_blocks_sign_in(client, corruption):
    assert choice(client).status_code == 200
    path = client.directory._advocate_path('adv_demo')
    blob = json.loads(path.read_text(encoding='utf8'))
    if corruption == 'copied_account':
        client.sign_in('other', fresh=True)
        path = client.directory._advocate_path('other')
        other = json.loads(path.read_text(encoding='utf8'))
        other['model_permission'] = blob['model_permission']
        blob = other
        actor = 'other'
    else:
        blob['model_permission'] = {'bytes': 'corrupt', 'plaintext': {'accepted': True},
                                    'null': None}[corruption]
        actor = 'adv_demo'
    path.write_text(json.dumps(blob), encoding='utf8')
    with pytest.raises(AuthenticationUnavailable):
        client.directory.model_permission(actor)
    assert client.directory.authenticate(actor, 'Fixture-password-not-a-secret-1')
    with pytest.raises(ModelPermissionRefused):
        require_permission(client.directory, actor, _config())


@pytest.mark.parametrize('alteration', ['old_notice', 'future', 'withdrawn'])
def test_current_attributed_acceptance_is_required(client, alteration):
    assert choice(client).status_code == 200
    now = utcnow()
    row = client.directory.model_permission('adv_demo')
    changed = {'old_notice': replace(row, notice_version='old'),
               'future': replace(row, recorded_at=now + timedelta(days=1)),
               'withdrawn': replace(row, accepted=False)}[alteration]
    assert not changed.permits('adv_demo', now)
    assert not row.permits('another', now)


def bound(client, transport=None, config=None):
    application = api.application()
    application.config = config or _config()
    transport = transport or _FakeOpenAI('Synthetic acknowledged')
    application._model_adapter = OpenAIModelAdapter(application.config, client=transport)
    application.model.inner.inner = application._model_adapter
    assert application.model.provider == 'openai'
    return application, transport


class _OpeningWire(_FakeOpenAI):
    def _create(self, **kwargs):
        properties = kwargs['response_format']['json_schema']['schema']['properties']
        if 'discloses' in properties:
            self._content = json.dumps({'discloses': 'matter', 'depth': 'a_question',
                                        'why': 'Synthetic matter question'})
        elif set(properties) == set(DUTY_SCHEMA['properties']):
            self._content = json.dumps({'ground': 'clear', 'quoted': '', 'why': 'Synthetic',
                                        'lawful_section': ''})
        else:
            raise AssertionError('unexpected model read before incomplete screens')
        return super()._create(**kwargs)


def test_served_turn_refuses_before_provider_and_keeps_owned_file(client):
    application, transport = bound(client, _OpeningWire())
    opened = client.post('/api/matters/intake', json={
        'request_key': 'ai-test', 'title': 'Synthetic'})
    assert opened.status_code == 200
    mid = opened.json()['matter_id']
    denied = client.post('/api/turn', json={'message': 'Hello', 'matter_id': mid,
                                          'expected_version': opened.json()['version']})
    assert denied.status_code == 403, denied.text
    assert denied.json()['detail']['code'] == 'model_permission_required'
    assert transport.calls == []
    assert client.get('/api/matters/' + mid).status_code == 200
    assert choice(client).status_code == 200
    # Genuine served route, fake wire result; no invented legal quality verdict.
    accepted = client.post('/api/turn', json={'message': 'Synthetic matter question',
        'matter_id': mid, 'expected_version': opened.json()['version']})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['blocked'] is True, 'incomplete screens still control substance'
    assert len(transport.calls) == 2  # route and professional-duty reads precede the screen
    assert all(call['store'] is False for call in transport.calls)
    assert [set(call['response_format']['json_schema']['schema']['properties'])
            for call in transport.calls] == [
                {'discloses', 'depth', 'why'}, set(DUTY_SCHEMA['properties'])]
    # The generic/unauthenticated model route is still blocked.
    with pytest.raises(EgressRefused):
        application.model.complete(Prompt('Synthetic'), Tier.ROUTINE)


def test_revocation_stops_next_call_on_an_already_constructed_engine(client):
    application, transport = bound(client)
    assert choice(client).status_code == 200
    model = application.engine_for('adv_demo', session_current=lambda: True)._model
    assert model.complete(Prompt('Synthetic'), Tier.ROUTINE).text
    assert choice(client, False, 1).status_code == 200
    with pytest.raises(ModelPermissionRefused):
        model.complete(Prompt('Synthetic follow-up'), Tier.ROUTINE)
    assert len(transport.calls) == 1
    assert model.take()['count'] == 1, 'policy wrapper lost the actual call trace'


def test_revocation_is_checked_again_on_transport_retry(client, monkeypatch):
    transport = _FakeOpenAI(fail_times=1, exc=RateLimited('Synthetic rate limit'))
    application, _ = bound(client, transport)
    assert choice(client).status_code == 200
    model = application.engine_for('adv_demo', session_current=lambda: True)._model
    def withdraw(_seconds):
        assert choice(client, False, 1).status_code == 200
    monkeypatch.setattr('nm.adapters.model.openai_adapter.time.sleep', withdraw)
    with pytest.raises(ModelPermissionRefused):
        model.complete(Prompt('Synthetic'), Tier.ROUTINE)
    assert len(transport.calls) == 1, 'retry sent bytes after withdrawal'


@pytest.mark.parametrize('url', ['https://elsewhere.example/v1', 'http://api.openai.com/v1',
    'https://api.openai.com.evil.example/v1', 'https://api.openai.com/v1?forward=1'])
def test_permission_never_admits_an_alternative_destination(client, url):
    cfg = _config()
    cfg = replace(cfg, tiers={k: replace(v, base_url=url) for k, v in cfg.tiers.items()})
    application, transport = bound(client, config=cfg)
    assert choice(client).status_code == 200
    with pytest.raises(ModelPermissionRefused):
        application.engine_for('adv_demo', session_current=lambda: True)
    assert transport.calls == []


def test_text_permission_never_enables_other_sinks_classes_or_embeddings(client):
    application, transport = bound(client)
    assert choice(client).status_code == 200
    model = application.engine_for('adv_demo', session_current=lambda: True)._model
    with pytest.raises(ModelPermissionRefused):
        model.embed(('Synthetic',))
    assert transport.calls == []
    for sink in Sink:
        route = Route(sink, 'openai', sink, (DataClass.CLIENT_MATTER,))
        assert bool(refuse(route, text_policy())) is (sink is not Sink.MODEL)
    assert refuse(Route(Sink.MODEL, 'openai', Sink.MODEL, (DataClass.RESTRICTED,)), text_policy())


def test_permission_history_is_attributable_not_a_legal_signoff(client):
    assert choice(client).status_code == 200
    row = client.directory.model_permission('adv_demo')
    assert ModelPermission.from_record(row.as_dict()) == row
    assert not text_policy().approved_foreign_regions
    assert 'NOT-COUNSEL' in text_policy().processing_exceptions[0].basis


def test_an_actor_id_alone_and_an_ended_session_cannot_send(client):
    application, transport = bound(client)
    assert choice(client).status_code == 200
    with pytest.raises(ModelPermissionRefused):
        application.engine_for('adv_demo')
    token = client.cookies.get('nm_session')
    device = api._device(client.cookies.get('nm_device'), client.headers.get('user-agent'))
    model = application.engine_for('adv_demo', session_current=lambda: bool(
        client.directory.session(token, device, utcnow())))._model
    model.complete(Prompt('Synthetic'), Tier.ROUTINE)
    assert client.post('/api/logout').status_code == 200
    with pytest.raises(ModelPermissionRefused):
        model.complete(Prompt('Synthetic after logout'), Tier.ROUTINE)
    assert len(transport.calls) == 1


def test_direct_transport_does_not_inherit_an_endpoint_or_redirect(monkeypatch):
    captured = {}
    def factory(**kwargs):
        captured.update(kwargs)
        return _FakeOpenAI()
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://elsewhere.example/v1')
    # Constructor contract, not SDK/network proof. Class A works without the
    # optional paid-provider package; a live smoke test is separately approved.
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=factory))
    OpenAIModelAdapter(_config())
    try:
        assert captured['base_url'] == 'https://api.openai.com/v1'
        assert captured['max_retries'] == 0, 'SDK retries would evade the permission recheck'
        assert captured['http_client'].follow_redirects is False
        assert captured['http_client'].trust_env is False
    finally:
        captured['http_client'].close()


def test_failed_permission_write_cannot_be_reported_as_acceptance(client, monkeypatch):
    def fail(*args):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(client.directory, '_replace_advocate', fail)
    result = choice(client)
    assert result.status_code == 503
    assert client.directory.model_permission('adv_demo') is None
