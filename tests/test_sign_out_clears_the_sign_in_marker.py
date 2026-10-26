"""Signing out clears the readable sign-in marker as well as the session (plan AN.22).

`nm_csrf` is the one sign-in cookie a page can read. The website's pages read it to know, before any
answer from the server, that someone may be signed in; left behind after a sign-out it would say so about
a visitor who has signed out. Through the real HTTP edge with the served fixture.
"""
from __future__ import annotations

import pytest

from tests.test_core_served import served  # noqa: F401 -- the fixture

pytestmark = pytest.mark.class_a


def cleared(response, name):
    return [header for header in response.headers.get_list("set-cookie") if header.startswith(f"{name}=")]


def test_signing_out_clears_the_session_and_the_readable_marker_together(served):
    assert served.client.cookies.get("nm_csrf"), "a sign-in leaves the marker (the premise of this test)"
    out = served.client.post("/api/logout")
    assert out.status_code == 200 and out.json()["signed_out"] is True
    for name in ("nm_session", "nm_csrf"):
        header, = cleared(out, name)
        assert "Max-Age=0" in header and "Path=/" in header, header
    assert served.client.cookies.get("nm_csrf") is None
    assert served.client.get("/api/session").status_code == 401


def test_an_unconfirmed_sign_out_leaves_both_alone(served):
    """A request the server refused (no CSRF header) ended nothing, so nothing is cleared."""
    refused = served.client.post("/api/logout", headers={"x-nm-csrf": ""})
    assert refused.status_code == 403
    assert cleared(refused, "nm_csrf") == [] and cleared(refused, "nm_session") == []
    assert served.client.get("/api/session").status_code == 200
