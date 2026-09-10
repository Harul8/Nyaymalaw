"""Independent integration checks for autonomy planning, not runtime assurance."""

from __future__ import annotations

from copy import deepcopy

import pytest

from tools import blueprint
from tools.blueprint_evaluations import _check_autonomy_case

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("field,value", [
    ("max_concurrent_specialists", 1), ("max_delegation_depth", 2),
])
def test_budget_race_cannot_pass_via_an_unrelated_admission_limit(field, value):
    case = _one(blueprint.load_contracts()["evaluations"]["synthetic_cases"], "EVAL-032")
    baseline = []
    _check_autonomy_case(case, baseline)
    assert baseline == []
    assert case["inputs"]["parent"][field] != value
    case["inputs"]["parent"][field] = value
    errors = []
    _check_autonomy_case(case, errors)
    assert any("concurrency must not mask the budget race" in error for error in errors)

# Independently stated acceptance owners: not read back from the contract being checked.
OWNERS = {
    "AUTO-01": ("BK-91", "BK-91-AC1", "P46"),
    "AUTO-02": ("BK-91", "BK-91-AC2", "P46"),
    "AUTO-03": ("BK-91", "BK-91-AC3", "P24"),
    "AUTO-04": ("BK-91", "BK-91-AC4", "P35"),
    "AUTO-05": ("BK-92", "BK-92-AC1", "P47"),
    "AUTO-06": ("BK-92", "BK-92-AC2", "P47"),
    "AUTO-07": ("BK-92", "BK-92-AC3", "P29"),
    "AUTO-08": ("BK-92", "BK-92-AC4", "P37"),
}
CASE_OWNERS = {
    "EVAL-031": {"BK-91-AC1", "BK-91-AC2", "BK-91-AC3"},
    "EVAL-032": {"BK-92-AC1", "BK-92-AC2"},
    "EVAL-033": {"BK-92-AC3"},
    "EVAL-034": {"BK-91-AC4", "BK-92-AC4"},
}


def _inputs():
    modules, registry = blueprint.load()
    contracts = blueprint.load_contracts()
    assert blueprint.check_all(modules, registry, contracts) == []
    return modules, registry, contracts


def _one(rows, identifier):
    found = [row for row in rows if row["id"] == identifier]
    assert len(found) == 1
    return found[0]


def test_all_eight_autonomy_obligations_have_independent_exact_final_owners():
    _, registry, contracts = _inputs()
    rows = contracts["autonomy"]["obligations"]
    packets = contracts["packets"]["packets"]
    assert len(rows) == len(OWNERS) == 8
    assert {row["id"] for row in rows} == set(OWNERS)
    for identity, (item_id, criterion, packet) in OWNERS.items():
        row = _one(rows, identity)
        assert (row["item"], row["criterion"], row["packet"]) == (item_id, criterion, packet)
        item = _one(registry["items"], item_id)
        ac = _one(item["acceptance"], criterion)
        assert ac["requirement"].strip() and ac["required_evidence"] and ac["negative_control"]
        assert [p["id"] for p in packets if criterion in p["final_criteria"]] == [packet]
        assert criterion in _one(packets, packet)["criteria"]


def test_main_checker_requires_the_autonomy_contract_population():
    modules, registry, contracts = _inputs()
    assert contracts.pop("autonomy")
    assert blueprint.check_all(modules, registry, contracts) == [
        "execution contracts: unknown or missing population"
    ]


def test_main_checker_actually_calls_the_autonomy_safety_control():
    modules, registry, contracts = _inputs()
    policy = contracts["autonomy"]["grounding"]
    assert policy["source_instructions"] == "untrusted_evidence_never_authority"
    policy["source_instructions"] = "source_may_grant_authority"
    assert any(
        "autonomy grounding.source_instructions" in error
        for error in blueprint.check_all(modules, registry, contracts)
    )


@pytest.mark.parametrize("identity", list(OWNERS))
def test_removing_any_autonomy_final_owner_is_refused(identity):
    modules, registry, contracts = _inputs()
    _, criterion, packet_id = OWNERS[identity]
    packet = _one(contracts["packets"]["packets"], packet_id)
    assert packet["final_criteria"].count(criterion) == 1
    packet["final_criteria"].remove(criterion)
    errors = blueprint.check_all(modules, registry, contracts)
    assert any(f"no final owner for {criterion}" in error for error in errors), errors


