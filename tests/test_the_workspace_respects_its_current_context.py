"""Real-browser context ownership witnesses; approval-only, synthetic and local.

The shared journey owns composition, sign-in and ordinary sending.
These tests hold genuine HTTP replies, not fabricated inter-stage matters.
Deliberate response mutations cover incomplete boards, an explicitly unconfirmed
logout and unavailable transcript read-back. None claims legal-quality or release evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.test_the_journey_login_to_logout import (
    BRIEF,
    WIDTHS,
    _advise,
    _open_account_menu,
    _reach_rail,
    _sign_in,
    _sign_out,
    _start_matter,
    playwright_api,
)
from tests.test_the_journey_login_to_logout import (
    journey as _base_journey,
)

pytestmark = pytest.mark.journey
# Register the existing fixture object unchanged, without an imported name
# colliding with pytest's ordinary function-parameter spelling.
journey = _base_journey
ARTIFACTS = Path(__file__).resolve().parents[1] / ".nm" / "conformance" / "browser"

# Observe native JSON parsing and optionally delay its promise, without changing
# the actual served response or parsed value. Keeping a synchronous Route alive
# after its callback returns is not a supported hold in this browser harness.
_OBSERVE_JSON = """() => {
  window.__workspaceWire = {held: [], consumed: [], parsed: [], gates: []};
  const json = Response.prototype.json;
  Response.prototype.json = function(...args) {
    const result = json.apply(this, args);
    const url = this.url;
    const wire = window.__workspaceWire;
    const path = new URL(url, location.href).pathname;
    const gate = wire.gates.find(item => item.path === path && !item.claimed);
    if (!gate) return result.finally(() => wire.parsed.push(url));
    gate.claimed = true;
    return result.then(value => new Promise(resolve => {
      gate.release = () => {
        wire.parsed.push(url);
        wire.consumed.push(gate.tag);
        resolve(value);
      };
      wire.held.push(gate.tag);
    }), error => {
      wire.parsed.push(url);
      throw error;
    });
  };
}"""


@pytest.fixture
def page(journey, request):
    """Fresh browser; never contact a remote asset; capture every case."""
    with playwright_api.sync_playwright() as driver:
        browser = driver.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = context.new_page()
        pg.add_init_script(f"({_OBSERVE_JSON})()")
        pg.errors = []
        pg.external_assets = []
        pg.request_identities = []
        pg.held_replies = []
        pg.static_assets = []
        pg.asset_navigations = []
        pg.failed_requests = []
        pg.console_errors = []
        asset_responses = []
        inspected_assets = {}
        pg.on("pageerror", lambda error: pg.errors.append(str(error)))
        local_origin = urlsplit(journey["base"]).netloc

        def asset_response(response):
            parsed = urlsplit(response.url)
            if parsed.netloc == local_origin and parsed.path.startswith("/static/"):
                # No body, headers or protocol I/O here. Reading a body in
                # a response callback can re-enter another pending callback.
                asset_responses.append(response)

        def request_failed(req):
            parsed = urlsplit(req.url)
            pg.failed_requests.append({"path": parsed.path,
                                       "resource_type": req.resource_type,
                                       "failure": req.failure})

        def console_error(message):
            if message.type == "error":
                pg.console_errors.append({"text": message.text[:2000],
                                          "location": message.location})

        def inspect_asset(response):
            identity = id(response)
            if identity in inspected_assets:
                return inspected_assets[identity]
            row = {"path": urlsplit(response.url).path, "status": response.status,
                   "resource_type": response.request.resource_type,
                   "body_length": None, "sha256": None}
            try:
                row["content_type"] = response.header_value("content-type")
                content = response.body()
                row["body_length"] = len(content)
                row["sha256"] = hashlib.sha256(content).hexdigest()
            except playwright_api.Error as exc:
                row["read_error"] = str(exc)
            inspected_assets[identity] = row
            pg.static_assets.append(row)
            return row

        def guarded_navigation(navigate, *args, **kwargs):
            start = len(asset_responses)
            response = navigate(*args, **kwargs)
            pg.wait_for_load_state("load")
            # Required assets come from the document under test, not a
            # second hardcoded list of controller filenames. Reads happen
            # after ordinary navigation, never inside an event callback.
            required = pg.locator('script[src], link[rel="stylesheet"][href]').evaluate_all(
                "nodes => nodes.map(el => ({url: el.src || el.href, "
                "kind: el.tagName === 'SCRIPT' ? 'script' : 'stylesheet'}))")
            observed = {item.url: inspect_asset(item) for item in tuple(asset_responses[start:])}
            problems = []
            if not any(item["kind"] == "script" for item in required):
                problems.append("the loaded document declares no required scripts")
            for item in required:
                parsed = urlsplit(item["url"])
                row = observed.get(item["url"])
                if parsed.netloc != local_origin:
                    problems.append(f"required {item['kind']} is not local: {parsed.path}")
                elif row is None:
                    problems.append(f"required asset produced no captured response: {parsed.path}")
                elif row["status"] != 200 or not row["body_length"]:
                    problems.append(f"required asset is not HTTP200 with a nonempty body: {row}")
            pg.asset_navigations.append({
                "path": urlsplit(pg.url).path,
                "required": [{"path": urlsplit(item["url"]).path, "kind": item["kind"]}
                             for item in required],
                "problems": problems,
            })
            assert not problems, "Required local asset delivery failed: " + "; ".join(problems)
            return response

        original_goto, original_reload = pg.goto, pg.reload
        pg.goto = lambda *args, **kwargs: guarded_navigation(original_goto, *args, **kwargs)
        pg.reload = lambda *args, **kwargs: guarded_navigation(original_reload, *args, **kwargs)

        def local_only(route):
            url = urlsplit(route.request.url)
            if url.netloc != local_origin:
                pg.external_assets.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        def record_request(req):
            parsed = urlsplit(req.url)
            identity = {"path": parsed.path, "method": req.method,
                        "resource_type": req.resource_type}
            if parsed.path == "/api/turn" and req.method == "POST":
                body = req.post_data_json
                identity["envelope"] = req.post_data
                identity.update({key: body.get(key) for key in
                                 ("turn_id", "matter_id", "chat_id", "expected_version")})
            pg.request_identities.append(identity)

        context.route("**/*", local_only)
        pg.on("request", record_request)
        pg.on("response", asset_response)
        pg.on("requestfailed", request_failed)
        pg.on("console", console_error)
        try:
            yield pg
        finally:
            ARTIFACTS.mkdir(parents=True, exist_ok=True)
            suffix = hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:10]
            stem = f"{request.node.originalname or request.node.name}-{suffix}"
            capture_errors = []
            # Include later dynamic static loads too, without executing any
            # response-body operation from the callback that observes them.
            for response in tuple(asset_responses):
                inspect_asset(response)
            try:
                pg.screenshot(path=str(ARTIFACTS / f"{stem}.png"), full_page=True)
                (ARTIFACTS / f"{stem}.html").write_text(pg.content(), encoding="utf-8")
            except playwright_api.Error as exc:
                capture_errors.append(str(exc))
            report = getattr(request.node, "rep_call", None)
            (ARTIFACTS / f"{stem}.json").write_text(json.dumps({
                "nodeid": request.node.nodeid,
                "outcome": getattr(report, "outcome", "setup_incomplete"),
                "viewport": pg.viewport_size,
                "requests": pg.request_identities,
                "static_assets": pg.static_assets,
                "asset_navigations": pg.asset_navigations,
                "request_failures": pg.failed_requests,
                "console_errors": pg.console_errors,
                "held_reply_count": len(pg.held_replies),
                "page_errors": pg.errors,
                "external_assets_refused": pg.external_assets,
                "capture_errors": capture_errors,
            }, indent=2), encoding="utf-8")
            for held in pg.held_replies:
                held.abandon()
            context.close()
            browser.close()


class _HeldReply:
    """Delay consumption of a genuine served body, keeping its identity intact."""

    def __init__(self, page, pattern):
        self.page = page
        self.pattern = pattern
        self.path = pattern.removeprefix("**").split("?", 1)[0]
        assert self.path.startswith("/api/") and "*" not in self.path
        self.tag = f"held-{len(page.held_replies)}"
        self.rows = []
        page.held_replies.append(self)
        page.on("response", self._capture)
        self._listening = True
        # Arm before the caller's action. The response event and native JSON
        # promise are distinct signals; neither callback may block on the other.
        self._waiter = page.expect_response(
            lambda response: urlsplit(response.url).path == self.path, timeout=60000)
        self._response = self._waiter.__enter__()
        self._waiter_open = True
        page.evaluate("gate => window.__workspaceWire.gates.push(gate)",
                      {"path": self.path, "tag": self.tag, "claimed": False})

    def _capture(self, response):
        if urlsplit(response.url).path != self.path:
            return
        # NO body/protocol I/O in an event callback. response.json() can pump
        # nested callbacks while the outer browser wait has already completed.
        self.rows.append({"response": response, "released": False})

    def wait(self, status=200):
        """The held reply's body. A message's first reply is its stop for the go-ahead (409, D134), not an answer."""
        response = self._response.value
        if self._waiter_open:
            self._waiter.__exit__(None, None, None)
            self._waiter_open = False
        assert len(self.rows) == 1, "expected one held request, not zero or duplicate sends"
        row = self.rows[0]
        assert row["response"] is response, (
            "the waiter and listener must identify the same response"
        )
        assert response.status == status, response.text()
        if "body" not in row:
            row.update(request=response.request, body=response.json())
        self.page.wait_for_function(
            "tag => window.__workspaceWire.held.includes(tag)", arg=self.tag,
            timeout=60000,
        )
        assert len(self.rows) == 1, "expected one held request, not zero or duplicate sends"
        return self.rows[0]["body"]

    def release(self):
        assert len(self.rows) == 1
        row = self.rows[0]
        assert not row["released"]
        self._stop_listening()
        self.page.evaluate("""tag => {
          const gate = window.__workspaceWire.gates.find(item => item.tag === tag);
          if (!gate || typeof gate.release !== 'function') throw Error('no held body');
          gate.release();
          window.__workspaceWire.gates = window.__workspaceWire.gates.filter(
            item => item.tag !== tag);
        }""", self.tag)
        row["released"] = True
        self.page.wait_for_function(
            "tag => window.__workspaceWire.consumed.includes(tag)", arg=self.tag,
            timeout=15000,
        )
        _rendered(self.page)

    def _stop_listening(self):
        # Release and teardown share this subscription. Removing it twice
        # only appeared harmless when it was the event's final listener;
        # independent asset observers keep the event alive and expose that
        # ownership error. Never remove another observer or swallow errors.
        if self._listening:
            self.page.remove_listener("response", self._capture)
            self._listening = False

    def abandon(self):
        self._stop_listening()
        if self._waiter_open:
            # Exceptional context exit cancels an unclaimed waiter. Never wait
            # for a response or deliver held application promises in teardown.
            error = RuntimeError("held response abandoned during test teardown")
            self._waiter.__exit__(type(error), error, None)
            self._waiter_open = False
        # Closing the context below abandons unresolved test promises. Do not
        # deliver them during teardown: the captured failure must stay intact.


def _rendered(page):
    page.evaluate("() => new Promise(done => requestAnimationFrame("
                  "() => requestAnimationFrame(done)))")


def _new_matter(page, client, width=1280):
    """A new matter with its answer, and its identity. Since the owner's decisions of 15 and 16 Oct 2026 a new matter is a
    conversation the top bar starts, opened on its message box, and its identity is the conversation's id; `client` begins
    its first message, so a later step can find it again in the conversation history."""
    _start_matter(page)
    _advise(page, f"{client}. {BRIEF}")
    # Complete the existing board read before a later test captures a new
    # request to the same route. Otherwise it measures an unrelated reply.
    page.wait_for_function("() => { const status = document.getElementById('board-status');"
                           " return status.hidden || status.textContent === ''; }")
    matter_id = page.evaluate("() => shownChatId()")
    assert matter_id, "the served conversation did not give the file an identity"
    return matter_id


def _all_matters(page, width=1280):
    """The conversation history, opened from the top bar (owner, 15 and 16 Oct 2026: no tabs)."""
    _reach_rail(page, width)
    page.wait_for_function(
        "() => document.querySelector('#rail-title').textContent.trim() === 'Conversation history'"
    )


def _open_by_keyboard(page, matter_id, width=1280, key="Enter"):
    _all_matters(page, width)
    row = page.locator(f"#rail-body .row[data-chat-id='{matter_id}']")
    row.wait_for(state="visible")
    assert row.get_attribute("role") == "button"
    assert row.get_attribute("tabindex") == "0"
    expected_title = row.locator(".r-title").inner_text()
    transcript_path = f"/api/chats/{matter_id}"  # a conversation is read whole by its own route
    parsed_before = page.evaluate("""path => window.__workspaceWire.parsed.filter(
        url => new URL(url, location.href).pathname === path).length""", transcript_path)
    row.focus()
    assert row.evaluate("el => el === document.activeElement")
    row.press(key)
    page.wait_for_function("""({path, before}) =>
        window.__workspaceWire.parsed.filter(
          url => new URL(url, location.href).pathname === path).length > before""",
        arg={"path": transcript_path, "before": parsed_before}, timeout=30000)
    _rendered(page)
    page.wait_for_function("id => shownChatId() === id", arg=matter_id)
    page.wait_for_function(
        "title => (document.querySelector('#thread .thread-title') || {}).textContent === title",
        arg=expected_title,
    )
    # Equal display titles must not make the old file's transcript pass for
    # this one: the exact selected transcript was consumed before these reads.
    page.wait_for_selector("#thread .turn", timeout=30000)


def _kept_messages(page, journey, chat_id):
    """The conversation's messages as it keeps them: each saved turn's, and the one waiting at its stop."""
    chat = page.request.get(journey["base"] + f"/api/chats/{chat_id}").json()
    held = chat.get("pending") or {}
    return [turn.get("message") for turn in chat.get("turns") or []] + ([held["message"]] if held.get("message") else [])


def _assert_fits(page, selector):
    control = page.locator(selector)
    assert control.is_visible(), f"primary control is hidden: {selector}"
    control.scroll_into_view_if_needed()
    geometry = control.bounding_box()
    assert geometry and geometry["width"] > 0 and geometry["height"] > 0
    assert geometry["x"] >= -1 and geometry["x"] + geometry["width"] <= (
        page.viewport_size["width"] + 1
    ), f"primary control is clipped horizontally: {selector}: {geometry}"


def _assert_no_overflow(page):
    assert page.evaluate("() => document.documentElement.scrollWidth <= "
                         "document.documentElement.clientWidth + 1"), (
        f"workspace overflows at {page.viewport_size}"
    )


def _assert_protected_dom_cleared(page):
    assert page.is_visible("#gate") and page.is_hidden("#masthead")
    # The Legal library's search, and a matter's History pane, went with those screens (plan AN.57, D292).
    for selector in ("#thread", "#rail-body", "#sessions-body", "#sessions-action-state"):
        assert not page.text_content(selector).strip(), (
            f"late reply repopulated protected DOM, including hidden content: {selector}"
        )
    assert not page.locator("#sessions-dialog").evaluate("el => el.open")
    assert not page.errors, page.errors


@pytest.mark.parametrize("width,height", WIDTHS,
                         ids=[f"{width}px" for width, _ in WIDTHS])
def test_the_live_workspace_is_local_and_keyboard_navigable_at_each_width(
    page, journey, width, height,
):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(journey["base"] + "/app")
    page.wait_for_selector("#login-go", state="visible")
    assert page.title().strip() and page.evaluate("typeof window.fetch === 'function'")
    _assert_no_overflow(page)
    _assert_fits(page, "#login-go")
    _sign_in(page, journey, width, height)
    first = _new_matter(page, f"First workspace client at {width}px", width)
    second = _new_matter(page, f"Second workspace client at {width}px", width)
    assert first != second
    for matter_id, key in ((first, "Enter"), (second, "Space")):
        _open_by_keyboard(page, matter_id, width, key)
        _assert_fits(page, "#message")
        _assert_fits(page, "#send")
        _assert_no_overflow(page)
    # THE TOP BAR (owner, 15 and 16 Oct 2026: no tabs - a new matter and the conversation history) fits at every width.
    for control in ("#top-new", "#top-history"):
        _assert_fits(page, control)
    _all_matters(page, width)
    _assert_no_overflow(page)
    # A conversation's own files (the board's Files) open, fit the screen and close on Escape; the file icon and its records
    # belong to a matter saved before conversations.
    _open_by_keyboard(page, second, width)
    if page.is_visible("#board-toggle"):          # on a phone the board is behind this button (owner, 16 Oct 2026)
        page.click("#board-toggle")
        page.wait_for_selector("#board-toggle[aria-expanded='true']")
    _assert_fits(page, "#board-files")
    page.click("#board-files")
    page.wait_for_selector("#brain-source-reader[open]")
    _assert_no_overflow(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#brain-source-reader:not([open])", state="attached")
    if width > 820:
        for selector in ("#who-name",):  # the workspace's name beside it was taken off the page
            _assert_fits(page, selector)
    _open_account_menu(page)
    for selector in ("#profile-name", "#profile-workspace", "#devices", "#signout"):
        _assert_fits(page, selector)
    linked_assets = page.locator("link[href], script[src]").evaluate_all("""nodes =>
        nodes.map(el => el.href || el.src).filter(url =>
          new URL(url, location.href).origin !== location.origin)""")
    assert linked_assets == [] and page.external_assets == []
    assert page.request.get(journey["base"] + "/api/health/detail").json()["code_state"] == "current"
    assert not page.errors, page.errors


@pytest.mark.parametrize("keep_rows", [False, True], ids=["empty", "nonempty"])
def test_partial_board_keeps_its_warning_with_or_without_readable_matters(
    page, journey, keep_rows,
):
    _sign_in(page, journey)
    own_id = _new_matter(page, f"Incomplete board {keep_rows}")
    mutations = []

    def incomplete(route):
        response = route.fetch()
        assert response.status == 200
        body = response.json()
        assert body["state"] == "ok" and any(
            row["chat_id"] == own_id for row in body["chats"])
        body["state"] = "partial"
        body["unreadable"] = body["unavailable"] = ["synthetic-unreadable-file"]
        if not keep_rows:
            body["chats"] = []
        # The history lists conversations only (plan AN.48, D307): an earlier matter is neither listed nor counted.
        assert "matters" not in body and "row_count" not in body
        body["row_count"] = len(body["chats"])
        mutations.append(body)
        route.fulfill(response=response, json=body)

    page.route("**/api/work?*", incomplete)  # the conversation history's own list
    _all_matters(page)
    warning = page.locator("#rail-body .unbuildable")
    warning.wait_for(state="visible")
    assert len(mutations) == 1
    assert "incomplete" in warning.inner_text().lower()
    assert "No conversations yet" not in page.inner_text("#rail-body")
    rows = page.locator("#rail-body .row")
    assert rows.count() == mutations[0]["row_count"]
    if keep_rows:
        assert rows.count() > 0
        assert warning.bounding_box()["y"] < rows.first.bounding_box()["y"]
    assert not page.errors, page.errors


def test_a_delayed_turn_cannot_repaint_or_retarget_a_newly_selected_matter(page, journey):
    _sign_in(page, journey)
    selected = _new_matter(page, "Selected file after navigation")
    original = _new_matter(page, "Original file with delayed reply")
    assert original != selected
    held = _HeldReply(page, "**/api/turn")
    delayed_brief = "Please review the original file without changing its stated facts."
    page.fill("#message", delayed_brief)
    page.click("#send")
    answer = held.wait(status=409)
    assert answer["detail"]["chat_id"] == original
    _open_by_keyboard(page, selected)
    selected_heading = page.inner_text("#thread .thread-title")
    following_brief = "Please review the selected file and retain the stated instruction."
    page.fill("#message", following_brief)
    held.release()
    page.wait_for_selector("#send:not([disabled])")
    assert page.evaluate("() => shownChatId()") == selected
    assert page.inner_text("#thread .thread-title") == selected_heading
    assert delayed_brief not in page.text_content("#thread")
    assert page.input_value("#message") == following_brief
    before = len([row for row in page.request_identities if row["path"] == "/api/turn"])
    _advise(page, following_brief)
    turns = [row for row in page.request_identities if row["path"] == "/api/turn"]
    assert len(turns) == before + 1 and turns[-1]["chat_id"] == selected
    assert following_brief in _kept_messages(page, journey, selected)
    assert not page.errors, page.errors


def test_repeated_enter_while_a_turn_is_pending_dispatches_only_once(page, journey):
    _sign_in(page, journey)
    matter_id = _new_matter(page, "One logical send")
    held = _HeldReply(page, "**/api/turn")
    brief = "Keep this instruction once in the file while the response is delayed."
    before = len([row for row in page.request_identities if row["path"] == "/api/turn"])
    page.fill("#message", brief)
    page.press("#message", "Enter")
    held.wait(status=409)
    page.press("#message", "Enter")
    page.press("#message", "Enter")
    _rendered(page)
    turns = [row for row in page.request_identities if row["path"] == "/api/turn"]
    assert len(turns) == before + 1 and turns[-1]["chat_id"] == matter_id
    assert len(held.rows) == 1
    held.release()
    page.wait_for_selector("#send:not([disabled])")
    assert _kept_messages(page, journey, matter_id).count(brief) == 1
    assert not page.errors, page.errors


# A matter's History pane, a third surface here, went with the screens of a matter saved before conversations (plan AN.57, D292).
@pytest.mark.parametrize("surface", ["history_list", "sessions"])
def test_late_authenticated_responses_cannot_repopulate_dom_after_logout(
    page, journey, surface,
):
    _sign_in(page, journey)
    _new_matter(page, f"Protected {surface} workspace")
    if surface == "history_list":
        held = _HeldReply(page, "**/api/work?*")  # the conversation history's own list
        _all_matters(page)
        assert held.wait()["chat_count"] > 0
    else:
        held = _HeldReply(page, "**/api/sessions")
        _open_account_menu(page)
        page.click("#devices")
        assert held.wait()["sessions"], "the live session population cannot be empty"
        page.click("#sessions-close")
    _sign_out(page)
    page.wait_for_selector("#gate:not([hidden])")
    _assert_protected_dom_cleared(page)
    held.release()
    _assert_protected_dom_cleared(page)
    assert page.request.get(journey["base"] + "/api/session").status == 401


def test_a_pending_answer_can_rejoin_its_own_reopened_context(page, journey):
    _sign_in(page, journey)
    original = _new_matter(page, "Return to pending instruction")
    other = _new_matter(page, "Other file while waiting")
    _open_by_keyboard(page, original)
    held = _HeldReply(page, "**/api/turn")
    brief = "Finish this instruction only in its original file after I return."
    page.fill("#message", brief)
    page.press("#message", "Enter")
    assert held.wait(status=409)["detail"]["chat_id"] == original
    _open_by_keyboard(page, other)
    _open_by_keyboard(page, original)
    # The in-flight message is shown as NM working in its own reopened conversation, its words once: Send is the ring while NM
    # works (D74-D76, D173). (The words of the earlier working line are not drawn since the turn's progress replaced it.)
    page.wait_for_function("() => document.getElementById('send').dataset.state === 'working'")
    assert page.locator("#thread .brief").filter(has_text=brief).count() == 1
    held.release()
    page.wait_for_selector("#send:not([disabled])")
    assert page.evaluate("() => shownChatId()") == original
    assert page.input_value("#message") == ""
    assert page.locator("#thread .brief").filter(has_text=brief).count() == 1
    assert not page.errors, page.errors


def _sign_in_without_reloading(page, journey):
    """Reauthentication must preserve the actual document's in-memory intent."""
    page.fill("#login-id", journey["advocate"])
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)


