"""Saved matters keep their index beside a selected conversation and board."""

import pytest

from tests.test_the_journey_login_to_logout import (
    WIDTHS,
    _sign_in,
    _sign_out,
)
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
page = _page


@pytest.fixture
def journey(tmp_path):
    from assurance.journeys.served import PASSWORD, running
    from nm.brain.turn import BrainService, BrainTurn
    from tests.test_brain_material import Model, material
    from tests.test_brain_turn import plan

    entries = [
        ("Synthetic Cedar client: Access obstruction",
         "Our client reports that the neighbour blocked access to the premises."),
        ("Synthetic Cedar client: Agreement termination",
         "Our client disputes the supplier's termination of the agreement."),
    ]
    with running(tmp_path / "workspace") as (box, base):
        advocate = box.enrol()
        matters = []
        for index, (title, message) in enumerate(entries):
            opening = plan(message, scope="proposed", step="legal_work",
                           reply="The account requires the relevant records.",
                           title=title, summary=message)
            opening["material"] = [material("dispute", title, message)]
            result = BrainService(box.application.store, Model([opening])).run(
                BrainTurn(advocate, message, f"workspace-layout-{index}",
                          offer={"message": message})).as_dict()
            assert result["matter_id"]
            matters.append({"id": result["matter_id"], "title": title,
                            "message": message})
        yield {"box": box, "base": base, "advocate": advocate,
               "password": PASSWORD, "matters": matters}


def _show_my_work(page):
    page.get_by_role("button", name="My work", exact=True).click()
    page.wait_for_selector("#rail-body .row[data-matter-id]")


def _select_saved_matter(page, matter, *, key=None):
    if page.is_hidden("#rail"):
        page.click("#matters-toggle")
    row = page.locator(f'#rail-body .row[data-matter-id="{matter["id"]}"]')
    row.wait_for(state="visible")
    if key:
        row.focus()
        row.press(key)
    else:
        row.click()
    page.wait_for_function(
        "title => document.querySelector('#matter-heading').textContent === title",
        arg=matter["title"],
    )
    page.wait_for_selector("#send:not([disabled])")
    page.locator("#thread .brief").get_by_text(matter["message"], exact=True).wait_for()


def _open_saved_matter(page, journey, width=1280, height=900):
    _sign_in(page, journey, width=width, height=height)
    _show_my_work(page)
    _select_saved_matter(page, journey["matters"][0])
    return journey["matters"][0]


@pytest.mark.parametrize("width,height", WIDTHS)
def test_my_work_starts_blank_and_selection_retains_the_saved_headings(
    page, journey, width, height,
):
    _sign_in(page, journey, width=width, height=height)
    _show_my_work(page)
    rows = page.locator("#rail-body .row[data-matter-id]")
    assert rows.count() == len(journey["matters"])
    for matter in journey["matters"]:
        row = page.locator(f'#rail-body .row[data-matter-id="{matter["id"]}"]')
        assert row.locator(".r-title").inner_text() == matter["title"]
        assert row.locator(".r-fields").count() == 0
    assert page.get_attribute("#pane-advise", "data-view") == "list"
    assert not page.get_attribute("#pane-advise", "data-matter-id")
    assert page.locator(".conversation").is_hidden()
    assert page.locator("#matter-board").is_hidden()
    assert page.locator("#thread").text_content() == ""
    assert page.locator("#matter-board-body").text_content() == ""
    if width > 820:
        assert page.locator("#sidebar-board > #rail").is_visible()
        assert page.locator("#pane-advise").inner_text().strip() == ""

    first, second = journey["matters"]
    for matter, key in ((first, "Enter"), (second, "Space")):
        _select_saved_matter(page, matter, key=key)
        assert page.get_attribute("#pane-advise", "data-matter-id") == matter["id"]
        assert rows.count() == len(journey["matters"])
        selected = page.locator('#rail-body .row[aria-pressed="true"]')
        assert selected.count() == 1
        assert selected.get_attribute("data-matter-id") == matter["id"]
        assert page.locator("#matter-heading").inner_text() == matter["title"]
        other = first if matter is second else second
        assert other["message"] not in page.locator("#thread").text_content()
        if width > 820:
            assert page.locator("#rail").is_visible()
            assert page.locator("#matter-board").is_visible()
            chat = page.locator(".conversation").bounding_box()
            board = page.locator("#matter-board").bounding_box()
            assert chat and board
            assert board["x"] >= chat["x"] + chat["width"] - 1
        else:
            assert page.locator("#rail").is_hidden()
            assert page.locator("#composer").is_visible()
            page.click("#board-toggle")
            assert page.locator("#matter-board").is_visible()
            assert page.locator("#rail").is_hidden()
            page.click("#board-toggle")
            assert page.locator("#composer").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    _show_my_work(page)
    assert page.locator(".conversation").is_hidden()
    assert page.locator("#matter-board").is_hidden()
    assert page.locator("#thread").text_content() == ""
    assert page.locator("#matter-board-body").text_content() == ""
    assert not page.errors


