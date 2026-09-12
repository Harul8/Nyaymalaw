"""EVERY COOKIE-AUTHENTICATED UNSAFE OPERATION REFUSES A CROSS-SITE CALLER.

BK-31-AC20.

WHAT WAS THERE BEFORE, MEASURED 10 SEPTEMBER 2026
---------------------------------------------------
Nothing. `grep -rn csrf nm/` returned no match. The only thing between a
signed-in advocate and a cross-site write was `samesite="lax"` on the session
cookie — one control, owned by the browser rather than by this product, absent
in clients that predate it, and no protection at all against a same-site
origin. It was never a decision; it was a default nobody had examined.

WHY THIS TEST ENUMERATES THE ROUTER
-------------------------------------
A per-route test proves the routes somebody remembered. The failure mode is the
SEVENTH route, added next month by someone who has never read this file — and a
list of six maintained by hand looks identical whether it is complete or three
behind. So the population comes from `app.routes`, and a new unsafe route is
covered the day it is written or it fails here with its own path in the message.

THE EXEMPTIONS ARE NAMED, WITH THE REASON
-------------------------------------------
`register`, `recover` and `login` carry no session cookie: they are what mints
one. A CSRF token cannot be required from a caller who does not have a session
yet. They are declared below with what protects them instead, because an
admitted gap is work and a silent one is a surprise.
"""
from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.routing import APIRoute

from nm.domain.advocate import csrf_token
from nm.edge.api import app, csrf_protected, signed_in

pytestmark = pytest.mark.class_a

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

#: Unsafe routes that legitimately carry no session cookie, and WHY.
#:
#: Each of these establishes a session rather than acting under one, so there is
#: no CSRF value to double-submit. That is not the same as unprotected: they are
#: rate-limited per source, they refuse without valid credentials, and a
#: cross-site caller forcing one succeeds only in signing the victim's browser
#: into an account the attacker already controls -- login CSRF, which is real
#: and is BK-31's own follow-on work rather than something this packet closes.
PRE_SESSION: dict[str, str] = {
    "/api/register": "no session minted; its own origin and bounded signup admission",
    "/api/recover": "mints no session at all; refuses without a valid one-time code",
    "/api/login": "mints the session; refuses without the credential",
}


#: Guarded routes that deliberately do NOT require an authenticated advocate,
#: and why that is safe. FOUND BY THE INVARIANT BELOW rather than reasoned
#: about in advance: the first version of that check reported `/api/logout` and
#: the reasoning behind the CSRF early-return had to be repaired, not the test.
SELF_LIMITING: dict[str, str] = {
    "/api/logout": (
        "acts only on whatever the caller's own cookie names, takes no input, "
        "is idempotent, and MUST work for a session that has already expired -- "
        "requiring auth would 401 and leave the cookies set, which is the "
        "half-signed-out state it exists to prevent. A cross-site forced logout "
        "is a nuisance and not a disclosure, and the CSRF check still applies "
        "whenever a session cookie is actually present."),
}


def _unsafe_routes() -> list[tuple[str, APIRoute]]:
    found = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.methods & UNSAFE:
            found.append((route.path, route))
    return sorted(found)


def _is_protected(route: APIRoute) -> bool:
    """Route-level dependency, not a call inside the handler.

    Checked structurally on purpose: a handler that CALLS the check can return
    before reaching it, and every early return becomes a bypass nobody sees.
    """
    #: `fastapi.params.Depends` holds the callable on `.dependency`; the
    #: resolved `Dependant` in `route.dependant.dependencies` holds it on
    #: `.call`. BOTH ARE CHECKED because the first draft looked only for `.call`
    #: on the raw list, found nothing, and reported `/api/turn` -- which is
    #: guarded -- as unguarded. The positive control caught that on its first
    #: run, which is the entire argument for having one.
    declared = [getattr(d, "dependency", None) for d in route.dependencies]
    resolved = [getattr(d, "call", None)
                for d in getattr(route.dependant, "dependencies", [])]
    return csrf_protected in declared or csrf_protected in resolved


