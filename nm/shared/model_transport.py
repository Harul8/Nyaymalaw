"""One retry/error/accounting policy for every external model transport."""

from __future__ import annotations

import random
import time

from nm.shared.model_port import (
    ConfigurationError,
    ContentRefused,
    ContextOverflow,
    ModelError,
    ProviderUnavailable,
    RateLimited,
    UsageLimitReached,
)

MAX_RETRIES = 3
#: What a provider calls an account with no credit or quota left (P51; OpenAI answered with type
#: insufficient_quota and code credit_balance_exhausted on 25 Oct 2026, as a 429).
NO_CREDIT = frozenset({"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"})
#: Provider failures that pass (17 Oct 2026: one dropped connection in a turn's twenty
#: calls had ended the whole turn): retried like rate limits, within the same bound.
TRANSIENT = frozenset({"APIConnectionError", "APITimeoutError", "InternalServerError", "OverloadedError"})


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
    if name in {"AuthenticationError", "PermissionDeniedError", "NotFoundError"}:
        return ConfigurationError(message)
    if name in {"BadRequestError", "UnprocessableEntityError"}:
        if "context_length_exceeded" in low or "maximum context length" in low:
            return ContextOverflow(message)
        if "content_filter" in low or "content policy" in low:
            return ContentRefused(message)
        return ConfigurationError(message)
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
    and transient provider failures are retried within the bound; nothing else is."""
    for attempt in range(MAX_RETRIES):
        if before_dispatch is not None:
            before_dispatch()
        reservation = call_budget.reserve(model) if call_budget else None
        try:
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
                time.sleep(0.5 * (2**attempt) + random.uniform(0, 0.2))
                continue
            if normalised is exc:
                raise
            raise normalised from exc
    raise AssertionError("The bounded transport loop did not return or raise")
