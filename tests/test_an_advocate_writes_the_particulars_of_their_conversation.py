"""An advocate writes the particulars of their own conversation, and NM proposes some from what it already understood (plan
AN.55, piece 55d2; D256, D332, D355).

The client, the court, the case number and the next date are the advocate's, each optional, written by their hand and shown
on the history row. NM proposes only from its last understanding of the matter as saved - the parties, the one it took as the
client first, and each proceeding it names with a number - with no model call, each through the same check the advocate's
own words pass, never one already kept, and never the court or the next date. A proposal is never written by itself. Only the
advocate's own conversation, only while NM is not working on it. Offline: the served application with scripted models, and
invented saved answers for the proposals.
"""
from __future__ import annotations

import pytest

from nm.app import api
from tests.served_application import OTHER, successful

pytestmark = pytest.mark.class_a


def answer(parties):
    return {"activities": {"research": {"plan": {"proposal": {"understanding": {"parties": parties}}}}}}


PARTIES = [
    {"who": "Greenfield Builders", "role": "builder", "parts": [{"proceeding": "Consumer complaint no. 41 of 2025"}]},
    {"who": "Asha  Rao", "role": "buyer", "client": True,
     "parts": [{"proceeding": "Consumer complaint no. 41 of 2025"}, {"proceeding": "the notice before suit"}]},
    {"who": "See https://example.test", "role": "a party whose words carry a link"},
]


def test_nm_proposes_the_client_first_then_the_other_parties_and_each_proceeding_named_with_a_number():
    proposed = api._proposed_particulars([answer([{"who": "An earlier party"}]), {"activities": {}}, answer(PARTIES),
                                          {"activities": {"research": {"plan": {"proposal": {"understanding": {
                                              "parties": []}}}}}}], {})
    assert proposed == {
        "client": [{"value": "Asha Rao", "said": "NM took this party as your client"},
                   {"value": "Greenfield Builders", "said": "A party in NM's understanding of the matter"}],
        "case_number": [{"value": "Consumer complaint no. 41 of 2025", "said": "A proceeding the papers name"}]}, (
        "the last understanding that names parties; a later answer naming none is passed over; a party whose words carry a "
        "link is never offered; a proceeding without a number is not a case number")
    kept = {"client": "Asha Rao", "case_number": "Consumer complaint no. 41 of 2025"}
    assert api._proposed_particulars([answer(PARTIES)], kept) == {
        "client": [{"value": "Greenfield Builders", "said": "A party in NM's understanding of the matter"}],
        "case_number": []}, "what is already kept is not proposed again"
    assert api._proposed_particulars([], {}) == {"client": [], "case_number": []}


def test_the_particulars_are_written_shown_on_the_history_and_read_back(served):
    chat_id = successful(served)["chat_id"]
    calls = len(served.model.calls)
    read = served.client.get(f"/api/chats/{chat_id}/particulars")
    assert read.status_code == 200 and read.json()["particulars"] == {}
    assert set(read.json()["proposed"]) == {"client", "case_number"}
    assert len(served.model.calls) == calls, "proposing makes no model call"
    reply = served.client.put(f"/api/chats/{chat_id}/particulars", json={
        "client": " Asha  Rao ", "court": "City Civil Court, Mumbai", "case_number": "", "next_date": "2026-12-04"})
    assert reply.status_code == 200, reply.text
    kept = {"client": "Asha Rao", "court": "City Civil Court, Mumbai", "next_date": "2026-12-04"}
    assert reply.json() == {"state": "saved", "chat_id": chat_id, "particulars": kept}
    assert served.client.get(f"/api/chats/{chat_id}/particulars").json()["particulars"] == kept
    line = next(chat for chat in served.client.get("/api/work").json()["chats"] if chat["chat_id"] == chat_id)
    assert line["particulars"] == kept
    emptied = served.client.put(f"/api/chats/{chat_id}/particulars", json={})
    assert emptied.json()["particulars"] == {}
    line = next(chat for chat in served.client.get("/api/work").json()["chats"] if chat["chat_id"] == chat_id)
    assert "particulars" not in line


def test_particulars_that_cannot_be_kept_are_refused_with_why_and_nothing_is_written(served):
    chat_id = successful(served)["chat_id"]
    for given, why in [({"next_date": "next Tuesday"}, "calendar date"), ({"client": "a" * 201}, "201 characters"),
                       ({"court": "https://example.test"}, "link")]:
        reply = served.client.put(f"/api/chats/{chat_id}/particulars", json=given)
        assert reply.status_code == 422 and why in reply.json()["detail"]["why"], reply.text
    assert served.client.put(f"/api/chats/{chat_id}/particulars", json={"judge": "x"}).status_code == 422
    assert served.client.get(f"/api/chats/{chat_id}/particulars").json()["particulars"] == {}


def test_only_the_advocate_s_own_and_not_while_nm_works_on_it(served, monkeypatch):
    chat_id = successful(served)["chat_id"]
    other = served.login(OTHER)
    assert other.get(f"/api/chats/{chat_id}/particulars").status_code == 404
    assert other.put(f"/api/chats/{chat_id}/particulars", json={"client": "Not theirs"}).status_code == 404
    monkeypatch.setattr(api, "_held", lambda matter: {"turn_id": "turn-at-work"})
    monkeypatch.setattr(served.app, "turn_running", lambda advocate_id, turn_id: turn_id == "turn-at-work")
    reply = served.client.put(f"/api/chats/{chat_id}/particulars", json={"client": "Asha Rao"})
    assert reply.status_code == 409 and "Change its particulars once NM has finished or stopped" in reply.json()["detail"]["why"]
    assert served.client.get(f"/api/chats/{chat_id}/particulars").json()["particulars"] == {}
