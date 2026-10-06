"""Offline tier receipts do not establish reviewer semantic quality."""
from dataclasses import replace

import pytest

from nm.brain.checked import require_independent_result
from nm.shared.budget_contracts import Completion
from nm.shared.model_port import ModelResult, Tier, TierUnavailable, Usage


def result():
    return ModelResult(text=None, data={}, tier=Tier.JUDGE, provider="offline",
                       model="offline", usage=Usage(0, 0, 0), latency_ms=0,
                       completion=Completion.COMPLETE)


def test_actual_judge_receipt_passes_without_an_extra_call():
    require_independent_result(result())


@pytest.mark.parametrize("flag", [None, Tier.JUDGE])
def test_routine_receipt_cannot_be_independent_evidence_even_without_downgrade_flag(flag):
    with pytest.raises(TierUnavailable, match="independent review"):
        require_independent_result(replace(result(), tier=Tier.ROUTINE, downgraded_from=flag))


def test_flagged_fallback_cannot_be_independent_evidence_even_with_judge_label():
    with pytest.raises(TierUnavailable, match="independent review"):
        require_independent_result(replace(result(), downgraded_from=Tier.JUDGE))
