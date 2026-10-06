"""Diagnostic length cannot turn the same supported legal effect into unread work."""
from copy import deepcopy

import pytest

from nm.brain.legal_requirements import finding_verification_valid, source_verification_valid
from nm.shared.model_port import Tier
from tests.test_brain_legal_requirements import (
    CONVERSATION, MATERIAL, REQUEST_SUBJECT, Model, call_budget, finding,
    request_hits, supported_verdict, verify_findings,
)

LONG_REASON = (
    "The supplied passage supports the conditional notice proposition, while the original "
    "account leaves its factual predicate unresolved. " * 4
    + "The finding preserves the condition without proving the account."
)
assert len(LONG_REASON) == 600
REASON_PATHS = [
    ("reason",), ("label_reason",), ("source_checks", 0, "reason"),
    ("material_checks", 0, "reason"),
    *(("use_checks", aspect, "reason") for aspect in ("entailment", "application", "force")),
    ("application_premises", 0, "reason"),
]


def _fixture():
    source = deepcopy(request_hits()["q1"]["candidates"][0])
    material = deepcopy(MATERIAL["d1"][0])
    subject = {**REQUEST_SUBJECT, "scope": "current", "record_ids": [material["id"]]}
    proposed = {"q1": [{**finding(material_ids=[material["id"]]), "sources": [source]}]}
    decision = supported_verdict("r1", source["id"])
    decision.update(label_verdict="faithful", label_reason="The label preserves the conditional rule.",
                    entailment_basis="source_rule",
                    material_checks=[{"material_id":material["id"], "verdict":"addresses",
                                      "reason":"The reported document addresses this enquiry."}],
                    use_checks={aspect:{"verdict":"supported",
                        "reason":"This use preserves the source's factual and legal limits.",
                        "source_ids":[source["id"]], "material_ids":[material["id"]]}
                        for aspect in ("entailment", "application", "force")},
                    application_premises=[{"source_id":source["id"],
                        "predicate_fragment_id":"f1", "status":"unresolved", "account_source_ids":[],
                        "preserved_condition":proposed["q1"][0]["need"],
                        "reason":"The full factual condition remains unresolved in the account."}])
    decision["source_checks"][0].update(scope_status="conditional", scope_fragment_id="f1")
    return subject, material, proposed, decision


def _set_reason(decision,path,reason):
    value=decision
    for part in path[:-1]:value=value[part]
    value[path[-1]]=reason


def _review(model,subject,material,proposed):
    return verify_findings(model,subjects=(subject,),material_by_subject={"q1":[material]},
        proposed=proposed,conversation=CONVERSATION)


@pytest.mark.parametrize("path",REASON_PATHS)
@pytest.mark.parametrize("reason",["The source and account preserve this conditional use.",LONG_REASON])
def test_same_meaningful_legal_decision_accepts_once_at_short_or_600_character_reason(path,reason):
    subject,material,proposed,decision=_fixture()
    _set_reason(decision,path,reason)
    untouched=deepcopy(proposed)
    model=Model([{"decisions":[decision]}])
    result=_review(model,subject,material,proposed)
    assert len(model.calls)==1 and model.calls[0][2] is Tier.JUDGE
    assert result.coverage["q1"]["unread_items"]==0
    assert result.coverage["q1"]["withheld_items"]==0
    row=result.rows["q1"][0]
    assert source_verification_valid(row["sources"][0])
    assert finding_verification_valid(row)
    assert row["need"]==proposed["q1"][0]["need"] and row["material_ids"]==[material["id"]]
    assert proposed==untouched
    assert 0<model.calls[0][3]<=16384 and call_budget(model.calls[0])<=model.budget
    if path[0]=="source_checks":assert row["sources"][0]["verification"]["reason"]==reason
    elif path[0]=="use_checks":assert row["use_verification"]["checks"][path[1]]["reason"]==reason
    elif path[0]=="application_premises":assert row["use_verification"]["application_premises"][0]["reason"]==reason


@pytest.mark.parametrize("path",REASON_PATHS)
def test_blank_reason_cannot_attest_supported_legal_work_after_bounded_correction(path):
    subject,material,proposed,decision=_fixture()
    _set_reason(decision,path,"   ")
    model=Model([{"decisions":[decision]},{"decisions":[deepcopy(decision)]}])
    result=_review(model,subject,material,proposed)
    assert len(model.calls)==2
    assert result.rows["q1"]==[] and result.coverage["q1"]["unread_items"]==1
    assert result.coverage["q1"]["withheld_items"]==0


def test_long_saved_reason_keeps_owner_force_and_exact_source_gates_consequential():
    subject,material,proposed,decision=_fixture()
    for path in REASON_PATHS:_set_reason(decision,path,LONG_REASON)
    result=_review(Model([{"decisions":[decision]}]),subject,material,proposed)
    row=result.rows["q1"][0]
    wrong_owner=deepcopy(row);wrong_owner["sources"][0]["verification"]["assertion_owner"]="party"
    assert source_verification_valid(wrong_owner["sources"][0]) is False
    foreign_evidence=deepcopy(row);foreign_evidence["sources"][0]["verification"]["support_excerpt"]="Words absent from this source."
    assert finding_verification_valid(foreign_evidence) is False
    false_force=deepcopy(row);false_force["use_verification"]["checks"]["force"]["source_ids"]=[]
    assert finding_verification_valid(false_force) is False
    blank=deepcopy(row);blank["use_verification"]["application_premises"][0]["reason"]=" "
    assert finding_verification_valid(blank) is False
