"""Generation coupling and admission mechanics; no semantic classification claims.

Every role and verdict below is deliberately authored by the fixture. A passing
test does not show that a real Judge distinguishes a premise from a dispute.
"""

from copy import deepcopy

import pytest

from nm.brain import dispute_verification as owner
from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation, on_the_wire, require_schema
from tests.test_brain_dispute_conflict_review_mechanics import (
    Model,
    candidate,
    check,
    decision,
)
from tests.test_brain_dispute_review_wire import wire_verdict
from tests.test_brain_record_review_wire import _strict_objects
from tests.test_brain_source_support_verifiers import proposal, source_catalogue, verdict

ROLES = ("independent_dispute", "supporting_premise", "evidence_gap_or_question",
         "duplicate", "unsupported")
WORDS = "The recorder reports that the handover date remains unconfirmed."
OTHER = "The custodian separately refuses to return the entrusted ledger."
REFERENCES, TREATMENTS = source_catalogue(WORDS + " " + OTHER)
TARGET = "prior-dispute-27"


def schema(*, wire=True):
    return owner._schema(("C1", "C2"), tuple(REFERENCES), (TARGET,), ("C2",),
                         source_references=REFERENCES, wire=wire)


def row(role="independent_dispute", result="accept"):
    result_row = wire_verdict(REFERENCES["L1"])
    result_row.update(candidate_role=role, verdict=result)
    result_row["target_checks"] = [{
        "target_id": TARGET, "identity_relation": "same_underlying_account",
        "account_preserved": True, "required_peer_ids": ["C2"],
        "reason": "The explicitly scripted successor preserves this owned account.",
    }]
    return result_row


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("result", ("accept", "reject"))
def test_fresh_provider_allows_only_the_declared_role_verdict_pairs(role, result):
    data = {"verdicts": [row(role, result)]}
    offered = on_the_wire(schema())
    before = deepcopy((data, offered))

    if result == "accept" and role != "independent_dispute":
        with pytest.raises(SchemaViolation):
            require_schema(data, offered)
    else:
        require_schema(data, offered)

    assert (data, offered) == before


def test_native_branches_preserve_every_closed_owned_source_and_operation_field():
    canonical = schema(wire=False)
    original = deepcopy(canonical)
    offered = on_the_wire(schema())
    _strict_objects(offered)
    branches = offered["properties"]["verdicts"]["items"]["anyOf"]
    assert len(branches) == 2
    expected = deepcopy(canonical["properties"]["verdicts"]["items"])
    expected["properties"].update(record.review_properties(
        tuple(REFERENCES), (TARGET,), ("C2",), source_references=REFERENCES, wire=True))

    by_verdict = {}
    for branch in branches:
        selected, = branch["properties"]["verdict"]["enum"]
        assert selected not in by_verdict
        by_verdict[selected] = branch
        common = deepcopy(branch)
        common["properties"]["verdict"]["enum"] = ["accept", "reject"]
        common["properties"]["candidate_role"]["enum"] = list(ROLES)
        assert common == expected
        account = branch["properties"]["account_check"]
        assert "source_ids" not in account["properties"]
        checks = account["properties"]["source_checks"]["items"]["anyOf"]
        assert len(checks) == len(REFERENCES)
        for source_check in checks:
            identity, = source_check["properties"]["source_id"]["enum"]
            bounds = source_check["properties"]["support_spans"]["items"]["properties"]
            assert bounds["start"]["maximum"] == len(REFERENCES[identity]["quoted"])
            assert bounds["end"]["maximum"] == len(REFERENCES[identity]["quoted"])
    assert set(by_verdict) == {"accept", "reject"}
    assert by_verdict["accept"]["properties"]["candidate_role"]["enum"] == ["independent_dispute"]
    assert by_verdict["reject"]["properties"]["candidate_role"]["enum"] == list(ROLES)
    assert canonical == original


def test_fresh_construction_leaves_default_canonical_shape_and_proof_unchanged():
    canonical = schema(wire=False)
    declared = deepcopy(owner._VERDICT)
    before = deepcopy((canonical, REFERENCES))

    schema()

    assert schema(wire=False) == canonical
    assert owner._VERDICT == declared
    assert (canonical, REFERENCES) == before
    item = canonical["properties"]["verdicts"]["items"]
    assert "anyOf" not in item
    assert item["properties"]["candidate_role"]["enum"] == list(ROLES)
    assert item["properties"]["verdict"]["enum"] == ["accept", "reject"]
    assert "source_ids" in item["properties"]["account_check"]["required"]
    historical = row("supporting_premise", "accept")
    historical["account_check"]["source_ids"] = ["L1"]
    require_schema({"verdicts": [historical]}, canonical)


@pytest.mark.parametrize("result", ("accept", "reject"))
@pytest.mark.parametrize("fault", (
    "foreign_candidate", "foreign_source", "overrun", "foreign_target"))
