"""Scoped admission protects dispute preview before any target can be retired."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import dispute_verification as disputes
from nm.brain.conversation import Conversation, Message
from nm.brain.material import MaterialCandidate, PriorReference, addressed_sources
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, build_mutation_authorities
from nm.brain.turn import _preview_disputes
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, SchemaViolation, Tier, Usage, require_schema
from tests.brain_reader_fixture import fresh_review_reply

FIRST = "The reported duty is disputed."
SECOND = "The record custody is contested."
REVIEW = "Reconcile the first dispute formulation."
NOTICE = "A separate refusal of notice is disputed."
OWNER = {"matter_id": "owned-matter", "advocate_id": "owned-advocate", "turn_id": "current",
         "offer_digest": "owned-offer"}
EARLIER = (Message("old", "advocate", FIRST + " " + SECOND),)
ACTIVE = (
    {"id": "dispute-a", "statement": FIRST, "quoted": FIRST, "source_turn_id": "old",
     "label": "Duty contest", "matter_scope": "current"},
    {"id": "dispute-b", "statement": SECOND, "quoted": SECOND, "source_turn_id": "old",
     "label": "Custody contest", "matter_scope": "current"},
)


class Model:
    """A full fabricated completed output; no helper invents acceptance fields."""
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema))
        data = deepcopy(next(self.responses))
        data = fresh_review_reply(json.loads(prompt.user), data)
        require_schema(data, schema)
        return ModelResult(text=None, data=data, tier=tier, provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


def candidate(words, *, target=None):
    return MaterialCandidate(
        kind="dispute", statement="Whether the reported duty is disputed." if target else NOTICE,
        quoted=words, relation="corrects" if target else "new",
        prior_references=(PriorReference("old", "advocate", FIRST),
                          PriorReference("old", "advocate", SECOND)) if target else (),
        matter_scope="current", basis="stated", importance="central",
        why_material="An independent contested account requires a practical conclusion.",
        label="Duty contest" if target else "Notice contest", identification="identified",
        related_dispute_ids=(target,) if target else ())


def sources(latest):
    _, current, prior = addressed_sources(EARLIER, latest)
    return {
        **{identity: {**vars(ref), "content_role": "reported_matter_account",
                      "reason": "An original attributed account is supplied."}
           for identity, ref in prior.items()},
        **{identity: {"turn_id": "current", "role": "advocate", "quoted": words,
                      "content_role": ("work_instruction" if words == REVIEW
                                       else "reported_matter_account"),
                      "reason": "Original framing distinguishes work authority and account."}
           for identity, words in current.items()},
    }


def scope(latest, *, allowed="dispute-a", whole=False):
    catalogue = sources(latest)
    ledger = build_mutation_authorities(
        owner=OWNER, expected_version=4,
        target_catalogue={row["id"]: row for row in ACTIVE}, source_catalogue=catalogue,
        proposals=[{
            "request_index": 0, "authority_kind": "interpretation_review",
            "authority_source_ids": ["L1"],
            "target_scope": "reviewed_whole" if whole else "exact",
            "target_ids": [] if whole else [allowed], "permitted_relations": ["corrects"],
        }], request_indices=(0,))
    return {"owner": OWNER, "mutation_authority_contract": AUTHORITY_CONTRACT,
            "mutation_authorities": ledger,
            "requests": [{"request_index": 0, "material_purposes": ["interpretation_review"]}]}


def verdict(identity, *, target=None, support="P1S1", peers=()):
    return {
        "candidate_id": identity, "candidate_role": "independent_dispute",
        "operation_supported": True, "verdict": "accept",
        "reason": "The fabricated independent Judge positively admits this exact proposal.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [support],
            "source_checks": [{"source_id": support, "supplies_account_content": True,
                               "supports_proposal": True,
                               "reason": "Original account supports the formulation."}],
            "reason": "This independently selected original account supplies content.",
        },
        "target_checks": [] if target is None else [{
            "target_id": target, "identity_relation": "same_underlying_account",
            "account_preserved": True, "required_peer_ids": list(peers),
            "reason": "The fabricated identity Judge certifies preservation of this target.",
        }],
    }


def assessment():
    return {"state": "complete", "missing_source_ids": [],
            "reason": "The fabricated independent reviewer considers the full account represented."}


def evaluate(model, candidates, latest, *, review_scope=None, review_state=None):
    audit, coverage, status = [], {}, {}
    retained = disputes.verify_disputes(
        model, candidates=candidates, earlier=EARLIER, latest=latest,
        active_disputes=ACTIVE, source_treatments=sources(latest),
        review_scope=scope(latest) if review_scope is None else review_scope,
        audit=audit, coverage=coverage, review_status=status, review_state=review_state)
    return retained, audit, coverage, status


def test_wrong_owned_target_positive_judge_is_withheld_before_dispute_preview():
    latest = REVIEW + " " + NOTICE
    wrong = candidate(REVIEW, target="dispute-b")
    peer = candidate(NOTICE)
    model = Model({"verdicts": [verdict("C1", target="dispute-b"),
                                verdict("C2", support="L2")], "coverage": assessment()})

    retained, audit, coverage, status = evaluate(model, (wrong, peer), latest)

    assert retained == (peer,)
    preview = _preview_disputes(
        Conversation(EARLIER, current_matter_id="owned-matter", open_disputes=ACTIVE),
        retained, "current", {})
    assert {row["id"] for row in ACTIVE} <= {row["id"] for row in preview}
    assert audit[0]["verdict"] == "reject"
    assert audit[0]["admission_issue"] == "mutation_scope"
    assert audit[0]["model_decision"]["verdict"] == "accept"
    assert status["withheld_items"] == 1
    assert status["unread_items"] == status["rejected_items"] == 0
    assert status["accepted_items"] == 1 and status["state"] == "checked"
    assert coverage["state"] == "unassessed"
    assert coverage["prior_assessment"]["state"] == "complete"
    assert "mutation scope" in coverage["validation_issue"]
    assert "required successors" not in coverage["validation_issue"]
    assert len(model.calls) == 1


def test_legitimate_exact_correction_attaches_binding_and_preserves_other_owned_dispute():
    latest = REVIEW
    proposed = candidate(REVIEW, target="dispute-a")
    model = Model({"verdicts": [verdict("C1", target="dispute-a")], "coverage": assessment()})

    retained, audit, coverage, status = evaluate(model, (proposed,), latest)

    assert retained == (proposed,)
    preview = _preview_disputes(
        Conversation(EARLIER, current_matter_id="owned-matter", open_disputes=ACTIVE),
        retained, "current", {})
    assert "dispute-b" in {row["id"] for row in preview}
    assert "dispute-a" not in {row["id"] for row in preview}
    certificate = audit[0]["mutation_authority"]
    assert certificate["target_ids"] == ["dispute-a"]
    assert certificate["supporting_source_ids"] == ["P1S1"]
    assert certificate["current_source_reference"]["quoted"] == REVIEW
    assert status["withheld_items"] == status["unread_items"] == 0
    assert coverage["state"] == "complete" and len(model.calls) == 1


def test_independent_review_cache_retains_positive_judgment_but_scope_is_reapplied():
    latest = REVIEW
    wrong = candidate(REVIEW, target="dispute-b")
    state = {}
    first = Model({"verdicts": [verdict("C1", target="dispute-b")], "coverage": assessment()})
    admitted, _, _, _ = evaluate(first, (wrong,), latest, review_state=state)
    assert admitted == ()
    second = Model({"verdicts": [], "coverage": assessment()})
    replayed, audit, coverage, status = evaluate(second, (wrong,), latest, review_state=state)
    assert replayed == () and audit[0]["admission_issue"] == "mutation_scope"
    assert audit[0]["model_decision"]["verdict"] == "accept"
    assert json.loads(second.calls[0][0].user)["candidates"] == []
    assert coverage["state"] == "unassessed" and status["unread_items"] == 0
    assert len(first.calls) == len(second.calls) == 1


def test_scope_failure_propagates_to_required_restoration_peers_only():
    first = candidate(REVIEW, target="dispute-a")
    other_words = "Explain the neighbouring formulation."
    second = replace(first, quoted=other_words, label="Second atomic restoration")
    peer = candidate(NOTICE)
    latest = REVIEW + " " + other_words + " " + NOTICE
    model = Model({"verdicts": [verdict("C1", target="dispute-a", peers=("C2",)),
                                verdict("C2", target="dispute-a"),
                                verdict("C3", support="L3")], "coverage": assessment()})

    retained, audit, coverage, status = evaluate(model, (first, second, peer), latest)

    assert retained == (peer,)
    assert audit[0]["admission_issue"] == "required_restoration_peer_unavailable"
    assert audit[1]["admission_issue"] == "mutation_scope"
    assert status["withheld_items"] == 2 and status["unread_items"] == 0
    assert "required successors" in coverage["validation_issue"]
    assert "mutation scope" in coverage["validation_issue"]
    assert len(model.calls) == 1


def test_scope_rejection_does_not_add_another_reviewer_correction_call():
    latest = REVIEW + " " + NOTICE
    wrong = candidate(REVIEW, target="dispute-b")
    peer = candidate(NOTICE)
    initial = {"verdicts": [verdict("C1", target="dispute-b")], "coverage": assessment()}
    repaired = {"verdicts": [verdict("C2", support="L2")], "coverage": assessment()}
    model = Model(initial, repaired)

    retained, audit, _, status = evaluate(model, (wrong, peer), latest)

    assert retained == (peer,) and audit[0]["admission_issue"] == "mutation_scope"
    assert len(model.calls) == 2 and status["unread_items"] == 0
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["C2"]


def test_genuinely_whole_authorized_review_keeps_semantic_identity_dependency_visible():
    latest = REVIEW
    wrong = candidate(REVIEW, target="dispute-b")
    model = Model({"verdicts": [verdict("C1", target="dispute-b")], "coverage": assessment()})
    retained, audit, _, _ = evaluate(
        model, (wrong,), latest, review_scope=scope(latest, whole=True))
    # Scope cannot disprove an incorrect identity judgment within a legitimately
    # broad authorization. This residual must not be reported as prevention.
    assert retained == (wrong,)
    assert audit[0]["mutation_authority"]["target_ids"] == ["dispute-b"]


def test_explicit_legacy_review_contract_remains_untracked_without_synthesised_binding():
    latest = REVIEW
    wrong = candidate(REVIEW, target="dispute-b")
    model = Model({"verdicts": [verdict("C1", target="dispute-b")], "coverage": assessment()})
    old_scope = {"requests": [{"request_index": 0, "material_purposes": ["interpretation_review"]}]}
    retained, audit, _, _ = evaluate(model, (wrong,), latest, review_scope=old_scope)
    assert retained == (wrong,) and "mutation_authority" not in audit[0]


def test_unreadable_scope_ledger_is_integrity_failure_not_a_unit_fallback():
    latest = REVIEW
    proposed = candidate(REVIEW, target="dispute-a")
    broken = scope(latest)
    broken["mutation_authorities"]["expected_version"] = 5
    model = Model({"verdicts": [verdict("C1", target="dispute-a")], "coverage": assessment()})
    with pytest.raises(SchemaViolation, match="changed after"):
        evaluate(model, (proposed,), latest, review_scope=broken)
