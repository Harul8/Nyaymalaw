"""The trust NM places in a proxy's address headers is NM's own setting, stated at start-up and pinned (plan AN.53,
53c3, D218; the review's F-28).

The sign-in limits count wrong answers by the visitor's address, and behind a proxy that address is what the proxy
writes in X-Forwarded-For. Which senders NM believes that header from was left to the web server library's
default: nothing in NM said it, and an upgrade could change it unseen. NM now names the trusted senders itself
(this machine, or the operator's FORWARDED_ALLOW_IPS), hands them to the web server explicitly, and says them at
start-up. These tests pin the address NM then counts by: with and without the headers, from a trusted sender and
from anyone else.
"""
from __future__ import annotations

import ast
import asyncio
import inspect

import pytest

from nm.app import main

pytestmark = pytest.mark.class_a

VISITOR, STRANGER = "203.0.113.9", "198.51.100.1"


def _address_seen(peer, headers, environment=None):
    """The visitor's address and scheme the app is given for a request from `peer` carrying `headers`, under NM's trust."""
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    trust = main.proxy_trust(environment or {})
    assert trust["proxy_headers"] is True
    seen = {}

    async def app(scope, receive, send):
        seen.update(client=scope["client"][0], scheme=scope["scheme"])

    wrapped = ProxyHeadersMiddleware(app, trusted_hosts=trust["forwarded_allow_ips"])
    scope = {"type": "http", "scheme": "http", "client": (peer, 5000), "server": ("127.0.0.1", 8000),
             "headers": [(name.encode(), value.encode()) for name, value in headers.items()]}
    asyncio.run(wrapped(scope, None, None))
    return seen["client"], seen["scheme"]


def test_by_default_only_this_machine_is_believed():
    assert main.proxy_trust({}) == {"proxy_headers": True, "forwarded_allow_ips": "127.0.0.1,::1"}
    assert main.proxy_trust({"FORWARDED_ALLOW_IPS": "  "}) == main.proxy_trust({})


def test_the_operators_setting_names_the_proxy_and_is_passed_as_given():
    assert main.proxy_trust({"FORWARDED_ALLOW_IPS": "10.0.0.5"})["forwarded_allow_ips"] == "10.0.0.5"


def test_a_proxy_on_this_machine_is_believed_about_the_visitor():
    forwarded = {"x-forwarded-for": VISITOR, "x-forwarded-proto": "https"}
    assert _address_seen("127.0.0.1", forwarded) == (VISITOR, "https")
    assert _address_seen("::1", forwarded) == (VISITOR, "https")


def test_without_the_headers_the_address_is_the_senders_own():
    assert _address_seen("127.0.0.1", {}) == ("127.0.0.1", "http")
    assert _address_seen(STRANGER, {}) == (STRANGER, "http")


def test_a_stranger_who_writes_the_headers_is_not_believed():
    forged = {"x-forwarded-for": VISITOR, "x-forwarded-proto": "https"}
    assert _address_seen(STRANGER, forged) == (STRANGER, "http"), "a forged address must not move the limit elsewhere"


def test_an_address_a_visitor_wrote_ahead_of_the_proxys_own_is_not_believed():
    assert _address_seen("127.0.0.1", {"x-forwarded-for": f"192.0.2.77, {VISITOR}"})[0] == VISITOR, (
        "the proxy appends the address it saw; what the visitor wrote before it is not the visitor's address")


def test_a_named_proxy_is_believed_and_this_machine_then_is_not():
    environment = {"FORWARDED_ALLOW_IPS": "10.0.0.5"}
    assert _address_seen("10.0.0.5", {"x-forwarded-for": VISITOR}, environment)[0] == VISITOR
    assert _address_seen("127.0.0.1", {"x-forwarded-for": VISITOR}, environment)[0] == "127.0.0.1"


def test_what_is_said_at_start_up_names_the_senders_and_warns_of_trusting_everyone():
    said = main.proxy_trust_said(main.proxy_trust({}))
    assert "127.0.0.1,::1" in said and "X-Forwarded-For" in said and "WARNING" not in said
    everyone = main.proxy_trust_said(main.proxy_trust({"FORWARDED_ALLOW_IPS": "*"}))
    assert "WARNING" in everyone and "any" in everyone.lower()


def test_the_web_server_is_started_with_nms_own_trust_and_it_is_said():
    """The launch itself: the one call that starts the web server is handed NM's trust, and the start says it."""
    source = inspect.getsource(main.main)
    runs = [node for node in ast.walk(ast.parse(source.lstrip() if source.startswith("def") else "if 1:\n" + source))
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "uvicorn.run"]
    assert len(runs) == 1
    assert any(keyword.arg is None and ast.unparse(keyword.value) == "trust" for keyword in runs[0].keywords), (
        "uvicorn.run is given **trust: the library's own default is not what decides")
    assert "trust = proxy_trust(os.environ)" in source and "proxy_trust_said(trust)" in source
