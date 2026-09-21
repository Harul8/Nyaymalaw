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
