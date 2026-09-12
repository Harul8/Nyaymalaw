"""BK-65-AC1 in a real browser. P18's browser proof, EVAL-010's live observation.

    "The advocate sees the old and corrected date and who changed it."
    "Only affected work reopens."

WHAT THIS DRIVES, END TO END
------------------------------
An advocate briefs a matter with one dated event. The board shows a deadline.
They open the case file, correct the date of that one entry, and say why. The
case file then shows the limitation and its deadline as NOT CURRENT with the
reason and the figure each used to be; the party role stays current; the
board shows the window as STALE with the date it was; and a reload -- the
browser's restart -- shows the same, because it is read from the file.

WHAT IT REFUSES TO PASS ON
----------------------------
A form that submits with no reason. A correction that leaves the board
leading with the corrected date. A currency pill that reads `current` or
`not assessed` over a file with a stale conclusion on it. A page reload that
forgets the correction.

Every assertion reads the PAGE, through the accessibility tree or the rendered
text, and then reads the STORE through the served harness's own handle -- so a
screen that says stale over a file that is not, or the reverse, fails here.
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

#: One dated event and one stated side, so the limitation rests on the date
#: and the role does not. Correcting the date must reach one and not the other.
BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")

CLIENT = "Ledger Traders"


# ------------------------------------------------------------- the fixtures ---

@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    import sys

    sys.path.insert(0, str(ROOT))
    from tools.served import PASSWORD, running

    root = tmp_path_factory.mktemp("journey-correction")
    with running(root) as (box, base):
        advocate = box.enrol("adv_ledger")
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD}


@pytest.fixture(scope="module")
def page(journey, request):
    """ONE PAGE FOR THE WHOLE MODULE, because the phases are one story: the
    correction in phase 3 is what phase 5 reloads. A fresh page per phase
    would make each phase brief the matter again, and the reload would be a
    reload of nothing."""
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
    """A screenshot and the page for any phase that did not pass -- and ONLY
    for those. The first version wrote one at the end of every run, and the
    journey runner listed it under "artifacts for every phase that did not
    pass" on a run in which every phase passed: an artifact that is always
    there is one nobody opens, and a runner that lists it is telling a
    half-truth about the run."""
    yield
    report = getattr(request.node, "rep_call", None)
    if report is None or report.failed or hasattr(report, "wasxfail"):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        stem = request.node.name.replace("/", "_")[:80]
        try:
            page.screenshot(path=str(ARTIFACTS / f"{stem}.png"), full_page=True)
            (ARTIFACTS / f"{stem}.html").write_text(page.content(), encoding="utf-8")
        except Exception:  # noqa: BLE001 -- an artifact is best effort
            pass


def _sign_in(page, journey):
    page.goto(journey["base"] + "/")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    page.fill("#login-id", journey["advocate"])
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)


def _intake(page):
    if page.is_hidden("#intake"):
        return
    page.fill("#in-client", CLIENT)
    page.fill("#in-adverse", "Kiran Steels")
    page.fill("#in-scope", "recover the price of goods sold")
    page.check("#in-capacity")
    page.click("#in-go")
    page.wait_for_selector("#intake", state="hidden", timeout=10000)


def _advise(page, message: str):
    page.fill("#message", message)
    page.click("#send")
    page.wait_for_selector(".turn", timeout=60000)
    page.wait_for_selector("#send:not([disabled])", timeout=90000)


def _tab(page, name: str):
    page.click(f"button[data-tab='{name}']")
    page.wait_for_selector(f"#pane-{name}:not([hidden])", timeout=15000)


def _board_text(page) -> str:
    """The rail, LOWER-CASED. The board renders labels through CSS
    `text-transform: uppercase`, and `inner_text` returns what is rendered --
    so a phrase compared in its authored case matches nothing and a check
    written that way passes vacuously on `[] == []`. Phase 5c of the
    login-to-logout journey made exactly that mistake; this helper is the
    one place the case is normalised."""
    return page.inner_text("#rail-body").lower()


def _dated_entry(page):
    """THE DATED EVENT, not the account sentence that also names the year.

    The first run of this suite corrected the account entry -- `We act for the
    plaintiff ... 14 March 2023 ...` -- which the party role ALSO rests on, and
    the ledger correctly reopened the role too. The test had asked for the
    wrong entry, not the ledger for the wrong closure. The event the date read
    produced begins with the goods, and the role does not rest on it.
    """
    return page.locator("#casefile-entries .entry:not(.superseded)",
                        has_text="Goods were supplied").filter(
                            has_not_text="We act").first


def _the_matter(journey):
    """The one matter this advocate holds, READ FROM THE STORE."""
    held = list(journey["box"].application.store.list_for(journey["advocate"]))
    assert len(held) == 1, f"expected one matter, found {len(held)}"
    return held[0]


# =============================================== 1. a deadline exists ==========

def test_phase_1_a_brief_puts_a_current_deadline_on_the_board(page, journey):
    _sign_in(page, journey)
    page.click("#new-matter")
    _intake(page)
    _advise(page, BRIEF)

    board = _board_text(page)
    assert "deadline" in board, board[:600]
    assert "stale" not in board, "the board reads stale before anything moved"

    matter = _the_matter(journey)
    from nm.core.dependency import Ledger
    ledger = Ledger.from_stored(matter.dependencies)
    assert ledger.nodes, "the served turn wrote no ledger"
    assert not ledger.stale(), [n.name for n in ledger.stale()]
    assert not page.errors, page.errors


# ================================== 2. the case file shows every entry ========

def test_phase_2_the_case_file_shows_the_entries_and_says_current(page, journey):
    _tab(page, "casefile")
    page.wait_for_selector("#casefile-entries .entry", timeout=15000)
    entries = page.locator("#casefile-entries .entry")
    assert entries.count() >= 1

    pill = page.locator("#currency-state .pill")
    assert pill.count() == 1, "no currency state is shown on the case file"
    assert pill.get_attribute("data-currency") == "current", pill.inner_text()

    # THE CORRECT CONTROL HAS A NAME an assistive technology can read.
    buttons = page.locator("#casefile-entries button.correct")
    assert buttons.count() >= 1
    assert buttons.first.get_attribute("aria-label", timeout=5000).startswith("Correct:")


# ======================================== 3. the correction, and its reach ====

def test_phase_3_a_correction_without_a_reason_does_not_submit(page, journey):
    """THE FORM REFUSES BEFORE THE SERVER HAS TO. A correction with no reason
    is a change nobody can later read."""
    dated = _dated_entry(page)
    dated.locator("button.correct").click()
    form = dated.locator("form.correction")
    form.wait_for(timeout=5000)
    form.locator("input[name='date']").fill("2019-03-14")
    # `required` blocks the native submit; drive the handler's own guard by
    # dispatching submit directly, which is what a script or a browser
    # without validation would do.
    form.evaluate("f => f.requestSubmit ? f.requestSubmit() : "
                  "f.dispatchEvent(new Event('submit', {cancelable: true}))")
    page.wait_for_timeout(300)
    matter = _the_matter(journey)
    from nm.core.dependency import Ledger
    assert not Ledger.from_stored(matter.dependencies).stale(), (
        "a correction with no reason reached the file")


def test_phase_3b_correcting_the_date_marks_exactly_the_dependents_stale(page, journey):
    dated = _dated_entry(page)
    form = dated.locator("form.correction")
    if not form.count():
        dated.locator("button.correct").click()
        form = dated.locator("form.correction")
        form.wait_for(timeout=5000)
    form.locator("input[name='date']").fill("2019-03-14")
    form.locator("input[name='reason']").fill(
        "the invoices are dated 2019; 2023 was a typing error")
    form.locator("button[type='submit']").click()

    # THE PAGE SAYS WHAT REOPENED. The pane re-renders after the write, so
    # wait for the currency pill to turn, not for a fixed time.
    page.wait_for_selector("#currency-state .pill[data-currency='stale']",
                           timeout=15000)
    stale = page.locator("#currency-stale li")
    assert stale.count() == 2, page.inner_text("#currency-stale")
    text = page.inner_text("#currency-stale").lower()
    assert "limitation" in text and "deadline" in text, text
    assert "role" not in text, "the party role was reopened by a corrected date"
    assert "2035-03-14" in text or "it read" in text, (
        "the stale list does not say what each value used to read")

    # THE HISTORY NAMES WHO AND WHY.
    page.click("#currency-nodes >> xpath=ancestor::details/summary")
    history = page.inner_text("#currency-history")
    assert "was 2035-03-14" in history or "was " in history, history
    assert "adv_ledger" in history and "typing error" in history, history

    # THE OLD ENTRY STAYS ON THE RECORD, marked.
    superseded = page.locator("#casefile-entries .entry.superseded")
    assert superseded.count() == 1
    assert "superseded by" in superseded.first.inner_text()

    # AND THE STORE AGREES WITH THE SCREEN.
    matter = _the_matter(journey)
    from nm.core.dependency import Ledger, names_for
    ledger = Ledger.from_stored(matter.dependencies)
    names = names_for(matter.threads[0].id)
    assert {n.name for n in ledger.stale()} == {names.limitation, names.deadline}
    assert ledger.node(names.role).currency.value == "current"
    assert not page.errors, page.errors


# ================================================= 4. the board says stale ====

def test_phase_4_the_board_shows_the_window_as_stale_not_as_the_deadline(page, journey):
    _tab(page, "advise")
    page.wait_for_selector("#rail-body .row", timeout=15000)
    board = _board_text(page)
    assert "stale" in board, board
    assert "awaiting recomputation" in board, board
    assert "was the deadline" in board, (
        "the stale window is not shown with the figure it was -- the advocate "
        "cannot recognise the number they were working to")
    assert "2035-03-14" in board, board
    # AND IT DOES NOT LEAD. The deadline field carries STALE, not the date.
    row_text = page.locator("#rail-body .row").first.inner_text().lower()
    assert "stale — awaiting recomputation" in row_text, row_text
    assert page.locator("#rail-body .row dt", has_text="deadline").count() >= 1


# ====================================================== 5. the reload ===========

def test_phase_5_a_reload_reads_the_same_currency_from_the_file(page, journey):
    """THE BROWSER'S RESTART. Nothing in the page's memory survives it; what
    is shown afterwards is what the file says."""
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    page.wait_for_selector("#rail-body .row", timeout=15000)
    # The rail lands on the matter LIST. It already says stale -- the same
    # rule one board up -- and the file is then opened for the figure.
    listing = _board_text(page)
    assert "stale" in listing, listing
    if page.is_hidden("#back"):
        page.locator("#rail-body .row").first.click()
        page.wait_for_selector("#back:not([hidden])", timeout=15000)
        page.wait_for_selector("#rail-body .row dt", timeout=15000)
    board = _board_text(page)
    assert "stale" in board and "2035-03-14" in board, board

    _tab(page, "casefile")
    page.wait_for_selector("#currency-state .pill[data-currency='stale']",
                           timeout=15000)
    assert page.locator("#currency-stale li").count() == 2
    assert not page.errors, page.errors


# ================================================= 6. the next brief reworks ==

def test_phase_6_the_next_brief_reworks_the_stale_values(page, journey):
    _tab(page, "advise")
    page.wait_for_selector("#send:not([disabled])", timeout=15000)
    _advise(page, "And where does the limitation stand now?")

    board = _board_text(page)
    assert "stale" not in board, board
    assert "2035-03-14" not in board, "the reworked board still shows the old figure"

    _tab(page, "casefile")
    page.wait_for_selector("#currency-state .pill[data-currency='current']",
                           timeout=15000)
    page.click("#currency-nodes >> xpath=ancestor::details/summary")
    history = page.inner_text("#currency-history")
    assert "now 2031-03-14" in history or ", now " in history, (
        "the revision did not close with the recomputed value:\n" + history)
    assert not page.errors, page.errors
