"""One turn owns model accounting and its bounded conditional draft corrections."""
from __future__ import annotations

import json
import re
import threading
import time
from contextlib import contextmanager
from copy import deepcopy

from nm.shared.model_port import ContextOverflow, ModelError, ModelResult, Prompt, SchemaViolation, estimate_tokens

#: Corrections the turn's shared steps (understanding, research, time limits) may make
#: between them: one, as before (owner decision, 17 Oct 2026).
SHARED_ALLOWANCE = 1
#: Corrections each section of an answer may make (owner decision P25, 19 Oct 2026: "At most
#: we can do a third try"): its draft and up to two rewrites, whatever asked for them - the
#: independent review, the date check or code's own checks of its form. A section that
#: still fails after that is trimmed statement by statement, never withheld whole.
SECTION_ALLOWANCE = 2
#: A shown section the cross-check between sections asks to correct gets one rewrite
#: (owner decision P27, 19 Oct 2026); if that does not pass, the section stays as shown.
EDIT_ALLOWANCE = 1
#: The corrections one turn may make in all, held durably so that a retried turn never
#: receives a fresh allowance beyond it (the turn-attempt store's own limit). The review may
#: correct its own form within its section's allowance (owner, 18 Oct 2026: a form slip by
#: the review withheld two answers the writer had got right).
ALLOWANCE = 32
#: Plain instructions for a rewrite the independent review asked for (owner decision P25, 19
#: Oct 2026: tell the model the answer is not grounded and ask it to ground the answer in the
#: details shared).
GROUNDING_PURPOSE = ("The independent review found the problems listed in mismatch in the rejected draft. "
                     "Rewrite the section so that every statement rests on the advocate's messages, the "
                     "documents they sent or the held sources supplied, exactly as those put it; where they do "
                     "not support a point, say plainly what is missing instead of asserting it. Keep what the "
                     "review did not fault.")
#: Plain instructions for a rewrite a v10 review asked for (owner decision P29, 20 Oct 2026):
#: what would mislead the advocate, and what could be better.
REVIEW_PURPOSE = ("The independent review found what is listed in mismatch in the rejected draft: statements that "
                  "would mislead the advocate as they stand, and what the section could add or put better. Rewrite "
                  "the section so that every statement rests on the advocate's messages, the documents they sent "
                  "or the held sources supplied, exactly as those put it; where they do not support a point, say "
                  "plainly what is missing instead of asserting it. Add or improve what the review suggests where "
                  "those sources bear it out. Keep what the review did not fault.")
#: Plain instructions for a correction the check across the sections asked for (owner
#: decision P27, 19 Oct 2026).
CONFLICT_PURPOSE = ("A check across the sections of this answer found the conflicts listed in mismatch between this "
                    "section, as shown in rejected_draft, and another section of the same answer. Rewrite this "
                    "section so that it is right and agrees with what the advocate's messages, the documents they "
                    "sent and the held sources support, exactly as those put it; where they do not settle the "
                    "point, say so plainly. Keep what the check did not fault.")


def refusal_reason(exc):
    """Why code refused an output, in the reason's own fixed words, up to the first quotation
    or detail: never the words refused (the first live run of 20 Oct 2026)."""
    return re.split(r"[:“\"'(\[{]", str(exc), maxsplit=1)[0].strip()[:120] or type(exc).__name__


def shape_mismatch(exc):
    """What a correction is told when code refused a draft's shape. A quotation refused as
    not the source's exact words is corrected with the source's own words nearest to it
    (18 Oct 2026)."""
    near = getattr(exc, "near", None)
    mismatch = str(exc) + (f". The source's own words nearest to that quotation, exactly as they stand: "
                           f"“{near}”" if near else "")
    if hasattr(exc, "near"):
        # The ninth live run (18 Oct 2026): shown the words, a writer still left a
        # listed item out of the middle of its quotation.
        mismatch += (". A quotation is one continuous stretch of its source, word for word, with nothing "
                     "left out in the middle: quote a shorter stretch rather than skip words.")
    return mismatch


class CorrectionUnavailable(ModelError):
    """This turn's draft corrections are spent. Never a reason to release it."""


class ReleaseWithheld(ModelError):
    """A terminal release boundary fired; draft correction cannot clear it."""