def test_the_router_still_has_unsafe_routes_to_check():
    """S11's guard. If the population goes to zero this file passes everything,
    and a renamed decorator or a moved app object would do exactly that."""
    routes = _unsafe_routes()
    assert len(routes) >= 6, (
        f"only {len(routes)} unsafe route(s) found -- the enumeration broke, "
        f"and a sweep that sees nothing approves everything")
    assert {"/api/turn", "/api/logout", "/api/sessions/revoke"} <= {p for p, _ in routes}


def test_every_cookie_authenticated_unsafe_route_declares_the_csrf_dependency():
    """THE SWEEP. Population from the router, exemptions named with a reason."""
    unguarded = []
    for path, route in _unsafe_routes():
        if path in PRE_SESSION:
            continue
        if not _is_protected(route):
            unguarded.append(f"{sorted(route.methods & UNSAFE)} {path}")
    assert not unguarded, (
        "these unsafe routes act under a session cookie and do not declare "
        "`CsrfProtected`:\n  " + "\n  ".join(unguarded)
        + "\n\nAdd `dependencies=[CsrfProtected]` to the decorator, or declare "
          "it in PRE_SESSION with what protects it instead.")


def test_every_csrf_guarded_route_also_requires_authentication():
    """THE SENTENCE THE CSRF CHECK RELIES ON, MADE CHECKABLE.

    `csrf_protected` returns early when there is no session cookie, so the 401
    comes from `signed_in` rather than a 403 from here -- which the turn
    route's contract test asserts and which `web/app.js` keys its
    sign-out-and-restore on.

    That early return is only safe while every guarded route ALSO requires an
    authenticated advocate. A route that took the CSRF dependency and no auth
    would be wide open to an anonymous caller, and the reasoning for the early
    return is buried in a comment nobody re-reads. So it is enforced here: the
    comment states the invariant, this states it in a form that fails.
    """
    unauthenticated = []
    for path, route in _unsafe_routes():
        if path in PRE_SESSION or path in SELF_LIMITING or not _is_protected(route):
            continue
        needs_advocate = any(
            getattr(d, "call", None) is signed_in
            for d in getattr(route.dependant, "dependencies", []))
        if not needs_advocate:
            unauthenticated.append(path)
    assert not unauthenticated, (
        "these routes take the CSRF dependency and do NOT require an "
        f"authenticated advocate: {unauthenticated}. `csrf_protected` waives "
        f"itself when no session cookie is present, so such a route is "
        f"reachable by an anonymous caller with no check at all.")


def test_the_sweep_can_see_a_route_that_forgot_the_dependency():
    """POSITIVE CONTROL. The sweep above passes identically whether it is
    working or has quietly stopped finding routes (B-049)."""
    planted = APIRoute("/api/planted-unsafe", lambda: None, methods=["POST"])
    assert planted.methods & UNSAFE
    assert not _is_protected(planted), "the plant is not an offender"

    guarded = next(r for p, r in _unsafe_routes() if p == "/api/turn")
    assert _is_protected(guarded), (
        "a genuinely guarded route reads as unguarded, so the sweep is merely "
        "strict rather than correct")


def test_the_auth_sweep_can_see_a_guarded_route_with_no_authentication():
    """POSITIVE CONTROL for the invariant above.

    That sweep passes identically whether it is working or has stopped
    resolving `signed_in` -- and it found `/api/logout` on its first run, so it
    demonstrably could fail then. This keeps that true: a route carrying the
    CSRF dependency and no advocate must be reported, because `csrf_protected`
    waives itself when there is no session cookie.
    """
    planted = APIRoute("/api/planted-guarded", lambda: None, methods=["POST"],
                       dependencies=[Depends(csrf_protected)])
    assert _is_protected(planted), "the plant is not guarded, so it proves nothing"
    resolved = [getattr(d, "call", None)
                for d in getattr(planted.dependant, "dependencies", [])]
    assert signed_in not in resolved, "the plant requires auth and is not an offender"

    real = next(r for path, r in _unsafe_routes() if path == "/api/turn")
    real_resolved = [getattr(d, "call", None)
                     for d in getattr(real.dependant, "dependencies", [])]
    assert signed_in in real_resolved, (
        "a genuinely authenticated route reads as unauthenticated, so the "
        "sweep is merely strict rather than correct")


