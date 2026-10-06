"""Endpoint diagnostics preserve owned context and existing bounded recovery.

These synthetic decisions test mechanical feedback, not semantic model quality.
Invalid types exercise the source owner directly; provider schema failures are
outside this endpoint-diagnostic slice.
"""

from copy import deepcopy

import pytest

from nm.brain import record_review as record
from nm.shared.model_port import SchemaViolation
from tests.brain_reader_fixture import fresh_review_reply
from tests.test_brain_source_owner_portion_contract import RawReplies, declared, read
from tests.test_brain_source_support_verifiers import (
    RawJudge,
    candidate_id,
    coverage,
    disposition,
    proposal,
    review,
    source_catalogue,
    verdict,
)

LONG_ACCOUNT = "The custodian reports that the northern parcel arrived with its seal intact."
SHORT_ACCOUNT = "The second parcel is missing."
MESSAGE = LONG_ACCOUNT + "\n" + SHORT_ACCOUNT


def assert_endpoint_feedback(message, *, source_id, start, end, length, reason):
    """Require correction evidence without fixing unrelated sentence wording."""
    assert f"source_id={source_id}" in message
    assert f"start={start!r}" in message
    assert f"end={end!r}" in message
    assert f"length={length}" in message
    assert reason in message.lower()


@pytest.mark.parametrize("start,end,reason", [
    (0, len(SHORT_ACCOUNT) + 1, "bound"),
    (-1, 3, "bound"),
    (4, 2, "start < end"),
    (3, 3, "start < end"),
    (True, 3, "integer"),
    (0, False, "integer"),
    ("0", 3, "integer"),
    (0, 3.0, "integer"),
])
def test_support_owner_names_source_attempted_endpoints_and_precise_failure(start, end, reason):
    references, treatments = source_catalogue(MESSAGE)
    row = verdict("material", references["L2"], source_id="L2", bounds=(start, end))
    before = deepcopy(row), deepcopy(treatments)

    with pytest.raises(SchemaViolation) as failure:
        record.validate_record_checks(
            row, source_ids={"L2"}, target_ids=set(), candidate_id="D1",
            candidates={"D1": set()}, source_treatments=treatments)

    assert (row, treatments) == before
    assert_endpoint_feedback(
        str(failure.value), source_id="L2", start=start, end=end,
        length=len(SHORT_ACCOUNT), reason=reason)


@pytest.mark.parametrize("operation", ["classify", "reconsider"])
def test_source_owner_correction_names_the_reversed_range_without_another_call(operation):
    bad = declared("reported_matter_account", [{"start": 4, "end": 2}])
    good = declared("reported_matter_account", [{"start": 0, "end": len(SHORT_ACCOUNT)}])
    model = RawReplies([bad, good], strict=True)

    result, _ = read(operation, model, SHORT_ACCOUNT)

    assert len(model.calls) == 2
    assert result["L1"]["substantive_spans"][0]["quoted"] == SHORT_ACCOUNT
    correction = model.calls[1]["input"]
    assert_endpoint_feedback(
        correction["validation_issue"], source_id="L1", start=4, end=2,
        length=len(SHORT_ACCOUNT), reason="start < end")
    assert correction["original_input"] == model.calls[0]["input"]


