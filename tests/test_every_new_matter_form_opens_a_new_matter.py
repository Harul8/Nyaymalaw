"""F-B-01: every Record and continue on a new matter's form opens a NEW matter.

Owner, 28 September 2026: *"when record and continue is clicked without filling
any details, it should still open a new matter without any details, instead a
blank form is going back to a latest previous matter chat directly."*

THE RULE: an opening's identity exists only so a retry after a LOST reply finds
the file the server may already hold. Once the server confirms the opening, the
identity is spent; a later form -- blank or not, same answers or not -- is a new
matter. The browser journey is `tests/test_opening_journey.py::
test_a_second_blank_opening_is_a_new_matter_not_the_last_one`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a

SCRIPT = (Path(__file__).resolve().parents[1] / "nm" / "app" / "app.js").read_text(encoding="utf8")


def _block(start: str, end: str) -> str:
    at = SCRIPT.index(start)
    return SCRIPT[at:SCRIPT.index(end, at)]


def test_a_confirmed_opening_spends_its_identity():
    submit = _block("$('intake').addEventListener('submit'", "\n});\n")
    confirmed = submit.index("opened.state !== 'intake_opened'")
    spent = submit.index("intent.opening = null;")
    shown = submit.index("await showThreadBoard(opened.matter_id")
    assert confirmed < spent < shown, (
        "the opening identity is kept after the server confirmed it, so the next "
        "form with the same answers reopens the earlier matter")


def test_a_new_form_keeps_only_an_unconfirmed_opening_identity():
    start = _block("function startMatter()", "\n}\n")
    assert ("if (activeIntent.opening && !activeIntent.opening.uncertain) "
            "activeIntent.opening = null;") in start


def _open(client, key: str) -> str:
    r = client.post("/api/matters/intake", json={"request_key": key, "title": "",
                                                 "parties": {}})
    assert r.status_code == 200, r.text
    return r.json()["matter_id"]


def test_two_blank_openings_are_two_matters_and_a_retry_is_the_same_one(client):
    first = _open(client, "turn_blank_one")
    second = _open(client, "turn_blank_two")
    assert first != second, "two blank openings were given one matter"
    assert _open(client, "turn_blank_one") == first, (
        "a retry of the same opening must find the file it already made")
    listed = {r["matter_id"]: r["matter"] for r in client.get("/api/matters").json()["matters"]}
    assert listed[first] == listed[second] == "New matter"
