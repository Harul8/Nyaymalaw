"""Real browser/account persistence, isolated synthetic profile, no provider calls."""
from __future__ import annotations

import json
import re

import pytest

from tests import test_the_journey_login_to_logout as support
from tests.test_email_registration_reaches_a_private_workspace import _registration

pytestmark = pytest.mark.journey
journey = support.journey
page = support.page


def open_permission(page):
    page.click('#account-toggle')
    page.click('#ai-sharing')
    page.wait_for_function("() => document.getElementById('ai-sharing-status').textContent"
                           ".includes('for your account') || "
                           "document.getElementById('ai-sharing-status').textContent"
                           ".includes('not enabled')")


@pytest.mark.parametrize('width,height', support.WIDTHS)
def test_existing_account_can_accept_reload_withdraw_and_keep_its_matter(
        page, journey, width, height):
    support._sign_in(page, journey, width, height)
    support._start_matter(page)
    page.click('#in-go')
    page.wait_for_selector('#composer:not([hidden])')
    mid = page.get_attribute('#pane-advise', 'data-matter-id')
    assert mid
    open_permission(page)
    assert not page.is_checked('#ai-sharing-accept')
    assert page.locator('#ai-sharing-save').is_disabled()
    assert 'outside India' in page.inner_text('#ai-sharing-dialog')
    assert '30 days' in page.inner_text('#ai-sharing-dialog')
    assert 'excludes raw' in page.inner_text('#ai-sharing-dialog')
    page.check('#ai-sharing-accept')
    page.click('#ai-sharing-save')
    page.get_by_text('Permission recorded for OpenAI text processing.', exact=True).wait_for()
    assert journey['box'].directory.model_permission(journey['advocate']).accepted
    page.reload()
    page.wait_for_selector('#masthead:not([hidden])')
    open_permission(page)
    assert 'enabled for your account' in page.inner_text('#ai-sharing-status')
    page.click('#ai-sharing-withdraw')
    page.get_by_text('Permission withdrawn.', exact=False).wait_for()
    assert not journey['box'].directory.model_permission(journey['advocate']).accepted
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.click('#ai-sharing-close')
    support._reach_rail(page, width)
    page.locator(f'#rail-body [data-matter-id="{mid}"]').click()
    page.wait_for_selector('#composer:not([hidden])')
    assert page.get_attribute('#pane-advise', 'data-matter-id') == mid
    support._sign_out(page)
    assert page.is_hidden('#ai-sharing-dialog')
    assert page.inner_text('#ai-sharing-status') == ''
    assert not page.errors


def test_registration_acceptance_is_carried_through_real_email_confirmation(page, journey):
    email = 'synthetic-openai-permission@example.test'
    _registration(page, journey, email)
    assert not page.is_checked('#reg-external-ai')
    assert 'outside India' in page.inner_text('#register')
    page.check('#reg-external-ai')
    page.click('#register-go')
    page.wait_for_selector('#confirm-email:not([hidden])')
    messages = journey['box'].application.mail.messages_for(email)
    code = re.search(r'\b[0-9]{6}\b', messages[-1]['text']).group()
    page.fill('#confirm-code', code)
    page.click('#confirm-go')
    page.get_by_text('Email confirmed', exact=True).wait_for()
    row = journey['box'].directory.model_permission(email)
    assert row and row.accepted and row.version == 1
    assert not page.is_checked('#reg-external-ai')
    assert not page.errors


def test_permission_refusal_keeps_the_matter_and_offers_the_actual_settings(page, journey):
    """Rendering control only; real dispatcher refusal is tested through the API."""
    support._sign_in(page, journey)
    support._start_matter(page)
    page.click('#in-go')
    page.wait_for_selector('#composer:not([hidden])')
    mid = page.get_attribute('#pane-advise', 'data-matter-id')
    page.route('**/api/turn', lambda route: route.fulfill(
        status=403, content_type='application/json', body=json.dumps({'detail': {
            'code': 'model_permission_required', 'committed': 'unknown',
            'why': 'Review the current notice to permit OpenAI text processing.',
        }})))
    page.fill('#message', 'Synthetic brief: please assess the supplied records.')
    page.click('#send')
    page.get_by_role('button', name='Review AI data sharing', exact=True).click()
    page.wait_for_selector('#ai-sharing-dialog[open]')
    assert 'outside India' in page.inner_text('#ai-sharing-dialog')
    assert page.is_hidden('#intake')
    assert page.get_attribute('#pane-advise', 'data-matter-id') == mid
    page.click('#ai-sharing-close')
    assert page.is_visible('#message')
    assert page.input_value('#message') == 'Synthetic brief: please assess the supplied records.'
    assert not page.errors
