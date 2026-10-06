"""Broad available evidence never changes an authored fixture's primary anchor."""
from copy import deepcopy

import pytest

from tests.brain_reader_fixture import reviewed_record_verdicts


@pytest.mark.parametrize("field", ["latest_message_passage", "latest_advocate_passage"])
@pytest.mark.parametrize("explicit", [False, True])
def test_primary_fixture_anchor_is_selected_and_explicit_decisions_are_never_repaired(
        field, explicit):
    payload = {"candidates": [{"candidate_id": "D1", field: "Second original passage.",
                               "allowed_account_source_ids": ["L1", "L2"]}],
               "source_treatments": {
                   "L1": {"quoted": "First original passage."},
                   "L2": {"quoted": "Second original passage."}}}
    verdict = {"candidate_id": "D1", "verdict": "accept", "operation_supported": True,
               "reason": "The fixture owner declares this decision."}
    if explicit:
        verdict["account_check"] = {"source_ids": ["L1"], "supported": False,
                                    "source_checks": [], "reason": "Explicit faulty decision."}
    original = deepcopy((payload, verdict))
    result = reviewed_record_verdicts(payload, {"verdicts": [verdict]})
    check = result["verdicts"][0]["account_check"]
    if explicit:
        assert check == verdict["account_check"]
    else:
        assert check["source_ids"] == ["L2"]
        assert check["source_checks"][0]["source_id"] == "L2"
    assert (payload, verdict) == original