@pytest.mark.parametrize("kind", ["material", "dispute"])
@pytest.mark.parametrize("start,end,reason", [
    (0, len(SHORT_ACCOUNT) + 1, "bound"),
    (4, 2, "start < end"),
])
def test_review_correction_localises_short_source_and_preserves_checked_peer(
        kind, start, end, reason):
    references, treatments = source_catalogue(MESSAGE)
    candidates = (proposal(kind, LONG_ACCOUNT), proposal(kind, SHORT_ACCOUNT))
    peer = verdict(kind, references["L1"])
    bad = verdict(kind, references["L2"], index=2, source_id="L2", bounds=(start, end))
    initial = {"verdicts": [peer, bad], "coverage": coverage(
        references, state="partial", dispositions=[
            disposition("L1", references["L1"], status="represented",
                        candidate_ids=(candidate_id(kind),)),
            disposition("L2", references["L2"]),
        ])}
    corrected = {"verdicts": [verdict(kind, references["L2"], index=2, source_id="L2")],
                 "coverage": coverage(references, dispositions=[
                     disposition(identity, reference, status="represented",
                                 candidate_ids=(candidate_id(kind, index),))
                     for index, (identity, reference) in enumerate(references.items(), 1)])}
    model = RawJudge([initial, corrected])
    before = deepcopy(treatments)

    retained, assessed, _, _ = review(
        kind, model, MESSAGE, candidates=candidates, treatments=treatments)

    assert retained == candidates
    assert assessed["state"] == "complete"
    assert len(model.calls) == 2
    assert treatments == before
    correction = model.calls[1]["payload"]
    assert [row["candidate_id"] for row in correction["candidates"]] == [candidate_id(kind, 2)]
    assert [row["candidate_id"] for row in correction["retained_candidate_context"]] == [
        candidate_id(kind)]
    assert correction["latest_message_spans"] == model.calls[0]["payload"]["latest_message_spans"]
    assert correction["source_treatments"] == references
    assert candidate_id(kind, 2) + ":" in correction["validation_issue"]
    assert_endpoint_feedback(
        correction["validation_issue"], source_id="L2", start=start, end=end,
        length=len(SHORT_ACCOUNT), reason=reason)


@pytest.mark.parametrize("location", ["source_check", "disposition"])
@pytest.mark.parametrize("start,end,reason", [
    (0, len(SHORT_ACCOUNT) + 1, "bound"),
    (4, 2, "start < end"),
])
def test_coverage_owner_names_the_exact_source_range(location, start, end, reason):
    references, _ = source_catalogue(MESSAGE)
    row = coverage(references, state="partial", dispositions=[
        disposition(identity, reference) for identity, reference in references.items()])
    if location == "source_check":
        row["source_checks"][1]["substantive_spans"] = [{"start": start, "end": end}]
    else:
        row["dispositions"][1].update(start=start, end=end)
    before = deepcopy(row), deepcopy(references)

    with pytest.raises(SchemaViolation) as failure:
        record.checked_coverage(row, tuple(references), source_references=references)

    assert (row, references) == before
    assert_endpoint_feedback(
        str(failure.value), source_id="L2", start=start, end=end,
        length=len(SHORT_ACCOUNT), reason=reason)


@pytest.mark.parametrize("words,start,end", [
    ("Ω", 0, 1),
    ("The witness said ‘perhaps’.", 17, 26),
    ("No delivery was confirmed.", 0, 26),
])
def test_valid_exact_source_spans_keep_their_original_words_and_anchors(words, start, end):
    reference = {"turn_id": "original", "role": "advocate", "quoted": words}
    selections = [{"start": start, "end": end}]
    before = deepcopy(reference), deepcopy(selections)

    result = record.owned_source_portions(reference, selections)

    assert result[0]["quoted"] == words[start:end]
    assert (result[0]["start"], result[0]["end"]) == (start, end)
    assert result[0]["anchor_id"].startswith("asp_")
    assert result == record.owned_source_portions(reference, selections)
    assert (reference, selections) == before


@pytest.mark.parametrize("kind", ["material", "dispute"])
def test_valid_support_and_coverage_keep_the_one_call_path(kind):
    references, treatments = source_catalogue(MESSAGE)
    candidates = (proposal(kind, LONG_ACCOUNT), proposal(kind, SHORT_ACCOUNT))
    output = {"verdicts": [
        verdict(kind, reference, index=index, source_id=identity)
        for index, (identity, reference) in enumerate(references.items(), 1)],
        "coverage": coverage(references, dispositions=[
            disposition(identity, reference, status="represented",
                        candidate_ids=(candidate_id(kind, index),))
            for index, (identity, reference) in enumerate(references.items(), 1)])}
    model = RawJudge([output])

    retained, assessed, _, _ = review(
        kind, model, MESSAGE, candidates=candidates, treatments=treatments)

    assert retained == candidates
    assert assessed["state"] == "complete"
    assert len(model.calls) == 1
    assert model.calls[0]["output"] == fresh_review_reply(model.calls[0]["payload"], output)
