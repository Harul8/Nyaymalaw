"""THE WHOLE PRODUCT AT EVERY SUPPORTED WIDTH. BK-32, BK-43, BK-47, BK-72,
J-5, J-7. P36.

WHY THIS IS ONE JOURNEY AND NOT FIVE SCREEN TESTS
---------------------------------------------------
P36's instruction is explicit: *do not redesign isolated screens only.*
Registration through logout and the new P29 to P32 flows are ONE product, and
the defects that matter live between screens -- a matter opened on one tab and
missing on another, a form that loses what was typed when an unrelated section
repaints, a control that is reachable at 1280px and clipped at 390px.

So each phase below drives the whole sequence at ONE WIDTH: start a matter,
find another, switch, prepare a package, propose an action, try to send it,
record an unknown outcome, reconcile it, prepare for a hearing, ask what can be
said in court, come back to the file, and sign out.

THE TWO CHECKS THIS SUITE EXISTS TO CARRY
-------------------------------------------
`assurance.gate.layout.clipped` asks whether each primary control's rectangle survives
every clipping ancestor between it and the viewport. It answers the same on a
page that clips its overflow and one that does not, which document scroll width
cannot -- BK-43.

`assurance.gate.layout.unexecuted` refuses a width that recorded a control as VISIBLE
rather than USED, and refuses one that recorded nothing. The cross-width
population is `assurance/journeys/journey.py`'s EXPECTED manifest, which is what that
manifest is for: a phase that stops running is MISSING rather than absent --
BK-47.

WHAT THIS SUITE CANNOT ESTABLISH, and says so rather than implying otherwise:
screen-reader conformance and whether the copy reads as counsel would write it.
Both need a person. BK-68-AC1 and J-7-AC1 keep `counsel_review` NOT RUN.
"""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.journey

playwright_api = pytest.importorskip(
    "playwright.sync_api",
    reason="the journey suite needs a browser: pip install -e .[journey] "
           "&& python -m playwright install chromium")

ROOT = pathlib.Path(__file__).resolve().parents[1]

ARTIFACTS = ROOT / ".nm" / "journey"

from assurance.gate.layout import (  # noqa: E402
    MEASURE_JS,
    REQUIRED_ACTIONS,
    WIDTHS,
    Did,
    clipped,
    from_measurement,
    measured,
    unexecuted,
)
from tests.test_the_journey_login_to_logout import (  # noqa: E402
    BRIEF,
    _advise,
    _intake,
    _reach_rail,
    _sign_in,
    _tab,
    _visible_text,
)

# THE HELPERS ARE IMPORTED AND THE FIXTURES ARE NOT, which is the convention
# `tests/test_the_journey_of_a_correction.py` already keeps. A suite that
# imported another suite's server fixture would share its matters, and every
# "the first row is the one I just made" assertion in both would depend on
# which file pytest collected first.


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    """The product on its own port, with one enrolled advocate."""
    import sys

    sys.path.insert(0, str(ROOT))
    from assurance.journeys.served import PASSWORD, running

    root = tmp_path_factory.mktemp("journey-preparation")
    with running(root) as (box, base):
        advocate = box.enrol("adv_journey")
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD}


@pytest.fixture
def page(journey):
    """A FRESH PAGE PER PHASE, because each phase is one width.

    A module-scoped page would carry the viewport, the signed-in session and
    the matters of the previous width into the next one, and "the advocate
    can do this at 390px" would be answered partly by work done at 1280px.
    """
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = context.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.errors = errors
        try:
            yield pg
        finally:
            context.close()
            browser.close()


@pytest.fixture(autouse=True)
def _artifact_on_failure(request, page):
    """A screenshot and the page for any phase that did not pass, and only
    those: an artifact that is always there is one nobody opens."""
    yield
    report = getattr(request.node, "rep_call", None)
    if report is None or report.failed or hasattr(report, "wasxfail"):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        stem = request.node.name.replace("/", "_")[:80]
        try:
            page.screenshot(path=str(ARTIFACTS / f"{stem}.png"), full_page=True)
            (ARTIFACTS / f"{stem}.html").write_text(page.content(),
                                                    encoding="utf-8")
        except Exception:  # noqa: BLE001 -- an artifact is best effort
            pass

