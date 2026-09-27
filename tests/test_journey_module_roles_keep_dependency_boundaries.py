"""The physical journey move cannot grant roles or lose security populations."""
import json
from collections import Counter

import pytest

from assurance.common.module_roles import (
    ROLES,
    LayoutError,
    classify_sources,
    load_module_roles,
    source_module,
)
from assurance.gate.layercheck import ALLOWED, main
from tests.source_role_fixtures import role_tree


def test_the_authored_dependency_matrix_has_not_been_relaxed():
    expected = {
        "domain": {"domain"}, "ports": {"ports", "domain"},
        "core": {"core", "ports", "domain"},
        "adapters": {"adapters", "ports", "domain", "core", "knowledge", "infrastructure"},
        "knowledge": {"knowledge", "ports", "domain", "infrastructure"},
        "infrastructure": {"infrastructure"}, "edge": {"edge", "core", "ports", "domain"},
        "drafting": {"drafting", "ports", "domain"}, "obs": {"obs", "ports", "domain"},
        "bootstrap": {"bootstrap", "domain", "ports", "core", "adapters", "knowledge",
                      "edge", "infrastructure"},
    }
    assert ALLOWED == expected


def _manifests(root, roles):
    current = {"schema": 1, "modules": dict(roles),
               "expected_roles": dict(Counter(roles.values())), "browser_assets": {}}
    migrated = []
    for index, (module, role) in enumerate(roles.items()):
        if module in {"nm", "nm.shared", "nm.work_the_file"}:
            continue
        old = f"nm.{role}.original{index}"
        migrated.append({"old_module": old, "module": module, "role": role,
                         "old_path": "backend/" + old.replace(".", "/") + ".py",
                         "path": module.replace(".", "/") + ".py",
                         "sha256_before": "0" * 64})
    history = {"schema": 1, "phases": ["work_the_file", "shared"], "modules": migrated,
               "expected_roles": dict(Counter(row["role"] for row in migrated)),
               "browser_assets": {}, "moves": [], "package_notes": []}
    (root / "assurance/common").mkdir(parents=True, exist_ok=True)
    (root / "nm/source_layout.json").write_text(json.dumps(current), encoding="utf8")
    (root / "assurance/common/journey_layout.json").write_text(json.dumps(history), encoding="utf8")
    return current, history


@pytest.mark.parametrize("role,target", [(role, target) for role in sorted(ROLES)
                                         for target in sorted(ROLES)])
def test_the_original_role_matrix_is_enforced_across_journey_files(tmp_path, role, target, capsys):
    roles = role_tree(tmp_path, "from nm.shared.target import value\n",
                      role=role, target_role=target)
    allowed = target in ALLOWED[role]
    assert main(root=tmp_path, roles=roles) == (0 if allowed else 1)
    output = capsys.readouterr().out
    assert ("may not import" in output) is not allowed


@pytest.mark.parametrize("statement,target,expected", [
    ("from ..shared.target import value", "adapters", 1),
    ("from ..shared.target import value", "ports", 0),
    ("from nm.shared import target", "adapters", 1),
    ("from nm.shared import target", "domain", 0),
    ("from nm.shared.unregistered import value", "domain", 1),
])
def test_relative_and_package_child_imports_do_not_hide_the_target_role(
    tmp_path, statement, target, expected,
):
    roles = role_tree(tmp_path, statement, target_role=target)
    assert main(root=tmp_path, roles=roles) == expected


def test_empty_or_missing_source_trees_never_pass(tmp_path):
    assert main(root=tmp_path, roles={"nm": "domain"}) == 1
    (tmp_path / "nm").mkdir()
    assert main(root=tmp_path, roles={"nm": "domain"}) == 1


def test_actual_unknown_and_declared_missing_modules_are_both_refused(tmp_path):
    roles = role_tree(tmp_path, "")
    with pytest.raises(LayoutError, match="unclassified"):
        classify_sources(root=tmp_path, roles={key: value for key, value in roles.items()
                                               if key != "nm.work_the_file.probe"})
    with pytest.raises(LayoutError, match="missing"):
        classify_sources(root=tmp_path, roles={**roles, "nm.shared.missing": "core"})


