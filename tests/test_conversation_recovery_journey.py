"""Owner's quiet recovery contract, driven through the served page."""
import pytest

from tests.test_opening_journey import saved
from tests.test_the_journey_login_to_logout import WIDTHS, _sign_in, _start_matter
from tests.test_the_journey_login_to_logout import journey as _journey, page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


def open_recovery(page):
    page.locator('#workspace-more summary').click()
    page.click('#draft-open')
    page.wait_for_selector('#draft-dialog[open]')


def reopen(page, mid):
    page.reload()
    page.get_by_role('button', name='My work', exact=True).click()
    page.locator(f'#rail-body [data-matter-id="{mid}"]').click()
    saved(page)


def test_recovery_is_on_demand_and_success_disappears_without_losing_text(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.click('#in-go')
    mid, _ = saved(page)
    text = 'Synthetic unsent instruction about two disputed transactions.'
    page.fill('#message', text)
    page.locator('#draft-status').filter(has_text='Saved on this device').wait_for()
    reopen(page, mid)
    assert not page.locator('#draft-dialog').is_visible()
    assert page.locator('#draft-recovery').inner_text() == ''
    assert page.locator('#message').input_value() == ''
    open_recovery(page)
    page.get_by_role('button', name='Recover unsent draft', exact=False).click()
    page.locator('#draft-restored').filter(has_text='Draft restored').wait_for()
    assert page.locator('#message').input_value() == text
    page.wait_for_function("document.getElementById('draft-restored').textContent === ''", timeout=7000)
    assert page.locator('#message').input_value() == text
    assert page.locator('#thread .turn').count() == 0
    assert not page.locator('#draft-dialog').is_visible()
    assert not page.errors


def test_recovery_does_not_offer_another_matters_draft(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.click('#in-go')
    first, _ = saved(page)
    page.fill('#message', 'Synthetic first matter only')
    page.locator('#draft-status').filter(has_text='Saved on this device').wait_for()
    _start_matter(page)
    page.click('#in-go')
    second, _ = saved(page)
    assert first != second
    open_recovery(page)
    page.get_by_text('No recoverable drafts for this input.', exact=True).wait_for()
    assert page.locator('#draft-recovery button').count() == 0
    page.keyboard.press('Escape')
    assert not page.locator('#draft-dialog').is_visible()


def test_a_save_failure_does_not_disappear_like_a_success(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    page.click('#in-go')
    saved(page)
    page.evaluate("() => { Storage.prototype.setItem = function() { throw Error('Synthetic quota failure'); }; }")
    page.fill('#message', 'Do not lose this unsaved synthetic instruction')
    page.locator('#draft-status').filter(has_text='Could not save this draft').wait_for()
    page.wait_for_timeout(5300)
    assert 'Could not save this draft' in page.locator('#draft-status').inner_text()
    assert page.locator('#message').input_value() == 'Do not lose this unsaved synthetic instruction'


@pytest.mark.parametrize('width,height', WIDTHS)
def test_composer_is_reachable_and_ime_enter_is_not_a_send(page, journey, width, height):
    _sign_in(page, journey, width, height)
    _start_matter(page)
    page.click('#in-go')
    saved(page)
    page.fill('#message', 'Synthetic multi-dispute instruction')
    requests = []
    page.on('request', lambda request: requests.append(request.url) if '/api/turn' in request.url else None)
    page.locator('#message').dispatch_event('keydown', {'key': 'Enter', 'isComposing': True})
    assert not requests
    box = page.locator('#send').bounding_box()
    assert box and box['x'] >= 0 and box['x'] + box['width'] <= width
    assert box['y'] >= 0 and box['y'] + box['height'] <= height
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#message').input_value() == 'Synthetic multi-dispute instruction'
    assert not page.errors