def test_a_structurally_valid_new_packet_cannot_steal_the_registered_final_owner():
    modules, registry, contracts = _inputs()
    packets = contracts["packets"]["packets"]
    original = _one(packets, "P46")
    assert "BK-91-AC1" in original["criteria"] and "BK-91-AC1" in original["final_criteria"]
    substitute_id = f"P{max(int(row['id'][1:]) for row in packets) + 1:02}"
    assert not any(row["id"] == substitute_id for row in packets)
    substitute = deepcopy(original)
    substitute["id"] = substitute_id
    substitute["criteria"] = ["BK-91-AC1"]
    substitute["final_criteria"] = ["BK-91-AC1"]
    original["criteria"].remove("BK-91-AC1")
    original["final_criteria"].remove("BK-91-AC1")
    packets.append(substitute)
    errors = blueprint.check_all(modules, registry, contracts)
    assert errors == ["autonomy AUTO-01 BK-91-AC1: exact final packet owner differs"], errors


@pytest.mark.parametrize("item_id", ["BK-91", "BK-92"])
def test_new_runtime_work_cannot_hide_in_current_planning_exclusions(item_id):
    modules, registry, contracts = _inputs()
    exclusions = contracts["packets"]["planning_delivery_exclusions"]
    assert {row["item"] for row in exclusions} == {"BK-87", "BK-89", "BK-90"}
    assert not any(row["item"] == item_id for row in exclusions)
    exclusions.append({"item": item_id, "reason": "Pretend runtime work is only plan authoring."})
    errors = blueprint.check_all(modules, registry, contracts)
    assert any(
        "only the explained BK-87, BK-89 and BK-90 planning deliveries are excluded" in error
        for error in errors
    ), errors


def test_new_synthetic_cases_cover_exact_owners_without_claiming_execution():
    _, _, contracts = _inputs()
    cases = contracts["evaluations"]["synthetic_cases"]
    assert len(CASE_OWNERS) == 4
    covered = set()
    for identity, owners in CASE_OWNERS.items():
        case = _one(cases, identity)
        assert set(case["owner_criteria"]) == owners
        assert len(case["owner_criteria"]) == len(owners)
        covered.update(owners)
        assert case["proof_level"] == "specification"
        assert case["execution_status"] == "NOT_RUN" and case["evidence"] == []
        assert case["inputs"] and case["expected"] and case["sequence"] and case["live_observation"]
        assert case["planted_negative"]["mutation"].strip()
        assert case["planted_negative"]["expected_refusal"].strip()
    assert covered == {owner[1] for owner in OWNERS.values()}

    lead = _one(cases, "EVAL-031")["inputs"]
    assert len(lead["sources"]) >= 2 and len(lead["transformations"]) >= 3
    assert len({source["id"] for source in lead["sources"]}) == len(lead["sources"])
    assert all(
        source["text"].strip() and source["locator"].strip() and source["version"] > 0
        for source in lead["sources"]
    )
    delegated = _one(cases, "EVAL-032")["inputs"]
    assert len(delegated["attempts"]) == 2 and len(delegated["faults"]) >= 6
    assert sum(row["units"] for row in delegated["attempts"]) > delegated["parent"]["total_units"]
    draft = _one(cases, "EVAL-033")["inputs"]
    assert set(draft["formats"]) == {"docx", "pdf"}
    assert len(draft["accepted_package"]["claims"]) >= 2
    assert (
        draft["accepted_package"]["unknown_fields"]
        and draft["accepted_package"]["reservation"].strip()
    )
    comparison = _one(cases, "EVAL-034")["inputs"]
    assert len(comparison["modes"]) == 3 and len(comparison["task_families"]) >= 3
    assert type(comparison["repeats_per_family"]) is int and comparison["repeats_per_family"] > 1
    assert comparison["expected_run_records"] == (
        len(comparison["modes"])
        * len(comparison["task_families"])
        * comparison["repeats_per_family"]
    )


@pytest.mark.parametrize("identity", list(CASE_OWNERS))
def test_new_case_ownership_cannot_disappear_from_the_main_checker(identity):
    modules, registry, contracts = _inputs()
    case = _one(contracts["evaluations"]["synthetic_cases"], identity)
    assert case["owner_criteria"]
    case["owner_criteria"] = []
    errors = blueprint.check_all(modules, registry, contracts)
    assert any(
        identity in error and ("owner" in error or "criteria" in error) for error in errors
    ), errors


@pytest.mark.parametrize("identity", list(CASE_OWNERS))
def test_valid_but_wrong_case_owner_cannot_hide_autonomy_work(identity):
    modules, registry, contracts = _inputs()
    case = _one(contracts["evaluations"]["synthetic_cases"], identity)
    assert "BK-64-AC1" not in case["owner_criteria"]
    assert any(
        ac["id"] == "BK-64-AC1" for row in registry["items"] for ac in row.get("acceptance", [])
    )
    before = list(case["owner_criteria"])
    case["owner_criteria"][0] = "BK-64-AC1"
    assert case["owner_criteria"] != before
    errors = blueprint.check_all(modules, registry, contracts)
    assert any(
        identity in error and ("owner" in error or "criteria" in error) for error in errors
    ), errors