def test_initializers_are_explicitly_classified_and_checked(tmp_path, capsys):
    roles = role_tree(tmp_path, "")
    path = tmp_path / "nm/__init__.py"
    path.write_text("import openai\n", encoding="utf8")
    assert source_module(path, root=tmp_path) == "nm"
    assert main(root=tmp_path, roles=roles) == 1
    assert "nm.core" not in capsys.readouterr().out


def test_a_package_and_module_cannot_share_one_declared_identity(tmp_path):
    roles = role_tree(tmp_path, "")
    (tmp_path / "nm/shared.py").write_text("", encoding="utf8")
    with pytest.raises(LayoutError, match="duplicate source identity"):
        classify_sources(root=tmp_path, roles=roles)


@pytest.mark.parametrize("change", ["schema_bool", "extra_field", "empty_roles", "unknown_role",
                                    "bad_role_shape", "bool_count", "wrong_count"])
def test_malformed_current_role_metadata_is_not_partial(tmp_path, change):
    roles = role_tree(tmp_path, "")
    current, _ = _manifests(tmp_path, roles)
    if change == "schema_bool":
        current["schema"] = True
    elif change == "extra_field":
        current["approved"] = True
    elif change == "empty_roles":
        current["modules"] = {}
    elif change == "unknown_role":
        current["modules"]["nm"] = "everything"
    elif change == "bad_role_shape":
        current["modules"]["nm"] = []
    elif change == "bool_count":
        current["expected_roles"]["core"] = True
    else:
        current["expected_roles"]["core"] += 1
    (tmp_path / "nm/source_layout.json").write_text(json.dumps(current), encoding="utf8")
    with pytest.raises(LayoutError):
        load_module_roles(root=tmp_path)


@pytest.mark.parametrize("member", ["nm/source_layout.json",
                                    "assurance/common/journey_layout.json"])
def test_duplicate_json_keys_in_either_owner_are_refused(tmp_path, member):
    roles = role_tree(tmp_path, "")
    _manifests(tmp_path, roles)
    path = tmp_path / member
    body = path.read_text(encoding="utf8")
    path.write_text(body.replace('"schema": 1', '"schema": 1, "schema": 1'), encoding="utf8")
    with pytest.raises(LayoutError, match="duplicate layout key"):
        load_module_roles(root=tmp_path)


@pytest.mark.parametrize("change", ["remove", "reclassify"])
def test_current_counts_cannot_erase_or_upgrade_a_migrated_owner(tmp_path, change):
    roles = role_tree(tmp_path, "")
    current, _ = _manifests(tmp_path, roles)
    if change == "remove":
        del current["modules"]["nm.work_the_file.probe"]
        (tmp_path / "nm/work_the_file/probe.py").unlink()
    else:
        current["modules"]["nm.work_the_file.probe"] = "adapters"
    current["expected_roles"] = dict(Counter(current["modules"].values()))
    (tmp_path / "nm/source_layout.json").write_text(json.dumps(current), encoding="utf8")
    with pytest.raises(LayoutError, match="migrated source owners"):
        load_module_roles(root=tmp_path)


def test_a_new_authored_role_slot_has_no_fabricated_old_origin(tmp_path):
    roles = role_tree(tmp_path, "")
    current, _ = _manifests(tmp_path, roles)
    current["modules"]["nm.shared.new_tool"] = "core"
    current["expected_roles"] = dict(Counter(current["modules"].values()))
    (tmp_path / "nm/shared/new_tool.py").write_text("", encoding="utf8")
    (tmp_path / "nm/source_layout.json").write_text(json.dumps(current), encoding="utf8")
    layout = load_module_roles(root=tmp_path)
    assert layout.role("nm.shared.new_tool") == "core"
    assert len(layout.paths) == len(roles) + 1


def test_missing_migration_owner_does_not_forge_preserved_roles(tmp_path):
    roles = role_tree(tmp_path, "")
    _manifests(tmp_path, roles)
    (tmp_path / "assurance/common/journey_layout.json").unlink()
    with pytest.raises(LayoutError, match="cannot read source layout"):
        load_module_roles(root=tmp_path)


def test_real_tree_reconciles_all_current_files_and_historical_owners():
    layout = load_module_roles()
    assert len(layout.paths) >= 293
    assert len(layout.sources_for_roles("core")) >= 109
    assert len(layout.sources_for_roles("ports")) >= 24
