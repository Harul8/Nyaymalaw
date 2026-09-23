"""BK-30 — the journey an advocate actually walks, in a real browser.

WHAT THIS EXISTS TO REPLACE
-----------------------------
`tests/test_the_page_and_the_script_agree.py` says in its own docstring that it
does not run the page, and it is right to: two files disagreeing about an
element name is a text problem. But that left responsive navigation, matter
restoration, session expiry and a failed logout outside every executable
contract in this repository — and those are where the measured defects were.

The rule the whole repo turns on is CLAUDE.md §8: *verify on the bytes, not the
return value.* Forty of forty offline tests passed while every served turn
crashed. This is that rule applied one layer further out — the served path was
the boundary then, and the PAGE is the boundary now.

WHAT A FAILING PHASE MEANS, AND WHY SOME ARE `xfail`
------------------------------------------------------
Wave 0's release gate is *"current browser counterexamples fail for the stated
reasons"*. So the phases that reproduce a known, unfixed row are marked
`xfail(strict=True)` and NAME that row. Strict is the whole point: the day
BK-32 lands, the phase passes, and a strict xfail that passes is an ERROR
telling you to delete the marker. A defect recorded this way cannot be quietly
fixed and cannot be quietly forgotten.

An `xfail` here is therefore not a skip. The browser really runs, the
assertion really executes, and the failure is really reproduced — which is
exactly what BK-30 was opened to produce.

WHY THE SERVER RUNS IN THIS PROCESS
-------------------------------------
`assurance/journeys/served.running` starts the real composition root on a real port in a
thread, so the suite holds the same store the browser is writing to. A
subprocess would leave every phase asserting on what the screen said, and a
product that renders a correct answer and persists nothing would pass its own
journey.
"""
from __future__ import annotations

import json
import pathlib
import re
import urllib.request

import pytest

pytestmark = pytest.mark.journey

playwright_api = pytest.importorskip(
    "playwright.sync_api",
    reason="the journey suite needs a browser: pip install -e .[journey] "
           "&& python -m playwright install chromium")

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".nm" / "journey"

BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023. Nothing has been paid.")

#: A brief whose period has certainly run, whatever Article is retrieved. The
#: case BK-35 exists for: the step must not send the advocate at a window the
#: same answer says is gone.
EXPIRED = ("We act for the plaintiff at Hyderabad. Goods were supplied "
           "against invoices on 14 March 2009. Nothing has been paid.")

#: The widths BK-30 names. 390 is a phone, 768 a tablet in portrait, 1280 a
#: laptop. The product's own breakpoint is 820px, so 768 is on the narrow side
#: of it and 1280 on the wide side -- the pair that actually tests the rule
#: rather than two points on the same side of it.
WIDTHS = ((390, 844), (768, 1024), (1280, 900))


# ------------------------------------------------------------- the fixtures ---

@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    """The product on a real port, with one enrolled advocate."""
    import sys

    sys.path.insert(0, str(ROOT))

    sys.path.insert(0, str(ROOT / "backend"))
    from assurance.journeys.served import PASSWORD, running

    root = tmp_path_factory.mktemp("journey")
    with running(root) as (box, base):
        advocate = box.enrol()
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD}


@pytest.fixture
def page(journey, request):
    """A fresh browser page, with an artifact written for any failed phase."""
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = context.new_page()
        # CONSOLE ERRORS ARE COLLECTED, not ignored. A page that throws in a
        # submit handler does nothing visible, which is the exact failure
        # `test_the_page_and_the_script_agree` was written after.
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.errors = errors
        try:
            yield pg
        finally:
            # `rep_call` is set by the makereport hook in `conftest.py`.
            # `getattr` because a phase that errored in SETUP never reaches
            # the call phase, and an artifact is worth having for that too.
            report = getattr(request.node, "rep_call", None)
            # AN XFAIL IS EVIDENCE, NOT A SKIP. Wave 0's release gate is that
            # the current counterexamples fail FOR THE STATED REASONS and the
            # artifacts are reviewable -- so a reproduced BK-32 or BK-40 is
            # exactly the screenshot somebody needs to look at. `report.failed`
            # is False for an xfail (its outcome is `skipped`), so capturing on
            # failure alone would throw away the only phases that currently
            # have something to show.
            if (report is None or report.failed
                    or hasattr(report, "wasxfail")):
                ARTIFACTS.mkdir(parents=True, exist_ok=True)
                stem = request.node.name.replace("/", "_")[:80]
                try:
                    pg.screenshot(path=str(ARTIFACTS / f"{stem}.png"),
                                  full_page=True)
                    (ARTIFACTS / f"{stem}.html").write_text(
                        pg.content(), encoding="utf-8")
                except Exception:  # noqa: BLE001 -- an artifact is best effort
                    pass
            context.close()
            browser.close()


def _sign_in(page, journey, width=1280, height=900):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(journey["base"] + "/")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    page.fill("#login-id", journey["advocate"])
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    return page


def _open_matter(page, journey, client=None, **kw):
    """Sign in and answer intake -- the state every later phase needs.

    `client` NAMES THE MATTER, and a phase that has to find its own file
    later must pass one. The server is module-scoped and every phase adds a
    matter to the same advocate's list, so "the first row" is whichever
    matter sorted first -- not the one this phase just opened. Phase 9 read
    that as the restore being broken when it was the click.
    """
    _sign_in(page, journey, **kw)
    # F-B-01. A NEW MATTER STARTS FROM HOME, on the intake form alone.
    _start_matter(page)
    _intake(page, client=client or "Ramesh Traders")
    return page


def _intake(page, client="Ramesh Traders", adverse="Kiran Steels",
            scope="recover the price of goods sold"):
    """Answer the intake form, if it is up. B3-B5.

    THE PRODUCT ASKS BEFORE IT WORKS, so the journey has to answer before it
    briefs -- exactly as an advocate does. A helper rather than a phase of its
    own because every later phase needs a workable matter, and a suite that
    re-typed this eleven times would be testing the form eleven times and the
    rest of the journey never.
    """
    if page.is_hidden("#intake"):
        return
    page.fill("#in-client", client)
    # The approved opening form uses progressive disclosure, not mandatory
    # opponent/capacity fields. This journey deliberately supplies both.
    if page.is_hidden("#in-adverse"):
        page.get_by_text("Other parties", exact=True).click()
    page.fill("#in-adverse", adverse)
    page.fill("#in-scope", scope)
    if page.is_hidden("#in-capacity"):
        page.get_by_text("Who is giving instructions?", exact=True).click()
    page.check("#in-capacity")
    page.click("#in-go")
    # `state="hidden"`, NOT the default. `wait_for_selector("#intake
    # [hidden]")` waits for that element to become VISIBLE, and an
    # element selected BY being hidden never will -- so the wait timed
    # out on a form that had closed correctly.
    page.wait_for_selector("#intake", state="hidden", timeout=10000)
    # F-B-01: the chat opens once the server has saved the matter.
    page.wait_for_selector("#composer:not([hidden])", timeout=15000)


