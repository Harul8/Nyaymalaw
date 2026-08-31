"""The scripted adapter. Deterministic, offline, free.

It exists for two reasons, and the second is the important one:

  1. Class-A and class-B tests need a model that costs nothing and never varies.
  2. IT IS THE SECOND PROVIDER. Provider independence is proved by SWITCHING,
     not by having an interface -- an abstraction nobody has switched is an
     unexercised claim, the same shape as a guard with no production caller.
     This adapter is what makes that switch runnable on every commit instead of
     only when a second API key appears.

It implements the SAME contract suite as the real adapters. If a change to the
port fits OpenAI and not this one, the port has become OpenAI-shaped and the
design has quietly failed.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

from nm.adapters.model._budget import estimate_tokens, guard_budget
from nm.adapters.model.config import CONTEXT_BUDGET, ModelConfig, TierConfig
from nm.ports.model import (
    EmbeddingResult,
    ModelResult,
    Prompt,
    SchemaViolation,
    Tier,
    Usage,
    require_schema,
)

Responder = Callable[[Prompt, Tier], str]

#: Posture extraction is a STRUCTURED call the engine now makes on every turn
#: whose posture is unresolved. The scripted adapter answers it deterministically
#: so class-A tests keep costing nothing -- reading the advocate's own words
#: with a small regex is fine HERE, in a test double, and was not fine in the
#: product, where the list could never be complete.
_SCRIPTED_POSTURE = re.compile(
    r"\b(?:we\s+act\s+for|we\s+represent|our\s+client\s+is|we\s+appear\s+for)"
    r"\s+(?:the\s+)?([a-z][a-z\- ]{2,30})", re.I)
_SCRIPTED_ROLES = {
    "plaintiff", "defendant", "complainant", "accused", "petitioner",
    "respondent", "appellant", "applicant", "opposite party",
    "decree holder", "judgment debtor",
}


def scripted_posture(message: str) -> str:
    """A deterministic stand-in for the model's posture extraction."""
    m = _SCRIPTED_POSTURE.search(message or "")
    if not m:
        return json.dumps({"states_client": False, "role": "not_stated",
                           "role_basis": "stated", "client_described_as": "",
                           "quoted": ""})
    party = " ".join(m.group(1).split()).lower()
    role = next((r for r in _SCRIPTED_ROLES if party.startswith(r)), None)
    return json.dumps({
        "states_client": True,
        "role": role or "not_stated",
        "role_basis": "stated",
        "client_described_as": "" if role else party.split(" in ")[0],
        "quoted": m.group(0),
    })


#: The ROLE read -- the second structured call, made once the advocate has
#: said who they act for and the five-field extraction returned no role.
#: Mapped from the account so the scripted provider behaves like a real one
#: for this call; without it the call falls through to `__default__`, which
#: is not JSON, and every offline test of the resolve path silently
#: exercises the failure branch instead.
_SCRIPTED_ROLE = (
    ("dismissed", "petitioner"),
    ("reinstatement", "petitioner"),
    ("maintenance", "petitioner"),
    ("talaq", "petitioner"),
    ("bounced", "complainant"),
    ("dishonour", "complainant"),
    ("cheque", "complainant"),
    ("quit notice", "respondent"),
    ("eviction", "respondent"),
    ("possession", "plaintiff"),
    ("title suit", "plaintiff"),
    ("recovery", "plaintiff"),
)


#: The DISPUTE read. Without this the call falls through to `__default__`,
#: which is not JSON, and every offline test of thread separation would
#: exercise the failure branch while looking like it exercised the
#: ordinary one -- the same trap `scripted_role` was added to close.
_OPENS_A_DISPUTE = (
    "second,", "third,", "fourth,", "fifth,", "separately",
    "another matter", "a different", "unrelated",
)


