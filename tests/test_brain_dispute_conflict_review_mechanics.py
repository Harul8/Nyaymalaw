"""Existing dispute checks carry independently scripted conflict judgments.

These offline tests prove source presentation, role admission and local recovery.
The authored verdicts do not prove that a model distinguishes neutral events,
defences, proof gaps or genuine adverse conduct. That requires pinned-model live
evaluation against independently labelled original conversations.
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.dispute_verification import verify_disputes
from nm.brain.material import MaterialCandidate, PriorReference, addressed_sources
from nm.brain.record_review import SOURCE_SELECTION_CONTRACT, owned_source_portions
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage


class Model:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []
        self.claims = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return 100_000

    def claim_recovery(self, phase):
        self.claims.append(phase)
        return True

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        payload = json.loads(prompt.user)
        self.calls.append((prompt, payload, deepcopy(schema)))
        reply = next(self.replies)
        data = reply(payload) if callable(reply) else deepcopy(reply)
        return ModelResult(text=None, data=data, tier=tier, provider="offline", model="offline",
                           usage=Usage(0, 0, 0), latency_ms=0, completion=Completion.COMPLETE)


def candidate(words, *, statement=None, earlier=()):
    return MaterialCandidate(
        kind="dispute", quoted=words, statement=statement or words,
        relation="new", prior_references=tuple(earlier), matter_scope="current",
        basis="attributed", importance="relevant",
        why_material="The fixture author requests an independent conflict judgment.",
        label="Proposed issue", identification="identified", clarification="")


def treatments(earlier, latest, *, roles=None):
    """Attach explicit fixture source-purpose decisions to the original evidence."""
    roles = roles or {}
    _, current, prior = addressed_sources(earlier, latest)
    references = {
        **{key: vars(reference) for key, reference in prior.items()
           if reference.role == "advocate"},
        **{key: {"turn_id": "current", "role": "advocate", "quoted": words}
           for key, words in current.items()},
    }
    result = {}
    for identity, reference in references.items():
        role = roles.get(identity, "reported_matter_account")
        selections = ([{"start": 0, "end": len(reference["quoted"])}]
                      if role in ("reported_matter_account", "reported_party_position") else [])
        result[identity] = {
            **reference, "content_role": role,
            "reason": "The fixture owner explicitly declares the original source purpose.",
            "selection_contract": SOURCE_SELECTION_CONTRACT,
            "substantive_spans": owned_source_portions(reference, selections),
        }
    return result


def decision(identity, role, *, accept, source, words, account=True, operation=True):
    """Declare role independently; correct attribution alone does not imply a dispute."""
    return {
        "candidate_id": identity, "candidate_role": role,
        "operation_supported": operation, "verdict": "accept" if accept else "reject",
        "reason": "The fixture owner independently labels this candidate's conflict role.",
        "account_check": {
            "content_role": "reported_matter_account" if account else "examination_material",
            "supported": account, "introduces_legal_analysis": False,
            "source_checks": [{
                "source_id": source, "supplies_account_content": account,
                "supports_proposal": account,
                "support_spans": [{"start": 0, "end": len(words)}] if account else [],
                "reason": "The fixture owner independently declares this exact source support.",
            }],
            "reason": "The fixture account judgment is distinct from the conflict-role judgment.",
        },
        "target_checks": [],
    }


def check(model, candidates, latest, *, earlier=(), active=(), roles=None):
    audit, status = [], {}
    accepted = verify_disputes(
        model, candidates=tuple(candidates), earlier=earlier, latest=latest,
        active_disputes=active, audit=audit, review_status=status,
        source_treatments=treatments(earlier, latest, roles=roles))
    return accepted, audit, status


def test_dispatch_preserves_full_original_context_and_separates_nm_formulations():
    original = "The contractor has not returned the entrusted equipment."
    nm_words = "NM previously described the matter as a dispute about delivery."
    latest = "The contractor now denies holding the equipment."
    earlier = (Message("original", "advocate", original), Message("original", "nm", nm_words))
    proposed = candidate(latest, earlier=(PriorReference("original", "advocate", original),))
    active = ({"id": "original:material:1", "label": "Entrusted equipment",
               "statement": "NM's derived formulation", "source_turn_id": "original",
               "quoted": original, "matter_scope": "current"},)
    model = Model({"verdicts": [decision(
        "C1", "independent_dispute", accept=True, source="L1", words=latest)]})

    accepted, audit, status = check(model, [proposed], latest, earlier=earlier, active=active)

    assert accepted == (proposed,) and status["state"] == "checked"
    assert audit[0]["account_check"]["source_ids"] == ["L1"]
    assert len(model.calls) == 1 and model.claims == []
    prompt, payload, schema = model.calls[0]
    assert prompt.operation == "verify_disputes"
    assert payload["earlier_conversation"] == [
        {"turn_id": message.turn_id, "role": message.role,
         "source_spans": [{"id": f"P{index}S1", "text": message.text}]}
        for index, message in enumerate(earlier, start=1)]
    assert "".join(row["text"] for row in payload["latest_message_spans"]) == latest
    assert payload["active_disputes"] == [{**active[0], "record_role": "nm_interpretation"}]
    assert set(payload["candidates"][0]["allowed_account_source_ids"]) == {"L1", "P1S1"}
    assert "P2S1" not in payload["source_treatments"]
    branches = schema["properties"]["verdicts"]["items"]["anyOf"]
    roles_by_verdict = {
        branch["properties"]["verdict"]["enum"][0]:
        set(branch["properties"]["candidate_role"]["enum"])
        for branch in branches
    }
    assert roles_by_verdict["accept"] == {"independent_dispute"}
    assert roles_by_verdict["reject"] == {
            "independent_dispute", "supporting_premise", "evidence_gap_or_question",
            "duplicate", "unsupported"}


@pytest.mark.parametrize("words,role", [
    ("Our client handed the inventory to the appointed examiner on 8 June.",
     "supporting_premise"),
    ("The custodian says the return was authorised by the existing agreement.",
     "supporting_premise"),
    ("The inventory was moved and its significance is unclear.", "evidence_gap_or_question"),
    ("The receipt does not identify the person who received the inventory.",
     "evidence_gap_or_question"),
])
def test_scripted_non_dispute_role_preserves_account_support_and_valid_peer(words, role):
    adverse = "The warehouse operator refused to return the entrusted tools."
    proposed, peer = candidate(words), candidate(adverse)
    model = Model({"verdicts": [
        decision("C1", role, accept=False, source="L1", words=words),
        decision("C2", "independent_dispute", accept=True, source="L2", words=adverse),
    ]})

    accepted, audit, status = check(model, [proposed, peer], words + " " + adverse)

    assert accepted == (peer,)
    assert [row["verdict"] for row in audit] == ["reject", "accept"]
    assert audit[0]["candidate_role"] == role
    assert audit[0]["account_check"]["supported"] is True
    assert audit[0]["operation_supported"] is True
    assert status["accepted_items"] == status["rejected_items"] == 1
    assert status["unread_items"] == 0
    assert len(model.calls) == 1 and model.claims == []


def test_scripted_examination_rejection_does_not_discard_supported_adverse_peer():
    draft = "Examine this unadopted draft alleging that the claimant concealed the file."
    adverse = "The recipient separately refused the requested inspection."
    proposed, peer = candidate(draft), candidate(adverse)
    model = Model({"verdicts": [
        decision("C1", "evidence_gap_or_question", accept=False, source="L1", words=draft,
                 account=False, operation=False),
        decision("C2", "independent_dispute", accept=True, source="L2", words=adverse),
    ]})

    accepted, audit, status = check(model, [proposed, peer], draft + " " + adverse,
                                   roles={"L1": "examination_material"})

    assert accepted == (peer,) and status["state"] == "checked"
    assert audit[0]["account_check"]["content_role"] == "examination_material"
    assert audit[0]["account_check"]["source_checks"][0]["support_spans"] == []
    assert len(model.calls) == 1 and model.claims == []


def test_scripted_uncertain_adverse_act_and_independent_opposing_act_remain_admissible():
    uncertain = "Someone may be withholding the entrusted originals and we cannot identify them."
    opposing = "The carrier separately demands payment for goods it did not deliver."
    candidates = (candidate(uncertain), candidate(opposing))
    model = Model({"verdicts": [
        decision("C1", "independent_dispute", accept=True, source="L1", words=uncertain),
        decision("C2", "independent_dispute", accept=True, source="L2", words=opposing),
    ]})

    accepted, audit, status = check(model, candidates, uncertain + " " + opposing)

    assert accepted == candidates and status["accepted_items"] == 2
    assert all(row["account_check"]["supported"] for row in audit)
    assert len(model.calls) == 1 and model.claims == []


def test_scripted_duplicate_opposing_position_preserves_its_attributed_account():
    first = "The recipient denies receiving the entrusted originals."
    opposing = "The depositor says the recipient took the originals."
    candidates = (candidate(first), candidate(opposing))
    model = Model({"verdicts": [
        decision("C1", "independent_dispute", accept=True, source="L1", words=first),
        decision("C2", "duplicate", accept=False, source="L2", words=opposing),
    ]})

    accepted, audit, status = check(model, candidates, first + " " + opposing)

    assert accepted == candidates[:1] and status["state"] == "checked"
    assert audit[1]["candidate_role"] == "duplicate"
    assert audit[1]["account_check"]["supported"] is True
    assert audit[1]["account_check"]["source_checks"][0]["supplies_account_content"] is True
    assert len(model.calls) == 1 and model.claims == []


def test_scripted_distinct_contested_rights_can_share_the_same_reported_event():
    first = "The operator moved the entrusted equipment despite our refusal of consent."
    other_right = "The operator demands a disputed relocation charge for that move."
    candidates = (candidate(first), candidate(other_right))
    model = Model({"verdicts": [
        decision("C1", "independent_dispute", accept=True, source="L1", words=first),
        decision("C2", "independent_dispute", accept=True, source="L2", words=other_right),
    ]})

    accepted, audit, status = check(model, candidates, first + " " + other_right)

    assert accepted == candidates and status["accepted_items"] == 2
    assert all(row["account_check"]["supported"] for row in audit)
    assert len(model.calls) == 1 and model.claims == []


@pytest.mark.parametrize("exhaust", [False, True])
def test_overall_acceptance_cannot_override_non_dispute_role_or_lose_valid_peer(exhaust):
    neutral = "The inventory was delivered to the appointed examiner."
    adverse = "The warehouse refused to return the entrusted tools."
    proposed, peer = candidate(neutral), candidate(adverse)
    wrong = decision("C1", "supporting_premise", accept=True, source="L1", words=neutral)

    def correction(payload):
        assert [row["candidate_id"] for row in payload["candidates"]] == ["C1"]
        assert [row["candidate_id"] for row in payload["retained_candidate_context"]] == ["C2"]
        assert payload["retained_candidate_context"][0]["decision"]["verdict"] == "accept"
        assert "C1: accept conflicts with candidate_role=supporting_premise" in (
            payload["validation_issue"])
        assert "".join(row["text"] for row in payload["latest_message_spans"]) == latest
        final = deepcopy(wrong)
        if not exhaust:
            final["verdict"] = "reject"
        return {"verdicts": [final]}

    latest = neutral + " " + adverse
    model = Model({"verdicts": [wrong, decision(
        "C2", "independent_dispute", accept=True, source="L2", words=adverse)]}, correction)

    accepted, audit, status = check(model, [proposed, peer], latest)

    assert accepted == (peer,)
    assert audit[1]["verdict"] == "accept"
    assert len(model.calls) == 2
    assert model.claims == ["verify_disputes:correction"]
    assert status["accepted_items"] == 1
    if exhaust:
        assert status["state"] == "partial"
        assert status["unread_candidate_ids"] == ["C1"]
        assert audit[0]["verdict"] == "unassessed"
    else:
        assert status["state"] == "checked"
        assert status["unread_candidate_ids"] == []
        assert audit[0]["verdict"] == "reject"