#: THE PRIMARY CONTROLS, by the name a person would use and the selector that
#: finds one. Named here rather than in `assurance/gate/layout.py` because the check is
#: about geometry and this is about THIS product's markup -- a drawer, a tab or
#: a menu would all satisfy the same required action with different selectors.
#:
#: TWO TUPLES, BECAUSE REACHABLE IS NOT VISIBLE. BK-32's rule is that the
#: navigator be REACHABLE at every width, and below 820px it is a drawer that
#: starts closed -- so `#new-matter` is legitimately off-screen until somebody
#: opens it. Measuring it there would fail a correct design, and a check that
#: fails correct designs is switched off within a week.
#:
#: The distinction is not a loophole: `MASTHEAD` must be reachable with no
#: disclosure at all, and `BEHIND_A_DISCLOSURE` is measured AFTER the control
#: that discloses it has been used -- which the phase does, and records as
#: having done.
MASTHEAD = (
    ("the matter navigator", "#matters-toggle, #rail"),
    ("research", "button[data-tab='search']"),
    ("the case file", "button[data-tab='casefile']"),
    ("history", "button[data-tab='history']"),
    ("preparation", "button[data-tab='prepare']"),
    ("who is signed in", "#who-name"),
    ("sign out", "#signout"),
)

BEHIND_A_DISCLOSURE = (
    ("start a matter", "#new-matter"),
)

PRIMARY = MASTHEAD + BEHIND_A_DISCLOSURE

#: The internal key shapes that must never reach a screen. J-5, and the same
#: pattern `tests/test_no_internal_id_reaches_the_advocate.py` reads off the id
#: helpers -- one shape, two populations, which is the sweep rule.
#:
#: `adv_` IS DELIBERATELY NOT HERE, and the reason is not convenience. J-5-AC1
#: names *internal thread, turn and operation identifiers*; an account handle
#: is none of those. It is the thing the advocate typed to sign in, and
#: "recorded by <the handle you sign in with>" is the attribution record
#: working rather than a key on a screen. Adding it would fail the masthead,
#: the screens record and every attribution line in the product -- and a check
#: that fails correct behaviour is switched off within a week, taking the eight
#: shapes that ARE defects with it.
KEYS = ("mat_", "thr_", "fact_", "turn_", "pkg_", "ap_", "hp_", "ho_")


def _no_control_is_clipped(page, width, controls_wanted=MASTHEAD):
    """BK-43-AC1, measured rather than inferred from document width."""
    rows = page.evaluate(MEASURE_JS, list(controls_wanted))
    controls = from_measurement(rows)
    assert measured(controls) == len(controls_wanted), (
        f"at {width}px the measurement returned {measured(controls)} of "
        f"{len(controls_wanted)} controls, so an empty result would prove "
        f"nothing")
    problems = clipped(controls)
    assert not problems, (
        f"at {width}px an advocate cannot reach these:\n  "
        + "\n  ".join(problems))


def _speaks_english(page, width):
    """J-5-AC1 in the browser. The static sweep proves no renderer CAN leak;
    this proves none DID on the path an advocate actually walks."""
    shown = _visible_text(page)
    leaked = [k for k in KEYS if k in shown]
    assert not leaked, (
        f"at {width}px these key prefixes are on the screen: {leaked}. An "
        f"advocate cannot act on a database key")


@pytest.mark.parametrize("width,height", WIDTHS,
                         ids=[f"{w}px" for w, _ in WIDTHS])
