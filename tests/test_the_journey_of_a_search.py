"""Research in a real browser. BK-38-AC1, BK-38-AC2, BK-45-AC1. P21's browser proof.

    "The research journey requires a post-submission result, explicit
     no-results or unavailable state and does not pass on static form labels."

Every phase here waits for `#research-outcome[data-outcome]` -- an element the
page creates only AFTER a submission has been answered -- and then reads the
outcome value. A page with the search box, the labels and the filters on it
and no submission behind them has no such element, and every phase fails on
the wait. That is BK-45-AC1's rule made into the harness rather than a
sentence: a no-op submit cannot pass here.

The indexes are SYNTHETIC (`tests/synthetic_index.py`), in the real schema,
holding invented judgments that say so in their own text.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.journey

playwright_api = pytest.importorskip(
    "playwright.sync_api",
    reason="the journey suite needs a browser: pip install -e .[journey] "
           "&& python -m playwright install chromium")

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".nm" / "journey"
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "backend"))

from tests.test_the_journey_login_to_logout import _start_matter  # noqa: E402
from tests.test_the_journey_login_to_logout import _tab as _open_surface  # noqa: E402

BRIEF = ("We act for the plaintiff at Hyderabad. Goods were supplied against "
         "invoices on 14 March 2023 and were never paid for.")


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    from nm.adapters.search.authority import AuthorityIndexSearch

    from assurance.journeys.served import PASSWORD, running
    from tests import synthetic_index as syn

    root = tmp_path_factory.mktemp("journey-search")
    authority, identity = syn.build(root / "index")
    search = AuthorityIndexSearch(authority, identity_path=identity)
    with running(root / "store", search=search) as (box, base):
        advocate = box.enrol("adv_search")
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD}


@pytest.fixture(scope="module")
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
    page.fill("#in-client", "Research Traders")
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
    _open_surface(page, name)


def _submit_research(page, query: str, *, court: str = "", objective="whether the marker was blue",
                     issue="colour at delivery") -> str:
    """Submit, then WAIT FOR THE OUTCOME ELEMENT and return its value.

    The wait is the whole control: the element exists only after an answered
    submission. Labels, placeholders and a filled box produce nothing here.
    """
    page.locator("#research-outcome").evaluate_all("els => els.forEach(e => e.remove())")
    if not page.is_checked("#r-on"):
        page.check("#r-on")
    page.fill("#r-objective", objective)
    page.fill("#r-issue", issue)
    page.fill("#r-citation", "")
    page.fill("#f-court", court)
    page.fill("#q", query)
    page.click("#search-form button[type='submit']")
    page.wait_for_selector("#research-outcome[data-outcome]", timeout=30000)
    return page.get_attribute("#research-outcome", "data-outcome")


# ================================================== 1. a matter to research ==

def test_phase_1_a_matter_is_open_and_research_is_offered_for_it(page, journey):
    _sign_in(page, journey)
    _start_matter(page)
    _intake(page)
    _advise(page, BRIEF)
    _tab(page, "search")
    assert not page.is_disabled("#r-on"), "research on the open matter is not offered"
    assert "open matter" in page.inner_text("#r-matter")
    assert not page.errors, page.errors


# ============================================ 2. results, and the cases =====

def test_phase_2_a_submission_produces_cases_not_labels(page, journey):
    outcome = _submit_research(page, "marker blue delivery")
    assert outcome == "results", outcome
    cases = page.locator("#research-cases .case")
    assert cases.count() >= 1
    marker = page.locator("#research-cases .case[data-case-id='SYN_1990_MARKER']")
    assert marker.count() == 1, page.inner_text("#research-cases")[:400]
    assert "2 paragraphs matched" in marker.inner_text(), marker.inner_text()
    assert "searched" in marker.inner_text().lower()
    # THE RECORD IS ON THE PAGE, with the adverse-search state as a value.
    record = page.inner_text("#research-record").lower()
    assert "rounds" in record and "1 of 2" in record, record
    assert "adverse search" in record


def test_phase_3_the_case_opens_to_its_paragraphs_by_locator(page, journey):
    marker = page.locator("#research-cases .case[data-case-id='SYN_1990_MARKER']")
    marker.locator("button.open-case").click()
    page.wait_for_selector(
        "#research-cases .case[data-case-id='SYN_1990_MARKER'] .para", timeout=15000)
    paras = marker.locator(".para")
    assert paras.count() == 3, paras.count()
    cover = marker.locator(".case-cover").inner_text().lower()
    assert "read back by locator" in cover
    assert "attributable paragraphs only" in cover, (
        "the expansion does not say its coverage; an incomplete case read as whole")
    assert marker.locator(".para[data-locator='SYN_1990_MARKER_P002_C01']").count() == 1
    assert marker.locator(".para[data-locator='SYN_1990_MARKER_P003_C01']").count() == 1


def test_phase_4_attaching_a_paragraph_shows_five_verdicts_not_one(page, journey):
    para = page.locator(".para[data-locator='SYN_1990_MARKER_P002_C01']")
    para.locator("button.attach").click()
    para.locator(".verdict-list").wait_for(timeout=15000)
    verdicts = para.locator(".verdict-list").inner_text().lower()
    for word in ("identity", "quote", "support", "treatment", "applies here"):
        assert word in verdicts, (word, verdicts)
    assert "resolved" in verdicts and "verbatim" in verdicts
    assert "not_assessed" in verdicts, "support was shown as established"
    note = para.locator(".verdict-note").inner_text().lower()
    assert "verified citation" in note and "identity and words only" in note
    record = page.inner_text("#research-record").lower()
    assert "attached to colour at delivery" in record, record
    assert not page.errors, page.errors


# ================================================ 3. the other outcomes =====

def test_phase_5_no_results_is_said_as_searched_not_as_absence_of_law(page, journey):
    outcome = _submit_research(page, "zebra quantum trombone",
                               objective="a proposition nothing holds")
    assert outcome == "searched_no_results", outcome
    said = page.inner_text("#research-outcome").lower()
    assert "no case matched" in said
    assert "not what the law is" in said
    assert page.locator("#research-cases .case").count() == 0


def test_phase_6_an_unsupported_court_is_not_a_zero(page, journey):
    outcome = _submit_research(page, "marker blue", court="Bombay High Court",
                               objective="a court this corpus does not hold")
    assert outcome == "unsupported_coverage", outcome
    said = page.inner_text("#research-outcome").lower()
    assert "outside what this corpus holds" in said, said


# ============================================= 4. the record survives =======

def test_phase_7_a_reload_shows_the_research_record_from_the_file(page, journey):
    page.reload()
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    # A sign-in lands on Home (F-A-18); My work is the list of matters (F-B-03).
    _tab(page, "advise")
    page.wait_for_selector("#rail-body .row", timeout=15000)
    if page.is_hidden("#back"):
        page.locator("#rail-body .row").first.click()
        page.wait_for_selector("#back:not([hidden])", timeout=15000)
    _tab(page, "search")
    page.wait_for_selector("#research-record:not([hidden])", timeout=15000)
    record = page.inner_text("#research-record").lower()
    assert "research record" in record
    assert "attached to colour at delivery" in record or "rounds" in record, record
    assert not page.errors, page.errors
