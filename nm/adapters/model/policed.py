"""The egress policy, in front of the model. BK-85-AC1. P06.

    model = PolicedModel(inner=TracedModel(...), policy=..., region=...)

WHY A WRAPPER AND NOT A CHECK INSIDE THE ADAPTER
--------------------------------------------------
`TracedModel` already answers this question for tracing, in words that apply
unchanged: tracing inside each adapter is two owners of one decision, and a
change described as global landing in half the product is the defect that file
most wants to avoid being. The same is true of egress, and harder -- an adapter
that checks its own policy is an adapter that can be written without one.

So this satisfies `ModelPort`, delegates everything, and refuses BEFORE it
delegates. The composition root decides whether to wrap, and
`tests/test_the_model_is_policed_before_it_is_called.py` refuses a wiring that
forgets to.

WHY THE CLASSIFICATION IS FIXED AT CONSTRUCTION
------------------------------------------------
A prompt on the turn path carries the advocate's client material. Deciding that
per call would mean inspecting the prompt -- which needs the content to decide,
and `nm/domain/egress.py` exists precisely so the decision does not need the
content.

So a model wired for matter work IS a client-material route, declared once, at
the composition root, where somebody can see it. A caller that genuinely wants
an operational-only dispatch constructs a differently-classified wrapper and
says so; it does not pass a flag that the next caller can omit.

THE REFUSAL IS NOT A DEGRADED ANSWER
--------------------------------------
`EgressRefused` propagates. It is not caught here and turned into an empty
`ModelResult`, because a refused dispatch that returns the shape of a clean
result is the single most repeated defect in this codebase -- a screen that
could not run returning a clean answer -- and it would be that defect holding
privileged client material.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from nm.domain.egress import DataClass, EgressRefused, Gatekeeper, Policy, Sink
from nm.ports.model import ModelPort, Tier

#: RE-EXPORTED, NOT REDEFINED. The refusal belongs with the decision that
#: makes it, and a second class by the same name here would mean an `except`
#: at a call site caught the model's refusals and not the store's.
__all__ = ["EgressRefused", "PolicedModel"]


@dataclass
class PolicedModel:
    """Any `ModelPort`, refused before it is called."""

    inner: ModelPort
    policy: Policy
    #: What this route carries. Declared once, here, rather than guessed per
    #: call from a prompt nobody wants to inspect.
    data_classes: tuple[DataClass, ...] = (DataClass.CLIENT_MATTER,)
    #: Where refusals are recorded. Content-free by construction: `audit_line`
    #: composes the route, the reason and a byte count and has no access to the
    #: prompt at all.
    audit: Callable[[str], None] | None = None
    refused: list[str] = field(default_factory=list)
    """Refusals this process has made. Counted so a policy that is refusing
    everything is visible as a number rather than as an outage somebody
    diagnoses from the other end."""
    #: The shared decision point, when the composition root has one. Passing it
    #: means every sink's refusals land in ONE audit in the order they
    #: happened, which is what an operator reconstructing an incident reads.
    #: Left out, this builds its own from `policy` and `audit`, so a test can
    #: construct a policed model without assembling an application.
    gate: Gatekeeper | None = None

    # -------------------------------------------------- pass-through -------

    @property
    def provider(self) -> str:
        return self.inner.provider

    def resolved_model(self, tier: Tier) -> str:
        return self.inner.resolved_model(tier)

    def context_budget(self, tier: Tier) -> int:
        return self.inner.context_budget(tier)

    # ------------------------------------------------------ policed --------

    def __post_init__(self) -> None:
        if self.gate is None:
            self.gate = Gatekeeper(policy=self.policy, audit=self.audit,
                                   refused=self.refused)

    def _permit(self, size: int) -> None:
        self.gate.permit(Sink.MODEL, self.inner.provider, self.data_classes,
                         size_bytes=size)

    @staticmethod
    def _size(prompt: Any) -> int:
        """Bytes, for the audit line. A size is not content."""
        try:
            return len(str(getattr(prompt, "user", "") or "").encode("utf8"))
        except Exception:  # noqa: BLE001 -- an unmeasurable prompt is not a refusal
            return 0

    def complete(self, prompt: Any, tier: Tier, *,
                 max_tokens: int | None = None):
        self._permit(self._size(prompt))
        return self.inner.complete(prompt, tier, max_tokens=max_tokens)

    def structured(self, prompt: Any, schema: Mapping[str, Any], tier: Tier, *,
                   max_tokens: int | None = None):
        self._permit(self._size(prompt))
        return self.inner.structured(prompt, schema, tier,
                                     max_tokens=max_tokens)

    def embed(self, texts: tuple[str, ...]):
        """POLICED, THOUGH `TracedModel` DELIBERATELY DOES NOT TRACE IT.

        Those are different questions and the answers differ. Tracing asks what
        a person could later read, and an embedding call carries no prompt and
        no readable answer -- so not tracing it is right. Egress asks what
        LEAVES, and an embedding call sends the text verbatim to the provider.
        The vectors come back; the sentences went.

        This was missing from the first draft and the port-coverage test found
        it. The wrapper answered `complete` and `structured` and silently did
        not answer `embed` at all -- which under Python's duck typing is not an
        error, it is an unpoliced route that works.
        """
        self._permit(sum(len((t or "").encode("utf8")) for t in texts or ()))
        return self.inner.embed(texts)
