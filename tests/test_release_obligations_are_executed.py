"""Release profiles enumerate obligations; bound outcomes decide their state."""
from __future__ import annotations

import copy

import pytest

from tools import backlog
from tools.release_obligations import mapping_problems, obligations

pytestmark = pytest.mark.class_a


def _criterion(*, effective="PASS", levels=("domain_test",)) -> dict:
    evidence = {}
    for level in levels:
        row = {"result": "PASS", "ref": f"tests/probe.py::test_{level}"}
        if effective is not None:
            row["_effective_result"] = effective
        evidence[level] = row
    return {
        "id": "BK-X-AC1", "requirement": "the control is actually enforced",
        "required_evidence": list(levels), "evidence": evidence,
    }


def _doc(*, effective="PASS", levels=("domain_test",)) -> dict:
    return {
        "items": [{
            "id": "BK-X", "implementation": "complete",
            "acceptance": [_criterion(effective=effective, levels=levels)],
        }, {
            "id": "BK-Y", "implementation": "complete",
            "acceptance": [dict(_criterion(effective=effective), id="BK-Y-AC1")],
        }],
        "plan": {"release_profiles": [{
            "id": "pilot", "required_items": ["BK-X"],
            "required_criteria": ["BK-X-AC1"],
            "conditional_items": [{"when": "feature Y is enabled", "items": ["BK-Y"]}],
        }, {
            "id": "production", "required_items": ["BK-X"],
            "required_criteria": ["BK-X-AC1"], "conditional_items": [],
        }]},
        "professional": {
            "advocate_standards": [{"id": "PA-01", "work_items": ["BK-X"]}],
            "workflow_states": [], "advice_maturity": [], "roles": [],
        },
    }


def test_a_bound_complete_population_can_complete_its_profile():
    report = obligations(_doc(), "pilot")
    assert report.problems == ()
    assert report.complete
    assert {row.identifier for row in report.rows} == {"BK-X-AC1", "PA-01"}


def test_a_test_name_or_authored_pass_without_execution_is_not_enforcement():
    report = obligations(_doc(effective=None), "pilot")
    criterion = next(row for row in report.rows if row.kind == "criterion")
    assert criterion.state == "NOT_RUN"
    assert "no bound execution result" in criterion.reasons[0]
    assert not report.complete


@pytest.mark.parametrize("effective", ["NOT_RUN", "STALE", "FAIL"])
def test_uncollected_skipped_stale_or_failed_evidence_blocks(effective):
    report = obligations(_doc(effective=effective), "pilot")
    assert not report.complete
    assert next(row for row in report.rows if row.kind == "criterion").state == effective


def test_removing_or_inventing_a_profile_criterion_is_identified():
    document = _doc()
    document["plan"]["release_profiles"][0]["required_criteria"] = []
    assert any("omits required criteria: BK-X-AC1" in problem
               for problem in mapping_problems(document))

    document = _doc()
    document["plan"]["release_profiles"][0]["required_criteria"].append("BK-Z-AC9")
    found = mapping_problems(document)
    assert any("outside its items" in problem for problem in found)
    assert any("unknown criteria" in problem for problem in found)


def test_status_change_recomputes_professional_coverage():
    document = _doc()
    assert obligations(document, "pilot").complete
    document["items"][0]["implementation"] = "partial"
    report = obligations(document, "pilot")
    professional = next(row for row in report.rows if row.kind == "advocate_standards")
    assert professional.state == "NOT_RUN"
    assert "BK-X" in professional.reasons[0]


def test_missing_professional_review_is_visible_in_both_populations():
    document = _doc(levels=("domain_test", "counsel_review"))
    del document["items"][0]["acceptance"][0]["evidence"]["counsel_review"]
    report = obligations(document, "pilot")
    criterion = next(row for row in report.rows if row.kind == "criterion")
    professional = next(row for row in report.rows if row.kind == "advocate_standards")
    assert criterion.state == professional.state == "NOT_RUN"
    assert any("counsel_review is NOT_RUN" in reason for reason in criterion.reasons)


def test_conditional_scope_adds_only_the_named_profile_population():
    document = _doc()
    pilot = obligations(document, "pilot", activated_items=["BK-Y"])
    production = obligations(document, "production")
    assert "BK-Y-AC1" in {row.identifier for row in pilot.rows}
    assert "BK-Y-AC1" not in {row.identifier for row in production.rows}


def test_unknown_conditional_activation_is_refused():
    report = obligations(_doc(), "pilot", activated_items=["BK-Z"])
    assert any("cannot activate" in problem for problem in report.problems)
    assert not report.complete


def test_the_real_release_profile_mapping_is_exact_and_the_probe_bites():
    document = backlog.load()
    assert mapping_problems(document) == []

    unexecuted = obligations(_doc(effective=None), "pilot")
    assert not unexecuted.complete
    assert any("no bound execution result" in reason
               for row in unexecuted.rows for reason in row.reasons)

    changed = copy.deepcopy(document)
    pilot = next(row for row in changed["plan"]["release_profiles"]
                 if row["id"] == "pilot")
    removed = pilot["required_criteria"].pop()
    found = mapping_problems(changed)
    assert any(removed in problem and "omits required criteria" in problem
               for problem in found), found