def test_every_named_exemption_is_a_route_that_still_exists():
    """An exemption for a route that was renamed is an exemption for nothing,
    and it would silently start covering whatever takes that path next."""
    paths = {p for p, _ in _unsafe_routes()}
    for name, table in (("PRE_SESSION", PRE_SESSION),
                        ("SELF_LIMITING", SELF_LIMITING)):
        missing = sorted(set(table) - paths)
        assert not missing, f"{name} names routes that no longer exist: {missing}"
        for path, reason in table.items():
            assert reason.strip(), f"{path} is exempted in {name} and says no why"


# ============================ the check itself ==============================

class _Request:
    """The two headers the check reads, and a base_url. Nothing else."""

    def __init__(self, origin=None, referer=None, base="http://testserver/"):
        self.headers = {}
        if origin is not None:
            self.headers["origin"] = origin
        if referer is not None:
            self.headers["referer"] = referer
        self.base_url = base


def _check(request, session="a-session-token", header=...):
    from fastapi import HTTPException
    if header is ...:
        header = csrf_token(session)
    try:
        csrf_protected(request, nm_session=session, x_nm_csrf=header)
        return None
    except HTTPException as refused:
        return refused


def test_a_same_origin_request_carrying_the_derived_token_is_allowed():
    """NEGATIVE CONTROL. Without it, a check that refused everything would
    satisfy every refusal below and break the product."""
    assert _check(_Request(origin="http://testserver")) is None
    assert _check(_Request(referer="http://testserver/index.html")) is None


@pytest.mark.parametrize("what,request_,session,header", [
    ("a foreign origin", _Request(origin="https://evil.example"), "s", ...),
    ("a foreign referer", _Request(referer="https://evil.example/x"), "s", ...),
    ("no origin and no referer at all", _Request(), "s", ...),
    ("no csrf header", _Request(origin="http://testserver"), "s", None),
    ("a wrong csrf header", _Request(origin="http://testserver"), "s", "nope"),
    ("another session's token", _Request(origin="http://testserver"), "s",
     csrf_token("a-different-session")),
])
def test_what_it_refuses(what, request_, session, header):
    refused = _check(request_, session=session, header=header)
    assert refused is not None, what
    assert refused.status_code == 403


@pytest.mark.parametrize("hostile", [
    "http://testserver.evil.example",   # the trusted host as a SUBDOMAIN LABEL
    "http://evil-testserver",           # the trusted host as a SUFFIX
    "http://testserver.evil.example:80",
    "https://testserver",               # same host, DIFFERENT SCHEME
    "http://testserver:9999",           # same host, DIFFERENT PORT
    "http://testserverr",               # one character further on
])
def test_an_origin_that_merely_resembles_the_trusted_one_is_refused(hostile):
    """THE CLASSIC ORIGIN-CHECK BYPASS, and the reason the comparison is exact.

    `startswith`, `in`, and endswith-on-the-host are the three ways this check
    is usually written and all three admit `http://testserver.evil.example` --
    an origin an attacker can register today. Scheme and port are part of an
    origin too: `https://testserver` and `http://testserver:9999` are different
    origins from `http://testserver` and a browser treats them as such.
    """
    assert _check(_Request(origin=hostile)) is not None, hostile
    assert _check(_Request(referer=hostile + "/page")) is not None, hostile


def test_an_absent_origin_is_refused_rather_than_waved_through():
    """§9, in the place it is most often got wrong. Most hand-written origin
    checks read `if origin and origin not in trusted` -- which permits every
    caller that simply omits the header, and that is the whole bypass."""
    assert _check(_Request()) is not None


def test_the_refusal_never_says_which_check_failed():
    """Three causes, one sentence. A refusal that distinguishes them tells a
    cross-site caller whether they guessed the origin right."""
    said = {
        str(_check(_Request(origin="https://evil.example")).detail),
        str(_check(_Request(origin="http://testserver"), header=None).detail),
        str(_check(_Request()).detail),
    }
    assert len(said) == 1, f"refusals differ by cause: {said}"


def test_the_token_is_one_way_and_session_bound():
    """A leaked CSRF value must not yield the session token it came from, or
    the readable cookie is as good as the httponly one."""
    token = "a-session-token"
    derived = csrf_token(token)
    assert token not in derived
    assert derived != csrf_token(token + "x")
    assert csrf_token("") != csrf_token(token)