def test_both_generation_verdicts_keep_source_bounds_and_owned_reference_rejection(result, fault):
    authored = row(result=result)
    if fault == "foreign_candidate":
        authored["candidate_id"] = "another-owner-candidate"
    elif fault == "foreign_source":
        authored["account_check"]["source_checks"][0]["source_id"] = "another-owner-source"
    elif fault == "overrun":
        authored["account_check"]["source_checks"][0]["support_spans"][0]["end"] = (
            len(REFERENCES["L1"]["quoted"]) + 1)
    else:
        authored["target_checks"][0]["target_id"] = "another-owner-target"
    before = deepcopy(authored)

    with pytest.raises(SchemaViolation):
        require_schema({"verdicts": [authored]}, on_the_wire(schema()))

    assert authored == before


def test_fresh_empty_candidate_list_remains_a_valid_empty_review():
    offered = on_the_wire(owner._schema((), (), wire=True))
    _strict_objects(offered)

    require_schema({"verdicts": []}, offered)

    assert offered["properties"]["verdicts"]["maxItems"] == 0


def test_fresh_negative_review_can_leave_inapplicable_evidence_empty():
    offered = on_the_wire(owner._schema(("C1",), (), wire=True))
    authored = row("unsupported", "reject")
    authored["operation_supported"] = False
    authored["account_check"].update(supported=False, source_checks=[])
    authored["target_checks"] = []

    require_schema({"verdicts": [authored]}, offered)

    assert authored["account_check"]["source_checks"] == []


@pytest.mark.parametrize("role", ROLES[1:])
def test_negative_non_dispute_role_retains_independently_authored_account_support(role):
    proposed = candidate(WORDS)
    authored = decision("C1", role, accept=False, source="L1", words=WORDS)
    before = deepcopy(authored)
    model = Model({"verdicts": [authored]})

    retained, audit, status = check(model, (proposed,), WORDS)

    assert retained == () and len(model.calls) == 1 and model.claims == []
    assert audit[0]["candidate_role"] == role and audit[0]["verdict"] == "reject"
    assert audit[0]["operation_supported"] is True
    assert audit[0]["account_check"] == {**authored["account_check"], "source_ids": ["L1"]}
    assert status["rejected_items"] == 1 and status["unread_items"] == 0
    assert authored == before


def test_canonical_non_dispute_acceptance_is_still_blocked_without_discarding_valid_peer():
    candidates = {"C1": proposal("dispute", WORDS), "C2": proposal("dispute", OTHER)}
    bad = verdict("dispute", REFERENCES["L1"])
    bad["candidate_role"] = "supporting_premise"
    peer = verdict("dispute", REFERENCES["L2"], index=2, source_id="L2")
    data = {"verdicts": [bad, peer]}
    before = deepcopy(data)

    accepted, issues = owner._read_verdicts(
        data, candidates, account_ids={"C1": {"L1"}, "C2": {"L2"}},
        targets={"C1": set(), "C2": set()}, source_treatments=TREATMENTS,
        source_references=REFERENCES)

    assert accepted == {"C2": peer}
    assert issues == {"C1": ("accept conflicts with candidate_role=supporting_premise",)}
    assert data == before


def test_permissive_fresh_output_uses_existing_bounded_recovery_and_preserves_peer():
    proposed, peer = candidate(WORDS), candidate(OTHER)
    wrong = decision("C1", "supporting_premise", accept=True, source="L1", words=WORDS)
    good_peer = decision("C2", "independent_dispute", accept=True, source="L2", words=OTHER)
    rejected = deepcopy(wrong)
    rejected["verdict"] = "reject"
    # This adapter intentionally bypasses provider-shape enforcement. The owner
    # must still reject the inconsistent combination instead of relabelling it.
    model = Model({"verdicts": [wrong, good_peer]}, {"verdicts": [rejected]})

    retained, audit, status = check(model, (proposed, peer), WORDS + " " + OTHER)

    assert retained == (peer,) and len(model.calls) == 2
    assert model.claims == ["verify_disputes:correction"]
    correction = model.calls[1][1]
    assert [item["candidate_id"] for item in correction["candidates"]] == ["C1"]
    assert [item["candidate_id"] for item in correction["retained_candidate_context"]] == ["C2"]
    assert correction["retained_candidate_context"][0]["decision"]["account_check"] == {
        **good_peer["account_check"], "source_ids": ["L2"]}
    assert "candidate_role=supporting_premise" in correction["validation_issue"]
    assert audit[0]["candidate_role"] == "supporting_premise" and audit[0]["verdict"] == "reject"
    assert audit[0]["account_check"] == {**wrong["account_check"], "source_ids": ["L1"]}
    assert audit[1]["verdict"] == "accept"
    assert status["accepted_items"] == status["rejected_items"] == 1
    assert status["unread_items"] == 0
