"""Faithful legal text survives width checks; meaning and owned evidence still matter."""

import json
from copy import deepcopy

import pytest

from nm.brain.conversation import Message
from nm.brain.legal_requirements import (
    FINDING_USE_CHECKS,
    RESEARCH_VERIFICATION,
    _application_premises_valid,
    _passage_fragments,
    _statement_valid,
    finding_verification_valid,
    source_verification_valid,
    verify_findings,
)
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, Usage

OWNER_LABEL = (
    "The Consolidated Agreement, Receipt, Notice, Service, Delivery, Withdrawal, "
    "Authority, Consent, Timing, Territorial Scope, Recipient Identity and "
    "Document Authentication Conditions Act 2026"
)
LIVE_PASSAGE = (
    OWNER_LABEL + ": Where the agreement requires written notice, the recipient must "
    "receive that notice before the agreed deadline. Service must identify the "
    "agreement, recipient and act concerned, and must comply with its stated mode "
    "of delivery. A notice withdrawn before receipt does not satisfy this rule. "
    "The obligation remains conditional on the agreement's actual scope and the "
    "relevant period; possession of a document alone does not establish its "
    "contents, signature, delivery, receipt or continued effect."
)
PRESERVED_CONDITION = (
    "If the agreement's actual terms impose this notice obligation, enquire into "
    "the original executed document and any later variation before treating the "
    "requirement as applicable. Preserve the distinction between the reported "
    "agreement and verified contents: the document's mere possession does not "
    "establish its signature, authentication or continuing effect. Check which "
    "recipient, transaction, act and period the obligation covers, retaining any "
    "express limitation or exception in those terms. Identify the contractual "
    "deadline without assuming that a date recorded elsewhere was agreed by the "
    "same parties for this act. Enquire into the permitted service method, the "
    "actual delivery and the recipient's receipt, preserving any uncertainty "
    "between dispatch and receipt. Check whether the notice identified the same "
    "agreement and act, and whether withdrawal before receipt displaced the "
    "notice relied on. Keep each unestablished matter conditional and distinguish "
    "reported account from proof. Treat this enquiry as a means to determine the "
    "rule's application, without asserting that the account has already satisfied "
    "the source's conditions or that the proposed work is complete."
)
LONG_EXACT_EXCERPT = (
    "The recipient, agreement, act and relevant period must each be identified "
    "from the source record, with any limitation or exception preserved. "
) * 8
SHORT_EXACT_EXCERPT = "Where the agreement requires written notice"
SAVED_PASSAGE = SHORT_EXACT_EXCERPT + ", the recipient must receive it. " + LONG_EXACT_EXCERPT
SUBJECT = {
    "id": "width-subject",
    "kind": "request",
    "owner_id": "width-owner",
    "scope": "none",
    "purpose": "requested_work",
    "question": "Explain the supplied rule and its limits",
    "record_ids": [],
}
CONVERSATION = (
    Message("request", "advocate", "Explain the supplied rule and preserve its limits."),
)


def _statement():
    return {
        "assertion_owner": "legislative_text",
        "assertion_role": "legislative_text",
        "assertion_statement": (
            "The recipient must receive the written notice under the stated conditions."
        ),
        "owner_label": "Synthetic Conditions Act",
        "source_treatment": "adopted",
        "support_excerpt": SHORT_EXACT_EXCERPT,
        "owner_excerpt": SHORT_EXACT_EXCERPT,
        "treatment_excerpt": SHORT_EXACT_EXCERPT,
    }


def _saved_source(contract=RESEARCH_VERIFICATION):
    return {
        "id": "source-one",
        "kind": "provision",
        "title": "Synthetic Conditions Act",
        "locator": "section 1",
        "text": SAVED_PASSAGE,
        "verification": {
            **_statement(),
            "contract": contract,
            "context_statements": [],
            "scope_status": "conditional",
            "scope_excerpt": SHORT_EXACT_EXCERPT,
            "reason": "Synthetic source-use attestation for mechanical validation.",
        },
    }