def _start_matter(page):
    """Start a new matter the only way there is: Home's Start a matter (F-B-01)."""
    if page.is_hidden("#pane-home"):
        page.click("#tabs button[data-tab='home']")
        page.wait_for_selector("#pane-home:not([hidden])", timeout=15000)
    page.click("#home-start")
    page.wait_for_selector("#intake:not([hidden])", timeout=15000)


def _advise(page, message: str):
    """Send a brief and WAIT FOR THE TURN TO FINISH DRAWING.

    This waited for `.turn` alone, which appears the moment the card is
    created -- before the elements, the gate rows and the trace line are in
    it. Every phase that read the page after it was therefore asserting
    against a half-drawn answer, and one of them proved it: phase 5b asserts
    that gate ids are on the screen (they are -- `G-DUTY`, `G-UNSCREENED`,
    `G-CONSISTENT`), and it XPASSED, because the text it read had none of
    them yet.

    A check that reads the page too early does not fail. It passes, quietly,
    on less than it claims to have looked at. The completion signal is the
    actual send control becoming enabled again; matching English text was
    never a state transition and did not even match the Unicode ellipsis the
    page renders.
    """
    page.fill("#message", message)
    page.click("#send")
    page.wait_for_selector(".turn", timeout=60000)
    page.wait_for_selector("#send:not([disabled])", timeout=90000)
    assert page.inner_text("#send") == "Send"


def _reach_rail(page, width):
    """Get the matter navigator on screen, however this width offers it.

    THE RULE IS REACHABLE, NOT VISIBLE (BK-32). Below 820px the rail is a
    drawer behind `#matters-toggle`; above it, it is simply there. A phase
    that asserted the rail was visible would fail on a correct drawer, and a
    phase that returned early when it WAS visible asserted nothing at desktop
    -- which is what BK-47 was.
    """
    # F-A-17/F-A-18. THE RAIL LIVES IN MY WORK, and a sign-in lands on Home, so
    # the navigator is reached through the ribbon's My work tab first.
    if page.is_hidden("#pane-advise"):
        page.click("#tabs button[data-tab='advise']")
        page.wait_for_selector("#pane-advise:not([hidden])", timeout=15000)
    # ASK THE TOGGLE, NOT THE RAIL. `is_visible("#rail")` is TRUE at every
    # width, because below 820px the drawer is moved off-screen rather than
    # removed -- so this returned early at 390px and 768px and never opened
    # anything. The narrow-width branch below had therefore never run, which
    # makes BK-47 worse than it was recorded: not "asserts nothing at
    # desktop" but asserts nothing at ANY width.
    #
    # `aria-expanded` is the product's own published state, and it is the
    # accessible truth rather than a guess from geometry.
    toggle = page.locator("#matters-toggle")
    if toggle.count() and toggle.is_visible():
        if toggle.get_attribute("aria-expanded") == "true":
            return
    elif page.is_visible("#rail"):
        return                          # no drawer at this width; it is just there
    assert toggle.is_visible(), (
        f"at {width}px the rail is not shown and no control opens it, so an "
        f"advocate can work the matter they are in and reach no other one")
    toggle.click()
    page.wait_for_selector("#rail", state="visible", timeout=10000)
    assert page.is_visible("#rail"), (
        f"at {width}px the control opened nothing")


def _visible_text(page) -> str:
    return page.inner_text("body")


def _tab(page, name: str):
    """Switch panes and WAIT FOR THE PANE, never for a fixed number of ms.

    This was `click(...)` then `wait_for_timeout(2000)`, and phase 8 failed
    once in three runs with the History pane still carrying `hidden` in the
    saved artifact. A sleep long enough on this machine is the flake that
    fails on a slower one -- and worse, it makes a real defect and a slow
    render indistinguishable, which is the whole failure mode this repository
    keeps recording.

    F-A-17. Home, My work, Legal library and Preparation are the ribbon's tabs.
    Case file and History are offered inside My work for the matter that is
    open, so they are reached there -- opening the first matter on the list
    when none is open, as an advocate would have to.
    """
    if name in ("casefile", "history"):
        if page.is_hidden("#pane-advise"):
            page.click("#tabs button[data-tab='advise']")
            page.wait_for_selector("#pane-advise:not([hidden])", timeout=15000)
        link = page.locator(f"#work-links button[data-tab='{name}']")
        if not link.is_visible():
            _reach_rail(page, page.viewport_size["width"])
            page.locator("#rail-body .row[data-matter-id]").first.click()
            link.wait_for(state="visible", timeout=15000)
        link.click()
    else:
        page.click(f"#tabs button[data-tab='{name}']")
    page.wait_for_selector(f"#pane-{name}:not([hidden])", timeout=15000)


def _open_account_menu(page):
    """The person menu (F-A-17): the profile, signed-in devices and Sign out."""
    if page.is_hidden("#account-panel"):
        page.click("#account-toggle")
        page.wait_for_selector("#account-panel:not([hidden])", timeout=10000)


def _sign_out(page):
    """Sign out from the person menu, where the control lives (F-A-17)."""
    _open_account_menu(page)
    page.click("#signout")


# ==================================================== 1. the door ============

def test_phase_1_an_advocate_signs_in_and_the_gate_gives_way(page, journey):
    """The gate closes and the application appears, with an identity on it."""
    _sign_in(page, journey)

    assert page.is_hidden("#gate")
    assert page.inner_text("#who-name").strip(), "signed in as nobody"
    assert not page.errors, f"the page threw: {page.errors}"


def test_phase_2_the_landing_is_not_blank_but_authenticated(page, journey):
    """BLANK-BUT-AUTHENTICATED IS A NAMED FAILURE in BK-30's acceptance.

    An advocate who has just proved who they are and is shown an empty
    rectangle has no way to tell a working product with no matters from a
    broken one. Either their matters are listed, or there is a control that
    starts one -- and the check is on VISIBLE TEXT, because an element that
    exists and renders nothing is the defect.
    """
    _sign_in(page, journey)
    shown = _visible_text(page).strip()

    assert len(shown) > 40, f"the landing shows almost nothing: {shown!r}"
    # F-A-18: the landing is Home, and its one button starts a matter.
    assert page.is_visible("#home-start") or page.is_visible("#message"), (
        "nothing on the landing lets the advocate begin")


