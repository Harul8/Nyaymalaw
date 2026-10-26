"""What the website's script relies on from the server (owner decision O28; plan AN.22), through the real HTTP edge.

The script reads one cookie, asks one route who is signed in and, when the visitor presses Sign out, calls one
route to end the session. These pin what it depends on: a sign-in leaves the readable marker and the answer
names the advocate in text; asking does not keep an idle session alive (a page left open on the site must not
hold a workspace open); a visitor with no session is refused, not shown a blank person; and the sign-out it
calls needs nothing the page cannot send.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

pytestmark = pytest.mark.class_a


def test_a_sign_in_leaves_the_marker_and_the_answer_names_the_advocate_in_text(client):
    assert client.cookies.get("nm_csrf"), "a sign-in leaves the readable marker the page looks for"
    answer = client.get("/api/session")
    assert answer.status_code == 200
    advocate = answer.json()["advocate"]
    assert isinstance(advocate, dict)
    shown = [advocate.get(key) for key in ("name", "email", "id")]
    assert all(value is None or isinstance(value, str) for value in shown), shown
    assert any(isinstance(value, str) and value.strip() for value in shown), "nothing for the control to show"


def test_asking_who_is_signed_in_does_not_keep_an_idle_session_alive(client, monkeypatch):
    from nm.app import api

    start = api.utcnow()
    clock = [start]
    monkeypatch.setattr(api, "utcnow", lambda: clock[0])
    first = client.get("/api/session").json()["access_window"]
    clock[0] = start + timedelta(minutes=20)
    again = client.get("/api/session")
    assert again.status_code == 200
    assert again.json()["access_window"]["valid_until"] == first["valid_until"], "the look moved the idle expiry"
    clock[0] = start + timedelta(minutes=31)
    assert client.get("/api/session").status_code == 401, "a session looked at 20 minutes in outlived its idle window"


def test_the_idle_expiry_does_move_when_the_visitor_is_active(client, monkeypatch):
    """The positive control for the test above: the expiry it watches is one that can move."""
    from nm.app import api

    start = api.utcnow()
    clock = [start]
    monkeypatch.setattr(api, "utcnow", lambda: clock[0])
    first = client.get("/api/session").json()["access_window"]
    clock[0] = start + timedelta(minutes=20)
    assert client.post("/api/session/activity").status_code == 200
    assert client.get("/api/session").json()["access_window"]["valid_until"] != first["valid_until"]


def test_a_visitor_with_no_session_is_refused_and_not_shown_a_blank_person(client):
    client.cookies.clear()
    answer = client.get("/api/session")
    assert answer.status_code == 401
    assert "advocate" not in answer.json()


def test_the_sign_out_the_page_calls_needs_only_the_cookie_the_page_can_read(client):
    """The script sends no body, only the value of nm_csrf as X-NM-CSRF, and reloads when the answer is a yes."""
    marker = client.cookies.get("nm_csrf")
    refused = client.post("/api/logout", headers={"x-nm-csrf": ""})
    assert refused.status_code == 403, "the server must not sign out a request that cannot show the marker"
    assert client.get("/api/session").status_code == 200
    done = client.post("/api/logout", headers={"x-nm-csrf": marker})
    assert done.status_code == 200 and done.json()["signed_out"] is True
    assert client.get("/api/session").status_code == 401
