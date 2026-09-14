"""Served browser evidence for missing search and operational-versus-legal dates.

The index is tiny, local and synthetic. These are UI truthfulness witnesses,
not an evaluation of the real corpus or legal-currentness assurance.
"""
from __future__ import annotations

import sqlite3

import pytest
from nm.adapters.search.authority import AuthorityIndexSearch

from tests.test_the_journey_login_to_logout import _sign_in, _tab
from tests.test_the_workspace_respects_its_current_context import journey as _base_journey
from tests.test_the_workspace_respects_its_current_context import page as _base_page

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page


def _search(page, query):
    _tab(page, "search")
    page.fill("#q", query)
    with page.expect_response(lambda r: "/api/search?" in r.url) as pending:
        page.locator("#search-form").get_by_role("button", name="Search", exact=True).click()
    result = pending.value.json()
    page.wait_for_function("!document.querySelector('#search-index').hidden")
    return result


def test_a_missing_index_is_not_presented_as_a_completed_search(
    page, journey, monkeypatch, tmp_path,
):
    missing = tmp_path / "not-published.db"
    monkeypatch.setattr(journey["box"].application, "search", AuthorityIndexSearch(missing))
    _sign_in(page, journey)
    result = _search(page, "synthetic limitation")
    assert result["coverage"] == "not_assessed" and result["hit_count"] == 0
    assert "Search not performed" in page.locator("#search-index").inner_text()
    assert "Searched the case law" not in page.locator("#search-index").inner_text()
    assert "NOT SEARCHED" in page.locator("#search-state").inner_text()
    assert "no relevant law exists" in page.locator("#search-state").inner_text()
    reason = page.locator(".search-diagnostic p")
    assert not reason.is_visible(), "operational detail must not dominate the primary message"
    page.get_by_text("Why the search did not run", exact=True).click()
    assert reason.is_visible() and reason.inner_text() == result["why"]
    assert str(missing) in reason.inner_text(), "retain the exact inspectable diagnostic"
    assert page.locator("#search-results .hit").count() == 0
    assert not page.errors and not page.external_assets


@pytest.mark.parametrize("held", [None, 0, 1])
def test_an_index_build_date_never_claims_legal_currency(
    page, journey, monkeypatch, tmp_path, held,
):
    index = tmp_path / "synthetic.db"
    with sqlite3.connect(index) as con:
        con.execute("create table identity (key text primary key, value text)")
        identity = {"built_at": "2026-09-01", "source": "synthetic",
                    "source_paragraphs": "1", "scope": "Synthetic test scope only"}
        if held is not None:
            identity["indexed_paragraphs"] = str(held)
        con.executemany("insert into identity values (?, ?)", identity.items())
        con.execute("create virtual table paras using fts5(case_id, case_name, "
                    "court, year, para_type, para_id, text)")
        if held == 1:
            con.execute("insert into paras values (?, ?, ?, ?, ?, ?, ?)",
                        ("synthetic", "Synthetic test case", "Synthetic court", "2000",
                         "ratio", "p1", "synthetic limitation"))
    monkeypatch.setattr(journey["box"].application, "search", AuthorityIndexSearch(index))
    _sign_in(page, journey)
    result = _search(page, "synthetic limitation")
    assert result["coverage"] == "answered" and result["identity"]["held"] == held
    assert result["hit_count"] == (1 if held == 1 else 0)
    label = page.locator("#search-index").inner_text()
    assert "Searched the case law" in label and "Synthetic test scope only" in label
    assert "index prepared 2026-09-01" in label
    assert "legal currency is not established by the index date" in label
    assert "current to" not in label and "null" not in label
    expected = "Indexed count not recorded" if held is None else f"{held} indexed paragraphs"
    assert expected in label
    assert page.locator("#search-results .hit").count() == result["hit_count"]
    assert not page.errors and not page.external_assets
