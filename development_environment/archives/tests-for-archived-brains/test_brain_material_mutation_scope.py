"""Scope permissions precede admission even when an independent judge is wrong."""
from copy import deepcopy
from dataclasses import replace

import pytest

from nm.brain.conversation import Message, OpeningCandidate
from nm.brain.material import MaterialCandidate, PriorReference
from nm.brain.material_verification import verify_material_grounding
from nm.brain.mutation_contracts import AUTHORITY_CONTRACT, build_mutation_authorities
from nm.shared.model_port import SchemaViolation
from tests.brain_reader_fixture import scripted_source_treatments
from tests.test_brain_material_verification import Model

OWNER = {"matter_id": "matter", "advocate_id": "advocate", "turn_id": "second",
         "offer_digest": "source-exact-offer"}
EARLIER = (Message("first", "advocate",
                   "The event happened on Monday. The document is with the client."),)
TARGETS = {
    "date": {"id": "date", "source_turn_id": "first", "quoted": "The event happened on Monday.",
             "statement": "The event happened on Monday.", "basis": "stated"},
    "custody": {"id": "custody", "source_turn_id": "first",
                "quoted": "The document is with the client.",
                "statement": "The document is with the client.", "basis": "stated"},
}


def sources(latest, *, review=False):
    return scripted_source_treatments(EARLIER, latest, turn_id="second",
                                     roles={"L1": "work_instruction"} if review else {})


def scope(latest, *, review=False):
    catalogue = sources(latest, review=review)
    ledger = build_mutation_authorities(
        owner=OWNER, expected_version=1, target_catalogue=TARGETS,
        source_catalogue=catalogue, request_indices=[0], proposals=[{
            "request_index": 0,
            "authority_kind": "interpretation_review" if review else "account_contribution",
            "authority_source_ids": ["L1"], "target_scope": "exact",
            "target_ids": ["date"], "permitted_relations": ["corrects"],
        }])
    return {"owner": OWNER, "requests": [], "mutation_authorities": ledger,
            "mutation_authority_contract": AUTHORITY_CONTRACT}


def changed(latest, *, target="date", relation="corrects"):
    old = TARGETS[target]
    return MaterialCandidate(
        kind="event", statement="The advocate's event account gives Tuesday.", quoted=latest,
        relation=relation, prior_references=(PriorReference("first", "advocate", old["quoted"]),),
        matter_scope="current", basis="stated", importance="central",
        why_material="The event's timing affects requested matter work.", placement="matter",
        related_material_ids=(target,))


def accepted(identity, *, support="L1", peers=(), target="date"):
    return {
        "candidate_id": identity, "operation_supported": True, "verdict": "accept",
        "reason": "The scripted judge accepts this exact proposed account operation.",
        "account_check": {
            "content_role": "reported_matter_account", "supported": True,
            "introduces_legal_analysis": False, "source_ids": [support],
            "reason": "The original selected advocate passage supplies the proposal's content.",
        },
        "target_checks": [{
            "target_id": target, "identity_relation": "same_underlying_account",
            "account_preserved": True, "required_peer_ids": list(peers),
            "reason": "The deliberately scripted judgment accepts this owned target.",
        }],
    }


def answer(*rows):
    return {"verdicts": list(rows), "coverage": {
        "state": "complete", "missing_source_ids": [],
        "reason": "The scripted semantic judge considers the requested account scope covered.",
    }}


def verify(model, proposals, latest, *, review=False, coverage=None, review_state=None):
    return verify_material_grounding(
        model, candidates=tuple(proposals), opening=OpeningCandidate(False, "", ""),
        earlier=EARLIER, latest=latest, current_matter_id="matter",
        prior_material=tuple(TARGETS.values()), active_material=tuple(TARGETS.values()),
        source_treatments=sources(latest, review=review), review_scope=scope(latest, review=review),
        coverage=coverage, review_state=review_state)


def test_wrong_owned_record_is_withheld_after_valid_positive_independent_verdict():
    latest = "Sorry, Tuesday."
    proposal = changed(latest, target="custody")
    model = Model([answer(accepted("D1", target="custody"))])
    assessment = {}
    result = verify(model, [proposal], latest, coverage=assessment)
    assert result.details == ()
    assert result.rejected_details == 0 and result.withheld_details == 1
    assert result.withheld_proposals[0]["admission_issue"] == "mutation_scope"
    assert result.withheld_proposals[0]["model_decision"]["verdict"] == "accept"
    assert result.mutation_bindings == ()
    assert len(model.calls) == 1
    assert assessment["state"] == "unassessed"
    assert assessment["previous_assessment"]["state"] == "complete"
    assert "mutation_scope" in assessment["validation_issue"]
    assert "required successors were unavailable" not in assessment["validation_issue"]


