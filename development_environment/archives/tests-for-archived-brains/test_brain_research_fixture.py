"""Fixture pool declarations cannot silently upgrade a negative Judge response."""
from copy import deepcopy

import pytest

from tests.brain_research_fixture import reviewed_retrieved_pool


def test_full_pool_judgment_requires_explicit_fixture_authorization():
    payload = {"coverage_subject_ids": ["requested"],
               "subjects": [{"subject": {"id": "requested"}, "candidates": []}]}
    data = {"decisions": [{"candidate_id": "candidate", "verdict": "supported"}]}
    original = deepcopy(data)
    assert reviewed_retrieved_pool(payload, data) == original
    assert data == original


def test_explicit_pool_judgment_covers_only_the_supplied_requested_subjects():
    payload = {"coverage_subject_ids": ["second", "first"],
               "subjects": [{"subject": {"id": identity}, "candidates": []}
                            for identity in ("first", "second", "unrequested")]}
    data = {"decisions": []}
    result = reviewed_retrieved_pool(payload, data, scripted_full_pool=True)
    assert [row["subject_id"] for row in result["subject_coverage"]] == ["second", "first"]
    assert all(row["outcome"] == "complete" and row["missing_source_ids"] == []
               for row in result["subject_coverage"])
    assert data == {"decisions": []}


@pytest.mark.parametrize("coverage", [
    [{"subject_id": "requested", "outcome": "partial", "missing_source_ids": ["source"],
      "reason": "An independently identified useful point is missing."}],
    [{"subject_id": "requested", "outcome": "unassessed", "missing_source_ids": [],
      "reason": "The independent Judge has not assessed this scope."}],
    [{"subject_id": "requested", "outcome": "complete"}],
    [],
])
def test_explicit_negative_invalid_or_missing_subject_coverage_remains_authoritative(coverage):
    payload = {"coverage_subject_ids": ["requested"]}
    data = {"decisions": [], "subject_coverage": deepcopy(coverage)}
    original = deepcopy(data)
    assert reviewed_retrieved_pool(payload, data, scripted_full_pool=True) == original
    assert data == original
