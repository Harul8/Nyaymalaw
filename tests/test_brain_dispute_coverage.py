"""Requested account omissions are reviewed independently, including empty reads."""

import json
from dataclasses import replace

import pytest

from nm.brain import dispute_verification as disputes
from nm.brain import record_review as record
from nm.brain.conversation import Message
from tests.brain_reader_fixture import scripted_source_treatments
from tests.test_brain_dispute_verification import Model, _candidate, _verdict

SCOPE = {"requests": [{"request_index": 0, "material_purposes": ["interpretation_review"]}]}


def judgment(state, reason, missing=()):
    return {"state": state, "reason": reason, "missing_source_ids": list(missing)}


@pytest.mark.parametrize("already_recorded", [False, True])
def test_requested_empty_review_distinguishes_omission_from_already_represented_no_change(
    already_recorded,
):
    account = "The custodian withheld the freight."
    latest = "Reconcile your saved formulation." if already_recorded else account
    earlier = (Message("old", "advocate", account),) if already_recorded else ()
    active = (
        (
            {
                "id": "old-record",
                "statement": account,
                "label": "Freight withholding",
                "source_turn_id": "old",
                "quoted": account,
            },
        )
        if already_recorded
        else ()
    )
    assessed = (
        judgment("complete", "The current record faithfully represents the earlier account.")
        if already_recorded
        else judgment("partial", "The reported withholding is omitted.", ("L1",))
    )
    model = Model([{"verdicts": [], "coverage": assessed}])
    sink = {}
    retained = disputes.verify_disputes(
        model,
        candidates=(),
        earlier=earlier,
        latest=latest,
        active_disputes=active,
        source_treatments=scripted_source_treatments(earlier, latest),
        review_scope=SCOPE,
        coverage=sink,
    )
    assert retained == ()
    assert len(model.calls) == 1
    assert sink["state"] == assessed["state"]
    payload = json.loads(model.calls[0][0].user)
    assert set(payload["coverage_source_ids"]) == set(payload["source_treatments"])
    assert payload["active_disputes"] == [
        {**row, "record_role": "nm_interpretation"} for row in active
    ]
    assert model.calls[0][1]["properties"]["verdicts"]["maxItems"] == 0
    if not already_recorded:
        assert sink["missing_sources"] == [
            {"source_id": "L1", "turn_id": "current", "role": "advocate", "quoted": account}
        ]


def test_read_only_empty_legacy_call_does_not_invent_independent_coverage():
    model = Model([])
    sink = {}
    assert (
        disputes.verify_disputes(
            model,
            candidates=(),
            earlier=(),
            latest="Repeat the location.",
            active_disputes=(),
            coverage=sink,
        )
        == ()
    )
    assert model.calls == [] and sink["state"] == "unassessed"
    assert sink["review_scope"] is None


def test_missing_coverage_gets_one_coverage_only_correction_preserving_valid_candidate():
    latest = "The custodian withheld the freight."
    candidate = _candidate(latest, "Freight withholding")
    model = Model(
        [
            {"verdicts": [_verdict("C1", accept=True)]},
            {
                "verdicts": [],
                "coverage": judgment("complete", "The accepted issue represents the account."),
            },
        ]
    )
    sink = {}
    retained = disputes.verify_disputes(
        model,
        candidates=(candidate,),
        earlier=(),
        latest=latest,
        active_disputes=(),
        source_treatments=scripted_source_treatments((), latest),
        review_scope=SCOPE,
        coverage=sink,
    )
    assert retained == (candidate,) and sink["state"] == "complete"
    assert len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert correction["candidates"] == []
    assert correction["pending_review_keys"] == ["$coverage"]
    assert correction["retained_candidate_context"][0]["candidate_id"] == "C1"
    assert correction["retained_candidate_context"][0]["decision"]["verdict"] == "accept"


def test_exhausted_coverage_is_unassessed_without_discarding_valid_candidate():
    latest = "The custodian withheld the freight."
    candidate = _candidate(latest, "Freight withholding")
    invalid = judgment("complete", "The account is both covered and still missing.", ("L1",))
    model = Model(
        [
            {"verdicts": [_verdict("C1", accept=True)], "coverage": invalid},
            {"verdicts": [], "coverage": invalid},
        ]
    )
    sink = {}
    retained = disputes.verify_disputes(
        model,
        candidates=(candidate,),
        earlier=(),
        latest=latest,
        active_disputes=(),
        source_treatments=scripted_source_treatments((), latest),
        review_scope=SCOPE,
        coverage=sink,
    )
    assert retained == (candidate,) and len(model.calls) == 2
    assert sink["state"] == "unassessed" and sink["missing_source_ids"] == []
    assert "complete contradicts nonempty missing_source_ids" in sink["validation_issue"]


