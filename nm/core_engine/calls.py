"""One turn owns model accounting and the single conditional draft correction."""
from __future__ import annotations

import json
import time
from copy import deepcopy

from nm.shared.model_port import ContextOverflow, ModelError, Prompt, SchemaViolation, estimate_tokens


class CorrectionUnavailable(ModelError):
    """This turn's draft repair is already spent. Never a reason to release it."""


class ReleaseWithheld(ModelError):
    """A terminal release boundary fired; draft correction cannot clear it."""


class TurnCalls:
    """Construct once per turn; pass this same object to every model stage.

    The model adapter owns bounded transport retries and the durable dollar cap.
    This owner bounds semantic/shape correction across activities and records
    their receipts. No nested stage receives a fresh allowance.
    """
    def __init__(self, model):
        self.inner = model
        self.calls = []
        self.correction = None
        self.correction_used = False
        self.last_output = None
        self.terminal = False

    def context_budget(self, tier):
        return self.inner.context_budget(tier)

    def structured(self, prompt, schema, tier, *, max_tokens):
        if self.terminal:
            raise ReleaseWithheld("This turn's release scope is withheld")
        feedback = self.correction
        if feedback is not None and feedback["operation"] == prompt.operation:
            payload = json.loads(prompt.user)
            payload["correction"] = deepcopy(feedback)
            prompt = Prompt(system=prompt.system, user=json.dumps(payload, ensure_ascii=False),
                            operation=prompt.operation)
        if (estimate_tokens((prompt.system or "") + prompt.user + json.dumps(schema))
                + max_tokens > self.context_budget(tier)):
            raise ContextOverflow("The complete stage input and correction exceed the context budget")
        self.last_output = None
        started, receipt, error = time.monotonic(), None, None
        try:
            receipt = self.inner.structured(prompt, schema, tier, max_tokens=max_tokens)
            if receipt.usable:
                self.last_output = deepcopy(receipt.data)
            return receipt
        except ModelError as exc:
            receipt, error = exc, type(exc).__name__
            rejected = getattr(exc, "rejected_result", None)
            if rejected is not None:
                self.last_output = deepcopy(rejected.data)
            raise
        finally:
            usage = getattr(receipt, "usage", None)
            self.calls.append({"operation": prompt.operation, "error": error,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "tokens_in": usage.tokens_in if usage else None,
                "tokens_out": usage.tokens_out if usage else None,
                "cost_usd": usage.cost_usd if usage else None,
                "retries": getattr(receipt, "retries", 0),
                "correction": feedback is not None and feedback["operation"] == prompt.operation,
                "usage_confirmed": usage is not None})

    def correct(self, operation, activity, *, mismatch, rejected=None):
        """Correct a typed owner-rejected draft; caller must revalidate the result.

        Operation-scoped feedback never enters an independent review call.
        It is untrusted draft data, not original evidence or an execution receipt.
        """
        if self.terminal:
            raise ReleaseWithheld("This turn's release scope is withheld")
        if self.correction_used:
            raise CorrectionUnavailable("The shared draft correction has already been used")
        if not isinstance(operation, str) or not operation or not mismatch:
            raise ValueError("Correction requires an owning operation and precise mismatch")
        self.correction_used = True
        self.correction = {"operation": operation,
            "purpose": "Correct the rejected draft using the complete original input and declared output contract.",
            "mismatch": deepcopy(mismatch), "rejected_draft": deepcopy(rejected),
            "provenance": "Untrusted rejected output and owner feedback; neither is original evidence."}
        try:
            return activity()
        finally:
            self.correction = None

    def checked(self, operation, activity):
        """Shape errors may consume the one repair; outages/refusals never do."""
        try:
            return activity()
        except SchemaViolation as exc:
            return self.correct(operation, activity, mismatch=str(exc), rejected=self.last_output)

    def withhold(self, reason):
        self.terminal = True
        raise ReleaseWithheld(reason)

    def metrics(self):
        return {"llm_calls": len(self.calls), "calls": deepcopy(self.calls),
                "reported_transport_retries": sum(c["retries"] for c in self.calls),
                "usage_unconfirmed_calls": sum(not c["usage_confirmed"] for c in self.calls),
                "cost_usd": sum(c["cost_usd"] or 0 for c in self.calls),
                "tokens_in": sum(c["tokens_in"] or 0 for c in self.calls),
                "tokens_out": sum(c["tokens_out"] or 0 for c in self.calls),
                "draft_corrections": int(self.correction_used)}
