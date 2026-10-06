"""Fresh coverage must depend on each candidate's actual original support."""

from copy import deepcopy

import pytest

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

FIRST = "The tenant returned the key at the station."
SECOND = "The witness reports the parcel arrived sealed."
MESSAGE = FIRST + "\n" + SECOND
pytestmark = pytest.mark.parametrize("kind", ["material"])


def test_other_source_cannot_borrow_a_candidate_and_repairs_only_coverage(kind):
    references, treatments = source_catalogue(MESSAGE)
    identity = candidate_id(kind)
    bad = coverage(references, dispositions=[
        disposition(source, reference, status="represented", candidate_ids=[identity])
        for source, reference in references.items()])
    correct = coverage(references, state="partial", dispositions=[
        disposition("L1", references["L1"], status="represented", candidate_ids=[identity]),
        disposition("L2", references["L2"]),
    ])
    proposed = proposal(kind, FIRST)
    model = RawJudge([
        {"verdicts": [verdict(kind, references["L1"])], "coverage": bad},
        {"verdicts": [], "coverage": correct},
    ])
    retained, assessed, _, _ = review(
        kind, model, MESSAGE, candidates=[proposed], treatments=treatments)
    assert retained == (proposed,)
    assert assessed["state"] == "partial"
    assert assessed["missing_source_ids"] == ["L2"]
    assert len(model.calls) == 2
    correction = model.calls[1]["payload"]
    assert correction["candidates"] == []
    assert "original source portion" in correction.get(
        "coverage_validation_issue", correction["validation_issue"])


def test_each_original_portion_has_its_own_checked_candidate_without_retry(kind):
    references, treatments = source_catalogue(MESSAGE)
    candidates = [proposal(kind, FIRST), proposal(kind, SECOND)]
    checked = [verdict(kind, references[source], index=index, source_id=source)
               for index, source in enumerate(references, 1)]
    assessed = coverage(references, dispositions=[
        disposition(source, reference, status="represented",
                    candidate_ids=[candidate_id(kind, index)])
        for index, (source, reference) in enumerate(references.items(), 1)])
    model = RawJudge([{"verdicts": checked, "coverage": assessed}])
    retained, assessed, _, _ = review(
        kind, model, MESSAGE, candidates=candidates, treatments=treatments)
    assert retained == tuple(candidates)
    assert assessed["state"] == "complete"
    assert len(model.calls) == 1


def test_repeated_wrong_representation_keeps_checked_work_without_false_complete(kind):
    references, treatments = source_catalogue(MESSAGE)
    identity = candidate_id(kind)
    bad = coverage(references, dispositions=[
        disposition(source, reference, status="represented", candidate_ids=[identity])
        for source, reference in references.items()])
    first = {"verdicts": [verdict(kind, references["L1"])], "coverage": bad}
    model = RawJudge([first, {"verdicts": [], "coverage": deepcopy(bad)}])
    proposed = proposal(kind, FIRST)
    retained, assessed, _, _ = review(
        kind, model, MESSAGE, candidates=[proposed], treatments=treatments)
    assert retained == (proposed,)
    assert assessed["state"] == "unassessed"
    assert len(model.calls) == 2