def test_omission_can_select_owned_original_span_not_selected_by_any_candidate():
    first = "The custodian withheld the freight."
    second = "The identity of the custodian is unknown."
    latest = f"{first} {second}"
    candidate = _candidate(first, "Freight withholding")
    model = Model(
        [
            {
                "verdicts": [_verdict("C1", accept=True)],
                "coverage": judgment(
                    "partial", "The unidentified actor is not preserved.", ("L2",)
                ),
            }
        ]
    )
    sink = {}
    retained = disputes.verify_disputes(
        model,
        candidates=(candidate,),
        earlier=(),
        latest=latest,
        active_disputes=(),
        source_treatments=scripted_source_treatments((), latest),
        review_scope=SCOPE,
        coverage=sink,
    )
    assert retained == (candidate,) and sink["state"] == "partial"
    payload = json.loads(model.calls[0][0].user)
    assert payload["candidates"][0]["allowed_account_source_ids"] == ["L1"]
    assert payload["coverage_source_ids"] == ["L1", "L2"]
    assert sink["missing_sources"][0]["quoted"] == second
    assert len(model.calls) == 1


def test_restoration_admission_downgrade_leaves_coverage_unassessed_and_independent_peer_retained():
    original = "Two independently contested acts were reported."
    earlier = (Message("old", "advocate", original),)
    request = "Reconcile the saved account."
    peer_words = "A separate notice is contested."
    latest = f"{request} {peer_words}"
    changed = replace(
        _candidate(request, "First restored act", relation="corrects", earlier=original),
        related_dispute_ids=("old-record",),
    )
    successor = replace(changed, label="Second restored act")
    independent = _candidate(peer_words, "Notice contest")
    active = (
        {
            "id": "old-record",
            "label": "Merged account",
            "statement": original,
            "source_turn_id": "old",
            "quoted": original,
        },
    )
    first = _verdict("C1", accept=True)
    first["account_check"] = {
        "content_role": "reported_matter_account",
        "supported": True,
        "introduces_legal_analysis": False,
        "source_ids": ["P1S1"],
        "reason": "The earlier original account supplies the restored content.",
    }
    first["target_checks"] = [
        {
            "target_id": "old-record",
            "identity_relation": "restore_invalid_interpretation",
            "account_preserved": True,
            "required_peer_ids": ["C2"],
            "reason": "Both atomic successors are required.",
        }
    ]
    model = Model(
        [
            {
                "verdicts": [first, _verdict("C2", accept=False), _verdict("C3", accept=True)],
                "coverage": judgment("complete", "The proposals appear to represent the account."),
            }
        ]
    )
    sink = {}
    retained = disputes.verify_disputes(
        model,
        candidates=(changed, successor, independent),
        earlier=earlier,
        latest=latest,
        active_disputes=active,
        source_treatments=scripted_source_treatments(earlier, latest),
        review_scope=SCOPE,
        coverage=sink,
    )
    assert retained == (independent,) and len(model.calls) == 1
    assert sink["state"] == "unassessed"
    assert "C1" in sink["validation_issue"]
    assert sink["prior_assessment"]["state"] == "complete"


def test_missing_coverage_at_strict_adapter_boundary_reasks_unvalidated_candidate():
    class StrictModel(Model):
        def structured(self, prompt, schema, tier, *, max_tokens=None):
            result = super().structured(prompt, schema, tier, max_tokens=max_tokens)
            record.require_schema(result.data, schema)
            return result

    latest = "The custodian withheld the freight."
    candidate = _candidate(latest, "Freight withholding")
    model = StrictModel(
        [
            {"verdicts": [_verdict("C1", accept=True)]},
            {
                "verdicts": [_verdict("C1", accept=True)],
                "coverage": judgment("complete", "The accepted dispute represents the account."),
            },
        ]
    )
    sink = {}
    retained = disputes.verify_disputes(
        model,
        candidates=(candidate,),
        earlier=(),
        latest=latest,
        active_disputes=(),
        source_treatments=scripted_source_treatments((), latest),
        review_scope=SCOPE,
        coverage=sink,
    )
    assert retained == (candidate,) and len(model.calls) == 2
    correction = json.loads(model.calls[1][0].user)
    assert [row["candidate_id"] for row in correction["candidates"]] == ["C1"]
    assert correction["retained_candidate_context"] == []
    assert correction["pending_review_keys"] == ["C1", "$coverage"]
    assert sink["state"] == "complete"