class TurnCalls:
    """Construct once per turn; pass this same object to every model stage.

    The model adapter owns bounded transport retries and the durable dollar cap.
    This owner bounds semantic/shape correction across activities and records
    their receipts. No nested stage receives a fresh allowance.
    """
    def __init__(self, model, *, corrections_used=0, reserve_correction=None):
        if (type(corrections_used) is not int or not 0 <= corrections_used <= ALLOWANCE
                or (reserve_correction is not None and not callable(reserve_correction))):
            raise ValueError("Correction ownership must come from a checked attempt")
        self.inner = model
        self.calls = []
        self.corrections_used = corrections_used
        self.reserve_correction = reserve_correction
        # Stages and sections run beside each other (18 and 19 Oct 2026): each thread keeps
        # its own last output, its own correction feedback and the scope it corrects within;
        # the allowances are taken under a lock.
        self._local, self._lock = threading.local(), threading.Lock()
        self._used = {}
        self.last_output = None
        self.terminal = False

    @property
    def last_output(self):
        """What this thread's latest call returned, for a correction of its own stage."""
        return getattr(self._local, "output", None)

    @last_output.setter
    def last_output(self, value):
        self._local.output = value

    @property
    def correction(self):
        """The correction feedback this thread's next call of the corrected stage carries."""
        return getattr(self._local, "correction", None)

    @correction.setter
    def correction(self, value):
        self._local.correction = value

    @contextmanager
    def scope(self, name, allowance=SECTION_ALLOWANCE):
        """Corrections made on this thread inside the block count against `name`'s own
        allowance (a section of the answer, the overview, a cross-check edit), not the
        turn's shared one. Every correction still counts towards the turn's durable total."""
        if not isinstance(name, str) or not name or type(allowance) is not int or allowance < 0:
            raise ValueError("A correction scope needs a name and an allowance")
        before = getattr(self._local, "scope", None)
        self._local.scope = (name, allowance)
        try:
            yield
        finally:
            self._local.scope = before

    def used(self, name):
        """How many corrections the named scope has made."""
        with self._lock:
            return self._used.get(name, 0)

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
            record = {}
            # Report an actual port receipt, including a quarantined completed
            # result. A requested tier or configured default is not a receipt
            # for a failed request whose provider/model remains unknown.
            result = receipt if isinstance(receipt, ModelResult) else getattr(
                receipt, "rejected_result", None)
            identity = result if isinstance(result, ModelResult) else None
            self._local.record = record
            self.calls.append(record)
            record.update({"operation": prompt.operation, "error": error,
                "provider": identity.provider if identity else None,
                "model": identity.model if identity else None,
                "tier": identity.tier.value if identity else None,
                "cached_tokens": usage.cached_tokens if usage else None,
                # Opaque adapter diagnostics, never authority for a decision or
                # cost calculation here. Absent metadata stays unestablished.
                "provider_usage": deepcopy(dict(usage.provider_extra)) if usage else None,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "tokens_in": usage.tokens_in if usage else None,
                "tokens_out": usage.tokens_out if usage else None,
                "cost_usd": usage.cost_usd if usage else None,
                "retries": getattr(receipt, "retries", 0),
                "correction": feedback is not None and feedback["operation"] == prompt.operation,
                "usage_confirmed": usage is not None,
                # Why code refused what this call returned, if it did (refused()).
                "refused": None})

    def refused(self, exc):
        """Note on this thread's latest call why code refused what it returned: the reason's
        own fixed words, up to the first quotation or detail, never the words refused (the
        first live run of 20 Oct 2026 could not tell why four reviews were refused)."""
        record = getattr(self._local, "record", None)
        if record is not None and record.get("refused") is None:
            record["refused"] = refusal_reason(exc)

    def correct(self, operation, activity, *, mismatch, rejected=None, asked_by_review=False, purpose=None):
        """Correct a typed owner-rejected draft; caller must revalidate the result.

        Operation-scoped feedback never enters an independent review call.
        It is untrusted draft data, not original evidence or an execution receipt.
        Within a scope (a section of the answer, the overview, a cross-check edit) any
        correction counts against that scope's allowance; outside one, against the turn's
        shared allowance of one. asked_by_review: the independent review's findings ask for
        it, so the writer is told plainly to ground the section (P25). purpose: what a
        correction asked for by another check is for (CONFLICT_PURPOSE).
        """
        if self.terminal:
            raise ReleaseWithheld("This turn's release scope is withheld")
        scope = getattr(self._local, "scope", None)
        name, allowance = scope if scope is not None else ("", SHARED_ALLOWANCE)
        with self._lock:
            if self._used.get(name, 0) >= allowance or self.corrections_used >= ALLOWANCE:
                raise CorrectionUnavailable("These draft corrections have been used")
            if not isinstance(operation, str) or not operation or not mismatch:
                raise ValueError("Correction requires an owning operation and precise mismatch")
            if self.reserve_correction is not None:
                # A lost acknowledgement conservatively spends the durable allowance.
                # Never dispatch a corrective call before that ownership is confirmed.
                self.reserve_correction()
            self.corrections_used += 1
            self._used[name] = self._used.get(name, 0) + 1
        self.correction = {"operation": operation,
            "purpose": (purpose if isinstance(purpose, str) and purpose else
                        GROUNDING_PURPOSE if asked_by_review is True else
                        "Correct the rejected draft using the complete original input and declared output contract."),
            "mismatch": deepcopy(mismatch), "rejected_draft": deepcopy(rejected),
            "provenance": "Untrusted rejected output and owner feedback; neither is original evidence."}
        try:
            return activity()
        finally:
            self.correction = None

    def checked(self, operation, activity):
        """A shape error may use the turn's first correction; outages/refusals never do."""
        try:
            return activity()
        except SchemaViolation as exc:
            self.refused(exc)
            return self.correct(operation, activity, mismatch=shape_mismatch(exc), rejected=self.last_output)

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
                "cached_tokens": sum(c["cached_tokens"] or 0 for c in self.calls),
                "draft_corrections": self.corrections_used}
