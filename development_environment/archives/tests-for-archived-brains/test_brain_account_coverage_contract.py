"""Independent account coverage states and owned-source mechanics."""

import pytest

from nm.brain import record_review as record


def judgment(state, reason, missing=()):
    return {"state": state, "reason": reason, "missing_source_ids": list(missing)}


@pytest.mark.parametrize(
    "value,expected",
    [
        (judgment("complete", "The current record already represents this account."), []),
        (
            judgment(
                "partial", "The reconciliation scope remains incomplete but is not localizable."
            ),
            [],
        ),
        (
            judgment("partial", "  The reported actor uncertainty is missing.  ", ("L1", "L1")),
            ["L1"],
        ),
        (judgment("unassessed", "The needed distinction could not be evaluated."), []),
        (judgment("unassessed", "The account framing remains unresolved.", ("L1",)), ["L1"]),
    ],
)
def test_checked_coverage_admits_legitimate_states_and_only_normalizes_formatting(value, expected):
    result = record.checked_coverage(value, ("L1",))
    assert result["missing_source_ids"] == expected
    assert result["reason"] == value["reason"].strip()
    assert result["state"] == value["state"]


@pytest.mark.parametrize(
    "value",
    [
        judgment("complete", "Missing account remains.", ("L1",)),
        judgment("partial", "Wrong owner.", ("foreign",)),
        judgment("unassessed", "   "),
    ],
)
def test_checked_coverage_rejects_consequential_contract_errors(value):
    with pytest.raises(record.SchemaViolation):
        record.checked_coverage(value, ("L1",))
