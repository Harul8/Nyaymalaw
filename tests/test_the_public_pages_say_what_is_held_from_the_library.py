"""The public pages say what NM holds, from the library's own records (plan AN.56, piece 56a; D258, the second review of 17 Nov 2026).

The home page and What it holds carry no typed figure and no placeholder: each figure's place is marked and says "Not available" as written,
and is filled when the page is served from the stores' lineage records and the Acts catalogue - the number of Acts, of judgments, the day
the library was last updated and the Acts themselves. Where the records cannot be read the page is served as written. Synthetic stores in
a temporary folder; the shipped pages read as files."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nm.app import held_pages
from nm.app.static_assets import BrowserAssetsRefused, browser_assets_router
from nm.arrive.admin_checks import AdminChecks
from nm.arrive.admin_library import AdminLibrary
from nm.shared.source_layout import browser_assets

pytestmark = pytest.mark.class_a

PLACES = ("acts", "judgments", "updated", "act-list")


@pytest.fixture
def places(tmp_path):
    (tmp_path / "matters").mkdir()
    (tmp_path / "law" / "acts").mkdir(parents=True)
    (tmp_path / "root" / ".nm" / "retrieval").mkdir(parents=True)
    return tmp_path


def recorded(places, *, acts=None, judgments=34037, corrected=(), swapped_in="2026-11-08T12:22:29+00:00"):
    retrieval = places / "root" / ".nm" / "retrieval"
    (retrieval / "bare_acts.lineage.json").write_text(json.dumps({
        "recorded_at": "2026-10-20T20:56:11+00:00", "passage_store": {"path": "acts/acts.db"},
        "corrected": [{"at": at, "plan": "AN.32"} for at in corrected]}), encoding="utf8")
    (retrieval / "judgments.lineage.json").write_text(json.dumps({
        "recorded_at": "2026-11-08T12:09:17+00:00", "swapped_in": swapped_in,
        "built_from": {"summary": {"judgments": judgments}}}), encoding="utf8")
    rows = acts if acts is not None else [
        {"act_id": "a1", "title": "The Zeta Act, 1990", "year": "1990", "standing": "in force", "kind": "act"},
        {"act_id": "a2", "title": "The Alpha & Beta Act, 1881", "year": "1881", "standing": None, "kind": "act"},
        {"act_id": "a3", "title": "The Alpha Rules, 1990", "year": "1990", "standing": "in force", "kind": "subordinate"},
        {"act_id": "a4", "title": "The Gamma Act, 2001", "year": "", "standing": "not in force according to India Code", "kind": "act"},
        {"act_id": "a5", "title": "The Alpha (Amendment) Act, 2002", "year": "2002", "standing": None, "kind": "amendment"}]
    (places / "law" / "acts" / "acts.json").write_text(json.dumps(rows), encoding="utf8")


def library_in(places):
    checks = AdminChecks(storage=places / "matters", root=places / "root", settings={}, corpus_dir=places / "law")
    return AdminLibrary(checks=checks, root=places / "root", corpus_dir=places / "law")


def test_the_library_says_how_many_acts_and_judgments_it_holds_and_when_it_was_last_updated(places):
    recorded(places, corrected=("2026-11-05T14:11:42+00:00", "2026-11-09T06:27:54+00:00"))
    held = library_in(places).held()
    # The Acts are the catalogue's Acts, not its rules or amending Acts, listed by title.
    assert held["acts"] == 3 and held["judgments"] == 34037
    assert held["act_list"] == (("The Alpha & Beta Act, 1881", "1881", ""), ("The Gamma Act, 2001", "", "not in force according to India Code"),
                                ("The Zeta Act, 1990", "1990", "in force"))
    # The latest of the Acts store's building and corrections and the judgment store's swap.
    assert held["updated"] == date(2026, 11, 9)
    retrieval = places / "root" / ".nm" / "retrieval"
    assert held["changed"] == max(path.stat().st_mtime for path in (retrieval / "bare_acts.lineage.json",
                                  retrieval / "judgments.lineage.json", places / "law" / "acts" / "acts.json"))


@pytest.mark.parametrize("damage", ["no acts record", "no judgments record", "no catalogue", "count not a number", "bad date"])
def test_where_the_records_cannot_be_read_nothing_is_said_to_be_held(places, damage):
    recorded(places, judgments="many" if damage == "count not a number" else 34037,
             swapped_in="yesterday" if damage == "bad date" else "2026-11-08T12:22:29+00:00")
    retrieval = places / "root" / ".nm" / "retrieval"
    if damage == "no acts record":
        (retrieval / "bare_acts.lineage.json").unlink()
    elif damage == "no judgments record":
        (retrieval / "judgments.lineage.json").unlink()
    elif damage == "no catalogue":
        (places / "law" / "acts" / "acts.json").write_text("not json", encoding="utf8")
    assert library_in(places).held() is None


PAGE = ('<p><span data-held="acts">Not available</span> Acts, <span data-held="judgments">Not available</span> judgments, '
        'updated <span data-held="updated">Not available</span>.</p><ul class="acts-list" data-held="act-list" aria-label="Acts">'
        '<li class="head"><span>Act</span><span>Year</span><span>Status</span></li><li><span>The list of Acts is not available just now.'
        '</span><span></span><span></span></li></ul>')
HELD = {"acts": 1393, "judgments": 990668, "updated": date(2026, 11, 9),
        "act_list": (("The <Alpha> & Beta Act", "1881", ""), ("The Zeta Act", "", "in force"))}


def test_a_page_is_filled_with_the_figures_written_the_indian_way_and_the_acts_escaped():
    page = held_pages.filled(PAGE, HELD)
    assert '<span data-held="acts">1,393</span>' in page and '<span data-held="judgments">9,90,668</span>' in page
    assert '<span data-held="updated">9 November 2026</span>' in page
    assert ('<li class="head"><span>Act</span><span>Year</span><span>Status</span></li>'
            '<li><span>The &lt;Alpha&gt; &amp; Beta Act</span><span>1881</span><span>Standing not recorded</span></li>'
            '<li><span>The Zeta Act</span><span>Year not recorded</span><span>In force</span></li></ul>') in page
    assert "not available" not in page.lower()
    assert [held_pages.indian(n) for n in (7, 999, 1000, 34037, 100000, 990668, 12345678)] == [
        "7", "999", "1,000", "34,037", "1,00,000", "9,90,668", "1,23,45,678"]


def test_where_nothing_is_known_to_be_held_the_page_is_served_as_written():
    assert held_pages.filled(PAGE, None) == PAGE


@pytest.mark.parametrize("name", ["home.html", "what-it-holds.html"])
def test_the_shipped_pages_mark_each_figure_and_type_none(name):
    page = browser_assets()[name].read_text(encoding="utf-8")
    marked = re.findall(r'data-held="([a-z-]+)"', page)
    assert marked == (["acts", "judgments", "updated", "act-list"] if name == "what-it-holds.html" else ["acts", "judgments", "updated"])
    assert not re.search(r"\[(?:N[N,]*|date|Act title|year|In force)\]", page), f"{name} still shows a placeholder"
    for place in re.findall(r'<span data-held="(?:acts|judgments|updated)">([^<]*)</span>', page):
        assert place == "Not available"
    # Filled from the records, no figure of the page is left as written.
    assert "Not available" not in held_pages.filled(page, HELD)


def _client(tmp_path, filled):
    product = tmp_path / "nm" / "app"
    product.mkdir(parents=True)
    (product / "index.html").write_text("<p>entry</p>", encoding="utf-8")
    (product / "home.html").write_text(PAGE * 4, encoding="utf-8")
    paths = {"index.html": product / "index.html", "home.html": product / "home.html"}
    app = FastAPI()
    app.include_router(browser_assets_router(asset_paths=lambda: paths, root=tmp_path, filled=filled))
    return TestClient(app)


def test_the_served_page_is_filled_at_each_request_compressed_where_asked_and_revalidated_by_its_own_bytes(tmp_path):
    state = {"held": HELD}
    with _client(tmp_path, {"home.html": lambda text: (held_pages.filled(text, state["held"]), state.get("changed"))}) as client:
        plain = client.get("/", headers={"accept-encoding": "identity"})
        assert plain.status_code == 200 and "1,393" in plain.text and plain.headers["content-type"].startswith("text/html")
        packed = client.get("/", headers={"accept-encoding": "gzip"})
        assert packed.headers["content-encoding"] == "gzip" and packed.headers["vary"] == "Accept-Encoding"
        tag = plain.headers["etag"]
        assert client.get("/", headers={"accept-encoding": "identity", "if-none-match": tag}).status_code == 304
        dated = plain.headers["last-modified"]
        assert client.get("/", headers={"accept-encoding": "identity", "if-modified-since": dated}).status_code == 304
        # Records written after the page was sent make a newer page by date too.
        state["changed"] = 4_102_444_800.0
        assert client.get("/", headers={"accept-encoding": "identity", "if-modified-since": dated}).status_code == 200
        # The records change, the page follows them at once, and the old validator no longer matches.
        state["held"] = None
        again = client.get("/", headers={"accept-encoding": "identity", "if-none-match": tag})
        assert again.status_code == 200 and "1,393" not in again.text and "Not available" in again.text
        # The test client opens what was compressed: the same page.
        assert packed.text == plain.text


def test_only_a_page_is_filled(tmp_path):
    with pytest.raises(BrowserAssetsRefused):
        browser_assets_router(asset_paths=dict, root=tmp_path, filled={"app.js": lambda text: (text, None)})