# ============================================ 3. the navigator, three widths ==

@pytest.mark.parametrize("width,height", WIDTHS,
                         ids=[f"{w}px" for w, _ in WIDTHS])
def test_phase_3_the_matter_navigator_is_reachable_at_every_width(
        page, journey, width, height):
    """THE COUNTEREXAMPLE BK-32 IS OPEN FOR, reproduced rather than described.

    `frontend/app.css` line 308: `@media (max-width: 820px) { .rail {display:none} }`
    The rail IS the matter navigator, and below 820px there is no other way to
    reach the list -- `#back` returns to it, but only from inside a matter.

    So an advocate on a phone can work the matter they are in and cannot get
    to any other one. This asserts the rule -- the navigator is REACHABLE, by
    some control, at every width -- rather than asserting the rail is visible,
    because a drawer, a tab or a menu would all satisfy it.
    """
    # AND IT NO LONGER RETURNS AT DESKTOP. BK-47.
    #
    # This read `if page.is_visible("#rail"): return`, so at 1280px the phase
    # asserted nothing at all past sign-in -- one of the three widths it is
    # parameterised over was doing no work. BK-32's acceptance is that the
    # advocate can START, FIND and SWITCH matters and reach Search, History,
    # identity and sign-out at every width, and reachability of the rail is
    # the first step of that, not the whole of it.
    #
    # (The version before THAT called `pytest.xfail(...)` whenever
    # `width < 820`, so the phase could never pass however the product
    # changed -- S11, a check that cannot fail wearing the costume of one
    # that does. Both are the same defect at different depths: an assertion
    # that does not run.)
    # THE RULE THIS PHASE PROVES is that the advocate can reach the
    # navigator, FIND a file in it and OPEN it, and still reach Search,
    # History, their identity and the way out -- at every width. BK-32.
    #
    # TWO FILES ARE CREATED IN THIS PHASE. A module-scoped store populated by
    # earlier phases proves only that some row opens, not that THIS phase can
    # switch away from the matter it just worked. The ids on the rendered
    # rows are the observable identity: similar client names cannot make a
    # same-file click look like a switch.
    _open_matter(page, journey, client=f"Width {width} First Traders",
                 width=width, height=height)
    _advise(page, BRIEF)
    first = page.get_attribute("#pane-advise", "data-matter-id")
    assert first, f"at {width}px the first matter has no rendered identity"

    _start_matter(page)
    _intake(page, client=f"Width {width} Second Traders")
    _advise(page, BRIEF)
    second = page.get_attribute("#pane-advise", "data-matter-id")
    assert second and second != first, (
        f"at {width}px two briefs resolved to the same matter: {second!r}")

    # ---- 1. the navigator is REACHABLE, not necessarily VISIBLE ----------
    # A drawer, a tab or a menu all satisfy the rule; the rail being on
    # screen at 1280px is one way of many.
    _reach_rail(page, width)

    # ---- 2. it LISTS files, and one of them OPENS --------------------
    if page.is_visible("#back"):
        page.click("#back")
        page.wait_for_function(
            "() => document.querySelector('#rail-title')"
            ".textContent.trim() === 'Matters'", timeout=15000)

    # WAIT FOR THE ROWS, NOT FOR THE TITLE. `showMatterList` sets
    # `#rail-title` to "Matters" and THEN awaits `/api/matters`, so a phase
    # that waited on the title asserted against a list still showing
    # "Loading matters..." and reported an empty navigator on a product that
    # was about to render one.
    try:
        page.wait_for_selector("#rail-body .row", timeout=15000)
    except Exception as exc:
        raise AssertionError(
            f"at {width}px the navigator lists no files at all, so an "
            f"advocate has no way to any matter but the one they are in: "
            f"{page.inner_text('#rail-body')[:200]!r}") from exc
    target = page.locator(f'#rail-body .row[data-matter-id="{first}"]')
    assert target.count() == 1, (
        f"at {width}px the first of two newly-created matters cannot be found")
    target.scroll_into_view_if_needed()
    target.click()
    page.wait_for_function(
        "() => document.querySelector('#rail-title')"
        ".textContent.trim() === 'Matter board'", timeout=15000)
    # `arg=`, BY KEYWORD. Playwright's Python API takes the argument by
    # keyword only, and the positional form raised TypeError on every width
    # the moment the installed version enforced it -- a harness failure that
    # read, in the summary line, exactly like a product one.
    page.wait_for_function(
        "expected => document.querySelector('#pane-advise').dataset.matterId "
        "=== expected", arg=first, timeout=15000)
    assert page.get_attribute("#pane-advise", "data-matter-id") != second, (
        f"at {width}px clicking another row left the same matter open")
    page.wait_for_selector("#thread .el > p.body", timeout=30000)
    assert f"Width {width} First Traders" in page.inner_text("#matter-heading")
    assert "Goods were supplied" in page.inner_text("#thread")
    assert not page.errors, f"at {width}px opening a file threw: {page.errors}"

    # ---- 4. TRAVERSE the rest of the application at this width -----------
    for tab in ("search", "history", "advise"):
        _tab(page, tab)
        assert not page.errors, (
            f"at {width}px the page threw switching to {tab}: {page.errors}")

    # ---- 5. identity and the way out are both REACHABLE ------------------
    # F-A-17: in the person menu at every width (and beside it above 820px).
    _open_account_menu(page)
    who = page.locator("#profile-name")
    assert who.is_visible() and who.inner_text().strip() not in ("", "—"), (
        f"at {width}px the advocate cannot see whose session this is, so a "
        f"shared machine gives them nothing to check before they type")
    assert page.locator("#signout").is_visible(), (
        f"at {width}px there is no way to sign out, and an advocate who "
        f"cannot leave a session on a borrowed device has no protection")


# ================================================= 4. keyboard-only working ==