@pytest.mark.parametrize(
    "identity,path",
    [
        ("EVAL-031", ("sources",)),
        ("EVAL-032", ("attempts",)),
        ("EVAL-033", ("accepted_package", "claims")),
        ("EVAL-034", ("task_families",)),
    ],
)
def test_new_case_substantive_populations_cannot_become_empty(identity, path):
    modules, registry, contracts = _inputs()
    case = _one(contracts["evaluations"]["synthetic_cases"], identity)
    target = case["inputs"]
    for key in path[:-1]:
        assert key in target and isinstance(target[key], dict)
        target = target[key]
    key = path[-1]
    assert key in target and isinstance(target[key], list) and target[key]
    target[key] = []
    errors = blueprint.check_all(modules, registry, contracts)
    assert any(identity in error and "autonomy" in error for error in errors), errors


def test_planning_proof_is_not_authored_as_unbuilt_product_evidence():
    _, registry, contracts = _inputs()
    inspected = []
    for item_id in ("BK-91", "BK-92"):
        item = _one(registry["items"], item_id)
        assert not item.get("legacy", False)
        assert len(item["acceptance"]) == 4
        for ac in item["acceptance"]:
            inspected.append(ac["id"])
            assert set(ac["required_evidence"]) - {"domain_test", "adversarial_test"}
            if item["implementation"] == "none":
                assert ac["evidence"] == {}, (
                    "No runtime implementation can borrow the static plan's PASS."
                )
    assert set(inspected) == {owner[1] for owner in OWNERS.values()}
    assert contracts["autonomy"]["evidence"] == []
    planning = _one(registry["items"], "BK-90")
    assert all(
        set(ac["required_evidence"]) <= {"domain_test", "adversarial_test"}
        for ac in planning["acceptance"]
    )


@pytest.mark.parametrize(
    "identity,path,replacement",
    [
        ("EVAL-031", "observed.lead_steps", 0),
        ("EVAL-031", "served.unsupported_material_claims", False),
        ("EVAL-032", "observed.ordinary_children_completed", 0),
        ("EVAL-032", "budget.race_admitted_children", 0),
        ("EVAL-033", "artifacts.pages_inspected", 0),
        ("EVAL-033", "persistence.stale_draft_issued_as_current", 0),
        ("EVAL-034", "comparison.observed_run_records", 0),
        ("EVAL-034", "comparison.scripted_fixture_claims_professional_approval", True),
    ],
)
def test_positive_operation_and_strict_observation_floors_refuse_weakening(
    identity, path, replacement
):
    case = _one(blueprint.load_contracts()["evaluations"]["synthetic_cases"], identity)
    errors = []
    _check_autonomy_case(case, errors)
    assert errors == []
    selected = [row for row in case["expected"] if row["path"] == path]
    assert len(selected) == 1
    row = selected[0]
    assert type(row["value"]) is not type(replacement) or row["value"] != replacement
    row["value"] = replacement
    _check_autonomy_case(case, errors)
    assert any(identity in error and path in error for error in errors), errors


@pytest.mark.parametrize("identity", list(CASE_OWNERS))
def test_missing_observation_is_not_an_authored_zero_success(identity):
    case = _one(blueprint.load_contracts()["evaluations"]["synthetic_cases"], identity)
    matches = [row for row in case["expected"] if row["path"] == "observed.missing_required_fields"]
    assert len(matches) == 1
    case["expected"].remove(matches[0])
    errors = []
    _check_autonomy_case(case, errors)
    assert any(
        "observed.missing_required_fields" in error and "missing" in error for error in errors
    )


def test_fixture_controls_allow_new_names_text_and_larger_valid_repetition_population():
    cases = blueprint.load_contracts()["evaluations"]["synthetic_cases"]
    lead = _one(cases, "EVAL-031")
    for index, source in enumerate(lead["inputs"]["sources"]):
        source["id"] = f"unfamiliar-source-{index}"
        source["text"] = (
            f"An unfamiliar supplied statement {index}; "
            "its legal meaning still needs independent review."
        )
    comparison = _one(cases, "EVAL-034")
    comparison["inputs"]["repeats_per_family"] = 3
    count = len(comparison["inputs"]["modes"]) * len(comparison["inputs"]["task_families"]) * 3
    comparison["inputs"]["expected_run_records"] = count
    for row in comparison["expected"]:
        if row["path"] in {"comparison.expected_run_records", "comparison.observed_run_records"}:
            row["value"] = count
    errors = []
    _check_autonomy_case(lead, errors)
    _check_autonomy_case(comparison, errors)
    assert errors == []