# The opening form's draft-key waits went with that form (plan AN.57, D292).


def test_drafts_and_unsubmitted_intake_belong_to_the_selected_file(page, journey):
    _sign_in(page, journey)
    first = _new_matter(page, "Draft isolation first")
    second = _new_matter(page, "Draft isolation second")
    first_text = "First file's unsent private instruction."
    second_text = "Second file's different unsent instruction."
    _open_by_keyboard(page, first)
    page.fill("#message", first_text)
    _open_by_keyboard(page, second)
    assert page.input_value("#message") == ""
    page.fill("#message", second_text)
    _open_by_keyboard(page, first)
    assert page.input_value("#message") == first_text
    _open_by_keyboard(page, second)
    assert page.input_value("#message") == second_text

    # A new conversation's message box starts empty, and the first's draft is still its own. (The opening form's unsubmitted
    # fields are not reached since the owner's decisions of 15 and 16 Oct 2026.)
    _start_matter(page)
    assert page.input_value("#message") == ""
    _open_by_keyboard(page, first)
    assert page.input_value("#message") == first_text
    assert not page.errors, page.errors


# A matter's transcript read-back and History pane went with its screens (plan AN.57, D292); an expired session keeping a
# message's exact envelope for one retry is driven for the conversation by
# tests/test_the_journey_of_a_lost_reply_across_an_expired_session.py.


