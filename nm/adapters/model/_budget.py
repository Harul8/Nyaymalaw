"""The context budget guard. ONE owner, called by every adapter.

WHY THIS IS ITS OWN MODULE
--------------------------
The first draft enforced the budget inside the scripted adapter and left the
OpenAI adapter to rely on the provider returning an overflow error. That makes
the budget a PROVIDER concept, which is exactly backwards: PRD §7.4.4 puts the
budget on the port, chosen as what the smallest supported provider can hold, so
that a prompt built to the budget ports unchanged.

It also failed the second-copy test. The question is never "where is the other
copy" but "what makes a second copy impossible" -- so the estimate and the
guard live here, and an adapter that wants them calls the owner.
"""
from __future__ import annotations

from nm.adapters.model.config import CONTEXT_BUDGET
from nm.ports.model import ContextOverflow, Prompt, Tier


def estimate_tokens(text: str) -> int:
    """A deliberately crude, deterministic estimate.

    Not a real tokenizer: a guard whose threshold moves with a tokenizer's
    version is a guard that fails differently across releases. It errs toward
    over-counting, so the guard trips before the provider's hard limit rather
    than after it.
    """
    return max(1, len(text) // 4)


def prompt_tokens(prompt: Prompt) -> int:
    return estimate_tokens((prompt.system or "") + prompt.user)


def guard_budget(prompt: Prompt, tier: Tier) -> None:
    """Raise ContextOverflow BEFORE the call, identically for every provider.

    A typed error, never a truncation. Silent truncation produces an answer
    that looks complete and was reasoned from a fraction of the material -- and
    the advocate has no way to tell the difference.
    """
    size = prompt_tokens(prompt)
    budget = CONTEXT_BUDGET[tier]
    if size > budget:
        raise ContextOverflow(
            f"prompt is ~{size} tokens against the port's {tier.value} budget of "
            f"{budget}. The budget belongs to the port, not to the provider, so "
            f"this fails the same way whichever adapter is live."
        )
