"""THE BROWSER JOURNEY FOR P33, P25 AND P27. BK-88-AC1, BK-94-AC5, BK-55-AC3.

WHAT A BROWSER TEST IS FOR HERE
---------------------------------
Every rule these packets carry is already proved against the domain and the
wire. This suite exists because CLAUDE.md §8 is the one this repository keeps
paying for: *every defect the first external review found lived between a
correct module and the served path*. A guard that is right in the core and
absent from the screen is a guard the advocate does not have.

So each phase drives the real page against a real server and asserts on what
the advocate can SEE and on what the server actually stored -- not on one or
the other. A phase that passed by reading its own POST response back would
prove the browser can talk to itself.

THE PHASES ARE A SEQUENCE and share one matter, in the order an advocate would
meet them: attach a document to the right dispute, decide something about the
advice, then ask for material to be erased and watch a hold refuse it.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".nm" / "journey"
sys.path.insert(0, str(ROOT))

pytestmark = [pytest.mark.journey, pytest.mark.class_d]

BRIEF = ("We act for Ledger Traders in a recovery suit against Kiran Steels. "
         "Goods were supplied against invoices on 14 March 2023 and were "
         "never paid for.")


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    from assurance.journeys.served import PASSWORD, running

    root = tmp_path_factory.mktemp("journey-custody")
    with running(root / "store") as (box, base):
        advocate = box.enrol("adv_custody")
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD}


@pytest.fixture(scope="module")
def page(journey):
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 1000})
        pg = context.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.errors = errors

        # WHAT THE SERVER ACTUALLY ANSWERED. A form that refuses renders its
        # reason, but a phase that never fires the submit renders nothing at
        # all -- and the two look identical from the page text. This tells
        # them apart.
        calls: list[str] = []

        def _seen(response):
            if "/api/" in response.url and response.request.method != "GET":
                calls.append(f"{response.request.method} "
                             f"{response.url.split('/api/')[-1]} -> "
                             f"{response.status}")
        pg.on("response", _seen)
        pg.api_calls = calls
        try:
            yield pg
        finally:
            context.close()
            browser.close()


@pytest.fixture(autouse=True)
def _artifact_on_failure(request, page):
    yield
    report = getattr(request.node, "rep_call", None)
    if report is None or report.failed:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        stem = request.node.name.replace("/", "_")[:80]
        try:
            page.screenshot(path=str(ARTIFACTS / f"{stem}.png"), full_page=True)
            (ARTIFACTS / f"{stem}.html").write_text(page.content(),
                                                    encoding="utf-8")
        except Exception:  # noqa: BLE001 -- an artifact is best effort
            pass


def _tab(page, name: str) -> None:
    """Go to a pane, and DO NOT re-click the one already open.

    Clicking the active tab re-runs the pane's async load, which replaces the
    forms mid-phase: the test fills inputs that are then thrown away, the
    click lands on a fresh empty form, and `required` makes the browser refuse
    the submit silently. Nothing is sent and the page looks untouched.

    Waiting longer does not fix it -- the race is with a render the click
    itself started, so the fix is not to start it. An advocate already on the
    case file does not click "Case file" again either.
    """
    if page.is_hidden(f"#pane-{name}"):
        page.click(f'.tab[data-tab="{name}"]')
        page.wait_for_selector(f"#pane-{name}:not([hidden])", timeout=15000)
    if name == "casefile":
        _settle_casefile(page)


def _settle_casefile(page) -> None:
    """WAIT FOR THE PANE TO FINISH DRAWING BEFORE TOUCHING A FORM.

    `showCasefile` is async and renders the three governance blocks in turn.
    Filling a form while that is still running gets the inputs REPLACED by the
    re-render before the click lands -- and the click then submits a fresh,
    empty form, whose `required` inputs make the browser refuse it. No request
    is sent, no error is shown, and the pane looks exactly as it did before.

    That cost an hour: the page text was identical to a form nobody had
    touched, and only a log of the unsafe requests told the two apart.

    THE SIGNAL IS THAT THE PANE STOPPED FETCHING. A first attempt waited for
    the retention block to have children -- already true from the previous
    phase, so the wait returned instantly and the re-render replaced the form
    exactly as before. A condition that is already satisfied is not a wait; it
    is a comment.
    """
    page.wait_for_selector("#retention-host", timeout=15000)
    page.wait_for_load_state("networkidle")


def _choose_matter(page, matter_id: str) -> None:
    """Pick the matter explicitly. AFTER A RELOAD NOTHING HAS PICKED ONE.

    The pane opens on "Choose a matter" when the app has no current matter in
    memory, so the governance blocks render against nothing and every wait on
    them waits on a hidden div. Selecting is what an advocate does here too.
    """
    page.wait_for_selector("#casefile-matter", timeout=15000)
    page.select_option("#casefile-matter", matter_id)
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#retention-host", timeout=15000)


def _sign_in(page, journey) -> None:
    """The canonical sequence, copied from the login-to-logout journey rather
    than guessed. The selectors are `#login-id` and `#login-password`; an
    earlier version of this file invented `#login-advocate` and timed out
    against a form that was working perfectly."""
    page.goto(journey["base"] + "/")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    page.fill("#login-id", journey["advocate"])
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])", timeout=20000)


def _open_matter(page) -> None:
    """THE PRODUCT ASKS BEFORE IT WORKS, so the journey answers before it
    briefs -- exactly as an advocate does.

    `#new-matter` comes first and lives in the rail. Omitting it left
    `#message` present but invisible, which is the failure mode a selector
    that "exists" produces: the locator resolves and the action never lands.
    The viewport is 1280px, where the rail is open rather than a drawer.
    """
    page.click("#new-matter")
    page.wait_for_selector("#intake:not([hidden])", timeout=15000)
    if page.is_hidden("#intake"):
        return
    page.fill("#in-client", "Ledger Traders")
    page.fill("#in-adverse", "Kiran Steels")
    page.fill("#in-scope", "recover the price of goods sold")
    page.check("#in-capacity")
    page.click("#in-go")
    page.wait_for_selector("#intake", state="hidden", timeout=15000)


def _advise(page, message: str) -> None:
    """Send a brief and WAIT FOR THE TURN TO FINISH DRAWING.

    The completion signal is the send control coming back, not the card
    appearing -- a phase that reads the page on `.turn` alone is asserting
    against a half-drawn answer, which passes on less than it claims.
    """
    page.fill("#message", message)
    page.click("#send")
    page.wait_for_selector(".turn", timeout=60000)
    page.wait_for_selector("#send:not([disabled])", timeout=90000)


def _selected_matter(page) -> str:
    """The matter the case-file pane is showing.

    A `<select>`'s current value is a DOM PROPERTY; the HTML attribute is not
    set and `get_attribute("value")` returns None for it. That read silently
    produced the empty matter id and every store assertion then looked at
    nothing.
    """
    chosen = page.eval_on_selector("#casefile-matter", "el => el.value")
    assert chosen, "the case-file pane is not showing any matter"
    return chosen


def _post_from_page(page, path: str, payload: dict) -> dict:
    """POST as the PAGE does, carrying its CSRF token and cookies.

    `page.request.post` shares the cookie jar but not the page's `X-NM-CSRF`
    header, so the server refused it with exactly the message it should:
    *this request could not be verified as coming from the Nyaymalaw page in
    this browser.* That refusal is the CSRF guard working, and routing around
    it with `--no-verify`-shaped cleverness would have tested a door the
    product does not have. The request is issued from inside the page instead.
    """
    result = page.evaluate(
        """async ({ path, payload }) => {
             const token = (document.cookie.match(/(?:^|; )nm_csrf=([^;]*)/)
                            || [])[1];
             const res = await fetch(path, {
               method: 'POST',
               headers: { 'Content-Type': 'application/json',
                          'X-NM-CSRF': token ? decodeURIComponent(token) : '' },
               body: JSON.stringify(payload),
             });
             let body = null;
             try { body = await res.json(); } catch (e) { body = null; }
             return { ok: res.ok, status: res.status, body };
           }""",
        {"path": path, "payload": payload})
    assert result["ok"], f"{path} -> {result['status']}: {result['body']}"
    return result["body"]


def _stored(journey, matter_id):
    """WHAT THE SERVER ACTUALLY HOLDS. Asserted beside the screen, because a
    page that renders its own POST response proves only that it can."""
    return journey["box"].application.store.load(matter_id)


# ================================================= phase 1: open the matter ==

def test_phase_1_a_matter_is_opened_and_the_governance_pane_is_there(
        page, journey):
    _sign_in(page, journey)
    _open_matter(page)
    _advise(page, BRIEF)

    _tab(page, "casefile")
    page.wait_for_selector("#governance", timeout=15000)
    heading = page.inner_text("#governance-h")
    assert "Custody" in heading, heading
    assert not page.errors, page.errors


# ============================================ phase 2: attribution, BK-94-AC5 =

def test_phase_2_an_unattached_document_is_attached_to_a_named_dispute(
        page, journey):
    """The advocate says which dispute the document belongs to. Nothing on the
    page offers to choose for them."""
    _tab(page, "casefile")
    page.wait_for_selector("#bindings-host .binding-form", timeout=15000)

    form = page.locator("#bindings-host .binding-form").last
    form.locator('input[name="source_id"]').fill("invoice_pack")
    form.locator('input[name="source_version"]').fill("v1")
    form.locator('input[name="thread_id"]').fill("thread_recovery")
    form.locator("button[type=submit]").click()

    try:
        page.wait_for_selector(
            '#bindings-host .binding[data-source-id="invoice_pack"]',
            timeout=15000)
    except playwright_api.TimeoutError:  # pragma: no cover -- diagnostic
        pytest.fail("the binding never appeared. the pane said: "
                    + page.inner_text("#bindings-host")[:400]
                    + " | unsafe calls: " + repr(page.api_calls[-6:]))
    shown = page.inner_text('#bindings-host .binding[data-source-id="invoice_pack"]')
    assert "thread_recovery" in shown, shown
    assert "you stated it" in shown.lower(), (
        f"an advocate's own attachment was shown as the product's reading: "
        f"{shown!r}")

    matter_id = _selected_matter(page)
    stored = _stored(journey, matter_id)
    assert any(row.get("thread_id") == "thread_recovery"
               for key, row in (stored.source_bindings or {}).items()
               if key != "__superseded__"), (
        "the page showed a binding the server did not store")
    assert not page.errors, page.errors


def test_phase_3_reattaching_names_the_dispute_whose_work_must_reopen(
        page, journey):
    """A correction is not an overwrite. The page says which dispute lost the
    source, so only that thread's work is reopened."""
    _tab(page, "casefile")
    row = page.locator('#bindings-host .binding[data-source-id="invoice_pack"]')
    row.locator('input[name="thread_id"]').fill("thread_second")
    row.locator("button[type=submit]").click()

    page.wait_for_function(
        "() => document.querySelector('#bindings-state').innerText.trim()"
        ".length > 0", timeout=15000)
    note = page.inner_text("#governance")
    assert "thread_recovery" in note, (
        f"the advocate is not told which dispute lost the source: {note[:400]}")
    assert not page.errors, page.errors


