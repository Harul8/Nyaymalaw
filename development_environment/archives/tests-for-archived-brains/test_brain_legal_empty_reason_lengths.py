"""Long bounded-empty explanations preserve useful outcomes without retries."""
from copy import deepcopy

import pytest

from nm.brain.legal_requirements import empty_reading_verification_valid
from nm.shared.model_port import Tier
from tests.test_brain_legal_empty_reading import check, reply, review
from tests.test_brain_legal_requirements import Model, call_budget, request_hits

LONG_REASON = (
    "The supplied passage supports the conditional notice proposition, while the original "
    "account leaves its factual predicate unresolved. " * 4
    + "The finding preserves the condition without proving the account."
)
assert len(LONG_REASON)==600


@pytest.mark.parametrize("outcome,derived,state",[
    ("no_supported_finding","no_supported_finding","ok"),
    ("supports_useful_finding","findings_omitted","partial"),
    ("uncertain","uncertain","partial")])
@pytest.mark.parametrize("reason",["The supplied text permits this bounded source decision.",LONG_REASON])
def test_same_bounded_empty_decision_retains_short_or_long_reason_in_one_call(outcome,derived,state,reason):
    source_check={**check(outcome=outcome),"reason":reason}
    model=Model([{"readings":[reply(checks=[source_check])]}])
    searches=request_hits();untouched=deepcopy(searches)
    result=review(model,searches=searches)
    assert len(model.calls)==1 and model.calls[0][2] is Tier.JUDGE
    coverage=result.coverage["q1"]
    assert coverage["state"]==state and coverage["unread_items"]==0
    receipt=coverage["empty_reading"]
    assert receipt["outcome"]==derived and receipt["source_checks"]==[source_check]
    assert receipt["sources"]==untouched["q1"]["candidates"]
    assert empty_reading_verification_valid(receipt,subject_id="q1")
    assert searches==untouched
    assert 0<model.calls[0][3]<=16384 and call_budget(model.calls[0])<=model.budget


def test_blank_empty_reason_cannot_attest_empty_work_after_one_correction():
    blank={**check(),"reason":"   "}
    model=Model([{"readings":[reply(checks=[blank])]},{"readings":[reply(checks=[deepcopy(blank)])]}])
    result=review(model,searches=request_hits())
    assert len(model.calls)==2
    assert result.coverage["q1"]["unread_items"]==1
    assert "empty_reading" not in result.coverage["q1"]


def test_long_saved_empty_reason_does_not_relax_owned_source_or_derived_outcome_checks():
    long_check={**check(),"reason":LONG_REASON}
    result=review(Model([{"readings":[reply(checks=[long_check])]}]),searches=request_hits())
    receipt=result.coverage["q1"]["empty_reading"]
    foreign=deepcopy(receipt);foreign["source_checks"][0]["source_id"]="foreign-source"
    false_complete=deepcopy(receipt);false_complete["source_checks"][0]["outcome"]="supports_useful_finding"
    blank=deepcopy(receipt);blank["source_checks"][0]["reason"]=" "
    assert empty_reading_verification_valid(foreign,subject_id="q1") is False
    assert empty_reading_verification_valid(false_complete,subject_id="q1") is False
    assert empty_reading_verification_valid(blank,subject_id="q1") is False