def _saved_finding(*, predicate=SHORT_EXACT_EXCERPT, condition=PRESERVED_CONDITION):
    source = _saved_source()
    source["verification"]["scope_excerpt"] = predicate
    return {
        "kind": "condition",
        "label": "Determine conditional notice application",
        "need": condition,
        "why": "The source's limiting predicates remain unresolved.",
        "force": "none",
        "source_ids": [source["id"]],
        "material_ids": [],
        "record_status": "not_mentioned",
        "sources": [source],
        "use_verification": {
            "contract": RESEARCH_VERIFICATION,
            "entailment_basis": "source_rule",
            "checks": {
                aspect: {
                    "verdict": "supported",
                    "reason": "Synthetic mechanical use decision.",
                    "source_ids": [source["id"]],
                    "material_ids": [],
                }
                for aspect in FINDING_USE_CHECKS
            },
            "application_premises": [
                {
                    "source_id": source["id"],
                    "predicate_excerpt": predicate,
                    "status": "unresolved",
                    "account_references": [],
                    "preserved_condition": condition,
                    "reason": "Application is unresolved; the qualification remains explicit.",
                }
            ],
        },
    }


class OfflineJudge:
    """Return explicit frozen decisions; never derive or truncate assertions."""

    def __init__(self, decision, *, budget=100_000):
        self.decision = deepcopy(decision)
        self.budget = budget
        self.calls = []

    def context_budget(self, tier):
        assert tier is Tier.JUDGE
        return self.budget

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        self.calls.append((prompt, schema, tier, max_tokens))
        assert prompt.operation == "verify_legal_requirements"
        return ModelResult(
            text=None,
            data={"decisions": [deepcopy(self.decision)]},
            tier=tier,
            provider="offline",
            model="explicit-width-contract-fixture",
            usage=Usage(0, 0, 0),
            latency_ms=0,
            completion=Completion.COMPLETE,
        )


def _live_case():
    assert len(OWNER_LABEL) > 160
    assert 500 < len(LIVE_PASSAGE) <= 700
    assert len(PRESERVED_CONDITION) > 1000
    source = {
        "id": "source-one",
        "kind": "provision",
        "title": OWNER_LABEL,
        "locator": "section 1",
        "text": LIVE_PASSAGE,
    }
    proposal = {
        "kind": "condition",
        "label": "Determine conditional notice application",
        "need": PRESERVED_CONDITION,
        "why": "Retain every unresolved application limit.",
        "force": "none",
        "source_ids": [source["id"]],
        "material_ids": [],
        "sources": [source],
    }
    decision = {
        "candidate_id": "r1",
        "verdict": "supported",
        "label_verdict": "faithful",
        "label_reason": "Synthetic heading validation.",
        "entailment_basis": "source_rule",
        "reason": "Synthetic acceptance exercises width and ownership contracts only.",
        "material_checks": [],
        "source_checks": [
            {
                "source_id": source["id"],
                "verdict": "supported",
                "assertion_owner": "legislative_text",
                "assertion_role": "legislative_text",
                "assertion_statement": LIVE_PASSAGE,
                "owner_label": OWNER_LABEL,
                "source_treatment": "adopted",
                "context_statements": [],
                "support_fragment_id": "f1",
                "owner_fragment_id": "f1",
                "treatment_fragment_id": "f1",
                "scope_fragment_id": "f1",
                "scope_status": "conditional",
                "reason": "Synthetic same-source use attestation.",
            }
        ],
        "use_checks": {
            aspect: {
                "verdict": "supported",
                "reason": "Synthetic use attestation.",
                "source_ids": [source["id"]],
                "material_ids": [],
            }
            for aspect in FINDING_USE_CHECKS
        },
        "application_premises": [
            {
                "source_id": source["id"],
                "predicate_fragment_id": "f1",
                "status": "unresolved",
                "account_source_ids": [],
                "preserved_condition": PRESERVED_CONDITION,
                "reason": "The entire existing proposal qualification is retained.",
            }
        ],
    }
    return proposal, decision


