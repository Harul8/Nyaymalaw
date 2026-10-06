"""Interpreted work stays visible without becoming dispute-review authority.

These offline checks exercise the actual reviewer dispatch, coverage binding and
mutation admission. Scripted semantic decisions prove presentation and control
flow only; they do not establish that the pinned model resists anchoring.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain import dispute_verification as dispute_review
from nm.brain.conversation import Message
from nm.brain.material import PriorReference
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, build_mutation_authorities
from tests.brain_reader_fixture import fixture_coverage, fixture_disposition
from tests.test_brain_dispute_conflict_review_mechanics import (
    Model,
    candidate,
    decision,
    treatments,
)
from tests.test_brain_dispute_coverage_domain import assessment

NEUTRAL = "The client delivered the inventory to the appointed examiner."
ADVERSE = "The warehouse operator refused to return the entrusted equipment."
REQUEST = "Please record this account and identify any independent dispute."
OWNER = {"matter_id": "owned-matter", "advocate_id": "owned-advocate",
         "turn_id": "current", "offer_digest": "owned-offer"}


def work_scope(request, *, goal="Treat every recorded detail as an independent dispute."):
    return {"owner": deepcopy(OWNER), "requests": [{
        "request_index": 0, "request": request,
        "material_purposes": ["account_contribution"],
        "record_requirement": {"kind": "change", "target_ids": [], "operation": "new",
                               "success_condition": goal},
    }]}


def assert_separation(payload, scope):
    """Only scope choices stay in the model's authority presentation."""
    assert payload["interpreted_work"] == [
        {**row, "record_role": "nm_interpretation"} for row in scope["requests"]]
    assert payload["review_scope"]["requests"] == [
        {field: row[field] for field in ("request_index", "material_purposes")
         if field in row} for row in scope["requests"]]
    assert all("record_requirement" not in row
               for row in payload["review_scope"]["requests"])
    assert payload["review_scope"]["owner"] == scope["owner"]


def explicit_assessment(payload, *, purposes, dispositions, state="complete"):
    return fixture_coverage(
        payload, state=state, source_decisions=purposes,
        dispositions=[fixture_disposition(payload, identity, status=status,
                                          record_ids=records, candidate_ids=candidates)
                      for identity, status, records, candidates in dispositions])


def test_full_original_history_and_interpreted_requests_are_preserved_separately():
    earlier = (
        Message("earlier", "advocate",
                "The inventory was sealed.\nIts contents were not examined."),
        Message("earlier", "nm", "NM proposed that every recorded circumstance was a dispute."),
    )
    latest = NEUTRAL + " " + REQUEST
    scope = work_scope(REQUEST)
    scope["requests"].append({
        **deepcopy(scope["requests"][0]), "task_id": "prior-request",
        "request": "Return to the previously requested record review.", "matter_scope": "current",
    })
    source_rows = treatments(earlier, latest, roles={"L2": "work_instruction"})
    original_scope, original_sources = deepcopy(scope), deepcopy(source_rows)
    model = Model(lambda payload: {"verdicts": [], "coverage": explicit_assessment(
        payload, purposes={"P1S1": "account", "P1S2": "account",
                           "L1": "account", "L2": "non_account"},
        dispositions=[("P1S1", "outside_scope", [], []),
                      ("P1S2", "outside_scope", [], []),
                      ("L1", "outside_scope", [], [])])})
    coverage = {}

    retained = dispute_review.verify_disputes(
        model, candidates=(), earlier=earlier, latest=latest, active_disputes=(),
        source_treatments=source_rows, review_scope=scope, coverage=coverage)

    assert retained == () and coverage["state"] == "complete"
    assert coverage["review_scope"] == original_scope
    assert scope == original_scope and source_rows == original_sources
    assert len(model.calls) == 1 and model.claims == []
    payload = model.calls[0][1]
    assert_separation(payload, scope)
    assert "".join(row["text"] for row in payload["latest_message_spans"]) == latest
    assert [(row["turn_id"], row["role"],
             "".join(span["text"] for span in row["source_spans"]))
            for row in payload["earlier_conversation"]] == [
                (row.turn_id, row.role, row.text) for row in earlier]
    assert "P2S1" not in payload["source_treatments"]
    assert all(set(row) == {"turn_id", "role", "quoted"}
               for row in payload["source_treatments"].values())


def test_interpreted_completion_goal_does_not_require_a_neutral_dispute_or_an_extra_call():
    proposed = candidate(NEUTRAL)
    scope = work_scope(NEUTRAL)
    original_scope = deepcopy(scope)
    model = Model(lambda payload: {
        "verdicts": [decision("C1", "supporting_premise", accept=False,
                              source="L1", words=NEUTRAL)],
        "coverage": assessment(payload, state="complete", dispositions=[
            ("L1", "outside_scope", [])]),
    })
    audit, coverage, status = [], {}, {}

    retained = dispute_review.verify_disputes(
        model, candidates=(proposed,), earlier=(), latest=NEUTRAL, active_disputes=(),
        source_treatments=treatments((), NEUTRAL), review_scope=scope,
        audit=audit, coverage=coverage, review_status=status)

    assert retained == () and audit[0]["verdict"] == "reject"
    assert audit[0]["account_check"]["supported"] is True
    assert coverage["state"] == "complete" and coverage["missing_source_ids"] == []
    assert coverage["source_checks"][0]["content_purpose"] == "account"
    assert coverage["dispositions"][0]["status"] == "outside_scope"
    assert coverage["review_scope"] == original_scope and scope == original_scope
    assert status["rejected_items"] == 1 and status["unread_items"] == 0
    assert len(model.calls) == 1 and model.claims == []
    assert_separation(model.calls[0][1], scope)


