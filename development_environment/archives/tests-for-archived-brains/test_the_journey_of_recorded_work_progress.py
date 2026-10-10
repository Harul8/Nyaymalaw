"""P52 / LB-139: saved working stages are KEPT for review and NEVER SHOWN.

Owner, 28 September 2026, asked whether 'Recorded work for this response' under
replies and 'Other recorded work progress' in History should come off the
screen like 'How this answer was made': "Remove, keep saved".

THE RULE: no page script mounts a recorded-work panel anywhere, and the saved
stages stay sealed with the matter and readable through the owned, authenticated
progress reads. The model is scripted and no loop is started through the
browser; this is presentation and retention, not legal-response quality.
"""

import re
from pathlib import Path

import pytest

from tests.test_saved_work_attaches_only_to_its_released_turn import scoped_work
from tests.test_the_journey_login_to_logout import _sign_in, _sign_out
from tests.test_the_journey_login_to_logout import journey as _base_journey
from tests.test_the_journey_login_to_logout import page as _base_page
from tests.test_the_workspace_respects_its_current_context import _open_by_keyboard

journey = _base_journey
page = _base_page

NM = Path(__file__).resolve().parents[1] / "nm"


@pytest.mark.class_a
def test_no_page_script_mounts_a_recorded_work_panel():
    """The population is every browser script the product serves."""
    # CODE, not comments: the history of why the panels went is written beside
    # where they were, and naming a thing in a comment mounts nothing.
    scripts = {path: re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(encoding="utf8"),
                            flags=re.S)
               for path in NM.rglob("*.js")}
    assert scripts, "no browser scripts were found, so nothing was checked"
    for path, text in scripts.items():
        for mount in ("NMLoopProgress.attach", "attachTurn(", "recorded-work-progress",
                      "Recorded work for this response", "Other recorded work progress"):
            assert mount not in text, f"{path.relative_to(NM)} still mounts {mount!r}"
    progress = (NM / "legal_brain" / "communicate" / "loop-progress.js").read_text(encoding="utf8")
    assert "window.NMLoopProgress = Object.freeze({ stopAll, working });" in progress


@pytest.mark.journey
def test_saved_work_is_kept_for_review_and_never_shown_with_its_response(page, journey):
    """Controlled browser fixture: no client loop or paid model is started."""
    matter, record = scoped_work(actor=journey["advocate"], matter_id="kept_not_shown")
    store = journey["box"].application.store
    store.commit(matter, expected_version=0)
    _sign_in(page, journey)
    _open_by_keyboard(page, matter.id, 1280)
    page.wait_for_function("() => state.matterReady")
    assert page.locator(".recorded-work-progress, details.audit").count() == 0, (
        "a recorded-work panel is on the screen")
    assert "Recorded work" not in page.inner_text("body")

    kept = page.request.get(
        journey["base"] + f"/api/matters/{matter.id}/loops/{record.identity.turn_id}")
    assert kept.status == 200, kept.text()
    assert len(kept.json()["events"]) == len(record.events), (
        "the saved working stages were not kept for review")
    assert not page.errors
    _sign_out(page)
    page.wait_for_selector("#gate:not([hidden])")
    assert page.request.get(
        journey["base"] + f"/api/matters/{matter.id}/loops/{record.identity.turn_id}"
    ).status == 401