def test_phase_4_a_brief_can_be_filed_without_a_mouse(page, journey):
    """Keyboard-only, because an advocate dictating or on a laptop trackpad
    is not an accessibility edge case -- it is the ordinary way a long brief
    gets typed."""
    _sign_in(page, journey)
    # F-A-18. A SIGN-IN LANDS ON HOME, and Home's one button starts the matter.
    page.wait_for_selector("#pane-home:not([hidden])", timeout=15000)
    assert page.is_hidden("#pane-advise"), "this phase must begin at the actual Home page"

    def active_id():
        return page.evaluate("() => document.activeElement.id")

    # Real Tab navigation proves reachability; focus() would bypass a broken
    # tab order. Authentication above is setup; every action from Home on
    # uses keys, including activating the new-matter and intake controls.
    for _ in range(64):
        if active_id() == "home-start":
            break
        page.keyboard.press("Tab")
    assert active_id() == "home-start", "Home's Start a matter control is not keyboard reachable"
    assert page.is_visible("#home-start")
    page.keyboard.press("Enter")
    page.wait_for_selector("#intake:not([hidden])", timeout=15000)
    assert active_id() == "in-client"
    client_name = "Keyboard Synthetic Client"
    adverse_name = "Keyboard Synthetic Opponent"
    scope = "Review the supplied invoice and advise on recovery"
    page.keyboard.type(client_name)
    page.keyboard.press("Tab")
    assert active_id() == "in-client-type"
    page.keyboard.press("Tab")
    assert active_id() == "in-scope"
    page.keyboard.type(scope)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent") == "Who is giving instructions?"
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    assert active_id() == "in-instructing"
    page.keyboard.press("Tab")
    assert active_id() == "in-capacity"
    page.keyboard.press("Space")
    assert page.is_checked("#in-capacity")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent") == "Other parties"
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    assert active_id() == "in-other-state"
    page.keyboard.press("ArrowDown")
    assert page.input_value("#in-other-state") == "identified"
    page.keyboard.press("Tab")
    assert active_id() == "in-adverse"
    page.keyboard.type(adverse_name)
    page.keyboard.press("Tab")
    assert active_id() == "in-others"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent") == "Current position"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.textContent") == "Anything time-sensitive?"
    page.keyboard.press("Tab")
    assert active_id() == "in-go"
    page.keyboard.press("Enter")
    page.wait_for_selector("#intake", state="hidden", timeout=15000)
    page.wait_for_function("document.activeElement.id === 'message'")
    assert active_id() == "message"
    page.keyboard.type(BRIEF)
    # The composer is a form: Enter submits from a focused control. If it does
    # not, the advocate must reach for the mouse to send a brief they just
    # typed with both hands.
    # NO MOUSE FALLBACK. This used to catch the timeout, click `#send`, and
    # call `pytest.xfail(...)` -- which reports the defect but can never XPASS,
    # because an imperative xfail only fires on the branch that takes it. The
    # marker above is strict, so the day Ctrl+Enter works this phase XPASSes
    # and the runner says to remove it. BK-44.
    with page.expect_response(lambda reply: reply.url.endswith("/api/turn")
                              and reply.request.method == "POST", timeout=90000) as sent:
        page.keyboard.press("Control+Enter")
    response = sent.value
    assert response.status == 200, response.text()
    answer = response.json()
    assert answer["route"] == "matter"
    assert answer["turn_id"] and answer["matter_id"]
    assert answer["committed"] == "committed" and answer["input_admitted"] is True
    assert answer["elements"], "a keyboard submit must release an actual nonempty answer"
    page.wait_for_selector("#send:not([disabled])", timeout=90000)
    page.wait_for_selector("#thread .el > p.body", timeout=30000)
    assert BRIEF in page.inner_text("#thread")
    assert page.input_value("#message") == ""
    assert page.get_attribute("#pane-advise", "data-matter-id") == answer["matter_id"]

    from nm.domain.turn_receipt import release_index

    saved = journey["box"].application.store.load(answer["matter_id"])
    assert saved is not None and saved.advocate_id == journey["advocate"]
    assert saved.intake_parties == {client_name: "client", adverse_name: "adverse"}
    assert saved.intake_answers["scope"]["answer"] == scope
    assert saved.intake_answers["capacity"]["state"] == "not_in_doubt"
    assert saved.intake_answers["capacity"]["raised_by"] == journey["advocate"]
    receipts, problems = release_index(saved)
    assert not problems and len(receipts) == 1
    receipt = receipts[answer["turn_id"]]
    assert saved.turns_applied.count(answer["turn_id"]) == 1
    assert receipt.message == BRIEF and receipt.input_admitted is True
    assert receipt.validated_answer().elements
    held = receipt.answer["elements"]
    assert len(held) == len(answer["elements"])
    from nm.domain.source_excerpt import SourceExcerpt

    for recorded, served in zip(held, answer["elements"], strict=True):
        recorded = dict(recorded)
        # THE SOURCE IS SERVED AS ITS HEADER. The receipt keeps the whole
        # excerpt, because the saved-source reader pages its text from there;
        # the chat carries identity only (`SourceExcerpt.header`). What must
        # hold is that the header served IS the header of what was recorded.
        if recorded.get("source"):
            recorded["source"] = SourceExcerpt(**recorded["source"]).header()
        assert {key: recorded[key] for key in served} == served
    assert not page.errors, f"the page threw: {page.errors}"


# =============================================== 5. what the answer may say ==

def test_phase_5_no_internal_identifier_or_raw_trace_reaches_the_screen(
        page, journey):
    """TWO OF BK-30'S NAMED FAILURES, checked on the rendered page.

    `tests/test_no_internal_id_reaches_the_advocate.py` owns the pattern and
    drives ONE scripted conversation through the engine. This is the same rule
    at the outer boundary, over everything actually painted -- which is the
    population J-5 says that sweep is missing.
    """
    from tests.test_no_internal_id_reaches_the_advocate import INTERNAL_ID

    _open_matter(page, journey)
    _advise(page, BRIEF)
    shown = _visible_text(page)

    leaked = INTERNAL_ID.findall(shown)
    assert not leaked, (
        f"these of this product's own keys are on the advocate's screen: "
        f"{sorted(set(leaked))}")

    # A CRASH IS NEVER SHOWN. Separate from the raw-trace question below,
    # because a traceback on an advocate's screen is not a register problem.
    for token in ("Traceback", "x-nm-read", "AttributeError"):
        assert token not in shown, (
            f"{token!r} is on the advocate's screen")


