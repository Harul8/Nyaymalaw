"""Each account's usage of the paid AI service, and the allowance it draws on (owner decisions O21-O24,
plans P53 and AN.17).

WHAT COUNTS (owner, O24: "Everything that consumes API tokens should count towards usage, we should
measure every API call expense regardless of success or failed response and count and keep track of all
API costs"): every request made to the paid AI service for an advocate - the calls of a turn, the
reading of page images, the transcription of voice notes and dictation, live dictation - whatever its
outcome, at the cost the provider's own usage report establishes. A call whose cost was not established
is still kept, as not established; it is never charged an invented figure.

THE ALLOWANCE: a trial of 30 cents, given once to each account the first time its allowance is read
("Load 30 cents once per account"), and whatever an operator adds until payment exists (later, by UPI).
Shown only as the percentage left (O21); once nothing is left, new work is refused before it starts
("Once nothing is left"), in the owner's words of P51.

Content-free by construction: no prompt, message, answer or file reaches this port, only what a call
cost and how it went.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from nm.shared.model_port import UsageLimitReached

#: The trial (owner, O24): 30 cents of usage, in millionths of a US dollar like every charge here.
TRIAL_MICRO_USD = 300_000
#: The percentages left at which the advocate is told (P53, O22, O23): 50% once, 25% once, then every 1%
#: from 10% down.
NOTICE_STEPS = (50, 25, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)
#: The 50% and 25% notices close by themselves after ten minutes (O22, O23); the rest stay until closed.
SELF_CLOSING_STEPS = frozenset({50, 25})
SELF_CLOSING_SECONDS = 600
#: The kinds of call a record may describe: the model port's own methods that send work to a provider.
CALL_KINDS = frozenset({"complete", "structured", "tool_call", "transcribe", "live_transcription", "embed"})
#: What a record of one call holds; every field but kind, operation, tier, model, outcome and attempts may
#: be None where the provider did not establish it.
CALL_FIELDS = ("kind", "operation", "tier", "model", "outcome", "attempts", "tokens_in", "tokens_out",
               "cached_tokens", "cache_write_tokens", "audio_seconds", "micro_usd")


class UsageRefused(Exception):
    """The usage store could not be read or written. Never a reason to treat usage as free."""


class AllowanceUsedUp(UsageLimitReached):
    """This account's own allowance is used up (AN.17): raised before any call is made, so every place
    that names the provider's usage limit (P51) names this one too, in the same words."""


def percent_left(granted: int, spent: int) -> int:
    """The whole percentage of the allowance left, rounded up, so that 0% always means nothing is left
    and an allowance with anything at all left never reads as 0%."""
    if type(granted) is not int or type(spent) is not int or spent < 0:
        raise ValueError("usage is counted in whole millionths of a dollar")
    left = granted - spent
    if granted <= 0 or left <= 0:
        return 0
    return min(100, -(-100 * left // granted))


def due_notice(left: int, noticed: int | None) -> int | None:
    """The notice to show now, if any: the step the allowance has reached, when it is lower than the last
    one shown. At nothing left the limit state replaces the notices (P53)."""
    if left <= 0:
        return None
    reached = [step for step in NOTICE_STEPS if step >= left]
    if not reached:
        return None
    step = min(reached)
    return step if noticed is None or step < noticed else None


@runtime_checkable
class UsagePort(Protocol):
    def standing(self, account_id: str) -> dict:
        """{'granted', 'spent' (millionths of a dollar), 'left' (whole percent), 'noticed' (the last notice
        step shown, or None)}. The first read of an account gives it its trial."""
        ...

    def record(self, account_id: str, call: dict) -> None:
        """Keep one call to the paid AI service, with exactly CALL_FIELDS."""
        ...

    def grant(self, account_id: str, micro_usd: int, *, note: str) -> dict:
        """An operator adds usage to an account (no web route); its notices start again. Its standing."""
        ...

    def noticed(self, account_id: str, step: int) -> None:
        """The advocate has been shown the notice for this step."""
        ...

    def totals(self) -> dict:
        """What every call cost, for the operator: overall, by model and by outcome, with the calls whose
        cost was not established counted apart."""
        ...