def test_the_whole_product_is_navigable_at_every_width(page, journey, width,
                                                       height):
    """START TO SIGN-OUT, INCLUDING P29 TO P32, AT ONE WIDTH.

    Every required action is RECORDED AS IT IS PERFORMED and the record is
    asserted at the end. A phase that returned early would leave the actions it
    skipped as NOT_ATTEMPTED, which `unexecuted` reports -- and that is exactly
    the shape BK-47 describes, where a phase that asserted nothing reported
    green.
    """
    did: dict[str, Did] = {}

    _sign_in(page, journey, width, height)
    _no_control_is_clipped(page, width)

    # ---- start a matter -------------------------------------------------
    _reach_rail(page, width)
    # MEASURED WHERE IT IS DISCLOSED. The drawer is open; if the control is
    # clipped now, an advocate who did the right thing still cannot reach it.
    _no_control_is_clipped(page, width, BEHIND_A_DISCLOSURE)
    page.click("#new-matter")
    _intake(page, client=f"Prep {width} First Traders")
    _advise(page, BRIEF)
    first = page.get_attribute("#pane-advise", "data-matter-id")
    assert first, f"at {width}px the matter has no rendered identity"
    did["start a matter"] = Did.RAN

    # ---- a second matter, so switching is a real switch -----------------
    _reach_rail(page, width)
    if page.is_visible("#back"):
        page.click("#back")
    page.wait_for_selector("#new-matter", state="visible", timeout=15000)
    page.click("#new-matter")
    _intake(page, client=f"Prep {width} Second Traders")
    _advise(page, BRIEF)
    second = page.get_attribute("#pane-advise", "data-matter-id")
    assert second and second != first, (
        f"at {width}px two briefs resolved to the same matter")

    _reach_rail(page, width)
    if page.is_visible("#back"):
        page.click("#back")
    page.wait_for_selector("#rail-body .row", timeout=15000)
    target = page.locator(f'#rail-body .row[data-matter-id="{first}"]')
    assert target.count() == 1, (
        f"at {width}px the first matter cannot be found in the navigator")
    did["find another matter in the navigator"] = Did.RAN

    target.scroll_into_view_if_needed()
    target.click()
    page.wait_for_function(
        "expected => document.querySelector('#pane-advise').dataset.matterId "
        "=== expected", arg=first, timeout=15000)
    did["switch to it"] = Did.RAN

    # ---- the other surfaces --------------------------------------------
    for tab, action in (("search", "reach research"),
                        ("casefile", "reach the case file"),
                        ("history", "reach history")):
        _tab(page, tab)
        assert not page.errors, (
            f"at {width}px the page threw switching to {tab}: {page.errors}")
        did[action] = Did.RAN

    # ---- P29 to P32, on the preparation surface -------------------------
    _tab(page, "prepare")
    did["reach preparation"] = Did.RAN
    page.wait_for_selector("#prepare-matter", state="visible", timeout=15000)
    page.select_option("#prepare-matter", first)
    page.wait_for_function(
        "() => document.querySelector('#prepare-state').textContent.trim() "
        "!== ''", timeout=15000)
    _no_control_is_clipped(page, width)

    _prepare_a_package(page, width)
    _propose_and_fail_to_send(page, width)
    _prepare_a_hearing(page, width)
    _come_back_to_the_file(page, width)

    # ---- identity and the way out ---------------------------------------
    who = page.locator("#who-name")
    assert who.count() == 1 and who.inner_text().strip() not in ("", "—"), (
        f"at {width}px the advocate cannot see whose session this is")
    did["reach identity"] = Did.RAN

    _speaks_english(page, width)
    _no_control_is_clipped(page, width)
    assert not _scrolls_sideways(page), (
        f"the page scrolls sideways at {width}px, so content is off the right "
        f"edge of the screen")

    page.click("#signout")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    did["sign out"] = Did.RAN

    missing = unexecuted(did)
    assert not missing, (
        f"at {width}px this phase did not do the work it reports:\n  "
        + "\n  ".join(missing))
    assert set(did) == set(REQUIRED_ACTIONS), sorted(
        set(REQUIRED_ACTIONS) - set(did))


def _scrolls_sideways(page) -> bool:
    """THE OLD CHECK, KEPT AS A SECOND OPINION and never as the only one.

    It is genuine evidence when it fires -- a document wider than its viewport
    is a real defect -- and it is worthless when it does not, because a style
    rule can make it silent. `clipped` is the check; this is a cheap extra.
    """
    return page.evaluate(
        "() => document.documentElement.scrollWidth > "
        "document.documentElement.clientWidth + 1")


