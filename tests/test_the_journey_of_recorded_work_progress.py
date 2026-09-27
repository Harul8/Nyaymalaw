"""P52: genuine browser reads safe stages from the real temporary sealed store.

The model is scripted and no loop is started through the browser. This tests
presentation and resumable receipts, not legal-response quality or release.
"""

from dataclasses import replace

import pytest

from nm.legal_brain.orchestrate.loop_contracts import StepKind, StopReason
from nm.work_the_file.matter_contracts import Matter
from tests.test_saved_loop_progress_is_not_an_advice_transport import SECRET, add, work
from tests.test_saved_work_attaches_only_to_its_released_turn import scoped_work
from tests.test_the_journey_login_to_logout import (
    _sign_in,
    _sign_out,
    _tab,
)
from tests.test_the_journey_login_to_logout import (
    journey as _base_journey,
)
from tests.test_the_journey_login_to_logout import (
    page as _base_page,
)

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page


def test_saved_work_is_closed_by_default_keyboard_reachable_and_updates_from_commits(page, journey):
    record = work(actor=journey["advocate"], stop=False)
    store = journey["box"].application.store
    matter = Matter(
        id=record.identity.matter_id,
        advocate_id=journey["advocate"],
        title="Saved progress presentation",
        version=1,
        loop_records=(record,),
    )
    store.commit(matter, expected_version=0)
    _sign_in(page, journey)
    _tab(page, "history")
    page.select_option("#history-matter", matter.id)
    panel = page.locator("#history-body .recorded-work-progress")
    panel.wait_for()
    assert panel.count() == 1 and not panel.evaluate("node => node.open")
    assert not page.get_by_text("Assessing the recorded file.", exact=True).is_visible()
    panel.locator(":scope > summary").click()
    child = panel.locator("details").first
    child.wait_for()
    assert not child.evaluate("node => node.open")
    summary = child.locator(":scope > summary")
    summary.focus()
    page.keyboard.press("Enter")
    page.wait_for_function(
        "document.querySelector('.recorded-work-progress .progress-stages')?.children.length === 3"
    )
    assert child.locator("[role='status'][aria-live='polite']").count() == 1
    assert "checks are still required" in child.inner_text()
    # More work is observable only after the existing sealed-store commit.
    # The browser is already following the actual SSE route at this point.
    updated = add(record, StepKind.TOOL_STARTED, {"private_context": SECRET})
    updated = add(updated, StepKind.STOP, {"reason": StopReason.BUDGET.value, "answer": SECRET})
    store.commit(replace(matter, version=2, loop_records=(updated,)), expected_version=1)
    page.wait_for_function(
        "document.querySelector('.recorded-work-progress .progress-stages')?.children.length === 5"
    )
    assert "Work paused at its resource limit." in child.inner_text()
    assert SECRET not in page.inner_text("body")
    assert "progress_turn" not in child.inner_text()
    assert "%" not in child.inner_text()
    panel.locator(":scope > summary").click()
    assert not panel.evaluate("node => node.open")
    assert not child.is_visible()
    # Reopening re-reads durable stages, not an obsolete in-memory list.
    panel.locator(":scope > summary").click()
    panel.locator("details > summary").first.click()
    page.wait_for_function(
        "document.querySelector('.recorded-work-progress .progress-stages')?.children.length === 5"
    )
    _sign_out(page)
    page.wait_for_selector("#gate:not([hidden])")
    assert not panel.is_visible()
    assert page.request.get(journey["base"] + f"/api/matters/{matter.id}/loops").status == 401
    assert not page.errors


def test_work_is_attached_to_its_released_response_and_shows_the_historic_dispute_scope(
    page, journey
):
    """Controlled browser fixture: no client loop or paid model is started."""
    matter, record = scoped_work(actor=journey["advocate"], matter_id="linked_browser_scope")
    unlinked = work(
        actor=journey["advocate"], matter_id=matter.id, turn_id="unreleased_browser_work"
    )
    matter = replace(
        matter,
        title="Historic working scope presentation",
        threads=tuple(replace(row, label="Renamed today") for row in matter.threads),
        loop_records=(record, unlinked),
    )
    store = journey["box"].application.store
    store.commit(matter, expected_version=0)
    _sign_in(page, journey)
    _tab(page, "history")
    page.select_option("#history-matter", matter.id)
    turn = page.locator("#history-body .recorded-turn")
    turn.wait_for()
    panel = turn.locator(".recorded-work-progress")
    panel.wait_for()
    assert panel.count() == 1 and not panel.evaluate("node => node.open")
    assert "Recorded work for this response" in panel.inner_text()
    summary = panel.locator(":scope > summary")
    summary.focus()
    page.keyboard.press("Enter")
    stages = panel.locator(".progress-stages li")
    stages.first.wait_for()
    assert stages.count() == len(record.events)
    scope = panel.locator(".progress-scope")
    assert scope.locator("ul li").all_text_contents() == ["One", "Two"]
    assert "not proof of a separate assessment of each dispute" in scope.inner_text()
    assert "Renamed today" not in scope.inner_text()
    assert SECRET not in page.inner_text("body")
    assert record.identity.turn_id not in panel.inner_text()
    summary.click()
    summary.click()
    stages.first.wait_for()
    assert stages.count() == len(record.events)  # Reopen does not duplicate durable frames.
    other = page.locator("#history-body > .recorded-work-progress")
    other.locator(":scope > summary").click()
    other.locator("details > summary").first.wait_for()
    assert other.locator("details").count() == 1  # The attached work is not listed a second time.
    assert not other.get_by_text("Please provide the original document.", exact=True).count()
    _sign_out(page)
    page.wait_for_selector("#gate:not([hidden])")
    assert not panel.is_visible()
    assert (
        page.request.get(
            journey["base"] + f"/api/matters/{matter.id}/loops/{record.identity.turn_id}"
        ).status
        == 401
    )
    assert not page.errors
