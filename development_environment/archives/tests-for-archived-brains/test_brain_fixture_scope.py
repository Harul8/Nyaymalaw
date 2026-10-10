"""Explicit scripted scope judgments preserve real negative coverage controls."""

import json
from copy import deepcopy

import pytest

from nm.brain.dispute_verification import _schema
from nm.brain.record_review import checked_coverage
from nm.shared.model_port import Prompt, Tier, require_schema
from tests.brain_reader_fixture import reviewed_record_verdicts
from tests.test_brain_automatic_requirements import Model as AutomaticModel
from tests.test_brain_board_proposals import ScriptedBrain
from tests.test_brain_continuation_service import PublicContinuationModel
from tests.test_brain_material import Model as MaterialModel
from tests.test_brain_research_purpose import RecordResearchModel
from tests.test_brain_turn import Model as TurnModel


def scope_payload():
    return {
        "review_scope": {
            "requests": [{"request_index": 0, "material_purposes": ["interpretation_review"]}]
        },
        "coverage_source_ids": ["P1S1", "L1"],
        "candidates": [],
    }


@pytest.mark.parametrize("executed", [False, True])
def test_bare_verdict_and_execution_never_supply_a_coverage_judgment(executed):
    payload = scope_payload()
    payload["material_coverage"] = {"execution": {"returned": executed}}
    result = reviewed_record_verdicts(payload, {"verdicts": []})
    assert "coverage" not in result


@pytest.mark.parametrize("candidates", [[], [{"candidate_id": "D1"}]])
def test_explicit_normal_fixture_judgment_accepts_legitimate_empty_or_nonempty_read(candidates):
    payload = scope_payload()
    payload["candidates"] = candidates
    result = reviewed_record_verdicts(payload, {"verdicts": []}, scripted_full_scope=True)
    assert (
        checked_coverage(result["coverage"], tuple(payload["coverage_source_ids"]))["state"]
        == "complete"
    )
    assert result["coverage"]["missing_source_ids"] == []


@pytest.mark.parametrize(
    "coverage",
    [
        {
            "state": "partial",
            "missing_source_ids": [],
            "reason": "The reconciliation scope remains unresolved.",
        },
        {
            "state": "partial",
            "missing_source_ids": ["P1S1"],
            "reason": "The original event is materially omitted.",
        },
        {
            "state": "unassessed",
            "missing_source_ids": [],
            "reason": "The reviewer could not finish the complete scope.",
        },
        {
            "state": "complete",
            "missing_source_ids": ["foreign"],
            "reason": "An explicitly contradictory fixture judgment.",
        },
        {"state": "wrong", "missing_source_ids": [], "reason": "An explicitly malformed state."},
        None,
    ],
)
def test_explicit_negative_or_invalid_coverage_is_never_repaired(coverage):
    data = {"verdicts": [], "coverage": deepcopy(coverage)}
    before = deepcopy(data)
    result = reviewed_record_verdicts(scope_payload(), data, scripted_full_scope=True)
    assert result == before and data == before


@pytest.mark.parametrize("missing", ["review_scope", "coverage_source_ids"])
def test_normal_fixture_judgment_is_only_supplied_for_requested_independent_scope(missing):
    payload = scope_payload()
    payload.pop(missing)
    assert "coverage" not in reviewed_record_verdicts(
        payload, {"verdicts": []}, scripted_full_scope=True
    )


@pytest.mark.parametrize(
    "factory,empty_only",
    [
        (lambda: TurnModel([]), True),
        (lambda: PublicContinuationModel([], []), True),
        (lambda: MaterialModel([]), False),
        (lambda: ScriptedBrain([]), False),
        (lambda: AutomaticModel([]), False),
        (lambda: RecordResearchModel([], [], dispute_reads=[]), False),
    ],
)
def test_public_fixture_owns_new_empty_dispute_judge_call_without_consuming_routes(
    factory, empty_only
):
    payload = scope_payload()
    model = factory()
    schema = _schema((), (), (), coverage_ids=tuple(payload["coverage_source_ids"]))
    result = model.structured(
        Prompt(
            system="Offline fixture check", user=json.dumps(payload), operation="verify_disputes"
        ),
        schema,
        Tier.JUDGE,
    )
    require_schema(result.data, schema)
    assert result.data["verdicts"] == []
    assert result.data["coverage"]["state"] == "complete"
    if empty_only:
        payload["candidates"] = [{"candidate_id": "C1"}]
        with pytest.raises(AssertionError, match="empty dispute review only"):
            model.structured(
                Prompt(
                    system="Offline fixture check",
                    user=json.dumps(payload),
                    operation="verify_disputes",
                ),
                schema,
                Tier.JUDGE,
            )
