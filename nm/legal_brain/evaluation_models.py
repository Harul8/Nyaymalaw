"""One explicit evaluation cap for both authorised model identities.

This constructs transports, not consent, a session or a cutover approval. Each
caller must still use the authenticated text boundary. No embedding, media or
alternate provider is covered by this pair.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nm.legal_brain.interaction_review import (
    COMMUNICATION_PROTOCOL_VERSIONS,
    communication_contract,
)
from nm.legal_brain.loop_contracts import digest
from nm.legal_brain.verifier import VERIFICATION_SCHEMA
from nm.shared.external_ai_contracts import ModelPermissionRefused
from nm.shared.model_call_budget import CallBudget
from nm.shared.model_config import ModelConfig, TierConfig, require_priced_snapshot
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_port import ConfigurationError, Tier

AUTHOR = "gpt-4o-mini-2024-07-18"
VERIFIER = "gpt-5.1-2025-11-13"


class VerifierOnly:
    """A separate verifier cannot be borrowed as an expensive author or tool agent."""
    def __init__(self, inner):
        self.inner = inner
        self._schema_identities = frozenset((digest(VERIFICATION_SCHEMA), *(
            digest(communication_contract(version)[1])
            for version in COMMUNICATION_PROTOCOL_VERSIONS)))

    @property
    def provider(self):
        return self.inner.provider

    @staticmethod
    def _tier(tier):
        if tier is not Tier.JUDGE:
            raise ModelPermissionRefused("This approval permits independent verification only.")

    def resolved_model(self, tier):
        self._tier(tier)
        return self.inner.resolved_model(tier)

    def context_budget(self, tier):
        self._tier(tier)
        return self.inner.context_budget(tier)

    def for_matter_text(self, before_dispatch):
        # Binding consent must retain the verifier's closed capability facade.
        return VerifierOnly(self.inner.for_matter_text(before_dispatch))

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self._tier(tier)
        if digest(schema) not in self._schema_identities:
            raise ModelPermissionRefused(
                "Only the owned evidence-package and communication checks are approved.")
        if (max_tokens is not None and (type(max_tokens) is not int
                                        or not 1 <= max_tokens <= 2048)):
            raise ModelPermissionRefused("The verifier output exceeds its bounded read allowance.")
        return self.inner.structured(prompt, schema, tier, max_tokens=max_tokens or 2048)

    def complete(self, *_args, **_kwargs):
        raise ModelPermissionRefused("Verification permission does not permit authoring.")

    def tool_call(self, *_args, **_kwargs):
        raise ModelPermissionRefused("Verification permission does not permit tool selection.")

    def embed(self, *_args, **_kwargs):
        raise ModelPermissionRefused("Verification permission does not permit embeddings.")


@dataclass(frozen=True)
class EvaluationModels:
    author: OpenAIModelAdapter
    verifier: VerifierOnly
    author_budget: CallBudget
    verifier_budget: CallBudget
    config: ModelConfig

    def bind(self, *, directory, account_id: str, session_current, audit=None):
        """Both roles use the same actual consent/session owner at dispatch."""
        from nm.app.model_permission import bind_text_model

        def bound(adapter):
            return bind_text_model(adapter, directory=directory, account_id=account_id,
                config=self.config, session_current=session_current, audit=audit)

        return bound(self.author), bound(self.verifier)


def _direct(config):
    if any(row.provider != "openai" or (row.base_url or "https://api.openai.com/v1")
           not in {"https://api.openai.com/v1", "https://api.openai.com/v1/"}
           for row in config.tiers.values()):
        raise ConfigurationError("The evaluation permits only the direct approved OpenAI endpoint.")


def bounded_pair(config: ModelConfig, *, ledger: Path, maximum_usd: str,
                 author_client=None, verifier_client=None) -> EvaluationModels:
    """Trusted evaluation composition; the same durable ledger bounds BOTH models.

    A snapshot mismatch refuses before constructing a provider client. The
    immutable ledger maximum cannot be raised on restart. GPT-5.1's USD0.55
    reservation bounds its published 400,000 context tokens and the enforced
    2,048-token output ceiling at USD1.25/10 per million (official model page
    checked 27 September 2026). Unknown outcomes retain that full reservation.
    GPT-4o mini retains the existing conservative USD0.03 reservation.
    """
    _direct(config)
    author = require_priced_snapshot(config.for_tier(Tier.ROUTINE), provider="openai")
    judge = require_priced_snapshot(config.for_tier(Tier.JUDGE), provider="openai")
    if author.model != AUTHOR or judge.model != VERIFIER:
        raise ConfigurationError(
            "This approval names GPT-4o mini as author and dated GPT-5.1 as verifier.")
    author_budget = CallBudget(ledger, maximum_usd, model=author.model,
        price_per_million=(str(author.price_in), str(author.price_out)),
        reservation_micro_usd=30000)
    judge_budget = CallBudget(ledger, maximum_usd, model=judge.model,
        price_per_million=(str(judge.price_in), str(judge.price_out)),
        reservation_micro_usd=550000)
    # The author's transport deliberately has no judge tier: it cannot use
    # the cheaper ledger to dispatch another model. The separate transport's
    # constructor gets its own key/endpoint; the closed facade permits JUDGE.
    author_config = ModelConfig({Tier.ROUTINE: author})
    judge_config = ModelConfig({
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, judge.provider, judge.model,
                                judge.api_key, judge.base_url),
        Tier.JUDGE: judge,
    })
    return EvaluationModels(
        OpenAIModelAdapter(author_config, client=author_client, call_budget=author_budget),
        VerifierOnly(OpenAIModelAdapter(judge_config, client=verifier_client,
                                       call_budget=judge_budget)),
        author_budget, judge_budget, ModelConfig(dict(config.tiers)))