def test_phase_5b_the_answer_does_not_speak_engineering(page, journey):
    """J-7, CLOSED. The working is present, checkable, and out of the way.

    WHAT WAS MEASURED: `G-DUTY · clear`, `G-UNSCREENED · unscreened`,
    `G-CONSISTENT · consistent` and `outcome ok · latency 69ms · calls 15 ·
    tokens 6860/606 · cost $0.000000 · violations 1` sat under every answer.
    An advocate cannot act on `G-UNSCREENED`, and the sentence beside it
    already says what it means.

    THIS PHASE ASSERTS BOTH HALVES, and the second is the one that stops the
    fix being a deletion. Engineering vocabulary is not on the screen; open
    the working and it is all still there. A product that had simply stopped
    recording gate states would pass the first assertion and fail the second,
    and it would be a worse product than the one that showed them.

    IT ALSO REPLACES A CHECK THAT HAD STARTED FAILING FOR THE WRONG REASON.
    The first version waited for `.gates` to be VISIBLE; once the working
    moved behind a closed `<details>` that wait timed out, the xfail went on
    passing, and a defect that had been fixed would have stayed recorded as
    open indefinitely. A reproduced counterexample has to reproduce the
    stated thing.
    """
    _open_matter(page, journey)
    _advise(page, BRIEF)
    # The working exists and is CLOSED. Waiting for the summary rather than
    # for `.gates` is the difference between asserting on the fix and
    # asserting on the fold.
    page.wait_for_selector("details.audit summary", timeout=60000)

    shown = _visible_text(page)
    gate_ids = sorted(set(re.findall(r"G-[A-Z]{3,}", shown)))
    assert not gate_ids, (
        f"these gate ids are on the advocate's screen: {gate_ids}")
    assert "outcome ok" not in shown.lower(), (
        "the turn's own telemetry -- latency, calls, tokens, cost -- is "
        "rendered to the advocate")

    # AND NOTHING WAS THROWN AWAY. Every one of these is what makes a claim
    # checkable; the change is that reaching them is a decision.
    page.click("details.audit summary")
    page.wait_for_selector("details.audit[open]", timeout=10000)
    opened = _visible_text(page)
    assert re.search(r"G-[A-Z]{3,}", opened), (
        "the working is empty -- the gate states were deleted rather than "
        "filed, which is a worse product than the one that showed them")
    assert "outcome" in opened.lower()


def test_phase_5c_the_answer_reads_as_a_brief_and_not_a_log(page, journey):
    """DG-14: ordered prose, every substantive element kept, no internal labels."""
    _open_matter(page, journey)
    with page.expect_response(lambda r: r.url.endswith('/api/turn')
                              and r.request.method == 'POST') as returned:
        _advise(page, BRIEF)
    elements = returned.value.json()['elements']
    assert len(elements) >= 2
    paragraphs = page.locator('#thread .el > p.body').all_text_contents()
    assert len(paragraphs) >= 2
    assert elements[0]['kind'] in ('action', 'question')
    assert paragraphs[0] == elements[0]['text'], 'the next step must still lead'
    assert all(el['text'] in paragraphs for el in elements), 'a substantive element was lost'
    assert page.locator('#thread h3.section, #thread .el .k').count() == 0


def test_phase_5d_the_masthead_is_not_a_configuration_dump(page, journey):
    """J-7's other half, and it is on every screen rather than one answer.

    MEASURED: `openai/gpt-4o-mini-2024-07-18 · hard: not configured · judge:
    configured · store: fernet · corpus: readable · manifest: 22 acts`.
    `hard: not configured` reads as something broken, `fernet` is a cipher
    name, and the model id is ours. None of it is a fact about their matter.
    """
    with page.expect_response(lambda reply: reply.url.endswith("/api/health")
                              and reply.request.method == "GET", timeout=30000) as checked:
        _sign_in(page, journey)
    # WAIT FOR THE LINE TO RESOLVE. `loadHealth()` is async and the field
    # reads `checking…` until it lands -- so reading immediately after
    # sign-in asserts against a placeholder, which contains none of the
    # tokens this phase is about and would pass on any product at all.
    response = checked.value
    assert response.status == 200, response.text()
    health = response.json()
    assert health["corpus"] in ("readable", "NOT READABLE")
    expected = ("Legal library available · check the scope of each result"
                if health["corpus"] == "readable" else
                "Legal library unavailable · authority-backed research is limited")
    page.wait_for_function(
        "expected => document.querySelector('#health').textContent.trim() === expected",
        arg=expected, timeout=30000)
    masthead = page.inner_text("#masthead")

    for token in ("fernet", "gpt-", "scripted-1", "not configured",
                  "manifest:"):
        assert token not in masthead, (
            f"{token!r} is in the masthead on every screen")
    # F-A-17. THE LINE LIVES ON THE LEGAL LIBRARY PAGE, the page it is about.
    _tab(page, "search")
    library = page.inner_text("#pane-search")
    for token in ("fernet", "gpt-", "scripted-1", "not configured",
                  "manifest:"):
        assert token not in library, f"{token!r} is on the Legal library page"
    assert expected in library, (
        "the Legal library says nothing about whether the corpus can be read, "
        "which is the one thing on that line an advocate needs")
    assert page.get_attribute("#health", "title") == (
        "Library availability does not establish legal coverage or currency.")
    assert ("bad" in (page.get_attribute("#health", "class") or "").split()) is (
        health["corpus"] != "readable")


def test_phase_6b_an_expired_period_is_never_a_window_to_act_within(
        page, journey):
    """BK-35, IN THE BROWSER. The row had no phase of its own until now.

    BK-30's own rule is that every later row adds its counterexample to this
    suite, and BK-35 -- the accrual and `G-CONSISTENT` -- did not. Phase 6
    covers the contradiction indirectly on a live period; this drives the
    case the row was actually opened for.

    THE BRIEF IS FIFTEEN YEARS OLD, so the period has run whatever Article is
    retrieved. What must never appear is a step telling the advocate to act
    within a window the same answer says is gone -- B-074, which was fixed by
    telling the model and recurred anyway.
    """
    _open_matter(page, journey)
    _advise(page, EXPIRED)
    shown = _visible_text(page)

    said = shown.lower()
    if "has run" in said or "passed" in said or "expired" in said:
        for phrase in ("within the limitation period",
                       "within the window",
                       "before the period expires"):
            assert phrase not in said, (
                f"the answer says the period has gone AND tells the advocate "
                f"to act {phrase!r} -- B-074, on the page")

    # AND THE ACCRUAL IS NAMED, so a wrong one can be seen and corrected. A
    # date with no stated starting point is one the advocate cannot check.
    if "limitation" in said:
        assert ("runs to" in said or "not computed" in said
                or "did not compute" in said), (
            "a limitation position is asserted with neither a date nor a "
            "reason it could not be computed")


# ========================================================== 7-8. the panes ===

