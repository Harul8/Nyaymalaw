"""A provider's stated wait is honoured, within a cap, and requests out at once are bounded (plan AN.52, piece 52f; D212; the
review's F-14).

When the AI provider refused a call for its rate, NM tried again after about half a second and then about one, whatever wait the
provider stated; a per-minute limit does not clear in a second and a half, so the third refusal failed the stage. The transport
now waits what the provider says, the waits of one call together never pass a cap, and the process sends at most a set number
of requests to a provider at once. Offline: the provider is a stand-in and no time is really waited.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from nm.shared import model_transport
from nm.shared.model_port import RateLimited
from nm.shared.model_transport import request_with_retries, stated_wait

pytestmark = pytest.mark.class_a


class RateLimitError(Exception):
    """The provider's own refusal, as its SDK names it."""

    def __init__(self, message="429 rate limit", headers=None):
        super().__init__(message)
        self.response = SimpleNamespace(headers=headers or {})


@pytest.fixture
def waits(monkeypatch):
    slept = []
    monkeypatch.setattr(model_transport.time, "sleep", slept.append)
    return slept


def refusing(times, **refusal):
    calls = []

    def call():
        calls.append(1)
        if len(calls) <= times:
            raise RateLimitError(**refusal)
        return "answered"
    return call, calls


def test_a_call_refused_twice_with_a_stated_five_second_wait_waits_at_least_that_each_time_and_then_answers(waits):
    call, calls = refusing(2, headers={"retry-after": "5"})
    assert request_with_retries(call) == ("answered", 2)
    assert len(calls) == 3 and len(waits) == 2 and all(5 <= wait < 5.5 for wait in waits)


def test_a_refusal_that_states_no_wait_is_retried_after_the_short_pauses_as_before(waits):
    call, _ = refusing(2)
    assert request_with_retries(call) == ("answered", 2)
    assert 0.5 <= waits[0] <= 0.7 and 1.0 <= waits[1] <= 1.2


@pytest.mark.parametrize("refusal, seconds", [
    ({"headers": {"retry-after-ms": "2500"}}, 2.5),
    ({"headers": {"retry-after": "7"}}, 7.0),
    ({"headers": {"retry-after-ms": "300", "retry-after": "9"}}, 0.3),
    ({"message": "Rate limit reached. Please try again in 6.2s."}, 6.2),
    ({"message": "Rate limit reached. Please try again in 450ms."}, 0.45),
    ({"headers": {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}}, None),
    ({"headers": {"retry-after": "-3"}}, None),
    ({}, None),
])
def test_the_wait_a_provider_states_is_read_from_its_headers_then_its_words(refusal, seconds):
    assert stated_wait(RateLimitError(**refusal)) == pytest.approx(seconds) if seconds is not None else (
        stated_wait(RateLimitError(**refusal)) is None)


def test_a_stated_wait_longer_than_the_cap_fails_the_call_at_once_as_a_rate_limit(waits):
    call, calls = refusing(5, headers={"retry-after": str(model_transport.WAIT_CAP + 1)})
    with pytest.raises(RateLimited):
        request_with_retries(call)
    assert len(calls) == 1 and waits == [], "it does not wait a minute to fail anyway"


def test_the_waits_of_one_call_together_never_pass_the_cap(waits):
    call, calls = refusing(5, headers={"retry-after": str(model_transport.WAIT_CAP * 0.6)})
    with pytest.raises(RateLimited):
        request_with_retries(call)
    assert len(calls) == 2 and sum(waits) <= model_transport.WAIT_CAP


def test_requests_out_to_a_provider_at_once_are_bounded_and_none_is_held_while_waiting(monkeypatch):
    monkeypatch.setattr(model_transport, "_gate", threading.BoundedSemaphore(2))
    out, most, lock, done = [0], [0], threading.Lock(), []

    def call():
        with lock:
            out[0] += 1
            most[0] = max(most[0], out[0])
        time.sleep(0.05)
        with lock:
            out[0] -= 1
        return "answered"
    threads = [threading.Thread(target=lambda: done.append(request_with_retries(call))) for _ in range(8)]
    for each in threads:
        each.start()
    for each in threads:
        each.join(30)
    assert len(done) == 8 and most[0] == 2

    # A call that is waiting to try again holds no place: another goes out meanwhile.
    held = []
    monkeypatch.setattr(model_transport, "_gate", threading.BoundedSemaphore(1))
    monkeypatch.setattr(model_transport.time, "sleep", lambda _: held.append(model_transport._gate.acquire(blocking=False))
                        or model_transport._gate.release())
    refused, _ = refusing(1)
    assert request_with_retries(refused) == ("answered", 1) and held == [True]


def test_the_bound_is_the_operators_setting_or_the_default(monkeypatch):
    monkeypatch.setattr(model_transport, "_gate", None)
    monkeypatch.setenv("NM_PROVIDER_REQUESTS_AT_ONCE", "3")
    gate = model_transport._out()
    assert [gate.acquire(blocking=False) for _ in range(4)] == [True, True, True, False]
    monkeypatch.setattr(model_transport, "_gate", None)
    monkeypatch.setenv("NM_PROVIDER_REQUESTS_AT_ONCE", "many")
    assert model_transport._out()._initial_value == model_transport.REQUESTS_AT_ONCE
    monkeypatch.setattr(model_transport, "_gate", None)
