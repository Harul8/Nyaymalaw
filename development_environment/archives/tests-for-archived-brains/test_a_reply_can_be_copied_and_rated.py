"""A reply's rating is recorded, attributed, kept and never a change to the file.

Owner, 28 September 2026: *"at the end of every NM response at the left corner
put copy message icon and like/unlike icon (upon clicking this pop up thumbs up
icon and down icon) -- record the user feedback in the database"*.

THE RULES (LB-56, LB-83):
1. A rating of a released reply is saved with the reply, the rating, the
   signed-in advocate and the time, and a reopened matter carries it back.
2. Ratings are only ever ADDED: a change or a withdrawal is a new entry, the
   history stays, and the reply's rating is its latest entry.
3. Rating a reply does not change the matter, so its version does not move.
4. Only a released reply on the advocate's own matter can be rated; anything
   else is refused with nothing recorded.
5. A latest entry the store cannot read back is UNKNOWN, never "no rating".

The icons themselves are browser behaviour, checked by the owner in the browser.
"""
from __future__ import annotations

import pytest

from nm.app.api import application
from tests.test_a_turn_receipt_is_not_an_archival_trace import _opened

pytestmark = pytest.mark.class_a


def _rate(client, opened, rating, *, turn_id=None):
    turn = turn_id or opened["turn_id"]
    return client.post(f"/api/matters/{opened['matter_id']}/turns/{turn}/feedback",
                       json={"rating": rating})


def _shown(client, opened) -> str:
    view = client.get(f"/api/matters/{opened['matter_id']}/transcript")
    assert view.status_code == 200, view.text
    return next(row for row in view.json()["turns"]
                if row["turn_id"] == opened["turn_id"])["rating"]


def test_a_rating_is_saved_attributed_and_carried_back_to_the_reply(client):
    opened = _opened(client)
    assert _shown(client, opened) == "none", "an unrated reply must read as unrated"

    rated = _rate(client, opened, "down")
    assert rated.status_code == 201, rated.text
    assert rated.json()["rating"] == "down"
    assert _shown(client, opened) == "down"

    entries = application().store.feedback_for(opened["matter_id"])
    assert len(entries) == 1
    assert entries[0]["turn_id"] == opened["turn_id"]
    assert entries[0]["by"] == "adv_demo", "the rater must be the signed-in advocate"
    assert entries[0]["at"], "a rating must say when it was given"


def test_a_changed_mind_is_a_new_entry_and_the_latest_one_counts(client):
    opened = _opened(client)
    for rating in ("up", "down", "none"):
        assert _rate(client, opened, rating).json()["rating"] == rating
    assert _shown(client, opened) == "none"
    kept = [e["rating"] for e in application().store.feedback_for(opened["matter_id"])]
    assert kept == ["up", "down", "none"], "an earlier rating was overwritten or reordered"


def test_rating_a_reply_does_not_change_the_matter(client):
    opened = _opened(client)
    store = application().store
    before = store.load(opened["matter_id"])
    assert _rate(client, opened, "up").status_code == 201
    after = store.load(opened["matter_id"])
    assert after.version == before.version, "a rating moved the matter's version"
    assert after == before, "a rating changed the matter file"


def test_only_a_released_reply_on_your_own_matter_can_be_rated(client):
    opened = _opened(client)
    store = application().store

    unknown = _rate(client, opened, "up", turn_id="no-such-turn")
    assert unknown.status_code == 404, unknown.text

    stranger = client.sign_in("adv_other", fresh=True)
    theirs = stranger.post(f"/api/matters/{opened['matter_id']}/turns/"
                           f"{opened['turn_id']}/feedback", json={"rating": "down"})
    assert theirs.status_code == 404, theirs.text
    assert store.feedback_for(opened["matter_id"]) == (), "a refused rating was recorded"


def test_a_withheld_reply_cannot_be_rated(client):
    """The negative control: a withheld answer is not advice and has no footer."""
    from tests.test_a_brief_lands_exactly_once import BRIEF
    from tests.test_a_withheld_turn_commits_no_conclusion import _Ungrounded
    from tests.test_turn_contract import _model_config

    opened = _opened(client)
    application().engine._model = _Ungrounded(_model_config())
    refused = client.post("/api/turn", json={"message": BRIEF, "matter_id": opened["matter_id"],
                                             "turn_id": "withheld-not-rateable"})
    assert refused.status_code == 422, refused.text
    rated = _rate(client, opened, "up", turn_id="withheld-not-rateable")
    assert rated.status_code == 404, rated.text
    assert application().store.feedback_for(opened["matter_id"]) == ()


@pytest.mark.parametrize("body", [
    {"rating": "love"},
    {"rating": "up", "by": "someone_else"},
    {},
])
def test_the_rating_request_carries_a_rating_and_nothing_else(client, body):
    """Who rated comes from the session, never from the request."""
    opened = _opened(client)
    response = client.post(f"/api/matters/{opened['matter_id']}/turns/"
                           f"{opened['turn_id']}/feedback", json=body)
    assert response.status_code == 422, response.text
    assert application().store.feedback_for(opened["matter_id"]) == ()


def test_an_unreadable_latest_rating_is_unknown_never_none(client):
    opened = _opened(client)
    assert _rate(client, opened, "down").status_code == 201
    store = application().store.inner
    saved = next((store._feedback / opened["matter_id"] / opened["turn_id"]).glob("*.json"))
    saved.write_text("{not json", encoding="utf8")

    assert _shown(client, opened) == "unknown", "a lost thumbs-down read as no rating"
    entries = store.feedback_for(opened["matter_id"])
    assert entries[0]["unreadable"] is True and entries[0]["turn_id"] == opened["turn_id"]

    # Rating again adds a readable latest entry, and that is what counts.
    assert _rate(client, opened, "up").json()["rating"] == "up"
    assert _shown(client, opened) == "up"