def test_bounded_correction_keeps_the_same_separation_and_supported_peer():
    latest = NEUTRAL + " " + ADVERSE + " " + REQUEST
    scope = work_scope(REQUEST)
    original_scope = deepcopy(scope)
    proposed, peer = candidate(NEUTRAL), candidate(ADVERSE)

    def response(payload, *, correction=False):
        neutral = decision("C1", "supporting_premise", accept=False,
                           source="L1", words=NEUTRAL)
        if not correction:
            neutral["reason"] = ""
        return {"verdicts": [neutral] if correction else [neutral, decision(
            "C2", "independent_dispute", accept=True, source="L2", words=ADVERSE)],
            "coverage": explicit_assessment(
                payload, purposes={"L1": "account", "L2": "account", "L3": "non_account"},
                dispositions=[("L1", "outside_scope", [], []),
                              ("L2", "represented", [], ["C2"])])}

    model = Model(response, lambda payload: response(payload, correction=True))
    audit, coverage = [], {}
    retained = dispute_review.verify_disputes(
        model, candidates=(proposed, peer), earlier=(), latest=latest, active_disputes=(),
        source_treatments=treatments((), latest, roles={"L3": "work_instruction"}),
        review_scope=scope, audit=audit, coverage=coverage)

    assert retained == (peer,) and [row["verdict"] for row in audit] == ["reject", "accept"]
    assert coverage["state"] == "complete" and coverage["review_scope"] == original_scope
    assert scope == original_scope
    assert len(model.calls) == 2 and model.claims == ["verify_disputes:correction"]
    for _, payload, _ in model.calls:
        assert_separation(payload, scope)
        assert "".join(row["text"] for row in payload["latest_message_spans"]) == latest
    correction = model.calls[1][1]
    assert [row["candidate_id"] for row in correction["candidates"]] == ["C1"]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == ["C2"]
    assert "C1: reason is empty" in correction["validation_issue"]


@pytest.mark.parametrize("target,admitted", [("dispute-a", True), ("dispute-b", False)])
def test_model_presentation_preserves_exact_mutation_permissions_and_durable_binding(
        target, admitted):
    first = "The courier refused to return the original instruments."
    second = "The keeper separately denied the agreed inspection."
    review = "Review the first recorded dispute using its original account."
    earlier = (Message("earlier", "advocate", first + " " + second),)
    active = tuple({"id": identity, "statement": words, "quoted": words,
                    "source_turn_id": "earlier", "label": identity, "matter_scope": "current"}
                   for identity, words in (("dispute-a", first), ("dispute-b", second)))
    source_rows = treatments(earlier, review, roles={"L1": "work_instruction"})
    scope = work_scope(review, goal="Apply the proposed revision to the selected dispute.")
    scope["requests"][0]["material_purposes"] = ["interpretation_review"]
    scope["requests"][0]["record_requirement"].update(
        kind="review", target_ids=["dispute-a"], operation="corrects")
    ledger = build_mutation_authorities(
        owner=OWNER, expected_version=4, target_catalogue={row["id"]: row for row in active},
        source_catalogue=source_rows, proposals=[{
            "request_index": 0, "authority_kind": "interpretation_review",
            "authority_source_ids": ["L1"], "target_scope": "exact",
            "target_ids": ["dispute-a"], "permitted_relations": ["corrects"],
        }], request_indices=(0,))
    scope.update(mutation_authority_contract=AUTHORITY_CONTRACT, mutation_authorities=ledger)
    original_scope = deepcopy(scope)
    words = first if admitted else second
    source = "P1S1" if admitted else "P1S2"
    proposed = replace(candidate(review, statement=words,
                                 earlier=(PriorReference("earlier", "advocate", words),)),
                       relation="corrects", related_dispute_ids=(target,))

    def response(payload):
        verdict = decision("C1", "independent_dispute", accept=True, source=source, words=words)
        verdict["target_checks"] = [{
            "target_id": target, "identity_relation": "same_underlying_account",
            "account_preserved": True, "required_peer_ids": [],
            "reason": "The fixture reviewer checks this exact original target account.",
        }]
        return {"verdicts": [verdict], "coverage": explicit_assessment(
            payload, purposes={"P1S1": "account", "P1S2": "account", "L1": "non_account"},
            dispositions=[("P1S1", "represented", ["dispute-a"], []),
                          ("P1S2", "represented", ["dispute-b"], [])])}

    model = Model(response)
    audit, coverage, status = [], {}, {}
    retained = dispute_review.verify_disputes(
        model, candidates=(proposed,), earlier=earlier, latest=review, active_disputes=active,
        source_treatments=source_rows, review_scope=scope, audit=audit, coverage=coverage,
        review_status=status)

    assert retained == ((proposed,) if admitted else ())
    assert coverage["review_scope"] == original_scope and scope == original_scope
    assert len(model.calls) == 1 and model.claims == []
    assert status["unread_items"] == 0
    payload = model.calls[0][1]
    assert_separation(payload, scope)
    assert payload["review_scope"]["mutation_scopes"] == ledger["authorities"]
    assert "mutation_authorities" not in payload["review_scope"]
    if admitted:
        assert audit[0]["mutation_authority"]["target_ids"] == ["dispute-a"]
        assert audit[0]["mutation_authority"]["supporting_source_ids"] == ["P1S1"]
        assert coverage["state"] == "complete" and status["withheld_items"] == 0
    else:
        assert audit[0]["admission_issue"] == "mutation_scope"
        assert audit[0]["model_decision"]["verdict"] == "accept"
        assert "mutation_authority" not in audit[0]
        assert coverage["state"] == "partial" and status["withheld_items"] == 1