# ============================================== phase 4: decisions, BK-55-AC3 =

def test_phase_4_a_decision_is_recorded_and_says_it_is_not_authority(
        page, journey):
    """The clause the criterion turns on, on the screen: a recorded acceptance
    is not authority to file, send, settle or concede."""
    _tab(page, "casefile")
    page.wait_for_selector("#decisions-host .decision-form", timeout=15000)

    form = page.locator("#decisions-host .decision-form")
    form.locator("select").select_option("accept")
    values = {"advice_version": "v1", "scope": "the recovery thread",
              "owner": "adv_custody",
              "review_trigger": "if the defence pleads limitation"}
    for name, value in values.items():
        form.locator(f'input[name="{name}"]').fill(value)

    # THE VALUES ARE CHECKED BEFORE THE CLICK. A re-render between filling and
    # submitting empties the boxes, the browser refuses the submit because they
    # are `required`, and NOTHING is sent -- no request, no error, a pane that
    # looks untouched. Asserting here turns that into a failure that says so.
    held = {name: form.locator(f'input[name="{name}"]').input_value()
            for name in values}
    if held != values:  # pragma: no cover -- diagnostic
        dom = page.evaluate(
            """() => [...document.querySelectorAll('#decisions-host form')]
                     .map((f, i) => ({form: i, fields:
                       [...f.querySelectorAll('input')].map(
                         x => [x.name, x.value])}))""")
        pytest.fail(f"held={held!r} dom={dom!r}")
    assert held == values, (
        f"the form did not hold what it was given at submit time: {held!r}. "
        f"If every field is empty the form was re-rendered; if one is, the "
        f"fill did not land on the element the test thought it did.")
    form.locator("button[type=submit]").click()

    try:
        page.wait_for_selector("#decisions-host .decision", timeout=15000)
    except playwright_api.TimeoutError:  # pragma: no cover -- diagnostic
        detail = page.evaluate(
            """() => {
                 const f = document.querySelector('#decisions-host .decision-form');
                 if (!f) return {form: 'missing'};
                 return {
                   inputs: [...f.querySelectorAll('input')].map(
                     i => ({v: i.value, valid: i.checkValidity()})),
                   formValid: f.checkValidity(),
                 };
               }""")
        pytest.fail("no decision was recorded. the pane said: "
                    + page.inner_text("#decisions-host")[:250]
                    + " | calls: " + repr(page.api_calls[-4:])
                    + " | form: " + repr(detail)
                    + " | js errors: " + repr(page.errors[-3:]))
    shown = page.inner_text("#decisions-host")
    assert "accept" in shown.lower(), shown
    assert "not authority to file" in shown.lower(), (
        f"the screen records an acceptance without saying what it does not "
        f"authorise: {shown[:300]}")

    matter_id = _selected_matter(page)
    stored = _stored(journey, matter_id)
    assert stored.advice_decisions, "the decision was shown and not stored"
    assert not page.errors, page.errors