def _verify(proposal, model):
    return verify_findings(
        model,
        subjects=(SUBJECT,),
        material_by_subject={SUBJECT["id"]: []},
        proposed={SUBJECT["id"]: [proposal]},
        conversation=CONVERSATION,
        source_treatments={},
    )


@pytest.mark.parametrize(
    "field,words",
    [
        ("assertion_statement", LIVE_PASSAGE),
        ("owner_label", OWNER_LABEL),
    ],
)
def test_meaningful_statement_and_owner_above_old_width_are_structurally_valid(field, words):
    source = _saved_source()
    statement = _statement()
    statement[field] = words
    if field == "assertion_statement":
        source["text"] += " " + LIVE_PASSAGE
    assert _statement_valid(statement, source, operative=True)


@pytest.mark.parametrize("field", ["assertion_statement", "owner_label"])
@pytest.mark.parametrize("empty", ["", "   "])
def test_statement_and_owner_still_require_meaningful_text(field, empty):
    source = _saved_source()
    statement = _statement()
    statement[field] = empty
    assert not _statement_valid(statement, source, operative=True)


@pytest.mark.parametrize(
    "contract",
    [
        RESEARCH_VERIFICATION,
        "research_support_v3",
        "research_support_v2",
        "research_support_v1",
    ],
)
@pytest.mark.parametrize(
    "field",
    [
        "support_excerpt",
        "scope_excerpt",
        "owner_excerpt",
        "treatment_excerpt",
    ],
)
def test_current_and_historical_exact_saved_excerpts_above_800_remain_valid(contract, field):
    assert len(LONG_EXACT_EXCERPT) > 800
    source = _saved_source(contract)
    source["verification"][field] = LONG_EXACT_EXCERPT
    assert source_verification_valid(source, contract=contract)
    assert source["verification"]["contract"] == contract
    assert source["verification"][field] == LONG_EXACT_EXCERPT


@pytest.mark.parametrize(
    "field",
    [
        "support_excerpt",
        "scope_excerpt",
        "owner_excerpt",
        "treatment_excerpt",
    ],
)
@pytest.mark.parametrize("invalid_words", ["   ", "Words supplied only by a different source."])
def test_saved_excerpts_still_require_nonblank_same_source_words(field, invalid_words):
    source = _saved_source()
    source["verification"][field] = invalid_words
    assert not source_verification_valid(source)


@pytest.mark.parametrize(
    "field,value",
    [
        ("assertion_owner", "party"),
        ("assertion_role", "court_conclusion"),
        ("source_treatment", "reported"),
    ],
)
def test_width_removal_keeps_owner_role_and_adoption_controls(field, value):
    source = _saved_source()
    source["verification"][field] = value
    assert not source_verification_valid(source)


def test_long_exact_predicate_and_complete_proposal_condition_remain_valid():
    finding = _saved_finding(predicate=LONG_EXACT_EXCERPT)
    assert len(LONG_EXACT_EXCERPT) > 800
    assert len(PRESERVED_CONDITION) > 1000
    assert _application_premises_valid(finding)
    assert finding_verification_valid(finding)
    premise = finding["use_verification"]["application_premises"][0]
    assert premise["predicate_excerpt"] == finding["sources"][0]["verification"]["scope_excerpt"]
    assert premise["preserved_condition"] == finding["need"]


