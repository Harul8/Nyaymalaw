"""Approved-only real-browser manual urgency flow; synthetic instructions only."""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import _sign_in
from tests.test_the_workspace_respects_its_current_context import (
    _assert_no_overflow,
    _new_matter,
    _open_by_keyboard,
)
from tests.test_the_workspace_respects_its_current_context import journey as _base_journey
from tests.test_the_workspace_respects_its_current_context import page as _base_page

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page


@pytest.mark.parametrize("width,height", [(390, 844), (1280, 900)])
def test_an_advocate_records_reopens_and_explicitly_resolves_one_danger(
        page, journey, width, height):
    _sign_in(page, journey, width, height)
    matter_id = _new_matter(page, f"Manual urgency client {width}", width)
    before = journey["box"].application.store.load(matter_id)
    page.get_by_role("button", name="Protective handoff", exact=True).click()
    page.get_by_role("button", name="Record a danger manually", exact=True).click()
    page.select_option("#mw-urgency-class", "personal_safety")
    page.fill("#mw-urgency-basis", "The instructing advocate reports a specific immediate danger")
    page.fill("#mw-urgency-action", "Contact the responsible advocate for a protective response")
    page.fill("#mw-urgency-owner", "The instructing advocate")
    page.fill("#mw-urgency-due-unknown", "The controlling order has not been supplied")
    _assert_no_overflow(page)
    page.get_by_role("button", name="Record this danger", exact=True).click()
    page.wait_for_selector("#matter-workspace-dialog[open]", state="hidden")
    page.wait_for_function("() => state.matterReady && !activeDelivery")
    saved = journey["box"].application.store.load(matter_id)
    assert saved.facts == before.facts and saved.emergencies == before.emergencies
    assert len(saved.urgency_records) == 1 and saved.urgency_records[0]["state"] == "live"
    urgency_id = saved.urgency_records[0]["urgency_id"]
    page.reload()
    page.wait_for_selector("#masthead", state="visible")
    _open_by_keyboard(page, matter_id, width)
    page.get_by_role("button", name="Protective handoff", exact=True).click()
    dialog = page.locator("#matter-workspace-dialog")
    dialog.get_by_role("heading", name="live · personal safety", exact=True).wait_for()
    assert "Unknown — The controlling order has not been supplied" in dialog.inner_text()
    assert "user-supplied, unverified" in dialog.inner_text()
    page.get_by_role("button", name="Record explicit resolution", exact=True).click()
    page.fill("#mw-urgency-resolution",
              "The responsible advocate confirmed the reported danger was addressed")
    page.get_by_role("button", name="Record this resolution", exact=True).click()
    page.wait_for_selector("#matter-workspace-dialog[open]", state="hidden")
    page.wait_for_function("() => state.matterReady && !activeDelivery")
    page.get_by_role("button", name="Protective handoff", exact=True).click()
    dialog.get_by_role("heading", name="resolved · personal safety", exact=True).wait_for()
    resolved = journey["box"].application.store.load(matter_id)
    record = resolved.urgency_records[0]
    assert record["urgency_id"] == urgency_id and record["state"] == "resolved"
    assert record["resolver"] == resolved.advocate_id and record["resolved_at"]
    assert resolved.emergencies == before.emergencies and resolved.facts == before.facts
    assert not page.errors and not page.external_assets
    _assert_no_overflow(page)
