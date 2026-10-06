"""Actual verifier resource proofs preserve sources and scope enforcement.

The fabricated providers return complete independently authored judgments.
These tests do not replace validation, mutate production state, or call a model.
"""
import json
from copy import deepcopy
from dataclasses import dataclass

import pytest

from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import MaterialCandidate, PriorReference, addressed_sources
from nm.brain.material_verification import verify_material_grounding
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, build_mutation_authorities
from nm.brain.record_review import derived_record
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import (
    ModelResult,
    SchemaViolation,
    Tier,
    Usage,
    estimate_tokens,
    require_schema,
)

OWNER = {"matter_id": "resource-matter", "advocate_id": "resource-advocate",
         "turn_id": "resource-current", "offer_digest": "resource-original-offer"}
LATEST = "Reconcile the first saved account against the original advocate words."


class ScriptedJudge:
    """One complete object passes the real strict schema and admission logic."""

    def __init__(self, response, *, budget=250_000):
        self.response = response
        self.budget = budget
        self.calls = []
        self.reservations = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        self.reservations.append(self.budget)
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        assert tier is Tier.JUDGE
        assert self.reservations, "The real owner must reserve context before dispatch."
        assert estimate_tokens(prompt.system + prompt.user) + max_tokens <= self.budget
        data = deepcopy(self.response)
        require_schema(data, schema)
        self.calls.append((prompt, schema, max_tokens))
        return ModelResult(
            text=None, data=data, tier=tier, provider="offline", model="scripted",
            usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


@dataclass(frozen=True)
class AccountFixture:
    kind: str
    earlier: tuple
    targets: tuple
    sources: dict
    scope: dict


def fixture(kind):
    """Forty-eight attributed records; every saved advocate and NM word remains."""
    messages = []
    targets = []
    for group in range(6):
        utterances = []
        for offset in range(8):
            index = group * 8 + offset
            words = (
                f"The advocate reports that participant {index} described event {index} "
                "as provisional and attributed to another participant, with timing "
                "still uncertain and independent verification outstanding.")
            utterances.append(words)
            targets.append({
                "id": f"owned-{index}", "source_turn_id": f"original-{group}",
                "quoted": words, "statement": words, "basis": "attributed",
                "kind": kind, "matter_scope": "current",
                **({"label": f"Contested account {index}"} if kind == "dispute" else {}),
            })
        messages.append(Message(f"original-{group}", "advocate", " ".join(utterances)))
        messages.append(Message(
            f"original-{group}", "nm",
            "NM's earlier analysis proposed an interpretation with an unresolved "
            "distinction; this wording is derived analysis rather than an original "
            "account and cannot independently substantiate the underlying event."))
    earlier = tuple(messages)
    _, current, prior = addressed_sources(earlier, LATEST)
    sources = {
        identity: {**vars(reference), "content_role": "reported_matter_account",
                   "reason": "This is the complete original attributed advocate account."}
        for identity, reference in prior.items() if reference.role == "advocate"
    }
    sources.update({
        identity: {"turn_id": OWNER["turn_id"], "role": "advocate", "quoted": words,
                   "content_role": "work_instruction",
                   "reason": "Review permission is distinct from factual account support."}
        for identity, words in current.items()
    })
    ledger = build_mutation_authorities(
        owner=OWNER, expected_version=6,
        target_catalogue={row["id"]: row for row in targets}, source_catalogue=sources,
        request_indices=(0,), proposals=[{
            "request_index": 0, "authority_kind": "interpretation_review",
            "authority_source_ids": ["L1"], "target_scope": "exact",
            "target_ids": ["owned-0"], "permitted_relations": ["corrects"],
        }])
    scope = {
        "owner": OWNER, "mutation_authority_contract": AUTHORITY_CONTRACT,
        "mutation_authorities": ledger,
        "requests": [{"request_index": 0, "record_requirement": {
            "kind": "review", "target_ids": ["owned-0"], "operation": "none",
            "success_condition": "Review the selected account against original words."}}],
        "additional_semantic_scope": {"preserve_uncertainty": True},
    }
    return AccountFixture(kind, earlier, tuple(targets), sources, scope)


def proposal_and_verdict(account, *, wrong_target=False):
    target = account.targets[1 if wrong_target else 0]
    source = next(identity for identity, row in account.sources.items()
                  if row["turn_id"] == target["source_turn_id"]
                  and row["quoted"] == target["quoted"])
    candidate = MaterialCandidate(
        kind=account.kind, statement=target["statement"], quoted=LATEST,
        relation="corrects", prior_references=(PriorReference(
            target["source_turn_id"], "advocate", target["quoted"]),),
        matter_scope="current", basis="attributed", importance="central",
        why_material="The requested review preserves the original attribution and limits.",
        placement="matter" if account.kind != "dispute" else "",
        label=target.get("label", ""), identification="identified",
        related_material_ids=(target["id"],) if account.kind != "dispute" else (),
        related_dispute_ids=(target["id"],) if account.kind == "dispute" else ())
    verdict = {
        "candidate_id": "C1" if account.kind == "dispute" else "D1",
        "verdict": "accept", "operation_supported": True,
        "reason": "The fabricated independent judgment positively accepts this proposal.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [source],
            "source_checks": [{
                "source_id": source, "supplies_account_content": True,
                "supports_proposal": True,
                "reason": "The selected exact original account supports this formulation."}],
            "reason": "Original account supplies content; review instruction supplies permission.",
        },
        "target_checks": [{
            "target_id": target["id"], "identity_relation": "same_underlying_account",
            "account_preserved": True, "required_peer_ids": [],
            "reason": "The scripted judgment certifies this exact selected target."}],
    }
    if account.kind == "dispute":
        verdict["candidate_role"] = "independent_dispute"
    response = {"verdicts": [verdict], "coverage": {
        "state": "complete", "missing_source_ids": [],
        "reason": "The fabricated independent judgment assesses all original source account."}}
    return candidate, response


