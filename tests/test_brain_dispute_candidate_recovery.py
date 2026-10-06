"""Detached mechanical recovery proof; scripted judgments are not model qualification."""

import json
from dataclasses import replace

import pytest

from nm.brain import dispute_verification as disputes
from nm.brain.conversation import Message
from nm.shared.model_port import SchemaViolation, require_schema
from tests.brain_reader_fixture import scripted_source_treatments
from tests.test_brain_dispute_verification import Model, _candidate, _verdict

SCOPE = {"requests": [{"request_index": 2, "material_purposes": ["interpretation_review"]}]}


class StrictModel(Model):
    def structured(self, prompt, schema, tier, *, max_tokens=None):
        result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
        require_schema(result.data, schema)
        return result


def assessment(state="complete"):
    return {
        "state": state,
        "reason": "The scoped account representation was examined.",
        "missing_source_ids": [],
    }


def evaluate(
    model, candidates, latest, *, earlier=(), active=(), audit=None, status=None, coverage=None
):
    return disputes.verify_disputes(
        model,
        candidates=candidates,
        earlier=earlier,
        latest=latest,
        active_disputes=active,
        audit=audit,
        review_status=status,
        source_treatments=scripted_source_treatments(earlier, latest),
        review_scope=SCOPE,
        coverage=coverage,
    )


@pytest.mark.parametrize("failure", ["absent", "contradictory_accept", "duplicate"])
def test_exhausted_independent_candidate_keeps_checked_peer_and_marks_unread(failure):
    first = "The payment is contested."
    second = "The records were withheld."
    latest = f"{first} {second}"
    candidates = (_candidate(first, "Payment contest"), _candidate(second, "Withheld records"))
    wrong = _verdict("C2", accept=True)
    if failure == "absent":
        bad = []
    elif failure == "contradictory_accept":
        wrong["operation_supported"] = False
        bad = [wrong]
    else:
        bad = [wrong, wrong]
    model = StrictModel(
        [
            {"verdicts": [_verdict("C1", accept=True), *bad], "coverage": assessment()},
            {"verdicts": bad, "coverage": assessment()},
        ]
    )
    audit, status, coverage = [], {}, {}
    assert (
        evaluate(model, candidates, latest, audit=audit, status=status, coverage=coverage)
        == candidates[:1]
    )
    assert len(model.calls) == 2
    repair = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in repair["candidates"]] == ["C2"]
    assert repair["retained_candidate_context"][0]["candidate_id"] == "C1"
    assert repair["source_treatments"] == json.loads(model.calls[0][0].user)["source_treatments"]
    unread = audit[1]
    assert unread["verdict"] == "unassessed" and unread["admission_issue"] == "review_unavailable"
    assert unread["proposal"]["quoted"] == second and unread["validation_issues"]
    assert not {"account_check", "target_checks", "model_decision"} & unread.keys()
    assert status == {
        "state": "partial",
        "checked_items": 1,
        "accepted_items": 1,
        "rejected_items": 0,
        "withheld_items": 0,
        "unread_items": 1,
        "unread_candidate_ids": ["C2"],
        "envelope_unread": False,
        "envelope_validation_issue": "",
        "conditional_review_failure": "",
    }
    assert coverage["state"] == "unassessed"
    assert coverage["prior_assessment"]["state"] == "complete"


def test_genuine_rejection_is_checked_and_does_not_become_unread_or_invalidate_coverage():
    first = "The payment is contested."
    second = "Please explain the saved dispute."
    latest = f"{first} {second}"
    candidates = (_candidate(first, "Payment contest"), _candidate(second, "Explanation request"))
    model = StrictModel(
        [
            {
                "verdicts": [_verdict("C1", accept=True), _verdict("C2", accept=False)],
                "coverage": assessment(),
            }
        ]
    )
    audit, status, coverage = [], {}, {}
    assert (
        evaluate(model, candidates, latest, audit=audit, status=status, coverage=coverage)
        == candidates[:1]
    )
    assert len(model.calls) == 1
    assert audit[1]["verdict"] == "reject" and "admission_issue" not in audit[1]
    assert status["checked_items"] == 2 and status["rejected_items"] == 1
    assert status["unread_items"] == status["withheld_items"] == 0
    assert coverage["state"] == "complete"


