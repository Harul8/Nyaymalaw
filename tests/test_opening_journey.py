"""Served opening proof: real persisted responses, synthetic accounts only."""
from __future__ import annotations

from urllib.parse import urljoin

import pytest

from tests.test_the_journey_login_to_logout import WIDTHS, _sign_in, _start_matter
from tests.test_the_journey_login_to_logout import journey as _base_journey
from tests.test_the_journey_login_to_logout import page as _base_page

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page


def saved(page):
    page.wait_for_selector('#composer:not([hidden])', timeout=15000)
    mid = page.get_attribute('#pane-advise', 'data-matter-id')
    assert mid
    response = page.request.get(urljoin(page.url, '/api/matters/' + mid))
    assert response.status == 200
    return mid, response.json()


@pytest.mark.parametrize('width,height', WIDTHS)
def test_open_unknowns_then_reopen_before_sending(page, journey, width, height):
    _sign_in(page, journey, width, height)
    _start_matter(page)
    page.click('#in-go')
    mid, body = saved(page)
    assert body['title'] == 'New matter'
    assert body['opening_brief']['brief']['urgency'] == 'not_known'
    assert body['row_count'] == 0
    page.reload()
    page.get_by_role('button', name='My work', exact=True).click()
    page.locator(f'#rail-body [data-matter-id="{mid}"]').click()
    again, restored = saved(page)
    assert again == mid and restored['opening_brief'] == body['opening_brief']
    assert not page.errors


def test_lost_opening_acknowledgement_recovers_original_not_changed_offer(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    original = 'Synthetic original task — do not turn it into another matter'
    page.fill('#in-scope', original)
    calls = []

    def intercept(route):
        response = route.fetch()
        assert response.status == 200
        calls.append((route.request.post_data_json, response.json()))
        if len(calls) == 1:
            route.abort('failed')
        else:
            route.fulfill(response=response)

    page.route('**/api/matters/intake', intercept)
    page.click('#in-go')
    page.get_by_text('Opening was not confirmed:', exact=False).wait_for()
    page.fill('#in-scope', 'Different task after an uncertain opening')
    page.click('#in-go')
    assert len(calls) == 1
    page.get_by_role('button', name='Restore original answers and retry', exact=True).click()
    mid, body = saved(page)
    assert len(calls) == 2 and calls[0][0] == calls[1][0]
    assert calls[0][1]['matter_id'] == mid == calls[1][1]['matter_id']
    assert body['opening_brief']['brief']['objective'] == original
    assert not page.errors


def test_all_new_fields_are_protected_and_restored_before_opening(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.fill('#in-title', 'Synthetic advisory file')
    page.fill('#in-client', 'Synthetic Company\nSynthetic Director')
    page.select_option('#in-client-type', 'mixed')
    page.fill('#in-scope', 'Review only; do not transmit')
    page.get_by_text('Who is giving instructions?', exact=True).click()
    page.select_option('#in-instructing', 'representative')
    page.fill('#in-instructor', 'Synthetic Officer')
    page.fill('#in-instructor-role', 'Officer')
    page.fill('#in-authority', 'Not yet verified')
    page.get_by_text('Current position', exact=True).click()
    page.select_option('#in-proceedings', 'none')
    page.get_by_text('Anything time-sensitive?', exact=True).click()
    page.select_option('#in-urgency', 'stated')
    page.fill('#in-date', '2026-10-01')
    page.fill('#in-date-source', 'Synthetic calendar')
    page.locator('#draft-status').filter(has_text='Saved on this device').wait_for()
    page.reload()
    # Recovery is now explicit and scoped to the opening input, never a global banner.
    _start_matter(page)
    page.locator('#workspace-more summary').click()
    page.click('#draft-open')
    page.get_by_role('button', name='Recover unsent draft', exact=False).click()
    page.click('#in-go')
    _, body = saved(page)
    record = body['opening_brief']
    assert len(record['parties']) == 2
    brief = record['brief']
    assert brief['instructor_name'] == 'Synthetic Officer'
    assert brief['authority_basis'] == 'Not yet verified'
    assert brief['proceedings'] == 'none'
    assert brief['reported_date'] == '2026-10-01'
    assert brief['date_source'] == 'Synthetic calendar'
    assert brief['capacity']['state'] == 'not_assessed'
    page.reload()
    page.wait_for_selector('#masthead:not([hidden])')
    assert page.get_by_role('button', name='Recover unsent draft', exact=False).count() == 0
    assert not page.errors


def test_store_only_upload_is_received_not_read_and_survives_reentry(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.click('#in-go')
    mid, _ = saved(page)
    page.click('#plus-toggle')
    page.click('#plus-voice')  # Opens the shared dialog without asking for a microphone.
    page.wait_for_selector('#materials-upload:not([disabled])')
    page.set_input_files('#materials-files', {
        'name': 'Synthetic original.txt', 'mimeType': 'text/plain',
        'buffer': b'Synthetic original. Storage only; no legal fact established.'})
    page.fill('#materials-purpose', 'Hold this synthetic original only; do not analyse')
    page.fill('#materials-authority', 'Synthetic local review material')
    page.select_option('#materials-retention', 'matter_life')
    page.click('#materials-upload')
    page.get_by_text('Original received in restricted quarantine.', exact=False).wait_for()
    listing = page.request.get(urljoin(page.url, f'/api/matters/{mid}/uploads')).json()
    assert len(listing['uploads']) == 1
    original = listing['uploads'][0]
    assert original['receipt']['state'] == 'received'
    assert original['may_reach_reasoning'] is False
    page.click('#materials-close')
    page.reload()
    page.get_by_role('button', name='My work', exact=True).click()
    page.locator(f'#rail-body [data-matter-id="{mid}"]').click()
    page.click('#plus-toggle')
    page.click('#plus-voice')
    page.get_by_text('Received — not admitted or read', exact=False).wait_for()
    assert not page.errors
