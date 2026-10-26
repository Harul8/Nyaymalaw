"""The public site at nyaymalaw.in is static, local and honest (owner decisions P52, O19, O21, O23, O28; plans
AN.16, AN.22).

Each public page is a declared browser asset. It reads no matter: the only scripts it loads are two files from
this server, the app's shared initials rule and the site's own, which asks only who is signed in, and it writes
none of its own; it loads nothing from any other host, the fonts included; its links go only to the site's own
addresses and the app; and it keeps what the owner left blank blank, with usage spoken of as a trial
allowance, never in cents (O21). This reads the shipped files; the owner's browser shows the pages.
"""
from __future__ import annotations

import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

PAGES = ("home.html", "how-it-works.html", "what-it-holds.html", "trust.html", "plans.html", "about.html",
         "legal.html")
#: The addresses a public page may link to: the site's own pages, the app, and places on the same page.
ADDRESSES = {"/", "/how-it-works", "/what-it-holds", "/trust", "/plans", "/about", "/legal", "/app",
             "/app#register", "/static/site.css", "/static/fonts.css"}


#: The only scripts a public page may load, in this order, as files from this server: the shared initials rule
#: and the site's own (owner decision O28; plan AN.22).
SCRIPTS = ["/static/person.js", "/static/site.js"]


def _page(name: str) -> str:
    return browser_assets()[name].read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PAGES)
def test_a_public_page_runs_only_its_two_scripts_and_loads_nothing_from_another_host(name):
    page = _page(name)
    assert re.findall(r"<script\b[^>]*>", page, re.I) == [f'<script src="{src}">' for src in SCRIPTS], \
        f"{name} loads a script it is not allowed"
    assert re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.I | re.S) == ["", ""], f"{name} writes a script"
    assert not re.search(r"\son\w+\s*=", page, re.I), f"{name} has an inline event handler"
    assert "javascript:" not in page.lower(), f"{name} has a script address"
    assert not re.search(r"\b(?:src|href)\s*=\s*\"(?:https?:)?//", page), f"{name} loads or links another host"
    assert "fonts.googleapis" not in page and "@import" not in page, f"{name} asks a font service"
    assert '<html lang="en">' in page and "<title>" in page and 'name="viewport"' in page


@pytest.mark.parametrize("name", PAGES)
def test_a_public_page_links_only_to_the_site_and_the_app(name):
    for link in re.findall(r'\bhref="([^"]*)"', _page(name)):
        assert link in ADDRESSES or link.startswith("#"), f"{name} links to {link}"


@pytest.mark.parametrize("name", PAGES)
def test_a_public_page_keeps_the_blanks_blank_and_speaks_of_usage_as_the_owner_decided(name):
    text = re.sub(r"<[^>]+>", " ", _page(name))
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), f"{name} names an email address the owner left blank"
    assert "cents" not in text, f"{name} speaks of usage in cents (O21: a trial allowance, a percentage left)"


def test_the_public_style_sheet_names_its_fonts_and_fetches_none():
    css = browser_assets()["site.css"].read_text(encoding="utf-8")
    assert "Source Serif 4" in css and "Georgia" in css, "the serif and its stand-in are no longer named"
    # The faces are declared once, in fonts.css, from this server (plan AN.18); the site's own sheet
    # fetches nothing.
    assert "url(" not in css and "@import" not in css and "@font-face" not in css, "the site fetches a font"


@pytest.mark.parametrize("name", PAGES)
def test_a_public_page_loads_the_design_fonts_from_this_server_first(name):
    sheets = re.findall(r'<link rel="stylesheet" href="([^"]+)">', _page(name))
    assert sheets == ["/static/fonts.css", "/static/site.css"], f"{name} loads {sheets}"