def _prepare_a_package(page, width):
    """P29 through the surface. IT IS NEVER READY TO FILE."""
    page.fill("#pk-document", "written statement")
    page.fill("#pk-posture", "defendant")
    page.fill("#pk-audience", "the City Civil Court")
    page.fill("#pk-court", "City Civil Court, Hyderabad")
    page.fill("#pk-purpose", "resist the summary decree")
    page.fill("#pk-theory", "the goods were rejected on delivery")
    page.fill("#pk-relief", "dismissal with costs")
    page.click("#pk-make")
    page.wait_for_selector("#pk-export", state="visible", timeout=20000)

    shown = page.inner_text("#package-host")
    assert "NOT ready to file" in shown or "not ready to file" in shown.lower(), (
        f"at {width}px the package does not say it is not ready to file, and "
        f"an advocate reading 'ready' will read it as ready for the registry:\n"
        f"{shown[:400]}")

    page.click("#pk-export")
    page.wait_for_function(
        "() => document.querySelector('#package-export').textContent"
        ".includes('parity')", timeout=20000)


def _propose_and_fail_to_send(page, width):
    """P30 through the surface. THE SEND BUTTON EXISTS AND ALWAYS REFUSES.

    A route that 404ed would read as "not built yet"; a button that is absent
    reads as "this product does not do that". A control that refuses with a
    reason is the only one of the three that tells the advocate the truth.
    """
    page.fill("#ac-authority", "the instructing solicitor")
    page.fill("#ac-object", "the written statement")
    page.fill("#ac-destination", "City Civil Court, Hyderabad")
    page.click("#ac-make")
    page.wait_for_selector("#ac-send", state="visible", timeout=20000)

    # A FORM PART-WAY THROUGH TYPING SURVIVES AN UNRELATED RENDER. The defect
    # the browser found in this build: a repaint replaced the form and the
    # advocate's half-typed destination went with it, then the submit did
    # nothing and said nothing.
    page.fill("#ac-destination", "half-typed, not submitted")
    page.click("#hp-make")
    page.wait_for_timeout(250)
    assert page.input_value("#ac-destination") == "half-typed, not submitted", (
        f"at {width}px an unrelated section repainted and took the advocate's "
        f"half-typed text with it")

    page.click("#ac-send")
    page.wait_for_selector("#action-error:not([hidden])", timeout=20000)
    refusal = page.inner_text("#action-error")
    assert "CHOICE-09" in refusal or "disabled" in refusal.lower(), refusal
    assert "nothing here has been sent" in refusal.lower() \
        or "cannot send" in refusal.lower() \
        or "nothing here can send it" in refusal.lower(), refusal

    # AN UNKNOWN OUTCOME STAYS UNKNOWN, and looking again does not send it.
    page.select_option("#oc-state", "delivery_unknown")
    page.fill("#oc-because", "the court portal timed out")
    page.click("#oc-record")
    page.wait_for_selector("#rc-go", state="visible", timeout=20000)
    assert "delivery unknown" in page.inner_text("#action-host").lower()

    page.fill("#rc-basis", "the portal lookup found nothing")
    page.click("#rc-go")
    page.wait_for_function(
        "() => document.querySelector('#action-host').textContent"
        ".includes('Still not known')", timeout=20000)


def _prepare_a_hearing(page, width):
    """P31 through the surface. A SCRIPTED TOPIC IS REFUSED AND NOT SAVED."""
    page.click("#hp-make")
    page.wait_for_selector("#wt-add", state="visible", timeout=20000)

    page.fill("#wt-witness", "Ramesh")
    page.fill("#wt-topics", "You will say the goods were rejected")
    page.click("#wt-add")
    page.wait_for_selector("#hearing-error:not([hidden])", timeout=20000)
    refused = page.inner_text("#hearing-error")
    assert "not saved" in refused.lower(), refused
    assert "supplies the answer" in refused.lower(), refused

    page.fill("#wt-topics", "what he recalls of the delivery on 14 March")
    page.click("#wt-add")
    page.wait_for_selector("#hp-incourt", state="visible", timeout=20000)

    page.click("#hp-incourt")
    page.wait_for_function(
        "() => document.querySelector('#incourt-host').textContent"
        ".includes('not interchangeable')", timeout=20000)
    # CASE-INSENSITIVELY. `.section` is uppercased by the stylesheet, and
    # `inner_text` returns what is RENDERED -- a harness that matched the
    # source casing would report a missing heading that is on the screen.
    shown = page.inner_text("#incourt-host").lower()
    assert "proposed" in shown, (
        f"at {width}px the in-court view does not separate proposed action "
        f"from verified material")


