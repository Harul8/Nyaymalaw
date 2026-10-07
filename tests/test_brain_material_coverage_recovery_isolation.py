"""Opening-only recovery cannot invalidate independent checked detail coverage.

All meanings and verdicts are explicitly scripted. These offline tests exercise
the actual material owner, strict completed-object quarantine and turn ledger;
they do not qualify a real model's source interpretation or useful delivery.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review
from nm.brain.conversation import OpeningCandidate
from nm.brain.turn import _CountedModel
from nm.shared.model_port import (
    ContentRefused,
    ContextOverflow,
    OutputTruncated,
    ProviderUnavailable,
    RateLimited,
)
from tests.brain_verdict_quarantine_support import Judge
from tests.test_brain_material_coverage import detail
from tests.test_brain_material_coverage_domain import (
    FIRST,
    SECOND,
    WORDS,
    coverage,
    current_record,
    positive,
    run,
    sources,
)
from tests.test_brain_source_support_verifiers import RawJudge

pytestmark = pytest.mark.class_a
KNOWN_FAILURES = [
    ProviderUnavailable, ContextOverflow, OutputTruncated, ContentRefused, RateLimited,
]


def original_payload(latest=FIRST):
    return {"source_treatments": {
        identity: {field: row[field] for field in ("turn_id", "role", "quoted")}
        for identity, row in sources((), latest).items()}}


def initial_checked_work(representation):
    payload = original_payload()
    selected = ("represented", ("current-material",), ()) if representation == "current" else (
        "represented", (), ("D1",))
    return {"verdicts": [positive(payload, "D1")],
            "coverage": coverage(payload, {"L1": selected})}


def original_assessment(output, representation):
    references = original_payload()["source_treatments"]
    return record_review.checked_coverage(
        output["coverage"], tuple(references), source_references=references,
        record_ids=("current-material",) if representation == "current" else (),
        candidate_ids=("D1",), admitted_candidate_ids=("D1",),
        candidate_support={"D1": output["verdicts"][0]})


def review_opening_and_detail(port, representation):
    candidate = detail(FIRST)
    current = (current_record("current-material"),) if representation == "current" else ()
    before = deepcopy((candidate, current))
    model = _CountedModel(port, recovery_limit=1, reply_recovery_reserve=0)
    cache = {}
    result, sink = run(model, candidates=(candidate,), active_material=current,
                       opening=OpeningCandidate(True, "Reported document custody", FIRST),
                       cache=cache)
    assert (candidate, current) == before
    assert result.details == (candidate,)
    assert set(cache["cache"].decisions) >= {"D1"}
    assert model.metrics()["llm_calls"] == 2
    recovery = model.metrics()["recovery"]
    assert recovery["reserved_calls"] == recovery["dispatched_calls"] == 1
    assert [row["phase"] for row in recovery["events"]] == [
        "verify_material_grounding:correction"]
    return result, sink, cache


def assert_original_coverage(sink, expected):
    assert sink["state"] == "complete"
    assert sink["missing_source_ids"] == sink["missing_sources"] == []
    for field, value in expected.items():
        assert sink[field] == value
    assert sink["contract"] == record_review.ACCOUNT_COVERAGE_CONTRACT
    assert "validation_issue" not in sink
    assert "previous_assessment" not in sink
    assert "admission_holds" not in sink


@pytest.mark.parametrize("representation", ["candidate", "current"])
def test_opening_only_correction_schema_does_not_request_another_material_assessment(
        representation):
    first = initial_checked_work(representation)
    corrected = {"verdicts": [positive(original_payload(), "O1")]}
    port = RawJudge([first, corrected])

    result, sink, _ = review_opening_and_detail(port, representation)

    initial, correction = port.calls
    assert set(initial["schema"]["required"]) == {"source_readings", "verdicts", "coverage"}
    assert correction["schema"]["required"] == ["source_readings", "verdicts"]
    assert "coverage" not in correction["schema"]["properties"]
    assert [row["candidate_id"] for row in correction["payload"]["candidates"]] == ["O1"]
    assert [row["candidate_id"] for row in correction["payload"][
        "retained_candidate_context"]] == ["D1"]
    assert correction["payload"]["source_treatments"] == initial["payload"]["source_treatments"]
    assert correction["payload"]["latest_message_spans"] == initial["payload"][
        "latest_message_spans"]
    assert "Return coverage" not in correction["payload"]["validation_issue"]
    assert result.opening_supported and not result.opening_unread
    assert_original_coverage(sink, original_assessment(first, representation))


@pytest.mark.parametrize("representation", ["candidate", "current"])
@pytest.mark.parametrize("failure", KNOWN_FAILURES)
def test_owned_detail_assessment_survives_opening_only_provider_failure(representation, failure):
    first = initial_checked_work(representation)
    port = Judge([first, failure("The conditional opening review is unavailable.")])

    result, sink, cache = review_opening_and_detail(port, representation)

    assert result.opening_unread and not result.opening_supported
    assert [row["candidate_id"] for row in result.unread_proposals] == ["O1"]
    assert cache["cache"].decisions["D1"] == first["verdicts"][0]
    assert_original_coverage(sink, original_assessment(first, representation))


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("representation", ["candidate", "current"])
def test_owned_detail_assessment_survives_malformed_opening_only_verdict(representation, strict):
    first = initial_checked_work(representation)
    malformed = positive(original_payload(), "O1")
    del malformed["account_check"]
    correction = {"verdicts": [malformed]}
    port = Judge([first, correction]) if strict else RawJudge([first, correction])

    result, sink, cache = review_opening_and_detail(port, representation)

    assert result.opening_unread and not result.opening_supported
    assert [row["candidate_id"] for row in result.unread_proposals] == ["O1"]
    assert cache["cache"].decisions["D1"] == first["verdicts"][0]
    assert_original_coverage(sink, original_assessment(first, representation))
    if strict:
        assert len(port.quarantined) == 1


@pytest.mark.parametrize("failure", KNOWN_FAILURES)
def test_unread_detail_dependency_still_requires_coverage_after_conditional_failure(failure):
    payload = original_payload(WORDS)
    first = {"verdicts": [positive(payload, "D1")], "coverage": coverage(payload, {
        "L1": ("represented", (), ("D1",)), "L2": ("missing", (), ())})}
    port = Judge([first, failure("A pending detail has not received its independent review.")])
    model = _CountedModel(port, recovery_limit=1, reply_recovery_reserve=0)
    first_candidate, unread_candidate = detail(FIRST), detail(SECOND)

    result, sink = run(model, candidates=(first_candidate, unread_candidate), latest=WORDS,
                       opening=OpeningCandidate(True, "Reported separate documents", WORDS))

    assert result.details == (first_candidate,)
    assert result.unread_details == 1 and result.opening_unread
    assert sink["state"] != "complete" and sink["missing_source_ids"] == ["L2"]
    assert [row["candidate_id"] for row in sink["admission_holds"]] == ["D2"]
    assert sink["dispositions"][0]["candidate_ids"] == ["D1"]
    correction = port.calls[1]
    assert "coverage" in correction["schema"]["required"]
    assert [row["candidate_id"] for row in correction["payload"]["candidates"]] == ["D2", "O1"]
    assert model.metrics()["recovery"]["reserved_calls"] == 1


@pytest.mark.parametrize("defect", ["missing", "foreign_record", "contradictory_purpose"])
def test_invalid_initial_coverage_cannot_be_promoted_by_opening_only_recovery(defect):
    first = initial_checked_work("candidate")
    if defect == "missing":
        del first["coverage"]
    elif defect == "foreign_record":
        first["coverage"]["dispositions"][0].update(
            record_ids=["another-owner"], candidate_ids=[])
    else:
        first["coverage"]["source_checks"][0]["content_purpose"] = "non_account"
    port = Judge([first, ProviderUnavailable("Unconfirmed coverage cannot be inferred.")])

    result, sink, _ = review_opening_and_detail(port, "candidate")

    assert result.opening_unread and sink["state"] == "unassessed"
    assert "validation_issue" in sink and "previous_assessment" not in sink
    assert "coverage" in port.calls[1]["schema"]["required"]


def test_unread_full_envelope_still_blocks_material_coverage_despite_positive_detail():
    first = initial_checked_work("candidate")
    first["unknown_shell_content"] = "This has no declared owner."
    correction = {"verdicts": [], "coverage": deepcopy(first["coverage"]),
                  "unknown_shell_content": "The whole envelope remains unread."}
    port = Judge([first, correction])

    result, sink, _ = review_opening_and_detail(port, "candidate")

    assert result.opening_unread and sink["state"] == "unassessed"
    assert "envelope" in sink["validation_issue"]
    assert sink["previous_assessment"]["state"] == "complete"
    assert "coverage" in port.calls[1]["schema"]["required"]
    assert "$envelope" in port.calls[1]["payload"]["validation_issue"]
