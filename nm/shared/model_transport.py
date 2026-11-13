"""One retry/error/accounting policy for every external model transport."""

from __future__ import annotations

import os
import random
import re
import threading
import time
from contextlib import contextmanager

from nm.shared.model_port import (
    ContentRefused,
    ContextOverflow,
    ModelError,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    UsageLimitReached,
)

MAX_RETRIES = 3
#: What a provider calls an account with no credit or quota left (P51; OpenAI answered with type
#: insufficient_quota and code credit_balance_exhausted on 25 Oct 2026, as a 429).
NO_CREDIT = frozenset({"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"})
#: Provider failures that pass (17 Oct 2026: one dropped connection in a turn's twenty
#: calls had ended the whole turn): retried like rate limits, within the same bound.
TRANSIENT = frozenset({"APIConnectionError", "APITimeoutError", "InternalServerError", "OverloadedError"})
#: Plan AN.52 (52i4, D215; the review's F-31): of those, the failures after which the provider may still have done the work - and
#: billed it - though NM let the attempt go and sent it again: the client stopped waiting, or the connection was lost. A rate
#: limit and the provider's own server error are not among them: the provider says it did not do the work.
MAY_HAVE_BEEN_BILLED = frozenset({"APITimeoutError", "APIConnectionError"})
_let_go = threading.local()


@contextmanager
def attempts_let_go():
    """The attempts of the calls this thread makes inside it that were let go and sent again after the provider may have done the
    work (MAY_HAVE_BEEN_BILLED), each by the name of its failure. The meter opens it around a call (nm/shared/model_metered.py),
    which alone knows whose call it is; outside it nothing is noted."""
    outer = getattr(_let_go, "attempts", None)
    _let_go.attempts = []
    try:
        yield _let_go.attempts
    finally:
        _let_go.attempts = outer


#: Plan AN.52 (52f, D212; the review's F-14). A provider that refuses a call for its rate says how long to wait, and a
#: per-minute limit does not clear in the second and a half the fixed pauses gave it. The wait it states is honoured, and
#: the waits of one call together never pass WAIT_CAP seconds: past that the call fails as it did, and its stage's own
#: bounded recovery decides.
WAIT_CAP = 60.0
#: How many requests this process has out to a provider at once, at most. A turn sends several large calls side by side
#: and every advocate shares one account, so without a bound a busy server walks into the rate limit by itself. Set with
#: NM_PROVIDER_REQUESTS_AT_ONCE; read once, when the first call is made.
REQUESTS_AT_ONCE = 16
_gate = None
_gate_made = threading.Lock()
_SAID_WAIT = re.compile(r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|s)(?![a-z])", re.I)


def _out():
    """The process's one bound on requests out to a provider at once."""
    global _gate
    with _gate_made:
        if _gate is None:
            try:
                most = int(os.environ.get("NM_PROVIDER_REQUESTS_AT_ONCE", "") or REQUESTS_AT_ONCE)
            except ValueError:
                most = REQUESTS_AT_ONCE
            _gate = threading.BoundedSemaphore(max(1, most))
        return _gate