def _come_back_to_the_file(page, width):
    """P32 through the surface. UNASSESSED IS NAMED, not rendered as empty."""
    page.click("#re-entry")
    page.wait_for_function(
        "() => document.querySelector('#continuity-host').textContent"
        ".trim() !== ''", timeout=20000)
    shown = page.inner_text("#continuity-host")
    assert "not assessed" in shown.lower(), (
        f"at {width}px re-entry renders unassessed sections as empty, and an "
        f"empty section reads as 'there is nothing here':\n{shown[:400]}")

    page.fill("#ho-to", "adv_colleague")
    page.fill("#ho-next", "file the written statement by 2 November")
    page.click("#ho-offer")
    page.wait_for_function(
        "() => document.querySelector('#handover-host').textContent"
        ".includes('has NOT moved')", timeout=20000)


def test_the_preparation_surface_is_keyboard_only(page, journey):
    """BK-32-AC1's *keyboard-accessible controls*, at the narrowest width.

    An advocate dictating, or on a trackpad, or using a screen reader reaches
    every control by Tab or reaches none of them. The tab ORDER matters as much
    as reachability: a control that can be focused only after forty presses is
    reachable in the same sense that a fire exit behind a locked door is.
    """
    _sign_in(page, journey, 390, 844)
    page.keyboard.press("Tab")

    reached: list[str] = []
    for _ in range(60):
        got = page.evaluate(
            "() => { const a = document.activeElement;"
            " return a ? (a.id || a.getAttribute('data-tab') || '') : ''; }")
        if got:
            reached.append(got)
        if "prepare" in reached:
            break
        page.keyboard.press("Tab")

    assert "prepare" in reached, (
        "the Preparation tab cannot be reached by keyboard from the top of "
        f"the page within 60 presses; what was reached: {reached}")
    page.keyboard.press("Enter")
    page.wait_for_selector("#pane-prepare:not([hidden])", timeout=15000)
    assert not page.errors, page.errors


def test_a_long_email_and_a_long_citation_stay_on_the_phone(page, journey):
    """BK-42/P36: *readable long emails, citations, titles and filenames*.

    One unbreakable token is the whole of a horizontal scrollbar at 390px, and
    the advocate then cannot read the right-hand end of anything on the page.
    """
    _sign_in(page, journey, 390, 844)
    _tab(page, "prepare")
    page.wait_for_selector("#prepare-matter", state="visible", timeout=15000)
    page.fill("#pk-purpose",
              "instructions.from.a.solicitor.with.a.very.long.address"
              "@chambers-of-a-long-name-indeed.example.co.in")
    assert not _scrolls_sideways(page), (
        "a long unbreakable token pushed the page sideways at 390px")
    rows = page.evaluate(MEASURE_JS, list(MASTHEAD))
    assert not clipped(from_measurement(rows))


def test_no_engineering_vocabulary_reaches_the_preparation_screen(page, journey):
    """J-7-AC1's static half. A provider path, a cipher name or a normalised
    rank shown as a percentage are all the product speaking to itself in front
    of somebody who is paying it for an answer."""
    _sign_in(page, journey, 1280, 900)
    _tab(page, "prepare")
    page.wait_for_selector("#prepare-matter", state="visible", timeout=15000)
    shown = _visible_text(page).lower()
    for word in ("traceback", "sqlite", "postgres", "aes-", "sha256",
                 "http 5", "null", "undefined", "json", "stack trace",
                 ".py", "exception"):
        assert word not in shown, (
            f"the preparation screen shows {word!r} to an advocate")
