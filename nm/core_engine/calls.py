"""One turn owns model accounting and its bounded conditional draft corrections."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace

from nm.core_engine import estimates, reasoning, routing
from nm.shared.model_port import (ConfigurationError, ContextOverflow, ModelError, ModelResult, Prompt, SchemaViolation, TierUnavailable,
                                  estimate_tokens)

log = logging.getLogger(__name__)

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


class StopRequested(Exception):
    """The advocate stopped the answer (plan AN.42, D78): no further call is sent, and a call already sent finishes and is paid
    for. Not a model failure: no section is answered with a note for it, and the turn stops, keeping every step finished."""


class TurnCalls:
    """Construct once per turn; pass this same object to every model stage.

    The model adapter owns bounded transport retries and the durable dollar cap.
    This owner bounds semantic/shape correction across activities and records
    their receipts. No nested stage receives a fresh allowance.
    """
    def __init__(self, model, *, corrections_used=0, reserve_correction=None, effort=reasoning.DEFAULT_CHOICE, chosen=None,
                 stronger=None, stopping=None):
        if (type(corrections_used) is not int or not 0 <= corrections_used <= ALLOWANCE
                or (reserve_correction is not None and not callable(reserve_correction))):
            raise ValueError("Correction ownership must come from a checked attempt")
        if effort not in reasoning.CHOICES or (chosen is not None and not isinstance(chosen, dict)):
            raise ValueError("A turn's effort is one an advocate may choose")
        #: The effort the advocate chose for the turn, which moves every call of it (plan AN.33, D23), and what they chose - the
        #: model and the effort - for the turn's record (metrics).
        self.effort, self.chosen = effort, deepcopy(chosen)
        self.inner = model
        self.calls = []
        self.corrections_used = corrections_used
        self.reserve_correction = reserve_correction
        # Stages and sections run beside each other (18 and 19 Oct 2026): each thread keeps
        # its own last output, its own correction feedback and the scope it corrects within;
        # the allowances are taken under a lock.
        self._local, self._lock = threading.local(), threading.Lock()
        self._used = {}
        #: Each scope's corrections by the operation that made them: Auto counts only those routing.FAULTED names (D51).
        self._made = {}
        self.last_output = None
        self.terminal = False
        #: The turn's own estimates (plan AN.37, D41): "start", before its plan is known, and "planned", once it is (expect()).
        self.expected = {}
        #: Under Auto (plan AN.38, D47-D48): the stronger model a call moves to on evidence (routing.escalated), and what the turn
        #: has found that moves a step (found()). None: every call runs on the turn's own model, as before.
        self.stronger, self.evidence = stronger, set()
        #: Whether the advocate has stopped the answer (plan AN.42, D78): asked before every call is sent. None: never stopped.
        self.stopping = stopping

    def successor(self):
        """The calls of the same turn as it goes on after a steer (plan AN.42, D79): the record of its calls, the corrections made
        and its estimates carry on, shared; each scope's own corrections start afresh, since a steered piece is reviewed and
        repaired anew. This one sends no further call: whatever of the earlier work is still under way stops at its next call."""
        with self._lock:
            after = TurnCalls(self.inner, corrections_used=self.corrections_used, reserve_correction=self.reserve_correction,
                              effort=self.effort, chosen=self.chosen, stronger=self.stronger, stopping=self.stopping)
            after.calls, after.expected, after.evidence = self.calls, dict(self.expected), set(self.evidence)
            self.stopping = lambda: True
        return after

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

    def model_for(self, tier, port=None):
        """The model a call on tier is asked to run on (on port, by default the turn's own), or None where that is not
        established: a tier not configured, or a port that cannot say (a stand-in with no resolved_model, reached through the
        wrappers that pass the question on)."""
        resolve = getattr(self.inner if port is None else port, "resolved_model", None)
        if not callable(resolve):
            return None
        try:
            return resolve(tier)
        except (TierUnavailable, ConfigurationError, AttributeError):
            return None

    def found(self, name):
        """What the turn has found that moves a step under Auto (routing.ON_EVIDENCE)."""
        with self._lock:
            self.evidence.add(name)

    def _routed(self, operation):
        """Whether this thread's call of operation moves to the stronger model (plan AN.38, D48)."""
        if self.stronger is None:
            return False
        scope = getattr(self._local, "scope", None)
        with self._lock:
            corrections = 0 if scope is None else max(self._faulted(scope[0]), self._faulted(scope[0].split(".")[0]))
            earlier = sum(1 for call in self.calls if call.get("operation") == operation)
            evidence = frozenset(self.evidence)
        return routing.escalated(operation, corrections=corrections, earlier=earlier, evidence=evidence)

    def _faulted(self, name):
        """The corrections the named scope has made that count towards moving it under Auto (routing.FAULTED). Under the lock."""
        return sum(count for operation, count in self._made.get(name, {}).items() if operation in routing.FAULTED)

    def expect(self, stage, usd):
        """Keep the turn's estimate at a stage of it (plan AN.37, D41): "start" or "planned". Diagnostics only (D45)."""
        if stage in ("start", "planned") and isinstance(usd, float):
            with self._lock:
                self.expected[stage] = usd

    def structured(self, prompt, schema, tier, *, max_tokens):
        if self.terminal:
            raise ReleaseWithheld("This turn's release scope is withheld")
        if self.stopping is not None and self.stopping():
            raise StopRequested("The advocate stopped this answer")
        feedback = self.correction
        if feedback is not None and feedback["operation"] == prompt.operation:
            payload = json.loads(prompt.user)
            payload["correction"] = deepcopy(feedback)
            user = json.dumps(payload, ensure_ascii=False)
            # The correction joins the end: the call keeps its effort, and its shared material where that still leads.
            shared = prompt.cache_through if user[:prompt.cache_through] == prompt.user[:prompt.cache_through] else 0
            also = tuple(mark for mark in prompt.cache_also if shared and user[:mark] == prompt.user[:mark])
            prompt = Prompt(system=prompt.system, user=user, operation=prompt.operation, effort=prompt.effort,
                            cache_through=shared, cache_also=also)
        own = prompt.effort
        if self.effort != reasoning.DEFAULT_CHOICE:
            # Plan AN.33 (D23): the effort the advocate chose moves the call's own level; what it may write is its room at every
            # effort (D27).
            prompt = replace(prompt, effort=reasoning.chosen(prompt.effort, self.effort))
        # D27 (plan AN.33): what the call may write is the room its whole input - a correction joined to it included - leaves.
        sent = estimate_tokens((prompt.system or "") + prompt.user + json.dumps(schema))
        left = self.context_budget(tier) - sent
        if left < min(max_tokens, reasoning.LEAST_ROOM):
            raise ContextOverflow("The complete stage input and correction exceed the context budget")
        max_tokens = min(max_tokens, left)
        # Plan AN.38 (D48): under Auto, the call moves to the stronger model where the turn's own evidence says so.
        routed = self._routed(prompt.operation)
        target = self.stronger if routed else self.inner
        # Plan AN.37 (D41, D45): what this call is expected to cost, worked out before it is sent and kept beside what it cost.
        model = self.model_for(tier, port=target)
        expected = None if model is None else estimates.call_usd(model, sent, prompt.operation, own=own, sent=prompt.effort)
        self.last_output = None
        started, receipt, error = time.monotonic(), None, None
        try:
            receipt = target.structured(prompt, schema, tier, max_tokens=max_tokens)
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
                "refused": None,
                # Plan AN.37 (D41): the level the call was sent at, and what it was expected to cost.
                "effort": prompt.effort, "estimated_usd": expected,
                # Plan AN.38 (D48): whether Auto moved it to the stronger model.
                **({"routed": True} if routed else {})})
            if estimates.passed(record["cost_usd"], expected, estimates.OVER_CALL):
                # D45: recorded for diagnostics; the call and the turn go on as they would.
                log.warning("A call cost more than %s times its estimate: %s, %.4f against %.4f", estimates.OVER_CALL,
                            prompt.operation, record["cost_usd"], expected)

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
        self.spend(operation, mismatch=mismatch)
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

    def spend(self, operation, *, mismatch=True):
        """Take one correction from the current scope's allowance (outside a scope, the turn's
        shared one) and the turn's durable total. correct() spends one so; a second look at the
        pieces code or the review found at fault (plan AN.28, D2) spends one so too, carrying its
        own feedback rather than the correction correct() adds to its operation's next call."""
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
            made = self._made.setdefault(name, {})
            made[operation] = made.get(operation, 0) + 1

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

    def estimate(self):
        """What the turn was expected to cost against what it has spent (plan AN.37, D41 and D45): the sum of its calls'
        estimates, its own estimates at its start and once planned, what it has spent, and which estimates spending passed by
        OVER_TURN times. Diagnostics only."""
        with self._lock:
            calls, expected = list(self.calls), dict(self.expected)
        spent = sum(call["cost_usd"] or 0 for call in calls)
        made = [call["estimated_usd"] for call in calls if call.get("estimated_usd") is not None]
        kept = {"calls_usd": round(sum(made), 6) if made else None, "calls_estimated": len(made),
                **{f"{stage}_usd": usd for stage, usd in expected.items()}, "spent_usd": round(spent, 6)}
        kept["passed"] = [name for name in ("calls", *expected) if estimates.passed(spent, kept[f"{name}_usd"],
                                                                                     estimates.OVER_TURN)]
        return kept

    def metrics(self):
        return {"llm_calls": len(self.calls), "calls": deepcopy(self.calls),
                "reported_transport_retries": sum(c["retries"] for c in self.calls),
                "usage_unconfirmed_calls": sum(not c["usage_confirmed"] for c in self.calls),
                "cost_usd": sum(c["cost_usd"] or 0 for c in self.calls),
                "tokens_in": sum(c["tokens_in"] or 0 for c in self.calls),
                "tokens_out": sum(c["tokens_out"] or 0 for c in self.calls),
                "cached_tokens": sum(c["cached_tokens"] or 0 for c in self.calls),
                "draft_corrections": self.corrections_used,
                # Plan AN.37 (D41, D45): the turn's estimates against what it has spent.
                "estimate": self.estimate(),
                # Plan AN.33 (D23): the model and the effort the advocate chose for the turn, where they chose them.
                **({"chosen": deepcopy(self.chosen)} if self.chosen is not None else {})}
