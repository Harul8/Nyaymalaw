"""The public site's top bar stays at the top as the page scrolls, the person control the website's script draws
for a visitor who is signed in is styled, and each of the seven pages carries the bar, the account bar the script
works on and the two scripts (owner decision O28; plan AN.22). Reads the shipped style sheet, script and pages;
the owner's browser shows how it looks."""
from __future__ import annotations

import re

import pytest

from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

CSS = re.sub(r"/\*.*?\*/", " ", browser_assets()["site.css"].read_text(encoding="utf-8"), flags=re.S)
SCRIPT = browser_assets()["site.js"].read_text(encoding="utf-8")
#: The sheet without its media queries, which only refine a rule at another width.
TOP_LEVEL = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", " ", CSS)


def rule(selector: str) -> str:
    """What the one top-level rule for exactly this selector declares, without spaces."""
    found = re.findall(r"(?:^|[{}])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}", TOP_LEVEL)
    assert len(found) == 1, f"{selector}: {len(found)} rules"
    return found[0].replace(" ", "")


def pixels(declarations: str, name: str) -> int:
    return int(re.search(r"(?:^|;)" + name + r":(\d+)px", declarations).group(1))


def test_the_bar_stays_at_the_top_with_a_colour_of_its_own():
    bar = rule(".topbar")
    assert "position:sticky" in bar and "top:0" in bar
    assert int(re.search(r"z-index:(\d+)", bar).group(1)) >= 50
    # Without a colour of its own, what scrolls beneath a frozen bar shows through it.
    assert "background:var(--paper)" in bar


def test_the_pages_anchors_stop_below_the_bar():
    """The tallest thing in the bar, its padding and its rule: an anchored heading must land clear of them."""
    bar = rule(".topbar .nav")
    padding = int(re.search(r"padding-top:(\d+)px", bar).group(1))
    assert padding == int(re.search(r"padding-bottom:(\d+)px", bar).group(1))
    tallest = pixels(rule(".btn"), "min-height")
    assert pixels(rule("html"), "scroll-padding-top") >= tallest + 2 * padding + 1


def test_the_bar_sets_its_height_and_leaves_its_sides_to_the_page():
    """The padding shorthand would also set the sides, which on a phone are the page's 24px: found in a real
    browser, where it left the logo and the person control touching the screen's edges."""
    bar = rule(".topbar .nav")
    assert not re.search(r"(?:^|;)padding:", bar), bar
    assert "padding-left" not in bar and "padding-right" not in bar and "padding-inline" not in bar


def test_the_hidden_attribute_wins_over_a_layout_rule():
    """The script shows and hides by the hidden attribute; a layout rule must not beat it."""
    assert re.search(r"\[hidden\]\{display:none !important\}", CSS)


def test_every_class_the_script_builds_has_a_rule():
    built: set[str] = set()
    for classes in re.findall(r"make\('\w+', '([^']+)'", SCRIPT) + re.findall(r"setAttribute\('class', '([^']+)'\)", SCRIPT):
        built.update(classes.split())
    assert {"acct", "acct-toggle", "acct-avatar", "acct-name", "acct-panel", "acct-signout"} <= built, built
    declared = set(re.findall(r"\.([A-Za-z][\w-]*)", CSS))
    assert not sorted(built - declared), f"the script builds classes the sheet never styles: {sorted(built - declared)}"


def test_the_circle_is_drawn_only_when_it_has_letters_or_the_server_is_still_being_asked():
    assert rule(".acct-avatar:empty") == "display:none"
    waiting = rule('#account[aria-busy="true"] .acct-avatar')
    assert "display:inline-flex" in waiting, "while waiting, the control holds its room"
    assert "display:inline-flex" in rule(".acct-avatar") and "border-radius:50%" in rule(".acct-avatar")


def test_the_name_gives_way_on_a_phone_and_the_initials_stay():
    phone = re.search(r"@media \(max-width:820px\)\{(.*?)\}\}", CSS).group(1)
    assert ".acct-name" in phone and "display:none" in phone
    assert ".acct-avatar" not in phone, "a phone rule hides or resizes the initials"


def test_the_menu_hangs_from_the_control_and_never_runs_off_a_phone():
    panel = rule(".acct-panel")
    assert "position:absolute" in panel and "right:0" in panel
    assert "width:min(300px,calc(100vw-32px))" in panel
    assert "overflow" not in rule(".acct-toggle") + rule(".acct"), "the menu would be clipped by the control"
    assert rule(".acct") == "position:relative;flex:none"


PAGES = ("home.html", "how-it-works.html", "what-it-holds.html", "trust.html", "plans.html", "about.html",
         "legal.html")
#: What the page bodies' own buttons say today. For a visitor who is signed in the script turns the first kind
#: into "Open your workspace" and hides the second (owner decision O28); a button saying anything else is a new
#: decision, not something the script should guess at.
BODY_REGISTER_TEXTS = {"Create your account", "Choose Pro", "Choose Elite"}


def _page(name: str) -> str:
    return browser_assets()[name].read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PAGES)
def test_every_page_freezes_its_bar_and_holds_the_buttons_the_script_puts_back(name):
    page = _page(name)
    # The header is the whole of the frozen bar.
    assert len(re.findall(r'<div class="topbar">\s*<header class="wrap nav">', page)) == 1, name
    assert len(re.findall(r"</header>\s*</div>", page)) == 1, name
    # One account bar, inside it, holding the two buttons the script puts back for a visitor who is not signed in.
    assert page.count('id="account"') == 1, name
    assert page.index('<div class="topbar">') < page.index('id="account"') < page.index("</header>"), name
    bar = re.search(r'<div class="right" id="account">(.*?)</div>', page, re.S).group(1)
    assert re.findall(r'<a class="([^"]*)" href="([^"]*)">([^<]*)</a>', bar) == [
        ("signin", "/app", "Sign in"), ("btn primary", "/app#register", "Create account")], name


@pytest.mark.parametrize("name", PAGES)
def test_every_page_loads_the_shared_rule_before_the_script_that_uses_it_at_the_end(name):
    assert re.search(
        r'<script src="/static/person.js"></script>\s*<script src="/static/site.js"></script>\s*</body>',
        _page(name)), name


@pytest.mark.parametrize("name", PAGES)
def test_the_buttons_in_a_pages_body_are_the_ones_the_script_knows_how_to_change(name):
    body = _page(name).split("</header>", 1)[1]
    for text in re.findall(r'<a [^>]*href="/app#register"[^>]*>([^<]*)</a>', body):
        assert text in BODY_REGISTER_TEXTS, f"{name}: a button saying {text!r} opens registration"
    for text in re.findall(r'<a [^>]*href="/app"[^>]*>([^<]*)</a>', body):
        assert text == "Sign in", f"{name}: a link saying {text!r} opens the app"