@pytest.mark.parametrize(
    "damage",
    [
        "blank_predicate",
        "foreign_predicate",
        "foreign_source",
        "blank_condition",
        "outside_condition",
    ],
)
def test_application_controls_survive_width_removal(damage):
    finding = _saved_finding(condition="If the agreement requires notice, check its application.")
    premise = finding["use_verification"]["application_premises"][0]
    if damage == "blank_predicate":
        premise["predicate_excerpt"] = "   "
    elif damage == "foreign_predicate":
        premise["predicate_excerpt"] = "Another source's limiting predicate."
    elif damage == "foreign_source":
        premise["source_id"] = "unowned-source"
    elif damage == "blank_condition":
        premise["preserved_condition"] = "   "
    else:
        premise["preserved_condition"] = "A qualification absent from both need and why."
    assert not _application_premises_valid(finding)


def test_explicit_long_assertion_owner_and_entire_condition_pass_in_one_existing_judge_call():
    proposal, decision = _live_case()
    model = OfflineJudge(decision)
    checked = _verify(proposal, model)
    assert len(checked.rows[SUBJECT["id"]]) == 1
    retained = checked.rows[SUBJECT["id"]][0]
    source = retained["sources"][0]
    verification = source["verification"]
    assert verification["assertion_statement"] == LIVE_PASSAGE
    assert verification["owner_label"] == OWNER_LABEL
    assert verification["scope_excerpt"] == LIVE_PASSAGE
    assert source["text"] == LIVE_PASSAGE
    assert retained["need"] == PRESERVED_CONDITION
    assert (
        retained["use_verification"]["application_premises"][0]["preserved_condition"]
        == PRESERVED_CONDITION
    )
    assert finding_verification_valid(retained)
    assert checked.coverage[SUBJECT["id"]]["checked_items"] == 1
    assert checked.coverage[SUBJECT["id"]]["unread_items"] == 0
    assert len(model.calls) == 1
    assert model.calls[0][2] is Tier.JUDGE
    payload = json.loads(model.calls[0][0].user)
    selected_source = payload["subjects"][0]["candidates"][0]["sources"][0]
    assert selected_source["fragments"] == [
        {"id": "f1", "start": 0, "end": len(LIVE_PASSAGE), "text": LIVE_PASSAGE}
    ]


@pytest.mark.parametrize(
    "damage",
    ["blank_assertion", "blank_owner", "wrong_role", "foreign_source", "outside_condition"],
)
def test_invalid_explicit_decisions_remain_unread_after_existing_bounded_repair(damage):
    proposal, decision = _live_case()
    # Short valid neighbours isolate the negative control before the width fix too.
    decision["source_checks"][0]["assertion_statement"] = (
        "The notice obligation remains conditional."
    )
    decision["source_checks"][0]["owner_label"] = "Synthetic Conditions Act"
    condition = "If the agreement requires notice, determine its application."
    proposal["need"] = condition
    decision["application_premises"][0]["preserved_condition"] = condition
    if damage == "blank_assertion":
        decision["source_checks"][0]["assertion_statement"] = "   "
    elif damage == "blank_owner":
        decision["source_checks"][0]["owner_label"] = "   "
    elif damage == "wrong_role":
        decision["source_checks"][0]["assertion_role"] = "court_conclusion"
    elif damage == "foreign_source":
        decision["source_checks"][0]["source_id"] = "unowned-source"
    else:
        decision["application_premises"][0]["preserved_condition"] = "An absent qualification."
    model = OfflineJudge(decision)
    checked = _verify(proposal, model)
    assert checked.rows[SUBJECT["id"]] == []
    assert checked.coverage[SUBJECT["id"]]["unread_items"] == 1
    assert len(model.calls) == 2


def test_context_budget_still_bounds_complete_long_unit_without_omission_or_call():
    proposal, decision = _live_case()
    model = OfflineJudge(decision, budget=1)
    checked = _verify(proposal, model)
    assert checked.rows[SUBJECT["id"]] == []
    assert checked.coverage[SUBJECT["id"]]["unread_items"] == 1
    assert not model.calls
    assert _passage_fragments(LIVE_PASSAGE) == [
        {"id": "f1", "start": 0, "end": len(LIVE_PASSAGE), "text": LIVE_PASSAGE}
    ]
