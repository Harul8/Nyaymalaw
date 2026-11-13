"""The trusted-origin rule is written once (plan AN.53, 53j3; D225; the review's F-41).

Which origins may make a credentialled request was worked out in two places - for an HTTP request, and again, word for word,
for the dictation socket. Two copies of a rule about who may act as the advocate drift apart at the first change to one of
them. Both now ask one function. No browser; the functions themselves are called.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from nm.app import api

pytestmark = pytest.mark.class_a
SETTING = "NM_TRUSTED_ORIGINS"


def _request(origin, own="http://nm.example.test/"):
    return SimpleNamespace(headers={"origin": origin} if origin else {}, base_url=own)


def _socket(origin, scheme="wss", netloc="nm.example.test"):
    return SimpleNamespace(headers={"origin": origin, "user-agent": "test"}, cookies={"nm_session": "s", "nm_device": "d"},
                           url=SimpleNamespace(scheme=scheme, netloc=netloc))


@pytest.fixture
def signed_in_socket(monkeypatch):
    """A directory in which the socket's cookies are a signed-in advocate's."""
    directory = SimpleNamespace(session=lambda *_: SimpleNamespace(advocate_id="adv_socket"), identity=lambda _id: object())
    monkeypatch.setattr(api, "application", lambda: SimpleNamespace(directory=directory))


def test_with_nothing_set_the_only_trusted_origin_is_the_servers_own(monkeypatch):
    monkeypatch.delenv(SETTING, raising=False)
    assert api._trusted_origins("http://nm.example.test") == {"http://nm.example.test"}


def test_the_setting_names_the_trusted_origins_and_replaces_the_servers_own(monkeypatch):
    monkeypatch.setenv(SETTING, " https://a.example.test/ , https://b.example.test,, ")
    assert api._trusted_origins("http://nm.example.test") == {"https://a.example.test", "https://b.example.test"}


@pytest.mark.parametrize("configured, origin, accepted", [
    (None, "http://nm.example.test", True),
    (None, "https://elsewhere.example.test", False),
    ("https://a.example.test", "https://a.example.test", True),
    ("https://a.example.test", "http://nm.example.test", False),
])
def test_a_request_and_a_socket_are_held_to_the_same_origins(monkeypatch, signed_in_socket, configured, origin, accepted):
    if configured is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, configured)
    if accepted:
        api._require_origin(_request(origin))
    else:
        with pytest.raises(HTTPException) as refused:
            api._require_origin(_request(origin))
        assert refused.value.status_code == 403
    socket = _socket(origin, scheme="ws")   # ws: the socket's own page is http://nm.example.test
    assert api._socket_advocate(socket) == ("adv_socket" if accepted else None)


def test_both_ask_the_one_function(monkeypatch, signed_in_socket):
    asked = []
    monkeypatch.setattr(api, "_trusted_origins", lambda own: (asked.append(own), {"https://only.example.test"})[1])
    api._require_origin(_request("https://only.example.test"))
    assert api._socket_advocate(_socket("https://only.example.test")) == "adv_socket"
    assert [own.rstrip("/") for own in asked] == ["http://nm.example.test", "https://nm.example.test"], "each gives its own origin"
    assert api._socket_advocate(_socket("https://nm.example.test")) is None, "the one function's answer decides"
