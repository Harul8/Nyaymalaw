"""A saved answer survives changed instructions as history, not a new assessment."""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import _sign_in, _tab
from tests.test_the_workspace_respects_its_current_context import (
    _new_matter,
    _open_by_keyboard,
)
from tests.test_the_workspace_respects_its_current_context import journey as _base_journey
from tests.test_the_workspace_respects_its_current_context import page as _base_page

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page

NOTICE = "Recorded response. It has not been reassessed against later changes to the file."


def test_changed_instructions_do_not_relabel_the_saved_answer_as_a_fresh_assessment(page, journey):
    _sign_in(page, journey)
    matter_id = _new_matter(page, "Synthetic changed-instruction client")
    before = journey["box"].application.store.load(matter_id)
    assert before.turn_receipts, "the historical answer must have really been saved"
    page.locator('#workspace-more summary').click()
    page.get_by_role("button", name="Matter cover & instructions", exact=True).click()
    page.get_by_role("button", name="Record the instructions", exact=True).click()
    page.fill("#mw-objective", "Review the changed synthetic instruction before any new assessment")
    page.select_option("#mw-work_product", "advice")
    page.fill("#mw-scope", "Internal review only; no external act")
    page.fill("#mw-exclusions", "No filing or communication")
    page.fill("#mw-instructing_id", "synthetic-instructor")
    page.fill("#mw-instructing_description", "Synthetic instructing client")
    page.select_option("#mw-instructing_capacity", "instructing")
    page.fill("#mw-deciding_id", "synthetic-decider")
    page.fill("#mw-deciding_description", "Synthetic decision owner")
    page.select_option("#mw-deciding_capacity", "deciding")
    page.fill("#mw-deadline_reason", "The operative basis is not established")
    page.fill("#mw-because", "Explicit changed instruction for a synthetic browser witness")
    page.get_by_role("button", name="Record instructions", exact=True).click()
    page.wait_for_selector("#matter-workspace-dialog[open]", state="hidden")
    page.get_by_text(NOTICE, exact=True).wait_for()
    saved = journey["box"].application.store.load(matter_id)
    assert saved.version > before.version
    assert saved.turn_receipts == before.turn_receipts
    assert saved.commission is not None
    writes = [row for row in page.request_identities
              if row["path"] == f"/api/matters/{matter_id}/commission"
              and row["method"] == "POST"]
    assert len(writes) == 1, "the instruction change must reach the real served route"
    _tab(page, "history")
    page.wait_for_selector(f"#history-matter option[value='{matter_id}']", state="attached")
    page.select_option("#history-matter", matter_id)
    page.locator("#pane-history").get_by_text(NOTICE, exact=True).wait_for()
    _tab(page, "advise")
    _open_by_keyboard(page, matter_id, 1280)
    page.locator("#pane-advise").get_by_text(NOTICE, exact=True).wait_for()
    assert not page.errors and not page.external_assets
