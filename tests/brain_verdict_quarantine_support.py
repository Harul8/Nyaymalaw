"""Raw paired envelopes for strict and permissive independent-review boundaries."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

from nm.brain import dispute_verification, material_verification
from nm.brain.conversation import OpeningCandidate
from nm.brain.material import MaterialCandidate, addressed_sources
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema

FIRST = "The custodian retained the signed original."
SECOND = "The courier delivered the duplicate copy."
WORDS = FIRST + " " + SECOND
SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["account_capture"]}]}


def proposals(kind):
    candidates = tuple(MaterialCandidate(
        kind="event", statement=words, quoted=words, relation="new", prior_references=(),
        matter_scope="current", basis="stated", importance="relevant",
        why_material="The supplied account bears on the authorised review.", placement="matter",
    ) for words in (FIRST, SECOND))
    if kind == "dispute":
        candidates = tuple(replace(row, kind="dispute", label="Reported account",
                                   identification="identified", placement="") for row in candidates)
    return candidates


def source_treatments():
    _, current, _ = addressed_sources((), WORDS)
    return {identity: {
        "turn_id": "latest", "role": "advocate", "quoted": words,
        "content_role": "reported_matter_account",
        "reason": "Original advocate evidence is reported account content.",
    } for identity, words in current.items()}


def envelope(payload):
    rows = []
    for candidate in payload["candidates"]:
        sources = candidate["allowed_account_source_ids"][:1]
        row = {
            "candidate_id": candidate["candidate_id"], "verdict": "accept",
            "operation_supported": True, "reason": "The whole original account supports this unit.",
            "account_check": {
                "content_role": "reported_matter_account", "supported": True,
                "introduces_legal_analysis": False, "source_ids": sources,
                "source_checks": [{
                    "source_id": source, "supplies_account_content": True,
                    "supports_proposal": True,
                    "reason": "The attributed original words support the proposition.",
                } for source in sources],
                "reason": "The entire proposed account was examined in its original context.",
            }, "target_checks": [],
        }
        if "label" in candidate:
            row["candidate_role"] = "independent_dispute"
        rows.append(row)
    result = {"verdicts": rows}
    if "review_scope" in payload:
        result["coverage"] = {
            "state": "complete", "missing_source_ids": [],
            "reason": "The full original account is represented by checked units.",
        }
    return result


class Judge:
    def __init__(self, outputs, *, strict=True, quarantine=True, tier=Tier.JUDGE,
                 recovery=True, mismatch=False, downgraded_from=None):
        self.outputs = iter(outputs)
        self.calls = []
        self.quarantined = []
        self.strict, self.quarantine, self.tier = strict, quarantine, tier
        self.recovery, self.mismatch = recovery, mismatch
        self.downgraded_from = downgraded_from

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def claim_recovery(self, phase):
        return self.recovery

    def structured(self, prompt, schema, tier, *, max_tokens):
        payload = json.loads(prompt.user)
        output = next(self.outputs)
        if isinstance(output, Exception):
            self.calls.append({"payload": payload, "failure": type(output).__name__,
                               "schema": schema})
            raise output
        data = output(payload) if callable(output) else deepcopy(output)
        self.calls.append({"payload": payload, "output": deepcopy(data), "schema": schema})
        result = ModelResult(
            text=None, data=data, tier=self.tier, provider="offline",
            model="fabricated-independent-review", usage=Usage(31, 23, 0.001),
            latency_ms=7, retries=1, completion=Completion.COMPLETE,
            downgraded_from=self.downgraded_from,
        )
        if self.strict:
            try:
                require_schema(data, schema)
            except SchemaViolation as exc:
                if not self.quarantine:
                    raise
                error = SchemaViolation(str(exc), rejected_result=result)
                self.quarantined.append(error)
                if self.mismatch:
                    error.usage = Usage(99, 23, 0.001)
                raise error from exc
        return result


def review(kind, model, *, candidates=None, requested=True, sinks=True):
    coverage, status, audit = {}, {}, []
    candidates = proposals(kind) if candidates is None else candidates
    arguments = dict(
        candidates=candidates, earlier=(), latest=WORDS, active_disputes=(),
        source_treatments=source_treatments(), review_scope=SCOPE if requested else None,
        coverage=coverage if sinks else None,
    )
    if kind == "dispute":
        accepted = dispute_verification.verify_disputes(
            model, **arguments, audit=audit if sinks else None,
            review_status=status if sinks else None,
        )
        unread = status.get("unread_candidate_ids", [])
    else:
        result = material_verification.verify_material_grounding(
            model, **arguments, opening=OpeningCandidate(False, "", ""),
        )
        accepted = result.details
        unread = [row["candidate_id"] for row in result.unread_proposals]
    return {"accepted": accepted, "unread": unread, "coverage": coverage, "status": status}


def broken_sibling(payload, defect="missing_account"):
    output = envelope(payload)
    sibling = next(row for row in output["verdicts"] if row["candidate_id"].endswith("2"))
    if defect == "missing_account":
        del sibling["account_check"]
    elif defect == "foreign_source":
        sibling["account_check"]["source_ids"] = ["unowned"]
        sibling["account_check"]["source_checks"][0]["source_id"] = "unowned"
    elif defect == "wrong_boolean":
        sibling["operation_supported"] = "true"
    else:
        sibling["account_check"]["supported"] = False
    return output


class LedgerJudge(Judge):
    """Reservation attribution is separate from the consumed recovery bound."""

    def __init__(self, outputs, *, overflow_on_correction=False):
        super().__init__(outputs)
        self.pending = None
        self.reservations = []
        self.abandoned = []
        self.dispatched = []
        self.budget_checks = 0
        self.overflow_on_correction = overflow_on_correction

    def claim_recovery(self, phase):
        assert self.pending is None
        self.reservations.append(phase)
        self.pending = phase
        return True

    def abandon_recovery(self, phase):
        assert self.pending == phase
        self.abandoned.append(phase)
        self.pending = None

    def context_budget(self, tier):
        self.budget_checks += 1
        if self.overflow_on_correction and self.budget_checks == 2:
            return 0
        return super().context_budget(tier)

    def structured(self, prompt, schema, tier, *, max_tokens):
        self.dispatched.append((prompt.operation, self.pending))
        self.pending = None
        return super().structured(prompt, schema, tier, max_tokens=max_tokens)
