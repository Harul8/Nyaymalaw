"""Non-vacuous controls for the blueprint's navigation contract only."""
from __future__ import annotations

from copy import deepcopy

import pytest

from tools import blueprint

pytestmark = pytest.mark.class_a


def test_blueprint_covers_current_registry_and_resolves_guides():
    manifest, registry = blueprint.load()
    assert len(manifest["modules"]) == 13
    assert len(registry["features"]) == 44
    assert len(registry["steps"]) == 47
    assert len(registry["items"]) >= 95
    assert blueprint.check(manifest, registry) == []


def test_all_execution_contracts_reconcile_without_conveying_release_authority():
    manifest, registry = blueprint.load()
    contracts = blueprint.load_contracts()
    assert blueprint.check_all(manifest, registry, contracts) == []
    blockers = blueprint.readiness_blockers(contracts)
    assert any("CHOICE-01" in value for value in blockers)
    assert any("PORT-JOURNEY" in value for value in blockers)
    assert any("cannot authorise" in value for value in blockers)


def test_contract_loader_refuses_duplicate_json_keys():
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        blueprint._unique_keys([("schema", 1), ("schema", 2)])


@pytest.mark.parametrize("probe,expected", [
    ("empty_modules", "modules: empty"),
    ("missing_module", "expected exactly"),
    ("duplicate_module", "expected exactly"),
    ("missing_owner", "items: unmapped"),
    ("duplicate_owner", "items: duplicate owner"),
    ("unknown_work", "items: unknown BK-999999"),
    ("missing_feature", "features: unmapped"),
    ("missing_step", "steps: unmapped"),
    ("empty_registry", "items: registry population empty"),
    ("new_registry_work", "items: unmapped BK-999999"),
    ("cycle", "dependency cycle"),
    ("unknown_dependency", "invalid prerequisite"),
    ("authored_status", "authored status is forbidden"),
    ("missing_guide", "guide missing or unknown"),
    ("malformed_mapping", "malformed items mapping"),
])
def test_blueprint_planted_failures(probe, expected):
    manifest, registry = blueprint.load()
    assert blueprint.check(manifest, registry) == []
    original = deepcopy((manifest, registry))
    modules = manifest["modules"]
    if probe == "empty_modules":
        modules.clear()
    elif probe == "missing_module":
        modules.pop()
    elif probe == "duplicate_module":
        modules.append(deepcopy(modules[0]))
    elif probe == "missing_owner":
        assert modules[0]["items"]
        modules[0]["items"].pop()
    elif probe == "duplicate_owner":
        modules[1]["items"].append(modules[0]["items"][0])
    elif probe == "unknown_work":
        modules[0]["items"].append("BK-999999")
    elif probe == "missing_feature":
        assert modules[1]["features"]
        modules[1]["features"].pop()
    elif probe == "missing_step":
        assert modules[1]["steps"]
        modules[1]["steps"].pop()
    elif probe == "empty_registry":
        registry["items"].clear()
    elif probe == "new_registry_work":
        registry["items"].append({"id": "BK-999999"})
    elif probe == "cycle":
        modules[0]["requires"].append("M01")
    elif probe == "unknown_dependency":
        modules[0]["requires"].append("M99")
    elif probe == "authored_status":
        assert "status" not in modules[0]
        modules[0]["status"] = "done"
    elif probe == "missing_guide":
        modules[0]["guide"] = "DOES_NOT_EXIST.md"
    elif probe == "malformed_mapping":
        modules[0]["items"] = None
    assert (manifest, registry) != original, "a probe that mutates nothing proves nothing"
    assert any(expected in error for error in blueprint.check(manifest, registry))