def evaluate(account, model, candidate):
    coverage = {}
    audit = []
    kwargs = dict(
        candidates=(candidate,), earlier=account.earlier, latest=LATEST,
        source_treatments=account.sources, review_scope=account.scope, coverage=coverage)
    if account.kind == "dispute":
        retained = verify_disputes(
            model, active_disputes=account.targets, audit=audit, review_status={}, **kwargs)
    else:
        result = verify_material_grounding(
            model, opening=OpeningCandidate(False, "", ""), current_matter_id=OWNER["matter_id"],
            prior_material=account.targets, active_material=account.targets, **kwargs)
        retained = result.details
        audit = list(result.withheld_proposals)
    return retained, coverage, audit


def assert_prompt_preservation(account, model):
    assert len(model.calls) == len(model.reservations) == 1
    prompt, _, output_limit = model.calls[0]
    payload = json.loads(prompt.user)
    original, _, _ = addressed_sources(account.earlier, LATEST)
    assert payload["earlier_conversation"] == original["earlier_conversation"]
    assert payload["latest_message_spans"] == original["latest_message_spans"]
    assert payload["source_treatments"] == account.sources
    assert payload["coverage_source_ids"] == list(account.sources)
    assert payload["active_disputes" if account.kind == "dispute" else "active_material"] == [
        derived_record(row) for row in account.targets]
    model_scope = payload["review_scope"]
    if "mutation_scopes" in model_scope:
        assert "mutation_authorities" not in model_scope
        presented_permissions = model_scope["mutation_scopes"]
    else:
        ledger = model_scope["mutation_authorities"]
        assert set(ledger) == {"contract", "owner", "expected_version", "authorities"}
        assert {key: ledger[key] for key in ("contract", "owner", "expected_version")} == {
            key: account.scope["mutation_authorities"][key]
            for key in ("contract", "owner", "expected_version")}
        presented_permissions = ledger["authorities"]
    assert presented_permissions == account.scope["mutation_authorities"]["authorities"]
    assert {key: value for key, value in model_scope.items()
            if key not in ("mutation_scopes", "mutation_authorities")} == {
        key: value for key, value in account.scope.items() if key != "mutation_authorities"}
    # Compare before the owner's output reservation, using the identical context estimator.
    hypothetical = {**payload, "review_scope": account.scope}
    full_user = json.dumps(hypothetical, ensure_ascii=False, separators=(",", ":"))
    lean_tokens = estimate_tokens(prompt.system + prompt.user)
    full_tokens = estimate_tokens(prompt.system + full_user)
    assert full_tokens - lean_tokens > 1_000
    assert full_tokens > lean_tokens * 1.25
    return lean_tokens, full_tokens, output_limit


@pytest.mark.parametrize("kind", ["event", "dispute"])
@pytest.mark.parametrize("wrong_target", [False, True])
def test_verifier_presents_complete_sources_with_lean_permissions_and_full_server_binding(
        kind, wrong_target):
    account = fixture(kind)
    initial_scope = deepcopy(account.scope)
    candidate, response = proposal_and_verdict(account, wrong_target=wrong_target)
    model = ScriptedJudge(response)
    retained, coverage, audit = evaluate(account, model, candidate)
    assert_prompt_preservation(account, model)
    assert account.scope == initial_scope
    assert coverage["review_scope"] == initial_scope
    assert "mutation_authorities" in coverage["review_scope"]
    if wrong_target:
        assert retained == ()
        assert audit[0]["admission_issue"] == "mutation_scope"
        assert audit[0]["model_decision"]["verdict"] == "accept"
        assert coverage["state"] == "unassessed"
    else:
        assert retained == (candidate,)
        assert coverage["state"] == "complete"


@pytest.mark.parametrize("kind", ["event", "dispute"])
def test_redundant_ledger_does_not_spend_context_needed_for_original_sources(kind):
    account = fixture(kind)
    candidate, response = proposal_and_verdict(account)
    baseline = ScriptedJudge(response)
    retained, _, _ = evaluate(account, baseline, candidate)
    assert retained == (candidate,)
    lean_tokens, full_tokens, output_limit = assert_prompt_preservation(account, baseline)
    budget = lean_tokens + output_limit + 32
    assert full_tokens + output_limit > budget
    budgeted = ScriptedJudge(response, budget=budget)
    retained, coverage, _ = evaluate(account, budgeted, candidate)
    assert retained == (candidate,)
    assert coverage["state"] == "complete"
    assert_prompt_preservation(account, budgeted)


@pytest.mark.parametrize("kind", ["event", "dispute"])
def test_corrupt_durable_permission_dependency_stops_before_model_dispatch(kind):
    account = fixture(kind)
    candidate, response = proposal_and_verdict(account)
    account.scope["mutation_authorities"]["target_catalogue"]["owned-1"][
        "statement"] = "A changed dependency must not become a new permission ledger."
    model = ScriptedJudge(response)
    with pytest.raises(SchemaViolation, match="changed after"):
        evaluate(account, model, candidate)
    assert model.calls == []
