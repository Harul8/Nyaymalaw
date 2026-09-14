"""BK-20 / BK-18 — the sign-in door stops accepting wrong answers.

The product had no rate limit, and had said so since slice 1 in a message the
ADVOCATE reads: *"this is the only thing standing between one advocate's
client file and another's, and the product has no rate limit yet."* A known
gap, declared in the one place nobody tracks.

Naming which of three things failed at sign-in (BK-20) made that gap worth
more, because enumeration is cheap in proportion to how fast it can be tried.
The two land together.

TWO COUNTERS, AND ONE DOES NOT IMPLY THE OTHER
------------------------------------------------
Per advocate stops guessing one account's password. Per source stops sweeping
many addresses from one place -- and a sweep never trips a per-account counter,
because it tries each address once. Either alone leaves the other attack
untouched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from nm.domain import attempts

pytestmark = pytest.mark.class_a

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _times(n: int, ago: timedelta) -> tuple[datetime, ...]:
    return tuple(NOW - ago for _ in range(n))


# ===================== the policy, as arithmetic ==========================

def test_the_door_opens_until_the_limit_and_then_does_not():
    """The boundary, both sides. A limiter asserted only on the refusal is one
    that could be refusing everything."""
    inside = _times(attempts.PER_ADVOCATE - 1, timedelta(minutes=1))
    assert attempts.verdict(inside, (), NOW).allowed

    at_limit = _times(attempts.PER_ADVOCATE, timedelta(minutes=1))
    assert not attempts.verdict(at_limit, (), NOW).allowed


def test_a_sweep_across_addresses_trips_the_source_counter():
    """THE HALF THAT PAIRS WITH NAMING THE FAILURE.

    A directory sweep tries each address ONCE, so the per-advocate counter
    never sees more than one failure and never fires. Only the source counter
    stops it -- which is why limiting per account alone would have left
    enumeration exactly as cheap as before.
    """
    one_each = _times(attempts.PER_SOURCE, timedelta(minutes=2))
    assert not attempts.verdict((), one_each, NOW).allowed
    assert "from this connection" in attempts.verdict((), one_each, NOW).because


def test_failures_older_than_the_window_do_not_count():
    """A count that never ages out is a lockout, and a lockout is a
    denial-of-service handed to whoever knows an advocate's email."""
    old = _times(attempts.PER_ADVOCATE * 3, attempts.WINDOW + timedelta(minutes=1))
    assert attempts.verdict(old, (), NOW).allowed


def test_the_pause_is_measured_from_the_oldest_attempt_in_the_window():
    """COUNTING FROM THE NEWEST WOULD EXTEND THE PAUSE EVERY TIME THE ATTACKER
    KNOCKED -- and extend it for the advocate, who is the one reading the
    message and the one with a hearing tomorrow.

    The oldest attempt in the window is what has to age out before one slot
    frees, so that is what `retry_after` measures.
    """
    oldest = NOW - timedelta(minutes=14)
    times = (oldest, *(_times(attempts.PER_ADVOCATE - 1, timedelta(seconds=5))))
    seen = attempts.verdict(times, (), NOW)

    assert not seen.allowed
    # One minute left of a fifteen-minute window, not fifteen.
    assert seen.retry_after is not None
    assert timedelta(seconds=30) < seen.retry_after < timedelta(minutes=2), (
        f"the pause is measured from the wrong end: {seen.retry_after}")


def test_a_refusal_says_when_and_says_nothing_is_locked():
    """"Too many attempts" with no time on it is a wall. A locked-out advocate
    needs to know whether the answer is four minutes or four hours, and an
    attacker learns nothing from a number they could measure with a clock."""
    said = attempts.verdict(
        _times(attempts.PER_ADVOCATE, timedelta(seconds=5)), (), NOW).said

    assert "Try again in about" in said
    assert "minute" in said or "second" in said
    assert "Nothing is locked" in said, (
        "the advocate is not told that their account is untouched, so a "
        "refusal reads as a disabled account")


def test_an_allowed_attempt_says_nothing_at_all():
    """THE BOUND. A message on every successful sign-in is one the advocate
    learns to skip, and then does not read on the turn it matters."""
    assert attempts.verdict((), (), NOW).said == ""


# ===================== the door, on the served path =======================

def test_the_limiter_runs_before_the_password_is_verified(client, monkeypatch):
    """The point of a limiter is that the EXPENSIVE part stops happening. A
    guard after the derivation still pays for every guess."""
    from nm.edge import api

    calls = []
    original = client.directory.authenticate_and_open_session

    def watched(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(client.directory, "authenticate_and_open_session", watched)
    credentials = {"advocate_id": "adv_demo",
                   "password": "Fixture-password-not-a-secret-1"}
    assert client.post("/api/login", json=credentials).status_code == 200
    assert calls == [True], "the positive path never reached credential verification"
    calls.clear()
    for _ in range(attempts.PER_ADVOCATE):
        client.directory.note_failure("adv_demo", "testclient", api.utcnow())
    response = client.post("/api/login", json=credentials)
    assert response.status_code == 429, response.text
    assert calls == [], "a refused attempt still reached credential verification"


def test_a_refused_attempt_is_429_and_not_401(client):
    """A refusal is NOT a wrong password, and calling it one tells an advocate
    to check credentials that may be perfectly correct."""
    from nm.edge import api

    for _ in range(attempts.PER_ADVOCATE):
        client.directory.note_failure("adv_demo", "testclient", api.utcnow())
    response = client.post("/api/login", json={
        "advocate_id": "adv_demo", "password": "Fixture-password-not-a-secret-1"})
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0


def test_a_limiter_that_cannot_run_opens_the_door_and_says_so(client, monkeypatch):
    """FAILING OPEN IS THE RIGHT DIRECTION AND MUST BE VISIBLE.

    Refusing every sign-in because a log file is unwritable would be a
    self-inflicted outage on a product used under time pressure. Allowing them
    SILENTLY is the S1 shape -- a control that could not run returning the
    shape of a clean result.

    So `failures_since` returns None for "could not tell", the door opens, and
    `/api/health` reports rate limiting as NOT RUNNING.
    """
    import inspect

    from nm.adapters.store.directory import FileDirectory
    reader = inspect.getsource(FileDirectory.failures_since)
    assert "return None" in reader, (
        "the store no longer distinguishes 'could not read' from 'no failures'")

    monkeypatch.setattr(client.directory, "failures_since", lambda *args: None)
    monkeypatch.setattr(client.directory, "limiter_available", lambda: False)
    response = client.post("/api/login", json={
        "advocate_id": "adv_demo", "password": "Fixture-password-not-a-secret-1"})
    assert response.status_code == 200, response.text
    health = client.get("/api/health")
    assert health.status_code == 200, health.text
    assert "NOT RUNNING" in health.json()["rate_limiting"], (
        "the unavailable limiter was hidden from the served health response")


def test_a_successful_sign_in_adds_nothing_to_the_count():
    """Otherwise an advocate who works all day locks themselves out."""
    import inspect

    from nm.edge import api

    src = inspect.getsource(api.login)
    note = src.index("note_failure")
    refused = src.index("if opened is None:")
    assert note > refused, (
        "the failure is recorded outside the failure branch, so every "
        "successful sign-in counts against the advocate")
