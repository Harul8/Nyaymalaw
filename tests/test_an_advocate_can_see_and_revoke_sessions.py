"""BK-31 — where am I signed in, and sign the others out.

WHAT WAS MISSING
------------------
The directory implemented enrol, login, session and logout, and nothing else
of the account lifecycle. An advocate who thought a device was compromised had
no way to see their sessions and no way to end them — the only lever was to
wait for expiry, on a product holding client files.

WHAT THIS IS NOT
------------------
It is not account recovery, and BK-31 asks for that too. Recovery needs a
delivery channel this deployment has not chosen, and inventing one would be
worse than the gap: a single-use expiring token is only as good as the path it
travels, and a token emailed by a product with no verified address is a way in
rather than a way back.

THE DEPLOYMENT DECISION THIS RESTS ON
---------------------------------------
Recorded 8 September 2026: **a controlled private roster**. Advocates are
enrolled; self-registration is closed or approval-gated. That is why the
sign-in path may keep distinguishing an unknown handle from a wrong password —
the roster is not public, and the message is worth more to the advocate than
the enumeration is to a stranger. If it ever becomes public self-enrolment,
one generic response and a verified address come with it.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.class_a


# ================================================================ the list ===

def test_an_advocate_can_see_where_they_are_signed_in(client):
    """The question is a security question, so the answer has to be checkable."""
    r = client.get("/api/sessions")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["count"] >= 1, "the signing-in session is not in its own list"
    mine = [s for s in body["sessions"] if s["this_one"]]
    assert len(mine) == 1, (
        f"{len(mine)} sessions claim to be this one, so the advocate cannot "
        f"tell which row is the device they are holding")
    assert mine[0]["live"] is True


def test_the_list_carries_no_token_and_no_fingerprint(client):
    """THE FINGERPRINT IS WHAT THE SERVER MATCHES A COOKIE AGAINST.

    Handing it to a browser would put the one value that identifies a session
    into a place this product does not control -- and a device list is not
    worth that.
    """
    body = client.get("/api/sessions").json()
    blob = str(body)
    assert "token_fingerprint" not in blob
    assert "token" not in blob.replace("this_one", "")


def test_an_ended_session_stays_on_the_list(client):
    """BOTH STATES, and the ended one is the interesting half.

    "One session, this device" is worth nothing to an advocate who cannot
    also see the one that ended an hour ago on a machine they do not
    recognise.
    """
    before = client.get("/api/sessions").json()["count"]
    client.post("/api/logout")
    client.sign_in()

    body = client.get("/api/sessions").json()
    assert body["count"] > before, "the ended session vanished from the list"
    ended = [s for s in body["sessions"] if not s["live"]]
    assert ended, "no session is recorded as ended"
    assert ended[0]["ended_because"], (
        "a session is over and does not say why, so an advocate cannot tell "
        "an expiry from a sign-out from a revocation")


# ============================================================= the revoke ====

def test_revoking_ends_the_others_and_keeps_this_one(client):
    """A CONTROL THAT LOGS YOU OUT TO PROTECT YOU IS USED ONCE.

    The case this exists for is a device the advocate no longer controls, so
    the session they are asking FROM has to survive -- otherwise securing the
    others costs them the one they are holding.
    """
    other = client.sign_in(fresh=True)
    assert other.get("/api/sessions").status_code == 200

    r = client.post("/api/sessions/revoke")
    assert r.status_code == 200, r.text
    assert r.json()["ended"] >= 1, (
        "revoking ended nothing, and the count is the only thing that makes "
        "'signed out everywhere' checkable")

    # THIS ONE SURVIVES.
    assert client.get("/api/sessions").status_code == 200
    # AND THE OTHER DOES NOT.
    assert other.get("/api/sessions").status_code == 401, (
        "a revoked session still authenticates, so the control did nothing "
        "and said it did something")


def test_revoking_twice_ends_nothing_the_second_time(client):
    """The count is a fact about what happened, not a fixed reassurance."""
    client.sign_in(fresh=True)
    first = client.post("/api/sessions/revoke").json()["ended"]
    second = client.post("/api/sessions/revoke").json()["ended"]

    assert first >= 1
    assert second == 0, (
        f"revoking again claims to have ended {second} sessions, so the "
        f"number is decoration rather than a report")


# ======================================================== the false promise ==

def test_registration_does_not_promise_a_firm_wide_conflict_registry():
    """BK-31: *do not claim a firm-wide conflict check until a verified firm
    membership and a working registry exist.*

    The sign-in page said the firm's conflicts registry GOVERNS the session.
    There is none: BK-34's conflict screen checks the matters THIS advocate
    holds and says so in its own words. A promise about the one check whose
    whole value is being trusted is the worst place in the product to be
    approximately right.
    """
    import pathlib
    html = (pathlib.Path(__file__).resolve().parents[1]
            / "frontend" / "index.html").read_text(encoding="utf-8")

    for claim in ("registry governs", "conflicts registry is scoped",
                  "registry governs the session"):
        assert claim not in html, (
            f"the sign-in page still promises {claim!r}, and there is no "
            f"firm-wide registry behind it")
    assert "not a firm-wide registry" in html, (
        "registration does not say what the conflict check actually covers")
