"""Browser setup and workspace navigation shared by the synthetic journeys."""

from pathlib import Path

import pytest

playwright_api = pytest.importorskip(
    "playwright.sync_api",
    reason="the journey suite needs a browser: pip install -e .[journey] "
           "&& python -m playwright install chromium",
)
ARTIFACTS = Path(__file__).resolve().parents[1] / ".nm" / "journey"

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
    page.goto(journey["base"] + "/app")
    page.wait_for_selector("#gate:not([hidden])", timeout=15000)
    page.fill("#login-id", journey["advocate"])
    page.fill("#login-password", journey["password"])
    page.click("#login-go")
    page.wait_for_selector("#masthead:not([hidden])", timeout=15000)
    return page


def _reach_rail(page, width):
    """Get the matter navigator on screen, however this width offers it.

    THE RULE IS REACHABLE, NOT VISIBLE (BK-32). The rail was once a drawer
    below 820px behind a toggle; it is now the conversation history the top
    bar opens at every width. A phase that returned early when the rail
    happened to be on screen asserted nothing - which is what BK-47 was - so
    this always goes through the control.
    """
    # Recent work opens the list at every width and marks it as the current page.
    # Check the control and the list's bounds: an off-screen list can still count as visible.
    history = page.locator("#top-history")
    assert history.is_visible(), (
        f"at {width}px no control opens the conversation history, so an "
        f"advocate can work the matter they are in and reach no other one")
    if history.get_attribute("aria-current") != "page":
        history.click()
    page.wait_for_selector("#top-history[aria-current='page']", timeout=10000)
    page.wait_for_selector("#rail", state="visible", timeout=10000)
    box = page.locator("#rail").bounding_box()
    assert box and box["x"] + box["width"] > 0 and box["x"] < width, (
        f"at {width}px the control opened a list that is not on the screen")
