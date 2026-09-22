"""Real browser interaction with the served saved-source boundary; synthetic model."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest
from nm.core.source_excerpt import capture
from nm.domain.answer import Element, ElementKind
from nm.domain.turn_receipt import answer_payload

from tests.test_conversation_recovery_journey import reopen
from tests.test_opening_journey import saved
from tests.test_the_journey_login_to_logout import BRIEF, _advise, _open_matter
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page
from tests.test_turn_contract import finding

pytestmark = pytest.mark.journey
journey, page = _journey, _page


def _ready(page, journey, **size):
    _open_matter(page, journey, client='Synthetic source reader', **size)
    saved(page)
    _advise(page, BRIEF)
    link = page.locator('#thread .citation-link').first
    link.wait_for()
    return link


@pytest.mark.parametrize('width,height', [(390, 844), (768, 1024), (1280, 900)])
def test_source_reader_preserves_conversation_draft_focus_and_exact_saved_words(
        page, journey, width, height):
    _ready(page, journey, width=width, height=height)
    # Reload through the actual persisted transcript, not an in-memory render.
    mid, _ = saved(page)
    reopen(page, mid)
    link = page.locator('#thread .citation-link').first
    link.wait_for()
    page.fill('#message', 'An unsent clarification stays here.\nSecond line.')
    before = page.locator('#thread').evaluate('el => el.scrollTop')
    link.focus()
    page.keyboard.press('Enter')
    page.wait_for_function("document.getElementById('source-text').textContent.length > 0")
    assert page.get_by_role('dialog').is_visible()
    assert page.locator('#source-close').evaluate('el => el === document.activeElement')
    assert 'complete Act or judgment' in page.locator('#source-coverage').inner_text()
    text = page.locator('#source-text').inner_text()
    assert len(text) > 12
    assert page.locator('#source-reader').bounding_box()['width'] <= width
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.fill('#source-search', text[:12])
    assert page.locator('#source-text mark').count() >= 1
    assert 'loaded text only' in page.locator('#source-search-result').inner_text()
    page.click('#source-return')
    assert page.locator('#source-text').evaluate('el => el === document.activeElement')
    page.keyboard.press('Escape')
    assert not page.get_by_role('dialog').is_visible()
    assert link.evaluate('el => el === document.activeElement')
    assert page.input_value('#message') == 'An unsent clarification stays here.\nSecond line.'
    assert abs(page.locator('#thread').evaluate('el => el.scrollTop') - before) < 2
    assert not page.errors


def _long_saved_source(page, journey):
    _ready(page, journey)
    mid, _ = saved(page)
    store = journey['box'].application.store
    matter = store.load(mid)
    receipt = matter.turn_receipts[-1]
    text = '<img src=x onerror=alert(1)>\n\n' + ('Original शब्द  quoted text.\n' * 650)
    source = capture(finding(span=text))
    answer = receipt.validated_answer()
    answer = replace(answer, elements=(*answer.elements, Element(
        kind=ElementKind.GROUND, text='Treatment remains unverified; this is a saved excerpt.',
        refs=(source.locator,), source=source)))
    updated = replace(receipt, answer=answer_payload(answer))
    store.commit(replace(matter, version=matter.version + 1,
                         turn_receipts=(*matter.turn_receipts[:-1], updated)),
                 expected_version=matter.version)
    reopen(page, mid)
    page.locator('#thread .citation-link').last.wait_for()
    page.locator('#thread .citation-link').last.click()
    page.wait_for_function("document.getElementById('source-text').textContent.length === 6000")
    return text


def test_paging_safe_markup_copy_and_scope_are_visible(page, journey):
    text = _long_saved_source(page, journey)
    assert page.locator('#source-text img').count() == 0
    assert page.locator('#source-more').is_visible()
    while page.locator('#source-more').is_visible():
        page.click('#source-more')
        page.wait_for_function("!document.getElementById('source-more').disabled")
    assert page.locator('#source-text').text_content() == text
    # A controlled clipboard port observes precisely what the real button copies.
    page.evaluate("""Object.defineProperty(navigator, 'clipboard', {configurable:true,
        value:{writeText: async value => {window.copiedSource=value;}}})""")
    page.click('#source-copy')
    page.wait_for_function('!!window.copiedSource')
    copied = page.evaluate('window.copiedSource')
    assert text in copied and 'not the full document' in copied
    assert 'Treatment remains unverified' in copied and 'Saved content' in copied
    assert not page.errors


def test_copy_reauthorises_and_clears_text_after_refusal(page, journey):
    _ready(page, journey).click()
    page.wait_for_function("document.getElementById('source-text').textContent.length > 0")
    page.route('**/sources/*?*', lambda route: route.fulfill(
        status=404, content_type='application/json', body=json.dumps({'detail': 'No source'})))
    page.click('#source-copy')
    page.get_by_text('The saved passage could not be opened.', exact=False).wait_for()
    assert page.locator('#source-text').text_content() == ''
    assert page.locator('#source-copy').is_disabled()
    assert page.locator('#source-retry').is_visible()


def test_clipboard_denial_does_not_claim_success_or_hide_the_passage(page, journey):
    _ready(page, journey).click()
    page.wait_for_function("document.getElementById('source-text').textContent.length > 0")
    text = page.locator('#source-text').text_content()
    page.evaluate("""Object.defineProperty(navigator, 'clipboard', {configurable:true,
        value:{writeText: async () => {throw new Error('permission denied');}}})""")
    page.click('#source-copy')
    page.get_by_text('Copy was not permitted by the browser.', exact=False).wait_for()
    assert page.locator('#source-text').text_content() == text
    assert page.locator('#source-copy').is_enabled()
    assert 'Copied' not in page.locator('#source-status').inner_text()


@pytest.mark.parametrize('transition', ['navigate', 'clear_privileged'])
def test_navigation_and_session_clear_discard_pending_source(page, journey, transition):
    link = _ready(page, journey)
    pending = []
    page.route('**/sources/*?*', lambda route: pending.append(route))
    link.click()
    page.wait_for_timeout(100)
    assert len(pending) == 1
    # Invoke the real transition while the native modal prevents background clicks.
    page.evaluate("showTab('home')" if transition == 'navigate' else 'clearPrivileged()')
    pending[0].continue_()
    page.wait_for_timeout(200)
    assert not page.locator('#source-reader').is_visible()
    assert page.locator('#source-text').text_content() == ''
    assert not page.errors


def test_late_response_cannot_reopen_closed_reader(page, journey):
    link = _ready(page, journey)
    pending = []
    page.route('**/sources/*?*', lambda route: pending.append(route))
    link.click()
    page.wait_for_timeout(150)
    assert len(pending) == 1
    page.keyboard.press('Escape')
    pending[0].continue_()
    page.wait_for_timeout(200)
    assert not page.locator('#source-reader').is_visible()
    assert page.locator('#source-text').text_content() == ''
    assert not page.errors


def test_new_reference_wins_over_old_response(page, journey):
    _long_saved_source(page, journey)
    page.keyboard.press('Escape')
    pending = []
    page.route('**/sources/*?*', lambda route: pending.append(route))
    page.locator('#thread .citation-link').first.click()
    page.wait_for_timeout(100)
    page.keyboard.press('Escape')
    page.locator('#thread .citation-link').last.click()
    page.wait_for_timeout(100)
    assert len(pending) == 2
    pending[1].continue_()
    page.wait_for_function("document.getElementById('source-text').textContent.startsWith('<img')")
    text = page.locator('#source-text').text_content()
    pending[0].continue_()
    page.wait_for_timeout(200)
    assert page.locator('#source-text').text_content() == text
    assert not page.errors


def test_equal_prose_never_drops_different_support_or_disclosures(page, journey):
    _ready(page, journey)
    elements = [dict(kind='finding', text='Same assessed position.', signal='none',
                     refs=[ref], disclosure=disclosure)
                for ref, disclosure in [('a', False), ('b', False), ('b', True)]]
    page.evaluate("""elements => document.getElementById('thread').replaceChildren(
        renderTurn({answer:{elements,metrics:null}}))""", elements)
    assert page.locator('#thread .el').count() == 3
    assert page.locator('#thread .disclosure').is_visible()
    assert page.locator('#thread .source-unavailable').count() == 3


def test_dark_mode_and_zoom_keep_reader_operable(page, journey):
    link = _ready(page, journey, width=820, height=900)
    page.emulate_media(color_scheme='dark', reduced_motion='reduce')
    page.evaluate("document.documentElement.style.fontSize = '200%'")
    link.click()
    page.wait_for_function("document.getElementById('source-text').textContent.length > 0")
    assert page.locator('#source-close').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.keyboard.press('Escape')
    assert not page.locator('#source-reader').is_visible()
