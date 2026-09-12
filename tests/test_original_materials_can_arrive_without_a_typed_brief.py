"""P16 scoped browser proof: original receipt and explicit local capture only."""
from __future__ import annotations

import hashlib
import json

import pytest

from tests.test_the_journey_login_to_logout import WIDTHS, _sign_in
from tests.test_the_workspace_respects_its_current_context import (
    _assert_no_overflow,
    _HeldReply,
)
from tests.test_the_workspace_respects_its_current_context import (
    journey as _base_journey,
)
from tests.test_the_workspace_respects_its_current_context import (
    page as _base_page,
)

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page


def _open(page):
    page.click("#materials-open")
    page.wait_for_selector("#materials-dialog[open]")


def _instructions(page):
    page.fill("#materials-purpose", "Retain this synthetic original for advocate review.")
    page.fill("#materials-authority",
              "Synthetic test owner supplies the file; authority remains unverified.")
    page.select_option("#materials-retention", "matter_life")


def _file(name="Original instruction.txt",
          data=b"Synthetic original instruction, not an established fact."):
    return {"name": name, "mimeType": "application/octet-stream", "buffer": data}


def _upload(page, files):
    page.set_input_files("#materials-files", files)
    _instructions(page)
    page.click("#materials-upload")
    page.wait_for_function("""() => !document.querySelector('#materials-upload').disabled
        && document.querySelector('#materials-status').textContent.includes('Original received')""",
        timeout=60000)


def _rows(page, journey):
    matter_id = page.get_attribute("#pane-advise", "data-matter-id")
    assert matter_id
    response = page.request.get(journey["base"] + f"/api/matters/{matter_id}/uploads")
    assert response.status == 200
    return matter_id, response.json()["uploads"]


@pytest.mark.parametrize("width,height", WIDTHS,
                         ids=[f"{width}px" for width, _ in WIDTHS])
def test_original_files_open_a_matter_without_a_placeholder_narrative(
    page, journey, width, height,
):
    _sign_in(page, journey, width, height)
    _open(page)
    _assert_no_overflow(page)
    originals = [_file(), _file("Second supplied file.pdf", b"%PDF- synthetic unvalidated bytes")]
    _upload(page, originals)
    matter_id, rows = _rows(page, journey)
    assert len(rows) == 2
    assert page.input_value("#message") == ""
    assert not any(request["path"] == "/api/turn" for request in page.request_identities)
    matter = journey["box"].application.store.load(matter_id)
    assert matter.title == originals[0]["name"]
    assert not matter.facts and not matter.turns_applied
    saved_by_name = {row["filename"]: row for row in rows}
    assert set(saved_by_name) == {original["name"] for original in originals}
    for supplied in originals:
        row = saved_by_name[supplied["name"]]
        assert row["receipt"]["observed_hash"] == hashlib.sha256(supplied["buffer"]).hexdigest()
        assert row["receipt"]["observed_size"] == len(supplied["buffer"])
        assert row["receipt"]["state"] == "received"
        assert row["state"] == "uploaded" and row["quarantine"] == "not_assessed"
        assert row["may_reach_reasoning"] is False and row["establishes_a_fact"] is False
        assert page.request.get(journey["base"] +
            f"/api/matters/{matter_id}/uploads/{row['asset_id']}/content").status == 423
        # Read through the real sealed-chunk owner, not a second test encoder.
        stored = matter.uploads[row["asset_id"]]
        restored = b"".join(journey["box"].application.uploads.objects.read(
            matter_id, chunk["object_id"]) for chunk in stored["chunks"])
        assert restored == supplied["buffer"]
    assert "not admitted or read" in page.inner_text("#materials-receipts")
    assert "not implemented" in page.inner_text("#materials-dialog").lower()
    _assert_no_overflow(page)
    assert not page.errors, page.errors


