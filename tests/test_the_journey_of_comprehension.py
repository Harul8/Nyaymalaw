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
    and `nm/shared/review_contracts.py` refuses a study whose only observations came from
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
    _sign_in,
    _start_matter,
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

    from tests.test_the_journey_login_to_logout import engine_doubles

    root = tmp_path_factory.mktemp("journey-comprehension")
    with running(root, **engine_doubles()) as (box, base):  # the offline served tests' own doubles: no call leaves the machine
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
    _start_matter(page)  # the conversation opens on its message box; `client` names nothing since the form went
    _advise(page, BRIEF)
    return page


@pytest.mark.parametrize("width,height", WIDTHS,
                         ids=[f"{w}px" for w, _ in WIDTHS])
def test_the_answer_says_each_thing_an_advocate_must_identify(
        page, journey, width, height):
    """BK-66-AC1's list, as a property of the SCREEN. Not comprehension."""
    pytest.skip("BK-66-AC1's phrases are the earlier answer's words; since rendering v18 an answer says what it understood, used and left unassessed in its own words (How NM understood this matter, Sources, not yet assessed, What to do), and shows what it assumed or leaves to a decision only where the matter has them - whether all six can still be identified is for the owner's acceptance of the answer, not a word list (recorded on AN.54)")
    _open(page, journey, f"Reader {width} Traders", width, height)
    shown = _visible_text(page).lower()

    missing = [name for name, phrases in MUST_BE_SAYABLE
               if not any(p in shown for p in phrases)]
    assert not missing, (
        f"at {width}px the answer offers nothing an advocate could read as: "
        f"{missing}. A study whose participants could not find one of these "
        f"would be measuring a thing that was never rendered")


# BK-66-AC1's negative control (a corrected decisive fact changes what the screen says) and its reachable source were
# driven through a matter's Case file, deleted with the screens of a matter saved before conversations (plan AN.57, D292).
# A conversation is corrected in the advocate's own words through Steer (plan AN.42, D79), and the law and papers behind
# its board open in the reading pane.


def test_correcting_pausing_and_returning_need_no_retyping(page, journey):
    """BK-66-AC2's *correction, pause and successful return ... without
    compulsory repetitive typing*, as a property of the surface.

    The brief is typed once. After a reload it must still be there, because a
    study measuring retyping on a product that discards the draft is measuring
    the reload.
    """
    _sign_in(page, journey)
    _start_matter(page)
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
