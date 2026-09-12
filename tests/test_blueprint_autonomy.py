"""Non-vacuous design mutations, not evidence of autonomous runtime behaviour."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools._documents import safe_load
from tools.blueprint_autonomy import (
    BOUNDARIES,
    COMPARISON_POLICIES,
    COMPARISON_SETS,
    FIELD_TYPES,
    POLICIES,
    check_contract,
    load_contract,
)

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def _registered():
    registry = safe_load((ROOT / "docs/backlog/status.yaml").read_text(encoding="utf-8"))
    packet_book = json.loads((ROOT / "docs/blueprint/packets.json").read_text(encoding="utf-8"))
    return {
        "known_items": {row["id"] for row in registry["items"]},
        "known_criteria": {
            ac["id"] for row in registry["items"] for ac in row.get("acceptance", [])
        },
        "known_packets": {row["id"] for row in packet_book["packets"]},
    }


def _target(root, path):
    node = root
    for part in path[:-1]:
        assert (
            part in node
            if isinstance(node, dict)
            else isinstance(part, int) and 0 <= part < len(node)
        )
        node = node[part]
    key = path[-1]
    assert key in node if isinstance(node, dict) else isinstance(key, int) and 0 <= key < len(node)
    return node, key


def _reject_changed(path, replacement, complaint):
    contract = load_contract()
    assert check_contract(contract) == []
    original = deepcopy(contract)
    node, key = _target(contract, path)
    assert type(node[key]) is not type(replacement) or node[key] != replacement
    node[key] = replacement
    assert json.dumps(contract, sort_keys=True) != json.dumps(original, sort_keys=True)
    errors = check_contract(contract)
    assert any(complaint in error for error in errors), errors
    assert check_contract(original) == []


def test_autonomy_contract_is_registered_and_not_runtime_evidence():
    contract = load_contract()
    assert check_contract(contract, **_registered()) == []
    assert len(contract["obligations"]) == 8
    assert {row["id"] for row in contract["roles"]} == {"lead", "research", "draft_document"}
    assert contract["execution_status"] == "NOT_RUN" and contract["evidence"] == []
    assert len(contract["comparison"]["modes"]) == 3
    assert len(contract["comparison"]["required_paths"]) == 11


@pytest.mark.parametrize(
    "group,key", [(group, key) for group, fields in FIELD_TYPES.items() for key in fields]
)
def test_every_minimum_field_type_refuses_weakening(group, key):
    _reject_changed((group, key), "unrestricted_free_text", f"{group}.{key}")


@pytest.mark.parametrize(
    "group,key", [(group, key) for group, policy in POLICIES.items() for key in policy]
)
def test_every_grounding_and_lifecycle_policy_refuses_weakening(group, key):
    _reject_changed((group, key), "model_decides_without_guard", f"{group}.{key}")


@pytest.mark.parametrize("group", list(FIELD_TYPES))
def test_empty_typed_populations_cannot_pass(group):
    _reject_changed((group,), {}, f"{group}: nonempty")


@pytest.mark.parametrize("key", list(BOUNDARIES))
def test_authority_boundary_cannot_be_removed(key):
    _reject_changed(("control_boundary", key), [], f"control_boundary.{key}")


@pytest.mark.parametrize("key", list(COMPARISON_SETS))
def test_comparison_populations_are_not_vacuous(key):
    _reject_changed(("comparison", key), [], f"comparison.{key}")


@pytest.mark.parametrize("key", list(COMPARISON_POLICIES))
def test_comparison_cannot_self_certify(key):
    _reject_changed(("comparison", key), "accept_model_verdict", f"comparison.{key}")


@pytest.mark.parametrize(
    "path,replacement,complaint",
    [
        (("schema_version",), True, "schema_version"),
        (("execution_status",), "PASS", "execution_status"),
        (("proof_level",), "runtime", "proof_level"),
        (("evidence",), ["a claimed run"], "evidence"),
        (("purpose",), " ", "purpose"),
        (("roles",), [], "roles: nonempty"),
        (("roles", 0, "optional"), True, "roles.lead"),
        (("roles", 1, "optional"), 1, "roles.research"),
        (("roles", 2, "id"), "unrestricted_shell", "roles: unsupported"),
        (("roles", 0, "purpose"), "", "roles.lead"),
        (("obligations",), [], "obligations: nonempty"),
        (("obligations", 0, "requirement"), "", "AUTO-01: substantive"),
        (("obligations", 0, "criterion"), "BK-91-AC2", "AUTO-01: exact"),
        (("obligations", 0, "packet"), "P22", "AUTO-01: exact"),
        (("obligations", 0, "item"), "BK-90", "AUTO-01: exact"),
        (("obligations", 0, "id"), "AUTO-99", "obligations: unknown"),
        (("initial_profile", "status"), "approved", "initial_profile.status"),
        (("initial_profile", "max_concurrent_specialists"), 0, "initial_profile.max_concurrent"),
        (("initial_profile", "max_delegation_depth"), True, "initial_profile.max_delegation"),
        (("initial_profile", "specialists_may_delegate"), True, "initial_profile.specialists"),
        (("initial_profile", "budget_dimensions"), [], "initial_profile.budget_dimensions"),
    ],
)
def test_actual_changed_input_refuses_specific_planted_failure(path, replacement, complaint):
    _reject_changed(path, replacement, complaint)


@pytest.mark.parametrize("field", ["roles", "obligations"])
def test_duplicate_and_deleted_rows_do_not_pass_even_if_count_is_preserved(field):
    contract = load_contract()
    population = contract[field]
    assert len(population) > 1 and population[0]["id"] != population[1]["id"]
    population[0] = deepcopy(population[1])
    assert any(field in error and "duplicate" in error for error in check_contract(contract))


@pytest.mark.parametrize("field", ["known_items", "known_criteria", "known_packets"])
def test_external_registration_population_may_not_be_empty(field):
    contract = load_contract()
    populations = _registered()
    assert populations[field]
    populations[field] = set()
    errors = check_contract(contract, **populations)
    assert len([error for error in errors if "is not registered" in error]) == 8


@pytest.mark.parametrize(
    "field", ["grounding", "lifecycle", "control_boundary", "initial_profile", "comparison"]
)
def test_unknown_or_missing_control_fields_are_not_silently_ignored(field):
    contract = load_contract()
    assert "silent_override" not in contract[field]
    contract[field]["silent_override"] = True
    assert any(
        f"{field}: missing or unexpected fields" in error for error in check_contract(contract)
    )


@pytest.mark.parametrize("bad", [None, [], True, "contract"])
def test_malformed_root_is_an_explicit_design_error(bad):
    assert check_contract(bad) == ["autonomy contract: expected object"]


def test_the_contract_does_not_close_the_legal_universe_or_require_one_action_trace():
    contract = load_contract()
    contract["task_fields"]["additional_grounded_question"] = "nonempty_text"
    contract["obligations"][0]["requirement"] = (
        "Investigate any supported new issue within scope and replan on evidence."
    )
    contract["control_boundary"]["dynamic_actions"].reverse()
    contract["comparison"]["required_paths"].reverse()
    assert check_contract(contract) == []


def test_unknown_top_level_controls_are_not_silently_ignored():
    contract = load_contract()
    assert "runtime_approved" not in contract
    contract["runtime_approved"] = True
    assert "autonomy contract: missing or unexpected fields" in check_contract(contract)