def test_unread_restoration_successor_preserves_old_target_and_distinct_counts():
    original = "Two independently contested acts were reported."
    earlier = (Message("old", "advocate", original),)
    request = "Reconcile the saved interpretation."
    peer_words = "A separate notice is contested."
    instruction = "Explain the record."
    latest = f"{request} {peer_words} {instruction}"
    changed = replace(
        _candidate(request, "First restored act", relation="corrects", earlier=original),
        related_dispute_ids=("old-record",),
    )
    unread_successor = replace(changed, label="Second restored act")
    independent = _candidate(peer_words, "Notice contest")
    rejected = _candidate(instruction, "Explanation request")
    active = (
        {
            "id": "old-record",
            "label": "Merged interpretation",
            "statement": original,
            "source_turn_id": "old",
            "quoted": original,
        },
    )
    accepted = _verdict("C1", accept=True)
    accepted["account_check"] = {
        "content_role": "reported_matter_account",
        "supported": True,
        "introduces_legal_analysis": False,
        "source_ids": ["P1S1"],
        "reason": "Earlier original advocate words support the restored account.",
    }
    accepted["target_checks"] = [
        {
            "target_id": "old-record",
            "identity_relation": "restore_invalid_interpretation",
            "account_preserved": True,
            "required_peer_ids": ["C2"],
            "reason": "Both independent successors are needed to preserve the account.",
        }
    ]
    model = StrictModel(
        [
            {
                "verdicts": [accepted, _verdict("C3", accept=True), _verdict("C4", accept=False)],
                "coverage": assessment(),
            },
            {"verdicts": [], "coverage": assessment()},
        ]
    )
    audit, status, coverage = [], {}, {}
    retained = evaluate(
        model,
        (changed, unread_successor, independent, rejected),
        latest,
        earlier=earlier,
        active=active,
        audit=audit,
        status=status,
        coverage=coverage,
    )
    assert retained == (independent,) and len(model.calls) == 2
    assert active[0]["id"] == "old-record" and all(
        "old-record" not in c.related_dispute_ids for c in retained
    )
    assert audit[0]["admission_issue"] == "required_restoration_peer_unavailable"
    assert (
        audit[1]["admission_issue"] == "review_unavailable" and audit[1]["verdict"] == "unassessed"
    )
    assert audit[2]["verdict"] == "accept" and audit[3]["verdict"] == "reject"
    assert status["checked_items"] == 3
    assert (
        status["accepted_items"]
        == status["rejected_items"]
        == status["withheld_items"]
        == status["unread_items"]
        == 1
    )
    assert coverage["state"] == "unassessed"
    assert "remained unread" in coverage["validation_issue"]
    assert "required successors" in coverage["validation_issue"]


@pytest.mark.parametrize(
    "core_fault", ["source_catalogue", "foreign_target", "conflicting_target", "malformed_target"]
)
def test_core_source_or_canonical_target_integrity_still_blocks_before_calls(core_fault):
    latest = "The account needs repair."
    candidate = _candidate(latest, "Account repair")
    sources = scripted_source_treatments((), latest)
    active = ()
    if core_fault == "source_catalogue":
        sources["L1"]["quoted"] = "Unowned original words."
    else:
        candidate = replace(candidate, relation="corrects", related_dispute_ids=("old-record",))
        if core_fault == "malformed_target":
            active = (None,)
        if core_fault == "conflicting_target":
            active = (
                {"id": "old-record", "statement": "A"},
                {"id": "old-record", "statement": "B"},
            )
    model = StrictModel([])
    audit, status = [], {}
    with pytest.raises(SchemaViolation):
        disputes.verify_disputes(
            model,
            candidates=(candidate,),
            earlier=(),
            latest=latest,
            active_disputes=active,
            source_treatments=sources,
            audit=audit,
            review_status=status,
            review_scope=SCOPE,
            coverage={},
        )
    assert model.calls == [] and audit == []
    assert status == {}


def test_second_adapter_schema_failure_retains_only_exposed_checked_peers():
    latest = "The payment is contested. The notice is contested."
    candidates = (
        _candidate("The payment is contested.", "Payment contest"),
        _candidate("The notice is contested.", "Notice contest"),
    )
    model = StrictModel(
        [
            {"verdicts": [_verdict("C1", accept=True)], "coverage": assessment()},
            SchemaViolation("Adapter refused the missing operation field"),
        ]
    )
    audit, status, coverage = [], {}, {}
    assert (
        evaluate(model, candidates, latest, audit=audit, status=status, coverage=coverage)
        == candidates[:1]
    )
    assert len(model.calls) == 2 and status["unread_items"] == 1
    assert "Adapter refused" in audit[1]["validation_issues"][0]
    assert coverage["state"] == "unassessed"


def test_first_adapter_schema_failure_does_not_invent_peer_acceptance():
    latest = "The payment is contested. The notice is contested."
    candidates = (
        _candidate("The payment is contested.", "Payment contest"),
        _candidate("The notice is contested.", "Notice contest"),
    )
    model = StrictModel(
        [
            {"verdicts": [_verdict("C1", accept=True)]},
            {"verdicts": [], "coverage": assessment()},
        ]
    )
    audit, status, coverage = [], {}, {}
    assert evaluate(model, candidates, latest, audit=audit, status=status, coverage=coverage) == ()
    assert len(model.calls) == 2 and status["checked_items"] == 0 and status["unread_items"] == 2
    assert all(row["verdict"] == "unassessed" for row in audit)
    assert coverage["state"] == "unassessed"


def test_provider_failure_still_propagates_without_fabricating_candidate_decisions():
    from nm.shared.model_port import ProviderUnavailable

    latest = "The payment is contested."
    candidate = _candidate(latest, "Payment contest")
    model = StrictModel([ProviderUnavailable("Independent review provider unavailable")])
    audit, status = [], {}
    with pytest.raises(ProviderUnavailable):
        evaluate(model, (candidate,), latest, audit=audit, status=status, coverage={})
    assert len(model.calls) == 1 and audit == [] and status == {}


@pytest.mark.parametrize("unscoped_sink", [False, True])
def test_unread_cannot_be_silently_dropped_without_an_explicit_diagnostic_receiver(unscoped_sink):
    latest = "The payment is contested."
    candidate = _candidate(latest, "Payment contest")
    model = StrictModel([{"verdicts": []}, {"verdicts": []}])
    with pytest.raises(SchemaViolation, match="remained incomplete for C1"):
        disputes.verify_disputes(
            model,
            candidates=(candidate,),
            earlier=(),
            latest=latest,
            active_disputes=(),
            source_treatments=scripted_source_treatments((), latest),
            coverage={} if unscoped_sink else None,
        )
    assert len(model.calls) == 2
