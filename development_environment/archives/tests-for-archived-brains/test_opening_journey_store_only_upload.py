"""Archived 16 Oct 2026 from tests/test_opening_journey.py: the store-only upload through the
original-material window, retired by the owner's item 6 decisions (15 Oct 2026: files sent with a
message are checked and read) and F-B-04 (16 Oct 2026). Kept for reference; not collected."""

from __future__ import annotations

from urllib.parse import urljoin

import pytest

from tests.matter_records import open_record
from tests.test_the_journey_login_to_logout import WIDTHS, _sign_in, _start_matter
from tests.test_the_journey_login_to_logout import journey as _base_journey
from tests.test_the_journey_login_to_logout import page as _base_page

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page



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