def test_phase_7_search_answers_or_says_why(page, journey):
    """A search that returns nothing must say whether it RAN. Zero results and
    an index that was never built read identically otherwise -- defect shape
    S3, and this product has three measured instances against the corpus."""
    _sign_in(page, journey)
    _tab(page, "search")

    # NOTHING IS CLAIMED BEFORE THE SEARCH RUNS. BK-45.
    #
    # This waited on `#pane-search` innerText being non-empty and then
    # asserted it was non-empty. The pane holds the search FORM, whose
    # `sr-only` labels are `clip-path: inset(50%)` and therefore in
    # `innerText` -- so the condition was already true before Enter was
    # handled, and the phase passed against a submit button wired to nothing.
    #
    # The two elements the renderer actually writes into start empty, so
    # asserting on THEM is a check that can fail.
    for empty in ("#search-state", "#search-results"):
        assert not page.inner_text(empty).strip(), (
            f"{empty} already has content before the search ran, so this "
            f"phase cannot tell a completed search from a dead button")

    page.fill("#q", "adverse possession")
    page.press("#q", "Enter")

    # WAITING FOR RESULTS WOULD HANG on the honest answer "the index is not
    # built", which is the answer this phase most wants to see rendered. So
    # wait for either half of the renderer to speak.
    page.wait_for_function(
        "() => ['#search-state', '#search-results'].some(s => {"
        "  const el = document.querySelector(s);"
        "  return el && el.innerText.trim().length > 0; })",
        timeout=30000)

    said = page.inner_text("#search-state").strip()
    results = page.inner_text("#search-results").strip()

    # AND IT IS ONE OF THE THREE NAMED STATES. A search that returns nothing
    # must say WHETHER IT RAN: zero results and an index that was never built
    # read identically otherwise -- defect shape S3, and this product has
    # three measured instances of it against the corpus.
    ran_and_found = bool(page.locator("#search-results .hit").count())
    not_searched = "NOT SEARCHED" in said.upper()
    searched_and_empty = bool(said) and not not_searched

    assert ran_and_found or not_searched or searched_and_empty, (
        "the search pane rendered neither results, nor a NOT SEARCHED state, "
        "nor a named zero -- so the advocate cannot tell whether the corpus "
        "was asked:\n"
        f"  #search-state:   {said[:200]!r}\n"
        f"  #search-results: {results[:200]!r}")

    if ran_and_found:
        assert page.locator("#search-results .result-count").count() == 1, (
            "hits were rendered with no count, so the advocate cannot tell "
            "whether they are looking at all of them")
    assert not page.errors, f"the page threw: {page.errors}"


def test_phase_8_history_shows_the_turn_that_was_served(page, journey):
    """The advocate's own record. A History that cannot show what was served
    makes every other guarantee unverifiable by them."""
    _open_matter(page, journey)
    _advise(page, BRIEF)
    _tab(page, "history")

    assert page.inner_text("#pane-history").strip(), "History is empty"
    assert not page.errors, f"the page threw: {page.errors}"


# ============================================= 9-10. surviving the ordinary ==

def test_phase_8b_history_is_a_record_and_not_a_json_dump(page, journey):
    """BK-39. The surface for REVIEW shows what the surface for ADVICE showed.

    History rendered the advocate's message and a collapsed *"The turn as it
    was served"* which, opened, printed the complete raw JSON: internal ids,
    prompts, model answers, metrics, gates. The answer they were actually
    given was not rendered at all.

    TWO RENDERERS FOR ONE ANSWER IS S9 and the drift was already real: BK-37
    filed the served answer into sections and History would still have been
    printing JSON. The assertion is that the record READS like the advice --
    same headings, same folding -- and that the raw material is still there
    for the review that needs it.
    """
    _open_matter(page, journey, client="History Test Traders")
    _advise(page, BRIEF)
    matter_id = page.get_attribute('#pane-advise', 'data-matter-id')
    original = page.locator('#thread .el > p.body').all_text_contents()
    assert original

    _tab(page, "history")
    page.select_option("#history-matter", value=matter_id)
    page.wait_for_selector("#pane-history .turn", timeout=30000)
    page.wait_for_selector("#pane-history .el > p.body", timeout=30000)

    shown = page.inner_text("#pane-history")
    assert page.locator('#pane-history .el > p.body').all_text_contents() == original
    assert page.locator('#pane-history h3.section, #pane-history .el .k').count() == 0
    # NOT RAW, AND NOT DELETED. The JSON is behind the same door every served
    # turn already has.
    assert '"turn_id"' not in shown, (
        "the raw record is the first thing History shows")
    page.click("#pane-history details.audit summary")
    page.wait_for_selector("#pane-history details.audit[open]", timeout=10000)
    assert '"turn_id"' in page.inner_text("#pane-history"), (
        "the raw record was deleted rather than filed -- forensic diagnosis "
        "is what this store is for")


def test_phase_9_reload_restores_the_matter(page, journey):
    """Closing a laptop is not a failure mode, it is Tuesday."""
    mine = "Reload Test Traders"
    _open_matter(page, journey, client=mine)
    _advise(page, BRIEF)
    before = _visible_text(page)
    original = page.locator('#thread .el > p.body').all_text_contents()
    assert original
    assert "Goods were supplied" in before

    page.reload()
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    page.get_by_role("button", name="My work", exact=True).click()
    page.wait_for_selector("#rail-body .row[data-matter-id]", timeout=15000)

    # THE CONVERSATION, NOT MERELY A NON-EMPTY PAGE. The first version of
    # this phase asserted `len(after) > 40`, which the matter rail alone
    # satisfies -- so it passed on exactly the defect BK-33 records: *"reload
    # of a live authenticated session showed a blank Advise pane"*. An
    # assertion that a page is not empty is not an assertion that the
    # advocate's work came back.
    # THIS PHASE'S OWN MATTER, by the name it gave at intake.
    page.click(f"#rail-body .row:has-text('{mine}')")
    # WAIT FOR WHAT THIS PHASE JUDGES, which is the restored ANSWER and not
    # the card around it. `.turn` appears on the first repaint; the sections
    # arrive with the elements, and reading between the two gave a page that
    # had the brief and none of the advice -- the third time in this suite
    # that waiting for a container rather than for the content reported a
    # working product as broken.
    page.wait_for_selector("#thread .el > p.body", timeout=30000)
    page.wait_for_selector("details.audit summary", timeout=30000)
    after = _visible_text(page)

    assert "Goods were supplied" in after, (
        "the brief the advocate wrote is not on the screen after a reload")
    # AND WHAT THEY WERE TOLD, not only what they said. A transcript that
    # restored the question and lost the answer would be the worse half.
    assert page.locator('#thread .el > p.body').all_text_contents() == original
    # A READ-BACK TURN SAYS SO. The run's latency, calls and cost are not on
    # the record, and rendering them as zeros would show a measurement nobody
    # made.
    page.click("details.audit summary")
    page.wait_for_selector("details.audit[open]", timeout=10000)
    assert "read back from the record" in _visible_text(page), (
        "a restored turn presents itself as a fresh one")


