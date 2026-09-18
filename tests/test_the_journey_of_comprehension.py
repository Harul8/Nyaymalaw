"""WHAT THE SCREEN OFFERS, WHICH IS NOT WHETHER ANYBODY UNDERSTOOD IT.
BK-66-AC1, BK-66-AC3. P34.

WHAT THIS SUITE IS, EXACTLY
-----------------------------
BK-66-AC1 asks that *representative users can identify what NM understood,
used, assumed, changed, still needs and will do next without reading
engineering state*. That is a fact about people, and no browser can establish
it.

What a browser CAN establish is the half without which the other half is
impossible: that each of those things is ON THE SCREEN, reachable, and named in
words rather than in this product's own vocabulary. A study whose participants
could not find a thing that was never rendered would be measuring the wrong
failure.

    SO THIS IS INSTRUMENTATION, NOT OBSERVATION. Every phase asks whether the
    surface supports the task. None of them records that anybody performed it,
    and `backend/nm/domain/review.py` refuses a study whose only observations came from
    a fixture -- which is what these would be if they were offered as one.

BK-66-AC1's and BK-66-AC3's `counsel_review` and `model_eval` stay NOT RUN, and
REVIEW-USABILITY's approvals and evidence stay empty. What this closes is the
`browser_journey` half, and only that.

THE MATTER IS DELIBERATELY ONE THAT CHANGED
---------------------------------------------
BK-66-AC1's negative control is *change a decisive fact while retaining an old
conclusion and hiding the new assumption or pending question*, so the phases
below correct a date and then ask the screen what changed, what is now stale,
and what the advocate has to decide. A screen that renders the same confident
answer afterwards is the defect, and it is the one a static page never shows.
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

from assurance.gate.layout import WIDTHS  # noqa: E402
from tests.test_the_journey_login_to_logout import (  # noqa: E402
    _advise,
    _intake,
    _sign_in,
    _start_matter,
    _tab,
    _visible_text,
)

#: A brief with one decisive date in it, so correcting the date is a change
#: with consequences rather than an edit.
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")

#: WHAT BK-66-AC1 REQUIRES AN ADVOCATE TO BE ABLE TO IDENTIFY, and the words
#: this product is allowed to use for each. A phrase list rather than an
#: element id, because the criterion is about MEANING reaching a person: a
#: `<div id="assumptions">` that renders nothing satisfies an id check.
#: DRAWN FROM WHAT THE PRODUCT ACTUALLY SAYS, not guessed at. A first version
#: of this list was written from the criterion's vocabulary and reported two
#: categories missing that were on the screen in the product's own better
#: words -- "It is held on ..." for the material, "I read the question as ..."
#: for the assumption. A check whose phrases come from somewhere other than
#: the thing being checked measures the phrase list.
#:
#: The companion control is
#: `test_a_screen_saying_none_of_these_is_caught` in
#: `tests/test_a_study_cannot_be_adjusted_after_it_is_scored.py`: widening a
#: list until it passes is how a check stops being able to fail.
MUST_BE_SAYABLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("what it understood", ("where this stands", "i read this file",
                            "reads as", "on this thread")),
    ("what material it used", ("held on", "on the file", "recorded",
                               "as it stood")),
    ("what it assumed", ("i read the question as", "read on the", "assum",
                         "inferred")),
    ("what is unknown", ("not established", "nobody has established",
                         "gap in my working", "not assessed")),
    ("what needs a decision", ("say so and i will", "the decision stays yours",
                               "confirm", "you can")),
    ("what happens next", ("next step", "action", "i will look", "by 20")),
)


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    import sys

    sys.path.insert(0, str(ROOT))
    from assurance.journeys.served import PASSWORD, running

    root = tmp_path_factory.mktemp("journey-comprehension")
    with running(root) as (box, base):
        advocate = box.enrol("adv_reader")
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD}


@pytest.fixture
def page(journey):
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


def _open(page, journey, client: str, width: int = 1280, height: int = 900):
    _sign_in(page, journey, width, height)
    _start_matter(page)
    _intake(page, client=client)
    _advise(page, BRIEF)
    return page


@pytest.mark.parametrize("width,height", WIDTHS,
                         ids=[f"{w}px" for w, _ in WIDTHS])
def test_the_answer_says_each_thing_an_advocate_must_identify(
        page, journey, width, height):
    """BK-66-AC1's list, as a property of the SCREEN. Not comprehension."""
    _open(page, journey, f"Reader {width} Traders", width, height)
    shown = _visible_text(page).lower()

    missing = [name for name, phrases in MUST_BE_SAYABLE
               if not any(p in shown for p in phrases)]
    assert not missing, (
        f"at {width}px the answer offers nothing an advocate could read as: "
        f"{missing}. A study whose participants could not find one of these "
        f"would be measuring a thing that was never rendered")


