"""Independent mutation controls for specification coverage, never legal quality."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools._documents import safe_load
from tools.blueprint_evaluations import check_evaluations, deployment_blockers

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    catalog = json.loads((ROOT / "docs/blueprint/evaluations.json").read_text(encoding="utf-8"))
    registry = safe_load((ROOT / "docs/backlog/status.yaml").read_text(encoding="utf-8"))
    criteria = {ac["id"] for row in registry["items"] for ac in row.get("acceptance", [])}
    return catalog, criteria


def test_evaluation_specifications_are_nonempty_and_not_execution_evidence():
    catalog, criteria = _inputs()
    assert len(catalog["synthetic_cases"]) >= 30
    assert len(catalog["release_portfolios"]) == 6
    assert len(catalog["manual_review_protocols"]) == 5
    assert check_evaluations(catalog, criteria) == []
    assert deployment_blockers(catalog)
    assert all(not row["evidence"] for row in catalog["release_portfolios"])


def test_empty_actual_populations_are_honest_specifications_but_not_release_proof():
    catalog, criteria = _inputs()
    for portfolio in catalog["release_portfolios"]:
        portfolio["members"] = []
    assert check_evaluations(catalog, criteria) == []
    blockers = deployment_blockers(catalog)
    for portfolio in catalog["release_portfolios"]:
        assert any(f"{portfolio['id']}: 0/{portfolio['minimum_count']} actual members" in error
                   for error in blockers)


@pytest.mark.parametrize("probe, expected", [
    ("empty_cases", "empty or malformed population"),
    ("removed_case_and_reduced_count", "missing baseline case"),
    ("duplicate_case", "duplicate or missing baseline case"),
    ("missing_path", "missing required scenario paths"),
    ("shrunk_module_baseline", "required_modules must retain"),
    ("unknown_criterion", "unknown owner criterion"),
    ("empty_fixture", "empty or malformed fixture inputs"),
    ("missing_expected_value", "observation: unsupported or missing fields"),
    ("unknown_operator", "invalid observation path or operator"),
    ("empty_refusal", "empty mutation or intended refusal"),
    ("claimed_pass", "specification cannot claim executed proof"),
    ("claimed_evidence", "specification cannot claim executed proof"),
    ("unknown_field", "unsupported or missing fields"),
    ("network_enabled", "network-denied boundary required"),
    ("empty_portfolios", "empty or malformed definitions"),
    ("shrunk_portfolio_minimum", "minimum cannot shrink"),
    ("strata_count_mismatch", "strata do not reconcile"),
    ("stratum_removed_count_preserved", "required primary stratum"),
    ("empty_overlay", "malformed overlay minima"),
    ("placeholder_member", "member missing required fields"),
    ("empty_protocols", "empty or malformed protocols"),
    ("empty_review_tasks", "empty or malformed tasks"),
    ("self_signed_review", "cannot self-certify approval"),
])
def test_specification_controls_reject_each_planted_mutation(probe, expected):
    catalog, criteria = _inputs()
    assert check_evaluations(catalog, criteria) == []
    original = deepcopy(catalog)
    case = catalog["synthetic_cases"][0]
    portfolio = catalog["release_portfolios"][0]
    if probe == "empty_cases":
        catalog["synthetic_cases"].clear()
    elif probe == "removed_case_and_reduced_count":
        catalog["synthetic_cases"].pop()
        catalog["synthetic_case_count"] -= 1
    elif probe == "duplicate_case":
        catalog["synthetic_cases"].append(deepcopy(case))
        catalog["synthetic_case_count"] += 1
    elif probe == "missing_path":
        for row in catalog["synthetic_cases"]:
            if row["module"] == "M00" and "denial" in row["required_paths"]:
                row["required_paths"].remove("denial")
    elif probe == "shrunk_module_baseline":
        catalog["required_modules"].pop()
    elif probe == "unknown_criterion":
        case["owner_criteria"][0] = "BK-999999-AC1"
    elif probe == "empty_fixture":
        case["inputs"].clear()
    elif probe == "missing_expected_value":
        del case["expected"][0]["value"]
    elif probe == "unknown_operator":
        case["expected"][0]["operator"] = "looks_good"
    elif probe == "empty_refusal":
        case["planted_negative"]["expected_refusal"] = " "
    elif probe == "claimed_pass":
        case["execution_status"] = "PASS"
    elif probe == "claimed_evidence":
        case["evidence"] = [{"result": "PASS"}]
    elif probe == "unknown_field":
        case["approved"] = True
    elif probe == "network_enabled":
        catalog["local_mode"]["default_network"] = "allow"
    elif probe == "empty_portfolios":
        catalog["release_portfolios"].clear()
    elif probe == "shrunk_portfolio_minimum":
        portfolio["minimum_count"] = 6
        for stratum in portfolio["primary_strata"]:
            stratum["minimum"] = 1
    elif probe == "strata_count_mismatch":
        portfolio["primary_strata"][0]["minimum"] += 1
    elif probe == "stratum_removed_count_preserved":
        removed = portfolio["primary_strata"].pop()
        portfolio["primary_strata"][0]["minimum"] += removed["minimum"]
    elif probe == "empty_overlay":
        portfolio["overlay_minima"].clear()
    elif probe == "placeholder_member":
        portfolio["members"] = [{"id": "placeholder"}]
    elif probe == "empty_protocols":
        catalog["manual_review_protocols"].clear()
    elif probe == "empty_review_tasks":
        catalog["manual_review_protocols"][0]["tasks"].clear()
    elif probe == "self_signed_review":
        catalog["manual_review_protocols"][0]["approvals"] = [True]
    assert catalog != original, "a probe that mutates nothing proves nothing"
    errors = check_evaluations(catalog, criteria)
    assert any(expected in error for error in errors), errors


def test_population_templates_can_never_confer_deployment_approval():
    catalog, _ = _inputs()
    for portfolio in catalog["release_portfolios"]:
        portfolio["members"] = [{"id": f"fake-{n}"} for n in range(portfolio["minimum_count"])]
    blockers = deployment_blockers(catalog)
    assert any("cannot grant deployment" in error for error in blockers)
    assert any("independent labels" in error for error in blockers)
    assert any("not qualified independent sign-off" in error for error in blockers)


@pytest.mark.parametrize("field, bad", [("operator", []), ("path", {}), ("operator", None)])
def test_malformed_observation_is_refused_without_crashing(field, bad):
    catalog, criteria = _inputs()
    assert field in catalog["synthetic_cases"][0]["expected"][0]
    catalog["synthetic_cases"][0]["expected"][0][field] = bad
    assert any("invalid observation" in error for error in check_evaluations(catalog, criteria))


@pytest.mark.parametrize("bad", [None, [], "", {"synthetic_cases": [None]}])
def test_malformed_catalog_is_an_explicit_failure_not_an_exception(bad):
    assert check_evaluations(bad, {"BK-82-AC1"})
    assert deployment_blockers(bad)