def test_phase_10_an_expired_session_does_not_leave_a_signed_in_masthead(
        page, journey):
    """THE COUNTEREXAMPLE BK-40 IS OPEN FOR.

    `api()` has no central 401 transition, so an expired session leaves the
    masthead claiming the advocate is signed in while each pane fails on its
    own. The advocate is looking at their own name above a product that can no
    longer do anything for them.
    """
    _open_matter(page, journey, client="Expiry Draft Synthetic Client")

    # THE BROKEN DRAFT SURVIVES, OR IT DOES NOT -- either way it is part of
    # what expiry costs the advocate, so it is typed before the session goes.
    page.fill("#message", BRIEF)

    # END THE SESSION SERVER-SIDE, the way an expiry does. BK-46.
    #
    # This called `page.context.clear_cookies()`, three lines under a comment
    # saying not to -- that is the BROWSER FORGETTING its token, which is a
    # different event with a different failure mode. An expiry leaves the
    # cookie in place and the session gone, and the whole defect this phase
    # is open for lives in what the page does when it presents a token the
    # server no longer honours.
    #
    # `assurance/journeys/served.py` runs the server in a THREAD and hands the harness the
    # same `Served`, explicitly so the suite can reach the store the browser
    # is talking to. `except_token=""` keeps nothing, so this session goes
    # too -- which the `/api/sessions/revoke` route deliberately cannot do.
    ended = journey["box"].directory.close_all_sessions(
        journey["advocate"], "journey phase 10: expiry", except_token="")
    assert ended >= 1, (
        "no session was ended, so this phase would go on to assert against a "
        "product that is still correctly signed in")

    page.click("#tabs button[data-tab='prepare']")
    # WAIT FOR THE THING UNDER TEST, which is the masthead.
    #
    # This waited for the history pane to have TEXT, and that stopped being
    # right the moment BK-40 landed: the central 401 handler strips
    # privileged content, so the pane is correctly EMPTY and the wait timed
    # out on the fix working. A phase that fails because the defect it
    # describes was fixed is worse than one that never ran.
    page.wait_for_selector("#gate:not([hidden])", timeout=30000)

    # THE ASSERTION, not a conditional xfail. The marker above carries the
    # row; this states the rule, so the phase XPASSes the day it holds. BK-44.
    assert page.is_hidden("#masthead"), (
        "the session is gone and the masthead still shows the advocate as "
        "signed in, so they are looking at their own name above a product "
        "that can no longer do anything for them")

    # AND THE BRIEF THEY HAD TYPED IS NOT SILENTLY GONE. BK-46.
    #
    # Expiry is not the advocate's doing and it arrives without warning. A
    # product that takes an unsent brief with it has made the session limit
    # cost them the work, which is the same absence BK-36 refused for a failed
    # send -- an identity for the attempt that outlives the attempt.
    shown = _visible_text(page).lower()
    assert BRIEF[:40].lower() in shown or "draft" in shown or "saved" in shown, (
        "the session expired and the brief in the composer is neither shown "
        "nor acknowledged, so the advocate has lost work to an event they "
        "did not cause and were not warned about")


def test_phase_13_a_send_that_fails_keeps_the_brief_and_offers_one_retry(
        page, journey):
    """BK-36, IN THE BROWSER. The advocate does not lose what they wrote.

    The composer used to be cleared before the request, so a send that failed
    before commitment took the only copy of a long brief with it -- gone on
    reload, gone on sign-out. And the retry minted a NEW turn id, so a send
    that had actually landed was written to the file a second time. Both are
    the same absence: an identity for the attempt that outlives the attempt.
    """
    _open_matter(page, journey, client="Failed Send Synthetic Client")
    page.route("**/api/turn", lambda route: route.abort())
    page.fill("#message", BRIEF)
    page.click("#send")
    page.wait_for_selector(".failure", timeout=60000)

    shown = _visible_text(page)
    assert BRIEF[:40] in shown, "the brief the advocate wrote is gone"
    assert page.input_value("#message") == "", "submitted text still occupies the typing field"
    assert page.locator('#thread .brief').last.inner_text() == BRIEF
    assert "Send this brief again" in shown, (
        "a failed send offers no way to try again")
    # AND IT SAYS WHETHER IT LANDED, which is the one question a failed send
    # has to answer. `The turn was refused: HTTP 500` answered none of it.
    assert ("was NOT saved" in shown or "could not tell whether" in shown), (
        f"the failure does not say whether the brief was saved: {shown[:600]}")
    assert "The response could not be received" in shown
    assert "The turn was refused" not in shown, "a lost response is not a known refusal"


def test_phase_13b_a_cancelled_turn_does_not_claim_it_was_not_saved(
        page, journey):
    """BK-41. Cancel abandons the REQUEST, which is all a browser can do.

    A turn's measured p90 is about 18 seconds and about 20 for one making
    eight or more model calls, with no way to stop it and the composer
    disabled throughout. Cancel is the escape.

    WHAT IT MUST NOT SAY is that nothing was saved. The server may have
    committed before the abort reached it, and `cancelled — nothing was
    recorded` is a claim the browser is in no position to make. `unknown` is
    the honest state, and its retry is already safe because BK-36 gave it the
    same turn id.
    """
    _open_matter(page, journey, client="Cancel Test Traders")
    page.fill("#message", BRIEF)
    page.click("#send")
    page.wait_for_selector("button.cancel", timeout=30000)
    page.click("button.cancel")
    page.wait_for_selector(".failure", timeout=60000)

    shown = _visible_text(page)
    assert "You cancelled this turn" in shown
    assert "The turn was refused" not in shown
    assert "could not tell whether" in shown, (
        "a cancelled turn claims to know whether the brief was saved")
    assert "was NOT saved" not in shown, (
        "cancelling asserts nothing was recorded, which the browser cannot "
        "know -- the server may have committed before the abort landed")
    assert "Send this brief again" in shown
    # AND THE BRIEF IS STILL THERE. Cancelling must not cost them what they
    # wrote any more than a failure does.
    assert page.input_value("#message") == ""
    assert page.locator('#thread .brief').last.inner_text() == BRIEF


