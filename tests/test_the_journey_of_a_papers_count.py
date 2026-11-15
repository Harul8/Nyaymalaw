"""In a real browser: a paper attached when the advocate keeps nine in ten of the most says so on its line (plan AN.53, 53h5b).

Chromium against the served application, signed in through the page's own form; the paper is attached through the page's own
file input. Only how many papers the advocate's space holds is stood in for, in the server (its names, which are all the count
reads): sending 1,849 real papers to reach it is not what this checks. Needs a browser (the `journey` extra).
"""
from __future__ import annotations

import pytest

from tests.test_the_journey_login_to_logout import _sign_in
from tests.test_the_journey_login_to_logout import journey as _journey
from tests.test_the_journey_login_to_logout import page as _page

pytestmark = pytest.mark.journey
journey, page = _journey, _page


def _told_of_the_server(page):
    page.wait_for_function("!document.getElementById('health').textContent.trim().startsWith('Checking')", timeout=15000)


def test_a_paper_attached_from_nine_in_ten_says_how_many_are_kept_on_its_line(page, journey, tmp_path, monkeypatch):
    texts = journey["box"].application.documents.texts
    real = texts.names
    monkeypatch.setattr(texts, "names", lambda where: tuple(
        f"doc_{number:024x}-{'d' * 64}" for number in range(1_849)) + real(where))
    _sign_in(page, journey)
    _told_of_the_server(page)
    paper = tmp_path / "notice.txt"
    paper.write_text("The notice was served on 3 March 2026.", encoding="utf-8")
    page.set_input_files("#attach-files", str(paper))
    line = page.locator("#attachments .attachment-status").first
    line.wait_for(timeout=15000)
    page.wait_for_function("document.querySelector('#attachments .attachment-status') && "
                           "!document.querySelector('#attachments .attachment-status').textContent.startsWith('Checking')",
                           timeout=15000)
    said = line.inner_text()
    assert "NM keeps 1,850 of your papers; it keeps at most 2,000 for one advocate." in said, said
    assert not page.errors


def test_below_it_the_line_says_nothing_of_the_count(page, journey, tmp_path):
    _sign_in(page, journey)
    _told_of_the_server(page)
    paper = tmp_path / "notice.txt"
    paper.write_text("The notice was served on 3 March 2026.", encoding="utf-8")
    page.set_input_files("#attach-files", str(paper))
    page.wait_for_function("document.querySelector('#attachments .attachment-status') && "
                           "!document.querySelector('#attachments .attachment-status').textContent.startsWith('Checking')",
                           timeout=15000)
    assert "NM keeps" not in page.locator("#attachments .attachment-status").first.inner_text()
    assert not page.errors