#: The DATE read. `\d{1,2} Month YYYY` and a bare `yesterday` are all the
#: scripted provider needs to behave like a real one for class-A tests; the
#: product's own reader takes no list at all, because there is no list of the
#: ways a date can be written.
_SCRIPTED_DATE = re.compile(
    r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(\d{4})\b", re.I)
_MONTHS = ("january february march april may june july august september "
           "october november december").split()


def scripted_dates(user: str) -> str:
    """A deterministic stand-in for the model's date read."""
    said = user.split("just said:", 1)[-1]
    ref = re.search(r"Today is (\d{4}-\d{2}-\d{2})", user)
    events = []
    for m in _SCRIPTED_DATE.finditer(said):
        day, month, year = m.group(1), m.group(2).lower(), m.group(3)
        events.append({
            "event": said.strip().split(".")[0][:70] or "an event",
            "date_expression": m.group(0),
            "resolved": f"{year}-{_MONTHS.index(month) + 1:02d}-{int(day):02d}",
            "documented": "dated" in said.lower() or "notice" in said.lower(),
        })
    if not events and "yesterday" in said.lower() and ref:
        import datetime
        on = datetime.date.fromisoformat(ref.group(1)) - datetime.timedelta(days=1)
        events.append({"event": said.strip().split(".")[0][:70] or "an event",
                       "date_expression": "yesterday",
                       "resolved": on.isoformat(), "documented": False})
    return json.dumps({"events": events})


def scripted_dispute(user: str) -> str:
    """A deterministic stand-in for the model's dispute read."""
    # ONLY WHAT THE ADVOCATE SAID, not the prompt around it. Taking everything
    # after the marker swept in the closing line -- "or open a different one?"
    # -- whose own words are on the marker list, so every message read as a new
    # dispute. The verbatim guard in `dispute.interpret` refused the span and
    # turned it into `cannot_tell`, which is that guard doing its job on the
    # test double.
    said = user.split("just said:", 1)[-1].rsplit(chr(10) * 2, 1)[0].lower()
    for needle in _OPENS_A_DISPUTE:
        if needle in said:
            start = said.index(needle)
            return json.dumps({
                "verdict": "opens",
                "quoted": said[start:start + len(needle)],
                "why": f"the advocate marks it off with {needle!r}"})
    return json.dumps({"verdict": "continues", "quoted": "",
                       "why": "it adds detail to what is on the file"})


def scripted_role(user: str) -> str:
    """A deterministic stand-in for the model's role read."""
    low = (user or "").lower()
    for needle, role in _SCRIPTED_ROLE:
        if needle in low:
            return json.dumps({"role": role,
                               "why": f"the account mentions {needle}"})
    return json.dumps({"role": "cannot_tell",
                       "why": "the account does not say what proceeding "
                              "exists or who moved it"})


#: Words an advocate uses for a cause, and the cause they name. TEST DOUBLE.
#:
#: A phrase list is fine HERE and is not fine in the product, for exactly the
#: reason `scripted_posture` gives about its own regex: this stands in for a
#: model on a deterministic path, and the product's own answer is a model read
#: with guards (`nm/core/cause.py`) precisely because no list can be complete.
_SCRIPTED_CAUSE = (
    ("goods were supplied", "goods_sold_price"),
    ("goods sold", "goods_sold_price"),
    ("invoices", "goods_sold_price"),
    ("money lent", "money_lent"),
    ("loan", "money_lent"),
    ("specific performance", "specific_performance"),
    ("agreement of sale", "specific_performance"),
    ("breach of contract", "breach_of_contract"),
    ("dispossessed", "possession_on_previous_possession"),
    ("title suit", "possession_on_title"),
    ("declaration", "declaration"),
    ("cheque", "cheque_dishonour"),
)


def scripted_cause(user: str) -> str:
    """A deterministic stand-in for the model's cause read.

    THE QUOTED SPAN IS THE ADVOCATE'S OWN WORDS, taken from `user`, because
    `nm.core.cause.interpret` refuses a span that is not — and a double that
    could not satisfy the product's own guard would prove the guard untested
    rather than satisfied.
    """
    said = user.split("just asked:", 1)[-1]
    whole = user or ""
    for needle, cause in _SCRIPTED_CAUSE:
        for haystack in (said, whole):
            i = haystack.lower().find(needle)
            if i >= 0:
                return json.dumps({
                    "cause": cause,
                    "quoted": haystack[i:i + len(needle)],
                    "why": f"the account mentions {needle}",
                })
    return json.dumps({"cause": "cannot_tell", "quoted": "",
                       "why": "the account does not name a cause this "
                              "product routes on"})


#: Schema TITLE -> the responder that answers it. AN EXACT KEY, NOT A SUBSTRING.
#:
#: It was a substring search over the schema's JSON, and that is fuzzy matching
#: doing identification — the thing CLAUDE.md §5 measures as not merely weak
#: but wrong. `cannot_tell` turned out to be claimed by THREE schemas (role,
#: dispute, cause); which one answered was decided by the order of an `elif`
#: chain, and the cause read lost. Every cause read got a role object back and
#: fired G-MODEL `unavailable` on every served turn.
#:
#: A title is an exact key on a closed vocabulary, so a collision is not
#: possible rather than merely unlikely, and a schema with no title has no
#: responder at all — which `tests/test_provider_independence.py` fails on
#: rather than degrading at runtime.
SCRIPTED_READS: dict[str, object] = {
    "posture": scripted_posture,
    "dispute": scripted_dispute,
    "dates": scripted_dates,
    "role": scripted_role,
    "cause": scripted_cause,
}

_tokens = estimate_tokens  # one owner: nm.adapters.model._budget


class ScriptedModelAdapter:
    """Serves canned or rule-derived responses. Never touches the network."""

    def __init__(
        self,
        config: ModelConfig,
        responses: Mapping[str, str] | None = None,
        responder: Responder | None = None,
    ) -> None:
        self._config = config
        self._responses = dict(responses or {})
        self._responder = responder
        self.calls: list[tuple[Tier, Prompt]] = []

    # ------------------------------------------------------------- port ---
    @property
    def provider(self) -> str:
        return "scripted"

    def resolved_model(self, tier: Tier) -> str:
        return f"scripted:{self._cfg(tier).model}"

    def context_budget(self, tier: Tier) -> int:
        return CONTEXT_BUDGET[tier]

    def complete(self, prompt: Prompt, tier: Tier, *,
                 max_tokens: int | None = None) -> ModelResult:
        started = time.perf_counter()
        self._guard_budget(prompt, tier)
        self.calls.append((tier, prompt))
        text = self._respond(prompt, tier)
        return self._result(text, None, prompt, tier, started)

    def structured(
        self,
        prompt: Prompt,
        schema: Mapping[str, Any],
        tier: Tier,
        *,
        max_tokens: int | None = None,
    ) -> ModelResult:
        started = time.perf_counter()
        self._guard_budget(prompt, tier)
        self.calls.append((tier, prompt))
        raw = self._respond(prompt, tier)
        responder = SCRIPTED_READS.get(schema.get("title") or "")
        if responder is not None:
            # ONE responder, or the dispatch is ambiguous and the FIRST match
            # silently wins. That is what happened when the cause read was
            # added: `CAUSE_SCHEMA` contains `cannot_tell`, which was the role
            # read's discriminator, so every cause read got a role object back,
            # failed validation, and fired G-MODEL `unavailable` on every
            # served turn while the model was perfectly available.
            #
            # `tests/test_provider_independence.py` refuses a second claimant
            # on a discriminator, which is the same rule
            # `tests/test_citation_patterns.py` already applies to Act
            # keywords: no keyword may be claimed by two Acts.
            raw = responder(prompt.user)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            # NEVER best-effort parsed. Lenient parsing is how an invented
            # vocabulary once emptied a charge map.
            raise SchemaViolation(f"scripted response is not JSON: {exc}") from exc
        require_schema(data, schema)
        return self._result(None, data, prompt, tier, started)

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        cfg = self._cfg(Tier.EMBED)
        vectors = tuple(_deterministic_vector(t) for t in texts)
        n = sum(_tokens(t) for t in texts)
        return EmbeddingResult(
            vectors=vectors, model=cfg.model, provider=self.provider,
            usage=Usage(tokens_in=n, tokens_out=0, cost_usd=0.0),
        )

    # -------------------------------------------------------- internals ---
    def _cfg(self, tier: Tier) -> TierConfig:
        return self._config.for_tier(tier)

    def _guard_budget(self, prompt: Prompt, tier: Tier) -> None:
        guard_budget(prompt, tier)

    def _respond(self, prompt: Prompt, tier: Tier) -> str:
        if self._responder is not None:
            return self._responder(prompt, tier)
        for needle, reply in self._responses.items():
            if needle.lower() in prompt.user.lower():
                return reply
        return self._responses.get("__default__", "SCRIPTED")

    def _result(self, text, data, prompt: Prompt, tier: Tier, started: float) -> ModelResult:
        cfg = self._cfg(tier)
        t_in = _tokens((prompt.system or "") + prompt.user)
        t_out = _tokens(text or json.dumps(data))
        return ModelResult(
            text=text, data=data, tier=tier, provider=self.provider,
            model=self.resolved_model(tier),
            usage=Usage(tokens_in=t_in, tokens_out=t_out,
                        cost_usd=cfg.cost(t_in, t_out), cached_tokens=0),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _deterministic_vector(text: str, dim: int = 16) -> tuple[float, ...]:
    """Stable pseudo-embedding. Not semantically meaningful and not pretending
    to be -- it exists so the port's embed() has a testable shape."""
    acc = [0.0] * dim
    for i, ch in enumerate(text):
        acc[i % dim] += (ord(ch) % 17) / 17.0
    norm = sum(v * v for v in acc) ** 0.5 or 1.0
    return tuple(round(v / norm, 6) for v in acc)
