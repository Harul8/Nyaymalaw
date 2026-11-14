"""No route gives one advocate another's work, or a visitor anyone's (plan AN.54, piece 54c; D228; the review's missing test).

The existing cross-account test asks two addresses it names. This one is built from the app's own route table, as the
cross-site and Admin tests are, so a route added later is covered the day it is added: every API route is asked by a visitor
who is not signed in, and every route that takes an identifier is asked by a second signed-in advocate holding the first
advocate's real identifiers. Neither is ever answered with success, a server error, or a word of the first advocate's work.
A route with a kind of identifier this file does not know fails it, until the identifier is given a value here. Offline: the
served app with stand-in models; no browser.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from nm.app import api
from tests.test_core_served import OTHER, OWNER, served, successful  # noqa: F401 - served is a fixture

pytestmark = pytest.mark.class_a

#: API routes that answer a visitor who is not signed in, each for its reason. Everything else must refuse one.
PUBLIC = {
    "/api/health": "says the server is up",
    "/api/login": "is how a visitor signs in",
    "/api/logout": "ends whatever sign-in the browser holds",
    "/api/account-capabilities": "tells the sign-in page what it may offer",
}
WORDS_OF_THE_OWNER = ("Inspect this reported account", "Counsel")


def api_routes():
    """Every HTTP route under /api, from the app's own table, routers inside routers included: (method, path)."""
    found = []

    def walk(routes, before=""):
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(inner.routes, before + (getattr(route, "prefix", "") or ""))
            elif getattr(route, "methods", None) and hasattr(route, "path"):
                found.extend((method, before + route.path) for method in route.methods if method not in ("HEAD", "OPTIONS"))
    walk(api.app.routes)
    return sorted({pair for pair in found if pair[1].startswith("/api/")})


def filled(path, values):
    """The path with each identifier given its value; fails on an identifier this file has no value for."""
    def value(match):
        name = match.group(1).split(":")[0]
        assert name in values, f"{path} takes '{name}', a kind of identifier this test does not know: give it a value here"
        return str(values[name])
    return re.sub(r"\{([^}]+)\}", value, path)


def ask(client, method, address):
    return client.request(method, address, json={} if method in ("POST", "PUT", "PATCH") else None)


@pytest.fixture
def owned(served):
    """The first advocate's saved conversation, and its real identifiers."""
    reply = successful(served)
    matter = served.store.list_for(OWNER).matters[0]
    return {"chat_id": reply["chat_id"], "turn_id": reply["turn_id"], "matter_id": matter.id, "element": 0, "source": 0,
            "tag": "S1", "document_ref": "doc-of-the-owner", "account_id": OWNER, "batch_id": "batch-1",
            "ref": matter.id}  # plan AN.53 (D241): a deleted conversation's reference, the owner's own


def test_the_route_table_is_read_and_holds_the_routes_this_test_is_for():
    routes = api_routes()
    assert len(routes) > 40 and ("GET", "/api/chats/{chat_id}") in routes and ("POST", "/api/turn") in routes
    assert any(path.startswith("/api/admin/") for _, path in routes), "the Admin router's routes are read too"
    assert set(PUBLIC) <= {path for _, path in routes}, f"no longer routes: {sorted(set(PUBLIC) - {p for _, p in routes})}"


def test_a_visitor_who_is_not_signed_in_is_refused_by_every_route_that_is_not_public(served, owned):
    with TestClient(api.app) as visitor:
        for method, path in api_routes():
            if path in PUBLIC:
                continue
            answer = ask(visitor, method, filled(path, owned))
            assert answer.status_code in (401, 403, 404), f"{method} {path} answered a visitor {answer.status_code}"
            assert not any(words in answer.text for words in WORDS_OF_THE_OWNER), f"{method} {path} told a visitor the owner's words"


def test_another_signed_in_advocate_holding_the_owners_identifiers_gets_nothing_of_the_owners(served, owned):
    other = served.login(OTHER)
    asked = 0
    for method, path in api_routes():
        if "{" not in path or path.startswith("/api/admin/"):
            continue  # the Admin routes have their own test: they answer admins and nobody else
        answer = ask(other, method, filled(path, owned))
        asked += 1
        assert answer.status_code < 500, f"{method} {path} failed for another advocate: {answer.status_code}"
        assert not 200 <= answer.status_code < 300, f"{method} {path} answered another advocate {answer.status_code}"
        assert not any(words in answer.text for words in WORDS_OF_THE_OWNER), f"{method} {path} told another advocate the owner's words"
    assert asked >= 15
    assert other.get("/api/work").json()["chats"] == [], "and the other advocate's own history holds none of it"
    assert served.client.get(f"/api/chats/{owned['chat_id']}").status_code == 200, "while the owner still reads their own"