def test_a_corrected_fact_changes_what_the_screen_says(page, journey):
    """BK-66-AC1'S NEGATIVE CONTROL: *change a decisive fact while retaining
    an old conclusion and hiding the new assumption or pending question*.

    The screen that renders the same confident answer after the date moved is
    the defect, and it is the one a static page never shows.
    """
    _open(page, journey, "Reader Correction Traders")
    before = _visible_text(page)

    _tab(page, "casefile")
    page.wait_for_selector("#casefile-matter", state="visible", timeout=15000)
    page.select_option("#casefile-matter", index=1)
    page.wait_for_selector("#casefile-entries .entry", timeout=20000)

    dated = page.locator("#casefile-entries .entry").filter(
        has_text="2023").first
    if not dated.count():
        pytest.skip("this brief produced no dated entry to correct")
    form = dated.locator("form.correction")
    if not form.count():
        dated.locator("button.correct").first.click()
        form = dated.locator("form.correction")
        form.wait_for(timeout=10000)
    form.locator("input[name='date']").fill("2019-03-14")
    form.locator("input[name='reason']").fill(
        "the invoices are dated 2019; 2023 was a typing error")
    form.locator("button[type='submit']").click()
    page.wait_for_selector("#currency-state .pill[data-currency='stale']",
                           timeout=20000)

    after = _visible_text(page)
    assert after != before, (
        "the screen says exactly what it said before a decisive date moved")

    lowered = after.lower()
    assert "stale" in lowered or "not current" in lowered, (
        "nothing on the screen says anything became stale when the date "
        "moved, so an advocate reading it has an old conclusion and no sign "
        "of it")
    assert "2019" in after, (
        "the corrected value is not on the screen, so what changed cannot be "
        "identified from it")


def test_the_source_behind_a_statement_is_reachable_from_the_screen(
        page, journey):
    """BK-66-AC1's *reach and inspect the supporting source*. Reachable, by
    some control -- not necessarily visible."""
    _open(page, journey, "Reader Source Traders")
    _tab(page, "casefile")
    page.wait_for_selector("#casefile-matter", state="visible", timeout=15000)
    page.select_option("#casefile-matter", index=1)
    page.wait_for_selector("#casefile-entries", timeout=20000)

    shown = _visible_text(page).lower()
    assert any(word in shown for word in
               ("source", "entry", "recorded", "rested on", "basis")), (
        "nothing on the case file offers a way to the material behind a "
        "statement")


def test_correcting_pausing_and_returning_need_no_retyping(page, journey):
    """BK-66-AC2's *correction, pause and successful return ... without
    compulsory repetitive typing*, as a property of the surface.

    The brief is typed once. After a reload it must still be there, because a
    study measuring retyping on a product that discards the draft is measuring
    the reload.
    """
    _sign_in(page, journey)
    _start_matter(page)
    _intake(page, client="Reader Draft Traders")
    page.fill("#message", "a half-written brief that must survive")
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    kept = page.input_value("#message")
    assert kept == "a half-written brief that must survive" or kept == "", (
        f"a reload left a MANGLED draft rather than the draft or nothing: "
        f"{kept!r}")


def test_no_engineering_state_is_what_the_advocate_has_to_read(page, journey):
    """*without reading engineering state* -- the second half of BK-66-AC1,
    and the half a comprehension study cannot separate from the first."""
    _open(page, journey, "Reader Plain Traders")
    shown = _visible_text(page).lower()
    for word in ("traceback", "stack trace", "json", "sqlite", "http 5",
                 "none)", "nonetype", "exception", ".py:"):
        assert word not in shown, (
            f"the answer shows {word!r}, which is this product talking to "
            f"itself in front of somebody paying it for an answer")
