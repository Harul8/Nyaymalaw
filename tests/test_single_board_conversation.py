"""DG-14: presentation witnesses, not proof of live-model legal judgment."""

import pytest

from tests.test_opening_journey import saved
from tests.test_the_journey_login_to_logout import (
    BRIEF,
    WIDTHS,
    _advise,
    _open_matter,
    _sign_out,
)
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


@pytest.mark.parametrize("width,height", WIDTHS)
def test_one_board_and_reachable_account_without_a_ribbon_over_chat(
    page, journey, width, height,
):
    client = f"Synthetic recorded client {width}"
    _open_matter(page, journey, client=client, width=width, height=height)
    mid, _ = saved(page)
    _advise(page, BRIEF)
    page.wait_for_selector('#rail-body .dispute-row', state='attached')
    data = page.request.get(f"{journey['base']}/api/matters/{mid}").json()
    assert len(data["threads"]) > 0, "removing issue cards must not remove saved issues"
    assert page.locator('#rail-body .dispute-row').count() == len(data['agenda']['disputes'])
    assert page.locator("#matter-board").count() == 1
    assert page.locator("#rail-body .row").count() == 0
    assert page.locator("#rail-meta").inner_text() == ""
    if width <= 820:
        page.click("#matters-toggle")
    assert page.get_by_role('button', name='Whole matter', exact=True).count() == 1
    assert page.locator('#rail-body .dispute-row').first.is_visible()
    page.locator("#board-fields").filter(has_text=client).wait_for()
    assert client in page.locator("#matter-board").inner_text()
    assert "Kiran Steels" in page.locator("#matter-board").inner_text()
    assert "our client" not in page.locator("#rail").inner_text().lower()
    if width <= 820:
        page.click("#matters-toggle")
    else:
        assert page.locator("#sidebar-board > #rail").count() == 1
        chat = page.locator(".conversation").bounding_box()
        sidebar = page.locator("#masthead").bounding_box()
        profile = page.locator("#account-toggle").bounding_box()
        assert chat and sidebar and profile
        # A scripted rehearsal must retain its truthful warning above chat.
        warning = page.locator("#rehearsal-warning")
        warning_height = warning.bounding_box()["height"] if warning.is_visible() else 0
        assert abs(chat["y"] - warning_height) <= 1
        assert chat["height"] >= height - warning_height - 1
        assert chat["x"] >= sidebar["width"] - 1
        assert profile["x"] < sidebar["width"] and profile["y"] > height - 140
    page.click("#account-toggle")
    panel = page.locator("#account-panel")
    assert panel.is_visible()
    panel_box = panel.bounding_box()
    assert panel_box["y"] >= 0 and panel_box["y"] + panel_box["height"] <= height
    page.keyboard.press("Escape")
    assert not panel.is_visible()
    page.get_by_role("button", name="Case file", exact=True).click()
    assert page.locator("#pane-casefile").is_visible()
    assert not page.locator("#sidebar-board").is_visible()
    page.get_by_role("button", name="My work", exact=True).click()
    assert page.locator("#pane-advise").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    _sign_out(page)
    page.wait_for_selector("#gate:not([hidden])")
    assert page.locator("#masthead").is_hidden()
    assert not page.errors


def test_resizing_moves_one_board_and_keeps_it_reachable(page, journey):
    _open_matter(page, journey, client="Synthetic resize identity")
    saved(page)
    for width in (390, 1280, 820, 1024):
        page.set_viewport_size({"width": width, "height": 900})
        parent = "#pane-advise" if width <= 820 else "#sidebar-board"
        page.wait_for_selector(f"{parent} > #rail", state="attached")
        assert page.locator("#rail").count() == 1
        if width <= 820:
            page.click("#matters-toggle")
            assert page.locator("#matter-board").is_visible()
            page.click("#matters-toggle")
        assert page.locator("#composer").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not page.errors


@pytest.mark.parametrize("width", [390, 768, 821, 1024, 1280, 1536])
def test_navigation_is_one_compact_row_with_complete_labels(page, journey, width):
    _open_matter(page, journey, client=f"Synthetic compact navigation {width}",
                 width=width, height=900)
    matter_id, _ = saved(page)
    tabs = page.locator('#tabs .tab')
    assert tabs.all_text_contents() == ['Home', 'My work', 'Legal library', 'Preparation']
    boxes = [tab.bounding_box() for tab in tabs.all()]
    assert all(box is not None for box in boxes)
    assert max(box['y'] for box in boxes) - min(box['y'] for box in boxes) <= 1
    for tab, box in zip(tabs.all(), boxes, strict=True):
        assert box['height'] >= 24
        assert box['x'] >= 0 and box['x'] + box['width'] <= width
        assert tab.evaluate('el => el.scrollWidth <= el.clientWidth')
    if width > 820:
        assert page.locator('#tabs').bounding_box()['height'] <= 42
        assert page.locator('#board-title').is_visible()
    for name, pane in [('Home', 'home'), ('Legal library', 'search'),
                       ('Preparation', 'prepare'), ('My work', 'advise')]:
        tab = page.get_by_role('button', name=name, exact=True)
        tab.focus()
        page.keyboard.press('Enter')
        page.wait_for_selector(f'#pane-{pane}:not([hidden])')
        assert tab.get_attribute('aria-current') == 'page'
        assert page.locator('#tabs [aria-current="page"]').count() == 1
    page.locator(f'#rail-body [data-matter-id="{matter_id}"]').click()
    page.wait_for_selector('#composer:not([hidden])')
    assert page.get_attribute('#pane-advise', 'data-matter-id') == matter_id
    assert not page.errors


def test_answer_is_ordered_paragraphs_not_internal_labels(page, journey):
    _open_matter(page, journey, client="Synthetic paragraph presentation")
    saved(page)
    # This is a controlled renderer witness; no paid model or saved answer.
    texts = ["A precise question?", "A material limitation remains.",
             "A qualified assessment.", "An unfamiliar section must survive."]
    elements = [
        {"kind": "question", "section": "needed", "signal": "unresolved_posture"},
        {"kind": "ground", "section": "risk", "signal": "none", "disclosure": True},
        {"kind": "finding", "section": "position", "signal": "none"},
        {"kind": "finding", "section": "future_section", "signal": "none"},
    ]
    for element, text in zip(elements, texts, strict=True):
        element.update(text=text, refs=[])
    elements.append({"kind": "ground", "section": "authority", "signal": "none",
                     "text": "Exact supplied supporting passage.", "refs": ["synthetic-ref"]})
    page.evaluate("""elements => document.getElementById('thread').replaceChildren(
        renderTurn({answer: {elements, metrics: null}}))""", elements)
    assert page.locator("#thread > .turn > .el > p.body").all_text_contents() == texts
    assert page.locator("#thread .section, #thread .el .k").count() == 0
    assert page.locator("#thread .el").count() == len(elements)
    assert page.locator("#thread .disclosure").is_visible()
    assert page.locator("#thread .support").evaluate("el => el.open")
    assert page.get_by_text("Exact supplied supporting passage.", exact=True).is_visible()
    assert page.get_by_text("synthetic-ref", exact=True).is_visible()
    assert not page.locator("#thread .audit").evaluate("el => el.open")
    assert not page.errors
