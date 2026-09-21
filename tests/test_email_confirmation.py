"""Arrive: a pending registration is not an account or a permission grant."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from nm.adapters.store.directory import FileDirectory
from nm.adapters.store.pending_accounts import PendingAccounts
from nm.domain.account_confirmation import CODE_ATTEMPTS, ConfirmationRefused
from nm.domain.advocate import AdvocateIdentity, Enrolment, enrol, registration_consent, utcnow
from nm.ports.directory import RegistrationUnavailable

from tests.registration import CONSENT
from tests.test_turn_contract import KEY

pytestmark = pytest.mark.class_a
EMAIL = 'confirmation@example.test'
PASSWORD = 'Synthetic-password-42!'


@pytest.fixture
def pending(tmp_path):
    directory = FileDirectory(tmp_path, KEY)
    now = utcnow()
    consent = registration_consent(CONSENT['notice_version'], True, True, now)
    request = Enrolment(AdvocateIdentity(id=EMAIL, name=EMAIL, email=EMAIL),
                       enrol(PASSWORD), now, consent)
    return directory, now, request


def request_registration(client, email=EMAIL, password=PASSWORD):
    return client.post('/api/register', json={
        'email': email, 'password': password, 'password_again': password, 'consent': CONSENT})


def confirmation_code(client, email=EMAIL):
    messages = [m for m in client.outbox.messages_for(email)
                if m['purpose'] == 'email-confirmation']
    assert messages, 'no actual confirmation message was queued'
    return re.search(r'\b[0-9]{6}\b', messages[-1]['text']).group()


def enable_local_registration(monkeypatch):
    from nm.edge.api import application
    app = application()
    monkeypatch.setattr(app, 'environment', {
        **app.environment, 'NM_PUBLIC_REGISTRATION': 'local-test', 'NM_MODEL_PROVIDER': 'scripted'})


def test_pending_account_cannot_authenticate_then_activates_once(pending):
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    assert directory.identity(EMAIL) is None
    assert directory.authenticate(EMAIL, PASSWORD) is None
    result = directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)
    assert result.id == EMAIL
    assert directory.authenticate(EMAIL, PASSWORD).id == EMAIL
    record = json.loads(directory._advocate_path(EMAIL).read_text())
    assert record['mailbox_confirmed_at'] == now.isoformat()
    assert record['consent']['notice_version'] == CONSENT['notice_version']
    with pytest.raises(ConfirmationRefused):
        directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)


def test_pending_storage_is_sealed_and_expiry_does_not_activate(pending):
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    payload = (directory._root / 'pending-accounts.sqlite3').read_bytes()
    for secret in [EMAIL, PASSWORD, response['flow'], request.credential.hash]:
        assert secret.encode() not in payload
    with pytest.raises(ConfirmationRefused):
        directory.confirm_registration(EMAIL, response['code'], response['flow'], None,
                                       now + timedelta(minutes=15))
    assert directory.identity(EMAIL) is None


def test_wrong_attempts_survive_restart_and_resend_does_not_reset_them(pending):
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    wrong = '000000' if response['code'] != '000000' else '000001'
    for _ in range(CODE_ATTEMPTS - 1):
        with pytest.raises(ConfirmationRefused):
            FileDirectory(directory._root, KEY).confirm_registration(
                EMAIL, wrong, response['flow'], None, now)
    assert directory.resend_registration(EMAIL, now + timedelta(seconds=61)) == response['code']
    with pytest.raises(ConfirmationRefused):
        directory.confirm_registration(EMAIL, wrong, response['flow'], None, now)
    with pytest.raises(ConfirmationRefused):
        directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)
    assert directory.resend_registration(EMAIL, now + timedelta(seconds=62)) is None


def test_only_one_concurrent_confirmation_activates(pending):
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    def confirm(_):
        try:
            FileDirectory(directory._root, KEY).confirm_registration(
                EMAIL, response['code'], response['flow'], None, now)
            return True
        except ConfirmationRefused:
            return False
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(confirm, range(4)))
    assert results.count(True) == 1
    assert directory.authenticate(EMAIL, PASSWORD).id == EMAIL


def test_another_browser_must_choose_its_own_password(pending):
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    with pytest.raises(ConfirmationRefused, match='Choose a new password'):
        directory.confirm_registration(EMAIL, response['code'], '', None, now)
    assert directory.identity(EMAIL) is None
    owner_password = 'Mailbox-owner-password-52!'
    directory.confirm_registration(EMAIL, response['code'], '', enrol(owner_password), now)
    assert directory.authenticate(EMAIL, PASSWORD) is None
    assert directory.authenticate(EMAIL, owner_password).id == EMAIL


def test_duplicate_signup_never_replaces_pending_or_active_account(pending):
    directory, now, request = pending
    first = directory.begin_pending_registration(request, now)
    assert directory.begin_pending_registration(request, now)['code'] is None
    directory.confirm_registration(EMAIL, first['code'], first['flow'], None, now)
    before = directory._advocate_path(EMAIL).read_bytes()
    assert directory.begin_pending_registration(request, now)['code'] is None
    assert directory._advocate_path(EMAIL).read_bytes() == before


def test_expired_pending_records_can_be_replaced(pending):
    directory, now, request = pending
    first = directory.begin_pending_registration(request, now)
    second = directory.begin_pending_registration(request, now + timedelta(hours=24))
    assert second['code'] is not None
    assert second['flow'] != first['flow']
    with pytest.raises(ConfirmationRefused):
        directory.confirm_registration(EMAIL, first['code'], first['flow'], None,
                                       now + timedelta(hours=24))


def test_account_published_before_confirmation_commit_is_reconciled(pending, monkeypatch):
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    write = PendingAccounts.write
    def fail_commit(self, db, email, doc):
        if doc['used']:
            raise OSError('synthetic interruption after account publication')
        return write(self, db, email, doc)
    monkeypatch.setattr(PendingAccounts, 'write', fail_commit)
    with pytest.raises(OSError):
        directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)
    before = directory._advocate_path(EMAIL).read_bytes()
    monkeypatch.setattr(PendingAccounts, 'write', write)
    result = FileDirectory(directory._root, KEY).confirm_registration(
        EMAIL, response['code'], response['flow'], None, now)
    assert result.id == EMAIL
    assert directory._advocate_path(EMAIL).read_bytes() == before
    with pytest.raises(ConfirmationRefused):
        directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)


def test_corrupt_pending_store_is_unavailable_not_a_new_population(pending):
    directory, now, request = pending
    path = directory._root / 'pending-accounts.sqlite3'
    path.write_bytes(b'synthetic corrupt database')
    with pytest.raises(RegistrationUnavailable):
        directory.begin_pending_registration(request, now)
    assert directory.identity(EMAIL) is None
    assert path.read_bytes() == b'synthetic corrupt database'


def test_correction_invalidates_only_the_owned_pending_code(pending):
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    assert not directory.cancel_pending_registration(EMAIL, 'wrong-flow', now)
    assert directory.cancel_pending_registration(EMAIL, response['flow'], now)
    with pytest.raises(ConfirmationRefused):
        directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)
    assert directory.identity(EMAIL) is None


def test_interrupted_account_publication_leaves_no_partial_login(pending, monkeypatch):
    from nm.adapters.store import directory as store
    directory, now, request = pending
    response = directory.begin_pending_registration(request, now)
    real_link = store.os.link
    def interrupt(*args):
        raise OSError('synthetic publish failure')
    monkeypatch.setattr(store.os, 'link', interrupt)
    with pytest.raises(OSError):
        directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)
    assert not directory._advocate_path(EMAIL).exists()
    assert not list(directory._advocates.glob('*.tmp'))
    monkeypatch.setattr(store.os, 'link', real_link)
    directory.confirm_registration(EMAIL, response['code'], response['flow'], None, now)
    assert directory.authenticate(EMAIL, PASSWORD).id == EMAIL


def test_registration_is_disabled_without_delivery(client, monkeypatch):
    from nm.edge.api import application
    monkeypatch.setattr(application(), 'environment', {'NM_MODEL_PROVIDER': 'scripted'})
    assert client.get('/api/account-capabilities').json()['public_registration'] is False
    assert request_registration(client).status_code == 503
    assert client.directory.identity(EMAIL) is None
    assert not client.outbox.messages_for(EMAIL)


def test_full_pending_population_reports_unavailable_without_activating(client, monkeypatch):
    from nm.adapters.store import pending_accounts
    enable_local_registration(monkeypatch)
    monkeypatch.setattr(pending_accounts, 'MAX_PENDING', 1)
    assert request_registration(client).status_code == 202
    response = request_registration(client, email='second@example.test')
    assert response.status_code == 503
    assert response.headers['retry-after'] == '60'
    assert client.directory.identity('second@example.test') is None
    assert not client.outbox.messages_for('second@example.test')


def test_served_signup_confirmation_and_private_workspace(client, monkeypatch):
    enable_local_registration(monkeypatch)
    client.cookies.clear()
    response = request_registration(client)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body['state'] == 'confirmation_required'
    assert body['delivery'] == 'local_outbox_only'
    assert client.directory.identity(EMAIL) is None
    assert client.post('/api/login', json={
        'advocate_id': EMAIL, 'password': PASSWORD}).status_code == 401
    assert client.get('/api/matters').status_code == 401
    confirmed = client.post('/api/register/confirm', json={
        'email': EMAIL, 'code': confirmation_code(client), 'flow': body['flow']})
    assert confirmed.status_code == 200, confirmed.text
    assert not confirmed.headers.get('set-cookie')
    assert client.get('/api/session').status_code == 401
    signed = client.post('/api/login', json={'advocate_id': EMAIL, 'password': PASSWORD})
    assert signed.status_code == 200, signed.text
    assert signed.json()['professional_approval']['state'] == 'unapproved'
    assert signed.json()['workspace']['id'] == f'advocate:{EMAIL}'


def test_public_resend_is_neutral_and_does_not_expose_code(client, monkeypatch):
    enable_local_registration(monkeypatch)
    assert request_registration(client).status_code == 202
    code = confirmation_code(client)
    before = len(client.outbox.messages_for(EMAIL))
    known = client.post('/api/register/resend', json={'email': EMAIL})
    unknown = client.post('/api/register/resend', json={'email': 'absent@example.test'})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert code not in known.text
    assert len(client.outbox.messages_for(EMAIL)) == before


@pytest.mark.parametrize('route,body', [
    ('/api/register/confirm', {'email': EMAIL, 'code': '123456'}),
    ('/api/register/resend', {'email': EMAIL}),
    ('/api/register/cancel', {'email': EMAIL, 'flow': 'synthetic'}),
    ('/api/login', {'advocate_id': EMAIL, 'password': PASSWORD}),
])
def test_browser_account_doors_refuse_a_foreign_origin(client, route, body):
    response = client.post(route, json=body, headers={'Origin': 'https://foreign.example'})
    assert response.status_code == 403