@pytest.mark.parametrize("width,height", WIDTHS)
def test_one_board_and_reachable_account_without_a_ribbon_over_chat(
    page, journey, width, height,
):
    matter = _open_saved_matter(page, journey, width, height)
    mid = matter["id"]
    page.wait_for_selector('#matter-board-body .dispute-proposal-item', state='attached')
    data = page.request.get(f"{journey['base']}/api/matters/{mid}").json()
    dispute_count = len(data['agenda']['disputes']) + len(data['proposed_disputes']['rows'])
    assert dispute_count > 0, "the saved proposal must remain visible on its board"
    assert page.locator('#matter-board-body .dispute-proposal-item').count() == (
        len(data['agenda']['disputes']) + len(data['proposed_disputes']['rows']))
    assert page.locator("#matter-board").count() == 1
    assert page.locator("#rail-body .dispute-proposal-item").count() == 0
    assert page.locator("#rail-body .row[data-matter-id]").count() == 2
    assert page.locator("#matter-board-meta").inner_text() == ""
    if width <= 820:
        page.click("#board-toggle")
    assert page.get_by_role('button', name='Whole matter', exact=True).count() == 0
    assert page.locator('#matter-board-body .dispute-proposal-item').first.is_visible()
    assert page.locator("#matter-heading").inner_text() == data['title']
    if width <= 820:
        page.click("#board-toggle")
    else:
        assert page.locator("#sidebar-board > #rail").count() == 1
        chat = page.locator(".conversation").bounding_box()
        board = page.locator("#matter-board").bounding_box()
        sidebar = page.locator("#masthead").bounding_box()
        profile = page.locator("#account-toggle").bounding_box()
        assert chat and board and sidebar and profile
        # A scripted rehearsal must retain its truthful warning above chat.
        warning = page.locator("#rehearsal-warning")
        warning_height = warning.bounding_box()["height"] if warning.is_visible() else 0
        assert abs(chat["y"] - warning_height) <= 1
        assert chat["height"] >= height - warning_height - 1
        assert chat["x"] >= sidebar["width"] - 1
        assert board["x"] >= chat["x"] + chat["width"] - 1
        assert profile["x"] < sidebar["width"] and profile["y"] > height - 140
    page.click("#account-toggle")
    panel = page.locator("#account-panel")
    assert panel.is_visible()
    panel_box = panel.bounding_box()
    assert panel_box["y"] >= 0 and panel_box["y"] + panel_box["height"] <= height
    page.keyboard.press("Escape")
    assert not panel.is_visible()
    page.click("#files-toggle")
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


def test_resizing_keeps_one_index_and_one_reachable_board(page, journey):
    _open_saved_matter(page, journey)
    for width in (390, 1280, 820, 1024):
        page.set_viewport_size({"width": width, "height": 900})
        parent = "#pane-advise" if width <= 820 else "#sidebar-board"
        page.wait_for_selector(f"{parent} > #rail", state="attached")
        assert page.locator("#rail").count() == 1
        assert page.locator("#pane-advise > #matter-board").count() == 1
        if width <= 820:
            page.click("#matters-toggle")
            assert page.locator("#rail").is_visible()
            page.click("#matters-toggle")
            page.click("#board-toggle")
            assert page.locator("#matter-board").is_visible()
            page.click("#board-toggle")
        assert page.locator("#composer").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not page.errors


@pytest.mark.parametrize("width", [390, 768, 821, 1024, 1280, 1536])
def test_navigation_is_one_compact_row_with_complete_labels(page, journey, width):
    matter = _open_saved_matter(page, journey, width, 900)
    matter_id = matter["id"]
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
        # Matter creation completes before its checked board read is painted.
        # Wait for the real board, not a fixed delay or an unrelated tab.
        page.locator('#matter-heading').wait_for(state='visible')
        assert page.locator('#matter-heading').is_visible()
    for name, pane in [('Home', 'home'), ('Legal library', 'search'),
                       ('Preparation', 'prepare'), ('My work', 'advise')]:
        tab = page.get_by_role('button', name=name, exact=True)
        tab.focus()
        page.keyboard.press('Enter')
        page.wait_for_selector(f'#pane-{pane}:not([hidden])')
        assert tab.get_attribute('aria-current') == 'page'
        assert page.locator('#tabs [aria-current="page"]').count() == 1
    _select_saved_matter(page, matter)
    page.wait_for_selector('#composer:not([hidden])')
    assert page.get_attribute('#pane-advise', 'data-matter-id') == matter_id
    assert not page.errors


def test_answer_is_ordered_paragraphs_not_internal_labels(page, journey):
    _open_saved_matter(page, journey)
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
    assert "How this answer was made" not in page.locator("#thread").text_content()
    assert not page.errors
