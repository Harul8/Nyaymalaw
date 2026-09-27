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
)

MAX_RETRIES = 3


def normalise_error(exc: Exception) -> Exception:
    """SDK failures become port errors; programming faults remain themselves."""
    if isinstance(
        exc,
        (NameError, AttributeError, TypeError, KeyError, AssertionError, ValueError, ModelError),
    ):
        return exc
    name, message = type(exc).__name__, str(exc)
    low = message.lower()
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
    """Unknown/failed attempts keep their reservations, including on retry."""
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
            if isinstance(normalised, RateLimited) and attempt < MAX_RETRIES - 1:
                time.sleep(0.5 * (2**attempt) + random.uniform(0, 0.2))
                continue
            if normalised is exc:
                raise
            raise normalised from exc
    raise AssertionError("The bounded transport loop did not return or raise")
