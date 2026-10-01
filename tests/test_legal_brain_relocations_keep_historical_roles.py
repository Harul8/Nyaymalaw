"""A second physical move cannot rewrite historical owners or their permissions."""
import json
from collections import Counter

import pytest

from assurance.common.module_roles import (
    LayoutError,
    current_module,
    legacy_modules,
    load_module_roles,
    original_stem,
)

CURRENT = "nm/source_layout.json"
HISTORY = "assurance/common/journey_layout.json"
RELOCATION = "assurance/common/legal_brain_layout.json"


def _write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf8")


def _row(before, after, role, *, original=False):
    return {"old_module": before, "module": after, "role": role,
            "old_path": ("backend/" if original else "") + before.replace(".", "/") + ".py",
            "path": after.replace(".", "/") + ".py", "sha256_before": "0" * 64}


def _tree(root):
    roles = {"nm": "domain", "nm.Archives": "domain",
             "nm.Archives.legal_brain": "domain",
             "nm.Archives.legal_brain.understand": "domain",
             "nm.Archives.legal_brain.common": "domain",
             "nm.Archives.legal_brain.communicate": "domain",
             "nm.Archives.legal_brain.understand.reading": "core",
             "nm.Archives.legal_brain.common.contracts": "ports",
             "nm.Archives.legal_brain.understand.tool_ask_advocate": "core"}
    packages = {"nm", "nm.Archives", "nm.Archives.legal_brain",
                "nm.Archives.legal_brain.understand",
                "nm.Archives.legal_brain.common",
                "nm.Archives.legal_brain.communicate"}
    for module in roles:
        relative = module.replace(".", "/")
        path = root / (relative + ("/__init__.py" if module in packages else ".py"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf8")
    asset_path = "nm/Archives/legal_brain/communicate/sources.js"
    historical_asset_path = "nm/legal_brain/communicate/sources.js"
    (root / asset_path).write_text("/* source reader */", encoding="utf8")
    current = {"schema": 1, "modules": roles,
               "expected_roles": dict(Counter(roles.values())),
               "browser_assets": {"sources.js": asset_path}}
    history_rows = [_row("nm.core.original_read", "nm.legal_brain.reading", "core", original=True),
                    _row("nm.ports.contracts", "nm.legal_brain.contracts", "ports", original=True)]
    history = {"schema": 1, "phases": ["legal_brain"], "modules": history_rows,
               "expected_roles": dict(Counter(row["role"] for row in history_rows)),
               "browser_assets": {"sources.js": "nm/legal_brain/sources.js"},
               "moves": [], "package_notes": []}
    relocated_rows = [_row("nm.legal_brain.reading", "nm.legal_brain.understand.reading", "core"),
                      _row("nm.legal_brain.contracts", "nm.legal_brain.common.contracts", "ports"),
                      _row("nm.legal_brain.tool_ask_advocate",
                           "nm.legal_brain.understand.tool_ask_advocate", "core")]
    relocation = {"schema": 1, "modules": relocated_rows,
                  "expected_roles": dict(Counter(row["role"] for row in relocated_rows)),
                  "browser_assets": {"sources.js": {
                      "old_path": "nm/legal_brain/sources.js", "path": historical_asset_path,
                      "sha256_before": "0" * 64}}}
    for name, value in [(CURRENT, current), (HISTORY, history), (RELOCATION, relocation)]:
        _write(root, name, value)
    return current, history, relocation


def test_original_and_first_journey_identities_compose_without_rewriting_history(tmp_path):
    current, _, _ = _tree(tmp_path)
    history_before = (tmp_path / HISTORY).read_bytes()
    layout = load_module_roles(root=tmp_path)
    assert set(layout.roles) == set(current["modules"])
    assert legacy_modules(root=tmp_path) == {
        "nm.core.original_read": "nm.Archives.legal_brain.understand.reading",
        "nm.ports.contracts": "nm.Archives.legal_brain.common.contracts",
    }
    for before in ["nm.core.original_read", "nm.legal_brain.reading",
                   "nm.legal_brain.understand.reading",
                   "nm.Archives.legal_brain.understand.reading"]:
        assert current_module(before, root=tmp_path) == (
            "nm.Archives.legal_brain.understand.reading"
        )
    assert current_module("nm.legal_brain.tool_ask_advocate", root=tmp_path) == (
        "nm.Archives.legal_brain.understand.tool_ask_advocate"
    )
    assert original_stem(tmp_path / "nm/Archives/legal_brain/understand/reading.py", root=tmp_path) == (
        "original_read"
    )
    assert (tmp_path / HISTORY).read_bytes() == history_before


@pytest.mark.parametrize("module", ["nm.Archives.legal_brain.understand.reading",
                                   "nm.Archives.legal_brain.understand.tool_ask_advocate"])
def test_both_historical_and_later_tool_roles_survive_adjusted_current_counts(tmp_path, module):
    current, _, _ = _tree(tmp_path)
    current["modules"][module] = "adapters"
    current["expected_roles"] = dict(Counter(current["modules"].values()))
    _write(tmp_path, CURRENT, current)
    with pytest.raises(LayoutError, match="owners missing or reclassified"):
        load_module_roles(root=tmp_path)


def test_a_new_relocation_cannot_overrule_an_original_role(tmp_path):
    current, _, relocation = _tree(tmp_path)
    current["modules"]["nm.Archives.legal_brain.understand.reading"] = "adapters"
    current["expected_roles"] = dict(Counter(current["modules"].values()))
    relocation["modules"][0]["role"] = "adapters"
    relocation["expected_roles"] = dict(Counter(row["role"] for row in relocation["modules"]))
    _write(tmp_path, CURRENT, current)
    _write(tmp_path, RELOCATION, relocation)
    with pytest.raises(LayoutError, match="migrated source owners"):
        load_module_roles(root=tmp_path)


@pytest.mark.parametrize("change", [
    "missing", "schema_bool", "extra_field", "empty", "missing_original", "duplicate",
    "wrong_count", "bool_count", "unknown_role", "bad_row", "invalid_digest",
    "outside_phase", "unknown_stage", "rename", "wrong_source_path", "wrong_target_path",
])
def test_a_missing_partial_or_malformed_second_move_never_partially_resolves(tmp_path, change):
    _, _, relocation = _tree(tmp_path)
    row = relocation["modules"][0]
    if change == "missing":
        (tmp_path / RELOCATION).unlink()
    elif change == "schema_bool":
        relocation["schema"] = True
    elif change == "extra_field":
        relocation["approved"] = True
    elif change == "empty":
        relocation["modules"] = []
        relocation["expected_roles"] = {}
    elif change == "missing_original":
        relocation["modules"].pop(0)
        relocation["expected_roles"] = dict(Counter(r["role"] for r in relocation["modules"]))
    elif change == "duplicate":
        relocation["modules"].append(dict(row))
    elif change == "wrong_count":
        relocation["expected_roles"]["core"] += 1
    elif change == "bool_count":
        relocation["expected_roles"]["core"] = True
    elif change == "unknown_role":
        row["role"] = "unrestricted"
    elif change == "bad_row":
        row["approved"] = True
    elif change == "invalid_digest":
        row["sha256_before"] = "not-a-digest"
    elif change == "outside_phase":
        row["old_module"] = "nm.shared.reading"
        row["old_path"] = "nm/shared/reading.py"
    elif change == "unknown_stage":
        row["module"] = "nm.legal_brain.unrestricted.reading"
        row["path"] = "nm/legal_brain/unrestricted/reading.py"
    elif change == "rename":
        row["module"] = "nm.legal_brain.understand.some_other_owner"
        row["path"] = "nm/legal_brain/understand/some_other_owner.py"
    elif change == "wrong_source_path":
        row["old_path"] = "nm/legal_brain/other.py"
    else:
        row["path"] = "nm/legal_brain/understand/other.py"
    if change != "missing":
        _write(tmp_path, RELOCATION, relocation)
    with pytest.raises(LayoutError):
        load_module_roles(root=tmp_path)
    with pytest.raises(LayoutError):
        current_module("nm.core.original_read", root=tmp_path)


@pytest.mark.parametrize("change", ["missing", "stale_served_target", "outside_phase",
                                    "wrong_filename", "invalid_digest", "extra_field"])
def test_browser_relocations_are_exact_and_bound_to_the_served_owner(tmp_path, change):
    current, _, relocation = _tree(tmp_path)
    asset = relocation["browser_assets"]["sources.js"]
    if change == "missing":
        relocation["browser_assets"] = {}
    elif change == "stale_served_target":
        current["browser_assets"]["sources.js"] = "nm/legal_brain/sources.js"
        _write(tmp_path, CURRENT, current)
    elif change == "outside_phase":
        asset["path"] = "nm/shared/communicate/sources.js"
    elif change == "wrong_filename":
        asset["path"] = "nm/legal_brain/communicate/private.py"
    elif change == "invalid_digest":
        asset["sha256_before"] = False
    else:
        asset["approved"] = True
    _write(tmp_path, RELOCATION, relocation)
    with pytest.raises(LayoutError):
        load_module_roles(root=tmp_path)


def test_leaving_the_old_python_copy_is_not_accepted_as_a_compatibility_alias(tmp_path):
    _tree(tmp_path)
    (tmp_path / "nm/legal_brain").mkdir()
    (tmp_path / "nm/legal_brain/reading.py").write_text("", encoding="utf8")
    with pytest.raises(LayoutError, match="unclassified"):
        load_module_roles(root=tmp_path)


def test_historical_custody_hashes_are_not_a_claim_of_current_verified_bytes(tmp_path):
    _tree(tmp_path)
    path = tmp_path / "nm/Archives/legal_brain/understand/reading.py"
    path.write_text('"""A later independently tested change."""\n', encoding="utf8")
    assert load_module_roles(root=tmp_path).role(
        "nm.Archives.legal_brain.understand.reading") == "core"