def test_implicit_correction_passes_without_an_explicit_record_change_request():
    latest = "Sorry, Tuesday."
    proposal = changed(latest)
    model = Model([answer(accepted("D1"))])
    assessment = {}
    result = verify(model, [proposal], latest, coverage=assessment)
    assert result.details == (proposal,)
    assert result.withheld_details == 0
    assert result.mutation_bindings[0][0] is proposal
    binding = result.mutation_bindings[0][1]
    assert binding["target_ids"] == ["date"]
    assert binding["supporting_source_ids"] == ["L1"]
    assert binding["attached_context_source_ids"] == ["P1S1"]
    assert assessment["state"] == "complete" and len(model.calls) == 1


def test_review_instruction_can_restore_earlier_account_without_supplying_a_new_fact():
    latest = "Review the event reading against the earlier original words."
    proposal = changed(latest)
    model = Model([answer(accepted("D1", support="P1S1"))])
    assessment = {}
    result = verify(model, [proposal], latest, review=True, coverage=assessment)
    assert result.details == (proposal,)
    binding = result.mutation_bindings[0][1]
    assert binding["supporting_source_ids"] == ["P1S1"]
    assert scope(latest, review=True)["mutation_authorities"]["authorities"][0][
        "authority_source_ids"] == ["L1"]
    assert assessment["state"] == "complete" and len(model.calls) == 1


def test_scope_failure_preserves_an_independently_valid_new_account():
    latest = "Sorry, Tuesday. A separate parcel arrived."
    wrong = changed("Sorry, Tuesday.", target="custody")
    peer = MaterialCandidate(
        kind="event", statement="The advocate reports arrival of a separate parcel.",
        quoted="A separate parcel arrived.", relation="new", prior_references=(),
        matter_scope="current", basis="stated", importance="relevant",
        why_material="A separate reported event matters to the file.", placement="matter")
    peer_verdict = accepted("D2", support="L2")
    peer_verdict["target_checks"] = []
    model = Model([answer(accepted("D1", target="custody"), peer_verdict)])
    result = verify(model, [wrong, peer], latest, coverage={})
    assert result.details == (peer,)
    assert result.withheld_details == 1 and result.mutation_bindings == ()
    assert len(model.calls) == 1


def test_scope_rejection_removes_dependent_binding_without_losing_the_predecessor():
    latest = "Sorry, Tuesday."
    first = changed(latest)
    second = changed(latest, relation="withdraws")
    model = Model([answer(accepted("D1", peers=("D2",)), accepted("D2"))])
    result = verify(model, [first, second], latest, coverage={})
    assert result.details == () and result.withheld_details == 2
    assert {row["admission_issue"] for row in result.withheld_proposals} == {
        "mutation_scope", "required_restoration_peer_unavailable"}
    assert result.mutation_bindings == () and len(model.calls) == 1


def test_retained_semantic_acceptance_cannot_bypass_scope_on_reuse():
    latest = "Sorry, Tuesday."
    wrong = changed(latest, target="custody")
    model = Model([answer(accepted("D1", target="custody")), answer()])
    review_state = {}
    first = verify(model, [wrong], latest, coverage={}, review_state=review_state)
    second = verify(model, [wrong], latest, coverage={}, review_state=review_state)
    assert first.details == second.details == ()
    assert first.withheld_details == second.withheld_details == 1
    assert second.withheld_proposals[0]["admission_issue"] == "mutation_scope"
    assert second.mutation_bindings == ()
    assert len(model.calls) == 2
    import json

    assert json.loads(model.calls[1][0].user)["candidates"] == []


def test_new_result_field_keeps_old_grounding_result_callers_compatible():
    from nm.brain.material_verification import GroundingResult

    assert GroundingResult((), True, 0).mutation_bindings == ()


def test_corrupt_scope_ledger_is_not_downgraded_to_a_truthful_empty_extraction():
    latest = "Sorry, Tuesday."
    model = Model([answer(accepted("D1"))])
    review = deepcopy(scope(latest))
    review["mutation_authorities"]["expected_version"] = 10
    with pytest.raises(SchemaViolation, match="changed after"):
        verify_material_grounding(
            model, candidates=(changed(latest),), opening=OpeningCandidate(False, "", ""),
            earlier=EARLIER, latest=latest, current_matter_id="matter",
            prior_material=tuple(TARGETS.values()), active_material=tuple(TARGETS.values()),
            source_treatments=sources(latest), review_scope=review, coverage={})


def test_wrong_operation_on_the_right_target_is_withheld_generically():
    latest = "Sorry, Tuesday."
    model = Model([answer(accepted("D1"))])
    result = verify(model, [changed(latest, relation="withdraws")], latest, coverage={})
    assert result.details == () and result.withheld_details == 1
    assert result.withheld_proposals[0]["admission_issue"] == "mutation_scope"


def test_ordinary_new_account_keeps_no_scope_binding_and_no_false_rejection():
    latest = "Sorry, Tuesday."
    proposal = replace(changed(latest), relation="new", prior_references=(),
                       related_material_ids=())
    judged = accepted("D1")
    judged["target_checks"] = []
    result = verify(Model([answer(judged)]), [proposal], latest, coverage={})
    assert result.details == (proposal,)
    assert result.mutation_bindings == () and result.withheld_details == 0
