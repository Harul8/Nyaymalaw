"""Synthetic browser design witnesses; not a WCAG or advocate-acceptance certificate."""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import WIDTHS, _sign_in
from tests.test_the_workspace_respects_its_current_context import journey as _journey
from tests.test_the_workspace_respects_its_current_context import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


_CONTRAST = """selector => {
  const channels = text => (text.match(/[\\d.]+/g) || []).map(Number);
  const luminance = rgb => rgb.slice(0, 3).map(v => {
    v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
  return [...document.querySelectorAll(selector)].filter(el => {
    const box = el.getBoundingClientRect();
    return box.width && box.height && getComputedStyle(el).visibility !== 'hidden';
  }).map(el => {
    const style = getComputedStyle(el);
    let at = el, bg;
    while (at) {
      const current = channels(getComputedStyle(at).backgroundColor);
      if (current.length === 3 || current[3] === 1) { bg = current; break; }
      at = at.parentElement;
    }
    const fg = channels(style.color);
    if (!bg || (fg.length > 3 && fg[3] !== 1)) throw Error('Unmeasured layered colour');
    const a = luminance(fg), b = luminance(bg);
    return {text: el.textContent.trim().slice(0, 90),
      ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)};
  });
}"""


@pytest.mark.parametrize("colour_scheme", ["light", "dark"])
@pytest.mark.parametrize("width,height", WIDTHS)
def test_intake_and_workspace_keep_readable_controls_in_each_theme(
    page, journey, colour_scheme, width, height,
):
    page.emulate_media(color_scheme=colour_scheme)
    _sign_in(page, journey, width, height)
    launch = page.locator("#materials-open")
    assert launch.is_visible() and launch.is_enabled()
    box = launch.bounding_box()
    assert box and box["height"] >= 42
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    # Keyboard-only operation through the shipped control, not a scripted click handler.
    launch.focus()
    page.keyboard.press("Enter")
    dialog = page.locator("#materials-dialog")
    dialog.wait_for(state="visible")
    assert page.locator("#materials-close").evaluate("el => el === document.activeElement")
    assert page.locator("#materials-files").is_visible()
    assert page.locator("#materials-record").is_visible()
    assert "not scanned, admitted, transcribed or read" in dialog.inner_text()
    samples = page.evaluate(_CONTRAST, (
        "#materials-dialog h2, #materials-dialog label, "
        "#materials-dialog .materials-muted, #materials-dialog .materials-limit, "
        "#materials-dialog button:not(:disabled)"))
    assert len(samples) >= 10, samples
    assert all(row["ratio"] >= 4.5 for row in samples), samples
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert dialog.evaluate("el => el.scrollWidth <= el.clientWidth")
    page.keyboard.press("Escape")
    assert not dialog.is_visible()
    assert launch.evaluate("el => el === document.activeElement")
    assert not page.errors
    assert not page.external_assets
