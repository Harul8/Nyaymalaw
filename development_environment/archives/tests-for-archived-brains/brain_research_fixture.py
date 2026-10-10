"""Offline legal research proposals follow the served owner and source contracts."""
from __future__ import annotations

import json
from copy import deepcopy

from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Usage
from tests.test_brain_continuation_service import PublicContinuationModel

PROVISION = (
    "Where an agreement contains a notice condition, that condition must be satisfied "
    "before exercising the agreed remedy."
)
JUDGMENT = (
    "Where the agreement required notice, the absence of notice prevented the claimed remedy "
    "in the circumstances considered by the court."
)


class Corpus:
    def __init__(self, *, revision="synthetic-corpus:1", state="ok", candidates=None):
        self.corpus_revision = revision
        self.state = state
        self.calls = []
        self.candidates = candidates

    def revision(self):
        return self.corpus_revision

    def search_subject(self, subject, queries, **kwargs):
        self.calls.append((deepcopy(subject), tuple(queries), deepcopy(kwargs)))
        candidates = self.candidates
        if candidates is None:
            candidates = [
                {"id": "A1", "kind": "provision", "title": "Synthetic Act",
                 "locator": "section 3", "text": PROVISION},
                {"id": "J1", "kind": "judgment", "title": "Synthetic Judgment",
                 "locator": "paragraph 12", "text": JUDGMENT},
            ]
        return {"state": self.state,
                "candidates": deepcopy(candidates) if self.state != "unavailable" else [],
                "diagnostics": [] if self.state == "ok" else [
                    "Synthetic corpus coverage is limited."]}

    search_dispute = search_subject


def finding(row, *, kind="condition", force="none", source_index=0):
    source = row["candidates"][source_index]
    return {"kind": kind, "label": "Check the cited notice condition" if kind == "gathering"
            else "Cited remedy condition",
            "need": source["text"],
            "why": "The cited passage explains this condition and its limit.",
            "force": force, "source_ids": [source["id"]], "material_ids": []}


def supported(candidate, *, verdict="supported"):
    return {"candidate_id": candidate["candidate_id"],
            "verdict": verdict, "reason": "The exact cited passage supports the conditional item.",
            "label_verdict": "faithful", "label_reason": "The label preserves the item's meaning.",
            "entailment_basis": "source_rule",
            "use_checks": {name: {
                "verdict": verdict, "reason": "The selected passage supports this conditional use.",
                "source_ids": [source["id"] for source in candidate["sources"]],
                "material_ids": candidate["material_ids"] if name == "application" else [],
            } for name in ("entailment", "application", "force")},
            "material_checks": [{"material_id": identifier, "verdict": "addresses",
                                 "reason": "The reported material concerns the selected point."}
                                for identifier in candidate["material_ids"]],
            "application_premises": [{
                "source_id": source["id"],
                "predicate_fragment_id": source["fragments"][0]["id"],
                "status": "unresolved", "account_source_ids": [],
                "preserved_condition": candidate["need"],
                "reason": "The condition is stated generally; factual applicability remains open.",
            } for source in candidate["sources"]],
            "source_checks": [{"source_id": source["id"], "verdict": "supported",
                               "assertion_owner": "legislative_text"
                               if source["kind"] == "provision" else "deciding_court",
                               "owner_label": source["title"],
                               "assertion_role": "legislative_text"
                               if source["kind"] == "provision" else "court_conclusion",
                               "assertion_statement": source["fragments"][0]["text"],
                               "context_statements": [],
                               "owner_fragment_id": source["fragments"][0]["id"],
                               "source_treatment": "adopted",
                               "treatment_fragment_id": source["fragments"][0]["id"],
                               "scope_status": "conditional",
                               "support_fragment_id": source["fragments"][0]["id"],
                               "scope_fragment_id": source["fragments"][0]["id"],
                               "reason": "The displayed claim preserves the passage's condition."}
                              for source in candidate["sources"]]}


def reviewed_retrieved_pool(payload, data, *, scripted_full_pool=False):
    """Add only an explicitly declared synthetic full-pool Judge decision.

    Existing coverage, including missing/malformed rows supplied by a negative
    test, stays authoritative. IDs bind the declared fixture judgment to the
    supplied scope; candidate support and row counts do not imply completeness.
    """
    result = deepcopy(data)
    if not scripted_full_pool or "subject_coverage" in result:
        return result
    if "coverage_subject_ids" in payload:
        result["subject_coverage"] = [{
            "subject_id": identity, "outcome": "complete", "missing_source_ids": [],
            "reason": ("Explicit synthetic Judge decision: the full supplied passage pool "
                       "supports no useful omitted finding for this subject."),
        } for identity in payload["coverage_subject_ids"]]
    return result


class ResearchModel(PublicContinuationModel):
    def __init__(self, routes, continuations, *, plans=None, readings=None, checks=None,
                 continuation_checks=None):
        super().__init__(routes, continuations, checks=continuation_checks)
        self.research_plans = plans
        self.research_readings = readings
        self.research_checks = checks
        self.research_prompts = []

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if prompt.operation not in (
                "decompose_disputes", "read_legal_requirements", "verify_legal_requirements"):
            return super().structured(prompt, schema, tier, max_tokens=max_tokens)
        payload = json.loads(prompt.user)
        self.calls.append((prompt.operation, payload))
        self.tiers.append(tier)
        self.research_prompts.append(prompt)
        if prompt.operation == "decompose_disputes":
            if self.research_plans is not None:
                data = self.research_plans(payload)
            else:
                data = {"plans": [{"subject_id": row["subject"]["id"],
                                   "queries": [{"text": text} for text in (
                                       row["subject"]["question"],
                                       "conditions governing the requested remedy",
                                       "judicial treatment of the relevant prerequisite")]}
                                  for row in payload["subjects"]]}
        elif prompt.operation == "read_legal_requirements":
            if self.research_readings is not None:
                data = self.research_readings(payload)
            else:
                data = {"readings": [{"subject_id": row["subject"]["id"],
                                      "findings": [finding(row)]}
                                     for row in payload["subjects"]]}
        elif self.research_checks is not None:
            data = self.research_checks(payload)
        else:
            data = reviewed_retrieved_pool(payload, {
                "decisions": [supported(candidate) for row in payload["subjects"]
                              for candidate in row["candidates"]]}, scripted_full_pool=True)
        return ModelResult(text=None, data=data, tier=tier, provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)
