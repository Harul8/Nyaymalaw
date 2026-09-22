"""A focused real-browser cover check; not a claim of a complete journey run."""
from __future__ import annotations

import pytest

from tests import test_the_journey_login_to_logout as journey_support
from tests.test_the_journey_login_to_logout import (
    BRIEF,
    _advise,
    _open_matter,
)

pytestmark = pytest.mark.journey
journey = journey_support.journey
page = journey_support.page


def test_the_browser_cover_shows_the_file_the_advocate_just_worked(page, journey):
    _open_matter(page, journey, client="Synthetic CoverBrowserClient")
    with page.expect_response(lambda reply: reply.url.endswith("/api/turn")
                              and reply.request.method == "POST") as sent:
        _advise(page, BRIEF)
    reply = sent.value
    assert reply.status == 200
    matter_id = reply.json()["matter_id"]
    response = page.request.get(f"{journey['base']}/api/matters/{matter_id}/cover")
    assert response.status == 200
    cover = response.json()
    assert cover["client"] == "Synthetic CoverBrowserClient"
    assert cover["last_activity"]
    assert cover["case_deadlines"]["deadline_entries"], "must really have worked a dated file"
    page.locator('#workspace-more summary').click()
    page.get_by_role("button", name="Matter cover & instructions", exact=True).click()
    dialog = page.locator("#matter-workspace-dialog")
    dialog.wait_for(state="visible")
    page.wait_for_function("() => document.querySelector('#matter-workspace-dialog')"
                           ".textContent.includes('Case deadlines')")
    shown = dialog.inner_text()
    assert "Synthetic CoverBrowserClient" in shown
    assert cover["last_activity"] in shown
    assert "plaintiff" in shown.lower()
    assert "Instruction deadline" in shown and "Case deadlines" in shown
    for row in cover["case_deadlines"]["deadline_entries"]:
        assert row["on"] is None or row["on"] in shown
        assert row["action"] in shown
        assert row["status"].replace("_", " ") in shown.lower()
    assert not page.errors


def test_capacity_correction_is_reachable_and_preserves_the_conversation(page, journey):
    from tests.test_opening_journey import saved
    _open_matter(page, journey, client='Synthetic CapacityCorrection')
    matter_id, _ = saved(page)
    page.fill('#message', 'Keep this unsent instruction.')
    page.locator('#workspace-more summary').click()
    page.get_by_role('button', name='Matter cover & instructions', exact=True).click()
    page.get_by_role('button', name='Record capacity assessment', exact=True).click()
    assert page.get_by_label('Your capacity assessment', exact=True).input_value() == ''
    page.get_by_label('Your capacity assessment', exact=True).select_option('not_in_doubt')
    page.get_by_label('Basis for your assessment', exact=True).fill(
        'The advocate explicitly assessed the current instructions.')
    page.get_by_role('button', name='Save capacity assessment', exact=True).click()
    page.get_by_text('Capacity assessment recorded.', exact=False).wait_for()
    assert page.input_value('#message') == 'Keep this unsent instruction.'
    cover = page.request.get(f"{journey['base']}/api/matters/{matter_id}/cover").json()
    assert cover['capacity_assessment']['state'] == 'not_in_doubt'
    assert cover['capacity_assessment']['raised_by']
    assert not page.errors
