"""LB-76 in the browser: a composed reply is read as prose, and reads back the same.

A controlled journey: the model is scripted, the composer and its check are
scripted to behave as a careful composer and a strict reader would, and no paid
model is called. This checks presentation and read-back, not the quality of a
live model's writing.
"""
from __future__ import annotations

import pytest

from nm.shared.model_scripted import SCRIPTED_READS
from tests.test_the_journey_login_to_logout import _sign_in
from tests.test_the_reply_is_told_from_checked_findings import _composer, _judge, _told
from tests.test_the_workspace_respects_its_current_context import (
    _assert_no_overflow,
    _new_matter,
    _open_by_keyboard,
)
from tests.test_the_workspace_respects_its_current_context import journey as _base_journey
from tests.test_the_workspace_respects_its_current_context import page as _base_page

pytestmark = pytest.mark.journey
journey = _base_journey
page = _base_page


def _with_a_passage(work):
    rows = _told(work)
    cited = next((item for item in work if item.get("passage")), None)
    if cited is not None:
        rows.insert(1, {"text": f"The passage this rests on is {cited['passage']['source']}.",
                        "passage": cited["id"], "carries": ""})
    return rows


@pytest.mark.parametrize("width,height", [(390, 844), (1280, 900)])
def test_a_composed_reply_is_read_as_prose_and_reads_back_the_same(
        page, journey, monkeypatch, width, height):
    monkeypatch.setitem(SCRIPTED_READS, "compose", _composer(_with_a_passage))
    monkeypatch.setitem(SCRIPTED_READS, "compose_check", _judge)
    _sign_in(page, journey, width, height)
    with page.expect_response(lambda reply: reply.url.endswith("/api/turn")
                              and reply.request.method == "POST") as sent:
        matter_id = _new_matter(page, f"Synthetic prose client {width}", width)
    served = sent.value.json()
    assert served["composed"], "the controlled composer did not compose the reply"

    turn = page.locator("#thread .turn").last
    shown = [p.strip() for p in turn.locator(".el.reply > p.body").all_text_contents()]
    assert shown == [p["text"].strip() for p in served["composed"]], (
        "the paragraphs on screen are not the reply the server checked")
    assert turn.locator(".el:not(.reply)").count() == 0, (
        "the checked findings were stacked under the reply as well as told in it")
    assert turn.locator("details.support").count() == 0
    linked = [p for p in served["composed"] if p["passage"] is not None]
    assert turn.locator(".el.reply .refs .citation-link").count() == len(linked)
    _assert_no_overflow(page)

    page.reload()
    page.wait_for_selector("#masthead", state="visible")
    _open_by_keyboard(page, matter_id, width)
    again = page.locator("#thread .turn").last
    assert [p.strip() for p in again.locator(".el.reply > p.body").all_text_contents()] == shown, (
        "the reopened conversation does not show the reply that was served")
    assert not page.errors and not page.external_assets