def test_upload_needs_explicit_instructions_and_rejects_an_oversized_original(page, journey):
    _sign_in(page, journey)
    _open(page)
    page.set_input_files("#materials-files", _file())
    page.click("#materials-upload")
    assert page.locator("#materials-purpose").evaluate("el => el.validity.valueMissing")
    assert not any("/uploads" in row["path"] or row["path"] == "/api/matters/intake"
                   for row in page.request_identities)
    _instructions(page)
    page.fill("#materials-purpose", "   ")
    page.click("#materials-upload")
    assert "nonblank purpose" in page.inner_text("#materials-status")
    page.evaluate("""() => {
      const files = new DataTransfer();
      files.items.add(new File([new Uint8Array(32 * 1024 * 1024 + 1)], 'too-large.bin'));
      const input = document.querySelector('#materials-files');
      input.files = files.files; input.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    assert "at most 32 MiB" in page.inner_text("#materials-status")
    assert not any(row["method"] in ("PUT", "POST") and "/uploads" in row["path"]
                   for row in page.request_identities)


def _partial(page):
    original = _file("Resumable original.bin", b"x" * (2 * 1024 * 1024 + 19))
    lost = []

    def lose_acknowledgement(route):
        response = route.fetch()
        assert response.status == 200
        assert response.json()["receipt"]["observed_size"] == 1024 * 1024
        lost.append(response.json())
        route.abort()

    page.route("**/uploads/*/chunks/0", lose_acknowledgement, times=1)
    page.set_input_files("#materials-files", original)
    _instructions(page)
    page.click("#materials-upload")
    page.wait_for_function("""() => !document.querySelector('#materials-upload').disabled
        && document.querySelector('#materials-status').textContent
          .includes('Accepted bytes may already be saved')""",
        timeout=60000)
    assert len(lost) == 1
    return original, lost[0]


def _reselect(page, asset_id, original):
    with page.expect_file_chooser() as chooser:
        page.locator(f".materials-receipt[data-asset-id='{asset_id}']").get_by_role(
            "button", name="Reselect original and resume").click()
    chooser.value.set_files(original)


def test_resume_uses_the_server_offset_and_refuses_a_different_reselected_original(page, journey):
    _sign_in(page, journey)
    _open(page)
    original, accepted = _partial(page)
    page.click("#materials-close")
    _open(page)
    row = page.locator(f".materials-receipt[data-asset-id='{accepted['asset_id']}']")
    row.wait_for(state="visible")
    assert "Incomplete" in row.inner_text()
    count_before = sum(request["method"] == "PUT" for request in page.request_identities)
    wrong = {**original, "buffer": b"y" * len(original["buffer"])}
    _reselect(page, accepted["asset_id"], wrong)
    page.wait_for_function("""() => document.querySelector('#materials-status').textContent
        .includes('does not match')""")
    assert sum(request["method"] == "PUT" for request in page.request_identities) == count_before
    _reselect(page, accepted["asset_id"], original)
    page.wait_for_function("""() => !document.querySelector('#materials-upload').disabled
        && document.querySelector('#materials-status').textContent.includes('Original received')""",
        timeout=60000)
    offsets = [int(request["path"].rsplit("/", 1)[1]) for request in page.request_identities
               if request["method"] == "PUT"
               and f"/uploads/{accepted['asset_id']}/chunks/" in request["path"]]
    assert offsets == [0, 1024 * 1024, 2 * 1024 * 1024]
    _, rows = _rows(page, journey)
    [saved] = [item for item in rows if item["asset_id"] == accepted["asset_id"]]
    assert saved["receipt"]["observed_hash"] == hashlib.sha256(original["buffer"]).hexdigest()


def test_cancellation_confirms_retained_bytes_instead_of_claiming_deletion(page, journey):
    _sign_in(page, journey)
    _open(page)
    _, accepted = _partial(page)
    page.click("#materials-refresh")
    row = page.locator(f".materials-receipt[data-asset-id='{accepted['asset_id']}']")
    row.get_by_role("button", name="Cancel this upload").click()
    page.wait_for_function("""() => document.querySelector('#materials-status').textContent
        .includes('Cancellation confirmed')""")
    assert "not deleted" in page.inner_text("#materials-status")
    _, rows = _rows(page, journey)
    [saved] = [item for item in rows if item["asset_id"] == accepted["asset_id"]]
    assert saved["receipt"]["state"] == "cancelled"
    assert saved["receipt"]["observed_size"] == 1024 * 1024


def test_a_late_receipt_list_cannot_undo_confirmed_cancellation(page, journey):
    _sign_in(page, journey)
    _open(page)
    _, accepted = _partial(page)
    matter_id = page.get_attribute("#pane-advise", "data-matter-id")
    held = _HeldReply(page, f"**/api/matters/{matter_id}/uploads")
    page.click("#materials-refresh")
    earlier = held.wait()
    assert earlier["uploads"][0]["receipt"]["state"] == "receiving"
    card = page.locator(f".materials-receipt[data-asset-id='{accepted['asset_id']}']")
    card.get_by_role("button", name="Cancel this upload").click()
    page.wait_for_function("""() => document.querySelector('#materials-status').textContent
        .includes('Cancellation confirmed')""")
    assert "Cancelled" in card.inner_text()
    held.release()
    assert "Cancelled" in card.inner_text()
    assert card.get_by_role("button", name="Reselect original and resume").count() == 0
    assert not page.errors, page.errors


def test_a_crossed_chunk_receipt_cannot_select_the_next_upload_target(page, journey):
    _sign_in(page, journey)
    _open(page)
    crossed = []

    def cross_identity(route):
        response = route.fetch()
        assert response.status == 200
        body = response.json()
        crossed.append(body["asset_id"])
        # Change both internally matching fields: the independent invariant is
        # their agreement with the asset the actual request named.
        body["asset_id"] = "synthetic_other_upload"
        body["receipt"]["upload_id"] = "synthetic_other_upload"
        route.fulfill(response=response, body=json.dumps(body))

    page.route("**/uploads/*/chunks/0", cross_identity, times=1)
    page.set_input_files("#materials-files", _file("Crossed receipt.bin", b"x" * (1024 * 1024 + 7)))
    _instructions(page)
    page.click("#materials-upload")
    page.wait_for_function("""() => !document.querySelector('#materials-upload').disabled
        && document.querySelector('#materials-status').textContent
          .includes('receipt identity or admission state could not be verified')""")
    assert len(crossed) == 1
    writes = [item for item in page.request_identities if item["method"] == "PUT"]
    assert [item["path"].rsplit("/", 1)[1] for item in writes] == ["0"]
    assert all("synthetic_other_upload" not in item["path"] for item in page.request_identities)
    _, rows = _rows(page, journey)
    assert len(rows) == 1
    assert rows[0]["asset_id"] == crossed[0]
    assert rows[0]["receipt"]["observed_size"] == 1024 * 1024
    assert rows[0]["receipt"]["state"] == "receiving"


def test_microphone_permission_is_requested_only_by_the_explicit_record_button(page, journey):
    page.add_init_script("""(() => {
      window.__micCalls = 0;
      Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: {
        getUserMedia: async () => { window.__micCalls += 1;
          throw new DOMException('synthetic permission denial', 'NotAllowedError'); }
      }});
    })()""")
    _sign_in(page, journey)
    _open(page)
    assert page.evaluate("window.__micCalls") == 0
    page.click("#materials-record")
    page.wait_for_function("""() => document.querySelector('#materials-record-state').textContent
        .includes('permission declined')""")
    assert page.evaluate("window.__micCalls") == 1
    assert not any(row["path"] == "/api/matters/intake" or "/uploads" in row["path"]
                   for row in page.request_identities)


@pytest.mark.parametrize("exit_kind", ["dialog_close", "session_expiry"])
def test_local_capture_pauses_stops_and_releases_tracks_and_urls_on_exit(page, journey, exit_kind):
    # No real microphone permission or capture. This deterministic fixture
    # preserves MediaRecorder event order while the actual UI owns all actions.
    page.add_init_script("""(() => {
      window.__captureProbe = {calls: 0, stopped: 0, revoked: 0, recorders: []};
      Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: {
        getUserMedia: async () => { window.__captureProbe.calls += 1;
          return {getTracks: () => [{stop: () => { window.__captureProbe.stopped += 1; }}]}; }
      }});
      window.MediaRecorder = class extends EventTarget {
        static isTypeSupported() { return true; }
        constructor() { super(); this.state = 'inactive'; this.mimeType = 'audio/webm';
          window.__captureProbe.recorders.push(this); }
        start() { this.state = 'recording'; }
        pause() { this.state = 'paused'; }
        resume() { this.state = 'recording'; }
        stop() { this.state = 'inactive'; queueMicrotask(() => {
          this.dispatchEvent(new BlobEvent('dataavailable', {
            data: new Blob(['synthetic audio'], {type: this.mimeType})}));
          this.dispatchEvent(new Event('stop')); }); }
      };
      const revoke = URL.revokeObjectURL.bind(URL);
      URL.revokeObjectURL = url => { window.__captureProbe.revoked += 1; revoke(url); };
    })()""")
    _sign_in(page, journey)
    _open(page)
    _upload(page, [_file("Capture session matter.txt")])
    page.click("#materials-record")
    page.wait_for_function("""() => document.querySelector('#materials-record-state').textContent
        .includes('Recording locally')""")
    page.click("#materials-record-pause")
    assert "paused locally" in page.inner_text("#materials-record-state")
    page.click("#materials-record-pause")
    assert "resumed locally" in page.inner_text("#materials-record-state")
    page.click("#materials-record-stop")
    page.wait_for_selector("#materials-playback:not([hidden])")
    assert page.evaluate("window.__captureProbe.stopped") >= 1
    assert "not been uploaded or transcribed" in page.inner_text("#materials-record-state")
    page.click("#materials-close")
    assert page.locator("#materials-playback").get_attribute("src") is None
    assert page.evaluate("window.__captureProbe.revoked") == 1
    _open(page)
    page.click("#materials-record")
    page.wait_for_function("() => window.__captureProbe.recorders.length === 2")
    # An old recorder's late error must not stop a new recording.
    page.evaluate("() => window.__captureProbe.recorders[0].dispatchEvent(new Event('error'))")
    assert page.evaluate("window.__captureProbe.recorders[1].state") == "recording"
    assert "Recording locally" in page.inner_text("#materials-record-state")
    if exit_kind == "session_expiry":
        ended = journey["box"].directory.close_all_sessions(
            journey["advocate"], "synthetic expiry while recording", except_token="")
        assert ended >= 1
        page.click("#materials-refresh")
        page.wait_for_selector("#gate:not([hidden])")
    else:
        page.click("#materials-close")
    assert not page.locator("#materials-dialog").evaluate("el => el.open")
    assert page.evaluate("window.__captureProbe.stopped") >= 2
    assert page.evaluate("window.__captureProbe.revoked") >= 1
    assert page.locator("#materials-playback").get_attribute("src") is None
    assert page.locator("#materials-selected li").count() == 0
    assert not page.errors, page.errors