# =========================================== phase 5: held deletion refuses ===

def test_phase_5_a_held_erasure_refuses_and_the_screen_says_why(
        page, journey):
    """SECTION 5's demonstration, on the served page.

    The request is made through the API because the pane is a read surface for
    retention -- and then the REFUSAL is asserted on what the advocate sees,
    which is the half that matters.
    """
    matter_id = _selected_matter(page)
    stored = _stored(journey, matter_id)

    body = _post_from_page(page, "/api/retention-requests", {
        "matter_id": matter_id, "scope": "selected_assets",
        "asset_versions": [{"id": "invoice_pack", "version": 1}],
        "requested_action": "erase",
        "purpose": "the client withdrew consent",
        "authority_id": "auth_1", "authority_version": 1,
        "copies": [{"location": "invoice_pack", "kind": "original"},
                   {"location": "vendor-x", "kind": "processor"}],
        "expected_matter_version": stored.version})
    assert body["state"] == "review_requested", body

    _post_from_page(
        page, f"/api/retention-requests/{body['request_id']}/holds",
        {"matter_id": matter_id, "reason": "anticipated litigation",
         "expected_matter_version": body["matter_version"]})

    page.reload(wait_until="networkidle")
    page.wait_for_selector("#masthead:not([hidden])", timeout=20000)
    page.click('.tab[data-tab="casefile"]')
    page.wait_for_selector("#pane-casefile:not([hidden])", timeout=15000)
    _choose_matter(page, matter_id)
    page.wait_for_selector("#retention-host .retention-row", timeout=15000)
    shown = page.inner_text("#retention-host")
    assert "under hold" in shown.lower(), shown
    assert "legal_hold" in shown.lower(), (
        f"the screen shows a held request without saying it is held: {shown[:300]}")
    assert "vendor-x" in shown.lower(), (
        f"the outstanding processor copy is not named on the screen: {shown[:300]}")
    assert not page.errors, page.errors


def test_phase_6_the_screen_never_claims_a_completion_it_did_not_reach(
        page, journey):
    """The last thing an advocate should be able to read off this pane is that
    material is gone when it is not."""
    shown = page.inner_text("#retention-host")
    assert "complete for declared scope" not in shown.lower(), (
        f"a held, unresolved request rendered as complete: {shown[:300]}")
    assert not page.errors, page.errors
