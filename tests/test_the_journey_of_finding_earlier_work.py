"""AN.55 D355(g): find, name, describe and reopen earlier work in a browser.

The page talks to the shipped server over HTTP. Saved conversations in the
throwaway store are synthetic so the journeys can check dates and replay
without making any model calls.
"""

from datetime import date, timedelta

import pytest

from assurance.journeys.served import PASSWORD, running
from nm.core_engine import response_rendering, turn
from nm.core_engine.conversation import commit_turn, hold_title, open_turn
from tests.test_the_journey_login_to_logout import _reach_rail, _sign_in
from tests.test_the_journey_login_to_logout import page as browser_page

pytestmark = pytest.mark.journey
page = browser_page


@pytest.fixture
def journey(tmp_path):
    with running(tmp_path) as (box, base):
        yield {"box": box, "base": base, "advocate": box.enrol(), "password": PASSWORD}


def _save(journey, key, title, message, *, advocate=None, parties=(), calculation=None):
    store = journey["box"].application.store
    context = open_turn(store, advocate_id=advocate or journey["advocate"], message=message, turn_id=key)
    context = hold_title(store, context, {"text": title, "from_matter": True})
    activities = {"contract": turn.UNANSWERED_CONTRACT}
    if parties or calculation:
        activities = {
            "contract": turn.CALCULATION_CONTRACT, "rendering_contract": response_rendering.AS_OF_CONTRACT,
            "interpretation": {}, "research": {"plan": {"proposal": {"understanding": {"parties": list(parties)}}}},
            "sources": {}, "draft": {}, "review": {}, "execution": {}, "authority_evidence": {},
            "calculation": calculation or {},
        }
    commit_turn(store, context, elements=[], activities=activities, session_current=lambda: True)
    return context.chat_id


def _history(page):
    _reach_rail(page, page.viewport_size["width"])
    return page.locator("#rail-body")


def _open(page, chat_id, title):
    from playwright.sync_api import expect

    _history(page).locator(f'[data-chat-id="{chat_id}"]').click()
    expect(page.locator(".thread-title")).to_have_text(title, timeout=15000)


def test_search_pages_only_matching_conversations_of_this_advocate(page, journey):
    from playwright.sync_api import expect

    matching = {
        _save(journey, f"lease-{number}", f"Harbour premises {number}", "Papers about the tenancy.")
        for number in range(11)
    }
    unrelated = _save(journey, "unrelated", "Unrelated contract", "Papers about a supply agreement.")
    other = journey["box"].enrol("adv_other_history")
    _save(journey, "other-lease", "Harbour premises another advocate", "Papers about the tenancy.", advocate=other)
    _sign_in(page, journey)
    history = _history(page)
    search = page.get_by_role("searchbox", name="Search your conversations")
    search.fill("HARBOUR tenancy")
    search.press("Enter")

    expect(page.locator("#rail-meta")).to_contain_text("11 conversations found")
    rows = history.locator("[data-chat-id]")
    expect(rows).to_have_count(10)
    expect(rows.first).to_contain_text("title")
    expect(rows.first).to_contain_text("your messages")
    history.get_by_role("button", name="Load more", exact=True).click()
    expect(rows).to_have_count(11)
    assert set(rows.evaluate_all("rows => rows.map(row => row.dataset.chatId)")) == matching

    search.fill("")
    expect(page.locator("#rail-meta")).to_contain_text("12 conversations")
    expect(history.locator(f'[data-chat-id="{unrelated}"]')).to_be_visible()
    assert not page.errors


def test_a_name_survives_reload_and_can_be_cleared(page, journey):
    from playwright.sync_api import expect

    chat_id = _save(journey, "rename", "Lease discussion", "The lease is in the file.")
    _sign_in(page, journey)
    _open(page, chat_id, "Lease discussion")
    heading = page.locator(".thread-title")
    dialog = page.locator("#rename-chat-dialog")
    rename = page.get_by_role("button", name="Rename this conversation")
    rename.click()
    dialog.get_by_label("Name", exact=True).fill("Lease renewal for review")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden()
    expect(heading).to_have_text("Lease renewal for review")

    page.reload()
    expect(heading).to_have_text("Lease renewal for review", timeout=15000)
    _open(page, chat_id, "Lease renewal for review")
    rename.click()
    dialog.get_by_label("Name", exact=True).fill("")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden()
    expect(heading).to_have_text("Lease discussion")
    assert not page.errors


