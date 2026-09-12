"""Real DOM renderer transfer only; synthetic signals are NOT legal assessment proof.

The unchanged canonical journey phase 6b retains the actual served expired-case
integration. Here every current domain Signal crosses the shipped renderer and
CSS at phone, tablet and desktop widths, without sending any invented matter.
"""
from __future__ import annotations

import pytest

from nm.domain.answer import Signal
from tests.test_the_journey_login_to_logout import WIDTHS, _sign_in
from tests.test_the_screen_never_folds_a_disclosure import renderer_signal_cases
from tests.test_the_workspace_respects_its_current_context import journey as _journey
from tests.test_the_workspace_respects_its_current_context import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


@pytest.mark.parametrize("width,height", WIDTHS)
def test_all_domain_signals_cross_the_real_renderer_without_a_fold(
    page, journey, width, height,
):
    _sign_in(page, journey, width, height)
    signals = renderer_signal_cases()
    assert {row["signal"] for row in signals} == {s.value for s in Signal if s.is_loud}
    assert len(signals) > 0
    ordinary = [{"kind": "ground", "text": f"Renderer-only support {index}.",
                 "signal": "none", "disclosure": False, "section": "because", "refs": []}
                for index in range(2)]
    disclosures = [{"kind": "ground", "text": f"Renderer-only unestablished item {index}.",
                    "signal": "none", "disclosure": True, "section": "needed", "refs": []}
                   for index in range(2)]
    uncertain = [{"kind": "ground", "text": f"Renderer-only uncertain signal {index}.",
                  "disclosure": False, "section": "risk", "refs": [], **fields}
                 for index, fields in enumerate(({}, {"signal": None},
                                                  {"signal": "future_signal"}))]
    question = {"kind": "question", "text": "Renderer fixture only; do not rely on this.",
                "signal": "none", "disclosure": False, "section": "needed", "refs": []}
    elements = [question, *ordinary, *disclosures, *signals, *uncertain]
    entry = {"brief": "Synthetic renderer-only visibility check, not a matter instruction.",
             "answer": {"elements": elements, "metrics": None}}
    # Deliberate renderer injection only. No request interception, turn/model
    # invocation, saved receipt, or claim that the server produced this advice.
    page.evaluate("""entry => {
      const rendered = renderTurn(entry);
      rendered.id = 'signal-renderer-probe';
      document.getElementById('thread').replaceChildren(rendered);
    }""", entry)
    probe = page.locator("#signal-renderer-probe")
    assert probe.locator(".el").count() == len(elements)
    assert probe.locator("details.support").count() == 1
    assert not probe.locator("details.support").evaluate("el => el.open")
    assert probe.locator("details.support .el").count() == len(ordinary)
    assert probe.locator("details .el.disclosure").count() == 0
    for row in (question, *signals, *uncertain, *disclosures):
        body = probe.get_by_text(row["text"], exact=True)
        assert body.count() == 1, row
        assert body.is_visible(), row
        assert body.evaluate("el => el.closest('details') === null"), row
        body.scroll_into_view_if_needed()
        box = body.bounding_box()
        assert box and box["width"] > 0 and box["height"] > 0, row
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, row
    for row in ordinary:
        body = probe.get_by_text(row["text"], exact=True)
        assert body.count() == 1 and not body.is_visible()
    probe.locator("details.support summary").click()
    for row in ordinary:
        assert probe.get_by_text(row["text"], exact=True).is_visible()
    assert not any(row["path"] == "/api/turn" for row in page.request_identities)
    assert not page.errors and not page.external_assets