def stated_wait(exc: Exception) -> float | None:
    """The seconds a provider says to wait before the call is made again, or None where it says none: its retry-after
    headers first, then the words of its refusal ("try again in 5.2s")."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    for name, unit in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        try:
            value = headers.get(name) if headers is not None else None
            if value is not None:
                seconds = float(value) * unit
                if seconds >= 0:
                    return seconds
        except (TypeError, ValueError, AttributeError):
            continue  # a date, or no number: the next way of saying it
    said = _SAID_WAIT.search(str(exc))
    if said:
        return float(said.group(1)) * (0.001 if said.group(2).lower() == "ms" else 1.0)
    return None


def _transient(exc: Exception) -> bool:
    """A provider-side failure that may pass. Only the SDK's own errors qualify: a port
    error our code raised after the provider answered (usage or cost not established)
    is never retried, since a retry would pay twice."""
    if isinstance(exc, ModelError):
        return False
    status = getattr(exc, "status_code", None)
    return type(exc).__name__ in TRANSIENT or (
        type(exc).__name__ == "APIStatusError" and isinstance(status, int) and status >= 500)


def _no_credit(exc: Exception) -> bool:
    """Whether a provider failure says the account has no credit or quota left: the code or type
    the SDK read from the provider's answer, wherever it keeps them; the words of the message only
    where it carries none of them (a stream reports its errors as text)."""
    body = getattr(exc, "body", None)
    body = body.get("error", body) if isinstance(body, dict) else {}
    said = [getattr(exc, "code", None), getattr(exc, "type", None),
            *(body.get(key) for key in ("code", "type") if isinstance(body, dict))]
    return any(isinstance(value, str) and value in NO_CREDIT for value in said) or any(
        word in str(exc).lower() for word in NO_CREDIT)


def normalise_error(exc: Exception) -> Exception:
    """SDK failures become port errors; programming faults remain themselves."""
    if isinstance(
        exc,
        (NameError, AttributeError, TypeError, KeyError, AssertionError, ValueError, ModelError),
    ):
        return exc
    name, message = type(exc).__name__, str(exc)
    low = message.lower()
    # Before every other reading: the provider answers this as a 429 (a rate limit by name) or as
    # a bad request, and neither is it (P51).
    if _no_credit(exc):
        return UsageLimitReached(message)
    if name == "RateLimitError" or (name == "RuntimeError" and "429 rate limit" in low):
        return RateLimited(message)
    if name in {"APIConnectionError", "APITimeoutError", "InternalServerError", "OverloadedError"}:
        return ProviderUnavailable(message)
    # Plan AN.52 (52i, D215; the review's F-31): the provider's rejection of NM's own request - not authorised, no such model,
    # malformed - has its own name. It was a plain ConfigurationError, which the engine's handlers took for an outage.
    if name in {"AuthenticationError", "PermissionDeniedError", "NotFoundError"}:
        return RequestRejected(message)
    if name in {"BadRequestError", "UnprocessableEntityError"}:
        if "context_length_exceeded" in low or "maximum context length" in low:
            return ContextOverflow(message)
        if "content_filter" in low or "content policy" in low:
            return ContentRefused(message)
        return RequestRejected(message)
    if name == "APIStatusError":
        return ProviderUnavailable(message)
    return exc


def request_with_retries(
    fn,
    *,
    model="",
    before_dispatch=None,
    call_budget=None,
    ledger_response=lambda response: response,
):
    """Unknown/failed attempts keep their reservations, including on retry. Rate limits
    and transient provider failures are retried within the bound; nothing else is. A wait the
    provider states is honoured within WAIT_CAP, and the request itself is made within the
    process's bound on requests out at once (plan AN.52, 52f) - never held while waiting."""
    waited = 0.0
    for attempt in range(MAX_RETRIES):
        if before_dispatch is not None:
            before_dispatch()
        reservation = call_budget.reserve(model) if call_budget else None
        try:
            with _out():
                response = fn()
            if reservation is not None:
                call_budget.settle(reservation, ledger_response(response))
            return response, attempt
        except Exception as exc:  # noqa: BLE001 -- unknown faults are re-raised unchanged
            normalised = normalise_error(exc)
            if isinstance(normalised, ModelError):
                normalised.retries = attempt
            if (isinstance(normalised, RateLimited) or _transient(exc)) and not isinstance(
                    normalised, UsageLimitReached) and attempt < MAX_RETRIES - 1:
                pause = 0.5 * (2**attempt) + random.uniform(0, 0.2)
                stated = stated_wait(exc)
                if stated is not None:
                    pause = max(pause, stated + random.uniform(0, 0.2))
                if waited + pause <= WAIT_CAP:
                    waited += pause
                    noted = getattr(_let_go, "attempts", None)
                    if noted is not None and type(exc).__name__ in MAY_HAVE_BEEN_BILLED:
                        noted.append(type(exc).__name__)  # let go and sent again: it may have been billed (52i4)
                    time.sleep(pause)
                    continue
                # The provider asks for longer than one call may wait: it fails now, as a rate limit, for its stage.
            if normalised is exc:
                raise
            raise normalised from exc
    raise AssertionError("The bounded transport loop did not return or raise")