def test_a_proposed_particular_is_saved_only_after_save(page, journey):
    from playwright.sync_api import expect

    client = "Asha Rao"
    chat_id = _save(journey, "particulars", "Consumer complaint", "We act for Asha Rao.",
                    parties=[{"who": client, "role": "buyer", "client": True}])
    _sign_in(page, journey)
    _open(page, chat_id, "Consumer complaint")
    button = page.get_by_role("button", name="This conversation's particulars")
    dialog = page.locator("#particulars-dialog")
    client_field = dialog.get_by_label("Client", exact=True)
    court = dialog.get_by_label("Court", exact=True)
    offered = dialog.get_by_role("button", name=f"Fill the box with {client} (NM took this party as your client)")
    button.click()
    expect(client_field).to_be_enabled()
    expect(client_field).to_have_value("")
    offered.click()
    expect(client_field).to_have_value(client)
    dialog.get_by_role("button", name="Cancel").click()

    button.click()
    expect(client_field).to_be_enabled()
    expect(client_field).to_have_value("")
    offered.click()
    court.fill("City Civil Court, Mumbai")
    dialog.get_by_label("Case number", exact=True).fill("44 of 2026")
    dialog.get_by_label("Next date", exact=True).fill("2027-01-13")
    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden()

    page.reload()
    expect(page.locator(".thread-title")).to_have_text("Consumer complaint", timeout=15000)
    button.click()
    expect(client_field).to_have_value(client)
    expect(court).to_have_value("City Civil Court, Mumbai")
    expect(dialog.get_by_label("Case number", exact=True)).to_have_value("44 of 2026")
    expect(dialog.get_by_label("Next date", exact=True)).to_have_value("2027-01-13")
    dialog.get_by_role("button", name="Cancel").click()
    row = _history(page).locator(f'[data-chat-id="{chat_id}"]')
    expect(row).to_contain_text(client)
    expect(row).to_contain_text("44 of 2026")
    assert not page.errors


def _limit(what, last_day):
    return {"id": what, "what": what, "provision_name": "Article 54", "provision": {"act": "The Limitation Act, 1963"},
            "working": {"last_day": last_day.isoformat()}, "standing": {"state": "open", "days": 0}, "done": None}


def _calculation(today, *limits, not_assessed=()):
    return {"contract": "core_calculation_v9", "state": "worked", "today": today.isoformat(),
            "calculations": list(limits), "not_assessed": list(not_assessed)}


def test_the_time_limits_diary_opens_the_selected_saved_conversation(page, journey, monkeypatch):
    from playwright.sync_api import expect

    today = date(2026, 11, 25)
    monkeypatch.setattr("nm.app.api.forum_today", lambda: today)
    where = _save(journey, "diary-lease", "Lease dispute", "The lease dispute is here.", calculation=_calculation(
        today, _limit("File the suit", today + timedelta(days=9)),
        not_assessed=[{"what": "Appeal period", "why": "The decree date is missing."}],
    ))
    _save(journey, "diary-reply", "Reply to the notice", "The notice is here.", calculation=_calculation(
        today, _limit("Reply to the notice", today + timedelta(days=1)), _limit("Earlier notice", today - timedelta(days=1)),
    ))
    other = journey["box"].enrol("adv_other_diary")
    _save(journey, "diary-other", "Another advocate's matter", "Different owner.", advocate=other,
          calculation=_calculation(today, _limit("Different advocate's limit", today + timedelta(days=1))))

    _sign_in(page, journey)
    _history(page)
    page.get_by_role("button", name="Time limits", exact=True).click()
    diary = page.get_by_role("dialog", name="Time limits", exact=True)
    expect(diary).to_contain_text("It is not a court diary")
    expect(diary.locator("h3")).to_have_text(["Still to come", "Passed", "Not worked out"])
    expect(diary.locator("ul").first.locator(".time-limit-what")).to_have_text([
        "Reply to the notice — Article 54, The Limitation Act, 1963",
        "File the suit — Article 54, The Limitation Act, 1963",
    ])
    expect(diary).to_contain_text("The decree date is missing.")
    expect(diary).not_to_contain_text("Different advocate's limit")
    diary.locator("li").filter(has_text="File the suit").get_by_role(
        "button", name="Open conversation: Lease dispute", exact=True,
    ).click()
    expect(diary).to_be_hidden()
    expect(page.locator(".thread-title")).to_have_text("Lease dispute")
    expect(page.locator("#thread")).to_contain_text("The lease dispute is here.")
    assert page.url.endswith(f"#chat={where}")
    assert not page.errors
