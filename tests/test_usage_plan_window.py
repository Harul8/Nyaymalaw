"""The Usage and plan window (owner decisions O21-O24 and O26; plans P53, AN.17, AN.19): what it holds,
that the plans in it are the public Plans page's, that no plan is offered that cannot be had, and that
usage is shown only as a percentage left. Reads the shipped page and the shipped public page; the
owner's browser shows how it looks."""
from __future__ import annotations

import html
import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

PAGE = browser_assets()["index.html"].read_text(encoding="utf-8")
PUBLIC = browser_assets()["plans.html"].read_text(encoding="utf-8")


def words(fragment: str) -> str:
    """What a person reads: no comments, no tags, entities decoded, spaces collapsed."""
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def window() -> str:
    start = PAGE.index('<dialog id="usage-plan-dialog"')
    return PAGE[start:PAGE.index("</dialog>", start) + len("</dialog>")]


def app_plans() -> dict[str, dict]:
    plans = {}
    for name, card in re.findall(r'<section class="plan-option" aria-label="([^"]+)">(.*?)</section>', window(), re.S):
        plans[name] = {
            "name": words(re.search(r"<h4>(.*?)</h4>", card, re.S).group(1)),
            "who": words(re.search(r'<p class="plan-who">(.*?)</p>', card, re.S).group(1)),
            "price": words(re.search(r'<p class="plan-price">(.*?)</p>', card, re.S).group(1)),
            "per": words(re.search(r'<p class="plan-per">(.*?)</p>', card, re.S).group(1)),
            "ticks": [words(li) for li in re.findall(r"<li>(.*?)</li>", card, re.S)],
        }
    return plans


def public_plans() -> dict[str, dict]:
    plans = {}
    for name, card in re.findall(r'<section class="plan[^"]*" aria-label="([^"]+)">(.*?)</section>', PUBLIC, re.S):
        plans[name] = {
            "name": words(re.search(r"<h3>(.*?)</h3>", card, re.S).group(1)),
            "who": words(re.search(r'<p class="per"[^>]*>(.*?)</p>', card, re.S).group(1)),
            "price": words(re.search(r'<p class="price">(.*?)</p>', card, re.S).group(1)),
            "per": words(re.search(r'<p class="price">.*?</p>\s*<p class="per">(.*?)</p>', card, re.S).group(1)),
            "ticks": [words(li) for li in re.findall(r"<li>(.*?)</li>", card, re.S)],
        }
    return plans


def test_the_window_holds_what_the_signed_off_page_draws():
    text = words(window())
    for piece in ("Usage and plan", "See what is left of your allowance, and choose a plan when you want more.",
                  "Trial allowance", "You are on the trial. Choose a plan below when you want more.",
                  "Your plan", "You have no plan yet. Choose one below when you want more usage.",
                  "No invoices yet", "Invoices appear here once you choose a plan.", "Choose a plan",
                  "All prices are per month and exclude GST."):
        assert piece in text, f"{piece!r} is missing from the Usage and plan window"
    # The three plans, in the order they are drawn.
    assert list(app_plans()) == ["Pro", "Elite", "Enterprise"]


def test_the_plans_in_the_app_are_the_plans_on_the_public_page():
    """One plan, one set of words: the name, who it is for, the price, and each line it promises. When
    the owner fills in the credits on one page the other must follow, or this fails."""
    assert app_plans() == public_plans()
    assert public_plans(), "the public page lost its plans, so this compares nothing"


def test_the_credits_stay_as_the_owner_left_them():
    ticks = [tick for plan in app_plans().values() for tick in plan["ticks"]]
    assert ticks.count("[XX] usage credits each month") == 2


def test_no_plan_is_offered_that_cannot_be_had():
    """Payment comes later, by UPI (owner, O24): until then Pro and Elite cannot be chosen and say so,
    in words a screen reader reads with the button. Enterprise is talked about, not bought."""
    page = window()
    for name in ("Pro", "Elite"):
        button = re.search(rf'<button[^>]*class="primary plan-choose"[^>]*>\s*Choose {name}\s*</button>', page)
        assert button, f"Choose {name} is missing"
        assert 'aria-disabled="true"' in button.group(0) and 'aria-describedby="usage-plan-payment"' in button.group(0)
    assert re.search(r'<p id="usage-plan-payment"[^>]*>Payment is not open yet', page)
    assert re.search(r'<a class="plan-link" href="/about"[^>]*>\s*Talk to us\s*</a>', page)
    assert "onclick" not in page.lower()


def test_usage_is_shown_only_as_a_percentage_left_never_as_cents_credits_or_dollars():
    """O21. The rupee figures are the plans' prices; the allowance itself has no unit but a percentage."""
    allowance = window()
    allowance = allowance[:allowance.index('<section class="usage-plan-choose"')]
    text = words(allowance)
    for forbidden in ("cent", "$", "₹", "credit", "dollar", "USD"):
        assert forbidden not in text, f"the allowance is shown with {forbidden!r}"


def test_the_window_can_be_opened_from_the_person_menu_and_its_fallbacks_still_reach_the_plans():
    assert re.search(r'<button id="usage-plan" type="button" class="ghost" aria-haspopup="dialog">Usage and plan</button>', PAGE)
    # Without the script the chip and the notice still reach the public Plans page.
    assert '<a id="usage-chip" class="usage" href="/plans"' in PAGE
    assert 'class="usage-notice-plans" href="/plans"' in PAGE


def test_every_part_the_script_fills_has_a_place_in_the_window():
    page = window()
    for name in ("usage-plan-close", "usage-plan-allowance", "usage-plan-left", "usage-plan-fill", "usage-plan-note",
                 "usage-plan-status", "usage-plan-name", "usage-plan-payment"):
        assert f'id="{name}"' in page, name
    assert 'aria-labelledby="usage-plan-title"' in page and 'id="usage-plan-title"' in page
