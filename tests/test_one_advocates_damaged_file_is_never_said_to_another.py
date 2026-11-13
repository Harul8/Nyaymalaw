"""One advocate's damaged file is never said to another (plan AN.53, 53b2, D217; the review's F-21).

The history looked at every saved file for whoever asked, and one that could not be opened - whoever's it was - was
named to every advocate and marked every advocate's history as partial. The history now asks the store for the
advocate's own files (53b1): another's file is not opened and no line of it is read; a file that cannot be opened is
said only to the advocate it is recorded as belonging to; and one nobody is recorded as owning is said to no advocate
and written to the server's log. Offline: the served app with stand-in models; no browser.
"""
from __future__ import annotations

import logging

import pytest

from nm.app import api
from tests.test_core_served import OTHER, OWNER, served, successful  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a


@pytest.fixture
def two(served):
    """Each of two advocates with one saved conversation: (served, the other's client, the owner's matter id)."""
    successful(served)
    other = served.login(OTHER)
    reply = other.post("/api/turn", json={"message": "Inspect this second account.", "turn_id": "turn-other"})
    assert reply.status_code == 200, reply.text
    (matter,) = served.store.list_for(OWNER).matters
    for client in (served.client, other):
        history = client.get("/api/work").json()
        assert history["state"] == "ok" and len(history["chats"]) == 1 and history["unavailable"] == []
    return served, other, matter.id


def _damage(served, matter_id):
    (served.store._matters / f"{matter_id}.nm").write_bytes(b"not a saved matter, and longer than the file was")


def test_the_others_history_is_whole_and_names_nothing_when_the_owners_file_is_damaged(two):
    served, other, matter_id = two
    _damage(served, matter_id)
    theirs = other.get("/api/work").json()
    assert theirs["state"] == "ok" and theirs["unavailable"] == [] and theirs["unreadable"] == []
    assert len(theirs["chats"]) == 1 and theirs["total"] == 1
    assert matter_id not in other.get("/api/work").text


def test_the_owner_is_still_told_which_of_their_own_cannot_be_read(two):
    served, _other, matter_id = two
    _damage(served, matter_id)
    own = served.client.get("/api/work").json()
    assert own["state"] == "partial" and own["unavailable"] == [matter_id] and own["chats"] == []


def test_a_damaged_file_nobody_is_recorded_as_owning_is_said_to_no_advocate_and_is_in_the_log(two, caplog):
    served, other, _matter_id = two
    (served.store._matters / "m_of_nobody.nm").write_bytes(b"not a saved matter")
    with caplog.at_level(logging.WARNING, logger="nm.history"):
        for client in (served.client, other):
            history = client.get("/api/work").json()
            assert history["state"] == "ok" and history["unavailable"] == [] and len(history["chats"]) == 1
            assert "m_of_nobody" not in client.get("/api/work").text
    assert any("could not be read" in record.getMessage() for record in caplog.records), "the operator is told"
    assert served.store.unowned_unreadable() == ("m_of_nobody",)


def test_the_history_of_one_opens_nothing_and_reads_no_line_of_anothers(two, monkeypatch):
    served, other, matter_id = two
    api._LISTED.clear()
    asked = []
    for name in ("load", "kept_line", "keep_line", "signature"):
        real = getattr(served.store, name)
        monkeypatch.setattr(served.store, name,
                            lambda mid, *rest, _real=real, _name=name: (asked.append((_name, str(mid))), _real(mid, *rest))[1])
    assert len(other.get("/api/work").json()["chats"]) == 1
    assert asked, "the other advocate's own file was looked at"
    assert matter_id not in {mid for _name, mid in asked}, "and the owner's was not: not opened, no line read"


def test_the_earlier_matter_address_gives_another_nothing_of_a_damaged_file(two):
    served, other, matter_id = two
    assert other.get(f"/api/matters/{matter_id}").status_code == 404
    _damage(served, matter_id)
    assert other.get(f"/api/matters/{matter_id}").status_code == 404, "not a server error that says it is there and damaged"