@pytest.mark.parametrize("retry_in_flight", [False, True])
def test_a_retired_logout_cannot_end_a_new_login(page, journey, retry_in_flight):
    _sign_in(page, journey)

    def unconfirmed(route):
        route.fulfill(status=200, json={"signed_out": False, "outcome": "unknown"})

    page.route("**/api/logout", unconfirmed)
    _sign_out(page)
    page.wait_for_selector("#login-state .loud")
    assert page.request.get(journey["base"] + "/api/session").status == 200
    page.unroute("**/api/logout", unconfirmed)
    if retry_in_flight:
        held = _HeldReply(page, "**/api/logout")
        page.get_by_role("button", name="Try to end the session again").click()
        assert held.wait()["signed_out"] is True
        before = sum(r["path"] == "/api/login" for r in page.request_identities)
        page.fill("#login-id", journey["advocate"])
        page.fill("#login-password", journey["password"])
        page.click("#login-go")
        _rendered(page)
        assert sum(r["path"] == "/api/login" for r in page.request_identities) == before
        held.release()
        page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    else:
        _sign_in_without_reloading(page, journey)
    logout_count = sum(r["path"] == "/api/logout" for r in page.request_identities)
    page.evaluate("() => window.dispatchEvent(new Event('online'))")
    _rendered(page)
    assert sum(r["path"] == "/api/logout" for r in page.request_identities) == logout_count
    assert page.request.get(journey["base"] + "/api/session").status == 200
    assert page.is_visible("#masthead") and page.is_hidden("#gate")
    assert not page.errors, page.errors


def test_http_success_without_revocation_confirmation_stays_unconfirmed(page, journey):
    _sign_in(page, journey)
    requests = []

    def unconfirmed(route):
        requests.append(route.request.method)
        # Do not forward: the actual local session deliberately remains live.
        route.fulfill(status=200, json={"signed_out": False, "outcome": "unknown"})

    page.route("**/api/logout", unconfirmed)
    _sign_out(page)
    page.wait_for_selector("#login-state .loud")
    assert requests == ["POST"]
    assert "may still be signed in" in page.inner_text("#login-state").lower()
    assert page.get_by_role("button", name="Try to end the session again").is_visible()
    _assert_protected_dom_cleared(page)
    assert page.request.get(journey["base"] + "/api/session").status == 200
    page.unroute("**/api/logout", unconfirmed)
    page.get_by_role("button", name="Try to end the session again").click()
    page.wait_for_function("() => document.querySelector('#login-state').textContent"
                           ".includes('session is now closed on the server')")
    assert page.request.get(journey["base"] + "/api/session").status == 401


# A protective (emergency) declaration was a matter's record, deleted with the screens of a matter saved before
# conversations (plan AN.57, D292).