@pytest.mark.parametrize("width,height", WIDTHS,
                         ids=[f"{w}px" for w, _ in WIDTHS])
def test_phase_14_every_control_has_a_name_and_the_page_does_not_scroll_sideways(
        page, journey, width, height):
    """BK-42. An accessible name on every control, at every width.

    A PLACEHOLDER IS NOT A NAME. It is announced once, it disappears the
    moment anything is typed, and a screen-reader user who tabs back to a
    filled field is told nothing about what it holds. Four search inputs had
    placeholders and no labels.

    AND NOTHING SCROLLS SIDEWAYS. `app.css` already records one instance --
    a conversation measuring 799px inside a 514px pane, every answer clipped
    at the right edge -- and it was found by looking at the screen rather
    than by any check. This is the check.
    """
    _sign_in(page, journey, width, height)
    _tab(page, "search")

    # EVERY CONTROL HAS A NAME. Read from the accessibility tree rather than
    # from the markup, so a label that exists and is not associated fails.
    unnamed = page.evaluate("""() => {
      const bad = [];
      for (const el of document.querySelectorAll(
              'input:not([type=hidden]), select, textarea, button')) {
        if (el.offsetParent === null && el.type !== 'hidden') continue;
        const label = el.labels && el.labels.length
          ? el.labels[0].textContent.trim() : '';
        const name = (el.getAttribute('aria-label') || label
                      || el.textContent || '').trim();
        if (!name) bad.push(el.id || el.tagName + '.' + el.className);
      }
      return bad;
    }""")
    assert not unnamed, (
        f"at {width}px these controls have no accessible name, so a screen "
        f"reader announces them as their type and nothing else: {unnamed}")

    sideways = page.evaluate(
        "() => document.documentElement.scrollWidth > "
        "document.documentElement.clientWidth + 1")
    assert not sideways, (
        f"the page scrolls sideways at {width}px, so content is off the "
        f"right edge of the screen")


# ================================================= 11-12. the way out ========

def test_phase_11_a_logout_the_server_refuses_is_not_shown_as_done(
        page, journey):
    """THE MEASURED DEFECT IN BK-40, and the worst one on this page.

    `signout` clears all on-screen state in `finally` even when
    `/api/logout` fails. With the server stopped the screen showed sign-in as
    if logout had succeeded; after a restart, reload reopened the
    authenticated session and its matter, because the server token was still
    live.

    An advocate who has been shown the sign-in screen believes they are signed
    out. On a shared machine that belief is the whole of the protection.
    """
    _sign_in(page, journey)
    # THE SERVER REFUSES THE LOGOUT, and the session stays live.
    page.route("**/api/logout", lambda route: route.abort())
    _sign_out(page)
    # The gate is cleared before the asynchronous refusal settles. Wait for
    # the actual retry control, not its pre-existing empty parent container.
    page.get_by_role("button", name="Try to end the session again", exact=True).wait_for(
        state="visible", timeout=15000)

    # THE RULE, ASSERTED. The gate may be up, but not SILENTLY: an advocate
    # shown the sign-in screen believes they are signed out, and on a shared
    # machine that belief is the whole of the protection. The marker above
    # carries the row so this XPASSes the day the product says so. BK-44.
    shown = _visible_text(page).lower()
    assert not page.is_visible("#gate") or any(
        p in shown for p in ("could not", "not confirmed", "unconfirmed",
                            "server did not confirm")), (
        "the sign-in screen is shown after a logout the server never "
        "confirmed, and nothing on the page says the logout was unconfirmed")
    assert "the server did not confirm the end of your session" in shown
    assert "you may still be signed in" in shown
    assert "this screen is not proof that you are signed out" in shown
    # Browser routing aborted logout, not the actual server session. The
    # context's real cookies must still authenticate at the server.
    session = page.request.get(journey["base"] + "/api/session")
    assert session.status == 200, session.text()
    assert session.json()["advocate"]["id"] == journey["advocate"]


def test_phase_12_a_confirmed_logout_cannot_be_undone_by_reload(page, journey):
    """The half that works today, and must keep working."""
    _sign_in(page, journey)
    _sign_out(page)
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)

    page.reload()
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    assert page.is_hidden("#masthead"), (
        "reload restored the application after a confirmed sign-out")

    # AND THE SERVER AGREES. A gate on screen while `/api/session` still
    # answers is a signed-out picture over a live session.
    req = urllib.request.Request(journey["base"] + "/api/session")
    try:
        urllib.request.urlopen(req)
        raise AssertionError("/api/session still answers after logout")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, f"expected 401, got {exc.code}"


# ==================================================== the harness's control ==

def test_the_journey_is_actually_driving_a_browser(page, journey):
    """A POSITIVE CONTROL ON THE HARNESS ITSELF.

    Every phase above would pass against a page that never loaded if the
    assertions happened to be about absence -- and half of them are. This
    proves the browser reached the product and ran its script, so an empty
    result means a failure rather than a harness that quietly did nothing.
    """
    page.goto(journey["base"] + "/")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)

    assert page.title().strip(), "the page has no title"
    assert page.evaluate("typeof window.fetch === 'function'")
    # The script ran: `boot()` resolves the session and reveals the gate.
    assert page.is_visible("#login-id"), "the sign-in form never appeared"

    health = json.loads(
        urllib.request.urlopen(journey["base"] + "/api/health").read())
    assert health["code_state"] == "current", (
        f"the server is not running the tree under test: {health}")
    # THE WIRED ADAPTER, NOT THE ENVIRONMENT. This read
    # `os.environ["NM_MODEL_PROVIDER"]` and failed on the first run -- on a
    # machine where that is legitimately `openai` for ordinary work, while
    # the harness had correctly wired a scripted double. A control that
    # reports the shell rather than the product fails where nothing is wrong
    # and passes where something is.
    # UNWRAPPED, because the composition root wraps every adapter in
    # `TracedModel` and that is the product working: the trace is where
    # refused reads and tier downgrades are recorded. A control that asserted
    # on the outermost object would report the product's own instrumentation
    # as a billing risk.
    wired = journey["box"].application.model
    while hasattr(wired, "inner"):
        wired = wired.inner
    assert type(wired).__name__ == "ScriptedModelAdapter", (
        f"the journey suite is driving {type(wired).__name__}, which may "
        f"reach a billed provider")
